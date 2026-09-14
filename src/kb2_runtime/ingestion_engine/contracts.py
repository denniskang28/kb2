from __future__ import annotations

import re
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from kb2_runtime.ingestion_profiles.contracts import ResolutionRequest, SchemaRef


class IngestionContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceSubmission(IngestionContract):
    """Opaque content plus the declared schema; no paths or inferred MIME state."""

    content: bytes = Field(min_length=1, max_length=16 * 1024 * 1024)
    source_schema: SchemaRef
    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=128)

    @field_validator("filename")
    @classmethod
    def filename_is_leaf(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized or "/" in normalized or "\\" in normalized:
            raise ValueError("filename must be a display leaf")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("filename contains control characters")
        return normalized

    @field_validator("media_type")
    @classmethod
    def media_type_is_bounded_mime(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", normalized):
            raise ValueError("media type must be MIME syntax")
        return normalized


class IngestionReceipt(IngestionContract):
    run_id: UUID
    profile_id: str
    plan_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    outputs: dict[str, UUID] = Field(max_length=128)


class IngestionRequest(IngestionContract):
    source: SourceSubmission
    resolution: ResolutionRequest
