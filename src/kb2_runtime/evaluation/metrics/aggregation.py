from __future__ import annotations
from uuid import UUID
from .contracts import MetricAggregate, MetricReport, MetricStatus, metric_aggregate_bytes
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
        keys = {
            (report.document_id,) if report.owner == "ingestion" else (
                report.case_id, report.metric_id, report.stage_kind, report.measured_artifact_id,
                report.answer_artifact_id, report.verification_artifact_id, report.final_response_artifact_id, report.cohort_digest,
                report.judge_definition_digest, report.calibration_report_artifact_id, report.calibration_policy_digest,
            )
            for _, report in selected
        }
        if len(keys) != len(selected): raise ValueError("duplicate metric reports")
        if len({(report.owner, report.stage_kind, report.metric_family_id, report.cohort_digest, report.cohort_case_ids, report.judge_definition_digest, report.calibration_report_artifact_id, report.calibration_policy_digest) for _, report in selected}) > 1:
            raise ValueError("mixed metric identities")
        values = [report.value for _, report in selected if report.status is MetricStatus.VALUE]
        scored_count = len(values)
        first = selected[0][1] if selected else None
        if first and first.owner == "decision":
            if first.cohort_digest and {report.case_id for _, report in selected} != set(first.cohort_case_ids):
                raise ValueError("decision aggregate does not contain its configured cohort")
            outcomes = [match.decision_id for _, report in selected for match in report.matches if match.decision_id in {"TP", "FP", "FN", "TN"}]
            true_positive = outcomes.count("TP")
            false_positive = outcomes.count("FP")
            false_negative = outcomes.count("FN")
            measure = metric_id.removesuffix("@1").rsplit("-", 1)[-1]
            denominator = true_positive + (false_positive if measure == "precision" else false_negative)
            aggregate_value = true_positive / denominator if denominator else None
            sample_count = denominator
        else:
            aggregate_value = sum(values) / len(values) if values else None
            sample_count = sum(report.sample_count or 0 for _, report in selected) if first and first.owner != "ingestion" else None
        return MetricAggregate(metric_id=metric_id, selector=dict(sorted(selector.items())), document_count=len(selected), scored_count=scored_count,
            not_applicable_count=sum(report.status is MetricStatus.NOT_APPLICABLE for _, report in selected), insufficient_labels_count=sum(report.status is MetricStatus.INSUFFICIENT_LABELS for _, report in selected),
            value=aggregate_value, report_artifact_ids=tuple(identifier for identifier, _ in sorted(selected, key=lambda item: str(item[0]))),
            owner=first.owner if first else "ingestion", metric_family_id=first.metric_family_id if first else None, stage_kind=first.stage_kind if first else None,
            case_count=len({report.case_id for _, report in selected}) if first and first.owner != "ingestion" else None,
            sample_count=sample_count, cohort_digest=first.cohort_digest if first else None, cohort_case_ids=first.cohort_case_ids if first else (),
            advisory_count=sum(report.eligibility == "ADVISORY" for _, report in selected),
            ineligible_count=sum(report.eligibility == "INELIGIBLE" for _, report in selected),
            drifted_count=sum(report.eligibility == "DRIFTED" for _, report in selected))

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
