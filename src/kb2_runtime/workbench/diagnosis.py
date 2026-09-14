from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any
from uuid import UUID

from kb2_runtime.evaluation.metrics.contracts import MetricStatus
from kb2_runtime.evaluation.runs.contracts import ComparisonMode, Delta, EvaluationManifest, FailedCaseLink, GateResult, LayeredReport, OperationReport
from kb2_runtime.evaluation.runs.service import EvaluationService
from kb2_runtime.trace.contracts import EngineKind
from kb2_runtime.trace.service import RunService

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,63}$")
_SAFE_AXIS = re.compile(r"^(?:ingestion|query)\.[a-z][a-z0-9_.-]{0,63}$")
_QUALITY_OWNERS = frozenset({"ingestion", "retrieval", "context", "answer", "citation", "decision", "judge"})
_LAYERS = frozenset({"ingestion", "retrieval", "answer", "citation", "decision", "judge", "latency", "resources"})


class ComparisonWorkbenchService:
    """Digest-verified, typed read facade over immutable S-021 comparisons."""

    def __init__(self, traces: Any, artifacts: Any) -> None:
        self._traces, self._artifacts = traces, artifacts
        self._runs = RunService(traces)

    async def eligible(self, baseline_report_id: UUID | None = None) -> list[dict[str, Any]]:
        catalog: list[tuple[dict[str, Any], EvaluationManifest]] = []
        for artifact in await self._traces.list_artifact_manifests("evaluation.report", "v1", 64):
            try:
                summary, manifest = await self._report_summary(artifact.id)
                trace = await self._traces.get_run_trace(artifact.producing_run_id)
                if not trace or trace.engine_kind is not EngineKind.EVALUATION or not trace.terminal_state or trace.terminal_state.value != "SUCCEEDED":
                    continue
                summary["state"] = trace.terminal_state.value
                catalog.append((summary, manifest))
            except Exception:
                continue
        baseline = next((manifest for summary, manifest in catalog if summary["reportId"] == str(baseline_report_id)), None)
        rows: list[dict[str, Any]] = []
        for summary, manifest in catalog:
            if baseline_report_id is not None:
                if baseline is None:
                    state, reason = "INCOMPATIBLE", "BASELINE_UNAVAILABLE"
                elif summary["reportId"] == str(baseline_report_id):
                    state, reason = "BASELINE", None
                elif EvaluationService.fixed_inputs_equivalent(baseline, manifest):
                    state, reason = "COMPATIBLE", None
                else:
                    state, reason = "INCOMPATIBLE", "PINNED_INPUTS_NOT_EQUIVALENT"
                summary["compatibility"] = {"state": state, "reason": reason}
            rows.append(summary)
        return rows

    async def create(self, baseline_report_id: UUID, candidate_report_id: UUID) -> dict[str, Any]:
        if baseline_report_id == candidate_report_id:
            return {"valid": False, "code": "COMPARISON_INCOMPATIBLE", "reason": "SAME_REPORT"}
        catalog = {item["reportId"]: item for item in await self.eligible(baseline_report_id)}
        candidate = catalog.get(str(candidate_report_id))
        if str(baseline_report_id) not in catalog or not candidate:
            return {"valid": False, "code": "COMPARISON_INCOMPATIBLE", "reason": "REPORT_UNAVAILABLE"}
        if candidate.get("compatibility", {}).get("state") != "COMPATIBLE":
            return {"valid": False, "code": "COMPARISON_INCOMPATIBLE", "reason": candidate.get("compatibility", {}).get("reason") or "PINNED_INPUTS_NOT_EQUIVALENT"}
        try:
            run_id, artifact_id, _ = await EvaluationService().compare(baseline_report_id, candidate_report_id, self._runs, self._artifacts)
        except (ValueError, KeyError) as exc:
            reason = "PINNED_INPUTS_NOT_EQUIVALENT" if str(exc) == "comparison inputs are not pinned-equivalent" else "COMPARISON_REJECTED"
            return {"valid": False, "code": "COMPARISON_INCOMPATIBLE", "reason": reason}
        return {"valid": True, "runId": str(run_id), "artifactId": str(artifact_id), "comparison": await self.detail(artifact_id)}

    async def detail(self, artifact_id: UUID) -> dict[str, Any]:
        try:
            value = self._comparison(await self._read(artifact_id, "evaluation.comparison"))
            baseline, _ = await self._report_summary(UUID(value["baseline_report_id"]))
            candidate, _ = await self._report_summary(UUID(value["candidate_report_id"]))
            return {"artifactId": str(artifact_id), "comparison": value, "reports": {"baseline": baseline, "candidate": candidate}}
        except Exception:
            return {"artifactId": str(artifact_id), "unavailable": {"code": "COMPARISON_ARTIFACT_UNAVAILABLE"}}

    async def _report_summary(self, report_id: UUID) -> tuple[dict[str, Any], EvaluationManifest]:
        report = LayeredReport.model_validate(await self._read(report_id, "evaluation.report"))
        manifest = EvaluationManifest.model_validate(await self._read(report.manifest_artifact_id, "evaluation.manifest", report.manifest_digest))
        report_ref = await self._artifacts.get_artifact_manifest(report_id)
        return ({"reportId": str(report_id), "runId": str(report_ref.producing_run_id),
                 "manifest": {"artifactId": str(report.manifest_artifact_id), "digest": report.manifest_digest,
                              "datasetSnapshotId": str(manifest.dataset_snapshot_id), "datasetDigest": manifest.dataset_snapshot_digest,
                              "taxonomyDigest": manifest.taxonomy_digest, "inputCatalogDigest": manifest.input_catalog_digest,
                              "caseCount": len(manifest.case_ids), "metricCount": len(manifest.metric_ids)}}, manifest)

    @classmethod
    def _comparison(cls, value: dict[str, Any]) -> dict[str, Any]:
        if value.get("schema_version") != "EvaluationComparison/v1": raise ValueError("comparison schema")
        baseline, candidate = str(UUID(str(value["baseline_report_id"]))), str(UUID(str(value["candidate_report_id"])))
        mode, changes, axis = ComparisonMode(value["mode"]), tuple(value.get("changes") or ()), value.get("axis")
        if not 1 <= len(changes) <= 64 or any(not isinstance(item, str) or not _SAFE_AXIS.fullmatch(item) for item in changes): raise ValueError("comparison changes")
        if (mode is ComparisonMode.SINGLE_AXIS and (axis not in changes or len(changes) != 1)) or (mode is ComparisonMode.MULTI_AXIS_NON_CAUSAL and axis is not None): raise ValueError("comparison axis")
        quality = value.get("quality")
        if not isinstance(quality, dict): raise ValueError("comparison quality")
        projected_quality = {side: [cls._quality_row(item, side) for item in quality.get(side, [])] for side in ("baseline", "candidate")}
        by_side = {side: {cls._quality_key(item): item for item in projected_quality[side]} for side in ("baseline", "candidate")}
        pairs = []
        for key in sorted(set(by_side["baseline"]) | set(by_side["candidate"]), key=str):
            baseline_row, candidate_row = by_side["baseline"].get(key), by_side["candidate"].get(key)
            pairs.append({"metric_id": key[0], "owner": key[1], "case_id": key[2], "slices": dict(key[3]),
                          "baseline": cls._quality_fact(baseline_row), "candidate": cls._quality_fact(candidate_row),
                          "delta": EvaluationService.delta(
                              baseline_row.get("value") if baseline_row else None,
                              candidate_row.get("value") if candidate_row else None,
                          ).model_dump(mode="json")})
        if quality.get("pairs") != pairs: raise ValueError("comparison quality pairs")
        projected_quality["pairs"] = pairs
        gates = {side: [GateResult.model_validate(item).model_dump(mode="json") for item in value.get("gates", {}).get(side, [])] for side in ("baseline", "candidate")}
        failed = {side: [FailedCaseLink.model_validate(item).model_dump(mode="json", exclude_none=True) for item in value.get("failed_cases", {}).get(side, [])] for side in ("baseline", "candidate")}
        latency = value.get("latency")
        if not isinstance(latency, dict) or any(not isinstance(latency.get(side), int) or latency[side] < 0 for side in ("baseline", "candidate")): raise ValueError("comparison latency")
        resources = {side: OperationReport.model_validate({"elapsed_ms": latency[side], **value.get("resources", {}).get(side, {})}).model_dump(mode="json", exclude={"elapsed_ms"}) for side in ("baseline", "candidate")}
        confidence = {side: cls._confidence(value.get("confidence", {}).get(side)) for side in ("baseline", "candidate")}
        layers, projected_layers = value.get("layers"), {}
        if not isinstance(layers, dict): raise ValueError("comparison layers")
        for side in ("baseline", "candidate"):
            if not isinstance(layers.get(side), dict) or set(layers[side]) != _LAYERS: raise ValueError("comparison layers")
            projected_layers[side] = {key: [str(UUID(str(item))) for item in items] for key, items in layers[side].items()}
        metric_ids = {side: [str(UUID(str(item))) for item in value.get("metric_report_ids", {}).get(side, [])] for side in ("baseline", "candidate")}
        recommendation = value.get("recommendation")
        if recommendation not in {"BASELINE_RETAINED", "CANDIDATE_ELIGIBLE"}: raise ValueError("comparison recommendation")
        return {"schema_version": "EvaluationComparison/v1", "baseline_report_id": baseline, "candidate_report_id": candidate,
                "mode": mode.value, "axis": axis, "changes": list(changes),
                "deltas": [Delta.model_validate(item).model_dump(mode="json") for item in value.get("deltas", [])],
                "quality": projected_quality, "confidence": confidence, "layers": projected_layers, "metric_report_ids": metric_ids,
                "gates": gates, "failed_cases": failed, "latency": {side: latency[side] for side in ("baseline", "candidate")},
                "resources": resources, "recommendation": recommendation}

    @staticmethod
    def _quality_row(item: Any, expected_subject: str) -> dict[str, Any]:
        if not isinstance(item, dict) or item.get("subject") != expected_subject or item.get("owner") not in _QUALITY_OWNERS: raise ValueError("quality row")
        metric_id = item.get("metric_id")
        if not isinstance(metric_id, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*", metric_id): raise ValueError("quality metric")
        status, metric_value = MetricStatus(item.get("status")), item.get("value")
        if (status is MetricStatus.VALUE) != isinstance(metric_value, (int, float)): raise ValueError("quality value")
        counts = {}
        for key in ("sample_count", "labelled_count", "matched_count"):
            count = item.get(key)
            if count is not None and (not isinstance(count, int) or count < 0 or count > 1000): raise ValueError("quality count")
            counts[key] = count
        slices = item.get("slices")
        if not isinstance(slices, dict) or not 1 <= len(slices) <= 8 or any(not isinstance(k, str) or not isinstance(v, str) for k, v in slices.items()): raise ValueError("quality slices")
        return {"subject": item.get("subject"), "metric_id": metric_id, "owner": item["owner"], "case_id": item.get("case_id"), "slices": slices, "status": status.value, "value": metric_value, **counts}

    @staticmethod
    def _quality_key(item: dict[str, Any]) -> tuple[Any, ...]:
        return item["metric_id"], item["owner"], item["case_id"], tuple(sorted(item["slices"].items()))

    @staticmethod
    def _quality_fact(item: dict[str, Any] | None) -> dict[str, Any] | None:
        return ({key: item.get(key) for key in ("subject", "status", "value", "sample_count", "labelled_count", "matched_count")}
                if item is not None else None)

    @staticmethod
    def _confidence(item: Any) -> dict[str, Any]:
        if not isinstance(item, dict) or item.get("state") not in {"VALUE", "NOT_MEANINGFUL"}: raise ValueError("confidence")
        if item["state"] == "NOT_MEANINGFUL":
            if item.get("reason") not in {"POLICY_NONE", "UNSUPPORTED_AGGREGATE"}: raise ValueError("confidence reason")
            return {"state": item["state"], "reason": item["reason"]}
        required = ("level", "numerator", "denominator", "lower", "upper")
        if item.get("method") != "wilson" or any(not isinstance(item.get(key), (int, float)) for key in required): raise ValueError("confidence value")
        return {key: item[key] for key in ("state", "method", *required)}

    async def _read(self, artifact_id: UUID, artifact_type: str, expected_digest: str | None = None) -> dict[str, Any]:
        manifest = await self._artifacts.get_artifact_manifest(artifact_id)
        if not manifest or manifest.artifact_type != artifact_type or manifest.schema_revision != "v1": raise ValueError("artifact identity")
        raw = await self._artifacts.read_content(artifact_id)
        if hashlib.sha256(raw).hexdigest() != manifest.content_digest or (expected_digest and manifest.content_digest != expected_digest): raise ValueError("artifact digest")
        value = json.loads(raw)
        if not isinstance(value, dict): raise ValueError("artifact payload")
        return value


class RunHistoryWorkbenchService:
    """Server-owned typed projection of bounded mixed Run history."""
    _types = frozenset({"INGESTION", "QUERY", "EVALUATION", "COMPARISON", "CONTRACT_TEST", "UNKNOWN"})
    _states = frozenset({"PENDING", "RUNNING", "SUCCEEDED", "FAILED"})

    def __init__(self, traces: Any) -> None: self._traces = traces

    async def list(self, run_type: str = "", state: str = "", query: str = "") -> list[dict[str, Any]]:
        kind, desired_state = run_type.upper(), state.upper()
        if (kind and kind not in self._types) or (desired_state and desired_state not in self._states) or len(query) > 64: return []
        needle = query.strip().lower()
        rows = [self._summary(item) for item in await self._traces.list_workbench_run_history(100)]
        return [item for item in rows if (not kind or item["type"] == kind) and (not desired_state or item["state"] == desired_state)
                and (not needle or any(needle in str(item.get(key) or "").lower() for key in ("id", "planDigest", "profileId", "pluginIds")))]

    async def detail(self, run_id: UUID) -> dict[str, Any] | None:
        trace = await self._traces.get_run_trace(run_id)
        if not trace: return None
        plan = await self._traces.get_run_plan(run_id) or {}
        row = self._summary({"id": trace.id, "engine_kind": trace.engine_kind.value, "state": trace.state.value,
                             "terminal_state": trace.terminal_state.value if trace.terminal_state else None,
                             "created_at": trace.created_at, "started_at": trace.started_at, "ended_at": trace.ended_at,
                             "plan_digest": trace.plan_digest, "plan_json": plan})
        row["stages"] = [self._stage(item, plan) for item in trace.stages]
        row["destinations"] = self._destinations(row, trace.stages)
        row["actions"] = {}
        return row

    @classmethod
    def _summary(cls, row: dict[str, Any]) -> dict[str, Any]:
        plan = row.get("plan_json") if isinstance(row.get("plan_json"), dict) else {}
        kind = cls._kind(row.get("engine_kind"), plan.get("kind"))
        profile = plan.get("profile_id") if isinstance(plan.get("profile_id"), str) and _SAFE_ID.fullmatch(plan["profile_id"]) else None
        started, ended = row.get("started_at"), row.get("ended_at")
        return {"id": str(UUID(str(row["id"]))), "type": kind, "state": row["state"], "terminalState": row.get("terminal_state"),
                "createdAt": row["created_at"].isoformat(), "startedAt": started.isoformat() if started else None,
                "endedAt": ended.isoformat() if ended else None, "durationMs": cls._duration(started, ended), "planDigest": row["plan_digest"],
                "profileId": profile, "pluginIds": cls._plugins(plan, kind), "input": cls._input(plan, kind)}

    @staticmethod
    def _kind(engine: Any, stored_kind: Any) -> str:
        if stored_kind == "evaluation_comparison": return "COMPARISON"
        if stored_kind == "contract_test": return "CONTRACT_TEST"
        if engine == "ingestion": return "INGESTION"
        if engine == "query": return "QUERY"
        if engine == "evaluation": return "EVALUATION"
        return "UNKNOWN"

    @staticmethod
    def _duration(started: datetime | None, ended: datetime | None) -> int | None:
        return max(0, int((ended - started).total_seconds() * 1000)) if started and ended else None

    @staticmethod
    def _plugins(plan: dict[str, Any], kind: str) -> list[str]:
        values: list[Any] = []
        if kind == "QUERY": values = [item.get("plugin_id") for item in plan.get("stages", []) if isinstance(item, dict)]
        elif kind == "INGESTION":
            for axis in plan.get("stages", []):
                for sub in axis.get("sub_stages", []) if isinstance(axis, dict) else []:
                    values.extend(item.get("plugin_id") for item in sub.get("candidates", []) if isinstance(item, dict))
        elif kind == "CONTRACT_TEST": values = [plan.get("plugin_id")]
        return list(dict.fromkeys(item for item in values if isinstance(item, str) and _SAFE_ID.fullmatch(item)))[:64]

    @staticmethod
    def _input(plan: dict[str, Any], kind: str) -> dict[str, str]:
        if kind == "QUERY" and isinstance(plan.get("search_artifact"), dict):
            try: return {"kind": "artifact", "summary": str(UUID(str(plan["search_artifact"].get("artifact_id"))))}
            except (ValueError, TypeError): pass
        if kind == "EVALUATION":
            try: return {"kind": "dataset", "summary": str(UUID(str(plan.get("manifest_id") or plan.get("dataset"))))}
            except (ValueError, TypeError): pass
        if kind == "COMPARISON":
            try: return {"kind": "reports", "summary": f"{UUID(str(plan['baseline']))} / {UUID(str(plan['candidate']))}"}
            except (KeyError, ValueError, TypeError): pass
        if kind == "CONTRACT_TEST" and isinstance(plan.get("contract_id"), str) and _SAFE_ID.fullmatch(plan["contract_id"]): return {"kind": "contract", "summary": plan["contract_id"]}
        return {"kind": "unavailable", "summary": "不可用"}

    @classmethod
    def _stage(cls, item: Any, plan: dict[str, Any]) -> dict[str, Any]:
        return {"stageKey": item.stage_key, "attempt": item.attempt_number, "state": item.state.value,
                "result": item.result.value if item.result else None, "pluginId": cls._stage_plugin(plan, item.stage_key),
                "startedAt": item.started_at.isoformat() if item.started_at else None, "endedAt": item.ended_at.isoformat() if item.ended_at else None,
                "durationMs": cls._duration(item.started_at, item.ended_at),
                "inputs": [{"id": str(x.id), "artifactType": x.artifact_type, "summary": x.summary} for x in item.inputs],
                "artifacts": [{"id": str(x.id), "artifactType": x.artifact_type, "summary": x.summary} for x in item.outputs],
                "failure": {"code": item.safe_error.code.value} if item.safe_error else None}

    @staticmethod
    def _stage_plugin(plan: dict[str, Any], stage_key: str) -> str | None:
        for item in plan.get("stages", []):
            if not isinstance(item, dict): continue
            if item.get("stage_id") == stage_key or stage_key.startswith(str(item.get("stage_id", "")) + "."):
                value = item.get("plugin_id"); return value if isinstance(value, str) and _SAFE_ID.fullmatch(value) else None
            for sub in item.get("sub_stages", []):
                if isinstance(sub, dict) and f"{item.get('axis')}.{sub.get('stage_id')}" in stage_key:
                    match, candidates = re.search(r"candidate-(\d+)", stage_key), sub.get("candidates", [])
                    index = int(match.group(1)) - 1 if match else 0
                    if 0 <= index < len(candidates) and isinstance(candidates[index], dict):
                        value = candidates[index].get("plugin_id"); return value if isinstance(value, str) and _SAFE_ID.fullmatch(value) else None
        return None

    @staticmethod
    def _destinations(row: dict[str, Any], stages: Any) -> list[dict[str, Any]]:
        result = [{"kind": "trace", "label": "Trace", "runId": row["id"]}]
        for output in [output for stage in stages for output in stage.outputs][:32]: result.append({"kind": "artifact", "label": output.artifact_type, "artifactId": str(output.id)})
        route = {"INGESTION": ("Documents", "documents"), "QUERY": ("Query / Evidence", "query"), "EVALUATION": ("Evaluation", "evaluation-run")}.get(row["type"])
        if route: result.append({"kind": "route", "label": route[0], "route": route[1], "runId": row["id"]})
        if row["type"] == "COMPARISON":
            artifact = next((output for stage in stages for output in stage.outputs if output.artifact_type == "evaluation.comparison"), None)
            result.append({"kind": "route", "label": "Comparison", "route": "compare", "runId": row["id"], "comparisonArtifactId": str(artifact.id)} if artifact else
                          {"kind": "unavailable", "label": "Comparison Artifact 不可用"})
        return result
