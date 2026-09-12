import asyncio
import hashlib
import json
from uuid import UUID, uuid4

import pytest

from kb2_runtime.evaluation.judges import CalibrationLabel, CalibrationPolicy, CalibrationSnapshot, JudgeCalibrationService, JudgeDefinition, JudgeResult, SlicePolicy, digest
from kb2_runtime.evaluation.metrics import MetricAggregator
from kb2_runtime.plugins.bootstrap import JUDGE_DEEPSEEK_DESCRIPTOR, bootstrap_registry
from kb2_runtime.plugins.contracts import RunnerType
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode
from kb2_runtime.plugins.executor import PluginExecutor
from kb2_runtime.plugins.runner import InProcessRunner
from kb2_runtime.trace.contracts import ArtifactManifest
from kb2_runtime.evaluation.datasets.contracts import Answerability, CaseOrigin, CaseProvenance, DatasetContent, QueryCase, ReviewEvent, SourceArtifactRef, canonical_bytes
from kb2_runtime.trace.schemas import schema_is_supported


def _digest(char: str) -> str:
    return char * 64


def _definition() -> JudgeDefinition:
    return JudgeDefinition(definition_id="judge.semantic@1", rubric_id="rubric.correctness@1", plugin_id="judge.deepseek@1", implementation_digest=_digest("9"), provider_id="deepseek", model="deepseek-v4-flash", prompt_template="Return a label.", parameters={"temperature": 0}, labels=("PASS", "FAIL"), positive_label="PASS", max_evidence_items=4, max_rationale_codes=4)


def _label(case: str, criticality: str, label: str, definition_id="judge.semantic@1", rubric_id="rubric.correctness@1") -> CalibrationLabel:
    return CalibrationLabel(case_id=case, definition_id=definition_id, rubric_id=rubric_id, source_artifact_id=uuid4(), source_digest=_digest("a"), evidence_artifact_id=uuid4(), evidence_digest=_digest("b"), slices={"format": "pdf", "processing_class": "native", "native_ocr": "native", "structure": "prose", "language": "en", "question_class": "lookup", "difficulty": "low", "criticality": criticality}, label=label, reviewer="reviewer", reviewed_at="2026-01-01T00:00:00Z", review_record_id="jreview_" + "1" * 16, reviewed_label_digest=_digest("c"))


def _result(snapshot: CalibrationSnapshot, definition: JudgeDefinition, label: CalibrationLabel, selected: str) -> JudgeResult:
    return JudgeResult(case_id=label.case_id, calibration_snapshot_id=UUID(int=1), calibration_snapshot_digest=snapshot.snapshot_digest, definition_id=definition.definition_id, definition_digest=definition.definition_digest, provider_id="deepseek", model=definition.model, plugin_id="judge.deepseek@1", implementation_digest=_digest("9"), prompt_digest=digest(definition.prompt_template), parameters_digest=digest(definition.parameters), evidence_artifact_id=label.evidence_artifact_id, evidence_digest=label.evidence_digest, final_response_artifact_id=uuid4(), label=selected, rationale_codes=("SUPPORTED",), cited_evidence_ids=(), elapsed_ms=1)


def test_critical_slice_failure_cannot_hide_aggregate_agreement():
    definition = _definition()
    labels = tuple(_label(f"qcase_{index:032x}", "high" if index == 0 else "low", "PASS") for index in range(10))
    snapshot = CalibrationSnapshot(dataset_snapshot_id=uuid4(), dataset_snapshot_digest=_digest("f"), definitions=(definition,), labels=labels)
    policy = CalibrationPolicy(policy_id="policy.semantic@1", slices=(SlicePolicy(selector={"criticality": "high"}, minimum_samples=1, minimum_agreement=1, maximum_false_positive_rate=0, maximum_false_negative_rate=0), SlicePolicy(selector={"criticality": "low"}, minimum_samples=1, minimum_agreement=.8, maximum_false_positive_rate=1, maximum_false_negative_rate=1)))
    results = tuple((uuid4(), _result(snapshot, definition, label, "FAIL" if index == 0 else "PASS")) for index, label in enumerate(labels))
    report = JudgeCalibrationService().report(UUID(int=1), snapshot, definition.definition_id, policy, results)
    assert report.overall.agreement == .9
    assert report.eligibility == "INELIGIBLE"
    assert report.slices[0].false_negative_count == 1


def test_definition_pin_and_catalog_are_closed():
    definition = _definition()
    with pytest.raises(ValueError):
        JudgeDefinition.model_validate(definition.model_dump() | {"parameters": {"secret": "nope"}})
    with pytest.raises(ValueError):
        JudgeDefinition.model_validate(definition.model_dump() | {"parameters": {"model": "untrusted-override"}})
    assert schema_is_supported("judge.calibration.snapshot", "v1")
    assert schema_is_supported("judge.result", "v1")
    availability = bootstrap_registry(capability_check=lambda _: False).inspect("judge.deepseek@1")[0]
    assert availability.plugin_id == JUDGE_DEEPSEEK_DESCRIPTOR.plugin_id
    assert not availability.runnable


def test_calibration_rejects_results_or_labels_not_bound_to_the_selected_definition():
    definition = _definition()
    alternate = definition.model_copy(update={"definition_id": "judge.alternate@1", "labels": ("YES", "NO"), "positive_label": "YES"})
    label = _label("qcase_00000000000000000000000000000001", "high", "YES", alternate.definition_id, alternate.rubric_id)
    snapshot = CalibrationSnapshot(dataset_snapshot_id=uuid4(), dataset_snapshot_digest=_digest("f"), definitions=(definition, alternate), labels=(label,))
    policy = CalibrationPolicy(policy_id="policy.semantic@1", slices=(SlicePolicy(selector={"criticality": "high"}, minimum_samples=1, minimum_agreement=0, maximum_false_positive_rate=1, maximum_false_negative_rate=1),))
    result = _result(snapshot, definition, label, "PASS")

    # Reviewed semantic labels are rubric/definition-specific. A label from a
    # second definition must not be scored against this definition's result.
    with pytest.raises(ValueError):
        JudgeCalibrationService().report(UUID(int=1), snapshot, definition.definition_id, policy, ((uuid4(), result),))


@pytest.mark.parametrize("change", [
    {"definition_id": "judge.other@1"},
    {"case_id": "qcase_000000000000000000000000000000ff"},
])
def test_calibration_rejects_result_identity_not_present_in_snapshot(change: dict[str, str]):
    definition = _definition()
    label = _label("qcase_00000000000000000000000000000001", "high", "PASS")
    snapshot = CalibrationSnapshot(dataset_snapshot_id=uuid4(), dataset_snapshot_digest=_digest("f"), definitions=(definition,), labels=(label,))
    policy = CalibrationPolicy(policy_id="policy.semantic@1", slices=(SlicePolicy(selector={"criticality": "high"}, minimum_samples=1, minimum_agreement=0, maximum_false_positive_rate=1, maximum_false_negative_rate=1),))
    result = _result(snapshot, definition, label, "PASS").model_copy(update=change)

    with pytest.raises(ValueError):
        JudgeCalibrationService().report(UUID(int=1), snapshot, definition.definition_id, policy, ((uuid4(), result),))


def test_semantic_metric_is_advisory_without_calibration_and_drifted_for_changed_definition():
    definition = _definition()
    label = _label("qcase_00000000000000000000000000000001", "high", "PASS")
    snapshot = CalibrationSnapshot(dataset_snapshot_id=uuid4(), dataset_snapshot_digest=_digest("f"), definitions=(definition,), labels=(label,))
    policy = CalibrationPolicy(policy_id="policy.semantic@1", slices=(SlicePolicy(selector={"criticality": "high"}, minimum_samples=1, minimum_agreement=1, maximum_false_positive_rate=0, maximum_false_negative_rate=0),))
    result = _result(snapshot, definition, label, "PASS")
    service = JudgeCalibrationService()

    advisory = service.semantic_metric(metric_id="metric.semantic.correctness@1", snapshot_id=UUID(int=1), label=label, result_id=uuid4(), result=result, calibration_report_id=None, calibration_report=None, definition=definition, expected_definition_digest=definition.definition_digest, policy=policy)
    drifted = service.semantic_metric(metric_id="metric.semantic.correctness@1", snapshot_id=UUID(int=1), label=label, result_id=uuid4(), result=result, calibration_report_id=None, calibration_report=None, definition=definition, expected_definition_digest=_digest("0"), policy=policy)

    assert advisory.eligibility == "ADVISORY"
    assert drifted.eligibility == "DRIFTED"


def test_judge_aggregate_retains_noneligible_state_counts_and_capability_is_isolated():
    definition = _definition()
    label = _label("qcase_00000000000000000000000000000001", "high", "PASS")
    snapshot = CalibrationSnapshot(dataset_snapshot_id=uuid4(), dataset_snapshot_digest=_digest("f"), definitions=(definition,), labels=(label,))
    policy = CalibrationPolicy(policy_id="policy.semantic@1", slices=(SlicePolicy(selector={"criticality": "high"}, minimum_samples=1, minimum_agreement=1, maximum_false_positive_rate=0, maximum_false_negative_rate=0),))
    result = _result(snapshot, definition, label, "PASS")
    report = JudgeCalibrationService().semantic_metric(metric_id="metric.semantic.correctness@1", snapshot_id=UUID(int=1), label=label, result_id=uuid4(), result=result, calibration_report_id=None, calibration_report=None, definition=definition, expected_definition_digest=definition.definition_digest, policy=policy)
    aggregate = MetricAggregator().aggregate(((uuid4(), report),), report.metric_id, {"criticality": "high"})

    assert aggregate.advisory_count == 1
    registry = bootstrap_registry(capability_check=lambda capability: capability != "judge.semantic")
    assert not registry.inspect("judge.deepseek@1")[0].runnable
    assert registry.inspect("generator.deepseek@1")[0].runnable


def test_missing_judge_provider_fails_scoped_without_publishing_or_corrupting_deterministic_artifact(monkeypatch: pytest.MonkeyPatch, tmp_path):
    class Artifacts:
        def __init__(self): self.contents, self.manifests = {}, {}
        def add(self, artifact_type, content):
            identifier = uuid4()
            self.contents[identifier] = content
            self.manifests[identifier] = ArtifactManifest(id=identifier, artifact_type=artifact_type, schema_revision="v1", content_digest=hashlib.sha256(content).hexdigest(), byte_size=len(content), summary="fixture", storage_locator="sha256/fixture", producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture.source@1", configuration_digest="a" * 64, parent_artifact_ids=())
            return identifier
        async def get_artifact_manifest(self, identifier): return self.manifests.get(identifier)
        async def read_content(self, identifier): return self.contents[identifier]
        async def complete_with_outputs(self, *_args, **_kwargs): raise AssertionError("judge failure must not publish output")
    class Runs:
        async def start_attempt(self, *_): return uuid4(), 1
        async def fail_attempt(self, *_args, **_kwargs): pass

    definition = _definition()
    label = _label("qcase_00000000000000000000000000000001", "high", "PASS")
    snapshot = CalibrationSnapshot(dataset_snapshot_id=uuid4(), dataset_snapshot_digest=_digest("f"), definitions=(definition,), labels=(label,))
    artifacts = Artifacts()
    snapshot_id = artifacts.add("judge.calibration.snapshot", snapshot.model_dump_json().encode())
    evidence_id = artifacts.add("evidence.set", b'{"schema_version":"EvidenceSet/v1","evidence_set_id":"evs_00000000000000000000000000000000","source_candidate_set_id":"rcs_00000000000000000000000000000000","index":{"artifact_id":"00000000-0000-0000-0000-000000000001","content_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"index_id":"idx_00000000000000000000000000000000","document_id":"doc_0000000000000000","context_plugin_id":"context.from-retrieval@1","implementation_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","configuration_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","items":[],"decisions":[],"shortage":{"minimum_items":0,"selected_items":0,"selected_tokens":0,"reason":"none"}}')
    # Bind the label to the actual fixture Artifact identities.
    snapshot = snapshot.model_copy(update={"labels": (label.model_copy(update={"evidence_artifact_id": evidence_id, "evidence_digest": artifacts.manifests[evidence_id].content_digest}),)})
    artifacts.contents[snapshot_id] = snapshot.model_dump_json().encode()
    artifacts.manifests[snapshot_id] = artifacts.manifests[snapshot_id].model_copy(update={"content_digest": hashlib.sha256(artifacts.contents[snapshot_id]).hexdigest(), "byte_size": len(artifacts.contents[snapshot_id])})
    final_id = artifacts.add("final.response", b'{"schema_version":"FinalResponse/v1","response_id":"fin_00000000000000000000000000000000","state":"FAILED","evidence_artifact_id":"' + str(evidence_id).encode() + b'","action":"Retry."}')
    deterministic_id = artifacts.add("metric.report", b"deterministic-result")
    key_file = tmp_path / "missing-key"; key_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("KB2_ENVIRONMENT", "test"); monkeypatch.setenv("KB2_DEEPSEEK_API_KEY_FILE", str(key_file))
    executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, Runs(), artifacts)  # type: ignore[arg-type]
    with pytest.raises(PluginError) as raised:
        asyncio.run(executor.invoke(uuid4(), "judge", "judge.deepseek@1", {"definition_id": definition.definition_id, "case_id": label.case_id}, (snapshot_id, evidence_id, final_id)))
    assert raised.value.code is PluginErrorCode.GENERATION_UNAVAILABLE
    assert artifacts.contents[deterministic_id] == b"deterministic-result"
    assert not any(item.artifact_type == "judge.result" for item in artifacts.manifests.values())
    assert bootstrap_registry().inspect("generator.deepseek@1")[0].runnable


def test_definition_rejects_secret_prompt_and_calibration_rejects_provider_pin_drift():
    with pytest.raises(ValueError):
        JudgeDefinition.model_validate(_definition().model_dump() | {"prompt_template": "Use bearer secret token."})
    definition = _definition(); label = _label("qcase_00000000000000000000000000000001", "high", "PASS")
    snapshot = CalibrationSnapshot(dataset_snapshot_id=uuid4(), dataset_snapshot_digest=_digest("f"), definitions=(definition,), labels=(label,))
    policy = CalibrationPolicy(policy_id="policy.semantic@1", slices=(SlicePolicy(selector={"criticality": "high"}, minimum_samples=1, minimum_agreement=0, maximum_false_positive_rate=1, maximum_false_negative_rate=1),))
    result = _result(snapshot, definition, label, "PASS").model_copy(update={"model": "other-model"})
    with pytest.raises(ValueError):
        JudgeCalibrationService().report(UUID(int=1), snapshot, definition.definition_id, policy, ((uuid4(), result),))


def test_semantic_metric_rejects_calibration_report_snapshot_or_result_lineage_mismatch_and_uses_positive_label():
    definition = _definition().model_copy(update={"labels": ("YES", "NO"), "positive_label": "YES"})
    label = _label("qcase_00000000000000000000000000000001", "high", "NO", definition.definition_id, definition.rubric_id)
    snapshot = CalibrationSnapshot(dataset_snapshot_id=uuid4(), dataset_snapshot_digest=_digest("f"), definitions=(definition,), labels=(label,))
    policy = CalibrationPolicy(policy_id="policy.semantic@1", slices=(SlicePolicy(selector={"criticality": "high"}, minimum_samples=1, minimum_agreement=0, maximum_false_positive_rate=1, maximum_false_negative_rate=1),))
    result = _result(snapshot, definition, label, "NO"); result_id = uuid4()
    calibration = JudgeCalibrationService().report(UUID(int=1), snapshot, definition.definition_id, policy, ((result_id, result),))
    metric = JudgeCalibrationService().semantic_metric(metric_id="metric.semantic.correctness@1", snapshot_id=UUID(int=1), label=label, result_id=result_id, result=result, calibration_report_id=uuid4(), calibration_report=calibration, definition=definition, expected_definition_digest=definition.definition_digest, policy=policy)
    assert metric.value == 0.0 and metric.eligibility == "ELIGIBLE"
    stale = calibration.model_copy(update={"calibration_snapshot_digest": _digest("0")})
    metric = JudgeCalibrationService().semantic_metric(metric_id="metric.semantic.correctness@1", snapshot_id=UUID(int=1), label=label, result_id=result_id, result=result, calibration_report_id=uuid4(), calibration_report=stale, definition=definition, expected_definition_digest=definition.definition_digest, policy=policy)
    assert metric.eligibility == "DRIFTED"
    metric = JudgeCalibrationService().semantic_metric(metric_id="metric.semantic.correctness@1", snapshot_id=uuid4(), label=label, result_id=result_id, result=result, calibration_report_id=uuid4(), calibration_report=calibration, definition=definition, expected_definition_digest=definition.definition_digest, policy=policy)
    assert metric.eligibility == "DRIFTED"


def test_calibration_publish_uses_snapshot_and_sorted_result_artifact_lineage():
    class Runs:
        async def start_attempt(self, *_args): return UUID(int=3), 1
    class Artifacts:
        async def complete_with_outputs(self, _run, _attempt, outputs, **_kwargs):
            self.output = outputs[0]
            return (UUID(int=4),)
    definition = _definition(); label = _label("qcase_00000000000000000000000000000001", "high", "PASS")
    snapshot = CalibrationSnapshot(dataset_snapshot_id=uuid4(), dataset_snapshot_digest=_digest("f"), definitions=(definition,), labels=(label,))
    policy = CalibrationPolicy(policy_id="policy.semantic@1", slices=(SlicePolicy(selector={"criticality": "high"}, minimum_samples=1, minimum_agreement=0, maximum_false_positive_rate=1, maximum_false_negative_rate=1),))
    result_id = UUID(int=2); artifacts = Artifacts()
    identifier, report = asyncio.run(JudgeCalibrationService().publish(UUID(int=5), "calibrate", UUID(int=1), snapshot, definition.definition_id, policy, ((result_id, _result(snapshot, definition, label, "PASS")),), Runs(), artifacts))
    assert identifier == UUID(int=4) and artifacts.output[0].parent_artifact_ids == (UUID(int=1), result_id)
    assert report.result_artifact_ids == (result_id,)


def test_calibration_execution_creates_evaluation_run_and_invokes_cases_in_case_order():
    definition = _definition()
    first = _label("qcase_00000000000000000000000000000001", "high", "PASS")
    second = _label("qcase_00000000000000000000000000000002", "high", "PASS")
    snapshot = CalibrationSnapshot(dataset_snapshot_id=uuid4(), dataset_snapshot_digest=_digest("f"), definitions=(definition,), labels=(second, first))
    policy = CalibrationPolicy(policy_id="policy.semantic@1", slices=(SlicePolicy(selector={"criticality": "high"}, minimum_samples=1, minimum_agreement=0, maximum_false_positive_rate=1, maximum_false_negative_rate=1),))
    results = {first.case_id: _result(snapshot, definition, first, "PASS"), second.case_id: _result(snapshot, definition, second, "PASS")}
    class Runs:
        async def create_run(self, kind, plan): self.kind, self.plan = kind, plan; return UUID(int=10)
        async def start_attempt(self, *_args): return UUID(int=11), 1
        async def finish_run(self, _run, succeeded): self.succeeded = succeeded
    class Executor:
        def __init__(self): self.calls = []
        async def invoke(self, _run, stage, _plugin, config, inputs):
            self.calls.append((stage, config["case_id"], inputs)); return (UUID(int=len(self.calls)),)
    class Artifacts:
        async def read_content(self, identifier): return results[[first.case_id, second.case_id][identifier.int - 1]].model_dump_json().encode()
        async def get_artifact_manifest(self, identifier):
            return ArtifactManifest(id=identifier, artifact_type="judge.calibration.snapshot", schema_revision="v1", content_digest=hashlib.sha256(canonical_bytes(snapshot)).hexdigest(), byte_size=1, summary="", storage_locator="x", producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture@1", configuration_digest=_digest("c"), parent_artifact_ids=())
        async def complete_with_outputs(self, *_args, **_kwargs): return (UUID(int=12),)
    runs, executor, artifacts = Runs(), Executor(), Artifacts()
    run_id, report_id, report = asyncio.run(JudgeCalibrationService().execute(UUID(int=1), snapshot, definition.definition_id, policy, {first.case_id: (uuid4(), uuid4()), second.case_id: (uuid4(), uuid4())}, executor, runs, artifacts))
    assert (run_id, report_id, report.result_artifact_ids) == (UUID(int=10), UUID(int=12), (UUID(int=1), UUID(int=2)))
    assert runs.kind.value == "evaluation" and runs.succeeded and [call[1] for call in executor.calls] == [first.case_id, second.case_id]


def test_compile_snapshot_requires_reviewed_golden_case_and_publishes_dataset_evidence_lineage():
    source_id, evidence_id = uuid4(), uuid4(); definition = _definition()
    raw_case = QueryCase(id="qcase_00000000000000000000000000000001", source=SourceArtifactRef(id=source_id, content_digest=_digest("a"), artifact_type="canonical.document"), evidence=SourceArtifactRef(id=evidence_id, content_digest=_digest("b"), artifact_type="evidence.set"), question="Reviewed?", answerability=Answerability.ANSWERABLE, provenance=CaseProvenance(origin=CaseOrigin.MANUAL, operation="create", created_at="2026-01-01T00:00:00Z"), slices={"format":"pdf","processing_class":"native","native_ocr":"native","structure":"prose","language":"en","question_class":"lookup","difficulty":"low","criticality":"high"})
    reviewed = raw_case.model_copy(update={"reviews": (ReviewEvent(reviewer="reviewer", reviewed_at="2026-01-01T00:00:00Z", content_digest=hashlib.sha256(canonical_bytes(raw_case)).hexdigest()),)})
    dataset_raw = {"schema_version":"GoldenDatasetSnapshot/v1", "taxonomy": DatasetContent().taxonomy.model_dump(mode="json"), "annotations":[], "query_cases":[reviewed.model_dump(mode="json")]}
    label_base = {"case_id": reviewed.id, "definition_id": definition.definition_id, "rubric_id": definition.rubric_id, "label":"PASS", "source_artifact_id":str(source_id), "source_digest":_digest("a"), "evidence_artifact_id":str(evidence_id), "evidence_digest":_digest("b"), "slices":reviewed.slices, "reviewer":"reviewer", "reviewed_at":"2026-01-01T00:00:00+00:00", "review_record_id":"jreview_" + "1" * 16, "review_operation":"mark_reviewed"}
    label = CalibrationLabel(**label_base, reviewed_label_digest=digest(label_base))
    class Runs:
        async def start_attempt(self, *_args): return uuid4(), 1
    class Artifacts:
        def __init__(self): self.manifest = ArtifactManifest(id=UUID(int=1), artifact_type="golden.dataset.snapshot", schema_revision="v1", content_digest=hashlib.sha256(json.dumps(dataset_raw, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), byte_size=1, summary="", storage_locator="x", producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture@1", configuration_digest=_digest("c"), parent_artifact_ids=())
        async def get_artifact_manifest(self, _id): return self.manifest
        async def read_content(self, _id): return json.dumps(dataset_raw, sort_keys=True, separators=(",", ":")).encode()
        async def complete_with_outputs(self, *_args, **_kwargs): self.output = _args[2][0][0]; return (UUID(int=2),)
    artifacts = Artifacts(); snapshot_id, snapshot = asyncio.run(JudgeCalibrationService().compile_snapshot(UUID(int=3), "compile", UUID(int=1), (definition,), (label,), Runs(), artifacts))
    assert snapshot_id == UUID(int=2) and artifacts.output.parent_artifact_ids == (UUID(int=1), evidence_id) and snapshot.labels == (label,)
    with pytest.raises(ValueError):
        asyncio.run(JudgeCalibrationService().compile_snapshot(UUID(int=3), "compile", UUID(int=1), (definition,), (label.model_copy(update={"reviewer": "forged"}),), Runs(), artifacts))
    dataset_raw["query_cases"] = [raw_case.model_dump(mode="json")]
    raw = json.dumps(dataset_raw, sort_keys=True, separators=(",", ":")).encode()
    artifacts.manifest = artifacts.manifest.model_copy(update={"content_digest": hashlib.sha256(raw).hexdigest()})
    with pytest.raises(ValueError):
        asyncio.run(JudgeCalibrationService().compile_snapshot(UUID(int=3), "compile", UUID(int=1), (definition,), (label,), Runs(), artifacts))
    dataset_raw["query_cases"] = [reviewed.model_dump(mode="json")]
    artifacts.manifest = artifacts.manifest.model_copy(update={"content_digest": _digest("0")})
    with pytest.raises(ValueError):
        asyncio.run(JudgeCalibrationService().compile_snapshot(UUID(int=3), "compile", UUID(int=1), (definition,), (label,), Runs(), artifacts))


def test_trusted_snapshot_services_fail_closed_when_manifest_bytes_or_lookup_are_unavailable():
    definition = _definition(); label = _label("qcase_00000000000000000000000000000001", "high", "PASS")
    snapshot = CalibrationSnapshot(dataset_snapshot_id=uuid4(), dataset_snapshot_digest=_digest("f"), definitions=(definition,), labels=(label,))
    policy = CalibrationPolicy(policy_id="policy.semantic@1", slices=(SlicePolicy(selector={"criticality":"high"}, minimum_samples=1, minimum_agreement=0, maximum_false_positive_rate=1, maximum_false_negative_rate=1),))
    class NoLookup: pass
    with pytest.raises(ValueError):
        asyncio.run(JudgeCalibrationService().execute(UUID(int=1), snapshot, definition.definition_id, policy, {label.case_id: (uuid4(), uuid4())}, object(), object(), NoLookup()))


def test_semantic_label_requires_bounded_human_review_provenance():
    label = _label("qcase_00000000000000000000000000000001", "high", "PASS")
    with pytest.raises(ValueError):
        CalibrationLabel.model_validate(label.model_dump(exclude={"reviewer", "reviewed_at", "review_record_id", "review_operation"}))
