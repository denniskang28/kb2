from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
import httpx
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from kb2_runtime.plugins.contracts import PluginDescriptor, PluginInvocationResult, PluginOutput, RunnerType
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode
from kb2_runtime.plugins.executor import PluginExecutor
from kb2_runtime.plugins.container import ContainerRunner
from kb2_runtime.plugins.registry import PluginRegistry
from kb2_runtime.plugins.runner import InProcessRunner
from kb2_runtime.plugins.runner_service import create_runner_app
from kb2_runtime.plugins.runner_service import app as sidecar_app
from kb2_runtime.plugins.bootstrap import SyntheticTransformConfig, bootstrap_registry
from kb2_runtime.api import create_app
import kb2_runtime.health.service as health_service_module
from kb2_runtime.health.contracts import HealthEntry
from kb2_runtime.trace.contracts import ArtifactManifest, ArtifactReference, SafeError


class TransformConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    suffix: str = "!"


def descriptor(plugin_id: str = "transform.synthetic@1", runner: RunnerType = RunnerType.IN_PROCESS, limit: int = 1024) -> PluginDescriptor:
    return PluginDescriptor(
        plugin_id=plugin_id, kind="transform", implementation_digest="a" * 64, runner=runner,
        configuration_schema=TransformConfig.model_json_schema(), input_schemas=(("opaque.bytes", "v1"),),
        output_schemas=(("opaque.bytes", "v1"),), timeout_seconds=1,
        resource_hints={"max_output_bytes": limit},
    )


class Transform:
    async def invoke(self, context: object) -> PluginInvocationResult:
        item = await context.input(context.invocation.inputs[0].id)  # type: ignore[attr-defined]
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="opaque.bytes", schema_revision="v1", content=item.content + context.invocation.validated_configuration["suffix"].encode(), metrics=({"name": "output_bytes", "value": 7},), quality_signals=({"name": "synthetic", "status": "PASS", "summary": "deterministic"},)),), summary="transformed", metrics=({"name": "runner_calls", "value": 1},), quality_signals=({"name": "synthetic-stage", "status": "PASS", "summary": "deterministic"},))  # type: ignore[attr-defined]


class FakeRuns:
    def __init__(self) -> None:
        self.attempt = uuid4()
        self.failures: list[SafeError] = []

    async def start_attempt(self, run_id: UUID, stage_key: str) -> tuple[UUID, int]:
        return self.attempt, 1

    async def fail_attempt(self, attempt: UUID, error: SafeError, summary: str = "") -> None:
        assert attempt == self.attempt
        self.failures.append(error)


class FakeArtifacts:
    def __init__(self) -> None:
        self.id, self.content = uuid4(), b"source"
        self.commits: list[object] = []
        self.manifest = ArtifactManifest(id=self.id, artifact_type="opaque.bytes", schema_revision="v1", content_digest=hashlib.sha256(self.content).hexdigest(), byte_size=len(self.content), summary="source", storage_locator="sha256/aa/x", producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(), producing_plugin_id="parent@1", configuration_digest="b" * 64)

    async def get_artifact_manifest(self, artifact_id: UUID) -> ArtifactManifest | None:
        return self.manifest if artifact_id == self.id else None

    async def read_content(self, artifact_id: UUID) -> bytes:
        assert artifact_id == self.id
        return self.content

    async def complete_with_outputs(self, run_id: UUID, attempt_id: UUID, outputs: object, **kwargs: object) -> tuple[UUID, ...]:
        self.commits.append((outputs, kwargs))
        return (uuid4(),)


def registry(*, runner_ready: bool = True) -> PluginRegistry:
    return PluginRegistry(lambda _: True, lambda _: runner_ready)


def test_registration_is_inspectable_without_factory_loading_and_rejects_conflicts() -> None:
    calls = 0
    def factory() -> Transform:
        nonlocal calls
        calls += 1
        return Transform()
    items = registry()
    items.register(descriptor(), factory, TransformConfig)
    assert items.inspect() == (items.inspect("transform.synthetic@1")[0],)
    assert items.inspect()[0].runnable and calls == 0
    with pytest.raises(PluginError, match="PLUGIN_ID_DUPLICATE"):
        items.register(descriptor(), factory, TransformConfig)
    with pytest.raises(Exception):
        PluginDescriptor.model_validate({**descriptor().model_dump(), "configuration_schema": {"command": "unsafe"}})


def test_synthetic_extension_uses_common_executor_contract_without_dispatch_changes() -> None:
    async def exercise() -> None:
        semantics = []
        for runner in (RunnerType.IN_PROCESS, RunnerType.CONTAINER):
            items = registry()
            items.register(descriptor(runner=runner), Transform, TransformConfig)
            artifacts, runs = FakeArtifacts(), FakeRuns()
            runners = {RunnerType.IN_PROCESS: InProcessRunner()}
            if runner is RunnerType.CONTAINER:
                sidecar = registry()
                sidecar.register(descriptor(runner=runner), Transform, TransformConfig)
                runners[RunnerType.CONTAINER] = ContainerRunner("http://plugin-runner", transport=httpx.ASGITransport(app=create_runner_app(sidecar)))
            executor = PluginExecutor(items, runners, runs, artifacts)  # type: ignore[arg-type]
            result = await executor.invoke(uuid4(), "transform", "transform.synthetic@1", {"suffix": "!"}, (artifacts.id,))
            outputs, completed = artifacts.commits[0]
            stored, content = outputs[0]
            semantics.append((len(result), stored.artifact_type, stored.schema_revision, stored.content_digest, content, tuple(stored.metrics), tuple(stored.quality_signals), completed["summary"], tuple(completed["metrics"]), tuple(completed["quality_signals"]), len(runs.failures)))
            assert stored.parent_artifact_ids == (artifacts.id,)
        assert semantics[0] == semantics[1]
        assert semantics[0][1:5] == ("opaque.bytes", "v1", hashlib.sha256(b"source!").hexdigest(), b"source!")
    asyncio.run(exercise())


def test_global_sidecar_bootstrap_executes_the_shared_allowlisted_plugin() -> None:
    async def exercise() -> None:
        items = bootstrap_registry(runner_ready=lambda _: True)
        artifacts, runs = FakeArtifacts(), FakeRuns()
        executor = PluginExecutor(items, {RunnerType.CONTAINER: ContainerRunner("http://plugin-runner", transport=httpx.ASGITransport(app=sidecar_app))}, runs, artifacts)  # type: ignore[arg-type]
        await executor.invoke(uuid4(), "transform", "transform.synthetic@1", {"suffix": "?"}, (artifacts.id,))
        assert artifacts.commits[0][0][0][1] == b"source?"
        assert not runs.failures
    asyncio.run(exercise())


def test_container_runner_serializes_cancellation_and_preserves_the_sidecar_code() -> None:
    async def exercise() -> None:
        items = bootstrap_registry(runner_ready=lambda _: True)
        artifacts, runs = FakeArtifacts(), FakeRuns()
        executor = PluginExecutor(items, {RunnerType.CONTAINER: ContainerRunner("http://plugin-runner", transport=httpx.ASGITransport(app=sidecar_app))}, runs, artifacts)  # type: ignore[arg-type]
        token = asyncio.Event()
        token.set()
        with pytest.raises(PluginError, match="PLUGIN_INVOCATION_CANCELLED"):
            await executor.invoke(uuid4(), "transform", "transform.synthetic@1", {}, (artifacts.id,), token)
        assert len(runs.failures) == 1
        assert runs.failures[0].code.value == "PLUGIN_INVOCATION_CANCELLED"
        assert not artifacts.commits
    asyncio.run(exercise())


class Crash:
    async def invoke(self, context: object) -> PluginInvocationResult:
        raise RuntimeError("provider payload must not escape")


class Sleep:
    async def invoke(self, context: object) -> PluginInvocationResult:
        await asyncio.sleep(0.05)
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="opaque.bytes", schema_revision="v1", content=b"late"),))


class FinishAndCancel:
    def __init__(self, token: asyncio.Event) -> None:
        self.token = token

    async def invoke(self, context: object) -> PluginInvocationResult:
        self.token.set()
        await asyncio.sleep(0)
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="opaque.bytes", schema_revision="v1", content=b"completed"),))


def test_midflight_cancellation_fails_once_without_outputs_for_both_runners() -> None:
    async def exercise(runner: RunnerType) -> None:
        items = registry()
        items.register(descriptor(plugin_id="transform.slow@1", runner=runner), Sleep, TransformConfig)
        artifacts, runs = FakeArtifacts(), FakeRuns()
        runners = {RunnerType.IN_PROCESS: InProcessRunner()}
        if runner is RunnerType.CONTAINER:
            sidecar = registry()
            sidecar.register(descriptor(plugin_id="transform.slow@1", runner=runner), Sleep, TransformConfig)
            runners[RunnerType.CONTAINER] = ContainerRunner("http://plugin-runner", transport=httpx.ASGITransport(app=create_runner_app(sidecar)))
        executor = PluginExecutor(items, runners, runs, artifacts)  # type: ignore[arg-type]
        token = asyncio.Event()
        task = asyncio.create_task(executor.invoke(uuid4(), "slow", "transform.slow@1", {}, (artifacts.id,), token))
        await asyncio.sleep(0.005)
        token.set()
        with pytest.raises(PluginError, match="PLUGIN_INVOCATION_CANCELLED"):
            await task
        assert not artifacts.commits
        assert len(runs.failures) == 1
        assert runs.failures[0].code.value == "PLUGIN_INVOCATION_CANCELLED"
    asyncio.run(exercise(RunnerType.IN_PROCESS))
    asyncio.run(exercise(RunnerType.CONTAINER))


def test_container_cancellation_wins_over_simultaneous_sidecar_completion() -> None:
    async def exercise() -> None:
        token = asyncio.Event()
        items, sidecar = registry(), registry()
        value = descriptor(plugin_id="transform.race@1", runner=RunnerType.CONTAINER)
        items.register(value, Transform, TransformConfig)
        sidecar.register(value, lambda: FinishAndCancel(token), TransformConfig)
        artifacts, runs = FakeArtifacts(), FakeRuns()
        executor = PluginExecutor(items, {RunnerType.CONTAINER: ContainerRunner("http://plugin-runner", transport=httpx.ASGITransport(app=create_runner_app(sidecar)))}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError, match="PLUGIN_INVOCATION_CANCELLED"):
            await executor.invoke(uuid4(), "race", "transform.race@1", {}, (artifacts.id,), token)
        assert token.is_set() and not artifacts.commits
        assert len(runs.failures) == 1
        assert runs.failures[0].code.value == "PLUGIN_INVOCATION_CANCELLED"
    asyncio.run(exercise())


class InvalidOutput:
    async def invoke(self, context: object) -> PluginInvocationResult:
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="not.allowed", schema_revision="v1", content=b"x"),))


@pytest.mark.parametrize(
    ("implementation", "limit", "timeout", "cancelled", "expected"),
    [
        (Crash, 1024, 1, False, PluginErrorCode.CRASHED),
        (Sleep, 1024, 0.001, False, PluginErrorCode.TIMEOUT),
        (InvalidOutput, 1024, 1, False, PluginErrorCode.RESULT_INVALID),
        (Transform, 1024, 1, True, PluginErrorCode.CANCELLED),
    ],
)
def test_terminal_plugin_failures_are_exactly_once_and_never_commit(
    implementation: type[object], limit: int, timeout: float, cancelled: bool, expected: PluginErrorCode
) -> None:
    async def exercise() -> None:
        items = registry()
        items.register(descriptor(limit=limit).model_copy(update={"timeout_seconds": timeout}), implementation, TransformConfig)  # type: ignore[arg-type]
        artifacts, runs = FakeArtifacts(), FakeRuns()
        executor = PluginExecutor(items, {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        token = asyncio.Event()
        if cancelled:
            token.set()
        with pytest.raises(PluginError, match=expected.value):
            await executor.invoke(uuid4(), "failure", "transform.synthetic@1", {}, (artifacts.id,), token)
        assert not artifacts.commits
        assert len(runs.failures) == 1
        assert runs.failures[0].code.value == expected.value
        assert "provider" not in runs.failures[0].message
    asyncio.run(exercise())


def test_unavailable_and_oversized_plugin_fail_without_output_commit() -> None:
    async def exercise() -> None:
        unavailable = registry(runner_ready=False)
        unavailable.register(descriptor(), Transform, TransformConfig)
        availability = unavailable.inspect()[0]
        assert availability.registered and not availability.runnable and availability.reason == "RUNNER_UNAVAILABLE"
        artifacts, runs = FakeArtifacts(), FakeRuns()
        executor = PluginExecutor(unavailable, {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError, match="PLUGIN_UNAVAILABLE"):
            await executor.invoke(uuid4(), "x", "transform.synthetic@1", {}, (artifacts.id,))
        assert not artifacts.commits and not runs.failures

        limited = registry()
        limited.register(descriptor(limit=1), Transform, TransformConfig)
        executor = PluginExecutor(limited, {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError, match="PLUGIN_OUTPUT_LIMIT_EXCEEDED"):
            await executor.invoke(uuid4(), "x", "transform.synthetic@1", {}, (artifacts.id,))
        assert not artifacts.commits and len(runs.failures) == 1
        assert runs.failures[0].code.value == "PLUGIN_OUTPUT_LIMIT_EXCEEDED"
    asyncio.run(exercise())


def test_optional_container_capability_does_not_break_liveness_or_default_readiness(
    settings: object, catalog: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unavailable(_: object) -> tuple[str, str]:
        return "unavailable", "DEPENDENCY_UNAVAILABLE"

    monkeypatch.setattr(health_service_module, "container_runner_probe", unavailable)
    async def ready_components(_: object) -> list[HealthEntry]:
        return [HealthEntry(id="control.api", required=True, status="ready", code="OK", latencyMs=0)]
    monkeypatch.setattr(health_service_module.HealthService, "_components", ready_components)
    client = TestClient(create_app(settings, catalog))  # type: ignore[arg-type]
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200
    response = client.get("/health/capabilities?require=runner.container")
    assert response.status_code == 503
    item = next(value for value in response.json()["capabilities"] if value["id"] == "runner.container")
    assert item["status"] == "unavailable" and item["code"] == "DEPENDENCY_UNAVAILABLE"


class OpenConfig(BaseModel):
    suffix: str = ""


def test_registry_rejects_malformed_descriptor_and_open_configuration_models() -> None:
    items = registry()
    with pytest.raises(PluginError, match="PLUGIN_DESCRIPTOR_INVALID"):
        items.register({"plugin_id": "bad", "kind": "transform"}, Transform, TransformConfig)
    open_descriptor = descriptor().model_copy(update={"configuration_schema": OpenConfig.model_json_schema()})
    with pytest.raises(PluginError, match="PLUGIN_DESCRIPTOR_INVALID"):
        items.register(open_descriptor, Transform, OpenConfig)
    with pytest.raises(Exception):
        TransformConfig.model_validate({"suffix": "ok", "undeclared": "injected"})
