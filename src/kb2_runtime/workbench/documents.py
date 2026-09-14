"""Bounded document submission and inspection projections for the workbench.

This module deliberately keeps uploads and cancellation ownership process-local.
The ingestion engine remains the sole owner of plan creation and execution.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
from datetime import datetime, timezone
import hmac
import json
from io import BytesIO
import secrets
import time
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID, uuid4

from kb2_runtime.ingestion_engine import IngestionEngine, SourceSubmission
from kb2_runtime.canonical.contracts import CanonicalDocument
from kb2_runtime.chunking.contracts import ChunkSet
from kb2_runtime.ingestion_profiles import ProfileCompiler, ProfileParser, ProfileResolver, ResolutionRequest
from kb2_runtime.ingestion_profiles.errors import ProfileError
from kb2_runtime.plugins.registry import PluginRegistry
from kb2_runtime.trace.contracts import DocumentSubmissionCursor
from kb2_runtime.trace.errors import TraceError
from kb2_runtime.trace.repositories import TraceRepository
from kb2_runtime.trace.service import ArtifactService, RunService
from .contracts import (
    DocumentActions, DocumentInspectorArtifact, DocumentInspectorRun,
    DocumentInspectorSource, DocumentInspectorSummary, DocumentInspectorTab,
    DocumentChunkCitationViewItem, DocumentChunkViewItem, DocumentElementViewItem,
    DocumentInspectorView, DocumentLatestRun, DocumentLineageViewItem, DocumentList,
    DocumentListItem, DocumentPage, DocumentPreview, DocumentTableCellViewItem,
    DocumentTableViewItem, DocumentViewPage,
)


class ProfileReader(Protocol):
    async def get_profile(self, profile_id: str) -> Any: ...


@dataclass
class _Preflight:
    content: bytes
    filename: str
    media_type: str
    workspace_profile_id: str
    expires_at: float
    automatic: dict[str, Any]
    selected_profile_id: str
    plan_digest: str
    disclosure: dict[str, Any]


class DocumentWorkbenchService:
    """Safe workbench facade over saved Profiles, traces, and Artifacts."""

    def __init__(self, profiles: ProfileReader, registry: PluginRegistry, engine: IngestionEngine,
                 runs: RunService, artifacts: ArtifactService, *, ttl_seconds: int = 300,
                 external_capabilities: frozenset[str] = frozenset(), repository: TraceRepository | None = None) -> None:
        self._profiles, self._registry, self._engine = profiles, registry, engine
        self._runs, self._artifacts, self._ttl = runs, artifacts, ttl_seconds
        self._preflights: dict[str, _Preflight] = {}
        self._jobs: dict[UUID, asyncio.Event] = {}
        self._view_cursor_key = secrets.token_bytes(32)
        self._external_capabilities = external_capabilities
        self._repository = repository or getattr(artifacts, "repository", None)

    async def documents_page(self, limit: int = 25, cursor: str | None = None) -> DocumentList:
        if not 1 <= limit <= 50:
            raise ValueError("DOCUMENT_PAGE_INVALID")
        if self._repository is None:
            raise RuntimeError("DOCUMENT_LIST_UNAVAILABLE")
        position = self._decode_cursor(cursor) if cursor else None
        rows, next_position = await self._repository.list_document_submissions(limit, position)
        items = tuple(DocumentListItem(
            sourceArtifactId=row.source_artifact_id,
            filename=row.display_filename,
            mediaType=row.media_type,
            format=row.format,
            byteSize=row.byte_size,
            documentClass=row.document_class,
            profileId=row.profile_id,
            registeredAt=row.registered_at,
            latestRun=DocumentLatestRun(id=row.run_id, state=row.run_state.value),
            actions=DocumentActions(
                inspectDocument=True,
                sourceArtifactId=row.source_artifact_id,
                outputArtifactId=row.output_artifact_id,
            ),
        ) for row in rows)
        return DocumentList(
            items=items,
            page=DocumentPage(limit=limit, nextCursor=self._encode_cursor(next_position) if next_position else None),
        )

    @staticmethod
    def _encode_cursor(cursor: DocumentSubmissionCursor) -> str:
        timestamp = cursor.registered_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        raw = json.dumps([1, timestamp, str(cursor.source_artifact_id)], separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(value: str) -> DocumentSubmissionCursor:
        if not value or len(value) > 256:
            raise ValueError("DOCUMENT_CURSOR_INVALID")
        try:
            raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
            payload = json.loads(raw)
            if not isinstance(payload, list) or len(payload) != 3 or payload[0] != 1:
                raise ValueError
            timestamp = datetime.fromisoformat(str(payload[1]).replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError
            return DocumentSubmissionCursor(registered_at=timestamp, source_artifact_id=UUID(str(payload[2])))
        except (ValueError, TypeError, json.JSONDecodeError, binascii.Error):
            raise ValueError("DOCUMENT_CURSOR_INVALID") from None

    async def preflight(self, content: bytes, filename: str, media_type: str, profile_id: str,
                        replaces_token: str | None = None) -> dict[str, Any]:
        self.discard_preflight(replaces_token)
        if not content or len(content) > 16 * 1024 * 1024 or len(filename) > 255 or len(media_type) > 128:
            raise ValueError("PREFLIGHT_INVALID")
        _, request, record = await self._resolve(profile_id, content, filename, media_type)
        automatic = self._resolution(record)
        return self._preview(content, filename, media_type, profile_id, request, record, automatic,
                             time.monotonic() + self._ttl)

    def discard_preflight(self, token: str | None) -> None:
        if token:
            self._preflights.pop(token, None)

    async def document_inspector(self, source_id: UUID) -> DocumentInspectorSummary | None:
        row, manifests = await self._document_context(source_id)
        if row is None:
            return None
        source = next((item for item in manifests if item.id == source_id), None)
        if source is None:
            raise RuntimeError("DOCUMENT_INSPECTOR_UNAVAILABLE")
        canonical = self._last_schema(manifests, "canonical.document", "v1")
        chunks = self._last_schema(manifests, "chunk.set", "v1")
        preview = await self._preview_contract(row, source)
        canonical_reason = self._missing_view_reason(row.run_state.value, "CANONICAL_UNAVAILABLE")
        chunks_reason = self._missing_view_reason(row.run_state.value, "CHUNKSET_UNAVAILABLE")
        tabs = (
            DocumentInspectorTab(id="canonical", state="available" if canonical else "unavailable",
                                 artifactId=canonical.id if canonical else None,
                                 reason=None if canonical else canonical_reason),
            DocumentInspectorTab(id="structure", state="available" if canonical else "unavailable",
                                 artifactId=canonical.id if canonical else None,
                                 reason=None if canonical else canonical_reason),
            DocumentInspectorTab(id="tables", state="available" if canonical else "unavailable",
                                 artifactId=canonical.id if canonical else None,
                                 reason=None if canonical else canonical_reason),
            DocumentInspectorTab(id="chunks", state="available" if chunks else "unavailable",
                                 artifactId=chunks.id if chunks else None,
                                 reason=None if chunks else chunks_reason),
            DocumentInspectorTab(id="metadata", state="available"),
            DocumentInspectorTab(id="lineage", state="available"),
        )
        artifacts = {"source": self._inspector_artifact(source)}
        if canonical:
            artifacts["canonical"] = self._inspector_artifact(canonical)
        if chunks:
            artifacts["chunks"] = self._inspector_artifact(chunks)
        return DocumentInspectorSummary(
            source=DocumentInspectorSource(id=source_id, filename=row.display_filename,
                                           mediaType=row.media_type, byteSize=row.byte_size,
                                           registeredAt=row.registered_at),
            latestRun=DocumentInspectorRun(id=row.run_id, state=row.run_state.value),
            preview=preview, tabs=tabs, artifacts=artifacts,
            metadata={"format": row.format, "documentClass": row.document_class,
                      "profileId": row.profile_id, "mediaType": row.media_type,
                      "byteSize": row.byte_size},
        )

    async def document_view(self, source_id: UUID, view: str, limit: int | None = None,
                            cursor: str | None = None) -> DocumentInspectorView:
        limits = {"canonical": (50, 100), "structure": (50, 100), "tables": (10, 20),
                  "chunks": (25, 50), "lineage": (50, 128)}
        if view not in limits:
            raise ValueError("DOCUMENT_VIEW_INVALID")
        limit = limits[view][0] if limit is None else limit
        if not 1 <= limit <= limits[view][1]:
            raise ValueError("DOCUMENT_VIEW_INVALID")
        row, manifests = await self._document_context(source_id)
        if row is None:
            raise LookupError("DOCUMENT_NOT_FOUND")
        selected = (self._last_schema(manifests, "chunk.set", "v1") if view == "chunks" else
                    self._last_schema(manifests, "canonical.document", "v1") if view != "lineage" else
                    next((item for item in manifests if item.id == source_id), None))
        if selected is None:
            raise PermissionError("DOCUMENT_VIEW_UNAVAILABLE")
        position = self._decode_view_cursor(cursor, source_id, selected.id, view) if cursor else (0, 0)
        offset, cell_offset = position
        if view == "lineage":
            values = [self._lineage_item(item) for item in manifests]
        else:
            if selected.byte_size > 64 * 1024 * 1024:
                raise OverflowError("DOCUMENT_VIEW_TOO_LARGE")
            try:
                raw = await self._artifacts.read_content(selected.id)
                if view in {"canonical", "structure", "tables"}:
                    document = CanonicalDocument.model_validate_json(raw)
                    if view == "tables":
                        values = list(document.tables)
                    else:
                        values = [self._element_item(item) for item in document.elements]
                else:
                    chunk_set = ChunkSet.model_validate_json(raw)
                    values = [self._chunk_item(item) for item in chunk_set.chunks]
            except (TraceError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
                raise PermissionError("DOCUMENT_VIEW_UNAVAILABLE") from None
        if offset < 0 or offset > len(values):
            raise ValueError("DOCUMENT_VIEW_INVALID")
        if view == "tables":
            if offset == len(values) and cell_offset != 0:
                raise ValueError("DOCUMENT_VIEW_INVALID")
            if offset < len(values) and not 0 <= cell_offset < len(values[offset].cells):
                raise ValueError("DOCUMENT_VIEW_INVALID")
            page, next_position = self._table_page(values, offset, cell_offset, limit)
            next_cursor = (
                self._encode_view_cursor(source_id, selected.id, view, *next_position)
                if next_position is not None else None
            )
        else:
            if cell_offset != 0:
                raise ValueError("DOCUMENT_VIEW_INVALID")
            page = values[offset:offset + limit]
            next_offset = offset + len(page)
            next_cursor = (
                self._encode_view_cursor(source_id, selected.id, view, next_offset)
                if next_offset < len(values) else None
            )
        return DocumentInspectorView(view=view, artifactId=selected.id, runId=row.run_id, items=tuple(page),
                                     page=DocumentViewPage(limit=limit, nextCursor=next_cursor))

    async def document_content(self, source_id: UUID) -> tuple[str, bytes, str, UUID]:
        row, manifests = await self._document_context(source_id)
        if row is None:
            raise LookupError("DOCUMENT_NOT_FOUND")
        source = next((item for item in manifests if item.id == source_id), None)
        if source is None:
            raise LookupError("SOURCE_CONTENT_UNAVAILABLE")
        content = await self._artifacts.read_content(source_id)
        if row.media_type == "application/pdf" and content.startswith(b"%PDF-"):
            try:
                from pypdf import PdfReader
                pages = len(PdfReader(BytesIO(content)).pages)
                if pages > 10000:
                    raise ValueError
            except Exception:
                raise TypeError("PREVIEW_FORMAT_UNAVAILABLE") from None
            return row.media_type, content, row.display_filename, row.run_id
        if row.media_type.startswith("text/"):
            try:
                text = content[:256 * 1024].decode("utf-8")
            except UnicodeDecodeError:
                raise TypeError("PREVIEW_FORMAT_UNAVAILABLE") from None
            return "text/plain; charset=utf-8", text.encode(), row.display_filename, row.run_id
        raise TypeError("PREVIEW_FORMAT_UNAVAILABLE")

    async def _document_context(self, source_id: UUID):
        if self._repository is None:
            raise RuntimeError("DOCUMENT_INSPECTOR_UNAVAILABLE")
        rows = await self._repository.get_document_submissions_by_source_ids((source_id,), limit=1)
        if not rows:
            return None, ()
        row = rows[0]
        manifests = await self._repository.list_document_artifact_manifests(source_id, row.run_id, limit=128)
        return row, manifests

    async def _preview_contract(self, row: Any, source: Any) -> DocumentPreview:
        if row.media_type == "application/pdf":
            try:
                content = await self._artifacts.read_content(source.id)
                from pypdf import PdfReader
                page_count = len(PdfReader(BytesIO(content)).pages)
                if page_count > 10000:
                    raise ValueError
                return DocumentPreview(kind="pdf", contentUrl=f"/api/workbench/documents/{source.id}/content",
                                       pageCount=page_count)
            except Exception:
                return DocumentPreview(kind="unavailable", reason="SOURCE_PREVIEW_UNAVAILABLE")
        if row.media_type.startswith("text/"):
            return DocumentPreview(kind="text", contentUrl=f"/api/workbench/documents/{source.id}/content")
        return DocumentPreview(kind="unavailable", reason="SOURCE_PREVIEW_UNAVAILABLE")

    @staticmethod
    def _last_schema(manifests: tuple[Any, ...], kind: str, revision: str):
        return next((item for item in reversed(manifests)
                     if (item.artifact_type, item.schema_revision) == (kind, revision)), None)

    @staticmethod
    def _missing_view_reason(state: str, fallback: str) -> str:
        return "RUN_IN_PROGRESS" if state in {"PENDING", "RUNNING"} else fallback

    @staticmethod
    def _inspector_artifact(item: Any) -> DocumentInspectorArtifact:
        return DocumentInspectorArtifact(id=item.id, artifactType=item.artifact_type,
                                         schemaRevision=item.schema_revision)

    @staticmethod
    def _element_item(item: Any) -> DocumentElementViewItem:
        text = item.text or item.alt_text or " ".join(x.text for x in (item.items or ()))
        return DocumentElementViewItem(
            id=item.id, kind=item.kind, readingOrder=item.reading_order,
            parentId=item.parent_id, level=item.level, text=text[:2048],
            truncated=len(text) > 2048, locator=item.locator,
        )

    @staticmethod
    def _table_item(item: Any, cell_offset: int = 0, cell_limit: int = 512) -> DocumentTableViewItem:
        end = min(len(item.cells), cell_offset + cell_limit)
        return DocumentTableViewItem(
            id=item.id, elementId=item.element_id, rows=item.rows, columns=item.columns,
            locator=item.locator, cellOffset=cell_offset, totalCells=len(item.cells),
            hasMoreCells=end < len(item.cells),
            cells=tuple(DocumentTableCellViewItem(
                id=cell.id, text=cell.text[:2048], row=cell.row, column=cell.column,
                rowSpan=cell.row_span, columnSpan=cell.column_span, isHeader=cell.is_header,
            ) for cell in item.cells[cell_offset:end]),
        )

    @classmethod
    def _table_page(cls, tables: list[Any], table_offset: int, cell_offset: int,
                    table_limit: int) -> tuple[list[DocumentTableViewItem], tuple[int, int] | None]:
        page: list[DocumentTableViewItem] = []
        cell_budget = 512
        index = table_offset
        current_cell_offset = cell_offset
        while index < len(tables) and len(page) < table_limit and cell_budget:
            table = tables[index]
            remaining = len(table.cells) - current_cell_offset
            take = min(remaining, cell_budget)
            page.append(cls._table_item(table, current_cell_offset, take))
            cell_budget -= take
            next_cell_offset = current_cell_offset + take
            if next_cell_offset < len(table.cells):
                return page, (index, next_cell_offset)
            index += 1
            current_cell_offset = 0
        return page, (index, 0) if index < len(tables) else None

    @staticmethod
    def _chunk_item(item: Any) -> DocumentChunkViewItem:
        content = item.content[:4096]
        return DocumentChunkViewItem(
            id=item.chunk_id, content=content, truncated=len(item.content) > len(content),
            tokenCount=item.token_count, sourceElementIds=item.source_element_ids,
            parentChunkId=item.parent_chunk_id, childChunkIds=item.child_chunk_ids,
            citations=tuple(DocumentChunkCitationViewItem(
                elementId=citation.element_id, locator=citation.locator,
            ) for citation in item.citations),
        )

    @staticmethod
    def _lineage_item(item: Any) -> DocumentLineageViewItem:
        return DocumentLineageViewItem(
            id=item.id, artifactType=item.artifact_type,
            schemaRevision=item.schema_revision, producer=item.producing_plugin_id,
            parents=item.parent_artifact_ids, summary=item.summary,
        )

    def _encode_view_cursor(self, source_id: UUID, artifact_id: UUID, view: str, offset: int,
                            cell_offset: int = 0) -> str:
        payload = json.dumps(
            [2, str(source_id), str(artifact_id), view, offset, cell_offset],
            separators=(",", ":"),
        ).encode()
        signature = hmac.digest(self._view_cursor_key, payload, "sha256")
        return base64.urlsafe_b64encode(payload + b"." + signature).decode().rstrip("=")

    def _decode_view_cursor(self, value: str, source_id: UUID, artifact_id: UUID,
                            view: str) -> tuple[int, int]:
        if not value or len(value) > 512:
            raise ValueError("DOCUMENT_VIEW_INVALID")
        try:
            raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
            if len(raw) <= 33 or raw[-33:-32] != b".":
                raise ValueError
            encoded, signature = raw[:-33], raw[-32:]
            if not hmac.compare_digest(signature, hmac.digest(self._view_cursor_key, encoded, "sha256")):
                raise ValueError
            payload = json.loads(encoded)
            if (not isinstance(payload, list) or len(payload) != 6 or payload[:4] !=
                    [2, str(source_id), str(artifact_id), view] or
                    type(payload[4]) is not int or type(payload[5]) is not int):
                raise ValueError
            return payload[4], payload[5]
        except (ValueError, TypeError, json.JSONDecodeError, binascii.Error):
            raise ValueError("DOCUMENT_VIEW_INVALID") from None

    async def select_candidate(self, token: str, profile_id: str) -> dict[str, Any]:
        item = self._claim_preflight(token)
        if profile_id not in item.automatic["candidateProfileIds"]:
            raise ValueError("PREFLIGHT_SELECTION_INVALID")
        _, request, record = await self._resolve(
            item.workspace_profile_id, item.content, item.filename, item.media_type,
            explicit_profile_id=profile_id,
        )
        return self._preview(
            item.content, item.filename, item.media_type, item.workspace_profile_id,
            request, record, item.automatic, item.expires_at,
        )

    def _preview(self, content: bytes, filename: str, media_type: str, workspace_profile_id: str,
                 request: ResolutionRequest, record: Any, automatic: dict[str, Any],
                 expires_at: float) -> dict[str, Any]:
        token = uuid4().hex
        stages = self._stages(record.plan.canonical_payload)
        disclosure = self._disclosure(stages)
        self._preflights[token] = _Preflight(
            content, filename, media_type, workspace_profile_id, expires_at, automatic,
            record.selected_profile_id, record.plan.digest, disclosure,
        )
        return {"contractVersion": "workbench-document-preflight/v1", "token": token,
                "workspaceProfileId": workspace_profile_id,
                "detected": request.observables(), "automatic": automatic,
                "selection": {"profileId": record.selected_profile_id, "selectionTier": record.selection_tier},
                "planDigest": record.plan.digest, "stages": stages,
                "disclosure": disclosure}

    def _claim_preflight(self, token: str) -> _Preflight:
        item = self._preflights.pop(token, None)
        if item is None or item.expires_at < time.monotonic():
            raise LookupError("PREFLIGHT_UNAVAILABLE")
        return item

    async def submit(self, token: str, profile_id: str | None, acknowledge_external: bool) -> dict[str, Any]:
        item = self._preflights.get(token)
        if item is None or item.expires_at < time.monotonic():
            self._preflights.pop(token, None)
            raise LookupError("PREFLIGHT_UNAVAILABLE")
        selected = profile_id or item.selected_profile_id
        if selected != item.selected_profile_id:
            raise PermissionError("PREFLIGHT_SELECTION_MISMATCH")
        try:
            compiled, request, record = await self._resolve(item.workspace_profile_id, item.content, item.filename, item.media_type, explicit_profile_id=selected)
        except (LookupError, ValueError, ProfileError):
            self._preflights.pop(token, None)
            raise PermissionError("PREFLIGHT_STALE") from None
        stages = self._stages(record.plan.canonical_payload)
        disclosure = self._disclosure(stages)
        if record.plan.digest != item.plan_digest or disclosure != item.disclosure:
            self._preflights.pop(token, None)
            raise PermissionError("PREFLIGHT_STALE")
        if disclosure["externalStages"] and not acknowledge_external:
            raise PermissionError("EXTERNAL_DISCLOSURE_REQUIRED")
        # A rejected disclosure acknowledgement does not consume a preflight;
        # successful confirmation consumes it before a new immutable Run starts.
        if self._preflights.pop(token, None) is not item:
            raise LookupError("PREFLIGHT_UNAVAILABLE")
        cancellation = asyncio.Event()

        created: asyncio.Future[UUID] = asyncio.get_running_loop().create_future()
        def on_created(run_id: UUID) -> None:
            if not created.done():
                created.set_result(run_id)
        task = asyncio.create_task(self._engine.submit(
            compiled,
            SourceSubmission(content=item.content, source_schema={"artifact_type": "opaque.bytes", "schema_revision": "v1"}, filename=item.filename, media_type=item.media_type),
            request, cancellation, on_created,
        ))
        done, _ = await asyncio.wait({created, task}, return_when=asyncio.FIRST_COMPLETED)
        if task in done and not created.done():
            try:
                task.result()
            except Exception:
                raise RuntimeError("INGESTION_SUBMISSION_UNAVAILABLE") from None
            raise RuntimeError("INGESTION_SUBMISSION_UNAVAILABLE")
        run_id = created.result()
        self._jobs[run_id] = cancellation
        task.add_done_callback(lambda _: self._jobs.pop(run_id, None))
        return {"contractVersion": "workbench-ingestion-receipt/v1", "runId": str(run_id), "profileId": record.selected_profile_id, "planDigest": record.plan.digest}

    async def run(self, run_id: UUID) -> dict[str, Any] | None:
        trace = await self._runs.get_run_trace(run_id)
        if trace is None or trace.engine_kind.value != "ingestion":
            return None
        plan = await self._runs.get_run_plan(run_id)
        stages = []
        for row in trace.stages:
            selection = next((x.value for x in row.quality_signals if x.name == "engine.candidate-selection"), None)
            plugin_id = self._planned_plugin(plan, row.stage_key)
            stages.append({"id": str(row.id), "stageKey": row.stage_key, "attempt": row.attempt_number,
                           "state": row.state.value, "result": row.result.value if row.result else None,
                           "startedAt": row.started_at, "endedAt": row.ended_at, "summary": row.summary,
                           "pluginId": plugin_id, "selection": selection, "inputs": [self._artifact(x) for x in row.inputs],
                           "outputs": [self._artifact(x) for x in row.outputs],
                           "metrics": [x.model_dump(mode="json") for x in row.metrics],
                           "quality": [x.model_dump(mode="json") for x in row.quality_signals],
                           "failure": row.safe_error.model_dump(mode="json") if row.safe_error else None})
        active = run_id in self._jobs
        return {"contractVersion": "workbench-ingestion-run/v1", "id": str(trace.id), "state": trace.state.value,
                "terminalState": trace.terminal_state.value if trace.terminal_state else None, "planDigest": trace.plan_digest,
                "createdAt": trace.created_at, "startedAt": trace.started_at, "endedAt": trace.ended_at,
                "resolution": trace.ingestion_evidence.model_dump(mode="json") if trace.ingestion_evidence else None,
                "stages": stages, "metrics": [x.model_dump(mode="json") for x in trace.metrics],
                "quality": [x.model_dump(mode="json") for x in trace.quality_signals],
                "actions": {"stop": active and trace.state.value in {"PENDING", "RUNNING"}, "rerun": True,
                            "artifact": any(row.outputs for row in trace.stages)}}

    async def stop(self, run_id: UUID) -> bool:
        event = self._jobs.get(run_id)
        if event is None:
            return False
        event.set()
        return True

    async def rerun_preflight(self, run_id: UUID, workspace_profile_id: str) -> dict[str, Any]:
        """Materialize the immutable source Artifact into a fresh preflight.

        The old Run is read-only: this operation creates neither a replay nor a
        mutation of its pinned plan. The returned token must complete fresh
        Profile resolution and normal confirmation before a new Run exists.
        """
        trace = await self._runs.get_run_trace(run_id)
        if trace is None or trace.engine_kind.value != "ingestion":
            raise LookupError("INGESTION_RUN_NOT_FOUND")
        source = next((item for item in trace.stages if item.stage_key == "ingestion.source" and item.outputs), None)
        if source is None:
            raise LookupError("RERUN_SOURCE_UNAVAILABLE")
        artifact_id = source.outputs[0].id
        manifest = await self._artifacts.get_artifact_manifest(artifact_id)
        if manifest is None or (manifest.artifact_type, manifest.schema_revision) != ("opaque.bytes", "v1"):
            raise LookupError("RERUN_SOURCE_UNAVAILABLE")
        result = await self.preflight(await self._artifacts.read_content(artifact_id), f"artifact-{artifact_id}.bin", "application/octet-stream", workspace_profile_id)
        result["sourceArtifactId"] = str(artifact_id)
        return result

    async def artifact(self, artifact_id: UUID) -> dict[str, Any] | None:
        manifest = await self._artifacts.get_artifact_manifest(artifact_id)
        if manifest is None:
            return None
        base = {"id": str(manifest.id), "artifactType": manifest.artifact_type, "schemaRevision": manifest.schema_revision,
                "contentDigest": manifest.content_digest, "byteSize": manifest.byte_size, "summary": manifest.summary,
                "producer": {"runId": str(manifest.producing_run_id), "pluginId": manifest.producing_plugin_id},
                "parents": [str(x) for x in manifest.parent_artifact_ids], "metrics": [x.model_dump(mode="json") for x in manifest.metrics],
                "quality": [x.model_dump(mode="json") for x in manifest.quality_signals]}
        try:
            content = await self._artifacts.read_content(artifact_id)
            view = self._artifact_view(manifest.artifact_type, manifest.schema_revision, content)
        except (TraceError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            view = {"available": False, "reason": "ARTIFACT_CONTENT_UNAVAILABLE", "tabs": ["metadata", "lineage"]}
        return {"contractVersion": "workbench-artifact-inspector/v1", **base, "view": view}

    async def _compiled(self, profile_id: str):
        saved = await self._profiles.get_profile(profile_id)
        if saved is None or saved.kind != "ingestion":
            raise LookupError("INGESTION_PROFILE_NOT_FOUND")
        return ProfileCompiler(self._registry).compile(ProfileParser.parse(json.dumps(saved.document), "application/json"))

    async def _resolve(self, workspace_profile_id: str, content: bytes, filename: str, media_type: str, explicit_profile_id: str | None = None):
        compiled = await self._compiled(workspace_profile_id)
        lower = filename.lower()
        extension = lower.rsplit(".", 1)[-1] if "." in lower else ""
        pdf = content.startswith(b"%PDF-")
        request = ResolutionRequest(media_type=media_type, extension=extension, byte_size=len(content), has_embedded_text=pdf,
                                    explicit_profile_id=explicit_profile_id)
        record = ProfileResolver().resolve(compiled, request)
        return compiled, request, record

    @staticmethod
    def _resolution(record: Any) -> dict[str, Any]:
        return {"candidateProfileIds": list(record.candidate_profile_ids), "evaluatedRules": list(record.evaluated_rules),
                "selectedProfileId": record.selected_profile_id, "selectionTier": record.selection_tier}

    def _stages(self, plan: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"key": f"{axis['axis']}.{sub['stage_id']}", "candidates": [
            {"pluginId": candidate["plugin_id"], "capabilities": list(self._registry.get(candidate["plugin_id"]).descriptor.capabilities)}
            for candidate in sub["candidates"]]} for axis in plan["stages"] for sub in axis["sub_stages"]]

    @staticmethod
    def _planned_plugin(plan: dict[str, Any] | None, stage_key: str) -> str | None:
        if stage_key == "ingestion.source":
            return "ingestion.source@1"
        if not isinstance(plan, dict):
            return None
        prefix, marker, number = stage_key.rpartition(".candidate-")
        if not marker or not number.isdigit():
            return None
        try:
            candidate_index = int(number) - 1
            axis, sub_stage = prefix.split(".", 1)
            stage = next(item for item in plan.get("stages", []) if item.get("axis") == axis)
            sub = next(item for item in stage.get("sub_stages", []) if item.get("stage_id") == sub_stage)
            candidate = sub["candidates"][candidate_index]
            return candidate["plugin_id"] if isinstance(candidate.get("plugin_id"), str) else None
        except (IndexError, KeyError, StopIteration, ValueError, AttributeError):
            return None

    def _disclosure(self, stages: list[dict[str, Any]]) -> dict[str, Any]:
        # Capability labels are a server-owned boundary. Current ingestion
        # plugins are local; future externally-backed labels must be explicit.
        external = [{"stage": stage["key"], "pluginId": candidate["pluginId"], "capability": capability,
                     "message": "文档内容可能发送到该外部提供方。"}
                    for stage in stages for candidate in stage["candidates"] for capability in candidate["capabilities"]
                    if capability in self._external_capabilities]
        return {"externalStages": external, "localPersistence": "提交后内容作为本地 Artifact 持久化。"}

    @staticmethod
    def _artifact(item: Any) -> dict[str, Any]:
        return {"id": str(item.id), "artifactType": item.artifact_type, "schemaRevision": item.schema_revision,
                "contentDigest": item.content_digest, "byteSize": item.byte_size, "summary": item.summary}

    @staticmethod
    def _artifact_view(kind: str, revision: str, content: bytes) -> dict[str, Any]:
        if (kind, revision) == ("opaque.bytes", "v1"):
            try:
                text = content.decode("utf-8")[:16_384]
            except UnicodeDecodeError:
                return {"available": False, "reason": "RAW_PREVIEW_UNAVAILABLE", "tabs": ["metadata", "lineage"]}
            return {"available": True, "tabs": ["raw", "metadata", "lineage"], "rawText": text}
        if (kind, revision) not in {("canonical.document", "v1"), ("chunk.set", "v1")}:
            return {"available": True, "tabs": ["metadata", "lineage"]}
        value = json.loads(content)
        if not isinstance(value, dict):
            raise ValueError("not object")
        if kind == "canonical.document":
            elements = value.get("elements", [])
            return {"available": True, "tabs": ["canonical", "tree", "table", "metadata", "lineage"],
                    "elements": [{"id": x.get("id"), "type": x.get("kind", x.get("type")), "locator": x.get("locator"), "text": (x.get("text") or "")[:2048]} for x in elements if isinstance(x, dict)],
                    "tables": [{"id": x.get("id"), "elementId": x.get("element_id"), "locator": x.get("locator"), "cells": x.get("cells", [])}
                               for x in value.get("tables", []) if isinstance(x, dict)]}
        chunks = value.get("chunks", [])
        return {"available": True, "tabs": ["chunks", "metadata", "lineage"],
                "chunks": [{"id": x.get("chunk_id"), "sourceElementIds": x.get("source_element_ids", []),
                            "citations": [{"elementId": citation.get("element_id"), "locator": citation.get("locator")}
                                          for citation in x.get("citations", []) if isinstance(citation, dict)],
                            "text": (x.get("content") or "")[:2048]}
                           for x in chunks if isinstance(x, dict)]}
