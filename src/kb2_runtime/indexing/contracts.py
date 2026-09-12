from __future__ import annotations

import math
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from kb2_runtime.canonical.contracts import DocumentMetadata, StableId
from kb2_runtime.chunking.contracts import ChunkCitation, EnrichmentField


DIMENSION = 256
MAX_QUERY_CHARS = 4096


class IndexingContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EmbeddingRecord(IndexingContract):
    chunk_id: Annotated[str, Field(pattern=r"^chk_[a-f0-9]{32}$")]
    values: tuple[float, ...] = Field(min_length=1, max_length=DIMENSION)

    @field_validator("values")
    @classmethod
    def finite(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if not all(math.isfinite(item) for item in value):
            raise ValueError("embedding values must be finite")
        return value

    @model_validator(mode="after")
    def normalized(self) -> "EmbeddingRecord":
        if abs(math.sqrt(sum(item * item for item in self.values)) - 1.0) > 1e-6:
            raise ValueError("embedding record must be L2 normalized")
        return self


class EmbeddingSet(IndexingContract):
    schema_version: Literal["EmbeddingSet/v1"] = "EmbeddingSet/v1"
    source_chunk_set_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    plugin_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
    implementation_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    model_id: str = Field(min_length=1, max_length=128)
    dimension: int = Field(gt=0, le=DIMENSION)
    normalization: Literal["l2"] = "l2"
    records: tuple[EmbeddingRecord, ...] = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def aligned_normalized_records(self) -> "EmbeddingSet":
        ids = [record.chunk_id for record in self.records]
        if len(ids) != len(set(ids)) or any(len(record.values) != self.dimension for record in self.records):
            raise ValueError("embedding records must be unique and match dimension")
        return self


class SearchDocument(IndexingContract):
    document_id: StableId
    chunk_id: Annotated[str, Field(pattern=r"^chk_[a-f0-9]{32}$")]
    keyword_text: str = Field(min_length=1, max_length=16_384)
    hierarchy_context: tuple[str, ...] = Field(default_factory=tuple, max_length=16)
    language: str | None = Field(default=None, max_length=64)
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    enrichments: dict[str, EnrichmentField] = Field(default_factory=dict, max_length=32)
    citations: tuple[ChunkCitation, ...] = Field(min_length=1, max_length=128)
    embedding: EmbeddingRecord
    parent_chunk_id: Annotated[str, Field(pattern=r"^chk_[a-f0-9]{32}$")] | None = None
    child_chunk_ids: tuple[Annotated[str, Field(pattern=r"^chk_[a-f0-9]{32}$")], ...] = Field(default_factory=tuple, max_length=64)

    @model_validator(mode="after")
    def citation_and_embedding_bindings(self) -> "SearchDocument":
        if (self.embedding.chunk_id != self.chunk_id or len({citation.element_id for citation in self.citations}) != len(self.citations)
                or self.parent_chunk_id == self.chunk_id or self.chunk_id in self.child_chunk_ids
                or len(set(self.child_chunk_ids)) != len(self.child_chunk_ids)):
            raise ValueError("search document bindings are invalid")
        return self


class SearchDocumentSet(IndexingContract):
    schema_version: Literal["SearchDocumentSet/v1"] = "SearchDocumentSet/v1"
    source_chunk_set_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    source_embedding_set_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    document_id: StableId
    embedding_plugin_id: str = Field(min_length=1, max_length=64)
    embedding_implementation_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    embedding_model_id: str = Field(min_length=1, max_length=128)
    dimension: int = Field(gt=0, le=DIMENSION)
    documents: tuple[SearchDocument, ...] = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def complete_alignment(self) -> "SearchDocumentSet":
        ids = [document.chunk_id for document in self.documents]
        if len(ids) != len(set(ids)) or any(document.document_id != self.document_id or len(document.embedding.values) != self.dimension for document in self.documents):
            raise ValueError("search documents must be unique and aligned")
        return self


class LocalHybridConfig(IndexingContract):
    lexical_weight: float = Field(default=0.5, ge=0, le=1)
    vector_weight: float = Field(default=0.5, ge=0, le=1)

    @model_validator(mode="after")
    def at_least_one_weight(self) -> "LocalHybridConfig":
        if self.lexical_weight + self.vector_weight <= 0:
            raise ValueError("at least one search weight is required")
        return self


class SearchIndexResult(IndexingContract):
    schema_version: Literal["SearchIndexResult/v1"] = "SearchIndexResult/v1"
    index_id: Annotated[str, Field(pattern=r"^idx_[a-f0-9]{32}$")]
    implementation_id: str = Field(min_length=1, max_length=64)
    implementation_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    configuration: LocalHybridConfig
    search_document_set_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    embedding_set_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    document_count: int = Field(gt=0, le=4096)
    term_postings: dict[str, tuple[tuple[str, int], ...]] = Field(max_length=100_000)
    document_lengths: dict[str, int] = Field(min_length=1, max_length=4096)
    documents: tuple[SearchDocument, ...] = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def payload_is_complete(self) -> "SearchIndexResult":
        if self.document_count != len(self.documents) or set(self.document_lengths) != {item.chunk_id for item in self.documents}:
            raise ValueError("index payload must cover exactly its documents")
        by_id = {item.chunk_id: item for item in self.documents}
        if any((item.parent_chunk_id and (item.parent_chunk_id not in by_id or item.chunk_id not in by_id[item.parent_chunk_id].child_chunk_ids))
               or any(child not in by_id or by_id[child].parent_chunk_id != item.chunk_id for child in item.child_chunk_ids)
               for item in self.documents):
            raise ValueError("index hierarchy links must agree")
        return self


class SearchRequest(IndexingContract):
    query: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)
    top_k: int = Field(default=10, ge=1, le=100)
    lexical_weight: float = Field(default=0.5, ge=0, le=1)
    vector_weight: float = Field(default=0.5, ge=0, le=1)
    language: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def search_weights(self) -> "SearchRequest":
        if self.lexical_weight + self.vector_weight <= 0:
            raise ValueError("at least one search weight is required")
        return self


class SearchHit(IndexingContract):
    document_id: StableId
    chunk_id: Annotated[str, Field(pattern=r"^chk_[a-f0-9]{32}$")]
    score: float
    lexical_score: float
    vector_score: float
    hierarchy_context: tuple[str, ...]
    language: str | None
    metadata: DocumentMetadata
    citations: tuple[ChunkCitation, ...]


class EmbeddingPort(Protocol):
    def embed_text(self, text: str) -> tuple[float, ...]: ...


class HybridSearchPort(Protocol):
    def search(self, result: SearchIndexResult, request: SearchRequest, embedder: EmbeddingPort) -> tuple[SearchHit, ...]: ...
