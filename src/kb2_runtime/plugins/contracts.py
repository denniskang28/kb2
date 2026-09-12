from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

from kb2_runtime.trace.contracts import ArtifactReference, Metric, QualitySignal, safe_metadata_text

PluginId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}@[1-9][0-9]*$")]
SchemaPair = tuple[str, str]
_FORBIDDEN_SCHEMA = re.compile(r"(?:command|script|path|credential|secret|environment|entrypoint|image|mount|executable)", re.I)


class PluginContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RunnerType(StrEnum):
    IN_PROCESS = "in_process"
    CONTAINER = "container"


class ResourceHints(PluginContract):
    cpu_class: str = Field(default="small", pattern=r"^[a-z0-9_.-]{1,32}$")
    memory_class: str = Field(default="small", pattern=r"^[a-z0-9_.-]{1,32}$")
    gpu_class: str | None = Field(default=None, pattern=r"^[a-z0-9_.-]{1,32}$")
    max_output_bytes: int = Field(default=1024 * 1024, ge=1, le=16 * 1024 * 1024)


class PluginPort(PluginContract):
    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}$")
    artifact_type: str = Field(min_length=1, max_length=64)
    schema_revision: str = Field(min_length=1, max_length=64)
    min_items: int = Field(default=1, ge=1, le=64)
    max_items: int = Field(default=1, ge=1, le=64)

    @model_validator(mode="after")
    def cardinality_is_valid(self) -> "PluginPort":
        if self.min_items > self.max_items:
            raise ValueError("port minimum cannot exceed maximum")
        return self

    @property
    def schema(self) -> SchemaPair:
        return (self.artifact_type, self.schema_revision)


class PluginDescriptor(PluginContract):
    plugin_id: PluginId
    kind: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}$")
    implementation_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    runner: RunnerType
    configuration_schema: dict[str, Any] = Field(max_length=64)
    input_schemas: tuple[SchemaPair, ...] = Field(min_length=1, max_length=16)
    output_schemas: tuple[SchemaPair, ...] = Field(min_length=1, max_length=16)
    input_ports: tuple[PluginPort, ...] = Field(default_factory=tuple, max_length=16)
    output_ports: tuple[PluginPort, ...] = Field(default_factory=tuple, max_length=16)
    quality_signal_names: tuple[str, ...] = Field(default_factory=tuple, max_length=16)
    resource_hints: ResourceHints = Field(default_factory=ResourceHints)
    timeout_seconds: float = Field(gt=0, le=300)
    capabilities: tuple[str, ...] = Field(default_factory=tuple, max_length=16)

    @field_validator("input_schemas", "output_schemas")
    @classmethod
    def schemas_valid(cls, value: tuple[SchemaPair, ...]) -> tuple[SchemaPair, ...]:
        # Named ports may intentionally carry the same artifact schema.
        if any(not a or not b for a, b in value):
            raise ValueError("schema declarations must be nonempty pairs")
        return value

    @model_validator(mode="after")
    def ports_match_schemas(self) -> "PluginDescriptor":
        # Legacy descriptors are normalized to deterministic names. New Profiles
        # always consume the resulting named contracts.
        if not self.input_ports:
            object.__setattr__(self, "input_ports", tuple(
                PluginPort(name=f"input_{index}", artifact_type=schema[0], schema_revision=schema[1])
                for index, schema in enumerate(self.input_schemas)
            ))
        if not self.output_ports:
            object.__setattr__(self, "output_ports", tuple(
                PluginPort(name=f"output_{index}", artifact_type=schema[0], schema_revision=schema[1])
                for index, schema in enumerate(self.output_schemas)
            ))
        for ports, schemas in ((self.input_ports, self.input_schemas), (self.output_ports, self.output_schemas)):
            if len({port.name for port in ports}) != len(ports) or tuple(port.schema for port in ports) != schemas:
                raise ValueError("named ports must exactly match schema declarations")
        if len(set(self.quality_signal_names)) != len(self.quality_signal_names) or any(
            not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", value) for value in self.quality_signal_names
        ):
            raise ValueError("quality signal names must be unique labels")
        if any(value.startswith("engine.") for value in self.quality_signal_names):
            raise ValueError("engine quality signal names are reserved")
        return self

    @field_validator("capabilities")
    @classmethod
    def capabilities_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value) or any(not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", item) for item in value):
            raise ValueError("capabilities must be unique labels")
        return value

    @field_validator("configuration_schema")
    @classmethod
    def schema_is_safe(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        if len(encoded) > 16 * 1024 or "$ref" in encoded or _FORBIDDEN_SCHEMA.search(encoded):
            raise ValueError("configuration schema contains unsupported executable configuration")
        return value


class PluginAvailability(PluginContract):
    plugin_id: PluginId
    registered: bool = True
    runnable: bool
    reason: str | None = Field(default=None, max_length=128)


class ArtifactInput(PluginContract):
    reference: ArtifactReference
    content: bytes = Field(max_length=16 * 1024 * 1024)


class StageInvocation(PluginContract):
    run_id: UUID
    stage_attempt_id: UUID
    stage_key: str = Field(min_length=1, max_length=64)
    plugin_id: PluginId
    implementation_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    validated_configuration: dict[str, Any] = Field(max_length=64)
    configuration_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    inputs: tuple[ArtifactReference, ...] = Field(max_length=64)
    deadline_at: datetime


class PluginOutput(PluginContract):
    artifact_type: str = Field(min_length=1, max_length=64)
    schema_revision: str = Field(min_length=1, max_length=64)
    content: bytes = Field(max_length=16 * 1024 * 1024)
    summary: str = Field(default="", max_length=1024)
    metrics: tuple[Metric, ...] = Field(default_factory=tuple, max_length=64)
    quality_signals: tuple[QualitySignal, ...] = Field(default_factory=tuple, max_length=64)

    _safe_summary = field_validator("summary", mode="before")(safe_metadata_text)


class PluginInvocationResult(PluginContract):
    outputs: tuple[PluginOutput, ...] = Field(min_length=1, max_length=16)
    summary: str = Field(default="", max_length=1024)
    metrics: tuple[Metric, ...] = Field(default_factory=tuple, max_length=64)
    quality_signals: tuple[QualitySignal, ...] = Field(default_factory=tuple, max_length=64)

    _safe_summary = field_validator("summary", mode="before")(safe_metadata_text)


class PluginInvocationReceipt(PluginContract):
    """Terminal invocation facts used by generic orchestrators."""

    attempt_id: UUID
    output_ids: tuple[UUID, ...] = Field(min_length=1, max_length=16)
    metrics: tuple[Metric, ...] = Field(default_factory=tuple, max_length=64)
    quality_signals: tuple[QualitySignal, ...] = Field(default_factory=tuple, max_length=64)


class PluginContext(Protocol):
    invocation: StageInvocation
    cancellation: asyncio.Event

    async def input(self, artifact_id: UUID) -> ArtifactInput: ...


class PluginImplementation(Protocol):
    async def invoke(self, context: PluginContext) -> PluginInvocationResult: ...


def configuration_digest(configuration: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(configuration, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
