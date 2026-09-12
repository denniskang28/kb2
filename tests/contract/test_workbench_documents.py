from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from kb2_runtime.workbench.documents import DocumentWorkbenchService
from kb2_runtime.plugins.registry import PluginRegistration
from kb2_runtime.canonical.contracts import ProviderFixture
from kb2_runtime.canonical.normalizer import normalize_fixture
from tests.contract.test_ingestion_engine import profile, registry
from tests.contract.test_canonical_document import fixture as canonical_fixture


class _Profiles:
    async def get_profile(self, profile_id: str):
        return SimpleNamespace(kind="ingestion", document=profile(profile_id=profile_id)) if profile_id == "complete" else None


def _service() -> DocumentWorkbenchService:
    # Preflight does not invoke the engine; these sentinels make that boundary
    # explicit and keep the contract test deterministic.
    return DocumentWorkbenchService(_Profiles(), registry(), object(), object(), object())  # type: ignore[arg-type]


def test_preflight_returns_detector_facts_automatic_resolution_stages_and_local_disclosure() -> None:
    async def exercise() -> None:
        result = await _service().preflight(b"%PDF-1.7 fixture", "sample.PDF", "application/pdf", "complete")
        assert result["detected"] == {"media_type": "application/pdf", "extension": "pdf", "byte_size": 16,
                                      "page_count": 0, "language_hint": "", "has_embedded_text": True,
                                      "is_scanned": False, "document_class": None}
        assert result["automatic"]["selectedProfileId"] == "complete"
        assert result["automatic"]["selectionTier"] == "default"
        assert result["stages"][0]["key"] == "extraction.parse"
        assert result["disclosure"] == {"externalStages": [], "localPersistence": "提交后内容作为本地 Artifact 持久化。"}
    asyncio.run(exercise())


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
    assert "row.citations.map" in source
    assert ".inspector-drawer.open" in source
    assert "inspector.remove();origin?.focus()" in source
    assert "e.key==='Escape'" in source and "e.key==='Tab'" in source
    assert "button('重新运行'" in source and "button('停止'" in source
    assert "button('重试'" not in source
    assert "/ingestion-runs/{run_id}/retry" not in Path("src/kb2_runtime/api.py").read_text()
