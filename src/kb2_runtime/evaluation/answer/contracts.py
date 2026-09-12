from __future__ import annotations

from typing import Annotated

from pydantic import Field

from kb2_runtime.evaluation.ingestion.contracts import IngestionMetricContract


class AnswerMetricConfig(IngestionMetricContract):
    case_id: str = Field(pattern=r"^qcase_[a-f0-9]{16,64}$")
    cohort: tuple[Annotated[str, Field(pattern=r"^qcase_[a-f0-9]{16,64}$")], ...] = Field(default_factory=tuple, max_length=1000)


FACT_METRICS = {
    "metric.answer.expected-fact-coverage@1",
    "metric.answer.forbidden-fact-violation@1",
}
CITATION_METRICS = {"metric.citation.precision@1", "metric.citation.recall@1"}
DECISION_METRICS = {
    "metric.decision.answerability-precision@1", "metric.decision.answerability-recall@1",
    "metric.decision.ambiguity-precision@1", "metric.decision.ambiguity-recall@1",
    "metric.decision.abstention-precision@1", "metric.decision.abstention-recall@1",
}
