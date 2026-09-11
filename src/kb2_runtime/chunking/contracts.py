from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from kb2_runtime.canonical.contracts import DocumentMetadata, Locator, StableId


MAX_CHUNK_CONTENT = 16_384
MAX_CITATIONS = 128
MAX_CHILDREN = 64
MAX_ENRICHMENTS = 32


class ChunkingContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ChunkStrategy(StrEnum):
    FIXED_WINDOW = "fixed_window"
    PARENT_CHILD = "parent_child"
    HIERARCHY = "hierarchy"
    TABLE = "table"


class ChunkerConfig(ChunkingContract):
    strategy: Literal["fixed_window", "parent_child", "hierarchy", "table"]
    max_tokens: int = Field(default=256, ge=64, le=512)
    overlap_tokens: int = Field(default=0, ge=0, le=64)
    max_children: int = Field(default=32, ge=1, le=64)

    @model_validator(mode="after")
    def overlap_is_bounded(self) -> "ChunkerConfig":
        if self.overlap_tokens >= self.max_tokens:
            raise ValueError("overlap_tokens must be less than max_tokens")
        return self


JsonValue = str | int | float | bool | None
EnrichmentValue = JsonValue | tuple[JsonValue, ...]


class EnricherConfig(ChunkingContract):
    fields: dict[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")], EnrichmentValue] = Field(min_length=1, max_length=MAX_ENRICHMENTS)

    @field_validator("fields")
    @classmethod
    def values_are_bounded(cls, value: dict[str, EnrichmentValue]) -> dict[str, EnrichmentValue]:
        def valid(item: JsonValue) -> bool:
            return (not isinstance(item, str) or len(item) <= 256) and (
                not isinstance(item, float) or math.isfinite(item)
            )
        if any((isinstance(item, tuple) and (len(item) > 16 or not all(valid(part) for part in item))) or
               (not isinstance(item, tuple) and not valid(item)) for item in value.values()):
            raise ValueError("enrichment values must be bounded primitives")
        return value


class ChunkCitation(ChunkingContract):
    element_id: StableId
    locator: Locator


class EnrichmentProvenance(ChunkingContract):
    producer_plugin_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
    configuration_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    source_chunk_id: Annotated[str, Field(pattern=r"^chk_[a-f0-9]{32}$")]


class EnrichmentField(ChunkingContract):
    value: EnrichmentValue
    provenance: EnrichmentProvenance


class Chunk(ChunkingContract):
    chunk_id: Annotated[str, Field(pattern=r"^chk_[a-f0-9]{32}$")]
    content: str = Field(min_length=1, max_length=MAX_CHUNK_CONTENT)
    token_count: int = Field(ge=1, le=512)
    source_element_ids: tuple[StableId, ...] = Field(min_length=1, max_length=MAX_CITATIONS)
    citations: tuple[ChunkCitation, ...] = Field(min_length=1, max_length=MAX_CITATIONS)
    parent_chunk_id: Annotated[str, Field(pattern=r"^chk_[a-f0-9]{32}$")] | None = None
    child_chunk_ids: tuple[Annotated[str, Field(pattern=r"^chk_[a-f0-9]{32}$")], ...] = Field(default_factory=tuple, max_length=MAX_CHILDREN)
    hierarchy_context: tuple[str, ...] = Field(default_factory=tuple, max_length=16)
    language: str | None = Field(default=None, max_length=64)
    enrichments: dict[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")], EnrichmentField] = Field(default_factory=dict, max_length=MAX_ENRICHMENTS)

    @model_validator(mode="after")
    def relation_and_citation_shape(self) -> "Chunk":
        if self.token_count != len(self.content.split()):
            raise ValueError("token count must match rendered content")
        if len(set(self.source_element_ids)) != len(self.source_element_ids):
            raise ValueError("source element IDs must be unique")
        if len({item.element_id for item in self.citations}) != len(self.citations):
            raise ValueError("citation element IDs must be unique")
        if set(self.source_element_ids) != {item.element_id for item in self.citations}:
            raise ValueError("citations must match source element IDs")
        if self.chunk_id in self.child_chunk_ids or self.parent_chunk_id == self.chunk_id or len(set(self.child_chunk_ids)) != len(self.child_chunk_ids):
            raise ValueError("chunk relations must not self-reference or duplicate")
        return self


class ChunkSet(ChunkingContract):
    schema_version: Literal["ChunkSet/v1"] = "ChunkSet/v1"
    document_id: StableId
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    language: str | None = Field(default=None, max_length=64)
    chunker_configuration: ChunkerConfig
    chunks: tuple[Chunk, ...] = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def relations_are_complete_and_acyclic(self) -> "ChunkSet":
        by_id = {chunk.chunk_id: chunk for chunk in self.chunks}
        if len(by_id) != len(self.chunks):
            raise ValueError("chunk IDs must be unique")
        for chunk in self.chunks:
            if any(field.provenance.source_chunk_id != chunk.chunk_id for field in chunk.enrichments.values()):
                raise ValueError("enrichment provenance must reference its containing chunk")
            if chunk.parent_chunk_id and chunk.parent_chunk_id not in by_id:
                raise ValueError("parent chunk must be in the ChunkSet")
            if any(child not in by_id for child in chunk.child_chunk_ids):
                raise ValueError("child chunk must be in the ChunkSet")
            if chunk.parent_chunk_id and chunk.chunk_id not in by_id[chunk.parent_chunk_id].child_chunk_ids:
                raise ValueError("parent and child links must agree")
            if any(by_id[child].parent_chunk_id != chunk.chunk_id for child in chunk.child_chunk_ids):
                raise ValueError("parent and child links must agree")
        seen, active = set(), set()
        def visit(identifier: str) -> None:
            if identifier in active:
                raise ValueError("chunk parent links must be acyclic")
            if identifier in seen:
                return
            active.add(identifier)
            for child in by_id[identifier].child_chunk_ids:
                visit(child)
            active.remove(identifier)
            seen.add(identifier)
        for identifier in by_id:
            visit(identifier)
        return self
