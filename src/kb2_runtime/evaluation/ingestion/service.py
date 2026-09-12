from __future__ import annotations

from uuid import UUID

from kb2_runtime.plugins.executor import PluginExecutor


class IngestionMetricService:
    """Generic registered-metric dispatch; metric semantics stay in Plugins."""
    def __init__(self, executor: PluginExecutor) -> None:
        self.executor = executor

    async def evaluate(self, run_id: UUID, stage_key: str, metric_id: str, snapshot_id: UUID, expected_id: UUID, observed_id: UUID) -> UUID:
        return (await self.executor.invoke(run_id, stage_key, metric_id, {}, (snapshot_id, expected_id, observed_id)))[0]
