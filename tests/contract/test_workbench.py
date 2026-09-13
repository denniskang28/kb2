from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
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
    for weight in (400, 600, 800):
        font = client.get(f"/workbench/assets/archivo-{weight}.woff2")
        assert font.status_code == 200
        assert font.headers["content-type"] == "font/woff2"


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


def test_workbench_client_defines_eight_primary_routes_and_shared_overview_snapshot() -> None:
    content = open("src/kb2_runtime/workbench/static/workbench.js", encoding="utf-8").read()
    primary_block = content.split("const PRIMARY_DESTINATIONS=[", 1)[1].split("];", 1)[0]

    assert primary_block.count("{id:") == 8
    for route in ("overview", "documents", "studio", "query", "evaluation-dataset", "compare", "runs", "plugins"):
        assert f"{{id:'{route}'" in primary_block
    assert "evaluation-run" not in primary_block
    assert "'evaluation-run':{label:'评估运行',parent:'evaluation-dataset'}" in content
    assert "aria-current" in content
    assert "fetch('/api/workbench/overview')" in content
    assert content.count("fetch('/api/workbench/overview')") == 1
    assert "innerHTML" not in content
    assert "document.createElementNS" in content
    assert "data-overview-state" in content
    assert "数据可能已过期" in content
    assert "setAttribute('inert','')" in content
    assert "removeAttribute('inert')" in content
    assert "trigger?.focus()" in content
    assert "addEventListener('resize',syncResponsiveNavigation)" in content
    assert "sidebar.querySelector('.nav-link[aria-current=\"page\"]')?.focus()" in content
    assert "unavailableOverview(surface,state.loading)" in content
    assert "^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$" in content
    assert "workspaceIds" not in content
    assert "locale" not in content
    assert "offline" not in content


def test_workbench_visual_tokens_keep_ui_013_and_legacy_surface_contracts() -> None:
    content = open("src/kb2_runtime/workbench/static/workbench.css", encoding="utf-8").read()

    for token in ("--space-1: 4px", "--space-2: 8px", "--space-3: 12px", "--space-4: 16px", "--space-6: 24px", "--space-8: 32px"):
        assert token in content
    assert '--font-body: Archivo, "PingFang SC"' in content
    for weight in (400, 600, 800):
        assert f'url("/workbench/assets/archivo-{weight}.woff2")' in content
        assert f"font-weight: {weight}" in content
    assert "body { margin: 0; background: var(--color-ground)" in content
    assert "--radius-md: 0" in content
    assert "outline: 2px solid var(--color-accent)" in content
    assert "grid-template-columns: 220px minmax(0, 1fr)" in content
    assert "@media (max-width: 899px)" in content
    for alias in ("--ink:", "--muted:", "--rule:", "--panel:", "--accent:", "--blue:", "--teal:", "--red:"):
        assert alias in content
    assert "linear-gradient" not in content


def test_s022_pinned_assets_and_visual_baseline_manifest_are_complete() -> None:
    static_root = Path("src/kb2_runtime/workbench/static")
    font_manifest = json.loads((static_root / "archivo-fonts.manifest.json").read_text(encoding="utf-8"))

    assert font_manifest["commit"] == "b5d63988ce19d044d3e10362de730af00526b672"
    assert font_manifest["licenseFile"] == "LICENSE.archivo.txt"
    license_payload = (static_root / font_manifest["licenseFile"]).read_bytes()
    assert hashlib.sha256(license_payload).hexdigest() == font_manifest["licenseSha256"]
    assert font_manifest["licenseSource"].startswith("https://api.github.com/repos/Omnibus-Type/Archivo/")
    assert {asset["weight"] for asset in font_manifest["assets"]} == {400, 600, 800}
    for asset in font_manifest["assets"]:
        payload = (static_root / asset["file"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == asset["sha256"]
        assert asset["source"].startswith("https://api.github.com/repos/Omnibus-Type/Archivo/")

    lucide_manifest = json.loads((static_root / "lucide-icons.manifest.json").read_text(encoding="utf-8"))
    assert lucide_manifest["version"] == "0.468.0"
    assert lucide_manifest["tag"] == "0.468.0"
    assert lucide_manifest["commit"] == "f12b0de177fbc2a6795e99be065887e72b237123"
    assert lucide_manifest["upstream"] == "https://github.com/lucide-icons/lucide"
    assert lucide_manifest["sourceTemplate"] == "https://api.github.com/repos/lucide-icons/lucide/contents/{sourcePath}?ref=f12b0de177fbc2a6795e99be065887e72b237123"
    assert lucide_manifest["license"] == "ISC"
    lucide_license = (static_root / lucide_manifest["licenseFile"]).read_bytes()
    assert hashlib.sha256(lucide_license).hexdigest() == lucide_manifest["licenseSha256"]
    assert lucide_manifest["licenseSource"].startswith("https://api.github.com/repos/lucide-icons/lucide/")

    script = (static_root / "workbench.js").read_text(encoding="utf-8")
    declarations = script.split("const LUCIDE={\n", 1)[1].split("\n};", 1)[0].splitlines()
    embedded = {line.strip().split(":", 1)[0]: hashlib.sha256(line.strip().encode()).hexdigest() for line in declarations}
    icons = lucide_manifest["icons"]
    assert len(icons) == 18
    assert set(embedded) == {icon["key"] for icon in icons}
    for icon in icons:
        assert embedded[icon["key"]] == icon["embeddedLineSha256"]
        assert icon["sourcePath"] == f"icons/{icon['sourceIcon']}.svg"
        assert len(icon["sourceGitBlobSha1"]) == 40
        assert len(icon["sourceSha256"]) == 64
        assert icon["relationship"]

    baseline_root = Path("tests/visual/baselines/s022")
    visual_manifest = json.loads((baseline_root / "manifest.json").read_text(encoding="utf-8"))
    assert visual_manifest["story"] == "S-022"
    assert visual_manifest["captureConditions"] == {
        "browser": {
            "product": "Chrome/152.0.7977.83",
            "protocolVersion": "1.3",
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/152.0.0.0 Safari/537.36",
            "javascriptRuntime": "V8 15.2.124.21",
            "renderingEngine": "537.36 (@79460ebecaa5625e57a5fb679a735659e73dc687)",
            "headlessMode": "new",
            "gpu": "disabled",
        },
        "device": {"deviceScaleFactor": 1, "mobile": False},
        "media": {
            "type": "screen",
            "colorScheme": "light",
            "forcedColors": "none",
            "reducedMotion": "no-preference",
        },
        "locale": {"browser": "zh-CN", "document": "zh-CN"},
        "readiness": {
            "document": "complete",
            "fontsPromise": "document.fonts.ready",
            "archivoWeights": [400, 600, 800],
            "archivoFaceStatus": "loaded",
            "assetResourceTimingRequired": True,
        },
        "stabilization": {
            "animations": "none",
            "transitions": "none",
            "caretColor": "transparent",
        },
        "screenshotFormat": "png",
    }
    assert visual_manifest["comparison"] == {
        "colorSpace": "RGBA",
        "channelTolerance": 12,
        "maximumDifferingPixelRatio": 0.005,
        "baselineUpdatesAutomatic": False,
    }
    assert len(visual_manifest["baselines"]) == 7
    assert {tuple(item["viewport"]) for item in visual_manifest["baselines"]} == {(1440, 900), (644, 900)}
    for baseline in visual_manifest["baselines"]:
        payload = (baseline_root / baseline["file"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == baseline["sha256"]


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
