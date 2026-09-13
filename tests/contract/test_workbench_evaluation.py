from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from kb2_runtime.evaluation.datasets.contracts import DEFAULT_TAXONOMY
from kb2_runtime.evaluation.ingestion import MetricReport, MetricStatus, metric_report_bytes
from kb2_runtime.workbench.evaluation import EvaluationWorkbenchService


def test_metric_projection_exposes_stored_diagnostic_fields() -> None:
    identifier = uuid4()
    metric = MetricReport(
        metric_id="metric.answer.fixture@1", owner="answer", snapshot_artifact_id=uuid4(),
        taxonomy_digest="a" * 64, slices={key: values[0] for key, values in DEFAULT_TAXONOMY.dimensions.items()},
        status=MetricStatus.VALUE, value=.75, elapsed_ms=4, labelled_count=2, matched_count=1,
        sample_count=2, metric_family_id="metric.answer.fixture@1", case_id="qcase_" + "1" * 16,
        question_source_artifact_id=uuid4(), label_evidence_artifact_id=uuid4(), stage_kind="generation",
        answer_artifact_id=uuid4(), verification_artifact_id=uuid4(), final_response_artifact_id=uuid4(),
    )
    payload = metric_report_bytes(metric)

    class Artifacts:
        async def get_artifact_manifest(self, artifact_id):
            return SimpleNamespace(artifact_type="metric.report", content_digest=hashlib.sha256(payload).hexdigest())

        async def read_content(self, artifact_id):
            return payload

    row = asyncio.run(EvaluationWorkbenchService(None, None, Artifacts())._metrics([str(identifier)]))[0]
    assert row == {
        "artifactId": str(identifier), "metricId": metric.metric_id, "owner": "answer",
        "method": "deterministic", "direction": "higher_is_better", "stageKind": "generation",
        "status": MetricStatus.VALUE, "value": .75, "labelledCount": 2, "matchedCount": 1,
        "sampleCount": 2, "caseId": metric.case_id, "eligibility": None,
        "calibrationReportArtifactId": None, "measuredArtifactId": None,
        "labelEvidenceArtifactId": str(metric.label_evidence_artifact_id),
        "answerArtifactId": str(metric.answer_artifact_id),
        "verificationArtifactId": str(metric.verification_artifact_id),
        "finalResponseArtifactId": str(metric.final_response_artifact_id), "slices": metric.slices,
    }


def test_evaluation_run_rejects_digest_valid_but_wrong_typed_artifact() -> None:
    run_id, artifact_id = uuid4(), uuid4()
    payload = b'{"schema_version":"EvaluationManifest/v1"}'
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)

    class Traces:
        async def list_evaluation_workbench_runs(self):
            return [{"id": run_id, "state": "FAILED", "terminal_state": "FAILED", "created_at": now,
                     "started_at": now, "ended_at": now, "plan_digest": "f" * 64}]

        async def list_run_artifacts(self, requested):
            return [SimpleNamespace(id=artifact_id, artifact_type="evaluation.manifest", content_digest=hashlib.sha256(payload).hexdigest())]

    class Artifacts:
        async def read_content(self, requested):
            return payload

    result = asyncio.run(EvaluationWorkbenchService(None, Traces(), Artifacts()).run(run_id))
    assert result["manifest"] is None
    assert result["unavailable"] == [{"artifactId": str(artifact_id), "artifactType": "evaluation.manifest", "code": "EVALUATION_ARTIFACT_UNAVAILABLE"}]
