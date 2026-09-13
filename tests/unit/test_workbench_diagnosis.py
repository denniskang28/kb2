import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from kb2_runtime.workbench.diagnosis import RunHistoryWorkbenchService


def test_mixed_history_uses_only_engine_and_allowlisted_plan_kind() -> None:
    now = datetime(2026, 9, 13, tzinfo=timezone.utc)
    ids = [uuid4() for _ in range(4)]

    class Traces:
        async def list_workbench_run_history(self, _limit):
            return (
                {"id": ids[0], "engine_kind": "ingestion", "state": "SUCCEEDED", "terminal_state": "SUCCEEDED", "created_at": now, "started_at": now, "ended_at": now, "plan_digest": "a" * 64, "plan_json": {"kind": "ordinary"}},
                {"id": ids[1], "engine_kind": "evaluation", "state": "SUCCEEDED", "terminal_state": "SUCCEEDED", "created_at": now, "started_at": now, "ended_at": now, "plan_digest": "b" * 64, "plan_json": {"kind": "evaluation_comparison"}},
                {"id": ids[2], "engine_kind": "evaluation", "state": "FAILED", "terminal_state": "FAILED", "created_at": now, "started_at": now, "ended_at": now, "plan_digest": "c" * 64, "plan_json": {"kind": "contract_test"}},
                {"id": ids[3], "engine_kind": "other", "state": "FAILED", "terminal_state": "FAILED", "created_at": now, "started_at": now, "ended_at": now, "plan_digest": "d" * 64, "plan_json": {"kind": "misleading_label"}},
            )

    async def exercise():
        service = RunHistoryWorkbenchService(Traces())
        assert [row["type"] for row in await service.list()] == ["INGESTION", "COMPARISON", "CONTRACT_TEST", "UNKNOWN"]
        assert [row["id"] for row in await service.list("COMPARISON")] == [str(ids[1])]
        assert await service.list("NOT_A_TYPE") == []

    asyncio.run(exercise())
