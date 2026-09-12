from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from kb2_runtime.trace.contracts import metadata_contains_sensitive_text

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
MetricId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def canonical_bytes(value: BaseModel | dict) -> bytes:
    raw = value.model_dump(mode="json", exclude_none=True) if isinstance(value, BaseModel) else value
    return json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False, default=str).encode("ascii")


def digest(value: BaseModel | dict) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class ArtifactBinding(Contract):
    role: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")]
    artifact_id: UUID
    artifact_type: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")]
    content_digest: Digest
    case_id: Annotated[str, Field(pattern=r"^qcase_[a-f0-9]{16,64}$")] | None = None


class PlanIdentity(Contract):
    plugin_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
    implementation_digest: Digest
    configuration_digest: Digest | None = None
    provider_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")] | None = None
    model: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    prompt_digest: Digest | None = None


class SubjectMetricReport(Contract):
    """S-021 attribution wrapper; MetricReport itself remains cross-story stable."""
    subject: Literal["baseline", "candidate"]
    metric_artifact_id: UUID


class EvaluationSubject(Contract):
    subject: Literal["baseline", "candidate"]
    ingestion_plan: dict = Field(min_length=1, max_length=32)
    ingestion_plan_digest: Digest
    query_plan: dict = Field(min_length=1, max_length=32)
    query_plan_digest: Digest
    bindings: tuple[ArtifactBinding, ...] = Field(min_length=1, max_length=1000)
    declared_identities: tuple[PlanIdentity, ...] = Field(default_factory=tuple, max_length=64)

    @model_validator(mode="after")
    def pinned_plans_and_roles(self) -> "EvaluationSubject":
        if digest(self.ingestion_plan) != self.ingestion_plan_digest or digest(self.query_plan) != self.query_plan_digest:
            raise ValueError("resolved plan digest does not match canonical payload")
        if metadata_contains_sensitive_text(self.ingestion_plan) or metadata_contains_sensitive_text(self.query_plan):
            raise ValueError("resolved plan contains unsafe content")
        roles = [(item.case_id, item.role) for item in self.bindings]
        if len(roles) != len(set(roles)):
            raise ValueError("duplicate case role binding")
        plan_plugins = {value.get("plugin") for value in (self.ingestion_plan, self.query_plan) if isinstance(value.get("plugin"), str)}
        declared = {item.plugin_id for item in self.declared_identities}
        if plan_plugins and (not declared or not plan_plugins <= declared):
            raise ValueError("resolved plan plugin identity is not declared")
        return self


class QualityGate(Contract):
    gate_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")]
    metric_id: MetricId
    owner: Literal["ingestion", "retrieval", "context", "answer", "citation", "decision", "judge"]
    selector: dict[str, str] = Field(min_length=1, max_length=8)
    aggregation: Literal["mean", "rate", "any_failure"]
    minimum_samples: int = Field(ge=1, le=1000)
    direction: Literal["higher_is_better", "lower_is_better"] | None = None
    threshold: float | None = Field(default=None, ge=0, le=1)
    severity: Literal["hard", "advisory"]
    failure_code: Literal["unsupported_fact", "invalid_citation"] | None = None

    @model_validator(mode="after")
    def shape(self) -> "QualityGate":
        if self.aggregation == "any_failure":
            if self.threshold is not None or self.direction is not None or self.failure_code is None:
                raise ValueError("any_failure gate must declare only its predicate")
        elif self.threshold is None or self.direction is None or self.failure_code is not None:
            raise ValueError("threshold gate is incomplete")
        if self.aggregation == "rate" and self.owner not in {"decision", "citation"}:
            raise ValueError("rate gate requires a binary metric owner")
        return self


class RuntimeSummary(Contract):
    runtime_digest: Digest
    package_digest: Digest
    implementation_digest: Digest
    os_family: Literal["darwin", "linux", "windows"]
    architecture: Annotated[str, Field(pattern=r"^[a-z0-9_:-]{1,32}$")]
    resource_sampler_version: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")]


class ConfidencePolicy(Contract):
    kind: Literal["none", "wilson"]
    level: float | None = Field(default=None, gt=0, lt=1)

    @model_validator(mode="after")
    def confidence_shape(self) -> "ConfidencePolicy":
        if (self.kind == "wilson") != (self.level is not None):
            raise ValueError("confidence policy level is invalid")
        return self


class EvaluationManifest(Contract):
    schema_version: Literal["EvaluationManifest/v1"] = "EvaluationManifest/v1"
    dataset_snapshot_id: UUID
    dataset_snapshot_digest: Digest
    taxonomy_digest: Digest
    input_catalog_digest: Digest
    case_ids: tuple[Annotated[str, Field(pattern=r"^qcase_[a-f0-9]{16,64}$")], ...] = Field(min_length=1, max_length=1000)
    subjects: tuple[EvaluationSubject, EvaluationSubject]
    metric_ids: tuple[MetricId, ...] = Field(min_length=1, max_length=64)
    gates: tuple[QualityGate, ...] = Field(default_factory=tuple, max_length=64)
    runtime: RuntimeSummary
    confidence_policy: ConfidencePolicy | None = None
    experiment_name: Annotated[str, Field(min_length=1, max_length=128)] | None = None

    @model_validator(mode="after")
    def complete(self) -> "EvaluationManifest":
        if tuple(sorted(self.case_ids)) != self.case_ids or len(set(self.case_ids)) != len(self.case_ids):
            raise ValueError("case IDs must be unique and ordered")
        if {item.subject for item in self.subjects} != {"baseline", "candidate"}:
            raise ValueError("manifest requires baseline and candidate")
        if len(set(self.metric_ids)) != len(self.metric_ids) or len({gate.gate_id for gate in self.gates}) != len(self.gates):
            raise ValueError("manifest identifiers are duplicated")
        if any(gate.metric_id not in self.metric_ids for gate in self.gates):
            raise ValueError("gate metric is not declared")
        return self


class GateState(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT = "INSUFFICIENT"
    INELIGIBLE = "INELIGIBLE"


class GateResult(Contract):
    subject: Literal["baseline", "candidate"] | None = None
    gate_id: str
    state: GateState
    reason: str
    selected_report_ids: tuple[UUID, ...]
    matched_case_ids: tuple[str, ...] = ()
    sample_count: int = Field(ge=0)
    value: float | None = Field(default=None, ge=0, le=1)
    aggregate_id: UUID | None = None
    state_counts: dict[str, int] = Field(default_factory=dict, max_length=4)


class FailedCaseLink(Contract):
    case_id: str
    subject: Literal["baseline", "candidate"]
    gate_id: str
    metric_report_id: UUID | None = None
    metric_aggregate_id: UUID | None = None
    source_artifact_id: UUID | None = None
    ingestion_artifact_id: UUID | None = None
    retrieval_artifact_id: UUID | None = None
    fusion_artifact_id: UUID | None = None
    rerank_artifact_id: UUID | None = None
    evidence_artifact_id: UUID | None = None
    generation_artifact_id: UUID | None = None
    verification_artifact_id: UUID | None = None
    final_response_artifact_id: UUID | None = None
    evaluation_run_id: UUID | None = None
    evaluation_report_id: UUID | None = None


class OperationReport(Contract):
    elapsed_ms: int = Field(ge=0)
    cpu_ms: int | None = Field(default=None, ge=0)
    peak_rss: int | None = Field(default=None, ge=0)
    io_bytes: int | None = Field(default=None, ge=0)
    availability: Literal["AVAILABLE", "PARTIAL", "UNAVAILABLE"]


class ComparisonMode(StrEnum):
    SINGLE_AXIS = "SINGLE_AXIS"
    MULTI_AXIS_NON_CAUSAL = "MULTI_AXIS_NON_CAUSAL"


class Delta(Contract):
    baseline: float | None
    candidate: float | None
    absolute: float | None
    relative: float | None
    relative_state: Literal["VALUE", "UNDEFINED_BASELINE_ZERO", "NOT_MEANINGFUL"]


class ReplayObservation(Contract):
    schema_version: Literal["EvaluationReplayObservation/v1"] = "EvaluationReplayObservation/v1"
    state: Literal["STABLE", "MODEL_OUTPUT_CHANGED", "ENVIRONMENT_CHANGED"]
    original_digest: Digest
    replay_digest: Digest
    expected_runtime_digest: Digest | None = None
    observed_runtime_digest: Digest | None = None


class LayeredReport(Contract):
    """Safe persisted index: values stay in MetricReport/MetricAggregate Artifacts."""
    schema_version: Literal["EvaluationReport/v1"] = "EvaluationReport/v1"
    manifest_artifact_id: UUID
    manifest_digest: Digest
    report_ids: tuple[UUID, ...] = Field(max_length=1000)
    aggregate_ids: tuple[UUID, ...] = Field(default_factory=tuple, max_length=1000)
    report_subjects: dict[UUID, Literal["baseline", "candidate"]] = Field(default_factory=dict, max_length=1000)
    layers: dict[str, tuple[UUID, ...]]
    gate_results: tuple[GateResult, ...]
    operation: OperationReport
    failed_cases: tuple[FailedCaseLink, ...] = Field(default_factory=tuple, max_length=1000)

    @model_validator(mode="after")
    def independent_layers(self) -> "LayeredReport":
        required = {"ingestion", "retrieval", "answer", "citation", "decision", "judge", "latency", "resources"}
        if set(self.layers) != required or any(key in self.layers for key in {"overall", "score", "rank"}):
            raise ValueError("evaluation report layers are incomplete")
        if tuple(sorted(self.report_ids, key=str)) != self.report_ids:
            raise ValueError("report IDs must be ordered")
        return self


class NavigationIndex(Contract):
    schema_version: Literal["EvaluationNavigationIndex/v1"] = "EvaluationNavigationIndex/v1"
    evaluation_report_id: UUID
    evaluation_run_id: UUID
    links: tuple[FailedCaseLink, ...] = Field(default_factory=tuple, max_length=1000)
