"""Bounded document submission and inspection projections for the workbench.

This module deliberately keeps uploads and cancellation ownership process-local.
The ingestion engine remains the sole owner of plan creation and execution.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
from datetime import datetime, timezone
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID, uuid4

from kb2_runtime.ingestion_engine import IngestionEngine, SourceSubmission
from kb2_runtime.ingestion_profiles import ProfileCompiler, ProfileParser, ProfileResolver, ResolutionRequest
from kb2_runtime.ingestion_profiles.errors import ProfileError
from kb2_runtime.plugins.registry import PluginRegistry
from kb2_runtime.trace.contracts import DocumentSubmissionCursor
from kb2_runtime.trace.errors import TraceError
from kb2_runtime.trace.repositories import TraceRepository
from kb2_runtime.trace.service import ArtifactService, RunService
from .contracts import DocumentActions, DocumentLatestRun, DocumentList, DocumentListItem, DocumentPage


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
