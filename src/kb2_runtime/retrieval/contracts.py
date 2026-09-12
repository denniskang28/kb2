from __future__ import annotations

import asyncio
import math
from datetime import datetime
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from kb2_runtime.canonical.contracts import Locator, StableId
from kb2_runtime.chunking.contracts import ChunkCitation
from kb2_runtime.indexing.contracts import MAX_QUERY_CHARS, SearchIndexResult


class RetrievalContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IndexArtifactBinding(RetrievalContract):
    id: UUID
    artifact_type: Literal["search.index.result"] = "search.index.result"
    schema_revision: Literal["v1"] = "v1"
    content_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class RetrievalFilters(RetrievalContract):
    language: str | None = Field(default=None, max_length=64)
    document_class: str | None = Field(default=None, max_length=128)
    metadata: dict[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")], str | int | float | bool | None] = Field(default_factory=dict, max_length=16)
    enrichments: dict[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")], str | int | float | bool | None] = Field(default_factory=dict, max_length=16)

    @field_validator("metadata", "enrichments")
    @classmethod
    def bounded_values(cls, value: dict[str, object]) -> dict[str, object]:
        if any(isinstance(item, str) and len(item) > 256 for item in value.values()):
            raise ValueError("filter value is unbounded")
        return value


class RetrieverConfig(RetrievalContract):
    limit: int = Field(default=10, ge=1, le=100)
    language: str | None = Field(default=None, max_length=64)
    document_class: str | None = Field(default=None, max_length=128)
    metadata: dict[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")], str | int | float | bool | None] = Field(default_factory=dict, max_length=16)
    enrichments: dict[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")], str | int | float | bool | None] = Field(default_factory=dict, max_length=16)

    @property
    def filters(self) -> RetrievalFilters:
        return RetrievalFilters(language=self.language, document_class=self.document_class, metadata=self.metadata, enrichments=self.enrichments)

    @classmethod
    def model_json_schema(cls, *args, **kwargs) -> dict[str, object]:
        return {
            "type": "object", "additionalProperties": False,
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
                "language": {"type": ["string", "null"], "maxLength": 64},
                "document_class": {"type": ["string", "null"], "maxLength": 128},
                "metadata": {"type": "object", "additionalProperties": {"type": ["string", "integer", "number", "boolean", "null"]}, "maxProperties": 16},
                "enrichments": {"type": "object", "additionalProperties": {"type": ["string", "integer", "number", "boolean", "null"]}, "maxProperties": 16},
            },
        }


class HierarchyRetrieverConfig(RetrieverConfig):
    relation_mode: Literal["self", "parent", "children"] = "self"

    @classmethod
    def model_json_schema(cls, *args, **kwargs) -> dict[str, object]:
        schema = super().model_json_schema(*args, **kwargs)
        schema["properties"]["relation_mode"] = {"type": "string", "enum": ["self", "parent", "children"], "default": "self"}  # type: ignore[index]
        return schema


class StructuralProjection(RetrievalContract):
    """Closed structural context; retrieval never preserves provider payloads."""

    hierarchy_path: tuple[Annotated[str, Field(min_length=1, max_length=256)], ...] = Field(default_factory=tuple, max_length=16)
    relation: Literal["parent", "children"] | None = None
    table_element_ids: tuple[StableId, ...] = Field(default_factory=tuple, max_length=128)
    matched_filter_keys: tuple[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")], ...] = Field(default_factory=tuple, max_length=32)

    @model_validator(mode="after")
    def fields_are_coherent(self) -> "StructuralProjection":
        if len(set(self.table_element_ids)) != len(self.table_element_ids) or len(set(self.matched_filter_keys)) != len(self.matched_filter_keys):
            raise ValueError("structural projection fields must be unique")
        return self


class RetrievalCandidate(RetrievalContract):
    candidate_id: Annotated[str, Field(pattern=r"^rcd_[a-f0-9]{32}$")]
    document_id: StableId
    chunk_id: Annotated[str, Field(pattern=r"^chk_[a-f0-9]{32}$")]
    element_ids: tuple[StableId, ...] = Field(min_length=1, max_length=128)
    locators: tuple[Locator, ...] = Field(min_length=1, max_length=128)
    rank: int = Field(ge=1, le=100)
    safe_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    score_kind: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")]
    structural_projection: StructuralProjection = Field(default_factory=StructuralProjection)

    @model_validator(mode="after")
    def evidence_is_aligned(self) -> "RetrievalCandidate":
        if len(self.element_ids) != len(self.locators) or len(set(self.element_ids)) != len(self.element_ids):
            raise ValueError("candidate citations must be unique and aligned")
        return self


class RetrievalCandidateSet(RetrievalContract):
    schema_version: Literal["RetrievalCandidateSet/v1"] = "RetrievalCandidateSet/v1"
    candidate_set_id: Annotated[str, Field(pattern=r"^rcs_[a-f0-9]{32}$")]
    index: IndexArtifactBinding
    index_id: Annotated[str, Field(pattern=r"^idx_[a-f0-9]{32}$")]
    document_id: StableId
    retriever_plugin_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
    implementation_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    contributor_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.@-]{0,47}$")]
    configuration_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    filtered_count: int = Field(default=0, ge=0, le=4096)
    candidates: tuple[RetrievalCandidate, ...] = Field(default_factory=tuple, max_length=100)

    @model_validator(mode="after")
    def ranked_consistent_candidates(self) -> "RetrievalCandidateSet":
        identifiers = [item.candidate_id for item in self.candidates]
        ranks = [item.rank for item in self.candidates]
        if len(identifiers) != len(set(identifiers)) or ranks != list(range(1, len(ranks) + 1)) or any(item.document_id != self.document_id for item in self.candidates):
            raise ValueError("candidate set ranks or lineage are invalid")
        return self


class RetrieverRequest(RetrievalContract):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    query: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)
    index: SearchIndexResult
    index_binding: IndexArtifactBinding
    contributor_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.@-]{0,47}$")]
    configuration: RetrieverConfig
    configuration_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    plugin_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
    implementation_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    cancellation: asyncio.Event | None = Field(default=None, exclude=True)
    deadline_at: datetime | None = Field(default=None, exclude=True)

    @field_validator("query")
    @classmethod
    def query_is_utf8_safe(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_QUERY_CHARS * 4:
            raise ValueError("query is unbounded")
        return value


class RetrieverPort(Protocol):
    def retrieve(self, request: RetrieverRequest) -> RetrievalCandidateSet: ...
