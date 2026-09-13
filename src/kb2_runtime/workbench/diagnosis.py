from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from kb2_runtime.evaluation.runs.contracts import EvaluationManifest, LayeredReport
from kb2_runtime.evaluation.runs.service import EvaluationService
from kb2_runtime.trace.contracts import EngineKind
from kb2_runtime.trace.service import RunService


class ComparisonWorkbenchService:
    """Digest-verified read facade over immutable evaluation comparisons."""

    def __init__(self, traces: Any, artifacts: Any) -> None:
        self._traces, self._artifacts = traces, artifacts
        self._runs = RunService(traces)

    async def eligible(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for artifact in await self._traces.list_artifact_manifests("evaluation.report", "v1", 64):
            trace = await self._traces.get_run_trace(artifact.producing_run_id)
            if not trace or trace.engine_kind is not EngineKind.EVALUATION or trace.terminal_state is None or trace.terminal_state.value != "SUCCEEDED":
                continue
            try:
                report = await self._read(artifact.id, "evaluation.report")
                parsed = LayeredReport.model_validate(report)
                manifest = EvaluationManifest.model_validate(await self._read(parsed.manifest_artifact_id, "evaluation.manifest"))
            except Exception:
                continue
            rows.append({"reportId": str(artifact.id), "runId": str(artifact.producing_run_id),
                         "manifestId": str(parsed.manifest_artifact_id), "datasetDigest": manifest.dataset_snapshot_digest,
                         "inputCatalogDigest": manifest.input_catalog_digest, "state": trace.terminal_state.value})
        return rows

    async def create(self, baseline_report_id: UUID, candidate_report_id: UUID) -> dict[str, Any]:
        eligible = {item["reportId"] for item in await self.eligible()}
        if str(baseline_report_id) not in eligible or str(candidate_report_id) not in eligible:
            return {"valid": False, "code": "COMPARISON_INCOMPATIBLE"}
        try:
            run_id, artifact_id, _ = await EvaluationService().compare(baseline_report_id, candidate_report_id, self._runs, self._artifacts)
        except (ValueError, KeyError) as exc:
            reason = "PINNED_INPUTS_NOT_EQUIVALENT" if str(exc) == "comparison inputs are not pinned-equivalent" else "COMPARISON_REJECTED"
            return {"valid": False, "code": "COMPARISON_INCOMPATIBLE", "reason": reason}
        return {"valid": True, "runId": str(run_id), "artifactId": str(artifact_id), "comparison": await self.detail(artifact_id)}

    async def detail(self, artifact_id: UUID) -> dict[str, Any] | None:
        try:
            value = await self._read(artifact_id, "evaluation.comparison")
        except Exception:
            return None
        required = {"baseline_report_id", "candidate_report_id", "mode", "changes", "quality", "gates", "failed_cases", "latency", "resources"}
        if not required <= set(value) or value.get("schema_version") != "EvaluationComparison/v1":
            return {"artifactId": str(artifact_id), "unavailable": {"code": "COMPARISON_ARTIFACT_UNAVAILABLE"}}
        # This is a direct read-only representation of the persisted policy result.
        return {"artifactId": str(artifact_id), "comparison": value}

    async def _read(self, artifact_id: UUID, artifact_type: str) -> dict[str, Any]:
        manifest = await self._artifacts.get_artifact_manifest(artifact_id)
        if not manifest or manifest.artifact_type != artifact_type or manifest.schema_revision != "v1":
            raise ValueError("artifact identity")
        raw = await self._artifacts.read_content(artifact_id)
        if hashlib.sha256(raw).hexdigest() != manifest.content_digest:
            raise ValueError("artifact digest")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("artifact payload")
        return value


class RunHistoryWorkbenchService:
    """Server-owned type classification and bounded mixed Run history."""

    _types = frozenset({"INGESTION", "QUERY", "EVALUATION", "COMPARISON", "CONTRACT_TEST", "UNKNOWN"})
    _states = frozenset({"PENDING", "RUNNING", "SUCCEEDED", "FAILED"})

    def __init__(self, traces: Any) -> None:
        self._traces = traces

    async def list(self, run_type: str = "", state: str = "", query: str = "") -> list[dict[str, Any]]:
        kind = run_type.upper()
        desired_state = state.upper()
        if kind and kind not in self._types or desired_state and desired_state not in self._states:
            return []
        needle = query.strip()[:64].lower()
        rows = [self._summary(item) for item in await self._traces.list_workbench_run_history(100)]
        return [item for item in rows if (not kind or item["type"] == kind) and (not desired_state or item["state"] == desired_state)
                and (not needle or needle in item["id"].lower() or needle in item["planDigest"])]

    async def detail(self, run_id: UUID) -> dict[str, Any] | None:
        trace = await self._traces.get_run_trace(run_id)
        if not trace:
            return None
        plan = await self._traces.get_run_plan(run_id)
        row = self._summary({"id": trace.id, "engine_kind": trace.engine_kind.value, "state": trace.state.value,
                             "terminal_state": trace.terminal_state.value if trace.terminal_state else None,
                             "created_at": trace.created_at, "started_at": trace.started_at, "ended_at": trace.ended_at,
                             "plan_digest": trace.plan_digest, "plan_json": plan or {}})
        row["stages"] = [{"stageKey": item.stage_key, "attempt": item.attempt_number, "state": item.state.value,
                          "result": item.result.value if item.result else None, "artifacts": [{"id": str(x.id), "artifactType": x.artifact_type} for x in item.outputs],
                          "failure": item.safe_error.code if item.safe_error else None} for item in trace.stages]
        # API composition replaces this with the owning workflow's live action
        # contract. It is never inferred from trace state.
        row["actions"] = {}
        return row

    @classmethod
    def _summary(cls, row: dict[str, Any]) -> dict[str, Any]:
        plan = row.get("plan_json") if isinstance(row.get("plan_json"), dict) else {}
        stored_kind = plan.get("kind")
        engine = row.get("engine_kind")
        if stored_kind == "evaluation_comparison": kind = "COMPARISON"
        elif stored_kind == "contract_test": kind = "CONTRACT_TEST"
        elif engine == "ingestion": kind = "INGESTION"
        elif engine == "query": kind = "QUERY"
        elif engine == "evaluation": kind = "EVALUATION"
        else: kind = "UNKNOWN"
        return {"id": str(row["id"]), "type": kind, "state": row["state"], "terminalState": row.get("terminal_state"),
                "createdAt": row["created_at"].isoformat(), "startedAt": row["started_at"].isoformat() if row.get("started_at") else None,
                "endedAt": row["ended_at"].isoformat() if row.get("ended_at") else None, "planDigest": row["plan_digest"]}
