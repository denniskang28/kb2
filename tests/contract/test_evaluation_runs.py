import asyncio
import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from kb2_runtime.evaluation.datasets.contracts import Answerability, CaseOrigin, CaseProvenance, DatasetContent, QueryCase, ReviewEvent, SourceArtifactRef, canonical_bytes as dataset_bytes
from kb2_runtime.evaluation.metrics import MetricMatch, MetricReport, MetricStatus
from kb2_runtime.evaluation.runs.contracts import ArtifactBinding, ConfidencePolicy, EvaluationManifest, EvaluationSubject, FailedCaseLink, PlanIdentity, QualityGate, RuntimeSummary, SubjectMetricReport, digest
from kb2_runtime.evaluation.runs.service import EvaluationService
from kb2_runtime.trace.contracts import ArtifactManifest
from kb2_runtime.trace.schemas import schema_is_supported


def _digest(char: str) -> str:
    return char * 64


def _binding(case_id: str) -> ArtifactBinding:
    return ArtifactBinding(role="evidence", case_id=case_id, artifact_id=UUID(int=1), artifact_type="evidence.set", content_digest=_digest("a"))


def _manifest(**changes) -> EvaluationManifest:
    case = "qcase_" + "1" * 16
    plan = {"plugin": "fixture.plugin@1"}
    subject = lambda name: EvaluationSubject(subject=name, ingestion_plan=plan, ingestion_plan_digest=digest(plan), query_plan=plan, query_plan_digest=digest(plan), bindings=(_binding(case),), declared_identities=(PlanIdentity(plugin_id="fixture.plugin@1", implementation_digest=_digest("1")),))
    value = dict(dataset_snapshot_id=UUID(int=2), dataset_snapshot_digest=_digest("b"), taxonomy_digest=_digest("c"), input_catalog_digest=_digest("d"), case_ids=(case,), subjects=(subject("baseline"), subject("candidate")), metric_ids=("metric.answer.expected-fact-coverage@1",), runtime=RuntimeSummary(runtime_digest=_digest("e"), package_digest=_digest("f"), implementation_digest=_digest("0"), os_family="linux", architecture="x86_64", resource_sampler_version="resource.v1"))
    value.update(changes)
    return EvaluationManifest(**value)


def _report(value: float, slices: dict[str, str] | None = None) -> MetricReport:
    slice_values = slices or {"format":"pdf", "processing_class":"native", "native_ocr":"native", "structure":"prose", "language":"en", "question_class":"lookup", "difficulty":"low", "criticality":"high"}
    return MetricReport(metric_id="metric.answer.expected-fact-coverage@1", owner="answer", snapshot_artifact_id=UUID(int=2), taxonomy_digest=_digest("c"), slices=slice_values, status=MetricStatus.VALUE, value=value, elapsed_ms=0, labelled_count=1, matched_count=1, metric_family_id="metric.answer.expected-fact-coverage@1", case_id="qcase_" + "1" * 16, question_source_artifact_id=UUID(int=3), label_evidence_artifact_id=UUID(int=1), stage_kind="generation", answer_artifact_id=UUID(int=4), verification_artifact_id=UUID(int=5), final_response_artifact_id=UUID(int=6))


def test_manifest_rejects_unreviewed_inputs_and_registers_evaluation_schemas():
    manifest = _manifest()
    with pytest.raises(ValueError, match="unreviewed"):
        EvaluationService.validate_manifest(manifest, _digest("b"), (), manifest.metric_ids, (_binding(manifest.case_ids[0]),))
    EvaluationService.validate_manifest(manifest, _digest("b"), manifest.case_ids, manifest.metric_ids, (_binding(manifest.case_ids[0]),))
    assert all(schema_is_supported(kind, "v1") for kind in ("evaluation.input.catalog", "evaluation.manifest", "evaluation.gate.report", "evaluation.operation.report", "evaluation.report.catalog", "evaluation.report", "evaluation.comparison"))


def test_hard_gate_cannot_pass_with_missing_data_or_a_failed_slice():
    gate = QualityGate(gate_id="gate.answer", metric_id="metric.answer.expected-fact-coverage@1", owner="answer", selector={"criticality":"high"}, aggregation="mean", minimum_samples=1, direction="higher_is_better", threshold=.9, severity="hard")
    result = EvaluationService.evaluate_gate(gate, ((UUID(int=7), _report(.2)),))
    assert result.state.value == "FAIL"
    with pytest.raises(ValueError):
        QualityGate(gate_id="bad", metric_id=gate.metric_id, owner="answer", selector={"criticality":"high"}, aggregation="mean", minimum_samples=1, severity="hard")


def test_zero_tolerance_invalid_citation_gate_fails_for_metric_diagnostics():
    gate = QualityGate(gate_id="gate.citation", metric_id="metric.answer.expected-fact-coverage@1", owner="answer", selector={"criticality":"high"}, aggregation="any_failure", minimum_samples=1, severity="hard", failure_code="invalid_citation")
    malformed = _report(1.0).model_copy(update={"matches": (MetricMatch(source_id="malformed-citation:fixture", relevant=False, decision_id="malformed"),)})
    assert EvaluationService.evaluate_gate(gate, ((UUID(int=8), malformed),)).state.value == "FAIL"


def test_comparison_marks_multi_axis_non_causal_and_zero_baseline_delta():
    plan_a, plan_b = {"plugin":"a@1"}, {"plugin":"b@1", "limit": 4}
    baseline = _manifest().subjects[0]
    candidate = EvaluationSubject(subject="candidate", ingestion_plan=plan_b, ingestion_plan_digest=digest(plan_b), query_plan=baseline.query_plan, query_plan_digest=baseline.query_plan_digest, bindings=(_binding("qcase_" + "1" * 16),), declared_identities=(PlanIdentity(plugin_id="fixture.plugin@1", implementation_digest=_digest("1")), PlanIdentity(plugin_id="b@1", implementation_digest=_digest("2"))))
    manifest = _manifest(subjects=(baseline, candidate), experiment_name="candidate exploration")
    mode, axis, changes = EvaluationService.axis_diff(manifest)
    assert (mode.value, axis, changes) == ("MULTI_AXIS_NON_CAUSAL", None, ("ingestion.limit", "ingestion.plugin"))
    assert EvaluationService.delta(0, .4).relative_state == "UNDEFINED_BASELINE_ZERO"


def test_publish_manifest_accepts_the_published_golden_snapshot_wire_contract():
    """S-016 snapshots carry GoldenDatasetSnapshot/v1, not DatasetContent directly."""
    class Runs:
        def __init__(self): self.created = 0
        async def create_run(self, *_args): self.created += 1; return uuid4()
        async def start_attempt(self, *_args): return uuid4(), 1
        async def finish_run(self, *_args): pass

    class Artifacts:
        def __init__(self): self.contents, self.manifests = {}, {}
        def add(self, artifact_type, content):
            identifier = uuid4(); self.contents[identifier] = content
            self.manifests[identifier] = ArtifactManifest(id=identifier, artifact_type=artifact_type, schema_revision="v1", content_digest=hashlib.sha256(content).hexdigest(), byte_size=len(content), summary="fixture", storage_locator="fixture", producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture@1", configuration_digest="a" * 64)
            return identifier
        async def get_artifact_manifest(self, identifier): return self.manifests.get(identifier)
        async def read_content(self, identifier): return self.contents[identifier]
        async def complete_with_outputs(self, _run, _attempt, outputs, **_kwargs): return tuple(self.add(item.artifact_type, content) for item, content in outputs)

    async def exercise():
        artifacts = Artifacts(); source_id = artifacts.add("canonical.document", b"{}")
        source = SourceArtifactRef(id=source_id, artifact_type="canonical.document", content_digest=hashlib.sha256(b"{}").hexdigest())
        bare = QueryCase(id="qcase_" + "1" * 16, source=source, slices={"format":"pdf", "processing_class":"native", "native_ocr":"native", "structure":"prose", "language":"en", "question_class":"lookup", "difficulty":"low", "criticality":"high"}, provenance=CaseProvenance(origin=CaseOrigin.MANUAL, operation="create", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)), question="What?", answerability=Answerability.AMBIGUOUS)
        reviewed = bare.model_copy(update={"reviews": (ReviewEvent(reviewer="reviewer", reviewed_at=datetime(2026, 1, 1, tzinfo=timezone.utc), content_digest=hashlib.sha256(dataset_bytes(bare)).hexdigest()),)})
        content = DatasetContent(query_cases=(reviewed,))
        snapshot = json.dumps({"schema_version":"GoldenDatasetSnapshot/v1", "dataset_id":str(uuid4()), "dataset_revision_id":str(uuid4()), "revision":1, "content_digest":hashlib.sha256(dataset_bytes(content)).hexdigest(), "taxonomy":content.taxonomy.model_dump(mode="json"), "annotations":[], "query_cases":[reviewed.model_dump(mode="json")], "sources":[str(source_id)]}, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        snapshot_id = artifacts.add("golden.dataset.snapshot", snapshot)
        binding = ArtifactBinding(role="source", case_id=reviewed.id, artifact_id=source_id, artifact_type="canonical.document", content_digest=source.content_digest)
        plan = {"plugin":"fixture.plugin@1"}; subject = lambda name: EvaluationSubject(subject=name, ingestion_plan=plan, ingestion_plan_digest=digest(plan), query_plan=plan, query_plan_digest=digest(plan), bindings=(binding,), declared_identities=(PlanIdentity(plugin_id="fixture.plugin@1", implementation_digest=_digest("1")),))
        catalog = {"schema_version":"EvaluationInputCatalog/v1", "bindings":[binding.model_dump(mode="json")]}
        manifest = EvaluationManifest(dataset_snapshot_id=snapshot_id, dataset_snapshot_digest=hashlib.sha256(snapshot).hexdigest(), taxonomy_digest=hashlib.sha256(dataset_bytes(content.taxonomy)).hexdigest(), input_catalog_digest=digest(catalog), case_ids=(reviewed.id,), subjects=(subject("baseline"), subject("candidate")), metric_ids=("metric.answer.expected-fact-coverage@1",), runtime=RuntimeSummary(runtime_digest=_digest("e"), package_digest=_digest("f"), implementation_digest=_digest("0"), os_family="linux", architecture="x86_64", resource_sampler_version="resource.v1"))
        forged_plan = {"plugin":"fixture.plugin@1", "implementation_digest":_digest("2")}
        forged_subject = manifest.subjects[0].model_copy(update={"ingestion_plan":forged_plan, "ingestion_plan_digest":digest(forged_plan)})
        forged = manifest.model_copy(update={"subjects":(forged_subject, manifest.subjects[1])})
        runs = Runs()
        with pytest.raises(ValueError, match="implementation identity"):
            await EvaluationService().publish_manifest(forged, runs, artifacts)
        assert runs.created == 0
        return await EvaluationService().publish_manifest(manifest, runs, artifacts)

    run_id, manifest_id = asyncio.run(exercise())
    assert run_id != manifest_id


def test_failed_case_link_rejects_ambiguous_subject_bindings():
    case = "qcase_" + "1" * 16
    baseline = _manifest().subjects[0]
    candidate_binding = ArtifactBinding(role="source", case_id=case, artifact_id=UUID(int=99), artifact_type="canonical.document", content_digest=_digest("9"))
    candidate = EvaluationSubject(subject="candidate", ingestion_plan=baseline.ingestion_plan, ingestion_plan_digest=baseline.ingestion_plan_digest, query_plan=baseline.query_plan, query_plan_digest=baseline.query_plan_digest, bindings=(candidate_binding,), declared_identities=baseline.declared_identities)
    manifest = _manifest(subjects=(baseline, candidate))
    gate = QualityGate(gate_id="gate.answer", metric_id="metric.answer.expected-fact-coverage@1", owner="answer", selector={"criticality":"high"}, aggregation="mean", minimum_samples=1, direction="higher_is_better", threshold=.9, severity="hard")
    report_id = UUID(int=7)
    failed = EvaluationService.evaluate_gate(gate, ((report_id, _report(.2)),))
    with pytest.raises(ValueError, match="subject"):
        EvaluationService.failed_case_links((failed,), ((report_id, _report(.2)),), manifest)


def test_failed_candidate_link_uses_explicit_subject_with_shared_source_and_evidence():
    case = "qcase_" + "1" * 16
    baseline = _manifest().subjects[0]
    shared = (ArtifactBinding(role="source", case_id=case, artifact_id=UUID(int=3), artifact_type="canonical.document", content_digest=_digest("3")), ArtifactBinding(role="evidence", case_id=case, artifact_id=UUID(int=1), artifact_type="evidence.set", content_digest=_digest("1")))
    baseline = baseline.model_copy(update={"bindings": shared})
    candidate = EvaluationSubject(subject="candidate", ingestion_plan=baseline.ingestion_plan, ingestion_plan_digest=baseline.ingestion_plan_digest, query_plan=baseline.query_plan, query_plan_digest=baseline.query_plan_digest, bindings=shared, declared_identities=baseline.declared_identities)
    manifest = _manifest(subjects=(baseline, candidate))
    gate = QualityGate(gate_id="gate.answer", metric_id="metric.answer.expected-fact-coverage@1", owner="answer", selector={"criticality":"high"}, aggregation="mean", minimum_samples=1, direction="higher_is_better", threshold=.9, severity="hard")
    report_id = UUID(int=9); failed = EvaluationService.evaluate_gate(gate, ((report_id, _report(.2)),))
    link = EvaluationService.failed_case_links((failed,), ((report_id, _report(.2)),), manifest, {report_id: "candidate"})[0]
    assert link.subject == "candidate"


def test_failed_case_lineage_validates_full_and_absent_stages_and_rejects_tampering():
    class Artifacts:
        def __init__(self): self.contents, self.manifests = {}, {}
        def add(self, artifact_type, parents=()):
            identifier, raw = uuid4(), (artifact_type + str(uuid4())).encode("ascii")
            self.contents[identifier] = raw
            self.manifests[identifier] = ArtifactManifest(id=identifier, artifact_type=artifact_type, schema_revision="v1", content_digest=hashlib.sha256(raw).hexdigest(), byte_size=len(raw), summary="fixture", storage_locator="fixture", producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture@1", configuration_digest="a" * 64, parent_artifact_ids=parents)
            return identifier
        async def get_artifact_manifest(self, identifier): return self.manifests.get(identifier)
        async def read_content(self, identifier): return self.contents[identifier]

    async def exercise():
        artifacts = Artifacts()
        source = artifacts.add("canonical.document")
        ingestion = artifacts.add("chunk.set", (source,))
        retrieval = artifacts.add("retrieval.candidate.set", (source,))
        fusion = artifacts.add("fusion.candidate.set", (retrieval,))
        rerank = artifacts.add("rerank.candidate.set", (fusion,))
        evidence = artifacts.add("evidence.set", (rerank,))
        generation = artifacts.add("generated.answer", (evidence,))
        verification = artifacts.add("verification.result", (generation,))
        final = artifacts.add("final.response", (verification,))
        metric = artifacts.add("metric.report", (final,))
        evaluation_report = artifacts.add("evaluation.report", (metric,))
        full = FailedCaseLink(case_id="qcase_" + "1" * 16, subject="baseline", gate_id="gate.answer", source_artifact_id=source, ingestion_artifact_id=ingestion, retrieval_artifact_id=retrieval, fusion_artifact_id=fusion, rerank_artifact_id=rerank, evidence_artifact_id=evidence, generation_artifact_id=generation, verification_artifact_id=verification, final_response_artifact_id=final, metric_report_id=metric)
        service = EvaluationService()
        checked = await service.validate_failed_case_lineage(full, artifacts, evaluation_report_id=evaluation_report, evaluation_run_id=UUID(int=77))
        absent = full.model_copy(update={"generation_artifact_id":None, "verification_artifact_id":None, "final_response_artifact_id":None, "metric_report_id":None})
        await service.validate_failed_case_lineage(absent, artifacts)
        artifacts.manifests[evidence] = artifacts.manifests[evidence].model_copy(update={"parent_artifact_ids": (source,)})
        with pytest.raises(ValueError, match="lineage"):
            await service.validate_failed_case_lineage(full, artifacts)
        artifacts.manifests[evidence] = artifacts.manifests[evidence].model_copy(update={"parent_artifact_ids": (rerank,)})
        artifacts.contents[final] = b"tampered"
        with pytest.raises(ValueError, match="digest"):
            await service.validate_failed_case_lineage(full, artifacts)
        artifacts.contents[final] = artifacts.manifests[final].artifact_type.encode("ascii")
        artifacts.manifests[final] = artifacts.manifests[final].model_copy(update={"content_digest": hashlib.sha256(artifacts.contents[final]).hexdigest()})
        with pytest.raises(ValueError, match="identity"):
            await service.validate_failed_case_lineage(full.model_copy(update={"ingestion_artifact_id": artifacts.add("opaque.bytes", (source,))}), artifacts)
        return checked

    checked = asyncio.run(exercise())
    assert checked.evaluation_report_id is not None and checked.evaluation_run_id == UUID(int=77)


def test_orchestration_replay_and_fixed_input_comparison_publish_immutable_artifacts():
    class Runs:
        def __init__(self): self.created, self.finished = [], []
        async def create_run(self, kind, plan): self.created.append((kind, plan)); return uuid4()
        async def start_attempt(self, *_args): return uuid4(), 1
        async def finish_run(self, run, succeeded): self.finished.append((run, succeeded))

    class Artifacts:
        def __init__(self): self.contents, self.manifests = {}, {}
        def add(self, artifact_type, content, parents=()):
            identifier = uuid4(); self.contents[identifier] = content
            self.manifests[identifier] = ArtifactManifest(id=identifier, artifact_type=artifact_type, schema_revision="v1", content_digest=hashlib.sha256(content).hexdigest(), byte_size=len(content), summary="fixture", storage_locator="fixture", producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture@1", configuration_digest="a" * 64, parent_artifact_ids=parents)
            return identifier
        async def get_artifact_manifest(self, identifier): return self.manifests.get(identifier)
        async def read_content(self, identifier): return self.contents[identifier]
        async def complete_with_outputs(self, _run, _attempt, outputs, **_kwargs): return tuple(self.add(item.artifact_type, content, item.parent_artifact_ids) for item, content in outputs)

    async def exercise():
        artifacts, runs = Artifacts(), Runs()
        source_id, evidence_id = artifacts.add("canonical.document", b"source"), artifacts.add("evidence.set", b"evidence")
        ingestion_id = artifacts.add("chunk.set", b"chunks", (source_id,))
        answer_id, verification_id, final_id = artifacts.add("generated.answer", b"answer"), artifacts.add("verification.result", b"verification"), artifacts.add("final.response", b"final")
        source = SourceArtifactRef(id=source_id, artifact_type="canonical.document", content_digest=hashlib.sha256(b"source").hexdigest())
        bare = QueryCase(id="qcase_" + "2" * 16, source=source, slices={"format":"pdf", "processing_class":"native", "native_ocr":"native", "structure":"prose", "language":"en", "question_class":"lookup", "difficulty":"low", "criticality":"high"}, provenance=CaseProvenance(origin=CaseOrigin.MANUAL, operation="create", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)), question="What?", answerability=Answerability.AMBIGUOUS)
        reviewed = bare.model_copy(update={"reviews": (ReviewEvent(reviewer="reviewer", reviewed_at=datetime(2026, 1, 1, tzinfo=timezone.utc), content_digest=hashlib.sha256(dataset_bytes(bare)).hexdigest()),)})
        content = DatasetContent(query_cases=(reviewed,))
        snapshot = json.dumps({"schema_version":"GoldenDatasetSnapshot/v1", "dataset_id":str(uuid4()), "dataset_revision_id":str(uuid4()), "revision":1, "content_digest":hashlib.sha256(dataset_bytes(content)).hexdigest(), "taxonomy":content.taxonomy.model_dump(mode="json"), "annotations":[], "query_cases":[reviewed.model_dump(mode="json")], "sources":[str(source_id)]}, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        snapshot_id = artifacts.add("golden.dataset.snapshot", snapshot)
        bindings = (ArtifactBinding(role="source", case_id=reviewed.id, artifact_id=source_id, artifact_type="canonical.document", content_digest=source.content_digest), ArtifactBinding(role="ingestion", case_id=reviewed.id, artifact_id=ingestion_id, artifact_type="chunk.set", content_digest=hashlib.sha256(b"chunks").hexdigest()), ArtifactBinding(role="evidence", case_id=reviewed.id, artifact_id=evidence_id, artifact_type="evidence.set", content_digest=hashlib.sha256(b"evidence").hexdigest()), ArtifactBinding(role="answer", case_id=reviewed.id, artifact_id=answer_id, artifact_type="generated.answer", content_digest=hashlib.sha256(b"answer").hexdigest()), ArtifactBinding(role="verification", case_id=reviewed.id, artifact_id=verification_id, artifact_type="verification.result", content_digest=hashlib.sha256(b"verification").hexdigest()), ArtifactBinding(role="final_response", case_id=reviewed.id, artifact_id=final_id, artifact_type="final.response", content_digest=hashlib.sha256(b"final").hexdigest()))
        catalog = {"schema_version":"EvaluationInputCatalog/v1", "bindings":[item.model_dump(mode="json") for item in sorted(bindings, key=lambda item: (item.case_id or "", item.role, str(item.artifact_id)))]}
        def manifest(candidate_plugin):
            baseline_plan, candidate_plan = {"plugin":"baseline@1"}, {"plugin":candidate_plugin}
            identities = (PlanIdentity(plugin_id="baseline@1", implementation_digest=_digest("1")), PlanIdentity(plugin_id=candidate_plugin, implementation_digest=_digest("2")))
            subject = lambda name, ingestion, query: EvaluationSubject(subject=name, ingestion_plan=ingestion, ingestion_plan_digest=digest(ingestion), query_plan=query, query_plan_digest=digest(query), bindings=bindings, declared_identities=identities)
            return EvaluationManifest(dataset_snapshot_id=snapshot_id, dataset_snapshot_digest=hashlib.sha256(snapshot).hexdigest(), taxonomy_digest=hashlib.sha256(dataset_bytes(content.taxonomy)).hexdigest(), input_catalog_digest=digest(catalog), case_ids=(reviewed.id,), subjects=(subject("baseline", baseline_plan, baseline_plan), subject("candidate", baseline_plan, candidate_plan)), metric_ids=("metric.answer.expected-fact-coverage@1", "metric.ingestion.cer@1"), runtime=RuntimeSummary(runtime_digest=_digest("e"), package_digest=_digest("f"), implementation_digest=_digest("0"), os_family="linux", architecture="x86_64", resource_sampler_version="resource.v1"))
        service = EvaluationService(registered_metrics=("metric.answer.expected-fact-coverage@1", "metric.ingestion.cer@1"))
        _, first_manifest = await service.publish_manifest(manifest("candidate-a@1"), runs, artifacts)
        metric = _report(1.0).model_copy(update={"snapshot_artifact_id":snapshot_id, "taxonomy_digest":hashlib.sha256(dataset_bytes(content.taxonomy)).hexdigest(), "case_id":reviewed.id, "question_source_artifact_id":source_id, "label_evidence_artifact_id":evidence_id, "answer_artifact_id":answer_id, "verification_artifact_id":verification_id, "final_response_artifact_id":final_id})
        metric_id = artifacts.add("metric.report", metric.model_dump_json().encode("ascii"))
        ingestion_metric = MetricReport(metric_id="metric.ingestion.cer@1", owner="ingestion", snapshot_artifact_id=snapshot_id, taxonomy_digest=hashlib.sha256(dataset_bytes(content.taxonomy)).hexdigest(), slices=reviewed.slices, status=MetricStatus.VALUE, value=1.0, elapsed_ms=0, labelled_count=1, matched_count=1, required_annotation_kinds=("text_span",), document_id="doc_0000000000000001", expected_artifact_id=source_id, observed_artifact_id=ingestion_id)
        ingestion_metric_id = artifacts.add("metric.report", ingestion_metric.model_dump_json().encode("ascii"))
        _, _, ingestion_report = await service.orchestrate(first_manifest, (SubjectMetricReport(subject="baseline", metric_artifact_id=ingestion_metric_id),), runs, artifacts)
        assert ingestion_report.layers["ingestion"] == (ingestion_metric_id,)
        assert ingestion_report.report_subjects[ingestion_metric_id] == "baseline"
        assert ingestion_report.aggregate_ids
        for field in ("answer_artifact_id", "verification_artifact_id", "final_response_artifact_id"):
            unpinned = metric.model_copy(update={field: uuid4()})
            unpinned_id = artifacts.add("metric.report", unpinned.model_dump_json().encode("ascii"))
            with pytest.raises(ValueError, match="stage bindings"):
                await service.orchestrate(first_manifest, ((unpinned_id, unpinned),), runs, artifacts)
        _, first_report, _ = await service.orchestrate(first_manifest, (SubjectMetricReport(subject="baseline", metric_artifact_id=metric_id),), runs, artifacts)
        _, observation_id, observation = await service.replay(first_manifest, (SubjectMetricReport(subject="baseline", metric_artifact_id=metric_id),), runs, artifacts, original_report_id=first_report)
        _, second_manifest = await service.publish_manifest(manifest("candidate-b@1"), runs, artifacts)
        _, second_report, _ = await service.orchestrate(second_manifest, (SubjectMetricReport(subject="baseline", metric_artifact_id=metric_id),), runs, artifacts)
        _, comparison_id, result = await service.compare(first_report, second_report, runs, artifacts)
        return artifacts, runs, first_manifest, first_report, observation_id, observation, comparison_id, result

    artifacts, runs, first_manifest, first_report, observation_id, observation, comparison_id, result = asyncio.run(exercise())
    assert artifacts.manifests[observation_id].artifact_type == "evaluation.replay.observation"
    observation_parents = artifacts.manifests[observation_id].parent_artifact_ids
    assert observation_parents[:2] == (first_manifest, first_report)
    assert artifacts.manifests[observation_parents[2]].artifact_type == "evaluation.report"
    assert observation.state == "STABLE"
    comparison = json.loads(artifacts.contents[comparison_id])
    assert comparison["layers"] and comparison["metric_report_ids"] and comparison["gates"]
    assert result.mode.value == "SINGLE_AXIS" and result.axis == "query.plugin"
    assert all(succeeded for _, succeeded in runs.finished)


def test_replay_observation_distinguishes_stable_model_and_runtime_differences():
    stable = EvaluationService.replay_observation(b'{"operation":{},"reports":["a"]}', b'{"operation":{"elapsed_ms":1},"reports":["a"]}', _digest("a"), _digest("a"))
    model = EvaluationService.replay_observation(b'{"reports":["a"]}', b'{"reports":["b"]}', _digest("a"), _digest("a"))
    environment = EvaluationService.replay_observation(b'{"reports":["a"]}', b'{"reports":["a"]}', _digest("a"), _digest("b"))
    assert (stable.state, model.state, environment.state) == ("STABLE", "MODEL_OUTPUT_CHANGED", "ENVIRONMENT_CHANGED")
    assert environment.expected_runtime_digest == _digest("a") and environment.observed_runtime_digest == _digest("b")


def test_subject_metric_reports_reject_shared_input_legacy_attribution():
    """Shared source/Evidence needs the explicit S-021 subject wrapper."""
    case = "qcase_" + "1" * 16
    plan = {"plugin": "fixture.plugin@1"}
    identity = (PlanIdentity(plugin_id="fixture.plugin@1", implementation_digest=_digest("1")),)
    source = ArtifactBinding(role="source", case_id=case, artifact_id=UUID(int=1), artifact_type="canonical.document", content_digest=_digest("a"))
    evidence = ArtifactBinding(role="evidence", case_id=case, artifact_id=UUID(int=2), artifact_type="evidence.set", content_digest=_digest("b"))
    baseline = EvaluationSubject(subject="baseline", ingestion_plan=plan, ingestion_plan_digest=digest(plan), query_plan=plan, query_plan_digest=digest(plan), bindings=(source, evidence), declared_identities=identity)
    candidate = baseline.model_copy(update={"subject": "candidate"})
    manifest = EvaluationManifest(dataset_snapshot_id=UUID(int=3), dataset_snapshot_digest=_digest("c"), taxonomy_digest=_digest("d"), input_catalog_digest=digest({"schema_version":"EvaluationInputCatalog/v1","bindings":[source.model_dump(mode="json"), evidence.model_dump(mode="json")]}), case_ids=(case,), subjects=(baseline, candidate), metric_ids=("metric.answer.expected-fact-coverage@1",), runtime=RuntimeSummary(runtime_digest=_digest("e"), package_digest=_digest("f"), implementation_digest=_digest("0"), os_family="linux", architecture="x86_64", resource_sampler_version="resource.v1"))
    report = _report(.1).model_copy(update={"case_id": case, "question_source_artifact_id": UUID(int=1), "label_evidence_artifact_id": UUID(int=2)})
    gate = QualityGate(gate_id="gate.answer", metric_id=report.metric_id, owner="answer", selector={"criticality":"high"}, aggregation="mean", minimum_samples=1, direction="higher_is_better", threshold=.9, severity="hard")
    result = EvaluationService.evaluate_gate(gate, ((UUID(int=4), report),))
    with pytest.raises(ValueError, match="subject"):
        EvaluationService.failed_case_links((result,), ((UUID(int=4), report),), manifest)


def test_confidence_policy_contract_and_partial_operation_observation():
    assert ConfidencePolicy(kind="none").level is None
    assert ConfidencePolicy(kind="wilson", level=.95).level == .95
    with pytest.raises(ValueError, match="level"):
        ConfidencePolicy(kind="wilson")
    before = __import__("resource").getrusage(__import__("resource").RUSAGE_SELF)
    operation = EvaluationService.operation(__import__("time").monotonic_ns(), before, __import__("resource").getrusage(__import__("resource").RUSAGE_SELF))
    assert operation.availability == "PARTIAL" and operation.io_bytes is None


def test_recursive_catalog_preserves_every_parent_beyond_direct_parent_limit():
    class Runs:
        async def start_attempt(self, *_args): return uuid4(), 1

    class Artifacts:
        def __init__(self): self.parents = {}
        async def complete_with_outputs(self, _run, _attempt, outputs, **_kwargs):
            identifiers = []
            for item, _raw in outputs:
                identifier = uuid4(); self.parents[identifier] = item.parent_artifact_ids; identifiers.append(identifier)
            return tuple(identifiers)

    async def exercise():
        artifacts, leaves = Artifacts(), tuple(uuid4() for _ in range(65))
        root = await EvaluationService()._publish_report_catalog_tree(uuid4(), leaves, Runs(), artifacts)
        reachable = set()
        def walk(identifier):
            for parent in artifacts.parents.get(identifier, ()):
                if parent not in reachable:
                    reachable.add(parent); walk(parent)
        walk(root)
        return leaves, artifacts, root, reachable

    leaves, artifacts, root, reachable = asyncio.run(exercise())
    assert len(artifacts.parents[root]) == 2
    assert set(leaves) <= reachable
