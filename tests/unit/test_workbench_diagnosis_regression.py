from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from kb2_runtime.evaluation.runs.contracts import LayeredReport, OperationReport, canonical_bytes
from kb2_runtime.trace.contracts import EngineKind

from kb2_runtime.workbench.diagnosis import ComparisonWorkbenchService, RunHistoryWorkbenchService


def _valid_comparison() -> dict[str, object]:
    layers = {key: [] for key in ("ingestion", "retrieval", "answer", "citation", "decision", "judge", "latency", "resources")}
    case_id = "qcase_0123456789abcdef"
    slices = {"criticality": "high"}
    baseline = {"subject": "baseline", "metric_id": "answer.coverage@1", "owner": "answer", "case_id": case_id, "slices": slices,
                "status": "VALUE", "value": .2, "sample_count": 10, "labelled_count": 9, "matched_count": 2}
    candidate = baseline | {"subject": "candidate", "value": .3, "matched_count": 3}
    pair = {"metric_id": "answer.coverage@1", "owner": "answer", "case_id": case_id, "slices": slices,
            "baseline": {key: baseline[key] for key in ("subject", "status", "value", "sample_count", "labelled_count", "matched_count")},
            "candidate": {key: candidate[key] for key in ("subject", "status", "value", "sample_count", "labelled_count", "matched_count")},
            "delta": {"baseline": .2, "candidate": .3, "absolute": .09999999999999998, "relative": .4999999999999999, "relative_state": "VALUE"}}
    return {"schema_version": "EvaluationComparison/v1", "baseline_report_id": str(uuid4()), "candidate_report_id": str(uuid4()),
            "mode": "MULTI_AXIS_NON_CAUSAL", "axis": None, "changes": ["query.plugin", "ingestion.plugin"],
            "deltas": [{"baseline": 8, "candidate": 9, "absolute": 1, "relative": .125, "relative_state": "VALUE"}],
            "quality": {"baseline": [baseline], "candidate": [candidate], "pairs": [pair]},
            "confidence": {"baseline": {"state": "NOT_MEANINGFUL", "reason": "POLICY_NONE"}, "candidate": {"state": "NOT_MEANINGFUL", "reason": "UNSUPPORTED_AGGREGATE"}},
            "layers": {"baseline": layers, "candidate": layers}, "metric_report_ids": {"baseline": [], "candidate": []},
            "gates": {"baseline": [], "candidate": []}, "failed_cases": {"baseline": [], "candidate": []},
            "latency": {"baseline": 8, "candidate": 9}, "resources": {"baseline": {"availability": "AVAILABLE"}, "candidate": {"availability": "PARTIAL"}},
            "recommendation": "BASELINE_RETAINED"}


def test_comparison_projection_validates_every_independent_band() -> None:
    projected = ComparisonWorkbenchService._comparison(_valid_comparison())
    assert projected["mode"] == "MULTI_AXIS_NON_CAUSAL"
    assert projected["latency"] == {"baseline": 8, "candidate": 9}
    assert projected["resources"]["candidate"]["availability"] == "PARTIAL"
    assert projected["quality"]["pairs"][0]["baseline"]["labelled_count"] == 9
    assert projected["quality"]["pairs"][0]["candidate"]["matched_count"] == 3
    malformed = _valid_comparison() | {"confidence": {"baseline": {"state": "FORGED"}, "candidate": {"state": "FORGED"}}}
    with pytest.raises(ValueError, match="confidence"):
        ComparisonWorkbenchService._comparison(malformed)

    forged = _valid_comparison()
    forged["quality"]["pairs"][0]["candidate"]["value"] = .9
    with pytest.raises(ValueError, match="quality pairs"):
        ComparisonWorkbenchService._comparison(forged)


def test_comparison_detail_treats_bad_digest_and_incomplete_payload_as_unavailable() -> None:
    comparison_id = uuid4()

    class Artifacts:
        async def get_artifact_manifest(self, _identifier):
            return SimpleNamespace(artifact_type="evaluation.comparison", schema_revision="v1", content_digest="0" * 64)

        async def read_content(self, _identifier):
            return b'{"schema_version":"EvaluationComparison/v1"}'

    async def exercise():
        assert await ComparisonWorkbenchService(object(), Artifacts()).detail(comparison_id) == {
            "artifactId": str(comparison_id), "unavailable": {"code": "COMPARISON_ARTIFACT_UNAVAILABLE"}}

    asyncio.run(exercise())


def test_report_manifest_digest_mismatch_is_excluded_and_detail_fails_closed() -> None:
    report_id, candidate_id, manifest_id, comparison_id, run_id = (uuid4() for _ in range(5))
    layers = {key: () for key in ("ingestion", "retrieval", "answer", "citation", "decision", "judge", "latency", "resources")}
    report = LayeredReport(manifest_artifact_id=manifest_id, manifest_digest="f" * 64, report_ids=(), layers=layers,
                           gate_results=(), operation=OperationReport(elapsed_ms=1, availability="AVAILABLE"))
    report_raw, manifest_raw = canonical_bytes(report), b"{}"
    comparison = _valid_comparison() | {"baseline_report_id": str(report_id), "candidate_report_id": str(candidate_id)}
    comparison_raw = canonical_bytes(comparison)

    class Artifacts:
        async def get_artifact_manifest(self, identifier):
            values = {
                report_id: ("evaluation.report", report_raw), candidate_id: ("evaluation.report", report_raw),
                manifest_id: ("evaluation.manifest", manifest_raw), comparison_id: ("evaluation.comparison", comparison_raw),
            }
            artifact_type, raw = values[identifier]
            return SimpleNamespace(artifact_type=artifact_type, schema_revision="v1", content_digest=hashlib.sha256(raw).hexdigest(), producing_run_id=run_id)

        async def read_content(self, identifier):
            return {report_id: report_raw, candidate_id: report_raw, manifest_id: manifest_raw, comparison_id: comparison_raw}[identifier]

    class Traces:
        async def list_artifact_manifests(self, *_args):
            return (SimpleNamespace(id=report_id, producing_run_id=run_id),)

        async def get_run_trace(self, _identifier):
            return SimpleNamespace(engine_kind=EngineKind.EVALUATION, terminal_state=SimpleNamespace(value="SUCCEEDED"))

    async def exercise():
        service = ComparisonWorkbenchService(Traces(), Artifacts())
        assert await service.eligible() == []
        assert await service.detail(comparison_id) == {"artifactId": str(comparison_id), "unavailable": {"code": "COMPARISON_ARTIFACT_UNAVAILABLE"}}

    asyncio.run(exercise())


def test_run_history_filters_are_bounded_and_do_not_classify_unknown_plan_as_contract_test() -> None:
    now = datetime(2026, 9, 13, tzinfo=timezone.utc)
    identifier = uuid4()

    class Traces:
        async def list_workbench_run_history(self, limit):
            assert limit == 100
            return ({"id": identifier, "engine_kind": "evaluation", "state": "SUCCEEDED", "terminal_state": "SUCCEEDED", "created_at": now, "started_at": now, "ended_at": now, "plan_digest": "a" * 64, "plan_json": {"kind": "misleading-contract-test-label"}},)

    async def exercise():
        service = RunHistoryWorkbenchService(Traces())
        assert (await service.list())[0]["type"] == "EVALUATION"
        assert await service.list(query="x" * 65) == []
        assert await service.list(run_type="UNKNOWN") == []
        assert await service.list(state="NOT_A_STATE") == []

    asyncio.run(exercise())


def test_comparison_destination_requires_a_real_comparison_artifact() -> None:
    destinations = RunHistoryWorkbenchService._destinations({"id": str(uuid4()), "type": "COMPARISON"}, ())
    assert destinations[0]["kind"] == "trace"
    assert destinations[1] == {"kind": "unavailable", "label": "Comparison Artifact 不可用"}


def test_comparison_rejection_exposes_only_safe_engine_reason(monkeypatch) -> None:
    baseline, candidate = uuid4(), uuid4()

    class Artifacts:
        pass

    async def eligible(_self, baseline_report_id=None):
        assert baseline_report_id == baseline
        return [{"reportId": str(baseline), "compatibility": {"state": "BASELINE"}},
                {"reportId": str(candidate), "compatibility": {"state": "COMPATIBLE"}}]

    async def incompatible(*_args):
        raise ValueError("comparison inputs are not pinned-equivalent")

    monkeypatch.setattr(ComparisonWorkbenchService, "eligible", eligible)
    from kb2_runtime.evaluation.runs.service import EvaluationService
    monkeypatch.setattr(EvaluationService, "compare", incompatible)

    async def exercise():
        result = await ComparisonWorkbenchService(object(), Artifacts()).create(baseline, candidate)
        assert result == {"valid": False, "code": "COMPARISON_INCOMPATIBLE", "reason": "PINNED_INPUTS_NOT_EQUIVALENT"}

    asyncio.run(exercise())
