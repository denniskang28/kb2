from __future__ import annotations

import hashlib
import json
import math

from kb2_runtime.evaluation.datasets.contracts import DatasetContent, canonical_bytes
from kb2_runtime.evaluation.ingestion.contracts import MetricMatch, MetricReport, MetricStatus, metric_report_bytes
from kb2_runtime.evidence.contracts import EvidenceSet
from kb2_runtime.evidence.serializer import citation_key, evidence_id
from kb2_runtime.fusion.contracts import FusionCandidateSet
from kb2_runtime.plugins.contracts import PluginContext, PluginInvocationResult, PluginOutput
from kb2_runtime.reranking.contracts import RerankedCandidateSet
from kb2_runtime.retrieval.contracts import RetrievalCandidateSet

from .contracts import RetrievalMetricConfig

RANKED_SCHEMAS = {"retrieval.candidate.set": ("retrieval", RetrievalCandidateSet), "fusion.candidate.set": ("fusion", FusionCandidateSet), "rerank.candidate.set": ("rerank", RerankedCandidateSet)}
FAMILIES = ("recall", "mrr", "ndcg", "evidence-hit-rate")


class RetrievalMetricPlugin:
    def __init__(self, metric_id: str) -> None:
        self.metric_id = metric_id

    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        config = RetrievalMetricConfig.model_validate(context.invocation.validated_configuration)
        snapshot_input, labels_input, measured_input = [await context.input(item.id) for item in context.invocation.inputs]
        try:
            raw = json.loads(snapshot_input.content)
            content = DatasetContent.model_validate({"taxonomy": raw["taxonomy"], "annotations": raw.get("annotations", []), "query_cases": raw.get("query_cases", [])})
            labels = EvidenceSet.model_validate_json(labels_input.content)
        except Exception as exc:
            raise ValueError("metric inputs are invalid") from exc
        case = next((item for item in content.query_cases if item.id == config.case_id), None)
        if case is None or case.evidence is None or case.evidence.id != labels_input.reference.id or case.evidence.content_digest != labels_input.reference.content_digest:
            raise ValueError("reviewed case evidence binding is invalid")
        if any(set(item.slices) != set(content.taxonomy.dimensions) or any(value not in content.taxonomy.dimensions[key] for key, value in item.slices.items()) for item in content.query_cases):
            raise ValueError("snapshot query slices are invalid")
        label_map = {item.evidence_id: item for item in labels.items}
        if any(identifier not in label_map for identifier in case.relevant_evidence_ids) or any(label_map[item].citation_key not in case.required_citation_keys for item in case.relevant_evidence_ids):
            raise ValueError("reviewed relevance labels are invalid")
        if measured_input.reference.artifact_type == "evidence.set":
            return self._context(config, case, content, snapshot_input.reference.id, labels_input.reference.id, measured_input.reference.id, labels, EvidenceSet.model_validate_json(measured_input.content))
        return self._ranked(config, case, content, snapshot_input.reference.id, labels_input.reference.id, measured_input.reference.id, labels, measured_input.reference.artifact_type, measured_input.content)

    def _ranked(self, config, case, content, snapshot_id, label_id, measured_id, labels, artifact_type, raw):
        if artifact_type not in RANKED_SCHEMAS:
            raise ValueError("ranked metric source is invalid")
        stage, model = RANKED_SCHEMAS[artifact_type]
        source = model.model_validate_json(raw)
        if source.document_id != labels.document_id:
            raise ValueError("measured source document differs")
        inventory = []
        for item in source.candidates:
            contributions = ((source.contributor_id, item),) if isinstance(source, RetrievalCandidateSet) else tuple(
                (contribution.contributor_id, contribution.candidate) for contribution in item.contributions
            )
            for contributor_id, candidate in contributions:
                matched = evidence_id(citation_key(candidate.document_id, candidate.chunk_id, candidate.element_ids, candidate.locators))
                inventory.append((matched, item.rank, (contributor_id,), "included" if isinstance(source, RerankedCandidateSet) else None))
        if isinstance(source, RerankedCandidateSet):
            # A reranker exposes only source identity for excluded inputs. Keep
            # that diagnostic decision without treating it as ranked evidence.
            inventory.extend(
                ("rerank-decision:" + decision.chunk_id, decision.input_rank, (), decision.reason)
                for decision in source.decisions if decision.reason != "included"
            )
        return self._report(config, case, content, snapshot_id, label_id, measured_id, stage, inventory, context=False)

    def _context(self, config, case, content, snapshot_id, label_id, measured_id, labels, source):
        if source.document_id != labels.document_id:
            raise ValueError("measured context document differs")
        selected = [(item.evidence_id, index + 1, tuple(score.contributor_id for score in item.contributors), "included") for index, item in enumerate(source.items)]
        decisions = [("decision:" + item.chunk_id, item.source_rank, (), item.reason) for item in source.decisions if item.reason != "included"]
        return self._report(config, case, content, snapshot_id, label_id, measured_id, "context", selected + decisions, context=True)

    def _report(self, config, case, content, snapshot_id, label_id, measured_id, stage, inventory, context):
        family = self.metric_id.split(".")[-2] if context else next(item for item in (*FAMILIES, "hit") if "." + item + "." in self.metric_id)
        if family == "hit": family = "evidence-hit-rate"
        relevant = set(case.relevant_evidence_ids)
        matches = tuple(MetricMatch(source_id=item[0], rank=item[1], relevant=item[0] in relevant, contributor_ids=item[2], decision_id=item[3]) for item in inventory)
        base = dict(metric_id=self.metric_id, metric_family_id=("metric.context." if context else "metric.retrieval.") + family + "@1", owner="context" if context else "retrieval", required_annotation_kinds=(), document_id=None, snapshot_artifact_id=snapshot_id, expected_artifact_id=None, observed_artifact_id=None, taxonomy_digest=hashlib.sha256(canonical_bytes(content.taxonomy)).hexdigest(), slices=case.slices, elapsed_ms=0, case_id=case.id, question_source_artifact_id=case.source.id, label_evidence_artifact_id=label_id, stage_kind=stage, measured_artifact_id=measured_id, k=config.k, matches=matches)
        if not relevant:
            return self._output(MetricReport(**base, status=MetricStatus.INSUFFICIENT_LABELS, value=None, labelled_count=0, matched_count=0, sample_count=0))
        selected = [item for item in matches if item.decision_id in (None, "included") and (context or (item.rank and item.rank <= config.k))]
        hit_ids = {item.source_id for item in selected if item.relevant}
        if context and family == "precision" and not selected:
            return self._output(MetricReport(**base, status=MetricStatus.NOT_APPLICABLE, value=None, labelled_count=0, matched_count=0, sample_count=0))
        if family == "recall": value = len(hit_ids) / len(relevant); sample = len(relevant)
        elif family == "precision": value = len(hit_ids) / len(selected); sample = len(selected)
        elif family == "mrr": value = next((1 / item.rank for item in selected if item.relevant), 0.0); sample = len(relevant)
        elif family == "ndcg":
            first_relevant_ranks: dict[str, int] = {}
            for item in selected:
                if item.relevant and item.source_id not in first_relevant_ranks:
                    first_relevant_ranks[item.source_id] = item.rank
            dcg = sum(1 / math.log2(rank + 1) for rank in first_relevant_ranks.values())
            ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(config.k, len(relevant)) + 1))
            value = dcg / ideal; sample = len(relevant)
        else: value = 1.0 if hit_ids else 0.0; sample = len(relevant)
        return self._output(MetricReport(**base, status=MetricStatus.VALUE, value=value, labelled_count=sample, matched_count=len(hit_ids), sample_count=sample))

    @staticmethod
    def _output(report):
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="metric.report", schema_revision="v1", content=metric_report_bytes(report), summary="retrieval metric report"),))
