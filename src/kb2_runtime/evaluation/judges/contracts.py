from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
CaseId = Annotated[str, Field(pattern=r"^qcase_[a-f0-9]{16,64}$")]


class JudgeContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def canonical_bytes(value: object) -> bytes:
    payload = value.model_dump(mode="json", exclude_none=True) if hasattr(value, "model_dump") else value
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class Eligibility(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    ADVISORY = "ADVISORY"
    INELIGIBLE = "INELIGIBLE"
    DRIFTED = "DRIFTED"


class JudgeDefinition(JudgeContract):
    schema_version: Literal["JudgeDefinition/v1"] = "JudgeDefinition/v1"
    definition_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
    rubric_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
    plugin_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
    implementation_digest: Digest
    provider_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}$")]
    model: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,96}$")]
    prompt_template: Annotated[str, Field(min_length=1, max_length=4096)]
    parameters: dict[str, str | int | float | bool] = Field(min_length=1, max_length=16)
    labels: tuple[Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,31}$")], ...] = Field(min_length=2, max_length=8)
    positive_label: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,31}$")]
    max_evidence_items: int = Field(ge=1, le=32)
    max_rationale_codes: int = Field(ge=0, le=16)

    @model_validator(mode="after")
    def shape(self) -> "JudgeDefinition":
        if len(set(self.labels)) != len(self.labels) or self.positive_label not in self.labels:
            raise ValueError("judge labels are invalid")
        if any(key.lower() in {"credential", "secret", "endpoint", "path", "command", "script", "model", "messages"} for key in self.parameters):
            raise ValueError("judge parameters contain unsafe configuration")
        if re.search(r"(?:credential|secret|api[-_ ]?key|authorization|bearer|password|endpoint)", self.prompt_template, re.I):
            raise ValueError("judge prompt contains unsafe content")
        return self

    @property
    def definition_digest(self) -> str:
        return digest(self)


class CalibrationLabel(JudgeContract):
    case_id: CaseId
    definition_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
    rubric_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
    source_artifact_id: UUID
    source_digest: Digest
    evidence_artifact_id: UUID
    evidence_digest: Digest
    slices: dict[str, str] = Field(min_length=8, max_length=8)
    label: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,31}$")]
    reviewer: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.@-]{1,64}$")]
    reviewed_at: datetime
    review_record_id: Annotated[str, Field(pattern=r"^jreview_[a-f0-9]{16,64}$")]
    review_operation: Literal["mark_reviewed"] = "mark_reviewed"
    reviewed_label_digest: Digest


class CalibrationSnapshot(JudgeContract):
    schema_version: Literal["JudgeCalibrationSnapshot/v1"] = "JudgeCalibrationSnapshot/v1"
    dataset_snapshot_id: UUID
    dataset_snapshot_digest: Digest
    definitions: tuple[JudgeDefinition, ...] = Field(min_length=1, max_length=16)
    labels: tuple[CalibrationLabel, ...] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_and_bound(self) -> "CalibrationSnapshot":
        if len({item.definition_id for item in self.definitions}) != len(self.definitions):
            raise ValueError("duplicate judge definition")
        if len({(item.case_id, item.definition_id) for item in self.labels}) != len(self.labels):
            raise ValueError("duplicate calibration case")
        definitions = {item.definition_id: item for item in self.definitions}
        if any(item.definition_id not in definitions or item.rubric_id != definitions[item.definition_id].rubric_id or item.label not in definitions[item.definition_id].labels for item in self.labels):
            raise ValueError("calibration label is outside definitions")
        return self

    @property
    def snapshot_digest(self) -> str:
        return digest(self)


class SlicePolicy(JudgeContract):
    selector: dict[str, str] = Field(min_length=1, max_length=8)
    minimum_samples: int = Field(ge=1, le=1000)
    minimum_agreement: float = Field(ge=0, le=1)
    maximum_false_positive_rate: float = Field(ge=0, le=1)
    maximum_false_negative_rate: float = Field(ge=0, le=1)


class CalibrationPolicy(JudgeContract):
    schema_version: Literal["CalibrationPolicy/v1"] = "CalibrationPolicy/v1"
    policy_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
    slices: tuple[SlicePolicy, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def unique_selectors(self) -> "CalibrationPolicy":
        keys = [tuple(sorted(item.selector.items())) for item in self.slices]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate calibration policy slice")
        return self

    @property
    def policy_digest(self) -> str:
        return digest(self)


class JudgeResult(JudgeContract):
    schema_version: Literal["JudgeResult/v1"] = "JudgeResult/v1"
    case_id: CaseId
    calibration_snapshot_id: UUID
    calibration_snapshot_digest: Digest
    definition_id: str
    definition_digest: Digest
    provider_id: str
    model: str
    plugin_id: str
    implementation_digest: Digest
    prompt_digest: Digest
    parameters_digest: Digest
    evidence_artifact_id: UUID
    evidence_digest: Digest
    final_response_artifact_id: UUID
    label: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,31}$")]
    rationale_codes: tuple[Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")], ...] = Field(max_length=16)
    cited_evidence_ids: tuple[Annotated[str, Field(pattern=r"^evd_[a-f0-9]{32}$")], ...] = Field(max_length=32)
    elapsed_ms: int = Field(ge=0, le=300_000)


class SliceReport(JudgeContract):
    selector: dict[str, str]
    sample_count: int = Field(ge=0)
    agreement: float | None = Field(default=None, ge=0, le=1)
    false_positive_count: int = Field(ge=0)
    false_negative_count: int = Field(ge=0)
    false_positive_rate: float | None = Field(default=None, ge=0, le=1)
    false_negative_rate: float | None = Field(default=None, ge=0, le=1)
    status: Eligibility


class CalibrationReport(JudgeContract):
    schema_version: Literal["JudgeCalibrationReport/v1"] = "JudgeCalibrationReport/v1"
    calibration_snapshot_id: UUID
    calibration_snapshot_digest: Digest
    definition_id: str
    definition_digest: Digest
    policy_digest: Digest
    result_artifact_ids: tuple[UUID, ...] = Field(min_length=1, max_length=1000)
    overall: SliceReport
    slices: tuple[SliceReport, ...] = Field(min_length=1, max_length=64)
    eligibility: Eligibility
