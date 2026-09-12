from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
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


# The studio deliberately transports only declarative profile values.  Keeping
# this envelope small prevents it becoming a second execution/request API.
class WorkspaceProfile(OverviewContract):
    profileId: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}$")
    kind: Literal["ingestion", "query"]
    document: dict[str, Any] = Field(max_length=64)
    updatedAt: datetime


class WorkspaceProfileSummary(OverviewContract):
    profileId: str
    kind: Literal["ingestion", "query"]
    updatedAt: datetime


class ProfileRequest(OverviewContract):
    kind: Literal["ingestion", "query"]
    document: dict[str, Any] | None = Field(default=None, max_length=64)
    source: str | None = Field(default=None, max_length=64 * 1024)
    mediaType: Literal["application/json", "application/yaml"] = "application/json"
    searchArtifact: dict[str, Any] | None = Field(default=None, max_length=8)


class StudioDiagnostic(OverviewContract):
    code: str = Field(pattern=r"^[A-Z_]{3,64}$")
    location: str = Field(pattern=r"^/")


class ProfileValidation(OverviewContract):
    valid: bool
    normalizedDocument: dict[str, Any] | None = None
    diagnostics: tuple[StudioDiagnostic, ...] = Field(default_factory=tuple, max_length=16)
    resolvedPlan: dict[str, Any] | None = None
    planDigest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class DryRunRequest(OverviewContract):
    kind: Literal["ingestion", "query"]
    questionArtifactId: str | None = Field(default=None, pattern=r"^[0-9a-fA-F-]{36}$")
    searchArtifact: dict[str, Any] | None = Field(default=None, max_length=8)


class CompatibilityRequest(ProfileRequest):
    stageId: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,95}$")


class DryRunReceipt(OverviewContract):
    runId: str
    profileId: str
    planDigest: str = Field(pattern=r"^[a-f0-9]{64}$")


class RegistryPort(OverviewContract):
    name: str
    artifactType: str
    schemaRevision: str
    minItems: int
    maxItems: int


class RegistryPlugin(OverviewContract):
    pluginId: str
    kind: str
    runner: str
    runnable: bool
    reason: str | None = None


class RegistryPluginDetail(RegistryPlugin):
    implementationDigest: str
    inputPorts: tuple[RegistryPort, ...]
    outputPorts: tuple[RegistryPort, ...]
    configurationSchema: dict[str, Any]
    capabilities: tuple[str, ...]
    resourceHints: dict[str, Any]
    timeoutSeconds: float
    safeExample: dict[str, Any]
    contractTests: tuple[dict[str, Any], ...] = ()
    recentRuns: tuple[dict[str, Any], ...] = ()
