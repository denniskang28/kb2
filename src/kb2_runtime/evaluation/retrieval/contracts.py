from __future__ import annotations

from pydantic import ConfigDict, Field

from kb2_runtime.evaluation.ingestion.contracts import IngestionMetricContract


class RetrievalMetricConfig(IngestionMetricContract):
    case_id: str = Field(pattern=r"^qcase_[a-f0-9]{16,64}$")
    k: int = Field(ge=1, le=100)
