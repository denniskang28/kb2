from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


AXES = ("extraction", "structure", "chunking", "enrichment", "embedding", "indexing")


class ProfileContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SchemaRef(ProfileContract):
    artifact_type: str = Field(min_length=1, max_length=64)
    schema_revision: str = Field(min_length=1, max_length=64)

    @property
    def pair(self) -> tuple[str, str]:
        return (self.artifact_type, self.schema_revision)


class QualityResult(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class Candidate(ProfileContract):
    plugin_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")
    configuration: dict[str, Any] = Field(default_factory=dict, max_length=64)
    inputs: dict[str, str] = Field(default_factory=dict, max_length=16)
    outputs: tuple[str, ...] = Field(default_factory=tuple, max_length=16)
    when: dict[str, Any] | None = None
    accept_quality: tuple[QualityResult, ...] = (QualityResult.PASS,)

    @field_validator("accept_quality")
    @classmethod
    def quality_unique(cls, value: tuple[QualityResult, ...]) -> tuple[QualityResult, ...]:
        if not value or len(set(value)) != len(value):
            raise ValueError("accept_quality must be a nonempty unique list")
        return value


class Axis(ProfileContract):
    candidates: tuple[Candidate, ...] = Field(min_length=1, max_length=16)
    on_exhausted: str | None = None

    @model_validator(mode="after")
    def terminal_policy(self) -> "Axis":
        if set(self.candidates[-1].accept_quality) != set(QualityResult) and self.on_exhausted != "fail":
            raise ValueError("last candidate requires on_exhausted=fail")
        return self


class Profile(ProfileContract):
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}$")
    axes: dict[str, Axis]

    @model_validator(mode="after")
    def all_axes(self) -> "Profile":
        if tuple(self.axes) != AXES:
            raise ValueError("axes must contain exactly the fixed ingestion axes in order")
        return self


class DocumentClassRule(ProfileContract):
    rule_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}$")
    document_class: str = Field(min_length=1, max_length=64)
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}$")


class PreflightRule(ProfileContract):
    rule_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}$")
    when: dict[str, Any]
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}$")


class ProfileSet(ProfileContract):
    schema_version: str = "v1"
    default_profile_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}$")
    document_inputs: dict[str, SchemaRef] = Field(default_factory=lambda: {"source": SchemaRef(artifact_type="opaque.bytes", schema_revision="v1")})
    profiles: tuple[Profile, ...] = Field(min_length=1, max_length=32)
    document_class_rules: tuple[DocumentClassRule, ...] = Field(default_factory=tuple, max_length=64)
    preflight_rules: tuple[PreflightRule, ...] = Field(default_factory=tuple, max_length=64)

    @model_validator(mode="after")
    def references_unique(self) -> "ProfileSet":
        ids = [profile.profile_id for profile in self.profiles]
        classes = [rule.document_class for rule in self.document_class_rules]
        if self.schema_version != "v1" or len(set(ids)) != len(ids) or self.default_profile_id not in ids or len(set(classes)) != len(classes):
            raise ValueError("profile or rule references are invalid")
        targets = [rule.profile_id for rule in (*self.document_class_rules, *self.preflight_rules)]
        if any(target not in ids for target in targets):
            raise ValueError("rule target does not exist")
        return self


class ResolutionRequest(ProfileContract):
    media_type: str = Field(default="", max_length=128)
    extension: str = Field(default="", max_length=32)
    byte_size: int = Field(default=0, ge=0, le=2**40)
    page_count: int = Field(default=0, ge=0, le=100000)
    language_hint: str = Field(default="", max_length=32)
    has_embedded_text: bool = False
    is_scanned: bool = False
    document_class: str | None = Field(default=None, max_length=64)
    explicit_profile_id: str | None = Field(default=None, max_length=48)

    def observables(self) -> dict[str, Any]:
        return self.model_dump(exclude={"explicit_profile_id"})
