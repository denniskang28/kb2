from uuid import UUID
from kb2_runtime.plugins.executor import PluginExecutor

class RetrievalMetricService:
    def __init__(self, executor: PluginExecutor) -> None: self.executor = executor
    async def evaluate(self, run_id: UUID, stage_key: str, metric_id: str, case_id: str, k: int, snapshot_id: UUID, label_evidence_id: UUID, measured_id: UUID) -> UUID:
        return (await self.executor.invoke(run_id, stage_key, metric_id, {"case_id": case_id, "k": k}, (snapshot_id, label_evidence_id, measured_id)))[0]
