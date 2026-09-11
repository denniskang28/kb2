"""Fixed local sidecar executing only repository-registered plugin bindings."""
from __future__ import annotations

import asyncio
import base64
from uuid import UUID

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from kb2_runtime.trace.contracts import ArtifactReference

from .contracts import ArtifactInput, PluginContext, RunnerType, StageInvocation
from .bootstrap import bootstrap_registry
from .errors import PluginError, PluginErrorCode
from .registry import PluginRegistry
from .runner import InProcessRunner


class _WireInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    reference: ArtifactReference
    content: str = Field(max_length=24 * 1024 * 1024)


class _WireRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    invocation: StageInvocation
    inputs: tuple[_WireInput, ...] = Field(max_length=64)
    cancelled: bool = False


class _SidecarContext:
    def __init__(self, invocation: StageInvocation, inputs: dict[UUID, ArtifactInput], cancellation: asyncio.Event) -> None:
        self.invocation, self._inputs = invocation, inputs
        self.cancellation = cancellation

    async def input(self, artifact_id: UUID) -> ArtifactInput:
        try:
            return self._inputs[artifact_id]
        except KeyError as exc:
            raise PluginError(PluginErrorCode.RESULT_INVALID) from exc


def create_runner_app(registry: PluginRegistry) -> FastAPI:
    app = FastAPI(title="KB2 Plugin Runner", docs_url=None, redoc_url=None)
    cancellations: dict[UUID, asyncio.Event] = {}

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ready": True}

    @app.post("/invoke")
    async def invoke(request: _WireRequest) -> JSONResponse:
        cancellation = asyncio.Event()
        if request.cancelled:
            cancellation.set()
        cancellations[request.invocation.stage_attempt_id] = cancellation
        try:
            registration = registry.get(request.invocation.plugin_id)
            descriptor = registration.descriptor
            if descriptor.runner is not RunnerType.CONTAINER or descriptor.implementation_digest != request.invocation.implementation_digest:
                raise PluginError(PluginErrorCode.NOT_REGISTERED)
            validated = registration.configuration_model.model_validate(request.invocation.validated_configuration).model_dump(mode="json")
            if validated != request.invocation.validated_configuration:
                raise PluginError(PluginErrorCode.RESULT_INVALID)
            if tuple(item.reference for item in request.inputs) != request.invocation.inputs:
                raise PluginError(PluginErrorCode.RESULT_INVALID)
            inputs: dict[UUID, ArtifactInput] = {}
            for item in request.inputs:
                if (item.reference.artifact_type, item.reference.schema_revision) not in descriptor.input_schemas:
                    raise PluginError(PluginErrorCode.RESULT_INVALID)
                inputs[item.reference.id] = ArtifactInput(reference=item.reference, content=base64.b64decode(item.content, validate=True))
            result = await InProcessRunner().invoke(registration.factory(), request.invocation, _SidecarContext(request.invocation, inputs, cancellation))
            body = result.model_dump(mode="json")
            for output, source in zip(body["outputs"], result.outputs, strict=True):
                output["content"] = base64.b64encode(source.content).decode("ascii")
            return JSONResponse(body)
        except PluginError as exc:
            return JSONResponse({"code": exc.code.value}, status_code=422)
        except (ValidationError, ValueError):
            return JSONResponse({"code": PluginErrorCode.RESULT_INVALID.value}, status_code=422)
        finally:
            cancellations.pop(request.invocation.stage_attempt_id, None)

    @app.post("/cancel/{attempt_id}")
    async def cancel(attempt_id: UUID) -> JSONResponse:
        token = cancellations.get(attempt_id)
        if token is None:
            return JSONResponse({"code": PluginErrorCode.NOT_REGISTERED.value}, status_code=404)
        token.set()
        return JSONResponse({"cancelled": True})

    return app


# Production bootstrap is intentionally empty until a repository-owned plugin is added.
app = create_runner_app(bootstrap_registry())
