from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from io import BytesIO
import hashlib
import json
from types import SimpleNamespace
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from kb2_runtime.api import create_app
from kb2_runtime.config import CapabilityCatalog, Settings
from kb2_runtime.workbench.documents import DocumentWorkbenchService
from kb2_runtime.workbench.contracts import DocumentElementViewItem, DocumentInspectorView
from kb2_runtime.plugins.registry import PluginRegistration
from kb2_runtime.canonical.contracts import (
    CanonicalDocument, CanonicalElement, CanonicalTable, PdfLocator, Provenance,
    ProviderFixture, TableCell,
)
from kb2_runtime.canonical.normalizer import normalize_fixture
from kb2_runtime.chunking.contracts import ChunkerConfig
from kb2_runtime.chunking.processor import canonical_bytes, process
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


def _table_inspector_service(table_sizes: tuple[int, ...]):
    source_id, canonical_id, run_id = uuid4(), uuid4(), uuid4()
    locator = PdfLocator(page_number=1, x0=0, y0=0, x1=1, y1=1)
    elements = []
    tables = []
    for table_index, size in enumerate(table_sizes):
        assert size > 0 and size <= 512 * 512
        rows = 1 if size <= 512 else 2
        assert size % rows == 0
        columns = size // rows
        element_id = f"elm_{table_index + 1:016x}"
        table_id = f"tbl_{table_index + 1:016x}"
        elements.append(CanonicalElement(
            id=element_id, kind="table", reading_order=table_index,
            table_id=table_id, locator=locator,
        ))
        cells = tuple(TableCell(
            id=f"cel_{table_index + 1:02x}{cell_index + 1:014x}", text=f"cell {cell_index}",
            row=cell_index // columns, column=cell_index % columns,
            row_span=1, column_span=1,
        ) for cell_index in range(size))
        tables.append(CanonicalTable(
            id=table_id, element_id=element_id, rows=rows, columns=columns,
            locator=locator, cells=cells,
        ))
    if not elements:
        elements.append(CanonicalElement(
            id="elm_0000000000000001", kind="paragraph", reading_order=0,
            text="no tables", locator=locator,
        ))
    document = CanonicalDocument(
        document_id="doc_0000000000000001",
        provenance=Provenance(
            source_artifact_id=str(source_id), source_content_digest="a" * 64,
            adapter_id="fixture.adapter@1",
        ),
        elements=tuple(elements), tables=tuple(tables),
    )
    content = document.model_dump_json().encode()
    registered = datetime(2026, 9, 15, 3, 0, tzinfo=timezone.utc)

    def manifest(identifier: UUID, artifact_type: str, payload: bytes, parents=()):
        return ArtifactManifest(
            id=identifier, artifact_type=artifact_type, schema_revision="v1",
            content_digest=hashlib.sha256(payload).hexdigest(), byte_size=len(payload),
            summary="safe", storage_locator="not-projected", producing_run_id=run_id,
            producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture.plugin@1",
            configuration_digest="b" * 64, parent_artifact_ids=parents,
        )

    manifests = (
        manifest(source_id, "opaque.bytes", b"source"),
        manifest(canonical_id, "canonical.document", content, (source_id,)),
    )
    row = DocumentSubmissionRecord(
        source_artifact_id=source_id, run_id=run_id, display_filename="table.txt",
        media_type="text/plain", registered_at=registered, byte_size=6, format="txt",
        document_class=None, profile_id="complete", run_state=RunState.SUCCEEDED,
        output_artifact_id=canonical_id,
    )

    class Repository:
        async def get_document_submissions_by_source_ids(self, source_ids, *, limit=64):
            return (row,) if tuple(source_ids) == (source_id,) else ()

        async def list_document_artifact_manifests(self, requested_source, requested_run, *, limit=128):
            return manifests if (requested_source, requested_run) == (source_id, run_id) else ()

    class Artifacts:
        repository = Repository()

        async def read_content(self, identifier):
            return content if identifier == canonical_id else b"source"

    service = DocumentWorkbenchService(
        _Profiles(), registry(), object(), object(), Artifacts(),  # type: ignore[arg-type]
    )
    return service, source_id, canonical_id, document


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
    assert payload["items"][0]["actions"] == {"inspectDocument": True, "sourceArtifactId": str(source_id), "outputArtifactId": str(output_id)}
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


def test_preflight_discard_is_idempotent_and_revokes_submission_authority(
    settings: Settings, catalog: CapabilityCatalog,
) -> None:
    service = _service()
    preview = asyncio.run(service.preflight(b"fixture", "fixture.txt", "text/plain", "complete"))
    app = create_app(settings, catalog)
    app.state.workbench_documents = service
    client = TestClient(app)
    assert client.delete(f"/api/workbench/documents/preflights/{preview['token']}").status_code == 204
    assert client.delete(f"/api/workbench/documents/preflights/{preview['token']}").status_code == 204
    response = client.post(f"/api/workbench/documents/preflights/{preview['token']}/runs", json={})
    assert response.status_code == 404 and response.json()["code"] == "PREFLIGHT_UNAVAILABLE"


def test_document_inspector_is_exact_source_paged_safe_and_range_capable(
    settings: Settings, catalog: CapabilityCatalog,
) -> None:
    from pypdf import PdfWriter

    source_id, canonical_id, chunks_id, run_id = uuid4(), uuid4(), uuid4(), uuid4()
    registered = datetime(2026, 9, 15, 2, 0, tzinfo=timezone.utc)
    pdf = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(pdf)
    pdf_bytes = pdf.getvalue()
    canonical_document = normalize_fixture(ProviderFixture.model_validate(canonical_fixture()), str(source_id))
    canonical_content = canonical_document.model_dump_json().encode()
    chunk_content = canonical_bytes(process(canonical_content, ChunkerConfig(strategy="parent_child", max_tokens=64)))

    def manifest(identifier, artifact_type, content, parents=()):
        return ArtifactManifest(
            id=identifier, artifact_type=artifact_type, schema_revision="v1",
            content_digest=hashlib.sha256(content).hexdigest(), byte_size=len(content), summary="safe summary",
            storage_locator="private/path/not-projected", producing_run_id=run_id,
            producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture.plugin@1",
            configuration_digest="b" * 64, parent_artifact_ids=parents,
        )

    manifests = (
        manifest(source_id, "opaque.bytes", pdf_bytes),
        manifest(canonical_id, "canonical.document", canonical_content, (source_id,)),
        manifest(chunks_id, "chunk.set", chunk_content, (canonical_id,)),
    )
    row = DocumentSubmissionRecord(
        source_artifact_id=source_id, run_id=run_id, display_filename="sample report.pdf",
        media_type="application/pdf", registered_at=registered, byte_size=len(pdf_bytes), format="pdf",
        document_class="native_long", profile_id="complete", run_state=RunState.SUCCEEDED,
        output_artifact_id=chunks_id,
    )

    class Repository:
        async def get_document_submissions_by_source_ids(self, source_ids, *, limit=64):
            return (row,) if tuple(source_ids) == (source_id,) else ()

        async def list_document_artifact_manifests(self, requested_source, requested_run, *, limit=128):
            assert (requested_source, requested_run) == (source_id, run_id)
            return manifests

    class Artifacts:
        repository = Repository()

        async def read_content(self, identifier):
            return {source_id: pdf_bytes, canonical_id: canonical_content, chunks_id: chunk_content}[identifier]

    service = DocumentWorkbenchService(_Profiles(), registry(), object(), object(), Artifacts())  # type: ignore[arg-type]
    app = create_app(settings, catalog)
    app.state.workbench_documents = service
    client = TestClient(app)

    summary_response = client.get(f"/api/workbench/documents/{source_id}/inspector")
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["preview"] == {"kind": "pdf", "contentUrl": f"/api/workbench/documents/{source_id}/content", "pageCount": 1}
    assert [tab["id"] for tab in summary["tabs"]] == ["canonical", "structure", "tables", "chunks", "metadata", "lineage"]
    assert all(tab["state"] == "available" for tab in summary["tabs"])
    assert set(summary) == {"contractVersion", "source", "latestRun", "preview", "tabs", "artifacts", "metadata"}
    assert "storage" not in str(summary).lower() and "private/path" not in str(summary)
    unknown = uuid4()
    assert client.get(f"/api/workbench/documents/{unknown}/inspector").status_code == 404
    assert client.get(f"/api/workbench/documents/{unknown}/content").status_code == 404
    assert client.get(f"/api/workbench/documents/{unknown}/inspector/views/chunks").status_code == 404

    chunks = client.get(f"/api/workbench/documents/{source_id}/inspector/views/chunks?limit=1").json()
    assert chunks["items"][0]["tokenCount"] >= 1
    assert chunks["items"][0]["sourceElementIds"] and chunks["items"][0]["citations"]
    assert set(chunks["items"][0]) == {"id", "content", "truncated", "tokenCount", "sourceElementIds", "parentChunkId", "childChunkIds", "citations"}
    assert client.get(f"/api/workbench/documents/{source_id}/inspector/views/chunks?cursor=forged").status_code == 422
    assert client.get(f"/api/workbench/documents/{source_id}/inspector/views/chunks?limit=51").status_code == 422
    assert client.get(f"/api/workbench/documents/{source_id}/inspector/views/raw").status_code == 422

    canonical = client.get(f"/api/workbench/documents/{source_id}/inspector/views/canonical?limit=1").json()
    assert set(canonical["items"][0]) == {"id", "kind", "readingOrder", "parentId", "level", "text", "truncated", "locator"}
    typed_canonical = asyncio.run(service.document_view(source_id, "canonical", 1))
    assert isinstance(typed_canonical.items[0], DocumentElementViewItem)
    with pytest.raises(ValidationError, match="document view items do not match"):
        DocumentInspectorView(
            view="tables", artifactId=canonical_id, runId=run_id,
            items=typed_canonical.items, page=typed_canonical.page,
        )
    if canonical["page"]["nextCursor"]:
        mismatch = client.get(
            f"/api/workbench/documents/{source_id}/inspector/views/chunks",
            params={"cursor": canonical["page"]["nextCursor"]},
        )
        assert mismatch.status_code == 422
    structure = client.get(f"/api/workbench/documents/{source_id}/inspector/views/structure?limit=100").json()
    assert any(item["parentId"] for item in structure["items"])
    assert any(item["level"] for item in structure["items"])
    tables = client.get(f"/api/workbench/documents/{source_id}/inspector/views/tables").json()
    assert set(tables["items"][0]) == {
        "id", "elementId", "rows", "columns", "locator", "cellOffset",
        "totalCells", "hasMoreCells", "cells",
    }
    assert tables["items"][0]["cells"]
    assert all(set(cell) == {"id", "text", "row", "column", "rowSpan", "columnSpan", "isHeader"}
               for cell in tables["items"][0]["cells"])
    lineage = client.get(f"/api/workbench/documents/{source_id}/inspector/views/lineage").json()
    assert len(lineage["items"]) == 3
    assert all(set(item) == {"id", "artifactType", "schemaRevision", "producer", "parents", "summary"}
               for item in lineage["items"])
    assert lineage["items"][1] == {
        "id": str(canonical_id), "artifactType": "canonical.document", "schemaRevision": "v1",
        "producer": "fixture.plugin@1", "parents": [str(source_id)], "summary": "safe summary",
    }
    serialized_views = json.dumps((canonical, tables, chunks, lineage)).lower()
    assert all(secret not in serialized_views for secret in
               ("private/path", "storage_locator", "configuration_digest", "providerpayload", "embedding", "vector"))

    complete = client.get(f"/api/workbench/documents/{source_id}/content")
    assert complete.content == pdf_bytes and complete.headers["cache-control"] == "private, no-store"
    assert complete.headers["x-content-type-options"] == "nosniff"
    assert complete.headers["cross-origin-resource-policy"] == "same-origin"
    assert complete.headers["accept-ranges"] == "bytes"
    assert complete.headers["content-disposition"].startswith("inline; filename*=UTF-8''sample%20report.pdf")
    partial = client.get(f"/api/workbench/documents/{source_id}/content", headers={"Range": "bytes=0-9"})
    assert partial.status_code == 206 and partial.content == pdf_bytes[:10]
    assert partial.headers["content-range"] == f"bytes 0-9/{len(pdf_bytes)}"
    chrome_range = client.get(
        f"/api/workbench/documents/{source_id}/content",
        headers={"Range": "bytes=0-1048575"},
    )
    assert chrome_range.status_code == 206 and chrome_range.content == pdf_bytes
    assert chrome_range.headers["content-range"] == f"bytes 0-{len(pdf_bytes) - 1}/{len(pdf_bytes)}"
    assert chrome_range.headers["content-length"] == str(len(pdf_bytes))
    beyond_eof = client.get(
        f"/api/workbench/documents/{source_id}/content",
        headers={"Range": f"bytes=1-{len(pdf_bytes) + 4096}"},
    )
    assert beyond_eof.status_code == 206 and beyond_eof.content == pdf_bytes[1:]
    assert beyond_eof.headers["content-range"] == f"bytes 1-{len(pdf_bytes) - 1}/{len(pdf_bytes)}"
    assert beyond_eof.headers["content-length"] == str(len(pdf_bytes) - 1)
    suffix = client.get(f"/api/workbench/documents/{source_id}/content", headers={"Range": "bytes=-8"})
    assert suffix.status_code == 206 and suffix.content == pdf_bytes[-8:]
    assert client.get(f"/api/workbench/documents/{source_id}/content", headers={"Range": "items=0-1"}).status_code == 416
    assert client.get(f"/api/workbench/documents/{source_id}/content", headers={"Range": f"bytes={len(pdf_bytes)}-"}).status_code == 416
    assert client.get(f"/api/workbench/documents/{source_id}/content", headers={"Range": "bytes=0-1,3-4"}).status_code == 416
    assert "private/path" not in str(dict(complete.headers))

    element = service._element_item(canonical_document.elements[0])
    with pytest.raises(ValidationError) as unsafe:
        DocumentElementViewItem(**element.model_dump(mode="python"), storageLocator="private/path")
    assert any(error["type"] == "extra_forbidden" and error["loc"] == ("storageLocator",)
               for error in unsafe.value.errors())


@pytest.mark.parametrize(
    ("table_sizes", "expected_page_sizes"),
    [((500, 20), ((500, 12), (8,))), ((520,), ((512,), (8,))), ((), ((),)), ((4,), ((4,),))],
)
def test_table_view_cursor_reaches_every_cell_once_with_stable_table_identity(
    table_sizes: tuple[int, ...], expected_page_sizes: tuple[tuple[int, ...], ...],
) -> None:
    service, source_id, _, document = _table_inspector_service(table_sizes)

    async def exercise() -> None:
        cursor = None
        pages = []
        collected: dict[str, list[str]] = {}
        offsets: dict[str, list[int]] = {}
        while True:
            result = await service.document_view(source_id, "tables", 20, cursor)
            pages.append(tuple(len(item.cells) for item in result.items))
            assert sum(len(item.cells) for item in result.items) <= 512
            for item in result.items:
                collected.setdefault(item.id, []).extend(cell.id for cell in item.cells)
                offsets.setdefault(item.id, []).append(item.cellOffset)
                assert item.totalCells == next(
                    len(table.cells) for table in document.tables if table.id == item.id
                )
                assert item.hasMoreCells == (
                    item.cellOffset + len(item.cells) < item.totalCells
                )
            cursor = result.page.nextCursor
            if cursor is None:
                break
        assert tuple(pages) == expected_page_sizes
        assert set(collected) == {table.id for table in document.tables}
        for table in document.tables:
            expected = [cell.id for cell in table.cells]
            assert collected[table.id] == expected
            assert len(collected[table.id]) == len(set(collected[table.id]))
            assert offsets[table.id][0] == 0

    asyncio.run(exercise())


def test_table_view_rejects_mismatched_malformed_and_out_of_schema_cursors(
    settings: Settings, catalog: CapabilityCatalog,
) -> None:
    service, source_id, canonical_id, _ = _table_inspector_service((520,))
    app = create_app(settings, catalog)
    app.state.workbench_documents = service
    client = TestClient(app)
    first = client.get(
        f"/api/workbench/documents/{source_id}/inspector/views/tables?limit=20"
    )
    assert first.status_code == 200
    cursor = first.json()["page"]["nextCursor"]
    assert cursor
    continued = client.get(
        f"/api/workbench/documents/{source_id}/inspector/views/tables",
        params={"limit": 20, "cursor": cursor},
    )
    assert continued.status_code == 200
    assert continued.json()["items"][0]["cellOffset"] == 512
    assert client.get(
        f"/api/workbench/documents/{source_id}/inspector/views/canonical",
        params={"cursor": cursor},
    ).status_code == 422
    middle = len(cursor) // 2
    tampered = cursor[:middle] + ("A" if cursor[middle] != "A" else "B") + cursor[middle + 1:]
    for forged in (
        "forged",
        tampered,
        service._encode_view_cursor(source_id, canonical_id, "tables", 0, 521),
        service._encode_view_cursor(source_id, canonical_id, "tables", -1, 0),
        service._encode_view_cursor(uuid4(), canonical_id, "tables", 0, 0),
    ):
        response = client.get(
            f"/api/workbench/documents/{source_id}/inspector/views/tables",
            params={"limit": 20, "cursor": forged},
        )
        assert response.status_code == 422
        assert response.json() == {
            "contractVersion": "workbench-problem/v1", "code": "DOCUMENT_VIEW_INVALID",
        }


def test_document_inspector_observability_is_structured_complete_and_safe(
    settings: Settings, catalog: CapabilityCatalog, caplog: pytest.LogCaptureFixture,
) -> None:
    service, source_id, canonical_id, _ = _table_inspector_service((520,))
    app = create_app(settings, catalog)
    app.state.workbench_documents = service
    client = TestClient(app)
    caplog.set_level("INFO", logger="kb2_runtime.api")

    assert client.get(f"/api/workbench/documents/{source_id}/inspector").status_code == 200
    assert client.get(
        f"/api/workbench/documents/{source_id}/inspector/views/tables?limit=20"
    ).status_code == 200
    assert client.get(
        f"/api/workbench/documents/{source_id}/content", headers={"Range": "bytes=1-3"},
    ).status_code == 206
    assert client.get(
        f"/api/workbench/documents/{source_id}/content", headers={"Range": "bytes=99-"},
    ).status_code == 416
    malicious_view = "credential%3Dsecret-path-content"
    assert client.get(
        f"/api/workbench/documents/{source_id}/inspector/views/{malicious_view}"
    ).status_code == 422
    unknown = uuid4()
    assert client.get(f"/api/workbench/documents/{unknown}/inspector").status_code == 404

    records = [record for record in caplog.records
               if getattr(record, "kb2_event", None) == "workbench_document_inspector"]
    assert len(records) == 6
    projected = [{
        "source": record.kb2_source_id,
        "run": record.kb2_run_id,
        "view": record.kb2_view,
        "artifact": record.kb2_artifact_id,
        "items": record.kb2_item_count,
        "bytes": record.kb2_byte_count,
        "outcome": record.kb2_outcome,
        "code": record.kb2_code,
    } for record in records]
    assert projected[0]["source"] == str(source_id)
    assert projected[0]["view"] == "summary" and projected[0]["items"] == 6
    assert projected[0]["artifact"] == str(source_id)
    assert projected[0]["run"] is not None
    assert projected[1] == {
        "source": str(source_id), "run": projected[0]["run"], "view": "tables",
        "artifact": str(canonical_id), "items": 1, "bytes": 0,
        "outcome": "success", "code": "OK",
    }
    assert projected[2] == {
        "source": str(source_id), "run": projected[0]["run"], "view": "content",
        "artifact": str(source_id), "items": 0, "bytes": 3,
        "outcome": "success", "code": "OK",
    }
    assert projected[3] == {
        "source": str(source_id), "run": projected[0]["run"], "view": "content",
        "artifact": str(source_id), "items": 0, "bytes": 0,
        "outcome": "failure", "code": "SOURCE_RANGE_INVALID",
    }
    assert projected[4] == {
        "source": str(source_id), "run": None, "view": "invalid", "artifact": None,
        "items": 0, "bytes": 0, "outcome": "failure", "code": "DOCUMENT_VIEW_INVALID",
    }
    assert projected[5] == {
        "source": str(unknown), "run": None, "view": "summary", "artifact": None,
        "items": 0, "bytes": 0, "outcome": "failure", "code": "DOCUMENT_NOT_FOUND",
    }
    assert all(record.kb2_duration_ms >= 0 for record in records)
    safe_log_text = " ".join(
        record.getMessage() + repr(projected[index]) for index, record in enumerate(records)
    ).lower()
    assert all(secret not in safe_log_text for secret in (
        "table.txt", "cell 0", "not-projected", "storage_locator", "providerpayload",
        "credential", "secret", "path", "/private/",
    ))
    assert all("credential=secret" not in repr(record.__dict__).lower() for record in records)


def test_document_inspector_observability_never_logs_exception_text(
    settings: Settings, catalog: CapabilityCatalog, caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "private filename.pdf /private/provider-payload credential=unsafe"

    class BrokenInspector:
        async def document_inspector(self, source_id):
            raise RuntimeError(secret)

        async def document_view(self, source_id, view, limit, cursor):
            raise RuntimeError(secret)

        async def document_content(self, source_id):
            raise RuntimeError(secret)

    app = create_app(settings, catalog)
    app.state.workbench_documents = BrokenInspector()
    client = TestClient(app)
    caplog.set_level("INFO", logger="kb2_runtime.api")
    source_id = uuid4()

    assert client.get(f"/api/workbench/documents/{source_id}/inspector").status_code == 503
    assert client.get(
        f"/api/workbench/documents/{source_id}/inspector/views/tables"
    ).status_code == 503
    assert client.get(f"/api/workbench/documents/{source_id}/content").status_code == 404

    records = [record for record in caplog.records
               if getattr(record, "kb2_event", None) == "workbench_document_inspector"]
    assert [record.kb2_code for record in records] == [
        "DOCUMENT_INSPECTOR_UNAVAILABLE", "DOCUMENT_INSPECTOR_UNAVAILABLE",
        "SOURCE_CONTENT_UNAVAILABLE",
    ]
    assert all(record.kb2_outcome == "failure" for record in records)
    assert secret not in " ".join(record.getMessage() for record in records)
    assert all(secret not in repr(record.__dict__) for record in records)


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
