import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from kb2_runtime.evaluation.answer import AnswerMetricPlugin
from kb2_runtime.evaluation.answer.plugin import _answer_with_raw_citations, _cohort_digest, _fact_matches
from kb2_runtime.evaluation.answer.contracts import AnswerMetricConfig
from kb2_runtime.evaluation.datasets.contracts import DEFAULT_TAXONOMY, Answerability, CaseOrigin, CaseProvenance, DatasetContent, QueryCase, ReviewEvent, SourceArtifactRef, canonical_bytes
from kb2_runtime.evaluation.ingestion import MetricAggregator, MetricReport, MetricStatus
from kb2_runtime.generation.contracts import FinalResponse, GeneratedAnswer, VerificationResult
from kb2_runtime.plugins.bootstrap import ANSWER_METRIC_DESCRIPTORS
from kb2_runtime.plugins.bootstrap import bootstrap_registry
from kb2_runtime.plugins.contracts import RunnerType
from kb2_runtime.plugins.executor import PluginExecutor
from kb2_runtime.plugins.runner import InProcessRunner
from kb2_runtime.trace.contracts import ArtifactManifest
from kb2_runtime.chunking.contracts import ChunkerConfig
from kb2_runtime.chunking.processor import process
from kb2_runtime.indexing.embedding import embed_chunk_set
from kb2_runtime.indexing.hybrid import build_index
from kb2_runtime.indexing.projection import project_search_documents
from kb2_runtime.indexing.serializer import search_index_result_bytes


def case(**changes):
    source = SourceArtifactRef(id=uuid4(), content_digest="a" * 64, artifact_type="canonical.document")
    evidence = SourceArtifactRef(id=uuid4(), content_digest="b" * 64, artifact_type="evidence.set")
    value = dict(id="qcase_" + "1" * 16, source=source, evidence=evidence, question="What happened?", answerability=Answerability.ANSWERABLE,
                 expected_facts=("Revenue increased", "Q4 results"), forbidden_facts=("declined",), required_citation_keys=("cit_" + "2" * 32,),
                 slices={key: values[0] for key, values in DEFAULT_TAXONOMY.dimensions.items()},
                 provenance=CaseProvenance(origin=CaseOrigin.MANUAL, operation="create", created_at="2026-01-01T00:00:00Z"))
    value.update(changes)
    return QueryCase(**value)


def answer(evidence_id):
    return GeneratedAnswer(answer_id="ans_" + "3" * 32, evidence_artifact_id=evidence_id, evidence_digest="b" * 64, question_artifact_id=uuid4(), question_digest="c" * 64,
        generator_plugin_id="generator.fixture@1", implementation_digest="d" * 64, configuration_digest="e" * 64,
        answer="Revenue\u3000increased. Revenue increased again.", citation_keys=("cit_" + "2" * 32,), attempt=1)


def base(plugin, query, evidence_id, final_id, answer_id=None, verification_id=None):
    return plugin._base(query, DatasetContent(), uuid4(), evidence_id, final_id, answer_id, verification_id)


def test_fact_matching_is_unicode_whitespace_normalized_and_retains_original_repeated_spans():
    spans = _fact_matches("Revenue\u3000increased. Revenue increased again.", "revenue increased")
    assert spans == ((0, 17), (19, 36))


def test_fact_and_forbidden_metrics_keep_zero_distinct_from_missing_labels():
    query = case()
    plugin = AnswerMetricPlugin("metric.answer.forbidden-fact-violation@1")
    report = MetricReport.model_validate_json(plugin._report(base(plugin, query, query.evidence.id, uuid4(), uuid4(), uuid4()), MetricStatus.VALUE, 0.0, 1, 0, ()).outputs[0].content)
    assert (report.value, report.direction, report.status) == (0.0, "lower_is_better", MetricStatus.VALUE)
    expected = AnswerMetricPlugin("metric.answer.expected-fact-coverage@1")
    missing = MetricReport.model_validate_json(expected._report(base(expected, query, query.evidence.id, uuid4(), uuid4(), uuid4()), MetricStatus.INSUFFICIENT_LABELS, None, 0, 0, ()).outputs[0].content)
    assert missing.value is None and missing.status is MetricStatus.INSUFFICIENT_LABELS


def test_citation_precision_and_recall_remain_separate_for_missing_required_key():
    query = case(required_citation_keys=("cit_" + "2" * 32, "cit_" + "4" * 32))
    evidence_id, final_id = query.evidence.id, uuid4()
    item = SimpleNamespace(citation_key="cit_" + "2" * 32, evidence_id="evd_" + "5" * 32, locators=())
    generated = answer(evidence_id)
    verification = VerificationResult(verification_id="ver_" + "6" * 32, generated_answer_artifact_id=uuid4(), evidence_artifact_id=evidence_id, evidence_digest="b" * 64,
        outcome="pass", resolved_citation_keys=generated.citation_keys, missing_citation_keys=(), answerable=True)
    precision_plugin = AnswerMetricPlugin("metric.citation.precision@1")
    precision = MetricReport.model_validate_json(precision_plugin._citations(base(precision_plugin, query, evidence_id, final_id, uuid4(), uuid4()), query, SimpleNamespace(items=(item,)), generated, verification).outputs[0].content)
    recall_plugin = AnswerMetricPlugin("metric.citation.recall@1")
    recall = MetricReport.model_validate_json(recall_plugin._citations(base(recall_plugin, query, evidence_id, final_id, uuid4(), uuid4()), query, SimpleNamespace(items=(item,)), generated, verification).outputs[0].content)
    assert (precision.value, recall.value, recall.matched_count) == (1.0, 0.5, 1)
    assert any(match.decision_id == "missing" for match in recall.matches)


def test_malformed_citation_is_retained_as_explicit_zero_precision_evidence():
    query = case()
    generated = answer(query.evidence.id)
    payload = generated.model_dump(mode="json")
    payload["citation_keys"] = ["not-a-citation"]
    parsed, raw_citations = _answer_with_raw_citations(json.dumps(payload).encode())
    verification = VerificationResult(verification_id="ver_" + "6" * 32, generated_answer_artifact_id=uuid4(), evidence_artifact_id=query.evidence.id, evidence_digest="b" * 64, outcome="repairable", answerable=False)
    plugin = AnswerMetricPlugin("metric.citation.precision@1")
    report = MetricReport.model_validate_json(plugin._citations(base(plugin, query, query.evidence.id, uuid4(), uuid4(), uuid4()), query, SimpleNamespace(items=()), parsed, verification, raw_citations).outputs[0].content)
    assert (report.status, report.value, report.matches[0].decision_id) == (MetricStatus.VALUE, 0.0, "malformed")


def test_decision_cohort_config_is_frozen_and_identifies_reports():
    identifiers = ("qcase_" + "1" * 16, "qcase_" + "2" * 16)
    config = AnswerMetricConfig(case_id=identifiers[0], cohort=identifiers)
    query = case(id=identifiers[0])
    response = FinalResponse(response_id="fin_" + "7" * 32, state="ANSWERED", evidence_artifact_id=query.evidence.id, answer="ok", citation_keys=("cit_" + "2" * 32,))
    report = MetricReport.model_validate_json(AnswerMetricPlugin("metric.decision.answerability-precision@1")._decision(query, DatasetContent(), uuid4(), query.evidence.id, uuid4(), response, config.cohort).outputs[0].content)
    assert report.cohort_digest == _cohort_digest(config.cohort)


def test_decision_aggregate_rejects_partial_configured_cohort_and_accepts_exact_set():
    identifiers = ("qcase_" + "a" * 16, "qcase_" + "b" * 16)
    plugin = AnswerMetricPlugin("metric.decision.answerability-precision@1")

    def report(identifier):
        query = case(id=identifier)
        response = FinalResponse(response_id="fin_" + ("8" if identifier == identifiers[0] else "9") * 32, state="ANSWERED", evidence_artifact_id=query.evidence.id, answer="ok", citation_keys=("cit_" + "2" * 32,))
        return MetricReport.model_validate_json(plugin._decision(query, DatasetContent(), uuid4(), query.evidence.id, uuid4(), response, identifiers).outputs[0].content)

    first, second = report(identifiers[0]), report(identifiers[1])
    with pytest.raises(ValueError, match="configured cohort"):
        MetricAggregator().aggregate(((uuid4(), first),), plugin.metric_id, {"language": "en"})
    aggregate = MetricAggregator().aggregate(((uuid4(), first), (uuid4(), second)), plugin.metric_id, {"language": "en"})
    assert aggregate.cohort_case_ids == identifiers


def test_review_digest_detects_unreviewed_and_stale_cases_before_metric_output():
    query = case()
    reviewed = query.model_copy(update={"reviews": (ReviewEvent(reviewer="fixture", reviewed_at="2026-01-01T00:00:00Z", content_digest=hashlib.sha256(canonical_bytes(query)).hexdigest()),)})
    from kb2_runtime.evaluation.datasets.service import DatasetService
    assert DatasetService._is_reviewed(reviewed)
    assert not DatasetService._is_reviewed(query)
    assert not DatasetService._is_reviewed(reviewed.model_copy(update={"expected_facts": ("changed",)}))


@pytest.mark.parametrize(("metric_id", "answerability", "state", "status", "value", "outcome"), [
    ("metric.decision.answerability-precision@1", Answerability.ANSWERABLE, "ANSWERED", MetricStatus.VALUE, 1.0, "TP"),
    ("metric.decision.ambiguity-recall@1", Answerability.AMBIGUOUS, "ABSTAINED", MetricStatus.VALUE, 0.0, "FN"),
    ("metric.decision.abstention-precision@1", Answerability.ANSWERABLE, "ABSTAINED", MetricStatus.VALUE, 0.0, "FP"),
    ("metric.decision.answerability-precision@1", Answerability.UNANSWERABLE, "FAILED", MetricStatus.NOT_APPLICABLE, None, "TN"),
])
def test_decision_metrics_keep_answerability_and_final_state_separate(metric_id, answerability, state, status, value, outcome):
    query = case(answerability=answerability)
    response = FinalResponse(response_id="fin_" + "7" * 32, state=state, evidence_artifact_id=query.evidence.id, action="Retry." if state != "ANSWERED" else None,
        answer="ok" if state == "ANSWERED" else None, citation_keys=("cit_" + "2" * 32,) if state == "ANSWERED" else ())
    report = MetricReport.model_validate_json(AnswerMetricPlugin(metric_id)._decision(query, DatasetContent(), uuid4(), query.evidence.id, uuid4(), response).outputs[0].content)
    assert (report.status, report.value, report.matches[0].decision_id) == (status, value, outcome)


def test_metric_match_rejects_partial_spans_and_answer_reports_require_all_attempt_bindings():
    with pytest.raises(ValueError):
        MetricReport(metric_id="metric.answer.expected-fact-coverage@1", owner="answer", snapshot_artifact_id=uuid4(), taxonomy_digest=hashlib.sha256(b"taxonomy").hexdigest(), slices={key: values[0] for key, values in DEFAULT_TAXONOMY.dimensions.items()}, status=MetricStatus.VALUE, value=1, elapsed_ms=0, labelled_count=1, matched_count=1, metric_family_id="metric.answer.expected-fact-coverage@1", case_id="qcase_" + "1" * 16, question_source_artifact_id=uuid4(), label_evidence_artifact_id=uuid4(), stage_kind="generation", final_response_artifact_id=uuid4())


def test_registered_answer_metric_ports_preserve_exact_trace_parents():
    descriptors = {descriptor.plugin_id: descriptor for descriptor in ANSWER_METRIC_DESCRIPTORS}
    citation = descriptors["metric.citation.recall@1"]
    decision = descriptors["metric.decision.abstention-recall@1"]
    assert citation.input_schemas == (("golden.dataset.snapshot", "v1"), ("evidence.set", "v1"), ("generated.answer", "v1"), ("verification.result", "v1"), ("final.response", "v1"))
    assert decision.input_schemas == (("golden.dataset.snapshot", "v1"), ("evidence.set", "v1"), ("final.response", "v1"))


def test_answer_attempt_aggregate_keeps_separate_answer_artifact_identities():
    query = case()
    plugin = AnswerMetricPlugin("metric.answer.expected-fact-coverage@1")
    first = MetricReport.model_validate_json(
        plugin._report(
            base(plugin, query, query.evidence.id, uuid4(), uuid4(), uuid4()),
            MetricStatus.VALUE,
            1.0,
            1,
            1,
            (),
        ).outputs[0].content
    )
    second = MetricReport.model_validate_json(
        plugin._report(
            base(plugin, query, query.evidence.id, uuid4(), uuid4(), uuid4()),
            MetricStatus.VALUE,
            0.0,
            1,
            0,
            (),
        ).outputs[0].content
    )

    aggregate = MetricAggregator().aggregate(
        ((uuid4(), first), (uuid4(), second)), first.metric_id, {"language": "en"}
    )

    assert (aggregate.case_count, aggregate.scored_count, aggregate.value) == (1, 2, 0.5)


def test_decision_precision_aggregate_reduces_tp_fp_fn_evidence_not_case_scores():
    plugin = AnswerMetricPlugin("metric.decision.answerability-precision@1")

    def report(case_id: str, answerability: Answerability, state: str) -> MetricReport:
        query = case(id=case_id, answerability=answerability)
        response = FinalResponse(
            response_id="fin_" + "7" * 32,
            state=state,
            evidence_artifact_id=query.evidence.id,
            action="Retry." if state != "ANSWERED" else None,
            answer="ok" if state == "ANSWERED" else None,
            citation_keys=("cit_" + "2" * 32,) if state == "ANSWERED" else (),
        )
        return MetricReport.model_validate_json(
            plugin._decision(query, DatasetContent(), uuid4(), query.evidence.id, uuid4(), response).outputs[0].content
        )

    reports = (
        (uuid4(), report("qcase_" + "1" * 16, Answerability.ANSWERABLE, "ANSWERED")),  # TP
        (uuid4(), report("qcase_" + "2" * 16, Answerability.UNANSWERABLE, "ANSWERED")),  # FP
        (uuid4(), report("qcase_" + "3" * 16, Answerability.ANSWERABLE, "ABSTAINED")),  # FN
    )

    aggregate = MetricAggregator().aggregate(reports, plugin.metric_id, {"language": "en"})

    assert (aggregate.value, aggregate.sample_count, aggregate.scored_count) == (0.5, 2, 2)
    assert (aggregate.not_applicable_count, aggregate.insufficient_labels_count) == (1, 0)


def test_executor_failed_answer_report_has_bounded_navigable_generation_trace():
    class Artifacts:
        def __init__(self):
            self.contents, self.manifests = {}, {}

        def add(self, artifact_type, content, parents=()):
            identifier = uuid4()
            self.contents[identifier] = content
            self.manifests[identifier] = ArtifactManifest(
                id=identifier, artifact_type=artifact_type, schema_revision="v1",
                content_digest=hashlib.sha256(content).hexdigest(), byte_size=len(content),
                summary="fixture", storage_locator="sha256/fixture", producing_run_id=uuid4(),
                producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture.source@1",
                configuration_digest="a" * 64, parent_artifact_ids=parents,
            )
            return identifier

        async def get_artifact_manifest(self, identifier): return self.manifests.get(identifier)
        async def read_content(self, identifier): return self.contents[identifier]
        async def complete_with_outputs(self, _run_id, _attempt_id, outputs, **_):
            return tuple(self.add(item.artifact_type, content, item.parent_artifact_ids) for item, content in outputs)

    class Runs:
        async def start_attempt(self, *_): return uuid4(), 1
        async def fail_attempt(self, *_args, **_kwargs): pass

    async def exercise():
        source = (Path(__file__).parents[1] / "fixtures" / "ingestion" / "table-heavy-canonical.json").read_bytes()
        chunks = process(source, ChunkerConfig(strategy="table", max_tokens=64))
        index = search_index_result_bytes(await build_index(project_search_documents(chunks, embed_chunk_set(chunks))))
        artifacts = Artifacts()
        canonical_id = artifacts.add("canonical.document", source)
        question_id = artifacts.add("opaque.bytes", b"revenue metrics")
        index_id = artifacts.add("search.index.result", index)
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, Runs(), artifacts)  # type: ignore[arg-type]
        retrieval_id = (await executor.invoke(uuid4(), "keyword", "retriever.keyword@1", {"limit": 8}, (question_id, index_id)))[0]
        evidence_id = (await executor.invoke(uuid4(), "context", "context.from-retrieval@1", {"minimum_items": 0}, (retrieval_id, index_id)))[0]
        query = case(source=SourceArtifactRef(id=canonical_id, content_digest=artifacts.manifests[canonical_id].content_digest, artifact_type="canonical.document"),
                     evidence=SourceArtifactRef(id=evidence_id, content_digest=artifacts.manifests[evidence_id].content_digest, artifact_type="evidence.set"),
                     expected_facts=("missing reviewed fact",))
        query = query.model_copy(update={"reviews": (ReviewEvent(reviewer="fixture", reviewed_at="2026-01-01T00:00:00Z", content_digest=hashlib.sha256(canonical_bytes(query)).hexdigest()),)})
        snapshot = {"schema_version": "GoldenDatasetSnapshot/v1", "taxonomy": DEFAULT_TAXONOMY.model_dump(mode="json"), "annotations": [], "query_cases": [query.model_dump(mode="json")]}
        snapshot_id = artifacts.add("golden.dataset.snapshot", json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii"))
        generated = answer(evidence_id).model_copy(update={"answer": "Fluent but unsupported output.", "evidence_digest": artifacts.manifests[evidence_id].content_digest,
                                                           "question_artifact_id": question_id, "question_digest": artifacts.manifests[question_id].content_digest})
        answer_id = artifacts.add("generated.answer", generated.model_dump_json().encode(), (question_id, evidence_id))
        verification = VerificationResult(verification_id="ver_" + "8" * 32, generated_answer_artifact_id=answer_id, evidence_artifact_id=evidence_id, evidence_digest=artifacts.manifests[evidence_id].content_digest, outcome="repairable", failure_codes=("UNSUPPORTED_CONTENT",), answerable=False)
        verification_id = artifacts.add("verification.result", verification.model_dump_json().encode(), (answer_id, evidence_id))
        final = FinalResponse(response_id="fin_" + "9" * 32, state="FAILED", evidence_artifact_id=evidence_id, verification_artifact_id=verification_id, generated_answer_artifact_id=answer_id, action="Retry.")
        final_id = artifacts.add("final.response", final.model_dump_json().encode(), (evidence_id, verification_id, answer_id))
        report_id = (await executor.invoke(uuid4(), "metric.answer.failed", "metric.answer.expected-fact-coverage@1", {"case_id": query.id}, (snapshot_id, evidence_id, answer_id, verification_id, final_id)))[0]
        return artifacts, report_id, snapshot_id, evidence_id, answer_id, verification_id, final_id, retrieval_id

    artifacts, report_id, snapshot_id, evidence_id, answer_id, verification_id, final_id, retrieval_id = asyncio.run(exercise())
    report_raw = artifacts.contents[report_id]
    report = MetricReport.model_validate_json(report_raw)
    assert report.value == 0.0
    assert artifacts.manifests[report_id].parent_artifact_ids == (snapshot_id, evidence_id, answer_id, verification_id, final_id)
    assert artifacts.manifests[final_id].parent_artifact_ids == (evidence_id, verification_id, answer_id)
    assert artifacts.manifests[evidence_id].parent_artifact_ids[0] == retrieval_id
    assert b"Fluent but unsupported output." not in report_raw
    assert b"revenue metrics" not in report_raw
