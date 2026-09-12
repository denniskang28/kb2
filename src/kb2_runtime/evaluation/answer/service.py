from uuid import UUID

from kb2_runtime.plugins.executor import PluginExecutor


class AnswerMetricService:
    def __init__(self, executor: PluginExecutor) -> None:
        self.executor = executor

    async def evaluate(self, run_id: UUID, stage_key: str, metric_id: str, case_id: str, snapshot_id: UUID, evidence_id: UUID, final_response_id: UUID, answer_id: UUID | None = None, verification_id: UUID | None = None) -> UUID:
        inputs = (snapshot_id, evidence_id, answer_id, verification_id, final_response_id) if answer_id and verification_id else (snapshot_id, evidence_id, final_response_id)
        return (await self.executor.invoke(run_id, stage_key, metric_id, {"case_id": case_id}, inputs))[0]
