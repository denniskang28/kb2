from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from kb2_runtime.workbench.diagnosis import ComparisonWorkbenchService, RunHistoryWorkbenchService


def test_comparison_detail_is_digest_checked_and_preserves_independent_bands() -> None:
    comparison_id = uuid4()
    payload = {
        "schema_version": "EvaluationComparison/v1",
        "baseline_report_id": str(uuid4()), "candidate_report_id": str(uuid4()),
        "mode": "MULTI_AXIS_NON_CAUSAL", "changes": ["query.plugin", "ingestion.plugin"],
        "quality": {"deltas": [{"key": ["answer", "coverage"], "delta": {"baseline": 0.0, "candidate": 0.2, "absolute": 0.2, "relative": None, "relative_state": "UNDEFINED_BASELINE_ZERO"}}]},
        "gates": {"baseline": [], "candidate": []}, "failed_cases": {"baseline": [], "candidate": []},
        "latency": {"baseline": 8, "candidate": 9}, "resources": {"baseline": {"availability": "AVAILABLE"}, "candidate": {"availability": "PARTIAL"}},
    }
    raw = json.dumps(payload, sort_keys=True).encode()

    class Artifacts:
        async def get_artifact_manifest(self, identifier):
            return SimpleNamespace(artifact_type="evaluation.comparison", schema_revision="v1", content_digest=hashlib.sha256(raw).hexdigest()) if identifier == comparison_id else None

        async def read_content(self, identifier):
            assert identifier == comparison_id
            return raw

    async def exercise():
        detail = await ComparisonWorkbenchService(object(), Artifacts()).detail(comparison_id)
        assert detail == {"artifactId": str(comparison_id), "comparison": payload}

    asyncio.run(exercise())


def test_comparison_detail_treats_bad_digest_and_incomplete_payload_as_unavailable() -> None:
    comparison_id = uuid4()

    class Artifacts:
        async def get_artifact_manifest(self, _identifier):
            return SimpleNamespace(artifact_type="evaluation.comparison", schema_revision="v1", content_digest="0" * 64)

        async def read_content(self, _identifier):
            return b'{"schema_version":"EvaluationComparison/v1"}'

    async def exercise():
        assert await ComparisonWorkbenchService(object(), Artifacts()).detail(comparison_id) is None

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


def test_comparison_rejection_exposes_only_safe_engine_reason(monkeypatch) -> None:
    baseline, candidate = uuid4(), uuid4()

    class Artifacts:
        pass

    async def eligible(_self):
        return [{"reportId": str(baseline)}, {"reportId": str(candidate)}]

    async def incompatible(*_args):
        raise ValueError("comparison inputs are not pinned-equivalent")

    monkeypatch.setattr(ComparisonWorkbenchService, "eligible", eligible)
    from kb2_runtime.evaluation.runs.service import EvaluationService
    monkeypatch.setattr(EvaluationService, "compare", incompatible)

    async def exercise():
        result = await ComparisonWorkbenchService(object(), Artifacts()).create(baseline, candidate)
        assert result == {"valid": False, "code": "COMPARISON_INCOMPATIBLE", "reason": "PINNED_INPUTS_NOT_EQUIVALENT"}

    asyncio.run(exercise())
