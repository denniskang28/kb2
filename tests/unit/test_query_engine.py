import asyncio
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

from kb2_runtime.generation.contracts import FinalResponse, VerificationResult
from kb2_runtime.generation.serializer import canonical_bytes, identity
from kb2_runtime.plugins.bootstrap import bootstrap_registry
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode
from kb2_runtime.query_profiles.compiler import QueryProfileCompiler, ResolvedQueryPlan
from kb2_runtime.query_profiles.contracts import QueryArtifactBinding
from kb2_runtime.query_profiles.parser import QueryProfileParser
from kb2_runtime.query_engine.engine import QueryEngine
from kb2_runtime.trace.contracts import ArtifactManifest, ArtifactReference


class Artifacts:
    def __init__(self, results: list[str]) -> None:
        self.values: dict[UUID, bytes] = {}
        self.results = iter(results)

    async def read_content(self, artifact: UUID) -> bytes:
        return self.values[artifact]


class Executor:
    def __init__(self, artifacts: Artifacts) -> None:
        self.artifacts, self.calls = artifacts, []

    async def invoke(self, run, stage, plugin, configuration, inputs, cancellation):
        self.calls.append((stage, plugin, inputs))
        output = uuid4()
        if plugin == "verifier.grounded@1":
            outcome = next(self.artifacts.results)
            base = {"generated_answer_artifact_id": inputs[0], "evidence_artifact_id": inputs[1], "evidence_digest": "a" * 64, "outcome": outcome, "failure_codes": (), "resolved_citation_keys": (), "missing_citation_keys": (), "answerable": outcome == "pass"}
            self.artifacts.values[output] = canonical_bytes(VerificationResult(verification_id=identity("ver_", base), **base))
        else:
            self.artifacts.values[output] = b"answer"
        return (output,)


def test_repair_is_bounded_and_reuses_only_question_and_evidence() -> None:
    async def exercise() -> None:
        initial_answer, evidence, initial_verification = uuid4(), uuid4(), uuid4()
        artifacts = Artifacts(["repairable", "pass"])
        base = {"generated_answer_artifact_id": initial_answer, "evidence_artifact_id": evidence, "evidence_digest": "a" * 64, "outcome": "repairable", "failure_codes": ("UNSUPPORTED_CONTENT",), "resolved_citation_keys": (), "missing_citation_keys": (), "answerable": False}
        artifacts.values[initial_verification] = canonical_bytes(VerificationResult(verification_id=identity("ver_", base), **base))
        executor = Executor(artifacts)
        engine = QueryEngine(executor, object(), artifacts)  # type: ignore[arg-type]
        logical = {"query.question": uuid4(), "context.evidence": evidence, "generate.answer": initial_answer, "verify.verification": initial_verification}
        repair = {"stage_id": "repair", "max_attempts": 2, "inputs": [{"name": "evidence", "source": "context.evidence"}, {"name": "answer", "source": "generate.answer"}, {"name": "verification", "source": "verify.verification"}]}
        stages = [{"kind": "generate", "plugin_id": "generator.deepseek@1", "configuration": {"model": "deepseek-v4-flash"}}, {"kind": "verify", "plugin_id": "verifier.grounded@1", "configuration": {}}, repair]
        await engine._repair(uuid4(), repair, stages, logical, logical["query.question"], None)
        assert [call[1] for call in executor.calls] == ["generator.deepseek@1", "verifier.grounded@1", "generator.deepseek@1", "verifier.grounded@1"]
        assert all(call[2] == (logical["query.question"], evidence) for call in executor.calls[::2])
        assert logical["repair.verification"] in artifacts.values
    asyncio.run(exercise())


def test_repair_exhaustion_stops_at_compiled_bound_without_new_context() -> None:
    async def exercise() -> None:
        initial_answer, evidence, initial_verification = uuid4(), uuid4(), uuid4()
        artifacts = Artifacts(["repairable", "repairable"])
        base = {"generated_answer_artifact_id": initial_answer, "evidence_artifact_id": evidence, "evidence_digest": "a" * 64, "outcome": "repairable", "failure_codes": ("UNSUPPORTED_CONTENT",), "resolved_citation_keys": (), "missing_citation_keys": (), "answerable": False}
        artifacts.values[initial_verification] = canonical_bytes(VerificationResult(verification_id=identity("ver_", base), **base))
        executor = Executor(artifacts)
        engine = QueryEngine(executor, object(), artifacts)  # type: ignore[arg-type]
        logical = {"query.question": uuid4(), "context.evidence": evidence, "generate.answer": initial_answer, "verify.verification": initial_verification}
        repair = {"stage_id": "repair", "max_attempts": 2, "inputs": [{"name": "evidence", "source": "context.evidence"}, {"name": "answer", "source": "generate.answer"}, {"name": "verification", "source": "verify.verification"}]}
        stages = [{"kind": "generate", "plugin_id": "generator.deepseek@1", "configuration": {"model": "deepseek-v4-flash"}}, {"kind": "verify", "plugin_id": "verifier.grounded@1", "configuration": {}}, repair]
        await engine._repair(uuid4(), repair, stages, logical, logical["query.question"], None)
        terminal = VerificationResult.model_validate_json(await artifacts.read_content(logical["repair.verification"]))
        assert len(executor.calls) == 4
        assert terminal.outcome == "repairable"
        assert all(inputs == (logical["query.question"], evidence) for _, _, inputs in executor.calls[::2])
    asyncio.run(exercise())


class _PlanArtifacts:
    def __init__(self, index: UUID, index_content: bytes) -> None:
        self.values: dict[UUID, bytes] = {index: index_content}
        self.manifest = ArtifactManifest(
            id=index, artifact_type="search.index.result", schema_revision="v1",
            content_digest=hashlib.sha256(index_content).hexdigest(), byte_size=len(index_content),
            summary="fixed index", storage_locator="sha256/fixed-index", producing_run_id=uuid4(),
            producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture.index@1", configuration_digest="a" * 64,
        )

    async def get_artifact_manifest(self, artifact: UUID):
        return self.manifest if artifact == self.manifest.id else None

    async def read_content(self, artifact: UUID) -> bytes:
        return self.values[artifact]


class _PlanRuns:
    def __init__(self) -> None:
        self.finished: list[bool] = []

    async def create_run(self, *_): return UUID("12345678-1234-5678-1234-567812345678")
    async def finish_run(self, _, *, succeeded: bool): self.finished.append(succeeded)


class _PlanExecutor:
    def __init__(self, artifacts: _PlanArtifacts) -> None:
        self.artifacts, self.calls = artifacts, []

    async def invoke(self, _, stage, plugin, __, inputs, ___):
        self.calls.append((stage, plugin, inputs))
        output = uuid4()
        if plugin == "verifier.grounded@1":
            base = {"generated_answer_artifact_id": inputs[0], "evidence_artifact_id": inputs[1], "evidence_digest": "a" * 64, "outcome": "pass", "failure_codes": (), "resolved_citation_keys": (), "missing_citation_keys": (), "answerable": True}
            self.artifacts.values[output] = canonical_bytes(VerificationResult(verification_id=identity("ver_", base), **base))
        else:
            self.artifacts.values[output] = b"deterministic fixture output"
        return (output,)


def test_two_query_profiles_execute_against_one_immutable_index_with_stage_attribution() -> None:
    async def exercise() -> None:
        index_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        index_content = b"immutable indexed artifact"
        artifacts = _PlanArtifacts(index_id, index_content)
        binding = QueryArtifactBinding.from_reference(ArtifactReference(
            id=index_id, artifact_type="search.index.result", schema_revision="v1",
            content_digest=artifacts.manifest.content_digest, byte_size=len(index_content), summary="fixed index",
        ))
        compiler = QueryProfileCompiler(bootstrap_registry())
        fixture_root = Path(__file__).parents[1] / "fixtures" / "query_profiles"
        text = compiler.compile(QueryProfileParser.parse((fixture_root / "text-hybrid.json").read_bytes(), "application/json"), binding).get("text-hybrid")
        precise = compiler.compile(QueryProfileParser.parse((fixture_root / "high-precision-fact.json").read_bytes(), "application/json"), binding).get("high-precision-fact")
        executor, runs = _PlanExecutor(artifacts), _PlanRuns()
        engine = QueryEngine(executor, runs, artifacts)  # type: ignore[arg-type]
        question = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        first = await engine.execute(text, question, index_id)
        second = await engine.execute(precise, question, index_id)
        assert first.profile_id == "text-hybrid" and second.profile_id == "high-precision-fact"
        assert first.plan_digest != second.plan_digest
        assert runs.finished == [True, True]
        assert artifacts.values[index_id] == index_content
        assert all(index_id in inputs for _, _, inputs in executor.calls if "retriever" in _ or "context" in _)
        assert [plugin for _, plugin, _ in executor.calls] == [
            "retriever.keyword@1", "retriever.vector@1", "fusion.reciprocal-rank@1", "context.from-fusion@1", "generator.deepseek@1", "verifier.grounded@1", "query.final-state@1",
            "retriever.metadata@1", "context.from-retrieval@1", "generator.deepseek-high-precision@1", "verifier.grounded@1", "query.final-state@1",
        ]
    asyncio.run(exercise())


class _FailureExecutor:
    def __init__(self, artifacts: _PlanArtifacts, failure_stage: str, failure: PluginErrorCode) -> None:
        self.artifacts, self.failure_stage, self.failure, self.calls = artifacts, failure_stage, failure, []

    async def invoke(self, _, stage, plugin, __, inputs, ___):
        self.calls.append((stage, plugin, inputs))
        if stage == self.failure_stage:
            raise PluginError(self.failure)
        output = uuid4()
        if stage == "verify":
            base = {"generated_answer_artifact_id": inputs[0], "evidence_artifact_id": inputs[1], "evidence_digest": "a" * 64, "outcome": "repairable", "failure_codes": ("UNSUPPORTED_CONTENT",), "resolved_citation_keys": (), "missing_citation_keys": (), "answerable": False}
            self.artifacts.values[output] = canonical_bytes(VerificationResult(verification_id=identity("ver_", base), **base))
        elif stage.startswith("final"):
            base = {"state": "FAILED", "evidence_artifact_id": inputs[0], "verification_artifact_id": None, "generated_answer_artifact_id": None, "answer": None, "citation_keys": (), "action": "Retry the configured query after generation is available."}
            self.artifacts.values[output] = canonical_bytes(FinalResponse(response_id=identity("fin_", base), **base))
        else:
            self.artifacts.values[output] = b"fixture output"
        return (output,)


def test_generation_unavailability_and_repair_provider_failure_publish_safe_failed_response() -> None:
    async def exercise(failure_stage: str, code: PluginErrorCode) -> tuple[FinalResponse, _FailureExecutor, _PlanRuns]:
        index_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
        index_content = b"fixed index"
        artifacts = _PlanArtifacts(index_id, index_content)
        binding = {"artifact_id": str(index_id), "artifact_type": "search.index.result", "schema_revision": "v1", "content_digest": artifacts.manifest.content_digest, "byte_size": len(index_content)}
        stages = [
            {"stage_id": "context", "kind": "context", "plugin_id": "context.fixture@1", "configuration": {}, "inputs": [], "outputs": [{"name": "evidence"}]},
            {"stage_id": "generate", "kind": "generate", "plugin_id": "generator.deepseek@1", "configuration": {}, "inputs": [{"name": "question", "source": "query.question"}, {"name": "evidence", "source": "context.evidence"}], "outputs": [{"name": "answer"}]},
            {"stage_id": "verify", "kind": "verify", "plugin_id": "verifier.grounded@1", "configuration": {}, "inputs": [{"name": "answer", "source": "generate.answer"}, {"name": "evidence", "source": "context.evidence"}], "outputs": [{"name": "verification"}]},
            {"stage_id": "repair", "kind": "repair", "plugin_id": "query.repair-control@1", "configuration": {}, "max_attempts": 1, "inputs": [{"name": "evidence", "source": "context.evidence"}, {"name": "answer", "source": "generate.answer"}, {"name": "verification", "source": "verify.verification"}], "outputs": [{"name": "answer"}, {"name": "verification"}]},
            {"stage_id": "final", "kind": "final_state", "plugin_id": "query.final-state@1", "configuration": {}, "inputs": [{"name": "evidence", "source": "context.evidence"}, {"name": "verification", "source": "repair.verification"}, {"name": "answer", "source": "repair.answer"}], "outputs": [{"name": "response"}]},
        ]
        plan = ResolvedQueryPlan("fixture", json.dumps({"search_artifact": binding, "stages": stages}), "a" * 64)
        runs = _PlanRuns()
        executor = _FailureExecutor(artifacts, failure_stage, code)
        receipt = await QueryEngine(executor, runs, artifacts).execute(plan, uuid4(), index_id)  # type: ignore[arg-type]
        return FinalResponse.model_validate_json(artifacts.values[receipt.outputs["final.response"]]), executor, runs

    unavailable, unavailable_calls, unavailable_runs = await_result = asyncio.run(exercise("generate", PluginErrorCode.UNAVAILABLE))
    assert unavailable.state == "FAILED" and unavailable.answer is None
    assert [stage for stage, _, _ in unavailable_calls.calls] == ["context", "generate", "final.generation-failure"]
    assert unavailable_runs.finished == [True]

    failed, repair_calls, repair_runs = asyncio.run(exercise("repair.generate-1", PluginErrorCode.GENERATION_PROVIDER_FAILED))
    assert failed.state == "FAILED" and failed.answer is None
    assert [stage for stage, _, _ in repair_calls.calls] == ["context", "generate", "verify", "repair.generate-1", "final.repair-failure"]
    assert repair_runs.finished == [True]
