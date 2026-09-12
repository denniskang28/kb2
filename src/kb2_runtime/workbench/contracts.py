from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OverviewContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OverviewComponent(OverviewContract):
    id: str
    status: Literal["ready", "unavailable", "not_configured", "not_probed"]
    code: str


class OverviewCapability(OverviewComponent):
    provider: str | None = None
    model: str | None = None
    latencyMs: int = Field(ge=0)


class OverviewPlugin(OverviewContract):
    pluginId: str
    runnable: bool
    reason: Literal["RUNNER_UNAVAILABLE", "CAPABILITY_UNAVAILABLE"] | None = None


class OverviewFailure(OverviewContract):
    code: str
    retryable: bool


class OverviewRun(OverviewContract):
    id: UUID
    engineKind: Literal["ingestion", "query", "evaluation"]
    state: Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]
    terminalState: Literal["SUCCEEDED", "FAILED"] | None = None
    createdAt: datetime
    startedAt: datetime | None = None
    endedAt: datetime | None = None
    planDigest: str = Field(pattern=r"^[a-f0-9]{64}$")
    failure: OverviewFailure | None = None


class OverviewComparison(OverviewContract):
    artifactId: UUID
    runId: UUID
    createdAt: datetime
    mode: str = Field(max_length=64)
    axis: str | None = Field(default=None, max_length=64)
    recommendation: str = Field(max_length=256)


class WorkbenchOverview(OverviewContract):
    contractVersion: Literal["workbench-overview/v1"] = "workbench-overview/v1"
    checkedAt: datetime
    coreStatus: Literal["ready", "not_ready"]
    core: tuple[OverviewComponent, ...]
    optionalCapabilities: tuple[OverviewCapability, ...]
    plugins: tuple[OverviewPlugin, ...]
    activeRunCount: int = Field(ge=0)
    recentRuns: tuple[OverviewRun, ...] = Field(max_length=8)
    recentComparisons: tuple[OverviewComparison, ...] = Field(max_length=4)
