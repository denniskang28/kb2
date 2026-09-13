from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from kb2_runtime.evaluation.datasets.contracts import DatasetContent, GoldenDataset
from kb2_runtime.evaluation.datasets.service import DatasetService, DatasetValidationError
from kb2_runtime.evaluation.ingestion.contracts import MetricReport


class EvaluationWorkbenchService:
    """Safe workbench projection over the engine-owned dataset and evaluation contracts."""

    def __init__(self, datasets: Any, traces: Any, artifacts: Any) -> None:
        self._datasets, self._traces, self._artifacts = datasets, traces, artifacts
        self._dataset_service = DatasetService(artifacts)

    async def datasets(self, query: str = "") -> list[dict[str, Any]]:
        return [self._dataset_summary(item) for item in await self._datasets.list_latest(query)]

    async def dataset(self, dataset_id: UUID, revision: int | None = None) -> dict[str, Any] | None:
        try:
            if revision is None:
                items = await self._datasets.list_latest()
                item = next(x for x in items if x.id == dataset_id)
            else:
                item = await self._datasets.get(dataset_id, revision)
        except (KeyError, StopIteration):
            return None
        validation = await self._dataset_service.validate(item.content)
        return {**self._dataset_summary(item), "content": item.content.model_dump(mode="json"), "validation": validation}

    async def edit(self, dataset_id: UUID, content: dict[str, Any]) -> dict[str, Any]:
        try:
            parsed = DatasetContent.model_validate(content)
            validation = await self._dataset_service.validate(parsed)
            if any(validation.values()):
                return {"valid": False, "validation": validation}
            item = await self._datasets.edit(dataset_id, DatasetService.edit_as_draft(parsed))
        except (ValueError, DatasetValidationError):
            return {"valid": False, "validation": {"/": ["DATASET_INVALID"]}}
        return {"valid": True, "dataset": await self.dataset(item.id, item.revision)}

    async def review(self, dataset_id: UUID, revision: int, case_id: str, reviewer: str) -> dict[str, Any]:
        try:
            await self._dataset_service.mark_persisted_review(self._datasets, dataset_id, revision, case_id, reviewer)
            item = await self.dataset(dataset_id, revision)
            return {"valid": True, "dataset": item}
        except (KeyError, ValueError, DatasetValidationError):
            return {"valid": False, "code": "CASE_REVIEW_INELIGIBLE"}

    async def runs(self) -> list[dict[str, Any]]:
        return [self._run_summary(row) for row in await self._traces.list_evaluation_workbench_runs()]

    async def run(self, run_id: UUID) -> dict[str, Any] | None:
        row = next((x for x in await self._traces.list_evaluation_workbench_runs() if x["id"] == run_id), None)
        if not row:
            return None
        values: dict[str, Any] = {"manifest": None, "report": None, "navigation": None, "unavailable": []}
        for artifact in await self._traces.list_run_artifacts(run_id):
            if artifact.artifact_type not in {"evaluation.manifest", "evaluation.report", "evaluation.navigation.index", "evaluation.gate.report", "evaluation.operation.report"}:
                continue
            try:
                raw = await self._artifacts.read_content(artifact.id)
                if hashlib.sha256(raw).hexdigest() != artifact.content_digest:
                    raise ValueError
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    raise ValueError
            except Exception:
                values["unavailable"].append({"artifactId": str(artifact.id), "artifactType": artifact.artifact_type, "code": "EVALUATION_ARTIFACT_UNAVAILABLE"})
                continue
            key = {"evaluation.manifest": "manifest", "evaluation.report": "report", "evaluation.navigation.index": "navigation"}.get(artifact.artifact_type)
            if key:
                values[key] = {"artifactId": str(artifact.id), "digest": artifact.content_digest, "value": parsed}
            else:
                values.setdefault("supporting", []).append({"artifactId": str(artifact.id), "artifactType": artifact.artifact_type, "value": parsed})
        report = values.get("report", {}).get("value") if values.get("report") else None
        if isinstance(report, dict):
            values["metrics"] = await self._metrics(report.get("report_ids", ()))
        return {**self._run_summary(row), **values}

    async def _metrics(self, identifiers: object) -> list[dict[str, Any]]:
        if not isinstance(identifiers, list):
            return []
        rows: list[dict[str, Any]] = []
        for raw_id in identifiers[:200]:
            try:
                identifier = UUID(str(raw_id))
                manifest = await self._artifacts.get_artifact_manifest(identifier)
                if not manifest or manifest.artifact_type != "metric.report":
                    raise ValueError
                payload = await self._artifacts.read_content(identifier)
                if hashlib.sha256(payload).hexdigest() != manifest.content_digest:
                    raise ValueError
                metric = MetricReport.model_validate_json(payload)
                rows.append({"artifactId": str(identifier), "metricId": metric.metric_id, "owner": metric.owner,
                             "status": metric.status, "value": metric.value, "labelledCount": metric.labelled_count,
                             "matchedCount": metric.matched_count, "slices": metric.slices})
            except Exception:
                rows.append({"artifactId": str(raw_id), "status": "UNAVAILABLE", "code": "METRIC_ARTIFACT_UNAVAILABLE"})
        return rows

    @staticmethod
    def _dataset_summary(item: GoldenDataset) -> dict[str, Any]:
        cases = (*item.content.annotations, *item.content.query_cases)
        return {"id": str(item.id), "revision": item.revision, "revisionId": str(item.revision_id), "digest": item.content_digest,
                "createdAt": item.created_at.isoformat(), "annotationCount": len(item.content.annotations), "queryCaseCount": len(item.content.query_cases),
                "reviewedCount": sum(DatasetService._is_reviewed(case) for case in cases), "caseCount": len(cases)}

    @staticmethod
    def _run_summary(row: dict[str, Any]) -> dict[str, Any]:
        return {"id": str(row["id"]), "state": row["state"], "terminalState": row["terminal_state"], "createdAt": row["created_at"].isoformat(),
                "startedAt": row["started_at"].isoformat() if row["started_at"] else None, "endedAt": row["ended_at"].isoformat() if row["ended_at"] else None,
                "planDigest": row["plan_digest"]}
