from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kb2_runtime.evaluation.datasets.contracts import DEFAULT_TAXONOMY


class IngestionMetricContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MetricStatus(StrEnum):
    VALUE = "VALUE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INSUFFICIENT_LABELS = "INSUFFICIENT_LABELS"


class MetricReport(IngestionMetricContract):
    schema_version: str = "MetricReport/v1"
    metric_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
    owner: str = "ingestion"
    method: str = "deterministic"
    direction: str = "higher_is_better"
    required_annotation_kinds: tuple[str, ...] = Field(min_length=1, max_length=8)
    document_id: Annotated[str, Field(pattern=r"^[a-z]+_[a-f0-9]{16,64}$")]
    snapshot_artifact_id: UUID
    expected_artifact_id: UUID
    observed_artifact_id: UUID
    taxonomy_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    slices: dict[str, str] = Field(min_length=8, max_length=8)
    status: MetricStatus
    value: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    elapsed_ms: int = Field(ge=0, le=300_000)
    labelled_count: int = Field(ge=0, le=1000)
    matched_count: int = Field(ge=0, le=1000)

    @model_validator(mode="after")
    def result_shape(self) -> "MetricReport":
        if self.schema_version != "MetricReport/v1":
            raise ValueError("metric report schema is invalid")
        if self.owner != "ingestion" or self.method != "deterministic" or self.direction != "higher_is_better":
            raise ValueError("metric definition is invalid")
        if (self.status is MetricStatus.VALUE) != (self.value is not None):
            raise ValueError("metric value and status disagree")
        if self.matched_count > self.labelled_count:
            raise ValueError("matched count exceeds labels")
        if set(self.slices) != set(DEFAULT_TAXONOMY.dimensions):
            raise ValueError("metric slices are outside the closed taxonomy")
        return self


class MetricAggregate(IngestionMetricContract):
    schema_version: str = "MetricAggregate/v1"
    metric_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
    selector: dict[str, str] = Field(min_length=1, max_length=8)
    document_count: int = Field(ge=0)
    scored_count: int = Field(ge=0)
    not_applicable_count: int = Field(ge=0)
    insufficient_labels_count: int = Field(ge=0)
    value: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    report_artifact_ids: tuple[UUID, ...] = Field(max_length=1000)

    @model_validator(mode="after")
    def counts_shape(self) -> "MetricAggregate":
        if self.schema_version != "MetricAggregate/v1":
            raise ValueError("metric aggregate schema is invalid")
        if self.document_count != self.scored_count + self.not_applicable_count + self.insufficient_labels_count:
            raise ValueError("aggregate counts disagree")
        if (self.scored_count > 0) != (self.value is not None):
            raise ValueError("aggregate value and scores disagree")
        if any(key not in DEFAULT_TAXONOMY.dimensions for key in self.selector):
            raise ValueError("aggregate selector is outside the closed taxonomy")
        return self


def metric_report_bytes(value: MetricReport) -> bytes:
    return json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def metric_aggregate_bytes(value: MetricAggregate) -> bytes:
    return json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
