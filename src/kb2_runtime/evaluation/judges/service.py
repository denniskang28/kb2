from __future__ import annotations

from uuid import UUID
import hashlib
import json

from .contracts import CalibrationLabel, CalibrationPolicy, CalibrationReport, CalibrationSnapshot, Eligibility, JudgeDefinition, JudgeResult, SlicePolicy, SliceReport, canonical_bytes, digest
from kb2_runtime.evaluation.metrics.contracts import MetricReport, MetricStatus
from kb2_runtime.trace.contracts import ArtifactInput
from kb2_runtime.trace.contracts import EngineKind
from kb2_runtime.trace.service import plan_digest
from kb2_runtime.evaluation.datasets.contracts import DatasetContent
from kb2_runtime.evaluation.datasets.service import DatasetService


def _slice(labels: tuple[CalibrationLabel, ...], results: dict[str, JudgeResult], definition, policy: SlicePolicy | None) -> SliceReport:
    selected = tuple(item for item in labels if item.definition_id == definition.definition_id and (policy is None or all(item.slices.get(k) == v for k, v in policy.selector.items())))
    predicted = [results.get(item.case_id) for item in selected]
    complete = all(predicted)
    correct = sum(result.label == item.label for item, result in zip(selected, predicted) if result)
    positives = sum(item.label == definition.positive_label for item in selected)
    negatives = len(selected) - positives
    fp = sum(result is not None and result.label == definition.positive_label and item.label != definition.positive_label for item, result in zip(selected, predicted))
    fn = sum(result is not None and result.label != definition.positive_label and item.label == definition.positive_label for item, result in zip(selected, predicted))
    agreement = correct / len(selected) if selected and complete else None
    fpr = fp / negatives if negatives else 0.0
    fnr = fn / positives if positives else 0.0
    eligible = complete and bool(selected)
    if policy:
        eligible = eligible and len(selected) >= policy.minimum_samples and agreement is not None and agreement >= policy.minimum_agreement and fpr <= policy.maximum_false_positive_rate and fnr <= policy.maximum_false_negative_rate
        selector = policy.selector
    else:
        selector = {}
    return SliceReport(selector=selector, sample_count=len(selected), agreement=agreement, false_positive_count=fp, false_negative_count=fn, false_positive_rate=fpr if selected else None, false_negative_rate=fnr if selected else None, status=Eligibility.ELIGIBLE if eligible else Eligibility.INELIGIBLE)


class JudgeCalibrationService:
    """Pure, fail-closed calibration arithmetic; invocation remains a Plugin concern."""
    def report(self, snapshot_id: UUID, snapshot: CalibrationSnapshot, definition_id: str, policy: CalibrationPolicy, results: tuple[tuple[UUID, JudgeResult], ...]) -> CalibrationReport:
        definition = next((item for item in snapshot.definitions if item.definition_id == definition_id), None)
        if definition is None:
            raise ValueError("unknown judge definition")
        actual = {result.case_id: result for _, result in results}
        labels_by_case = {item.case_id: item for item in snapshot.labels if item.definition_id == definition.definition_id}
        if (not labels_by_case
                or len(actual) != len(results)
                or any(result.case_id not in labels_by_case
                       or result.definition_id != definition.definition_id
                       or result.definition_digest != definition.definition_digest
                       or result.calibration_snapshot_digest != snapshot.snapshot_digest
                       or result.calibration_snapshot_id != snapshot_id
                       or result.provider_id != definition.provider_id
                       or result.model != definition.model
                       or result.plugin_id != definition.plugin_id
                       or result.implementation_digest != definition.implementation_digest
                       or result.prompt_digest != digest(definition.prompt_template)
                       or result.parameters_digest != digest(definition.parameters)
                       or result.label not in definition.labels
                       or result.evidence_artifact_id != labels_by_case[result.case_id].evidence_artifact_id
                       or result.evidence_digest != labels_by_case[result.case_id].evidence_digest
                       for result in actual.values())):
            raise ValueError("judge result pin is invalid")
        by_policy = tuple(_slice(snapshot.labels, actual, definition, item) for item in policy.slices)
        overall = _slice(snapshot.labels, actual, definition, None)
        eligibility = Eligibility.ELIGIBLE if overall.status is Eligibility.ELIGIBLE and all(item.status is Eligibility.ELIGIBLE for item in by_policy) else Eligibility.INELIGIBLE
        return CalibrationReport(calibration_snapshot_id=snapshot_id, calibration_snapshot_digest=snapshot.snapshot_digest, definition_id=definition.definition_id, definition_digest=definition.definition_digest, policy_digest=policy.policy_digest, result_artifact_ids=tuple(identifier for identifier, _ in sorted(results, key=lambda item: str(item[0]))), overall=overall, slices=by_policy, eligibility=eligibility)

    async def publish(self, run_id: UUID, stage_key: str, snapshot_id: UUID, snapshot: CalibrationSnapshot, definition_id: str, policy: CalibrationPolicy, results: tuple[tuple[UUID, JudgeResult], ...], runs: object, artifacts: object) -> tuple[UUID, CalibrationReport]:
        """Publish the immutable report with snapshot and Judge-result lineage."""
        report = self.report(snapshot_id, snapshot, definition_id, policy, results)
        ordered_results = tuple(identifier for identifier, result in sorted(results, key=lambda item: item[1].case_id))
        report = report.model_copy(update={"result_artifact_ids": ordered_results})
        parents = tuple(dict.fromkeys((snapshot_id, *ordered_results)))
        attempt_id, _ = await runs.start_attempt(run_id, stage_key, parents)
        raw = canonical_bytes(report)
        manifest = ArtifactInput(artifact_type="judge.calibration.report", schema_revision="v1", content_digest=hashlib.sha256(raw).hexdigest(), byte_size=len(raw), producing_plugin_id="evaluation.judge-calibration@1", configuration_digest=plan_digest({"definition_id": definition_id, "policy_digest": policy.policy_digest}), parent_artifact_ids=parents, summary="judge calibration report")
        artifact_id = (await artifacts.complete_with_outputs(run_id, attempt_id, ((manifest, raw),), summary="judge calibration report"))[0]
        return artifact_id, report

    async def compile_snapshot(self, run_id: UUID, stage_key: str, dataset_snapshot_id: UUID, definitions: tuple[JudgeDefinition, ...], labels: tuple[CalibrationLabel, ...], runs: object, artifacts: object) -> tuple[UUID, CalibrationSnapshot]:
        """Compile reviewed labels from one immutable Golden Dataset snapshot Artifact."""
        manifest = await artifacts.get_artifact_manifest(dataset_snapshot_id)
        if manifest is None or (manifest.artifact_type, manifest.schema_revision) != ("golden.dataset.snapshot", "v1"):
            raise ValueError("golden dataset snapshot artifact is invalid")
        try:
            raw_bytes = await artifacts.read_content(dataset_snapshot_id)
            if hashlib.sha256(raw_bytes).hexdigest() != manifest.content_digest:
                raise ValueError("golden dataset snapshot digest is invalid")
            raw = json.loads(raw_bytes)
            content = DatasetContent.model_validate({"taxonomy": raw["taxonomy"], "annotations": raw.get("annotations", []), "query_cases": raw.get("query_cases", [])})
        except Exception as exc:
            raise ValueError("golden dataset snapshot content is invalid") from exc
        cases = {item.id: item for item in content.query_cases}
        definition_map = {item.definition_id: item for item in definitions}
        if not labels or len({(item.case_id, item.definition_id) for item in labels}) != len(labels):
            raise ValueError("calibration labels are invalid")
        for label in labels:
            case, definition = cases.get(label.case_id), definition_map.get(label.definition_id)
            provenance = {"case_id": label.case_id, "definition_id": label.definition_id, "rubric_id": label.rubric_id, "label": label.label, "source_artifact_id": str(label.source_artifact_id), "source_digest": label.source_digest, "evidence_artifact_id": str(label.evidence_artifact_id), "evidence_digest": label.evidence_digest, "slices": label.slices, "reviewer": label.reviewer, "reviewed_at": label.reviewed_at.isoformat(), "review_record_id": label.review_record_id, "review_operation": label.review_operation}
            if (case is None or definition is None or label.rubric_id != definition.rubric_id or label.label not in definition.labels
                    or not DatasetService._is_reviewed(case) or case.evidence is None
                    or case.source.id != label.source_artifact_id or case.source.content_digest != label.source_digest
                    or case.evidence.id != label.evidence_artifact_id or case.evidence.content_digest != label.evidence_digest
                    or case.slices != label.slices or label.reviewed_label_digest != digest(provenance)):
                raise ValueError("calibration label is not reviewed dataset provenance")
        snapshot = CalibrationSnapshot(dataset_snapshot_id=dataset_snapshot_id, dataset_snapshot_digest=manifest.content_digest, definitions=definitions, labels=labels)
        parents = (dataset_snapshot_id, *tuple(sorted({item.evidence_artifact_id for item in labels}, key=str)))
        attempt_id, _ = await runs.start_attempt(run_id, stage_key, parents)
        content_bytes = canonical_bytes(snapshot)
        output = ArtifactInput(artifact_type="judge.calibration.snapshot", schema_revision="v1", content_digest=hashlib.sha256(content_bytes).hexdigest(), byte_size=len(content_bytes), producing_plugin_id="evaluation.judge-calibration@1", configuration_digest=plan_digest({"dataset_snapshot_id": str(dataset_snapshot_id), "definitions": [item.definition_digest for item in definitions]}), parent_artifact_ids=parents, summary="reviewed judge calibration snapshot")
        snapshot_id = (await artifacts.complete_with_outputs(run_id, attempt_id, ((output, content_bytes),), summary="reviewed judge calibration snapshot"))[0]
        return snapshot_id, snapshot

    async def execute(self, snapshot_id: UUID, snapshot: CalibrationSnapshot, definition_id: str, policy: CalibrationPolicy, case_inputs: dict[str, tuple[UUID, UUID]], executor: object, runs: object, artifacts: object) -> tuple[UUID, UUID, CalibrationReport]:
        """Run the pinned Judge once per sorted calibration case, then publish its report."""
        lookup = getattr(artifacts, "get_artifact_manifest", None)
        if lookup is None:
            raise ValueError("calibration snapshot trust lookup is unavailable")
        manifest = await lookup(snapshot_id)
        if (manifest is None or (manifest.artifact_type, manifest.schema_revision) != ("judge.calibration.snapshot", "v1")
                or manifest.content_digest != hashlib.sha256(canonical_bytes(snapshot)).hexdigest()):
            raise ValueError("calibration snapshot is not a trusted published artifact")
        definition = next((item for item in snapshot.definitions if item.definition_id == definition_id), None)
        labels = tuple(sorted((item for item in snapshot.labels if item.definition_id == definition_id), key=lambda item: item.case_id))
        if definition is None or not labels or set(item.case_id for item in labels) != set(case_inputs):
            raise ValueError("calibration execution cases are invalid")
        run_id = await runs.create_run(EngineKind.EVALUATION, {"kind": "judge_calibration", "snapshot_id": str(snapshot_id), "snapshot_digest": snapshot.snapshot_digest, "definition_id": definition_id, "policy_digest": policy.policy_digest, "case_ids": [item.case_id for item in labels]})
        try:
            outputs: list[tuple[UUID, JudgeResult]] = []
            for label in labels:
                evidence_id, final_id = case_inputs[label.case_id]
                output_id = (await executor.invoke(run_id, "judge." + label.case_id[-16:], definition.plugin_id, {"definition_id": definition_id, "case_id": label.case_id}, (snapshot_id, evidence_id, final_id)))[0]
                outputs.append((output_id, JudgeResult.model_validate_json(await artifacts.read_content(output_id))))
            report_id, report = await self.publish(run_id, "judge.calibration", snapshot_id, snapshot, definition_id, policy, tuple(outputs), runs, artifacts)
            await runs.finish_run(run_id, True)
            return run_id, report_id, report
        except Exception:
            await runs.finish_run(run_id, False)
            raise

    def semantic_metric(self, *, metric_id: str, snapshot_id: UUID, label: CalibrationLabel, result_id: UUID, result: JudgeResult, calibration_report_id: UUID | None, calibration_report: CalibrationReport | None, definition: JudgeDefinition, expected_definition_digest: str, policy: CalibrationPolicy) -> MetricReport:
        """Create a pinned advisory result; only matching eligible calibration is gate-eligible."""
        eligibility = Eligibility.ADVISORY
        if (snapshot_id != result.calibration_snapshot_id
                or label.case_id != result.case_id
                or label.evidence_artifact_id != result.evidence_artifact_id
                or label.evidence_digest != result.evidence_digest
                or label.definition_id != definition.definition_id or label.rubric_id != definition.rubric_id
                or result.definition_id != definition.definition_id or result.definition_digest != expected_definition_digest):
            eligibility = Eligibility.DRIFTED
        elif calibration_report is not None and calibration_report_id is not None:
            eligibility = calibration_report.eligibility
            if (calibration_report.calibration_snapshot_id != result.calibration_snapshot_id
                    or calibration_report.calibration_snapshot_digest != result.calibration_snapshot_digest
                    or result_id not in calibration_report.result_artifact_ids
                    or calibration_report.definition_id != result.definition_id
                    or calibration_report.definition_digest != result.definition_digest
                    or calibration_report.policy_digest != policy.policy_digest):
                eligibility = Eligibility.DRIFTED
        return MetricReport(metric_id=metric_id, owner="judge", method="llm_judge", direction="higher_is_better", required_annotation_kinds=(), document_id=None,
            snapshot_artifact_id=snapshot_id, expected_artifact_id=None, observed_artifact_id=None, taxonomy_digest="0" * 64, slices=label.slices,
            status=MetricStatus.VALUE, value=1.0 if result.label == definition.positive_label else 0.0, elapsed_ms=result.elapsed_ms, labelled_count=1, matched_count=int(result.label == definition.positive_label), metric_family_id=metric_id,
            case_id=label.case_id, question_source_artifact_id=label.source_artifact_id, label_evidence_artifact_id=label.evidence_artifact_id, stage_kind="final_state", measured_artifact_id=None, k=None,
            answer_artifact_id=None, verification_artifact_id=None, final_response_artifact_id=result.final_response_artifact_id, judge_result_artifact_id=result_id,
            calibration_report_artifact_id=calibration_report_id, judge_definition_digest=result.definition_digest, calibration_policy_digest=policy.policy_digest, eligibility=eligibility.value)
