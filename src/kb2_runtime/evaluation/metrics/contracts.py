from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kb2_runtime.evaluation.datasets.contracts import DEFAULT_TAXONOMY


class IngestionMetricContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MetricStatus(StrEnum):
    VALUE = "VALUE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INSUFFICIENT_LABELS = "INSUFFICIENT_LABELS"


class MetricMatch(IngestionMetricContract):
    """Bounded, source-only evidence used to explain a query metric."""
    source_id: str = Field(min_length=1, max_length=128)
    rank: int | None = Field(default=None, ge=1, le=4096)
    relevant: bool
    contributor_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=16)
    decision_id: str | None = Field(default=None, max_length=128)
    span_start: int | None = Field(default=None, ge=0, le=4096)
    span_end: int | None = Field(default=None, ge=0, le=4096)
    citation_key: Annotated[str, Field(pattern=r"^cit_[a-f0-9]{32}$")] | None = None
    evidence_id: Annotated[str, Field(pattern=r"^evd_[a-f0-9]{32}$")] | None = None
    locator_fingerprint: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")] | None = None

    @model_validator(mode="after")
    def diagnostic_shape(self) -> "MetricMatch":
        if (self.span_start is None) != (self.span_end is None):
            raise ValueError("metric match span is incomplete")
        if self.span_start is not None and self.span_end is not None and self.span_end <= self.span_start:
            raise ValueError("metric match span is invalid")
        return self


class MetricReport(IngestionMetricContract):
    schema_version: str = "MetricReport/v1"
    metric_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
    owner: Literal["ingestion", "retrieval", "context", "answer", "citation", "decision"] = "ingestion"
    method: str = "deterministic"
    direction: Literal["higher_is_better", "lower_is_better"] = "higher_is_better"
    required_annotation_kinds: tuple[str, ...] = Field(default_factory=tuple, max_length=8)
    document_id: Annotated[str, Field(pattern=r"^[a-z]+_[a-f0-9]{16,64}$")] | None = None
    snapshot_artifact_id: UUID
    expected_artifact_id: UUID | None = None
    observed_artifact_id: UUID | None = None
    taxonomy_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    slices: dict[str, str] = Field(min_length=8, max_length=8)
    status: MetricStatus
    value: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    elapsed_ms: int = Field(ge=0, le=300_000)
    labelled_count: int = Field(ge=0, le=1000)
    matched_count: int = Field(ge=0, le=1000)
    metric_family_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")] | None = None
    case_id: Annotated[str, Field(pattern=r"^qcase_[a-f0-9]{16,64}$")] | None = None
    question_source_artifact_id: UUID | None = None
    label_evidence_artifact_id: UUID | None = None
    stage_kind: Literal["retrieval", "fusion", "rerank", "context", "generation", "verification", "final_state"] | None = None
    measured_artifact_id: UUID | None = None
    k: int | None = Field(default=None, ge=1, le=100)
    # Context permits 100 selected Evidence items and 4096 decisions; retain
    # that complete bounded diagnostic inventory without truncation.
    matches: tuple[MetricMatch, ...] = Field(default_factory=tuple, max_length=4196)
    sample_count: int | None = Field(default=None, ge=0, le=1000)
    answer_artifact_id: UUID | None = None
    verification_artifact_id: UUID | None = None
    final_response_artifact_id: UUID | None = None
    cohort_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")] | None = None
    cohort_case_ids: tuple[Annotated[str, Field(pattern=r"^qcase_[a-f0-9]{16,64}$")], ...] = Field(default_factory=tuple, max_length=1000)

    @model_validator(mode="after")
    def result_shape(self) -> "MetricReport":
        if self.schema_version != "MetricReport/v1":
            raise ValueError("metric report schema is invalid")
        if self.method != "deterministic" or (self.direction == "lower_is_better" and self.owner != "answer"):
            raise ValueError("metric definition is invalid")
        if (self.status is MetricStatus.VALUE) != (self.value is not None):
            raise ValueError("metric value and status disagree")
        if self.matched_count > self.labelled_count:
            raise ValueError("matched count exceeds labels")
        if set(self.slices) != set(DEFAULT_TAXONOMY.dimensions):
            raise ValueError("metric slices are outside the closed taxonomy")
        if self.owner == "ingestion":
            if not (self.required_annotation_kinds and self.document_id and self.expected_artifact_id and self.observed_artifact_id):
                raise ValueError("ingestion metric binding is invalid")
            if any(value is not None for value in (self.case_id, self.question_source_artifact_id, self.label_evidence_artifact_id, self.stage_kind, self.measured_artifact_id, self.k, self.answer_artifact_id, self.verification_artifact_id, self.final_response_artifact_id, self.cohort_digest)):
                raise ValueError("ingestion metric has query fields")
        else:
            if self.required_annotation_kinds or self.document_id or self.expected_artifact_id or self.observed_artifact_id:
                raise ValueError("query metric has ingestion fields")
            if self.owner in {"retrieval", "context"} and not all((self.case_id, self.question_source_artifact_id, self.label_evidence_artifact_id, self.stage_kind, self.measured_artifact_id, self.k, self.metric_family_id)):
                raise ValueError("query metric binding is invalid")
            if self.owner in {"answer", "citation"} and not all((self.case_id, self.question_source_artifact_id, self.label_evidence_artifact_id, self.metric_family_id, self.answer_artifact_id, self.verification_artifact_id, self.final_response_artifact_id)):
                raise ValueError("answer metric binding is invalid")
            if self.owner == "decision" and not all((self.case_id, self.label_evidence_artifact_id, self.metric_family_id, self.final_response_artifact_id)):
                raise ValueError("decision metric binding is invalid")
            if self.owner != "decision" and self.cohort_digest is not None:
                raise ValueError("non-decision metric has cohort identity")
            if self.owner != "decision" and self.cohort_case_ids:
                raise ValueError("non-decision metric has cohort membership")
            if self.cohort_digest is not None and (not self.cohort_case_ids or self.case_id not in self.cohort_case_ids):
                raise ValueError("decision cohort membership is invalid")
            if self.owner in {"answer", "citation", "decision"} and self.stage_kind not in {"generation", "verification", "final_state"}:
                raise ValueError("answer metric stage is invalid")
            if (self.owner == "context") != (self.stage_kind == "context"):
                raise ValueError("query metric owner and stage disagree")
            if self.owner == "retrieval" and self.stage_kind == "context":
                raise ValueError("retrieval metric stage is invalid")
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
    owner: Literal["ingestion", "retrieval", "context", "answer", "citation", "decision"] = "ingestion"
    metric_family_id: str | None = None
    stage_kind: Literal["retrieval", "fusion", "rerank", "context", "generation", "verification", "final_state"] | None = None
    case_count: int | None = Field(default=None, ge=0)
    sample_count: int | None = Field(default=None, ge=0)
    cohort_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")] | None = None
    cohort_case_ids: tuple[Annotated[str, Field(pattern=r"^qcase_[a-f0-9]{16,64}$")], ...] = Field(default_factory=tuple, max_length=1000)

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
    payload = value.model_dump(mode="json", exclude_none=True)
    # Existing ingestion report bytes are part of persisted Artifact identity.
    if value.owner == "ingestion":
        for key in ("metric_family_id", "case_id", "question_source_artifact_id", "label_evidence_artifact_id", "stage_kind", "measured_artifact_id", "k", "matches", "sample_count", "answer_artifact_id", "verification_artifact_id", "final_response_artifact_id", "cohort_digest", "cohort_case_ids"):
            payload.pop(key, None)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def metric_aggregate_bytes(value: MetricAggregate) -> bytes:
    payload = value.model_dump(mode="json", exclude_none=True)
    if value.owner == "ingestion":
        for key in ("owner", "metric_family_id", "stage_kind", "case_count", "sample_count", "cohort_digest", "cohort_case_ids"):
            payload.pop(key, None)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
