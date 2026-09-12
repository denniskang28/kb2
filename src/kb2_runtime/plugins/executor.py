from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

from pydantic import ValidationError

from kb2_runtime.trace.contracts import ArtifactInput as StoredArtifactInput, ArtifactReference, SafeError
from kb2_runtime.trace.errors import TraceError, TraceErrorCode
from kb2_runtime.trace.service import ArtifactService, RunService

from .contracts import ArtifactInput, PluginContext, PluginInvocationReceipt, PluginInvocationResult, RunnerType, StageInvocation, configuration_digest
from .errors import PluginError, PluginErrorCode
from .registry import PluginRegistry
from .runner import PluginRunner


class _Context:
    def __init__(self, invocation: StageInvocation, inputs: dict[UUID, ArtifactInput], cancellation: asyncio.Event) -> None:
        self.invocation, self._inputs, self.cancellation = invocation, inputs, cancellation

    async def input(self, artifact_id: UUID) -> ArtifactInput:
        try:
            return self._inputs[artifact_id]
        except KeyError as exc:
            raise PluginError(PluginErrorCode.RESULT_INVALID) from exc


class PluginExecutor:
    def __init__(self, registry: PluginRegistry, runners: dict[RunnerType, PluginRunner], runs: RunService, artifacts: ArtifactService) -> None:
        self.registry, self.runners, self.runs, self.artifacts = registry, runners, runs, artifacts

    async def invoke(self, run_id: UUID, stage_key: str, plugin_id: str, configuration: dict[str, object], input_ids: tuple[UUID, ...], cancellation: asyncio.Event | None = None) -> tuple[UUID, ...]:
        return (await self.invoke_with_receipt(run_id, stage_key, plugin_id, configuration, input_ids, cancellation)).output_ids

    async def invoke_with_receipt(self, run_id: UUID, stage_key: str, plugin_id: str, configuration: dict[str, object], input_ids: tuple[UUID, ...], cancellation: asyncio.Event | None = None) -> PluginInvocationReceipt:
        registration = self.registry.get(plugin_id)
        if not self.registry.inspect(plugin_id)[0].runnable or registration.descriptor.runner not in self.runners:
            try:
                attempt_id, _ = await self.runs.start_attempt(run_id, stage_key, input_ids)
            except TypeError:
                attempt_id, _ = await self.runs.start_attempt(run_id, stage_key)
            try:
                await self.runs.fail_attempt(
                    attempt_id,
                    SafeError(
                        code=TraceErrorCode.PLUGIN_UNAVAILABLE,
                        category="dependency",
                        message="plugin invocation failed",
                        retryable=True,
                    ),
                )
            except TraceError:
                pass
            raise PluginError(PluginErrorCode.UNAVAILABLE)
        try:
            validated = registration.configuration_model.model_validate(configuration).model_dump(mode="json")
        except ValidationError as exc:
            raise PluginError(PluginErrorCode.DESCRIPTOR_INVALID) from exc
        ports = registration.descriptor.input_ports
        if not sum(port.min_items for port in ports) <= len(input_ids) <= sum(port.max_items for port in ports):
            raise PluginError(PluginErrorCode.RESULT_INVALID)
        manifests = []
        position = 0
        for port_index, port in enumerate(ports):
            remaining_minimum = sum(item.min_items for item in ports[port_index + 1:])
            count = min(port.max_items, len(input_ids) - position - remaining_minimum)
            if count < port.min_items:
                raise PluginError(PluginErrorCode.RESULT_INVALID)
            for artifact_id in input_ids[position:position + count]:
                manifest = await self.artifacts.get_artifact_manifest(artifact_id)
                if not manifest or (manifest.artifact_type, manifest.schema_revision) != port.schema:
                    raise PluginError(PluginErrorCode.RESULT_INVALID)
                manifests.append(manifest)
            position += count
        if position != len(input_ids):
            raise PluginError(PluginErrorCode.RESULT_INVALID)
        try:
            attempt_id, _ = await self.runs.start_attempt(run_id, stage_key, input_ids)
        except TypeError:
            attempt_id, _ = await self.runs.start_attempt(run_id, stage_key)
        try:
            input_map = {
                item.id: ArtifactInput(
                    reference=ArtifactReference(
                        id=item.id, artifact_type=item.artifact_type, schema_revision=item.schema_revision,
                        content_digest=item.content_digest, byte_size=item.byte_size, summary=item.summary,
                    ),
                    content=await self.artifacts.read_content(item.id),
                )
                for item in manifests
            }
            invocation = StageInvocation(run_id=run_id, stage_attempt_id=attempt_id, stage_key=stage_key, plugin_id=registration.descriptor.plugin_id, implementation_digest=registration.descriptor.implementation_digest, validated_configuration=validated, configuration_digest=configuration_digest(validated), inputs=tuple(ArtifactReference(id=item.id, artifact_type=item.artifact_type, schema_revision=item.schema_revision, content_digest=item.content_digest, byte_size=item.byte_size, summary=item.summary) for item in manifests), deadline_at=datetime.now(timezone.utc) + timedelta(seconds=registration.descriptor.timeout_seconds))
            context = _Context(invocation, input_map, cancellation or asyncio.Event())
            result = await self.runners[registration.descriptor.runner].invoke(registration.factory(), invocation, context)
            # A runner can finish immediately before cancellation is observed;
            # recheck at the publication boundary so it cannot commit output.
            if context.cancellation.is_set():
                raise PluginError(PluginErrorCode.CANCELLED)
            output_ids = await self._commit(run_id, attempt_id, registration.descriptor.plugin_id, invocation.configuration_digest, registration.descriptor, tuple(dict.fromkeys(input_ids)), result)
            return PluginInvocationReceipt(attempt_id=attempt_id, output_ids=output_ids, metrics=result.metrics, quality_signals=result.quality_signals)
        except Exception as exc:
            code = self._trace_code(exc)
            try:
                await self.runs.fail_attempt(attempt_id, SafeError(code=code, category="dependency" if code == TraceErrorCode.PLUGIN_UNAVAILABLE else "validation", message="plugin invocation failed", retryable=code == TraceErrorCode.PLUGIN_UNAVAILABLE))
            except TraceError:
                pass
            if isinstance(exc, PluginError):
                raise
            raise PluginError(PluginErrorCode.RESULT_INVALID) from exc

    async def _commit(self, run_id: UUID, attempt_id: UUID, plugin_id: str, config_digest: str, descriptor: object, parent_artifact_ids: tuple[UUID, ...], result: PluginInvocationResult) -> tuple[UUID, ...]:
        try:
            if len(result.outputs) != len(descriptor.output_ports) or tuple(
                (output.artifact_type, output.schema_revision) for output in result.outputs
            ) != tuple(port.schema for port in descriptor.output_ports):
                raise PluginError(PluginErrorCode.RESULT_INVALID)
            outputs = []
            for output in result.outputs:
                if len(output.content) > descriptor.resource_hints.max_output_bytes:
                    raise PluginError(PluginErrorCode.OUTPUT_LIMIT_EXCEEDED)
                if (output.artifact_type, output.schema_revision) not in descriptor.output_schemas:
                    raise PluginError(PluginErrorCode.RESULT_INVALID)
                outputs.append((StoredArtifactInput(artifact_type=output.artifact_type, schema_revision=output.schema_revision, content_digest=hashlib.sha256(output.content).hexdigest(), byte_size=len(output.content), producing_plugin_id=plugin_id, configuration_digest=config_digest, parent_artifact_ids=parent_artifact_ids, summary=output.summary, metrics=output.metrics, quality_signals=output.quality_signals), output.content))
            return await self.artifacts.complete_with_outputs(run_id, attempt_id, outputs, summary=result.summary, metrics=result.metrics, quality_signals=result.quality_signals)
        except (ValidationError, TraceError) as exc:
            raise PluginError(PluginErrorCode.RESULT_INVALID) from exc

    @staticmethod
    def _trace_code(error: Exception) -> TraceErrorCode:
        if isinstance(error, PluginError):
            return TraceErrorCode(error.code.value)
        return TraceErrorCode.PLUGIN_RESULT_INVALID
