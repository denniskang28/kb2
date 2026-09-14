from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient
import yaml

import kb2_runtime.api as api_module
from kb2_runtime.api import create_app
from kb2_runtime.config import CapabilityCatalog, Settings
from kb2_runtime.workbench.studio import StudioService


class _Repository:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, object]] = {}

    async def list_profile_workspaces(self, kind=None, query=""):
        return tuple(value for key, value in sorted(self.rows.items()) if (kind is None or value["profile_kind"] == kind) and query in key)

    async def get_profile_workspace(self, profile_id): return self.rows.get(profile_id)

    async def save_profile_workspace(self, profile_id, kind, document):
        row = {"profile_id": profile_id, "profile_kind": kind, "source_document": document, "updated_at": datetime.now(timezone.utc)}
        self.rows[profile_id] = row
        return row


class _Runner:
    def __init__(self) -> None: self.called = None
    async def execute(self, plan, question_artifact, search_artifact):
        self.called = (plan, question_artifact, search_artifact)
        return SimpleNamespace(run_id=UUID(int=1), profile_id=plan.profile_id, plan_digest=plan.digest)


def _document() -> dict[str, object]:
    return json.loads(Path("tests/fixtures/query_profiles/text-hybrid.json").read_text())


def _binding() -> dict[str, object]:
    return {"artifact_id": "12345678-1234-5678-1234-567812345678", "artifact_type": "search.index.result", "schema_revision": "v1", "content_digest": "a" * 64, "byte_size": 1}


def test_yaml_round_trip_persists_normalized_working_profile_and_survives_service_restart() -> None:
    async def exercise() -> None:
        repository = _Repository()
        first = StudioService(repository=repository)
        source = Path("tests/fixtures/query_profiles/text-hybrid.json").read_text()
        validated = await first.validate("query", None, source=source, media_type="application/yaml")
        assert validated.valid and validated.normalizedDocument
        saved = await first.save("text-hybrid", "query", validated.normalizedDocument)
        assert saved.profileId == "text-hybrid"
        second = StudioService(repository=repository)
        restored = await second.get_profile("text-hybrid")
        assert restored and restored.document == validated.normalizedDocument
    asyncio.run(exercise())


def test_actual_yaml_round_trip_preserves_typed_stages_and_rejects_executable_content() -> None:
    async def exercise() -> None:
        service = StudioService()
        document = _document()
        source = yaml.safe_dump(document, sort_keys=False)
        result = await service.validate("query", None, source=source, media_type="application/yaml")
        assert result.valid
        assert result.normalizedDocument is not None
        stage = result.normalizedDocument["profiles"][0]["stages"][0]
        assert stage["configuration"]["limit"] == 8
        assert stage["outputs"] == ["candidates"]

        unsafe = await service.validate(
            "query",
            None,
        source=source.replace("limit: 8", "command: rm -rf /", 1),
            media_type="application/yaml",
        )
        assert not unsafe.valid
        assert unsafe.diagnostics[0].code == "QUERY_PROFILE_UNSAFE_CONTENT"
    asyncio.run(exercise())


def test_fastapi_profile_save_get_and_copy_return_json_safe_persisted_working_values(settings: Settings, catalog: CapabilityCatalog, monkeypatch) -> None:
    class Repository(_Repository):
        async def close(self) -> None:
            return None

    repository = Repository()

    async def connect(**_: object) -> Repository:
        return repository

    monkeypatch.setattr(api_module.TraceRepository, "connect", connect)
    client = TestClient(create_app(settings, catalog))
    document = _document()

    saved = client.put("/api/workbench/profiles/text-hybrid", json={"kind": "query", "document": document})
    assert saved.status_code == 200
    assert saved.json()["profileId"] == "text-hybrid"
    assert saved.json()["document"]["schema_version"] == document["schema_version"]
    stage = saved.json()["document"]["profiles"][0]["stages"][0]
    assert stage["plugin_id"] == "retriever.keyword@1"
    assert stage["configuration"] == {"limit": 8}
    assert stage["inputs"] == {"question": "query.question", "index": "search.index"}
    assert isinstance(saved.json()["updatedAt"], str)

    read = client.get("/api/workbench/profiles/text-hybrid")
    assert read.status_code == 200
    assert read.json()["document"]["profiles"][0]["stages"][0]["plugin_id"] == "retriever.keyword@1"

    copied = client.post("/api/workbench/profiles/text-hybrid/copy?copy_id=text-hybrid-copy")
    assert copied.status_code == 201
    assert copied.json()["profileId"] == "text-hybrid-copy"
    assert client.get("/api/workbench/profiles?kind=query&q=text-hybrid").json()[0]["profileId"] == "text-hybrid"


def test_fastapi_profile_rejects_unsafe_declarative_input_without_persisting(settings: Settings, catalog: CapabilityCatalog, monkeypatch) -> None:
    class Repository(_Repository):
        async def close(self) -> None:
            return None

    repository = Repository()

    async def connect(**_: object) -> Repository:
        return repository

    monkeypatch.setattr(api_module.TraceRepository, "connect", connect)
    client = TestClient(create_app(settings, catalog))
    unsafe = _document()
    unsafe["command"] = "do-not-run"

    response = client.put("/api/workbench/profiles/text-hybrid", json={"kind": "query", "document": unsafe})
    assert response.status_code == 422
    assert response.json()["valid"] is False
    assert response.json()["diagnostics"] == [{"code": "QUERY_PROFILE_UNSAFE_CONTENT", "location": "/"}]
    assert repository.rows == {}


def test_registry_compatibility_is_server_owned_and_detail_projects_bounded_run_summaries() -> None:
    class Repository(_Repository):
        async def list_plugin_workbench_runs(self, plugin_id: str):
            assert plugin_id == "retriever.keyword@1"
            now = datetime(2026, 9, 12, tzinfo=timezone.utc)
            return (
                {"id": UUID(int=1), "engine_kind": "evaluation", "state": "SUCCEEDED", "terminal_state": "SUCCEEDED", "created_at": now},
                {"id": UUID(int=2), "engine_kind": "query", "state": "FAILED", "terminal_state": "FAILED", "created_at": now},
            )

    async def exercise() -> None:
        service = StudioService(repository=Repository())
        compatible = await service.compatible_plugins("retrieve")
        assert compatible
        assert all(item.kind == "retriever" and item.runnable for item in compatible)
        assert {item.pluginId for item in compatible} >= {"retriever.keyword@1"}

        detail = await service.plugin_detail("retriever.keyword@1")
        assert detail is not None
        assert detail.safeExample == {"limit": 10}
        assert detail.contractTests == ({"runId": str(UUID(int=1)), "engineKind": "evaluation", "state": "SUCCEEDED", "terminalState": "SUCCEEDED", "createdAt": "2026-09-12T00:00:00+00:00"},)
        assert tuple(item["runId"] for item in detail.recentRuns) == (str(UUID(int=1)), str(UUID(int=2)))
    asyncio.run(exercise())


def test_real_registry_routes_accept_empty_filters_and_survive_run_history_unavailability(settings: Settings, catalog: CapabilityCatalog, monkeypatch) -> None:
    async def report(*_: object, **__: object):
        return SimpleNamespace(capabilities=())

    async def unavailable_repository(**_: object):
        raise RuntimeError("test repository unavailable")

    monkeypatch.setattr(api_module.HealthService, "report", report)
    monkeypatch.setattr(api_module.TraceRepository, "connect", unavailable_repository)
    client = TestClient(create_app(settings, catalog))

    response = client.get("/api/workbench/plugins?kind=&runner=&readiness=&q=")
    assert response.status_code == 200
    assert len(response.json()) > 1
    assert {item["pluginId"] for item in response.json()} >= {"retriever.keyword@1"}

    detail = client.get("/api/workbench/plugins/retriever.keyword@1")
    assert detail.status_code == 200
    assert detail.json()["pluginId"] == "retriever.keyword@1"
    assert detail.json()["configurationSchema"]["type"] == "object"
    assert detail.json()["recentRuns"] == []

    assert client.get("/api/workbench/plugins?runner=unknown").status_code == 422


def test_query_dry_run_recompiles_saved_profile_and_delegates_only_artifact_ids() -> None:
    async def exercise() -> None:
        repository, runner = _Repository(), _Runner()
        service = StudioService(repository=repository, query_runner=runner)
        document = _document()
        await service.save("text-hybrid", "query", document)
        result = await service.dry_run("text-hybrid", "query", "12345678-1234-5678-1234-567812345679", _binding())
        assert result.runId == str(UUID(int=1))
        assert runner.called and runner.called[1:] == (UUID("12345678-1234-5678-1234-567812345679"), UUID("12345678-1234-5678-1234-567812345678"))
        assert not (await service.dry_run("missing", "query", "12345678-1234-5678-1234-567812345679", _binding())).valid
        assert not (await service.dry_run("text-hybrid", "ingestion", None, None)).valid
    asyncio.run(exercise())


def test_server_compatibility_derives_prior_ports_and_omits_incompatible_same_family() -> None:
    async def exercise() -> None:
        service = StudioService()
        document = _document()
        # The initial generate slot has no prior evidence output; generator
        # descriptors therefore cannot be selected from an empty port set.
        result = await service.compatible_for_document("query", document, "generate")
        assert isinstance(result, tuple) and result == ()
        # A real stage identity is parsed, and incompatible generator ports are
        # omitted rather than accepted based solely on its family label.
        options = await service.compatible_for_document("query", document, document["profiles"][0]["stages"][0]["stage_id"])
        assert isinstance(options, tuple)
        assert all(item.kind != "generator" for item in options)
    asyncio.run(exercise())
