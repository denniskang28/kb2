from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from kb2_runtime.ingestion_profiles.contracts import ResolutionRequest, SchemaRef


class IngestionContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceSubmission(IngestionContract):
    """Opaque content plus the declared schema; no paths or inferred MIME state."""

    content: bytes = Field(min_length=1, max_length=16 * 1024 * 1024)
    source_schema: SchemaRef


class IngestionReceipt(IngestionContract):
    run_id: UUID
    profile_id: str
    plan_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    outputs: dict[str, UUID] = Field(max_length=128)


class IngestionRequest(IngestionContract):
    source: SourceSubmission
    resolution: ResolutionRequest
