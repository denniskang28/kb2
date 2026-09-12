from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Annotated, Literal, Protocol

from pydantic import ConfigDict, Field, model_validator

from kb2_runtime.canonical.contracts import StableId
from kb2_runtime.retrieval.contracts import IndexArtifactBinding, RetrievalCandidate, RetrievalContract, RetrievalCandidateSet


class FusionConfig(RetrievalContract):
    limit: int = Field(default=10, ge=1, le=100)
    rank_constant: int = Field(default=60, ge=1, le=1000)


class CandidateContribution(RetrievalContract):
    contributor_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.@-]{0,47}$")]
    original_rank: int = Field(ge=1, le=100)
    candidate: RetrievalCandidate

    @model_validator(mode="after")
    def rank_matches_candidate(self) -> "CandidateContribution":
        if self.original_rank != self.candidate.rank:
            raise ValueError("contribution rank must match source candidate")
        return self


class FusedCandidate(RetrievalContract):
    document_id: StableId
    chunk_id: Annotated[str, Field(pattern=r"^chk_[a-f0-9]{32}$")]
    rank: int = Field(ge=1, le=100)
    safe_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    contributions: tuple[CandidateContribution, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def contributions_match_identity(self) -> "FusedCandidate":
        if any(item.candidate.document_id != self.document_id or item.candidate.chunk_id != self.chunk_id for item in self.contributions):
            raise ValueError("fused evidence identity is inconsistent")
        return self


class FusionCandidateSet(RetrievalContract):
    schema_version: Literal["FusionCandidateSet/v1"] = "FusionCandidateSet/v1"
    candidate_set_id: Annotated[str, Field(pattern=r"^fcs_[a-f0-9]{32}$")]
    index: IndexArtifactBinding
    index_id: Annotated[str, Field(pattern=r"^idx_[a-f0-9]{32}$")]
    document_id: StableId
    fusion_plugin_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
    implementation_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    configuration_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    contributor_set_ids: tuple[Annotated[str, Field(pattern=r"^rcs_[a-f0-9]{32}$")], ...] = Field(min_length=1, max_length=8)
    method: Literal["reciprocal_rank_fusion"] = "reciprocal_rank_fusion"
    candidates: tuple[FusedCandidate, ...] = Field(default_factory=tuple, max_length=100)

    @model_validator(mode="after")
    def ranks_and_identity_are_valid(self) -> "FusionCandidateSet":
        if len(set(self.contributor_set_ids)) != len(self.contributor_set_ids):
            raise ValueError("contributor sets must be unique")
        if [item.rank for item in self.candidates] != list(range(1, len(self.candidates) + 1)) or len({item.chunk_id for item in self.candidates}) != len(self.candidates) or any(item.document_id != self.document_id for item in self.candidates):
            raise ValueError("fused ranks or identities are invalid")
        return self


class FusionRequest(RetrievalContract):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    candidate_sets: tuple[RetrievalCandidateSet, ...] = Field(min_length=1, max_length=8)
    configuration: FusionConfig
    configuration_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    plugin_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
    implementation_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    cancellation: asyncio.Event | None = Field(default=None, exclude=True)
    deadline_at: datetime | None = Field(default=None, exclude=True)


class FusionPort(Protocol):
    def fuse(self, request: FusionRequest) -> FusionCandidateSet: ...
