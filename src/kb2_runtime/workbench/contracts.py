from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kb2_runtime.canonical.contracts import Locator


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


class DocumentLatestRun(OverviewContract):
    id: UUID
    state: Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]


class DocumentActions(OverviewContract):
    inspectDocument: bool = False
    sourceArtifactId: UUID | None = None
    outputArtifactId: UUID | None = None


class DocumentListItem(OverviewContract):
    sourceArtifactId: UUID
    filename: str = Field(min_length=1, max_length=255)
    mediaType: str = Field(min_length=1, max_length=128)
    format: str | None = Field(default=None, max_length=32)
    byteSize: int = Field(ge=0)
    documentClass: str | None = Field(default=None, max_length=64)
    profileId: str = Field(min_length=1, max_length=64)
    registeredAt: datetime
    latestRun: DocumentLatestRun | None = None
    actions: DocumentActions


class DocumentPage(OverviewContract):
    limit: int = Field(ge=1, le=50)
    nextCursor: str | None = Field(default=None, max_length=256)


class DocumentList(OverviewContract):
    contractVersion: Literal["workbench-document-list/v1"] = "workbench-document-list/v1"
    items: tuple[DocumentListItem, ...] = Field(max_length=50)
    page: DocumentPage


class DocumentInspectorRun(OverviewContract):
    id: UUID
    state: Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]


class DocumentInspectorSource(OverviewContract):
    id: UUID
    filename: str = Field(min_length=1, max_length=255)
    mediaType: str = Field(min_length=1, max_length=128)
    byteSize: int = Field(ge=0)
    registeredAt: datetime


class DocumentPreview(OverviewContract):
    kind: Literal["pdf", "text", "unavailable"]
    contentUrl: str | None = Field(default=None, max_length=512)
    pageCount: int | None = Field(default=None, ge=0, le=10000)
    reason: str | None = Field(default=None, max_length=64)


class DocumentInspectorTab(OverviewContract):
    id: Literal["canonical", "structure", "tables", "chunks", "metadata", "lineage"]
    state: Literal["available", "unavailable"]
    artifactId: UUID | None = None
    reason: str | None = Field(default=None, max_length=64)


class DocumentInspectorArtifact(OverviewContract):
    id: UUID
    artifactType: str = Field(max_length=64)
    schemaRevision: str = Field(max_length=32)


class DocumentInspectorSummary(OverviewContract):
    contractVersion: Literal["workbench-document-inspector/v1"] = "workbench-document-inspector/v1"
    source: DocumentInspectorSource
    latestRun: DocumentInspectorRun
    preview: DocumentPreview
    tabs: tuple[DocumentInspectorTab, ...] = Field(max_length=6)
    artifacts: dict[Literal["source", "canonical", "chunks"], DocumentInspectorArtifact] = Field(max_length=3)
    metadata: dict[str, str | int | None] = Field(max_length=8)


class DocumentViewPage(OverviewContract):
    limit: int = Field(ge=1, le=128)
    nextCursor: str | None = Field(default=None, max_length=512)


class DocumentViewItemContract(OverviewContract):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class DocumentElementViewItem(DocumentViewItemContract):
    id: str = Field(pattern=r"^[a-z]+_[a-f0-9]{16,64}$")
    kind: Literal["heading", "paragraph", "list", "figure", "caption", "code", "table"]
    readingOrder: int = Field(ge=0)
    parentId: str | None = Field(default=None, pattern=r"^[a-z]+_[a-f0-9]{16,64}$")
    level: int | None = Field(default=None, ge=1, le=9)
    text: str = Field(max_length=2048)
    truncated: bool
    locator: Locator


class DocumentTableCellViewItem(DocumentViewItemContract):
    id: str = Field(pattern=r"^[a-z]+_[a-f0-9]{16,64}$")
    text: str = Field(max_length=2048)
    row: int = Field(ge=0, le=511)
    column: int = Field(ge=0, le=511)
    rowSpan: int = Field(gt=0, le=512)
    columnSpan: int = Field(gt=0, le=512)
    isHeader: bool


class DocumentTableViewItem(DocumentViewItemContract):
    id: str = Field(pattern=r"^[a-z]+_[a-f0-9]{16,64}$")
    elementId: str = Field(pattern=r"^[a-z]+_[a-f0-9]{16,64}$")
    rows: int = Field(gt=0, le=512)
    columns: int = Field(gt=0, le=512)
    locator: Locator
    cellOffset: int = Field(ge=0, le=512 * 512)
    totalCells: int = Field(gt=0, le=512 * 512)
    hasMoreCells: bool
    cells: tuple[DocumentTableCellViewItem, ...] = Field(max_length=512)


class DocumentChunkCitationViewItem(DocumentViewItemContract):
    elementId: str = Field(pattern=r"^[a-z]+_[a-f0-9]{16,64}$")
    locator: Locator


class DocumentChunkViewItem(DocumentViewItemContract):
    id: str = Field(pattern=r"^chk_[a-f0-9]{32}$")
    content: str = Field(min_length=1, max_length=4096)
    truncated: bool
    tokenCount: int = Field(ge=1, le=512)
    sourceElementIds: tuple[str, ...] = Field(min_length=1, max_length=128)
    parentChunkId: str | None = Field(default=None, pattern=r"^chk_[a-f0-9]{32}$")
    childChunkIds: tuple[str, ...] = Field(max_length=64)
    citations: tuple[DocumentChunkCitationViewItem, ...] = Field(min_length=1, max_length=128)


class DocumentLineageViewItem(DocumentViewItemContract):
    id: UUID
    artifactType: str = Field(min_length=1, max_length=64)
    schemaRevision: str = Field(min_length=1, max_length=32)
    producer: str = Field(min_length=1, max_length=64)
    parents: tuple[UUID, ...] = Field(max_length=64)
    summary: str = Field(max_length=1024)


DocumentViewItem = (
    DocumentElementViewItem | DocumentTableViewItem | DocumentChunkViewItem |
    DocumentLineageViewItem
)


class DocumentInspectorView(OverviewContract):
    contractVersion: Literal["workbench-document-view/v1"] = "workbench-document-view/v1"
    view: Literal["canonical", "structure", "tables", "chunks", "lineage"]
    artifactId: UUID
    runId: UUID = Field(exclude=True)
    items: tuple[DocumentViewItem, ...] = Field(max_length=128)
    page: DocumentViewPage

    @model_validator(mode="after")
    def items_match_view(self) -> "DocumentInspectorView":
        expected = {
            "canonical": DocumentElementViewItem,
            "structure": DocumentElementViewItem,
            "tables": DocumentTableViewItem,
            "chunks": DocumentChunkViewItem,
            "lineage": DocumentLineageViewItem,
        }[self.view]
        if any(not isinstance(item, expected) for item in self.items):
            raise ValueError("document view items do not match the selected view")
        return self


# The studio deliberately transports only declarative profile values.  Keeping
# this envelope small prevents it becoming a second execution/request API.
class WorkspaceProfile(OverviewContract):
    profileId: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,47}$")
    kind: Literal["ingestion", "query"]
    document: dict[str, Any] = Field(max_length=64)
    canonicalYaml: str = Field(max_length=64 * 1024)
    documentDigest: str = Field(pattern=r"^[a-f0-9]{64}$")
    updatedAt: datetime


class WorkspaceProfileSummary(OverviewContract):
    profileId: str
    kind: Literal["ingestion", "query"]
    stageCount: int = Field(ge=0, le=128)
    stageSummary: str | None = Field(default=None, max_length=256)
    documentDigest: str = Field(pattern=r"^[a-f0-9]{64}$")
    validationState: Literal["VALID", "INVALID"]
    diagnosticCount: int = Field(ge=0, le=16)
    checkedAt: datetime
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
    canonicalYaml: str | None = Field(default=None, max_length=64 * 1024)
    documentDigest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
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
    implementationDigest: str
    inputSchemas: tuple[str, ...]
    outputSchemas: tuple[str, ...]
    capabilities: tuple[str, ...]
    contractTestState: Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"] | None = None
    contractTestRunId: str | None = None


class RegistryPluginDetail(RegistryPlugin):
    inputPorts: tuple[RegistryPort, ...]
    outputPorts: tuple[RegistryPort, ...]
    configurationSchema: dict[str, Any]
    resourceHints: dict[str, Any]
    timeoutSeconds: float
    safeExample: dict[str, Any]
    contractTests: tuple[dict[str, Any], ...] = ()
    recentRuns: tuple[dict[str, Any], ...] = ()
