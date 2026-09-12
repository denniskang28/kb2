from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse


CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
STATIC_ROOT = Path(__file__).parents[2] / "src" / "kb2_runtime" / "workbench" / "static"


def _fixture(state: str) -> dict[str, object]:
    unavailable = state == "dependency"
    return {
        "contractVersion": "workbench-overview/v1",
        "checkedAt": "2026-09-12T12:00:00Z",
        "coreStatus": "not_ready" if unavailable else "ready",
        "core": [{"id": "postgres", "status": "unavailable" if unavailable else "ready", "code": "CONNECTION_REFUSED" if unavailable else "OK"}],
        "optionalCapabilities": [{"id": "deepseek", "status": "not_configured", "code": "NOT_CONFIGURED", "provider": "deepseek", "model": None, "latencyMs": 0}],
        "plugins": [{"pluginId": "parser.pdf", "runnable": not unavailable, "reason": "RUNNER_UNAVAILABLE" if unavailable else None}],
        "activeRunCount": 1,
        "recentRuns": [{"id": "12345678-1234-5678-1234-567812345678", "engineKind": "evaluation", "state": "FAILED", "terminalState": "FAILED", "createdAt": "2026-09-12T12:00:00Z", "startedAt": "2026-09-12T12:00:00Z", "endedAt": "2026-09-12T12:00:00Z", "planDigest": "a" * 64, "failure": {"code": "TRACE_STORAGE_FAILURE", "retryable": True}}],
        "recentComparisons": [{"artifactId": "12345678-1234-5678-1234-567812345679", "runId": "12345678-1234-5678-1234-567812345678", "createdAt": "2026-09-12T12:00:00Z", "mode": "candidate", "axis": "quality", "recommendation": "CANDIDATE_ELIGIBLE"}],
    }


# Test-only transport: production never returns these sample values. The static
# shell is served byte-for-byte from the implementation under test.
fixture_app = FastAPI()


@fixture_app.get("/api/workbench/overview")
async def fixture_overview(request: Request) -> JSONResponse:
    state = os.getenv("KB2_WORKBENCH_FIXTURE_STATE", "populated")
    if state == "loading":
        await __import__("asyncio").sleep(2)
    return JSONResponse(_fixture("dependency" if state == "dependency" else "populated"))


@fixture_app.get("/workbench/assets/{asset_name}")
async def fixture_asset(asset_name: str) -> FileResponse:
    return FileResponse(STATIC_ROOT / asset_name)


@fixture_app.get("/workbench/{path:path}")
async def fixture_shell(path: str) -> FileResponse:
    return FileResponse(STATIC_ROOT / "index.html")


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for browser shell evidence",
)
@pytest.mark.parametrize(("state", "plugin_runnable"), (("populated", True), ("dependency", False), ("loading", True)))
def test_fixture_backed_workbench_shell_renders_overview_states(tmp_path: Path, state: str, plugin_runnable: bool) -> None:
    """Exercise shipped browser assets with test-only, API-backed overview states."""
    port = "8894"
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    environment["KB2_WORKBENCH_FIXTURE_STATE"] = state
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", port],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment,
    )
    url = f"http://127.0.0.1:{port}/workbench/overview?workspace=local_demo"
    try:
        for _ in range(40):
            try:
                if httpx.get(url, timeout=0.2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            pytest.fail("FastAPI workbench shell did not start")
        payload = httpx.get(f"http://127.0.0.1:{port}/api/workbench/overview", timeout=3).json()
        assert payload["recentRuns"][0]["failure"]["code"] == "TRACE_STORAGE_FAILURE"
        assert payload["recentComparisons"][0]["recommendation"] == "CANDIDATE_ELIGIBLE"
        assert payload["plugins"][0]["runnable"] is plugin_runnable
        for width in (1440, 644):
            image = tmp_path / f"{state}-workbench-{width}.png"
            browser = subprocess.Popen(
                [str(CHROME), "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--disable-crash-reporter", f"--window-size={width},900", f"--screenshot={image}", "--virtual-time-budget=1000", f"--user-data-dir={tmp_path / str(width)}", url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                for _ in range(60):
                    if image.exists() and image.stat().st_size > 1_000:
                        break
                    time.sleep(0.1)
                else:
                    pytest.fail(f"Chrome did not capture fixture state at {width}px")
            finally:
                browser.terminate()
                browser.wait(timeout=10)
    finally:
        server.terminate()
        server.wait(timeout=10)
