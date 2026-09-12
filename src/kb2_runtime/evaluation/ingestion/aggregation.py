from __future__ import annotations
from uuid import UUID
from .contracts import MetricAggregate, MetricReport, MetricStatus
from .contracts import metric_aggregate_bytes
from kb2_runtime.trace.contracts import ArtifactInput
from kb2_runtime.trace.service import plan_digest

class MetricAggregator:
    def aggregate(self, reports: tuple[tuple[UUID, MetricReport], ...], metric_id: str, selector: dict[str, str]) -> MetricAggregate:
        if any(report.metric_id != metric_id for _, report in reports):
            raise ValueError("mixed metric reports")
        if len({report.taxonomy_digest for _, report in reports}) > 1:
            raise ValueError("mixed report taxonomies")
        if any(not all(report.slices.get(key) == value for key, value in selector.items()) for _, report in reports):
            raise ValueError("report does not match aggregate selector")
        selected = reports
        if len({report.document_id for _, report in selected}) != len(selected): raise ValueError("duplicate document reports")
        values = [report.value for _, report in selected if report.status is MetricStatus.VALUE]
        return MetricAggregate(metric_id=metric_id, selector=dict(sorted(selector.items())), document_count=len(selected), scored_count=len(values),
            not_applicable_count=sum(report.status is MetricStatus.NOT_APPLICABLE for _, report in selected), insufficient_labels_count=sum(report.status is MetricStatus.INSUFFICIENT_LABELS for _, report in selected),
            value=sum(values) / len(values) if values else None, report_artifact_ids=tuple(identifier for identifier, _ in sorted(selected, key=lambda item: str(item[0]))))

    async def publish(self, run_id: UUID, stage_key: str, reports: tuple[tuple[UUID, MetricReport], ...], metric_id: str, selector: dict[str, str], runs: object, artifacts: object) -> tuple[UUID, MetricAggregate]:
        """Publish a bounded aggregate with exact report Artifact lineage."""
        aggregate = self.aggregate(reports, metric_id, selector)
        parents = aggregate.report_artifact_ids
        attempt_id, _ = await runs.start_attempt(run_id, stage_key, parents)
        raw = metric_aggregate_bytes(aggregate)
        plan = {"metric_id": metric_id, "selector": aggregate.selector}
        manifest = ArtifactInput(artifact_type="metric.aggregate", schema_revision="v1", content_digest=__import__("hashlib").sha256(raw).hexdigest(), byte_size=len(raw), producing_plugin_id="evaluation.metric-aggregate@1", configuration_digest=plan_digest(plan), parent_artifact_ids=parents, summary="metric aggregate")
        artifact_id = (await artifacts.complete_with_outputs(run_id, attempt_id, ((manifest, raw),), summary="metric aggregate"))[0]
        return artifact_id, aggregate
