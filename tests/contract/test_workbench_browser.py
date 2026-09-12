from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import httpx
import pytest
import websocket
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse


CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
STATIC_ROOT = Path(__file__).parents[2] / "src" / "kb2_runtime" / "workbench" / "static"

_PROFILE = {
    "profileId": "browser-query",
    "kind": "query",
    "updatedAt": "2026-09-12T12:00:00Z",
    "document": {
        "schema_version": "v1",
        "default_profile_id": "browser-query",
        "selection_rules": [],
        "profiles": [{"profile_id": "browser-query", "stages": [{"stage_id": "keyword", "kind": "retrieve", "plugin_id": "retriever.keyword@1", "configuration": {"limit": 8}, "inputs": {"question": "query.question", "index": "search.index"}, "outputs": ["candidates"], "when": None, "max_attempts": None}]}],
    },
}

_PLUGIN = {
    "pluginId": "retriever.keyword@1",
    "kind": "retrieve",
    "runner": "in_process",
    "runnable": False,
    "reason": "RUNNER_UNAVAILABLE",
    "implementationDigest": "a" * 64,
    "inputPorts": [{"name": "question", "artifactType": "query.question", "schemaRevision": "v1", "minItems": 1, "maxItems": 1}],
    "outputPorts": [{"name": "candidates", "artifactType": "retrieval.candidates", "schemaRevision": "v1", "minItems": 1, "maxItems": 1}],
    "configurationSchema": {"type": "object", "properties": {
        "limit": {"type": "integer", "default": 8, "minimum": 1, "maximum": 64},
        "strategy": {"type": "string", "enum": ["plain", "ranked"], "default": "plain"},
        "enabled": {"type": "boolean", "default": True},
        "labels": {"type": "object", "properties": {"corpus": {"type": "string"}}},
    }},
    "capabilities": [], "resourceHints": {"cpu": 1}, "timeoutSeconds": 30,
    "safeExample": {"limit": 8}, "contractTests": [{"state": "SUCCEEDED"}], "recentRuns": [{"state": "FAILED"}],
}


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
compatible_requests: list[dict[str, object]] = []


@fixture_app.get("/api/workbench/overview")
async def fixture_overview(request: Request) -> JSONResponse:
    state = os.getenv("KB2_WORKBENCH_FIXTURE_STATE", "populated")
    if state == "loading":
        await __import__("asyncio").sleep(2)
    return JSONResponse(_fixture("dependency" if state == "dependency" else "populated"))


@fixture_app.get("/api/workbench/profiles")
async def fixture_profiles() -> JSONResponse:
    return JSONResponse([{key: _PROFILE[key] for key in ("profileId", "kind", "updatedAt")}])


@fixture_app.get("/api/workbench/profiles/browser-query")
async def fixture_profile() -> JSONResponse:
    return JSONResponse(_PROFILE)


@fixture_app.post("/api/workbench/profiles/{action}")
async def fixture_profile_action(action: str) -> JSONResponse:
    invalid = action == "compile"
    return JSONResponse({"valid": not invalid, "normalizedDocument": _PROFILE["document"] if not invalid else None,
                         "diagnostics": [] if not invalid else [{"code": "QUERY_PROFILE_PARSE_INVALID", "location": "/profiles/0/stages/0/plugin_id"}],
                         "resolvedPlan": {"fixture": True} if action == "compile" and not invalid else None,
                         "planDigest": "b" * 64 if action == "compile" and not invalid else None})


@fixture_app.get("/api/workbench/plugins")
async def fixture_plugins() -> JSONResponse:
    return JSONResponse([{key: _PLUGIN[key] for key in ("pluginId", "kind", "runner", "runnable", "reason")}])


@fixture_app.post("/api/workbench/plugins/compatible")
async def fixture_compatible_plugins(request: Request) -> JSONResponse:
    value = await request.json()
    compatible_requests.append(value)
    assert value["kind"] == "query"
    assert value["stageId"] == "keyword"
    assert value["document"] == _PROFILE["document"]
    return JSONResponse([{key: _PLUGIN[key] for key in ("pluginId", "kind", "runner", "runnable", "reason")}])


@fixture_app.get("/api/fixture/compatible-requests")
async def fixture_compatible_requests() -> JSONResponse:
    return JSONResponse(compatible_requests)


@fixture_app.get("/api/workbench/plugins/retriever.keyword@1")
async def fixture_plugin() -> JSONResponse:
    return JSONResponse(_PLUGIN)


@fixture_app.get("/workbench/assets/{asset_name}")
async def fixture_asset(asset_name: str) -> FileResponse:
    return FileResponse(STATIC_ROOT / asset_name)


@fixture_app.get("/workbench/{path:path}")
async def fixture_shell(path: str) -> FileResponse:
    return FileResponse(STATIC_ROOT / "index.html")


def _cdp(port: int, expression: str, *, await_promise: bool = False) -> object:
    for _ in range(60):
        try:
            pages = httpx.get(f"http://127.0.0.1:{port}/json", timeout=0.2).json()
            if any("/workbench/" in page.get("url", "") for page in pages):
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    else:
        pytest.fail("Chrome DevTools endpoint did not start")
    page = next(page for page in pages if "/workbench/" in page.get("url", ""))
    socket = websocket.create_connection(page["webSocketDebuggerUrl"], origin="http://localhost")
    try:
        socket.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": expression, "awaitPromise": await_promise, "returnByValue": True}}))
        while True:
            message = json.loads(socket.recv())
            if message.get("id") == 1:
                assert "exceptionDetails" not in message.get("result", {}), message
                return message["result"]["result"].get("value")
    finally:
        socket.close()


def _capture_cdp(port: int, target: Path) -> None:
    pages = httpx.get(f"http://127.0.0.1:{port}/json", timeout=1).json()
    page = next(page for page in pages if "/workbench/" in page.get("url", ""))
    socket = websocket.create_connection(page["webSocketDebuggerUrl"], origin="http://localhost")
    try:
        socket.send(json.dumps({"id": 2, "method": "Page.captureScreenshot", "params": {"format": "png"}}))
        while True:
            message = json.loads(socket.recv())
            if message.get("id") == 2:
                target.write_bytes(base64.b64decode(message["result"]["data"]))
                return
    finally:
        socket.close()


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


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for browser Studio evidence",
)
@pytest.mark.parametrize("width", (1440, 644))
def test_fixture_backed_studio_and_registry_states_are_reachable_without_overflow(tmp_path: Path, width: int) -> None:
    """Exercise valid, invalid, draft, unavailable, and inspector states in shipped assets."""
    port, debug_port = "8895", "9226"
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", port],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment,
    )
    browser = subprocess.Popen(
        [str(CHROME), "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--remote-allow-origins=*", f"--remote-debugging-port={debug_port}", f"--window-size={width},900", f"--user-data-dir={tmp_path / 'profile'}", f"http://127.0.0.1:{port}/workbench/studio"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    click_profile = """(async () => { const wait = async predicate => { for (let i = 0; i < 100; i++) { const value = predicate(); if (value) return value; await new Promise(r => setTimeout(r, 50)); } throw new Error('Studio fixture did not become ready'); }; const profile = await wait(() => [...document.querySelectorAll('button')].find(x => x.textContent === 'browser-query')); profile.click(); await wait(() => document.querySelector('select[aria-label=\"keyword 插件\"]')); return {overflow: document.documentElement.scrollWidth <= innerWidth, selector: !!document.querySelector('select[aria-label=\"keyword 插件\"]')}; })()"""
    try:
        assert _cdp(int(debug_port), click_profile, await_promise=True) == {"overflow": True, "selector": True}
        controls = """(async () => { const wait = async predicate => { for (let i = 0; i < 100; i++) { const value = await predicate(); if (value) return value; await new Promise(r => setTimeout(r, 50)); } throw new Error('Studio schema controls did not become ready'); }; await wait(async () => { const requests = await fetch('/api/fixture/compatible-requests').then(r => r.json()); return document.querySelector('input[aria-label=\"keyword limit\"]') && document.querySelector('select[aria-label=\"keyword strategy\"]') && document.querySelector('input[aria-label=\"keyword enabled\"]') && document.querySelector('input[aria-label=\"keyword labels 对象\"]') && requests.length; }); const requests = await fetch('/api/fixture/compatible-requests').then(r => r.json()); return {schemaScalar: !!document.querySelector('input[aria-label=\"keyword limit\"]'), schemaEnum: !!document.querySelector('select[aria-label=\"keyword strategy\"]'), schemaBoolean: !!document.querySelector('input[aria-label=\"keyword enabled\"]'), boundedObject: !!document.querySelector('input[aria-label=\"keyword labels 对象\"]'), compatibleOnly: [...document.querySelector('select[aria-label=\"keyword 插件\"]').options].every(x => x.value === 'retriever.keyword@1'), postedCanonicalContext: requests.some(x => x.kind === 'query' && x.stageId === 'keyword' && x.document.default_profile_id === 'browser-query')}; })()"""
        assert _cdp(int(debug_port), controls, await_promise=True) == {"schemaScalar": True, "schemaEnum": True, "schemaBoolean": True, "boundedObject": True, "compatibleOnly": True, "postedCanonicalContext": True}
        assert _cdp(int(debug_port), "(async () => { [...document.querySelectorAll('button')].find(x => x.textContent === '验证').click(); await new Promise(r => setTimeout(r, 150)); return document.body.innerText.includes('配置有效'); })()", await_promise=True) is True
        _capture_cdp(int(debug_port), tmp_path / f"studio-valid-{width}.png")

        # The fixture makes compile return a field-addressable compiler error.
        assert _cdp(int(debug_port), "(async () => { [...document.querySelectorAll('button')].find(x => x.textContent === '编译预览').click(); await new Promise(r => setTimeout(r, 150)); return document.body.innerText.includes('/profiles/0/stages/0/plugin_id: QUERY_PROFILE_PARSE_INVALID'); })()", await_promise=True) is True
        _capture_cdp(int(debug_port), tmp_path / f"studio-invalid-{width}.png")

        draft = """(async () => { [...document.querySelectorAll('button')].find(x => x.textContent === 'YAML').click(); const t = document.querySelector('textarea[aria-label="YAML Profile"]'); t.value += '\\n# draft'; t.dispatchEvent(new Event('input', {bubbles:true})); return {draft: document.body.innerText.includes('需先保存并成功编译'), overflow: document.documentElement.scrollWidth <= innerWidth}; })()"""
        assert _cdp(int(debug_port), draft, await_promise=True) == {"draft": True, "overflow": True}
        _capture_cdp(int(debug_port), tmp_path / f"studio-draft-{width}.png")
    finally:
        browser.terminate()
        browser.wait(timeout=10)
        server.terminate()
        server.wait(timeout=10)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", port],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment,
    )
    browser = subprocess.Popen(
        [str(CHROME), "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--remote-allow-origins=*", f"--remote-debugging-port={debug_port}", f"--window-size={width},900", f"--user-data-dir={tmp_path / 'registry'}", f"http://127.0.0.1:{port}/workbench/plugins"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        expression = """(async () => { const wait = async predicate => { for (let i = 0; i < 100; i++) { const value = predicate(); if (value) return value; await new Promise(r => setTimeout(r, 50)); } throw new Error('Registry fixture did not become ready'); }; const row = await wait(() => [...document.querySelectorAll('button')].find(x => x.textContent.includes('retriever.keyword@1'))); row.click(); const d = await wait(() => { const detail = document.querySelector('.registry-detail'); return detail?.innerText.includes('输出端口') ? detail : null; }); return {unavailable: d.innerText.includes('不可运行: RUNNER_UNAVAILABLE'), detail: d.innerText.includes('输出端口') && d.innerText.includes('安全示例'), overflow: document.documentElement.scrollWidth <= innerWidth, modal: innerWidth >= 900 || d.getAttribute('role') === 'dialog'}; })()"""
        assert _cdp(int(debug_port), expression, await_promise=True) == {"unavailable": True, "detail": True, "overflow": True, "modal": True}
        _capture_cdp(int(debug_port), tmp_path / f"registry-unavailable-detail-{width}.png")
        if width < 900:
            assert _cdp(int(debug_port), "(async () => { document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true})); await new Promise(r => setTimeout(r, 30)); return {closed: !document.querySelector('.registry-detail').classList.contains('open'), focusReturned: document.activeElement.textContent.includes('retriever.keyword@1')}; })()", await_promise=True) == {"closed": True, "focusReturned": True}
    finally:
        browser.terminate()
        browser.wait(timeout=10)
        server.terminate()
        server.wait(timeout=10)
