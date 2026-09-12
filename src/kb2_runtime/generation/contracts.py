from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GenerationContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GenerationConfig(GenerationContract):
    model: Literal["deepseek-v4-flash", "deepseek-v4-pro"]
    prompt_revision: Literal["grounded-json-v1"] = "grounded-json-v1"
    max_answer_chars: int = Field(default=2048, ge=1, le=4096)
    max_tokens: int = Field(default=512, ge=1, le=1024)
    temperature: float = Field(default=0.0, ge=0, le=0.3, allow_inf_nan=False)


class DefaultGenerationConfig(GenerationConfig):
    model: Literal["deepseek-v4-flash"] = "deepseek-v4-flash"


class HighPrecisionGenerationConfig(GenerationConfig):
    model: Literal["deepseek-v4-pro"] = "deepseek-v4-pro"


class VerificationConfig(GenerationContract):
    minimum_items: int = Field(default=1, ge=0, le=100)
    citation_policy: Literal["all_claims"] = "all_claims"
    answerability: Literal["answerable", "ambiguous", "not_answerable"] = "answerable"
    forbidden_phrases: tuple[str, ...] = Field(default_factory=tuple, max_length=16)


class FinalStateConfig(GenerationContract):
    pass


class RepairConfig(GenerationContract):
    pass


class GeneratedAnswer(GenerationContract):
    schema_version: Literal["GeneratedAnswer/v1"] = "GeneratedAnswer/v1"
    answer_id: str = Field(pattern=r"^ans_[a-f0-9]{32}$")
    evidence_artifact_id: UUID
    evidence_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    question_artifact_id: UUID
    question_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    generator_plugin_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")
    implementation_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    configuration_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    answer: str = Field(min_length=1, max_length=4096)
    citation_keys: tuple[Annotated[str, Field(pattern=r"^cit_[a-f0-9]{32}$")], ...] = Field(min_length=1, max_length=100)
    attempt: int = Field(ge=1, le=4)

    @model_validator(mode="after")
    def unique_citations(self) -> "GeneratedAnswer":
        if len(self.citation_keys) != len(set(self.citation_keys)):
            raise ValueError("citation keys must be unique")
        return self


class VerificationResult(GenerationContract):
    schema_version: Literal["VerificationResult/v1"] = "VerificationResult/v1"
    verification_id: str = Field(pattern=r"^ver_[a-f0-9]{32}$")
    generated_answer_artifact_id: UUID
    evidence_artifact_id: UUID
    evidence_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    outcome: Literal["pass", "repairable", "clarification_required", "abstain", "failed"]
    failure_codes: tuple[str, ...] = Field(default_factory=tuple, max_length=16)
    resolved_citation_keys: tuple[str, ...] = Field(default_factory=tuple, max_length=100)
    missing_citation_keys: tuple[str, ...] = Field(default_factory=tuple, max_length=100)
    answerable: bool


class FinalResponse(GenerationContract):
    schema_version: Literal["FinalResponse/v1"] = "FinalResponse/v1"
    response_id: str = Field(pattern=r"^fin_[a-f0-9]{32}$")
    state: Literal["ANSWERED", "CLARIFICATION_REQUIRED", "ABSTAINED", "FAILED"]
    evidence_artifact_id: UUID
    verification_artifact_id: UUID | None = None
    generated_answer_artifact_id: UUID | None = None
    answer: str | None = Field(default=None, max_length=4096)
    citation_keys: tuple[str, ...] = Field(default_factory=tuple, max_length=100)
    action: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def terminal_payload(self) -> "FinalResponse":
        if self.state == "ANSWERED":
            if not self.answer or not self.citation_keys or self.action is not None:
                raise ValueError("answered response requires validated answer and citations")
        elif self.answer is not None or self.citation_keys or not self.action:
            raise ValueError("non-answered response must contain only a safe action")
        return self
