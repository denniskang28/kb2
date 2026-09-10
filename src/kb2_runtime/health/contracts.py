from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


EntryStatus = Literal["ready", "unavailable", "not_configured", "not_probed"]
AggregateStatus = Literal["ready", "not_ready"]


class HealthEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    required: bool
    status: EntryStatus
    code: str
    latencyMs: int = Field(ge=0)
    provider: str | None = None
    model: str | None = None


class HealthReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contractVersion: Literal["health/v1"] = "health/v1"
    environment: str
    status: AggregateStatus
    checkedAt: datetime
    components: list[HealthEntry]
    capabilities: list[HealthEntry]

    @classmethod
    def create(
        cls,
        environment: str,
        components: list[HealthEntry],
        capabilities: list[HealthEntry],
    ) -> "HealthReport":
        required_entries = [entry for entry in (*components, *capabilities) if entry.required]
        status: AggregateStatus = "ready" if all(entry.status == "ready" for entry in required_entries) else "not_ready"
        return cls(
            environment=environment,
            status=status,
            checkedAt=datetime.now(timezone.utc),
            components=components,
            capabilities=capabilities,
        )


class LivenessReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contractVersion: Literal["health/v1"] = "health/v1"
    live: Literal[True] = True
    checkedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
