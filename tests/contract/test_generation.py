import hashlib
from types import SimpleNamespace
from uuid import UUID
from datetime import datetime, timezone
import asyncio

import httpx
import pytest
from pydantic import ValidationError

from kb2_runtime.generation.contracts import FinalResponse, GeneratedAnswer, GenerationConfig, VerificationConfig, VerificationResult
from kb2_runtime.generation.serializer import canonical_bytes, identity
from kb2_runtime.plugins.bootstrap import bootstrap_registry
from kb2_runtime.plugins.contracts import ArtifactInput, StageInvocation
from kb2_runtime.trace.contracts import ArtifactReference
from kb2_runtime.generation.plugin import DeepSeekGenerator, FinalStatePlugin, LocalVerifier
from kb2_runtime.generation import plugin as generation_plugin
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode


class _FailureContext:
    def __init__(self) -> None:
        self.cancellation = asyncio.Event()
        evidence = ArtifactReference(id=UUID("12345678-1234-5678-1234-567812345678"), artifact_type="evidence.set", schema_revision="v1", content_digest="a" * 64, byte_size=1, summary="evidence")
        self.invocation = StageInvocation(run_id=UUID("87654321-4321-8765-4321-876543218765"), stage_attempt_id=UUID("11111111-1111-1111-1111-111111111111"), stage_key="final", plugin_id="query.final-state@1", implementation_digest="a" * 64, validated_configuration={}, configuration_digest="b" * 64, inputs=(evidence,), deadline_at=datetime.now(timezone.utc))
        self.value = ArtifactInput(reference=evidence, content=b"x")

    async def input(self, _): return self.value


class _FinalContext:
    def __init__(self, outcome: str) -> None:
        self.cancellation = asyncio.Event()
        evidence = ArtifactReference(id=UUID("12345678-1234-5678-1234-567812345678"), artifact_type="evidence.set", schema_revision="v1", content_digest="a" * 64, byte_size=1, summary="evidence")
        verification = ArtifactReference(id=UUID("87654321-4321-8765-4321-876543218765"), artifact_type="verification.result", schema_revision="v1", content_digest="b" * 64, byte_size=1, summary="verification")
        answer = ArtifactReference(id=UUID("11111111-1111-1111-1111-111111111111"), artifact_type="generated.answer", schema_revision="v1", content_digest="c" * 64, byte_size=1, summary="answer")
        self.invocation = StageInvocation(run_id=UUID("22222222-2222-2222-2222-222222222222"), stage_attempt_id=UUID("33333333-3333-3333-3333-333333333333"), stage_key="final", plugin_id="query.final-state@1", implementation_digest="a" * 64, validated_configuration={}, configuration_digest="b" * 64, inputs=(evidence, verification, answer), deadline_at=datetime.now(timezone.utc))
        generated = _answer(evidence_artifact_id=evidence.id, evidence_digest=evidence.content_digest)
        base = {"generated_answer_artifact_id": answer.id, "evidence_artifact_id": evidence.id, "evidence_digest": evidence.content_digest, "outcome": outcome, "failure_codes": (), "resolved_citation_keys": generated.citation_keys, "missing_citation_keys": (), "answerable": outcome == "pass"}
        result = VerificationResult(verification_id=identity("ver_", base), **base)
        self.values = {
            evidence.id: ArtifactInput(reference=evidence, content=b"evidence"),
            verification.id: ArtifactInput(reference=verification, content=canonical_bytes(result)),
            answer.id: ArtifactInput(reference=answer, content=canonical_bytes(generated)),
        }

    async def input(self, artifact_id): return self.values[artifact_id]


class _GenerationContext:
    def __init__(self, question: bytes = b"What was revenue?", stage_key: str = "generate") -> None:
        self.cancellation = asyncio.Event()
        question_ref = ArtifactReference(id=UUID("44444444-4444-4444-4444-444444444444"), artifact_type="opaque.bytes", schema_revision="v1", content_digest=hashlib.sha256(question).hexdigest(), byte_size=len(question), summary="question")
        evidence_content = b"fixture-evidence"
        evidence_ref = ArtifactReference(id=UUID("55555555-5555-5555-5555-555555555555"), artifact_type="evidence.set", schema_revision="v1", content_digest=hashlib.sha256(evidence_content).hexdigest(), byte_size=len(evidence_content), summary="evidence")
        self.invocation = StageInvocation(run_id=UUID("66666666-6666-6666-6666-666666666666"), stage_attempt_id=UUID("77777777-7777-7777-7777-777777777777"), stage_key=stage_key, plugin_id="generator.deepseek@1", implementation_digest="a" * 64, validated_configuration={"model": "deepseek-v4-flash"}, configuration_digest="b" * 64, inputs=(question_ref, evidence_ref), deadline_at=datetime.now(timezone.utc))
        self.values = {
            question_ref.id: ArtifactInput(reference=question_ref, content=question),
            evidence_ref.id: ArtifactInput(reference=evidence_ref, content=evidence_content),
        }

    async def input(self, artifact_id): return self.values[artifact_id]


class _VerifierContext:
    def __init__(self, answer: GeneratedAnswer, configuration: dict[str, object] | None = None) -> None:
        self.cancellation = asyncio.Event()
        answer_content = canonical_bytes(answer)
        answer_ref = ArtifactReference(id=UUID("88888888-8888-8888-8888-888888888888"), artifact_type="generated.answer", schema_revision="v1", content_digest=hashlib.sha256(answer_content).hexdigest(), byte_size=len(answer_content), summary="answer")
        evidence_content = b"fixture-evidence"
        evidence_ref = ArtifactReference(id=UUID("99999999-9999-9999-9999-999999999999"), artifact_type="evidence.set", schema_revision="v1", content_digest=hashlib.sha256(evidence_content).hexdigest(), byte_size=len(evidence_content), summary="evidence")
        self.invocation = StageInvocation(run_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"), stage_attempt_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"), stage_key="verify", plugin_id="verifier.grounded@1", implementation_digest="a" * 64, validated_configuration=configuration or {"minimum_items": 1}, configuration_digest="b" * 64, inputs=(answer_ref, evidence_ref), deadline_at=datetime.now(timezone.utc))
        self.values = {
            answer_ref.id: ArtifactInput(reference=answer_ref, content=answer_content),
            evidence_ref.id: ArtifactInput(reference=evidence_ref, content=evidence_content),
        }

    async def input(self, artifact_id): return self.values[artifact_id]


def _answer(**changes: object) -> GeneratedAnswer:
    value = {
        "answer_id": "ans_" + "a" * 32,
        "evidence_artifact_id": UUID("12345678-1234-5678-1234-567812345678"),
        "evidence_digest": "b" * 64,
        "question_artifact_id": UUID("87654321-4321-8765-4321-876543218765"),
        "question_digest": "c" * 64,
        "generator_plugin_id": "generator.deepseek@1",
        "implementation_digest": "d" * 64,
        "configuration_digest": "e" * 64,
        "answer": "Revenue increased according to the report.",
        "citation_keys": ("cit_" + "f" * 32,),
        "attempt": 1,
    }
    value.update(changes)
    return GeneratedAnswer(**value)


def test_generated_answer_requires_unique_bounded_citation_keys() -> None:
    answer = _answer()
    assert answer.citation_keys == ("cit_" + "f" * 32,)
    with pytest.raises(ValidationError):
        _answer(citation_keys=("cit_" + "f" * 32, "cit_" + "f" * 32))


def test_final_response_never_persists_answer_for_non_answered_state() -> None:
    base = {"response_id": "fin_" + "a" * 32, "evidence_artifact_id": UUID("12345678-1234-5678-1234-567812345678")}
    abstained = FinalResponse(state="ABSTAINED", action="Provide more evidence or retry the configured query.", **base)
    assert abstained.answer is None and not abstained.citation_keys
    with pytest.raises(ValidationError):
        FinalResponse(state="FAILED", answer="unsafe answer", action="Retry.", **base)


def test_generation_descriptors_are_allowlisted_and_capability_scoped() -> None:
    registry = bootstrap_registry(capability_check=lambda capability: capability != "generation.default")
    default, high_precision = registry.inspect("generator.deepseek@1")[0], registry.inspect("generator.deepseek-high-precision@1")[0]
    assert not default.runnable and default.reason == "CAPABILITY_UNAVAILABLE"
    assert high_precision.runnable
    assert GenerationConfig.model_validate({"model": "deepseek-v4-flash"}).prompt_revision == "grounded-json-v1"


def test_generation_descriptors_reject_cross_capability_models() -> None:
    registry = bootstrap_registry()
    with pytest.raises(ValidationError):
        registry.get("generator.deepseek@1").configuration_model.model_validate({"model": "deepseek-v4-pro"})
    with pytest.raises(ValidationError):
        registry.get("generator.deepseek-high-precision@1").configuration_model.model_validate({"model": "deepseek-v4-flash"})


def test_declared_final_stage_publishes_safe_failed_response_for_generation_failure() -> None:
    result = asyncio.run(FinalStatePlugin().invoke(_FailureContext()))
    response = FinalResponse.model_validate_json(result.outputs[0].content)
    assert response.state == "FAILED" and response.answer is None and not response.citation_keys


@pytest.mark.parametrize(("outcome", "state"), [
    ("pass", "ANSWERED"),
    ("clarification_required", "CLARIFICATION_REQUIRED"),
    ("abstain", "ABSTAINED"),
    ("failed", "FAILED"),
])
def test_final_state_preserves_declared_verification_terminal_outcome(outcome: str, state: str) -> None:
    result = asyncio.run(FinalStatePlugin().invoke(_FinalContext(outcome)))
    response = FinalResponse.model_validate_json(result.outputs[0].content)
    assert response.state == state
    assert (response.answer is not None) is (state == "ANSWERED")


@pytest.mark.parametrize(("field", "value"), [
    ("generated_answer_artifact_id", UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")),
    ("evidence_artifact_id", UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")),
    ("evidence_digest", "f" * 64),
])
def test_final_state_rejects_mismatched_answer_verification_or_evidence_lineage(field: str, value: object) -> None:
    context = _FinalContext("pass")
    verification_ref = context.invocation.inputs[1]
    verification = VerificationResult.model_validate_json(context.values[verification_ref.id].content)
    context.values[verification_ref.id] = ArtifactInput(
        reference=verification_ref,
        content=canonical_bytes(verification.model_copy(update={field: value})),
    )
    with pytest.raises(PluginError) as raised:
        asyncio.run(FinalStatePlugin().invoke(context))
    assert raised.value.code is PluginErrorCode.VERIFICATION_INPUT_INVALID


def test_deepseek_request_is_evidence_only_and_never_persists_secret(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    key_file = tmp_path / "deepseek-key"
    key_file.write_text("test-secret", encoding="utf-8")
    monkeypatch.setenv("KB2_ENVIRONMENT", "test")
    monkeypatch.setenv("KB2_DEEPSEEK_API_KEY_FILE", str(key_file))
    captured: dict[str, object] = {}

    class Client:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def post(self, url, *, headers, json):
            captured.update(url=url, headers=headers, body=json)
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"answer":"Revenue increased.","citation_keys":["cit_ffffffffffffffffffffffffffffffff"]}'}}]})

    evidence = SimpleNamespace(items=(SimpleNamespace(citation_key="cit_ffffffffffffffffffffffffffffffff", excerpt="Revenue increased in the report."),))
    monkeypatch.setattr(generation_plugin.httpx, "AsyncClient", Client)
    monkeypatch.setattr(generation_plugin.EvidenceSet, "model_validate_json", lambda _: evidence)
    result = asyncio.run(DeepSeekGenerator().invoke(_GenerationContext()))
    answer = GeneratedAnswer.model_validate_json(result.outputs[0].content)

    assert captured["client"] == {"trust_env": False, "follow_redirects": False, "timeout": pytest.approx(0.1)}
    assert captured["url"] == "http://deepseek-fixture:8080/chat/completions"
    assert captured["headers"] == {"Authorization": "Bearer test-secret"}
    assert captured["body"] == {"model": "deepseek-v4-flash", "temperature": 0.0, "max_tokens": 512, "messages": [{"role": "system", "content": "Return JSON with answer and citation_keys using only evidence."}, {"role": "user", "content": '{"question":"What was revenue?","evidence":[{"citation_key":"cit_ffffffffffffffffffffffffffffffff","excerpt":"Revenue increased in the report."}]}'}]}
    assert answer.evidence_artifact_id == UUID("55555555-5555-5555-5555-555555555555")
    assert b"test-secret" not in result.outputs[0].content


def test_deepseek_rejects_provider_answer_over_the_configured_character_bound(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    key_file = tmp_path / "deepseek-key"
    key_file.write_text("test-secret", encoding="utf-8")
    monkeypatch.setenv("KB2_ENVIRONMENT", "test")
    monkeypatch.setenv("KB2_DEEPSEEK_API_KEY_FILE", str(key_file))

    class Client:
        def __init__(self, **_): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def post(self, *args, **kwargs):
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"answer":"four","citation_keys":["cit_ffffffffffffffffffffffffffffffff"]}'}}]})

    context = _GenerationContext()
    context.invocation = context.invocation.model_copy(update={"validated_configuration": {"model": "deepseek-v4-flash", "max_answer_chars": 3}})
    monkeypatch.setattr(generation_plugin.httpx, "AsyncClient", Client)
    monkeypatch.setattr(generation_plugin.EvidenceSet, "model_validate_json", lambda _: SimpleNamespace(items=(SimpleNamespace(citation_key="cit_ffffffffffffffffffffffffffffffff", excerpt="Revenue increased."),)))
    with pytest.raises(PluginError) as raised:
        asyncio.run(DeepSeekGenerator().invoke(context))
    assert raised.value.code is PluginErrorCode.GENERATION_PROVIDER_FAILED


def test_repair_generation_attempt_identity_is_distinct_and_traceable(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    key_file = tmp_path / "deepseek-key"
    key_file.write_text("test-secret", encoding="utf-8")
    monkeypatch.setenv("KB2_ENVIRONMENT", "test")
    monkeypatch.setenv("KB2_DEEPSEEK_API_KEY_FILE", str(key_file))

    class Client:
        def __init__(self, **_): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def post(self, *args, **kwargs):
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"answer":"Revenue increased.","citation_keys":["cit_ffffffffffffffffffffffffffffffff"]}'}}]})

    evidence = SimpleNamespace(items=(SimpleNamespace(citation_key="cit_ffffffffffffffffffffffffffffffff", excerpt="Revenue increased in the report."),))
    monkeypatch.setattr(generation_plugin.httpx, "AsyncClient", Client)
    monkeypatch.setattr(generation_plugin.EvidenceSet, "model_validate_json", lambda _: evidence)
    initial = GeneratedAnswer.model_validate_json(asyncio.run(DeepSeekGenerator().invoke(_GenerationContext())).outputs[0].content)
    repaired = GeneratedAnswer.model_validate_json(asyncio.run(DeepSeekGenerator().invoke(_GenerationContext(stage_key="repair.generate-1"))).outputs[0].content)
    assert initial.attempt == 1 and repaired.attempt == 2
    assert initial.answer_id != repaired.answer_id


@pytest.mark.parametrize(("answer", "configuration", "evidence_items", "outcome", "codes"), [
    (_answer(), {"minimum_items": 1}, (SimpleNamespace(citation_key="cit_ffffffffffffffffffffffffffffffff", excerpt="Revenue increased according to the report."),), "pass", ()),
    (_answer(), {"minimum_items": 1, "answerability": "ambiguous"}, (SimpleNamespace(citation_key="cit_ffffffffffffffffffffffffffffffff", excerpt="Revenue increased according to the report."),), "clarification_required", ("AMBIGUOUS_QUESTION",)),
    (_answer(citation_keys=("cit_00000000000000000000000000000000",)), {"minimum_items": 1}, (SimpleNamespace(citation_key="cit_ffffffffffffffffffffffffffffffff", excerpt="Revenue increased according to the report."),), "repairable", ("UNKNOWN_CITATION",)),
    (_answer(), {"minimum_items": 2}, (SimpleNamespace(citation_key="cit_ffffffffffffffffffffffffffffffff", excerpt="Revenue increased according to the report."),), "abstain", ("INSUFFICIENT_EVIDENCE",)),
    (_answer(), {"minimum_items": 1, "forbidden_phrases": ["revenue increased"]}, (SimpleNamespace(citation_key="cit_ffffffffffffffffffffffffffffffff", excerpt="Revenue increased according to the report."),), "repairable", ("FORBIDDEN_CONTENT",)),
    (_answer(answer="The weather is sunny."), {"minimum_items": 1}, (SimpleNamespace(citation_key="cit_ffffffffffffffffffffffffffffffff", excerpt="Revenue increased according to the report."),), "repairable", ("UNSUPPORTED_CONTENT",)),
    (_answer(answer="Revenue increased. The weather is sunny."), {"minimum_items": 1}, (SimpleNamespace(citation_key="cit_ffffffffffffffffffffffffffffffff", excerpt="Revenue increased according to the report."),), "repairable", ("UNSUPPORTED_CONTENT",)),
])
def test_local_verifier_has_deterministic_grounding_outcomes(monkeypatch: pytest.MonkeyPatch, answer: GeneratedAnswer, configuration: dict[str, object], evidence_items: tuple[object, ...], outcome: str, codes: tuple[str, ...]) -> None:
    monkeypatch.setattr(generation_plugin.EvidenceSet, "model_validate_json", lambda _: SimpleNamespace(items=evidence_items))
    result = asyncio.run(LocalVerifier().invoke(_VerifierContext(answer, configuration)))
    verification = VerificationResult.model_validate_json(result.outputs[0].content)
    assert verification.outcome == outcome
    assert set(codes).issubset(verification.failure_codes)


def test_generated_answer_rejects_duplicate_citations_before_verification() -> None:
    with pytest.raises(ValidationError):
        _answer(citation_keys=("cit_ffffffffffffffffffffffffffffffff", "cit_ffffffffffffffffffffffffffffffff"))
