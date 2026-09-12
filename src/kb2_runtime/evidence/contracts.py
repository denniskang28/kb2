from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Annotated, Literal, Protocol

from pydantic import ConfigDict, Field, model_validator

from kb2_runtime.canonical.contracts import Locator, StableId
from kb2_runtime.indexing.contracts import SearchIndexResult
from kb2_runtime.retrieval.contracts import IndexArtifactBinding, RetrievalContract


class ContextAssemblerConfig(RetrievalContract):
    max_items: int = Field(default=8, ge=1, le=100)
    max_tokens: int = Field(default=2048, ge=1, le=16384)
    max_excerpt_chars: int = Field(default=1024, ge=1, le=4096)
    minimum_items: int = Field(default=1, ge=0, le=100)
    structural_rule: Literal["none", "hierarchy", "table"] = "none"
    expand_parent: bool = False
    neighbor_window: int = Field(default=0, ge=0, le=2)
    source_diversity: Literal["none", "document"] = "none"

    @model_validator(mode="after")
    def bounded_minimum(self) -> "ContextAssemblerConfig":
        if self.minimum_items > self.max_items:
            raise ValueError("minimum items cannot exceed maximum items")
        if self.structural_rule == "none" and (self.expand_parent or self.neighbor_window):
            raise ValueError("structural expansion requires a declared structural rule")
        return self


class EvidenceScore(RetrievalContract):
    contributor_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.@-]{0,47}$")]
    safe_score: float = Field(ge=0, le=1, allow_inf_nan=False)


class EvidenceItem(RetrievalContract):
    evidence_id: Annotated[str, Field(pattern=r"^evd_[a-f0-9]{32}$")]
    citation_key: Annotated[str, Field(pattern=r"^cit_[a-f0-9]{32}$")]
    document_id: StableId
    chunk_id: Annotated[str, Field(pattern=r"^chk_[a-f0-9]{32}$")]
    element_ids: tuple[StableId, ...] = Field(min_length=1, max_length=128)
    locators: tuple[Locator, ...] = Field(min_length=1, max_length=128)
    excerpt: str = Field(min_length=1, max_length=4096)
    contributors: tuple[EvidenceScore, ...] = Field(min_length=1, max_length=16)
    hierarchy_context: tuple[Annotated[str, Field(min_length=1, max_length=256)], ...] = Field(default_factory=tuple, max_length=16)
    table_element_ids: tuple[StableId, ...] = Field(default_factory=tuple, max_length=128)

    @model_validator(mode="after")
    def source_identity_is_aligned(self) -> "EvidenceItem":
        # Keep the item identity independently verifiable when it is loaded
        # outside an EvidenceSet Artifact.
        from .serializer import citation_key, evidence_id
        if (len(self.element_ids) != len(self.locators) or len(set(self.element_ids)) != len(self.element_ids)
                or len({score.contributor_id for score in self.contributors}) != len(self.contributors)
                or any(item not in self.element_ids for item in self.table_element_ids)
                or self.citation_key != citation_key(self.document_id, self.chunk_id, self.element_ids, self.locators)
                or self.evidence_id != evidence_id(self.citation_key)):
            raise ValueError("evidence source identity is invalid")
        return self


class ContextDecision(RetrievalContract):
    chunk_id: Annotated[str, Field(pattern=r"^chk_[a-f0-9]{32}$")]
    source_rank: int = Field(ge=1, le=4096)
    reason: Literal["included", "excluded_budget", "deduplicated", "expanded_parent", "expanded_neighbor", "excluded_diversity"]
    safe_score: float = Field(ge=0, le=1, allow_inf_nan=False)


class EvidenceShortage(RetrievalContract):
    minimum_items: int = Field(ge=0, le=100)
    selected_items: int = Field(ge=0, le=100)
    selected_tokens: int = Field(ge=0, le=16384)
    reason: Literal["none", "no_candidates", "below_minimum", "budget_exhausted"]


class EvidenceSet(RetrievalContract):
    schema_version: Literal["EvidenceSet/v1"] = "EvidenceSet/v1"
    evidence_set_id: Annotated[str, Field(pattern=r"^evs_[a-f0-9]{32}$")]
    source_candidate_set_id: Annotated[str, Field(pattern=r"^(?:rcs|fcs|rrs)_[a-f0-9]{32}$")]
    index: IndexArtifactBinding
    index_id: Annotated[str, Field(pattern=r"^idx_[a-f0-9]{32}$")]
    document_id: StableId
    context_plugin_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
    implementation_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    configuration_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    items: tuple[EvidenceItem, ...] = Field(default_factory=tuple, max_length=100)
    decisions: tuple[ContextDecision, ...] = Field(default_factory=tuple, max_length=4096)
    shortage: EvidenceShortage

    @model_validator(mode="after")
    def output_is_explainable(self) -> "EvidenceSet":
        keys = [item.citation_key for item in self.items]
        chunks = [item.chunk_id for item in self.items]
        if (len(keys) != len(set(keys)) or len(chunks) != len(set(chunks))
                or self.shortage.selected_items != len(self.items)):
            raise ValueError("evidence set citations or shortage are invalid")
        return self


class ContextAssemblyRequest(RetrievalContract):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    candidates: object
    index: SearchIndexResult
    index_binding: IndexArtifactBinding
    configuration: ContextAssemblerConfig
    configuration_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    plugin_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
    implementation_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    cancellation: asyncio.Event | None = Field(default=None, exclude=True)
    deadline_at: datetime | None = Field(default=None, exclude=True)


class ContextAssemblerPort(Protocol):
    def assemble(self, request: ContextAssemblyRequest) -> EvidenceSet: ...
