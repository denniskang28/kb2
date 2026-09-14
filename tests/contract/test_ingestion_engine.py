from __future__ import annotations

import asyncio
import hashlib
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ConfigDict

from kb2_runtime.ingestion_engine import IngestionEngine, IngestionError, IngestionErrorCode, SourceSubmission
from kb2_runtime.ingestion_profiles import ProfileCompiler, ProfileParser, ResolutionRequest
from kb2_runtime.plugins.contracts import PluginDescriptor, PluginInvocationReceipt, PluginInvocationResult, PluginOutput, RunnerType
from kb2_runtime.plugins.executor import PluginExecutor
from kb2_runtime.plugins.registry import PluginRegistry
from kb2_runtime.plugins.runner import InProcessRunner
from kb2_runtime.trace.contracts import ArtifactInput, ArtifactManifest, EngineKind, QualitySignal, SafeError
from kb2_runtime.trace.errors import TraceErrorCode


AXES = ("extraction", "structure", "chunking", "enrichment", "embedding", "indexing")


class OutcomeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    quality: str = "PASS"
    strategy: str = "default"


class OutcomePlugin:
    async def invoke(self, context):
        item = await context.input(context.invocation.inputs[0].id)
        quality = context.invocation.validated_configuration["quality"]
        return PluginInvocationResult(
            outputs=(PluginOutput(artifact_type="opaque.bytes", schema_revision="v1", content=item.content),),
            quality_signals=({"name": "result_quality", "status": quality, "value": quality},),
        )


def descriptor(digest: str = "a" * 64, plugin_id: str = "transform.outcome@1") -> PluginDescriptor:
    return PluginDescriptor(
        plugin_id=plugin_id, kind="transform", implementation_digest=digest,
        runner=RunnerType.IN_PROCESS, configuration_schema=OutcomeConfig.model_json_schema(),
        input_schemas=(("opaque.bytes", "v1"),), output_schemas=(("opaque.bytes", "v1"),),
        input_ports=({"name": "source", "artifact_type": "opaque.bytes", "schema_revision": "v1"},),
        output_ports=({"name": "result", "artifact_type": "opaque.bytes", "schema_revision": "v1"},),
        quality_signal_names=("result_quality",), timeout_seconds=1,
    )


class Runs:
    def __init__(self) -> None:
        self.run_id = uuid4()
        self.attempts: list[dict] = []
        self.evidence = None
        self.finished: bool | None = None

    async def create_run(self, engine_kind, plan):
        assert engine_kind is EngineKind.INGESTION and plan["stages"]
        return self.run_id

    async def record_ingestion_evidence(self, run_id, evidence) -> None:
        assert run_id == self.run_id
        self.evidence = evidence

    async def start_attempt(self, run_id: UUID, stage_key: str, input_ids=()):
        item = {"id": uuid4(), "key": stage_key, "inputs": tuple(input_ids), "error": None, "signals": []}
        self.attempts.append(item)
        return item["id"], 1 + sum(old["key"] == stage_key for old in self.attempts[:-1])

    async def skip_attempt(self, attempt_id, summary="") -> None:
        next(item for item in self.attempts if item["id"] == attempt_id)["result"] = "SKIPPED"

    async def fail_attempt(self, attempt_id, error: SafeError, summary="") -> None:
        next(item for item in self.attempts if item["id"] == attempt_id)["error"] = error

    async def invalidate_attempt(self, attempt_id, error: SafeError, summary="") -> None:
        await self.fail_attempt(attempt_id, error, summary)
        next(item for item in self.attempts if item["id"] == attempt_id)["result"] = "FAILED"

    async def record_attempt_observations(self, attempt_id, metrics=(), quality_signals=()) -> None:
        next(item for item in self.attempts if item["id"] == attempt_id)["signals"].extend(quality_signals)

    async def finish_run(self, run_id, succeeded: bool) -> None:
        self.finished = succeeded

    async def get_run_trace(self, run_id):
        stages = [SimpleNamespace(stage_key=item["key"], safe_error=item["error"]) for item in self.attempts]
        return SimpleNamespace(stages=stages)


class Artifacts:
    def __init__(self) -> None:
        self.content: dict[UUID, bytes] = {}
        self.manifests: dict[UUID, ArtifactManifest] = {}

    async def complete_with_outputs(self, run_id, attempt_id, outputs, **kwargs):
        result = []
        for item, content in outputs:
            artifact_id = uuid4()
            self.content[artifact_id] = content
            self.manifests[artifact_id] = ArtifactManifest(
                id=artifact_id, storage_locator="sha256/aa/fixture", producing_run_id=run_id,
                producing_stage_attempt_id=attempt_id, **item.model_dump(),
            )
            result.append(artifact_id)
        return tuple(result)

    async def get_artifact_manifest(self, artifact_id):
        return self.manifests.get(artifact_id)

    async def read_content(self, artifact_id):
        return self.content[artifact_id]


def registry(digest: str = "a" * 64) -> PluginRegistry:
    result = PluginRegistry(lambda _: True, lambda _: True)
    result.register(descriptor(digest), OutcomePlugin, OutcomeConfig)
    return result


def profile(*, fallback: bool = False, profile_id: str = "complete", strategy: str = "default", extraction_plugin: str = "transform.outcome@1") -> dict:
    previous = "document.source"
    axes: dict[str, object] = {}
    for index, axis in enumerate(AXES):
        stage_id = "parse" if axis == "extraction" else "main"
        plugin_id = extraction_plugin if axis == "extraction" else "transform.outcome@1"
        candidates = [{"plugin_id": plugin_id, "configuration": {"quality": "WARN" if fallback and axis == "extraction" else "PASS", "strategy": strategy}, "inputs": {"source": previous}, "outputs": ["result"], "accept_quality": ["PASS"]}]
        if fallback and axis == "extraction":
            candidates.append({"plugin_id": plugin_id, "configuration": {"quality": "PASS", "strategy": strategy}, "inputs": {"source": previous}, "outputs": ["result"], "accept_quality": ["PASS", "WARN", "FAIL"]})
        sub_stages = [{"stage_id": stage_id, "candidates": candidates, "on_exhausted": "fail"}]
        if axis == "extraction":
            sub_stages.append({"stage_id": "normalize", "candidates": [{"plugin_id": "transform.outcome@1", "configuration": {"quality": "PASS", "strategy": strategy}, "inputs": {"source": "extraction.parse.result"}, "outputs": ["result"], "accept_quality": ["PASS"]}], "on_exhausted": "fail"})
            previous = "extraction.normalize.result"
        else:
            previous = f"{axis}.main.result"
        axes[axis] = {"sub_stages": sub_stages}
    return {"schema_version": "v1", "default_profile_id": profile_id, "profiles": [{"profile_id": profile_id, "axes": axes}]}


def engine(current_registry: PluginRegistry):
    runs, artifacts = Runs(), Artifacts()
    executor = PluginExecutor(current_registry, {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
    return IngestionEngine(current_registry, executor, runs, artifacts), runs


def test_engine_executes_explicit_sub_stages_with_pinned_evidence_and_ordered_inputs() -> None:
    current = registry()
    compiled = ProfileCompiler(current).compile(ProfileParser.parse(json.dumps(profile()), "application/json"))
    runtime, runs = engine(current)
    receipt = asyncio.run(runtime.submit(compiled, SourceSubmission(content=b"fixture", source_schema={"artifact_type": "opaque.bytes", "schema_revision": "v1"}, filename="fixture.txt", media_type="text/plain"), ResolutionRequest(explicit_profile_id="complete")))
    assert receipt.profile_id == "complete" and receipt.outputs["indexing.main.result"]
    assert runs.finished is True and runs.evidence.plan_digest == receipt.plan_digest
    assert [item["key"] for item in runs.attempts] == [
        "ingestion.source", "extraction.parse.candidate-1", "extraction.normalize.candidate-1",
        "structure.main.candidate-1", "chunking.main.candidate-1", "enrichment.main.candidate-1",
        "embedding.main.candidate-1", "indexing.main.candidate-1",
    ]
    assert all(item["signals"][-1].name == "engine.candidate-selection" for item in runs.attempts[1:])


def test_source_publication_carries_document_registration_only_once() -> None:
    current = registry()
    compiled = ProfileCompiler(current).compile(ProfileParser.parse(json.dumps(profile()), "application/json"))
    runtime, _ = engine(current)
    registrations = []
    original = runtime.artifacts.complete_with_outputs

    async def capture(*args, **kwargs):
        if kwargs.get("document_submission") is not None:
            registrations.append(kwargs["document_submission"])
        return await original(*args, **kwargs)

    runtime.artifacts.complete_with_outputs = capture
    asyncio.run(runtime.submit(
        compiled,
        SourceSubmission(content=b"fixture", source_schema={"artifact_type": "opaque.bytes", "schema_revision": "v1"}, filename="report.pdf", media_type="application/pdf"),
        ResolutionRequest(),
    ))
    assert [(item.display_filename, item.media_type) for item in registrations] == [("report.pdf", "application/pdf")]


def test_engine_rejects_mismatched_source_schema_before_creating_a_run() -> None:
    current = registry()
    compiled = ProfileCompiler(current).compile(ProfileParser.parse(json.dumps(profile()), "application/json"))
    runtime, runs = engine(current)
    with pytest.raises(IngestionError) as raised:
        asyncio.run(runtime.submit(compiled, SourceSubmission(content=b"fixture", source_schema={"artifact_type": "canonical.document", "schema_revision": "v1"}, filename="fixture.txt", media_type="text/plain"), ResolutionRequest()))
    assert raised.value.code is IngestionErrorCode.SOURCE_SCHEMA_MISMATCH and not runs.attempts


def test_engine_records_quality_rejection_then_declared_fallback_without_dispatch_branch() -> None:
    current = registry()
    compiled = ProfileCompiler(current).compile(ProfileParser.parse(json.dumps(profile(fallback=True)), "application/json"))
    runtime, runs = engine(current)
    asyncio.run(runtime.submit(compiled, SourceSubmission(content=b"fixture", source_schema={"artifact_type": "opaque.bytes", "schema_revision": "v1"}, filename="fixture.txt", media_type="text/plain"), ResolutionRequest()))
    extraction = [item for item in runs.attempts if item["key"].startswith("extraction.parse")]
    assert [item["key"] for item in extraction] == ["extraction.parse.candidate-1", "extraction.parse.candidate-2"]
    assert extraction[0]["signals"][-1].value == "rejected" and extraction[1]["signals"][-1].value == "accepted"


def test_engine_records_condition_skip_separately_from_the_selected_fallback() -> None:
    current = registry()
    payload = profile(fallback=True)
    payload["profiles"][0]["axes"]["extraction"]["sub_stages"][0]["candidates"][0]["when"] = {
        "eq": ["document.extension", "pdf"]
    }
    compiled = ProfileCompiler(current).compile(ProfileParser.parse(json.dumps(payload), "application/json"))
    runtime, runs = engine(current)
    asyncio.run(runtime.submit(
        compiled,
        SourceSubmission(content=b"fixture", source_schema={"artifact_type": "opaque.bytes", "schema_revision": "v1"}, filename="fixture.txt", media_type="text/plain"),
        ResolutionRequest(extension="txt"),
    ))
    extraction = [item for item in runs.attempts if item["key"].startswith("extraction.parse")]
    assert extraction[0]["result"] == "SKIPPED"
    assert extraction[0]["signals"][-1].value == "rejected"
    assert extraction[1]["signals"][-1].value == "accepted"


def test_engine_fails_a_pinned_run_when_registry_implementation_has_drifted() -> None:
    compiled = ProfileCompiler(registry("a" * 64)).compile(ProfileParser.parse(json.dumps(profile()), "application/json"))
    runtime, runs = engine(registry("b" * 64))
    with pytest.raises(IngestionError) as raised:
        asyncio.run(runtime.submit(compiled, SourceSubmission(content=b"fixture", source_schema={"artifact_type": "opaque.bytes", "schema_revision": "v1"}, filename="fixture.txt", media_type="text/plain"), ResolutionRequest()))
    assert raised.value.code is IngestionErrorCode.PLAN_IMPLEMENTATION_DRIFT and runs.finished is False
    assert runs.attempts[-1]["error"].code is TraceErrorCode.PLAN_IMPLEMENTATION_DRIFT


def test_engine_records_a_cancelled_stage_without_attempting_a_fallback() -> None:
    current = registry()
    compiled = ProfileCompiler(current).compile(ProfileParser.parse(json.dumps(profile(fallback=True)), "application/json"))
    runtime, runs = engine(current)
    cancellation = asyncio.Event()
    cancellation.set()
    with pytest.raises(IngestionError) as raised:
        asyncio.run(runtime.submit(
            compiled,
            SourceSubmission(content=b"fixture", source_schema={"artifact_type": "opaque.bytes", "schema_revision": "v1"}, filename="fixture.txt", media_type="text/plain"),
            ResolutionRequest(),
            cancellation,
        ))
    assert raised.value.code is IngestionErrorCode.STAGE_EXHAUSTED
    assert runs.finished is False
    assert [item["key"] for item in runs.attempts] == ["ingestion.source", "extraction.parse.candidate-1"]
    assert runs.attempts[-1]["error"].code is TraceErrorCode.PLUGIN_INVOCATION_CANCELLED


class ManifestMismatchThenSuccessExecutor:
    def __init__(self, delegate: PluginExecutor, runs: Runs) -> None:
        self.delegate, self.runs, self.calls = delegate, runs, 0

    async def invoke_with_receipt(self, run_id, stage_key, plugin_id, configuration, input_ids, cancellation=None):
        self.calls += 1
        if self.calls == 1:
            attempt_id, _ = await self.runs.start_attempt(run_id, stage_key, input_ids)
            return PluginInvocationReceipt(attempt_id=attempt_id, output_ids=(uuid4(),))
        return await self.delegate.invoke_with_receipt(run_id, stage_key, plugin_id, configuration, input_ids, cancellation)


def test_engine_invalidates_manifest_mismatch_before_declared_fallback() -> None:
    current = registry()
    compiled = ProfileCompiler(current).compile(ProfileParser.parse(json.dumps(profile(fallback=True)), "application/json"))
    runs, artifacts = Runs(), Artifacts()
    delegate = PluginExecutor(current, {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
    runtime = IngestionEngine(current, ManifestMismatchThenSuccessExecutor(delegate, runs), runs, artifacts)  # type: ignore[arg-type]
    asyncio.run(runtime.submit(
        compiled,
        SourceSubmission(content=b"fixture", source_schema={"artifact_type": "opaque.bytes", "schema_revision": "v1"}, filename="fixture.txt", media_type="text/plain"),
        ResolutionRequest(),
    ))
    rejected = next(item for item in runs.attempts if item["key"] == "extraction.parse.candidate-1")
    assert rejected["error"].code is TraceErrorCode.STAGE_OUTPUT_INVALID
    assert rejected["result"] == "FAILED"
    assert rejected["signals"][-1].value == "rejected"
    assert any(item["key"] == "extraction.parse.candidate-2" for item in runs.attempts)


class RetryOnceExecutor:
    def __init__(self, runs: Runs, artifacts: Artifacts) -> None:
        self.runs, self.artifacts, self.calls = runs, artifacts, 0

    async def invoke_with_receipt(self, run_id, stage_key, plugin_id, configuration, input_ids, cancellation=None):
        self.calls += 1
        attempt_id, _ = await self.runs.start_attempt(run_id, stage_key, input_ids)
        if self.calls == 1:
            await self.runs.fail_attempt(
                attempt_id,
                SafeError(
                    code=TraceErrorCode.PLUGIN_UNAVAILABLE,
                    category="dependency",
                    message="transient runner unavailability",
                    retryable=True,
                ),
            )
            raise RuntimeError("retryable")
        output = ArtifactInput(
            artifact_type="opaque.bytes",
            schema_revision="v1",
            content_digest=hashlib.sha256(b"result").hexdigest(),
            byte_size=len(b"result"),
            producing_plugin_id=plugin_id,
            configuration_digest=hashlib.sha256(b"fixture").hexdigest(),
        )
        output_ids = await self.artifacts.complete_with_outputs(run_id, attempt_id, [(output, b"result")])
        return PluginInvocationReceipt(
            attempt_id=attempt_id,
            output_ids=output_ids,
            quality_signals=(QualitySignal(name="result_quality", status="PASS", value="PASS"),),
        )


def test_engine_retries_only_the_same_pinned_candidate_after_a_retryable_failure() -> None:
    current = registry()
    compiled = ProfileCompiler(current).compile(ProfileParser.parse(json.dumps(profile()), "application/json"))
    runs, artifacts = Runs(), Artifacts()
    executor = RetryOnceExecutor(runs, artifacts)
    runtime = IngestionEngine(current, executor, runs, artifacts)  # type: ignore[arg-type]
    receipt = asyncio.run(runtime.submit(
        compiled,
        SourceSubmission(content=b"fixture", source_schema={"artifact_type": "opaque.bytes", "schema_revision": "v1"}, filename="fixture.txt", media_type="text/plain"),
        ResolutionRequest(),
    ))
    attempts = [item for item in runs.attempts if item["key"] == "extraction.parse.candidate-1"]
    assert receipt.plan_digest == runs.evidence.plan_digest and runs.finished is True
    assert len(attempts) == 2 and attempts[0]["error"].retryable
    assert executor.calls == 8


class MultiRunRuns(Runs):
    def __init__(self) -> None:
        super().__init__()
        self.run_ids: list[UUID] = []
        self.evidences: dict[UUID, object] = {}

    async def create_run(self, engine_kind, plan):
        assert engine_kind is EngineKind.INGESTION and plan["stages"]
        run_id = uuid4()
        self.run_ids.append(run_id)
        return run_id

    async def record_ingestion_evidence(self, run_id, evidence) -> None:
        assert run_id in self.run_ids
        self.evidences[run_id] = evidence


def test_changed_profile_configuration_compiles_to_a_new_pinned_plan_and_run() -> None:
    current = registry()
    first = ProfileCompiler(current).compile(ProfileParser.parse(json.dumps(profile(strategy="first")), "application/json"))
    second = ProfileCompiler(current).compile(ProfileParser.parse(json.dumps(profile(strategy="second")), "application/json"))
    runs, artifacts = MultiRunRuns(), Artifacts()
    executor = PluginExecutor(current, {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
    runtime = IngestionEngine(current, executor, runs, artifacts)
    source = SourceSubmission(content=b"fixture", source_schema={"artifact_type": "opaque.bytes", "schema_revision": "v1"}, filename="fixture.txt", media_type="text/plain")
    first_receipt = asyncio.run(runtime.submit(first, source, ResolutionRequest()))
    second_receipt = asyncio.run(runtime.submit(second, source, ResolutionRequest()))
    assert first_receipt.plan_digest != second_receipt.plan_digest
    assert first_receipt.run_id != second_receipt.run_id
    assert [runs.evidences[run_id].plan_digest for run_id in runs.run_ids] == [
        first_receipt.plan_digest,
        second_receipt.plan_digest,
    ]
