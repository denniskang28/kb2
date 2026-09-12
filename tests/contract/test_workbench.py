from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from fastapi.testclient import TestClient
from uuid import UUID

import kb2_runtime.health.service as health_module
import kb2_runtime.api as api_module
from kb2_runtime.api import create_app
from kb2_runtime.config import CapabilityCatalog, Settings
from kb2_runtime.health.contracts import HealthReport
from kb2_runtime.workbench.service import WorkbenchOverviewService


async def _ready(_: Settings) -> tuple[str, str]:
    return "ready", "OK"


class _OverviewRepository:
    async def close(self) -> None:
        return None

    async def list_workbench_runs(self, limit: int = 8):
        return ()

    async def count_active_runs(self) -> int:
        return 0

    async def list_workbench_comparisons(self, limit: int = 4):
        return ()


def _client(settings: Settings, catalog: CapabilityCatalog, monkeypatch, repository: _OverviewRepository | None = None) -> TestClient:
    monkeypatch.setattr(health_module, "postgres_probe", _ready)
    monkeypatch.setattr(health_module, "artifact_probe", _ready)
    monkeypatch.setattr(health_module, "worker_probe", _ready)
    async def connect(**_: object) -> _OverviewRepository:
        return repository or _OverviewRepository()
    monkeypatch.setattr(api_module.TraceRepository, "connect", connect)
    return TestClient(create_app(settings, catalog))


def test_workbench_shell_and_assets_are_served_for_all_eight_routes(
    settings: Settings, catalog: CapabilityCatalog, monkeypatch
) -> None:
    client = _client(settings, catalog, monkeypatch)
    for route in ("overview", "documents", "studio", "query", "evaluation-dataset", "compare", "runs", "plugins"):
        response = client.get(f"/workbench/{route}?workspace=local")
        assert response.status_code == 200
        assert 'lang="zh-CN"' in response.text
    assert client.get("/workbench/assets/workbench.js").status_code == 200
    assert client.get("/workbench/assets/workbench.css").status_code == 200


def test_overview_uses_non_probing_health_and_keeps_optional_state_separate(
    settings: Settings, catalog: CapabilityCatalog, monkeypatch
) -> None:
    async def forbidden(*_: object) -> set[str]:
        raise AssertionError("overview must not call an optional provider")

    monkeypatch.setattr(health_module, "deepseek_models", forbidden)
    monkeypatch.setattr(health_module, "container_runner_probe", _ready)
    payload = _client(settings, catalog, monkeypatch).get("/api/workbench/overview").json()

    assert payload["contractVersion"] == "workbench-overview/v1"
    assert payload["coreStatus"] == "ready"
    assert payload["recentRuns"] == []
    assert payload["recentComparisons"] == []
    assert {item["id"] for item in payload["core"]} == {item.id for item in catalog.components}
    assert any(item["status"] == "not_configured" for item in payload["optionalCapabilities"])
    assert next(item for item in payload["optionalCapabilities"] if item["id"] == "runner.container")["status"] == "ready"
    assert "capabilities" not in payload
    assert all(set(item) <= {"pluginId", "runnable", "reason"} for item in payload["plugins"])


def test_workbench_client_has_eight_keyboard_links_and_no_locale_switcher() -> None:
    source = ("src/kb2_runtime/workbench/static/workbench.js")
    content = open(source, encoding="utf-8").read()
    assert content.count("['") >= 8
    assert "aria-current" in content
    assert "lang" not in content
    assert "fetch('/api/workbench/overview')" in content
    assert "innerHTML" not in content
    assert "document.createElement" in content
    assert "插件能力" in content
    assert "skeleton" in content
    assert "document.activeElement===last" in content
    assert "trigger?.focus()" in content
    assert "id:'workbench-shell'" in content
    assert "background.setAttribute('inert','')" in content
    assert "background.removeAttribute('inert')" in content
    assert "link.addEventListener('click',closeDrawer)" in content
    assert "runId:run.id" in content
    assert "^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$" in content
    assert "workspaceIds" not in content
    assert "validateWorkspace();\nroute()[0]==='overview'" in content


def test_default_app_projects_bounded_persisted_runs_and_verified_comparisons(
    settings: Settings, catalog: CapabilityCatalog, monkeypatch
) -> None:
    identifier = UUID("12345678-1234-5678-1234-567812345678")
    comparison = UUID("12345678-1234-5678-1234-567812345679")
    now = datetime(2026, 9, 12, tzinfo=timezone.utc)

    content = b'{"schema_version":"EvaluationComparison/v1","mode":"candidate","axis":"quality","recommendation":"CANDIDATE_ELIGIBLE"}'

    class Persisted(_OverviewRepository):
        async def list_workbench_runs(self, limit: int = 8):
            assert limit == 8
            return ({"id": identifier, "engine_kind": "evaluation", "state": "FAILED", "terminal_state": "FAILED", "created_at": now, "started_at": now, "ended_at": now, "plan_digest": "a" * 64, "safe_error": {"code": "TRACE_STORAGE_FAILURE", "retryable": True}},)

        async def count_active_runs(self) -> int:
            return 2

        async def list_workbench_comparisons(self, limit: int = 4):
            assert limit == 4
            digest = hashlib.sha256(content).hexdigest()
            return ({"id": comparison, "producing_run_id": identifier, "created_at": now, "content_digest": digest, "storage_locator": "sha256/fixture"},)

    monkeypatch.setattr(api_module.ArtifactStore, "read", lambda *_: content)
    client = _client(settings, catalog, monkeypatch, Persisted())
    payload = client.get("/api/workbench/overview").json()

    assert payload["activeRunCount"] == 2
    assert payload["recentRuns"][0]["id"] == str(identifier)
    assert payload["recentRuns"][0]["failure"] == {"code": "TRACE_STORAGE_FAILURE", "retryable": True}
    assert payload["recentComparisons"] == [{"artifactId": str(comparison), "runId": str(identifier), "createdAt": now.isoformat().replace("+00:00", "Z"), "mode": "candidate", "axis": "quality", "recommendation": "CANDIDATE_ELIGIBLE"}]


def test_comparison_projection_skips_digest_mismatch_and_malformed_content() -> None:
    identifier = UUID("12345678-1234-5678-1234-567812345678")
    now = datetime(2026, 9, 12, tzinfo=timezone.utc)

    class Comparisons(_OverviewRepository):
        async def list_workbench_comparisons(self, limit: int = 4):
            array = b"[]"
            null = b"null"
            invalid = b'{"schema_version":"EvaluationComparison/v1","mode":7,"recommendation":"CANDIDATE_ELIGIBLE"}'
            return (
                {"id": identifier, "producing_run_id": identifier, "created_at": now, "content_digest": "a" * 64, "storage_locator": "bad-digest"},
                {"id": UUID("12345678-1234-5678-1234-567812345679"), "producing_run_id": identifier, "created_at": now, "content_digest": hashlib.sha256(b"not json").hexdigest(), "storage_locator": "bad-json"},
                {"id": UUID("12345678-1234-5678-1234-567812345680"), "producing_run_id": identifier, "created_at": now, "content_digest": hashlib.sha256(array).hexdigest(), "storage_locator": "array"},
                {"id": UUID("12345678-1234-5678-1234-567812345681"), "producing_run_id": identifier, "created_at": now, "content_digest": hashlib.sha256(null).hexdigest(), "storage_locator": "null"},
                {"id": UUID("12345678-1234-5678-1234-567812345682"), "producing_run_id": identifier, "created_at": now, "content_digest": hashlib.sha256(invalid).hexdigest(), "storage_locator": "invalid"},
            )

    async def health() -> HealthReport:
        return HealthReport.create("test", [], [])

    contents = {"bad-json": b"not json", "array": b"[]", "null": b"null", "invalid": b'{"schema_version":"EvaluationComparison/v1","mode":7,"recommendation":"CANDIDATE_ELIGIBLE"}'}
    result = __import__("asyncio").run(WorkbenchOverviewService(health, Comparisons(), lambda _digest, locator: contents.get(locator, b"different")).read())
    assert result.recentComparisons == ()
