import json
import asyncio
import hashlib
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from kb2_runtime.evaluation.datasets.contracts import DEFAULT_TAXONOMY, CaseOrigin, CaseProvenance, DatasetContent, QueryCase, SourceArtifactRef
from kb2_runtime.evaluation.ingestion import MetricAggregator, MetricReport, MetricStatus, metric_report_bytes
from kb2_runtime.evaluation.retrieval import RetrievalMetricConfig, RetrievalMetricPlugin
from kb2_runtime.evidence.serializer import citation_key, evidence_id
from kb2_runtime.evidence.contracts import ContextDecision
from kb2_runtime.evidence.serializer import evidence_set_bytes
from kb2_runtime.fusion.contracts import CandidateContribution, FusionCandidateSet
from kb2_runtime.chunking.contracts import ChunkerConfig
from kb2_runtime.chunking.processor import process
from kb2_runtime.indexing.embedding import embed_chunk_set
from kb2_runtime.indexing.hybrid import build_index
from kb2_runtime.indexing.projection import project_search_documents
from kb2_runtime.indexing.serializer import search_index_result_bytes
from kb2_runtime.plugins.bootstrap import bootstrap_registry
from kb2_runtime.plugins.contracts import RunnerType
from kb2_runtime.plugins.executor import PluginExecutor
from kb2_runtime.plugins.runner import InProcessRunner
from kb2_runtime.reranking.contracts import RerankedCandidateSet
from kb2_runtime.trace.contracts import ArtifactManifest
from kb2_runtime.plugins.bootstrap import RETRIEVAL_METRIC_DESCRIPTORS


def query_case() -> QueryCase:
    source = SourceArtifactRef(id=uuid4(), content_digest="a" * 64, artifact_type="canonical.document")
    evidence = SourceArtifactRef(id=uuid4(), content_digest="b" * 64, artifact_type="evidence.set")
    return QueryCase(id="qcase_" + "1" * 16, source=source, evidence=evidence, question="Where?", answerability="answerable", relevant_evidence_ids=("evd_" + "2" * 32, "evd_" + "3" * 32), required_citation_keys=("cit_" + "4" * 32, "cit_" + "5" * 32), slices={key: values[0] for key, values in DEFAULT_TAXONOMY.dimensions.items()}, provenance=CaseProvenance(origin=CaseOrigin.MANUAL, operation="create", created_at="2026-01-01T00:00:00Z"))


def report(metric_id: str, inventory: list[tuple[str, int, tuple[str, ...], str | None]], context: bool = False) -> MetricReport:
    case = query_case()
    result = RetrievalMetricPlugin(metric_id)._report(RetrievalMetricConfig(case_id=case.id, k=2), case, DatasetContent(), uuid4(), uuid4(), uuid4(), "context" if context else "retrieval", inventory, context)
    return MetricReport.model_validate_json(result.outputs[0].content)


def test_ranked_binary_metrics_are_bounded_and_deterministic() -> None:
    inventory = [("evd_" + "9" * 32, 1, ("keyword",), None), ("evd_" + "2" * 32, 2, ("keyword",), None), ("evd_" + "3" * 32, 3, ("keyword",), None)]
    recall = report("metric.retrieval.recall.from-retrieval@1", inventory)
    assert (recall.value, recall.sample_count, recall.matched_count) == (0.5, 2, 1)
    assert report("metric.retrieval.mrr.from-retrieval@1", inventory).value == 0.5
    assert report("metric.retrieval.ndcg.from-retrieval@1", inventory).value > 0
    hit = report("metric.retrieval.hit.from-retrieval@1", inventory)
    assert hit.value == 1
    assert hit.metric_family_id == "metric.retrieval.evidence-hit-rate@1"
    assert metric_report_bytes(recall) == metric_report_bytes(MetricReport.model_validate_json(metric_report_bytes(recall)))


def test_context_empty_precision_is_not_applicable_and_recall_is_zero() -> None:
    assert report("metric.context.precision.from-evidence@1", [], True).status is MetricStatus.NOT_APPLICABLE
    recall = report("metric.context.recall.from-evidence@1", [], True)
    assert (recall.status, recall.value) == (MetricStatus.VALUE, 0.0)


def test_context_metrics_use_all_selected_items_regardless_of_k() -> None:
    inventory = [("evd_" + "2" * 32, 1, ("keyword",), "included"), ("evd_" + "9" * 32, 2, ("keyword",), "included"), ("evd_" + "3" * 32, 3, ("keyword",), "included")]
    assert report("metric.context.precision.from-evidence@1", inventory, True).value == pytest.approx(2 / 3)
    assert report("metric.context.recall.from-evidence@1", inventory, True).value == 1.0


def test_ndcg_deduplicates_repeated_reviewed_evidence() -> None:
    relevant = "evd_" + "2" * 32
    metric = report("metric.retrieval.ndcg.from-retrieval@1", [(relevant, 1, ("keyword",), None), (relevant, 2, ("vector",), None)])
    assert metric.value == pytest.approx(1 / (1 + 1 / 1.5849625007211563))
    assert metric.value < 1


def test_full_bounded_fusion_rerank_inventory_is_serializable() -> None:
    metric = report("metric.retrieval.recall.from-rerank@1", [("source-" + str(index), index + 1, ("keyword",), "included") for index in range(900)])
    assert len(metric.matches) == 900


def test_context_decision_inventory_above_rerank_bound_is_serializable() -> None:
    metric = report("metric.context.recall.from-evidence@1", [("decision:" + str(index), index + 1, (), "excluded_budget") for index in range(901)], True)
    assert len(metric.matches) == 901


def test_query_aggregate_keeps_states_samples_and_sorted_report_lineage() -> None:
    first = report("metric.retrieval.recall.from-retrieval@1", [("evd_" + "2" * 32, 1, ("keyword",), None)])
    second = first.model_copy(update={"case_id": "qcase_" + "4" * 16, "status": MetricStatus.INSUFFICIENT_LABELS, "value": None, "labelled_count": 0, "matched_count": 0, "sample_count": 0})
    high, low = uuid4(), uuid4()
    aggregate = MetricAggregator().aggregate(((high, first), (low, second)), first.metric_id, {"language": "en"})
    assert (aggregate.case_count, aggregate.sample_count, aggregate.scored_count, aggregate.insufficient_labels_count) == (2, 2, 1, 1)
    assert aggregate.report_artifact_ids == tuple(sorted((high, low), key=str))


def test_missing_labels_and_invalid_k_are_explicit_contract_states() -> None:
    case = query_case().model_copy(update={"relevant_evidence_ids": (), "required_citation_keys": ()})
    result = RetrievalMetricPlugin("metric.retrieval.recall.from-retrieval@1")._report(RetrievalMetricConfig(case_id=case.id, k=1), case, DatasetContent(), uuid4(), uuid4(), uuid4(), "retrieval", [], False)
    assert MetricReport.model_validate_json(result.outputs[0].content).status is MetricStatus.INSUFFICIENT_LABELS
    with pytest.raises(ValueError):
        RetrievalMetricConfig(case_id=case.id, k=0)


def test_excluded_rerank_decision_is_retained_without_affecting_ranked_score() -> None:
    relevant = "evd_" + "2" * 32
    metric = report("metric.retrieval.recall.from-rerank@1", [("rerank-decision:chk_" + "a" * 32, 1, (), "limit_excluded"), (relevant, 2, ("keyword",), "included")])
    assert metric.value == 0.5
    assert metric.matches[0].decision_id == "limit_excluded"


def test_registered_metric_adapters_keep_stage_ports_separate() -> None:
    assert len(RETRIEVAL_METRIC_DESCRIPTORS) == 14
    by_id = {item.plugin_id: item for item in RETRIEVAL_METRIC_DESCRIPTORS}
    assert by_id["metric.retrieval.recall.from-fusion@1"].input_schemas[-1] == ("fusion.candidate.set", "v1")
    assert by_id["metric.retrieval.recall.from-rerank@1"].input_schemas[-1] == ("rerank.candidate.set", "v1")
    assert by_id["metric.context.precision.from-evidence@1"].input_schemas[-1] == ("evidence.set", "v1")
    assert by_id["metric.context.precision.from-evidence@1"].resource_hints.max_output_bytes == 16 * 1024 * 1024


def test_fusion_uses_every_contributor_and_rerank_keeps_excluded_decisions() -> None:
    class Artifacts:
        def __init__(self) -> None:
            self.contents: dict[object, bytes] = {}
            self.manifests: dict[object, ArtifactManifest] = {}

        def add(self, artifact_type: str, content: bytes):
            identifier = uuid4()
            self.contents[identifier] = content
            self.manifests[identifier] = ArtifactManifest(
                id=identifier, artifact_type=artifact_type, schema_revision="v1",
                content_digest=hashlib.sha256(content).hexdigest(), byte_size=len(content),
                summary="fixture", storage_locator="sha256/fixture", producing_run_id=uuid4(),
                producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture.source@1",
                configuration_digest="a" * 64,
            )
            return identifier

        async def get_artifact_manifest(self, identifier): return self.manifests.get(identifier)
        async def read_content(self, identifier): return self.contents[identifier]
        async def complete_with_outputs(self, _run_id, _attempt_id, outputs, **_kwargs):
            return tuple(self.add(item.artifact_type, content) for item, content in outputs)

    class Runs:
        async def start_attempt(self, *_args): return uuid4(), 1
        async def fail_attempt(self, *_args, **_kwargs): pass

    async def build():
        source = (Path(__file__).parents[1] / "fixtures" / "ingestion" / "table-heavy-canonical.json").read_bytes()
        chunks = process(source, ChunkerConfig(strategy="table", max_tokens=64))
        index = search_index_result_bytes(await build_index(project_search_documents(chunks, embed_chunk_set(chunks))))
        artifacts = Artifacts()
        index_id, question_id = artifacts.add("search.index.result", index), artifacts.add("opaque.bytes", b"revenue metrics")
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, Runs(), artifacts)  # type: ignore[arg-type]
        keyword = (await executor.invoke(uuid4(), "keyword", "retriever.keyword@1", {"limit": 8}, (question_id, index_id)))[0]
        vector = (await executor.invoke(uuid4(), "vector", "retriever.vector@1", {"limit": 8}, (question_id, index_id)))[0]
        fused_id = (await executor.invoke(uuid4(), "fuse", "fusion.reciprocal-rank@1", {"limit": 8}, (keyword, vector)))[0]
        reranked_id = (await executor.invoke(uuid4(), "rerank", "reranker.lexical-overlap@1", {"limit": 1}, (question_id, fused_id, index_id)))[0]
        return FusionCandidateSet.model_validate_json(artifacts.contents[fused_id]), RerankedCandidateSet.model_validate_json(artifacts.contents[reranked_id])

    fused, reranked = asyncio.run(build())
    second = fused.candidates[0].contributions[1].candidate
    first = fused.candidates[0].contributions[0].candidate
    alternate_element = "elm_eeeeeeeeeeeeeeee" if first.element_ids[0] == "elm_ffffffffffffffff" else "elm_ffffffffffffffff"
    replacement = second.model_copy(update={"element_ids": (alternate_element,)})
    changed = fused.candidates[0].contributions[1].model_copy(update={"candidate": replacement})
    changed_fused = fused.model_copy(update={"candidates": (fused.candidates[0].model_copy(update={"contributions": (fused.candidates[0].contributions[0], changed)}), *fused.candidates[1:])})
    relevant = evidence_id(citation_key(replacement.document_id, replacement.chunk_id, replacement.element_ids, replacement.locators))
    case = query_case().model_copy(update={"relevant_evidence_ids": (relevant,), "required_citation_keys": (citation_key(replacement.document_id, replacement.chunk_id, replacement.element_ids, replacement.locators),)})
    plugin = RetrievalMetricPlugin("metric.retrieval.recall.from-fusion@1")
    assert relevant != evidence_id(citation_key(first.document_id, first.chunk_id, first.element_ids, first.locators))
    fusion_report = MetricReport.model_validate_json(plugin._ranked(RetrievalMetricConfig(case_id=case.id, k=1), case, DatasetContent(), uuid4(), uuid4(), uuid4(), SimpleNamespace(document_id=fused.document_id), "fusion.candidate.set", changed_fused.model_dump_json()).outputs[0].content)
    assert fusion_report.value == 1.0
    rerank_report = MetricReport.model_validate_json(plugin._ranked(RetrievalMetricConfig(case_id=case.id, k=2), case, DatasetContent(), uuid4(), uuid4(), uuid4(), SimpleNamespace(document_id=reranked.document_id), "rerank.candidate.set", reranked.model_dump_json()).outputs[0].content)
    assert any(item.source_id == "rerank-decision:" + decision.chunk_id and item.decision_id == decision.reason for item in rerank_report.matches for decision in reranked.decisions if decision.reason == "limit_excluded")


def test_metric_executor_keeps_keyword_vector_hierarchy_table_fusion_and_rerank_distinct() -> None:
    class Artifacts:
        def __init__(self) -> None: self.contents, self.manifests = {}, {}
        def add(self, artifact_type, content, parents=()):
            identifier = uuid4(); self.contents[identifier] = content
            self.manifests[identifier] = ArtifactManifest(id=identifier, artifact_type=artifact_type, schema_revision="v1", content_digest=hashlib.sha256(content).hexdigest(), byte_size=len(content), summary="fixture", storage_locator="sha256/fixture", producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture.source@1", configuration_digest="a" * 64, parent_artifact_ids=parents)
            return identifier
        async def get_artifact_manifest(self, identifier): return self.manifests.get(identifier)
        async def read_content(self, identifier): return self.contents[identifier]
        async def complete_with_outputs(self, _run_id, _attempt_id, outputs, **_kwargs): return tuple(self.add(item.artifact_type, content, item.parent_artifact_ids) for item, content in outputs)
    class Runs:
        async def start_attempt(self, *_args): return uuid4(), 1
        async def fail_attempt(self, *_args, **_kwargs): pass

    async def exercise():
        source = (Path(__file__).parents[1] / "fixtures" / "ingestion" / "table-heavy-canonical.json").read_bytes()
        chunks = process(source, ChunkerConfig(strategy="table", max_tokens=64)); index = search_index_result_bytes(await build_index(project_search_documents(chunks, embed_chunk_set(chunks))))
        artifacts = Artifacts(); canonical_id, index_id, question_id = artifacts.add("canonical.document", source), artifacts.add("search.index.result", index), artifacts.add("opaque.bytes", b"revenue metrics")
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, Runs(), artifacts)  # type: ignore[arg-type]
        stages = {name: (await executor.invoke(uuid4(), name, plugin, {"limit": 8}, (question_id, index_id)))[0] for name, plugin in (("keyword", "retriever.keyword@1"), ("vector", "retriever.vector@1"), ("hierarchy", "retriever.hierarchy@1"), ("table", "retriever.table@1"))}
        stages["fusion"] = (await executor.invoke(uuid4(), "fusion", "fusion.reciprocal-rank@1", {"limit": 8}, (stages["keyword"], stages["vector"])))[0]
        stages["rerank"] = (await executor.invoke(uuid4(), "rerank", "reranker.lexical-overlap@1", {"limit": 8}, (question_id, stages["fusion"], index_id)))[0]
        evidence_id = (await executor.invoke(uuid4(), "context", "context.from-retrieval@1", {"minimum_items": 0}, (stages["keyword"], index_id)))[0]
        evidence = __import__("kb2_runtime.evidence.contracts", fromlist=["EvidenceSet"]).EvidenceSet.model_validate_json(artifacts.contents[evidence_id]); relevant = evidence.items[0]
        case = QueryCase(id="qcase_" + "7" * 16, source=SourceArtifactRef(id=canonical_id, content_digest=artifacts.manifests[canonical_id].content_digest, artifact_type="canonical.document"), evidence=SourceArtifactRef(id=evidence_id, content_digest=artifacts.manifests[evidence_id].content_digest, artifact_type="evidence.set"), question="revenue metrics", answerability="answerable", relevant_evidence_ids=(relevant.evidence_id,), required_citation_keys=(relevant.citation_key,), slices={key: values[0] for key, values in DEFAULT_TAXONOMY.dimensions.items()}, provenance=CaseProvenance(origin=CaseOrigin.MANUAL, operation="create", created_at="2026-01-01T00:00:00Z"))
        payload = {"schema_version": "GoldenDatasetSnapshot/v1", "taxonomy": DEFAULT_TAXONOMY.model_dump(mode="json"), "annotations": [], "query_cases": [case.model_dump(mode="json")]}
        snapshot_id = artifacts.add("golden.dataset.snapshot", json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii"))
        reports, report_ids = {}, {}
        descriptors = {"keyword": "metric.retrieval.recall.from-retrieval@1", "vector": "metric.retrieval.recall.from-retrieval@1", "hierarchy": "metric.retrieval.recall.from-retrieval@1", "table": "metric.retrieval.recall.from-retrieval@1", "fusion": "metric.retrieval.recall.from-fusion@1", "rerank": "metric.retrieval.recall.from-rerank@1"}
        for name, descriptor in descriptors.items():
            report_id = (await executor.invoke(uuid4(), "metric." + name, descriptor, {"case_id": case.id, "k": 8}, (snapshot_id, evidence_id, stages[name])))[0]
            reports[name] = MetricReport.model_validate_json(artifacts.contents[report_id])
            report_ids[name] = report_id
        oversized_context = evidence.model_copy(update={"decisions": tuple(ContextDecision(chunk_id="chk_" + format(index, "032x"), source_rank=index + 1, reason="excluded_budget", safe_score=0.0) for index in range(901))})
        oversized_context_id = artifacts.add("evidence.set", evidence_set_bytes(oversized_context))
        context_report_id = (await executor.invoke(uuid4(), "metric.context.large", "metric.context.recall.from-evidence@1", {"case_id": case.id, "k": 1}, (snapshot_id, evidence_id, oversized_context_id)))[0]
        return artifacts, snapshot_id, evidence_id, stages, reports, report_ids, oversized_context_id, context_report_id
    artifacts, snapshot_id, evidence_id, stages, reports, report_ids, oversized_context_id, context_report_id = asyncio.run(exercise())
    assert {report.stage_kind for report in reports.values()} == {"retrieval", "fusion", "rerank"}
    assert len({report.measured_artifact_id for report in reports.values()}) == 6
    assert all(report.matches for report in reports.values())
    assert all(any(item.contributor_ids for item in report.matches) for report in reports.values())
    assert {reports["fusion"].metric_id, reports["rerank"].metric_id} == {"metric.retrieval.recall.from-fusion@1", "metric.retrieval.recall.from-rerank@1"}
    assert all(artifacts.manifests[report_ids[name]].parent_artifact_ids == (snapshot_id, evidence_id, stages[name]) for name in reports)
    context_report = MetricReport.model_validate_json(artifacts.contents[context_report_id])
    assert len(context_report.matches) > 900
    assert artifacts.manifests[context_report_id].parent_artifact_ids == (snapshot_id, evidence_id, oversized_context_id)
