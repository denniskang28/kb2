from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kb2_runtime.trace.contracts import ArtifactReference

STAGE_KINDS = ("analyze", "rewrite", "route", "retrieve", "fuse", "rerank", "context", "generate", "verify", "repair", "abstain", "final_state")
_ORDER = {kind: index for index, kind in enumerate(STAGE_KINDS)}


class QueryProfileContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class QueryStage(QueryProfileContract):
    stage_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}$")
    kind: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}$")
    plugin_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")
    configuration: dict[str, Any] = Field(default_factory=dict, max_length=64)
    inputs: dict[str, str] = Field(default_factory=dict, max_length=16)
    outputs: tuple[str, ...] = Field(default_factory=tuple, max_length=16)
    when: dict[str, Any] | None = None
    max_attempts: int | None = None


class QueryProfile(QueryProfileContract):
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}$")
    stages: tuple[QueryStage, ...] = Field(min_length=2, max_length=16)

    @model_validator(mode="after")
    def bounded_fixed_slots(self) -> "QueryProfile":
        kinds = [stage.kind for stage in self.stages]
        if any(kind not in _ORDER for kind in kinds) or len({stage.stage_id for stage in self.stages}) != len(self.stages):
            raise ValueError("stage IDs and kinds are invalid")
        return self


class SelectionRule(QueryProfileContract):
    rule_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}$")
    question_class: str | None = Field(default=None, max_length=64)
    document_class: str | None = Field(default=None, max_length=64)
    when: dict[str, Any] | None = None
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}$")

    @model_validator(mode="after")
    def selector_present(self) -> "SelectionRule":
        if self.question_class is None and self.document_class is None and self.when is None:
            raise ValueError("selection rule needs a selector")
        return self


class QueryProfileSet(QueryProfileContract):
    schema_version: str = "v1"
    default_profile_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}$")
    profiles: tuple[QueryProfile, ...] = Field(min_length=1, max_length=32)
    selection_rules: tuple[SelectionRule, ...] = Field(default_factory=tuple, max_length=64)

    @model_validator(mode="after")
    def valid_references(self) -> "QueryProfileSet":
        ids = [profile.profile_id for profile in self.profiles]
        if self.schema_version != "v1" or len(ids) != len(set(ids)) or self.default_profile_id not in ids or any(rule.profile_id not in ids for rule in self.selection_rules):
            raise ValueError("profile references are invalid")
        return self


class QueryArtifactBinding(QueryProfileContract):
    artifact_id: str
    artifact_type: str
    schema_revision: str
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_size: int = Field(ge=0)

    @classmethod
    def from_reference(cls, reference: ArtifactReference) -> "QueryArtifactBinding":
        return cls(artifact_id=str(reference.id), artifact_type=reference.artifact_type, schema_revision=reference.schema_revision, content_digest=reference.content_digest, byte_size=reference.byte_size)

    @model_validator(mode="after")
    def is_search_index(self) -> "QueryArtifactBinding":
        if (self.artifact_type, self.schema_revision) != ("search.index.result", "v1"):
            raise ValueError("search artifact must be search.index.result/v1")
        return self


class QueryResolutionRequest(QueryProfileContract):
    explicit_profile_id: str | None = Field(default=None, max_length=48)
    question_class: str | None = Field(default=None, max_length=64)
    document_class: str | None = Field(default=None, max_length=64)
    language_hint: str = Field(default="", max_length=32)
    question_length: int = Field(default=0, ge=0, le=100_000)
    has_tables: bool = False
    has_hierarchy: bool = False

    def observables(self) -> dict[str, Any]:
        return self.model_dump(exclude={"explicit_profile_id"})
