from __future__ import annotations

from datetime import datetime
from enum import StrEnum
import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import TraceErrorCode

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
# Plugin IDs are revisioned (for example ``transform.synthetic@1``) and are
# persisted as producer identities alongside existing metric and artifact labels.
Label = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,63}$")]
JsonPrimitive = str | int | float | bool | None

_SENSITIVE_TEXT = re.compile(
    r"(?:canary|password|passwd|secret|credential|api[-_ ]?key|authorization|bearer|"
    r"\btoken\b|deepseek|provider\s*(?:request|response|payload)|raw\s*payload|"
    r"(?:sk|pk|rk)-[A-Za-z0-9_-]{8,}|[A-Za-z0-9+/=_-]{32,})",
    re.IGNORECASE,
)
_DIGEST_FIELDS = frozenset({"implementation_digest", "configuration_digest", "content_digest", "plan_digest"})
_REGISTERED_PROVIDER_LABEL = re.compile(
    r"(?:generator\.deepseek(?:-high-precision)?@[1-9][0-9]*|deepseek-v4-(?:flash|pro))"
)


def safe_metadata_text(value: str) -> str:
    """Keep bounded diagnostics while preventing secret or provider-body propagation."""
    normalized = " ".join(value.split())
    if _SENSITIVE_TEXT.search(normalized) or normalized.startswith(("{", "[")):
        return "[redacted]"
    return normalized


def metadata_contains_sensitive_text(value: object, *, allow_registered_provider_labels: bool = False) -> bool:
    """Detect unsafe text in resolved-plan JSON, which cannot be redacted without changing its digest."""
    if isinstance(value, str):
        if allow_registered_provider_labels and _REGISTERED_PROVIDER_LABEL.fullmatch(value):
            return False
        return safe_metadata_text(value) == "[redacted]"
    if isinstance(value, dict):
        return any(
            metadata_contains_sensitive_text(key, allow_registered_provider_labels=allow_registered_provider_labels)
            or (
                key not in _DIGEST_FIELDS
                and metadata_contains_sensitive_text(item, allow_registered_provider_labels=allow_registered_provider_labels)
            )
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(
            metadata_contains_sensitive_text(item, allow_registered_provider_labels=allow_registered_provider_labels)
            for item in value
        )
    return False


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EngineKind(StrEnum):
    INGESTION = "ingestion"
    QUERY = "query"
    EVALUATION = "evaluation"


class RunState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class StageState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class StageResult(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class Metric(Contract):
    name: Label
    value: float = Field(allow_inf_nan=False)


class QualitySignal(Contract):
    name: Label
    status: Literal["PASS", "WARN", "FAIL"]
    value: JsonPrimitive = None
    summary: str = Field(default="", max_length=512)

    _safe_summary = field_validator("summary", mode="before")(safe_metadata_text)

    @field_validator("value", mode="before")
    @classmethod
    def safe_string_value(cls, value: JsonPrimitive) -> JsonPrimitive:
        return safe_metadata_text(value) if isinstance(value, str) else value


class SafeError(Contract):
    code: TraceErrorCode
    category: Literal["validation", "storage", "lifecycle", "dependency"]
    message: str = Field(min_length=1, max_length=256)
    retryable: bool = False
    details: dict[Label, JsonPrimitive] = Field(default_factory=dict, max_length=12)

    _safe_message = field_validator("message", mode="before")(safe_metadata_text)

    @field_validator("details", mode="before")
    @classmethod
    def safe_details(cls, value: dict[str, JsonPrimitive]) -> dict[str, JsonPrimitive]:
        return {key: safe_metadata_text(item) if isinstance(item, str) else item for key, item in value.items()}


class ArtifactInput(Contract):
    artifact_type: Label
    schema_revision: Label
    content_digest: Digest
    byte_size: int = Field(ge=0)
    producing_plugin_id: Label
    configuration_digest: Digest
    summary: str = Field(default="", max_length=1024)
    parent_artifact_ids: tuple[UUID, ...] = Field(default_factory=tuple, max_length=64)
    metrics: tuple[Metric, ...] = Field(default_factory=tuple, max_length=64)
    quality_signals: tuple[QualitySignal, ...] = Field(default_factory=tuple, max_length=64)

    _safe_summary = field_validator("summary", mode="before")(safe_metadata_text)

    @field_validator("parent_artifact_ids")
    @classmethod
    def parents_are_unique(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("parent artifact IDs must be unique")
        return value


class DocumentSubmissionInput(Contract):
    """Safe display metadata registered atomically with an ingestion source."""

    display_filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$")

    @field_validator("display_filename", mode="before")
    @classmethod
    def safe_leaf_filename(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("filename must be text")
        normalized = " ".join(value.split())
        if not normalized or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("filename must be a non-empty display leaf")
        if "/" in normalized or "\\" in normalized:
            raise ValueError("filename must not contain a path")
        return safe_metadata_text(normalized)

    @field_validator("media_type", mode="before")
    @classmethod
    def normalize_media_type(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("media type must be text")
        return value.strip().lower()


class DocumentSubmissionCursor(Contract):
    registered_at: datetime
    source_artifact_id: UUID


class DocumentSubmissionRecord(Contract):
    source_artifact_id: UUID
    run_id: UUID
    display_filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=128)
    registered_at: datetime
    byte_size: int = Field(ge=0)
    format: str | None = Field(default=None, max_length=32)
    document_class: str | None = Field(default=None, max_length=64)
    profile_id: str = Field(min_length=1, max_length=64)
    run_state: RunState
    output_artifact_id: UUID | None = None


class ArtifactReference(Contract):
    id: UUID
    artifact_type: str
    schema_revision: str
    content_digest: Digest
    byte_size: int
    summary: str

    _safe_summary = field_validator("summary", mode="before")(safe_metadata_text)


class ArtifactManifest(ArtifactReference):
    storage_locator: str
    producing_run_id: UUID
    producing_stage_attempt_id: UUID
    producing_plugin_id: str
    configuration_digest: Digest
    parent_artifact_ids: tuple[UUID, ...] = ()
    metrics: tuple[Metric, ...] = ()
    quality_signals: tuple[QualitySignal, ...] = ()


class StageTrace(Contract):
    id: UUID
    stage_key: str
    attempt_number: int
    state: StageState
    result: StageResult | None
    started_at: datetime | None
    ended_at: datetime | None
    summary: str
    safe_error: SafeError | None
    inputs: tuple[ArtifactReference, ...] = ()
    outputs: tuple[ArtifactReference, ...] = ()
    metrics: tuple[Metric, ...] = ()
    quality_signals: tuple[QualitySignal, ...] = ()

    _safe_summary = field_validator("summary", mode="before")(safe_metadata_text)


class RunTrace(Contract):
    id: UUID
    engine_kind: EngineKind
    plan_digest: Digest
    state: RunState
    terminal_state: RunState | None
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    stages: tuple[StageTrace, ...]
    metrics: tuple[Metric, ...] = ()
    quality_signals: tuple[QualitySignal, ...] = ()
    ingestion_evidence: "IngestionEvidence | None" = None


class IngestionEvidence(Contract):
    """Frozen, bounded resolver facts sufficient to explain Profile selection."""

    candidate_profile_ids: tuple[Label, ...] = Field(max_length=32)
    evaluated_rules: tuple[dict[Label, JsonPrimitive], ...] = Field(max_length=64)
    observables: dict[Label, JsonPrimitive] = Field(max_length=16)
    selected_profile_id: Label
    selection_tier: Label
    plan_digest: Digest
