from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from kb2_runtime.api import create_app
from kb2_runtime.config import CapabilityCatalog, Settings
from kb2_runtime.workbench.documents import DocumentWorkbenchService
from kb2_runtime.plugins.registry import PluginRegistration
from kb2_runtime.canonical.contracts import ProviderFixture
from kb2_runtime.canonical.normalizer import normalize_fixture
from kb2_runtime.trace.contracts import ArtifactManifest, DocumentSubmissionCursor, DocumentSubmissionRecord, RunState
from tests.contract.test_ingestion_engine import profile, registry
from tests.contract.test_canonical_document import fixture as canonical_fixture


class _Profiles:
    async def get_profile(self, profile_id: str):
        return SimpleNamespace(kind="ingestion", document=profile(profile_id=profile_id)) if profile_id == "complete" else None


def _service() -> DocumentWorkbenchService:
    # Preflight does not invoke the engine; these sentinels make that boundary
    # explicit and keep the contract test deterministic.
    return DocumentWorkbenchService(_Profiles(), registry(), object(), object(), object())  # type: ignore[arg-type]


class _CandidateProfiles:
    def __init__(self, default: str = "local") -> None:
        document = profile(profile_id="local", strategy="local")
        external = profile(profile_id="external", strategy="external", extraction_plugin="transform.external@1")
        document["profiles"].append(external["profiles"][0])
        document["default_profile_id"] = default
        self.document = document

    async def get_profile(self, profile_id: str):
        return SimpleNamespace(kind="ingestion", document=self.document) if profile_id == "workspace-set" else None


def _candidate_service(default: str = "local") -> tuple[DocumentWorkbenchService, _CandidateProfiles]:
    current = registry()
    registration = current.get("transform.outcome@1")
    current._items["transform.external@1"] = PluginRegistration(  # type: ignore[attr-defined]
        registration.descriptor.model_copy(update={"plugin_id": "transform.external@1", "capabilities": ("external.fixture",)}),
        registration.factory, registration.configuration_model,
    )
    profiles = _CandidateProfiles(default)
    return DocumentWorkbenchService(
        profiles, current, object(), object(), object(),  # type: ignore[arg-type]
        external_capabilities=frozenset({"external.fixture"}),
    ), profiles


def test_preflight_returns_detector_facts_automatic_resolution_stages_and_local_disclosure() -> None:
    async def exercise() -> None:
        result = await _service().preflight(b"%PDF-1.7 fixture", "sample.PDF", "application/pdf", "complete")
        assert result["detected"] == {"media_type": "application/pdf", "extension": "pdf", "byte_size": 16,
                                      "page_count": 0, "language_hint": "", "has_embedded_text": True,
                                      "is_scanned": False, "document_class": None}
        assert result["automatic"]["selectedProfileId"] == "complete"
        assert result["automatic"]["selectionTier"] == "default"
        assert result["selection"] == {"profileId": "complete", "selectionTier": "default"}
        assert result["stages"][0]["key"] == "extraction.parse"
        assert result["disclosure"] == {"externalStages": [], "localPersistence": "提交后内容作为本地 Artifact 持久化。"}
    asyncio.run(exercise())


def test_candidate_selection_rotates_token_and_binds_candidate_specific_preview() -> None:
    async def exercise() -> None:
        service, _ = _candidate_service()
        automatic = await service.preflight(b"fixture", "fixture.txt", "text/plain", "workspace-set")
        assert automatic["selection"] == {"profileId": "local", "selectionTier": "default"}
        assert automatic["disclosure"]["externalStages"] == []
        selected = await service.select_candidate(automatic["token"], "external")
        assert selected["token"] != automatic["token"]
        assert selected["automatic"] == automatic["automatic"]
        assert selected["selection"] == {"profileId": "external", "selectionTier": "explicit"}
        assert selected["planDigest"] != automatic["planDigest"]
        assert selected["stages"][0]["candidates"][0]["pluginId"] == "transform.external@1"
        assert selected["disclosure"]["externalStages"]
        with pytest.raises(LookupError, match="PREFLIGHT_UNAVAILABLE"):
            await service.select_candidate(automatic["token"], "local")
        with pytest.raises(PermissionError, match="PREFLIGHT_SELECTION_MISMATCH"):
            await service.submit(selected["token"], "local", True)
        assert selected["token"] in service._preflights
    asyncio.run(exercise())


def test_external_to_local_selection_removes_disclosure_and_invalid_selection_consumes_token() -> None:
    async def exercise() -> None:
        service, _ = _candidate_service("external")
        automatic = await service.preflight(b"fixture", "fixture.txt", "text/plain", "workspace-set")
        assert automatic["disclosure"]["externalStages"]
        selected = await service.select_candidate(automatic["token"], "local")
        assert selected["selection"]["profileId"] == "local"
        assert selected["disclosure"]["externalStages"] == []
        with pytest.raises(ValueError, match="PREFLIGHT_SELECTION_INVALID"):
            await service.select_candidate(selected["token"], "unknown")
        assert selected["token"] not in service._preflights
    asyncio.run(exercise())


def test_replacement_and_stale_preview_consume_old_token_without_creating_a_run() -> None:
    async def exercise() -> None:
        service, profiles = _candidate_service()
        first = await service.preflight(b"fixture", "fixture.txt", "text/plain", "workspace-set")
        with pytest.raises(ValueError, match="PREFLIGHT_INVALID"):
            await service.preflight(b"", "fixture.txt", "text/plain", "workspace-set", first["token"])
        assert first["token"] not in service._preflights

        current = await service.preflight(b"fixture", "fixture.txt", "text/plain", "workspace-set")
        profiles.document["profiles"][0]["axes"]["extraction"]["sub_stages"][0]["candidates"][0]["configuration"]["strategy"] = "changed"
        with pytest.raises(PermissionError, match="PREFLIGHT_STALE"):
            await service.submit(current["token"], None, False)
        assert current["token"] not in service._preflights
    asyncio.run(exercise())


def test_candidate_selection_api_rotates_and_replacement_header_revokes(
    settings: Settings, catalog: CapabilityCatalog,
) -> None:
    app = create_app(settings, catalog)
    service = _service()
    app.state.workbench_documents = service
    client = TestClient(app)
    headers = {"X-Profile-Id": "complete", "X-Filename": "fixture.txt", "Content-Type": "text/plain"}
    initial = client.put("/api/workbench/documents/preflight", headers=headers, content=b"fixture").json()
    selected_response = client.post(
        f"/api/workbench/documents/preflights/{initial['token']}/selection", json={"profileId": "complete"},
    )
    assert selected_response.status_code == 200
    selected = selected_response.json()
    assert selected["token"] != initial["token"] and selected["selection"]["selectionTier"] == "explicit"
    assert client.post(f"/api/workbench/documents/preflights/{initial['token']}/selection", json={"profileId": "complete"}).status_code == 404
    replaced = client.put(
        "/api/workbench/documents/preflight",
        headers={**headers, "X-Replaces-Preflight-Token": selected["token"]}, content=b"",
    )
    assert replaced.status_code == 422
    assert client.post(f"/api/workbench/documents/preflights/{selected['token']}/runs", json={}).status_code == 404


def test_document_list_projection_is_strict_paged_and_safe(settings: Settings, catalog: CapabilityCatalog) -> None:
    source_id, output_id, run_id = uuid4(), uuid4(), uuid4()
    registered = datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc)

    class Repository:
        calls = []

        async def list_document_submissions(self, limit, cursor):
            self.calls.append((limit, cursor))
            row = DocumentSubmissionRecord(
                source_artifact_id=source_id, run_id=run_id, display_filename="sample.pdf",
                media_type="application/pdf", registered_at=registered, byte_size=1234,
                format="pdf", document_class=None, profile_id="native-long",
                run_state=RunState.RUNNING, output_artifact_id=output_id,
            )
            return (row,), DocumentSubmissionCursor(registered_at=registered, source_artifact_id=source_id)

    repository = Repository()
    service = DocumentWorkbenchService(_Profiles(), registry(), object(), object(), object(), repository=repository)  # type: ignore[arg-type]
    first = asyncio.run(service.documents_page(1))
    payload = first.model_dump(mode="json")
    assert set(payload) == {"contractVersion", "items", "page"}
    assert set(payload["items"][0]) == {"sourceArtifactId", "filename", "mediaType", "format", "byteSize", "documentClass", "profileId", "registeredAt", "latestRun", "actions"}
    assert payload["items"][0]["documentClass"] is None
    assert payload["items"][0]["actions"] == {"sourceArtifactId": str(source_id), "outputArtifactId": str(output_id)}
    assert not any(key in str(payload).lower() for key in ("storage_locator", "contentdigest", "providerpayload", "filesystem"))
    second = asyncio.run(service.documents_page(1, first.page.nextCursor))
    assert second.items[0].sourceArtifactId == source_id
    assert repository.calls[1][1] == DocumentSubmissionCursor(registered_at=registered, source_artifact_id=source_id)

    app = create_app(settings, catalog)
    app.state.workbench_documents = service
    client = TestClient(app)
    assert client.get("/api/workbench/documents?limit=1").status_code == 200
    invalid = client.get("/api/workbench/documents?cursor=not-a-cursor")
    assert invalid.status_code == 422
    assert invalid.json() == {"contractVersion": "workbench-problem/v1", "code": "DOCUMENT_CURSOR_INVALID"}
    for limit in ("0", "51", "not-a-number"):
        invalid_page = client.get(f"/api/workbench/documents?limit={limit}")
        assert invalid_page.status_code == 422
        assert invalid_page.json() == {"contractVersion": "workbench-problem/v1", "code": "DOCUMENT_PAGE_INVALID"}


def test_document_list_failure_uses_safe_503_problem(settings: Settings, catalog: CapabilityCatalog) -> None:
    class Repository:
        async def list_document_submissions(self, limit, cursor):
            raise RuntimeError("database path /private/source and provider payload")

    app = create_app(settings, catalog)
    app.state.workbench_documents = DocumentWorkbenchService(_Profiles(), registry(), object(), object(), object(), repository=Repository())  # type: ignore[arg-type]
    response = TestClient(app).get("/api/workbench/documents")
    assert response.status_code == 503
    assert response.json() == {"contractVersion": "workbench-problem/v1", "code": "DOCUMENT_LIST_UNAVAILABLE"}


def test_preflight_is_bounded_and_requires_a_saved_ingestion_profile() -> None:
    async def exercise() -> None:
        with pytest.raises(LookupError, match="INGESTION_PROFILE_NOT_FOUND"):
            await _service().preflight(b"x", "x.txt", "text/plain", "missing")
        with pytest.raises(ValueError, match="PREFLIGHT_INVALID"):
            await _service().preflight(b"", "x.txt", "text/plain", "complete")
    asyncio.run(exercise())


def test_preflight_keeps_workspace_profile_set_while_automatic_selection_uses_inner_profile_id() -> None:
    class Profiles:
        async def get_profile(self, profile_id: str):
            if profile_id != "workspace-set":
                return None
            document = profile(profile_id="default")
            alternate = json.loads(json.dumps(document["profiles"][0]))
            alternate["profile_id"] = "automatic"
            document["profiles"].append(alternate)
            document["preflight_rules"] = [{"rule_id": "text", "when": {"eq": ["document.extension", "txt"]}, "profile_id": "automatic"}]
            return SimpleNamespace(kind="ingestion", document=document)
    async def exercise() -> None:
        service = DocumentWorkbenchService(Profiles(), registry(), object(), object(), object())  # type: ignore[arg-type]
        result = await service.preflight(b"fixture", "fixture.txt", "text/plain", "workspace-set")
        assert result["automatic"]["selectedProfileId"] == "automatic"
        assert service._preflights[result["token"]].workspace_profile_id == "workspace-set"
    asyncio.run(exercise())


def test_external_selected_stage_is_disclosed_and_cannot_be_confirmed_without_acknowledgement() -> None:
    async def exercise() -> None:
        current = registry()
        registration = current.get("transform.outcome@1")
        current._items["transform.outcome@1"] = PluginRegistration(  # type: ignore[attr-defined]
            registration.descriptor.model_copy(update={"capabilities": ("external.fixture",)}),
            registration.factory, registration.configuration_model,
        )
        service = DocumentWorkbenchService(_Profiles(), current, object(), object(), object(), external_capabilities=frozenset({"external.fixture"}))  # type: ignore[arg-type]
        preflight = await service.preflight(b"fixture", "fixture.txt", "text/plain", "complete")
        assert preflight["disclosure"]["externalStages"]
        with pytest.raises(PermissionError, match="EXTERNAL_DISCLOSURE_REQUIRED"):
            await service.submit(preflight["token"], "complete", False)
        # Acknowledgement can be corrected without re-uploading, but a
        # successful confirmation is the only path that consumes this token.
        assert preflight["token"] in service._preflights
    asyncio.run(exercise())


def test_pinned_plan_resolves_plugin_identity_for_failed_skipped_and_running_attempts() -> None:
    plan = {"stages": [{"axis": "extraction", "sub_stages": [{"stage_id": "parse", "candidates": [
        {"plugin_id": "parser.first@1"}, {"plugin_id": "parser.fallback@1"},
    ]}]}]}
    assert DocumentWorkbenchService._planned_plugin(plan, "ingestion.source") == "ingestion.source@1"
    assert DocumentWorkbenchService._planned_plugin(plan, "extraction.parse.candidate-1") == "parser.first@1"
    assert DocumentWorkbenchService._planned_plugin(plan, "extraction.parse.candidate-2") == "parser.fallback@1"
    assert DocumentWorkbenchService._planned_plugin(plan, "chunking.main.candidate-1") is None


def test_artifact_view_preserves_canonical_table_identity_and_locator() -> None:
    document = normalize_fixture(
        ProviderFixture.model_validate(canonical_fixture()),
        "c7f1c2c2-2bd1-4ff3-a641-0f52f50bfdd1",
    )
    view = DocumentWorkbenchService._artifact_view(
        "canonical.document", "v1", document.model_dump_json().encode()
    )

    assert view["tabs"] == ["canonical", "tree", "table", "metadata", "lineage"]
    assert view["elements"][6]["id"] == document.elements[6].id
    assert view["elements"][6]["locator"] == document.elements[6].locator.model_dump(mode="json")
    assert view["tables"] == [{
        "id": document.tables[0].id,
        "elementId": document.tables[0].element_id,
        "locator": document.tables[0].locator.model_dump(mode="json"),
        "cells": [cell.model_dump(mode="json") for cell in document.tables[0].cells],
    }]


def test_artifact_projects_structured_producer_identity_from_manifest() -> None:
    async def exercise() -> None:
        artifact_id, run_id = uuid4(), uuid4()
        manifest = ArtifactManifest(
            id=artifact_id, artifact_type="opaque.fixture", schema_revision="v1",
            content_digest="a" * 64, byte_size=7, summary="fixture", storage_locator="fixture",
            producing_run_id=run_id, producing_stage_attempt_id=uuid4(),
            producing_plugin_id="parser.fixture@1", configuration_digest="b" * 64,
        )

        class Artifacts:
            async def get_artifact_manifest(self, identifier):
                return manifest if identifier == artifact_id else None

            async def read_content(self, identifier):
                assert identifier == artifact_id
                return b"fixture"

        service = DocumentWorkbenchService(_Profiles(), registry(), object(), object(), Artifacts())  # type: ignore[arg-type]
        projection = await service.artifact(artifact_id)
        assert projection is not None
        assert projection["producer"] == {"runId": str(run_id), "pluginId": "parser.fixture@1"}

    asyncio.run(exercise())


def test_artifact_view_preserves_chunk_citation_locator() -> None:
    content = json.dumps({
        "chunks": [{
            "chunk_id": "chk_0123456789abcdef0123456789abcdef",
            "content": "source words",
            "source_element_ids": ["elm_0123456789abcdef", "elm_0123456789abcdee"],
            "citations": [
                {"element_id": "elm_0123456789abcdef", "locator": {"kind": "pdf", "page_number": 1, "x0": 0, "y0": 0, "x1": 1, "y1": 1}},
                {"element_id": "elm_0123456789abcdee", "locator": {"kind": "pdf", "page_number": 2, "x0": 2, "y0": 2, "x1": 3, "y1": 3}},
            ],
        }],
    }).encode()
    view = DocumentWorkbenchService._artifact_view("chunk.set", "v1", content)

    assert view["chunks"] == [{
        "id": "chk_0123456789abcdef0123456789abcdef",
        "sourceElementIds": ["elm_0123456789abcdef", "elm_0123456789abcdee"],
        "citations": [
            {"elementId": "elm_0123456789abcdef", "locator": {"kind": "pdf", "page_number": 1, "x0": 0, "y0": 0, "x1": 1, "y1": 1}},
            {"elementId": "elm_0123456789abcdee", "locator": {"kind": "pdf", "page_number": 2, "x0": 2, "y0": 2, "x1": 3, "y1": 3}},
        ],
        "text": "source words",
    }]


def test_static_workbench_has_artifact_actions_schema_tabs_locator_sync_and_narrow_drawer_keyboard_support() -> None:
    source = Path("src/kb2_runtime/workbench/static/workbench.js").read_text()
    assert "/api/workbench/artifacts/${id}" in source
    assert "Artifact ${output.artifactType}" in source
    assert "inspector-tabs" in source
    assert "source-view" in source and "稳定对象列表" in source
    assert "data-stable-id" in source and "source-selected" in source
    assert "node.dataset.stableId===key" in source
    # A Chunk can cite more than one source element; a first-citation-only
    # source pane would silently make the remaining real locators unreachable.
    assert "row.citations?.[0]?.locator" not in source
    assert "(row.citations||[]).map" in source
    assert "resolution.selected_profile_id" in source
    assert "Boolean(x.actions?.artifact)" in source
    assert "signalValue(stage.metrics)" in source and "signalValue(stage.quality)" in source
    assert "signalValue(x.metrics)" in source and "signalValue(x.quality)" in source
    assert "role:'status'" in source and "正在预检" in source and "预检失败，可重试" in source
    assert "表格源定位" in source
    assert ".inspector-drawer.open" in source
    assert "overlay.remove()" in source and "returnFocus?.focus()" in source
    assert "e.key==='Escape'" in source and "e.key==='Tab'" in source
    assert "button('重新运行'" in source and "button('停止'" in source
    assert "actions?.retry" not in source
    assert "/ingestion-runs/{run_id}/retry" not in Path("src/kb2_runtime/api.py").read_text()
