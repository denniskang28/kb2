from __future__ import annotations
import asyncio
from datetime import datetime
from typing import Annotated, Literal, Protocol
from pydantic import ConfigDict, Field, model_validator
from kb2_runtime.fusion.contracts import FusedCandidate, FusionCandidateSet
from kb2_runtime.canonical.contracts import StableId
from kb2_runtime.indexing.contracts import SearchIndexResult
from kb2_runtime.retrieval.contracts import IndexArtifactBinding, RetrievalContract

class RerankerConfig(RetrievalContract): limit: int = Field(default=10, ge=1, le=100)

class RerankDecision(RetrievalContract):
    chunk_id: Annotated[str, Field(pattern=r"^chk_[a-f0-9]{32}$")]
    input_rank: int = Field(ge=1, le=100)
    output_rank: int | None = Field(default=None, ge=1, le=100)
    safe_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    reason: Literal["included", "limit_excluded"]
    @model_validator(mode="after")
    def coherent(self) -> "RerankDecision":
        if (self.reason == "included") != (self.output_rank is not None): raise ValueError("decision inclusion must match output rank")
        return self


class RerankInputCandidate(RetrievalContract):
    """The immutable identity/rank inventory that every decision must cover."""

    chunk_id: Annotated[str, Field(pattern=r"^chk_[a-f0-9]{32}$")]
    input_rank: int = Field(ge=1, le=100)

class RerankedCandidateSet(RetrievalContract):
    schema_version: Literal["RerankedCandidateSet/v1"] = "RerankedCandidateSet/v1"
    candidate_set_id: Annotated[str, Field(pattern=r"^rrs_[a-f0-9]{32}$")]
    fusion_candidate_set_id: Annotated[str, Field(pattern=r"^fcs_[a-f0-9]{32}$")]
    index: IndexArtifactBinding
    index_id: Annotated[str, Field(pattern=r"^idx_[a-f0-9]{32}$")]
    document_id: StableId
    reranker_plugin_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
    implementation_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    configuration_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    input_candidates: tuple[RerankInputCandidate, ...] = Field(default_factory=tuple, max_length=100)
    candidates: tuple[FusedCandidate, ...] = Field(default_factory=tuple, max_length=100)
    decisions: tuple[RerankDecision, ...] = Field(default_factory=tuple, max_length=100)
    @model_validator(mode="after")
    def decisions_are_complete(self) -> "RerankedCandidateSet":
        selected = {item.chunk_id: item for item in self.candidates}
        inputs = {item.chunk_id: item for item in self.input_candidates}
        decisions = {item.chunk_id: item for item in self.decisions}
        if (len(inputs) != len(self.input_candidates) or len(decisions) != len(self.decisions)
                or [item.input_rank for item in self.input_candidates] != list(range(1, len(self.input_candidates) + 1))
                or set(decisions) != set(inputs)
                or any(decisions[key].input_rank != item.input_rank for key, item in inputs.items())
                or [item.rank for item in self.candidates] != list(range(1, len(self.candidates) + 1))
                or any(item.document_id != self.document_id or item.chunk_id not in inputs for item in self.candidates)
                or {key for key, value in decisions.items() if value.reason == "included"} != set(selected)
                or any(decisions[key].output_rank != value.rank for key, value in selected.items())):
            raise ValueError("rerank decisions are invalid")
        return self

class RerankerRequest(RetrievalContract):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    question: str = Field(min_length=1, max_length=4096)
    fused: FusionCandidateSet
    index: SearchIndexResult
    index_binding: IndexArtifactBinding
    configuration: RerankerConfig
    configuration_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    plugin_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
    implementation_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    cancellation: asyncio.Event | None = Field(default=None, exclude=True)
    deadline_at: datetime | None = Field(default=None, exclude=True)

class RerankerPort(Protocol):
    def rerank(self, request: RerankerRequest) -> RerankedCandidateSet: ...
