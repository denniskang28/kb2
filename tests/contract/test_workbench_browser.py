from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import socket
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
_INGESTION_RUN = "12345678-1234-5678-1234-567812345680"
_ARTIFACT = "12345678-1234-5678-1234-567812345681"
_VISUAL_RUN = "12345678-1234-5678-1234-567812345682"
_EVALUATION_DATASET = "12345678-1234-5678-1234-567812345690"
_EVALUATION_RUN = "12345678-1234-5678-1234-567812345691"


@fixture_app.put("/api/workbench/documents/preflight")
async def fixture_document_preflight(request: Request) -> JSONResponse:
    profile = request.headers["x-profile-id"]
    assert profile in {"fixture-ingestion", "external-ingestion"}
    assert request.headers["x-filename"] == "fixture.pdf"
    assert await request.body() == b"%PDF-fixture"
    return JSONResponse({
        "contractVersion": "workbench-document-preflight/v1", "token": "fixture-token", "workspaceProfileId": profile,
        "detected": {"media_type": "application/pdf", "extension": "pdf", "byte_size": 12},
        "automatic": {"candidateProfileIds": (["fixture-default", "fixture-ingestion"] if profile == "fixture-ingestion" else [profile]), "evaluatedRules": [{"rule_id": "pdf", "matched": True}], "selectedProfileId": profile, "selectionTier": "preflight"},
        "planDigest": "d" * 64, "stages": [{"key": "extraction.parse", "candidates": [{"pluginId": "parser.fixture@1", "capabilities": []}]}],
        "disclosure": {"externalStages": ([{"stage": "extraction.parse", "pluginId": "parser.external@1", "capability": "external.fixture", "message": "文档内容可能发送到该外部提供方。"}] if profile == "external-ingestion" else []), "localPersistence": "提交后内容作为本地 Artifact 持久化。"},
    })


@fixture_app.post("/api/workbench/documents/preflights/fixture-token/runs")
async def fixture_document_submit(request: Request) -> JSONResponse:
    value = await request.json()
    assert value in ({"profileId": "fixture-default", "acknowledgeExternal": False}, {"profileId": "external-ingestion", "acknowledgeExternal": True})
    return JSONResponse({"contractVersion": "workbench-ingestion-receipt/v1", "runId": _VISUAL_RUN, "profileId": value["profileId"], "planDigest": "d" * 64}, status_code=202)


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


@fixture_app.get("/api/workbench/ingestion-runs/{run_id}")
async def fixture_ingestion_run(run_id: str) -> JSONResponse:
    if run_id == _VISUAL_RUN:
        return JSONResponse({
            "id": run_id, "state": "RUNNING", "planDigest": "d" * 64,
            "actions": {"stop": True, "rerun": True, "artifact": True},
            "stages": [
                {"stageKey": "extraction.parse", "attempt": 1, "state": "FAILED", "result": "FAILED", "selection": "rejected", "pluginId": "parser.fixture@1", "failure": {"code": "PLUGIN_TIMEOUT"}, "outputs": []},
                {"stageKey": "extraction.parse", "attempt": 2, "state": "SUCCEEDED", "result": "SUCCEEDED", "selection": "accepted", "pluginId": "parser.fixture@1", "inputs": [{"id": "12345678-1234-5678-1234-567812345683", "artifactType": "opaque.bytes"}], "startedAt": "2026-09-13T01:02:03Z", "endedAt": "2026-09-13T01:02:04Z", "metrics": [{"name": "latency_ms", "value": 12}], "quality": [{"name": "parse_quality", "status": "PASS", "value": "native"}], "failure": None, "outputs": [{"id": _ARTIFACT, "artifactType": "canonical.document"}]},
                {"stageKey": "structure.main", "attempt": 1, "state": "SKIPPED", "result": "SKIPPED", "selection": "rejected", "pluginId": "structure.fixture@1", "failure": None, "outputs": []},
                {"stageKey": "chunking.main", "attempt": 1, "state": "RUNNING", "result": None, "selection": None, "pluginId": "chunker.fixture@1", "failure": None, "outputs": []},
            ],
        })
    assert run_id == _INGESTION_RUN
    return JSONResponse({
        "id": run_id, "state": "SUCCEEDED", "planDigest": "c" * 64,
        "actions": {"stop": False, "rerun": True, "artifact": True},
        "stages": [{"stageKey": "normalize.document", "attempt": 1,
                    "state": "SUCCEEDED", "result": "SUCCEEDED",
                    "selection": None, "failure": None, "outputs": [{
                        "id": _ARTIFACT, "artifactType": "canonical.document",
                    }]}],
    })


@fixture_app.post("/api/workbench/ingestion-runs/{run_id}/rerun-preflight")
async def fixture_rerun_preflight(run_id: str, request: Request) -> JSONResponse:
    assert run_id == _INGESTION_RUN
    assert await request.json() == {"workspaceProfileId": "fixture-ingestion"}
    return JSONResponse({"token": "rerun-token", "workspaceProfileId": "fixture-ingestion", "sourceArtifactId": _ARTIFACT,
                         "automatic": {"selectedProfileId": "fixture-ingestion"},
                         "disclosure": {"externalStages": []}, "stages": [], "planDigest": "e" * 64})


@fixture_app.get("/api/workbench/artifacts/{artifact_id}")
async def fixture_artifact(artifact_id: str) -> JSONResponse:
    assert artifact_id == _ARTIFACT
    locator_a = {"kind": "pdf", "page_number": 1, "x0": 0, "y0": 0, "x1": .5, "y1": .5}
    locator_b = {"kind": "pdf", "page_number": 1, "x0": .5, "y0": .5, "x1": 1, "y1": 1}
    return JSONResponse({
        "artifactType": "canonical.document", "schemaRevision": "v1",
        "summary": "fixture canonical", "metrics": [], "quality": [], "parents": [],
        "view": {"available": True, "tabs": ["canonical", "tree", "table", "metadata", "lineage"],
                 "elements": [{"id": "elm_a", "text": "First", "locator": locator_a},
                              {"id": "elm_b", "text": "Second", "locator": locator_b}],
                 "tables": []},
    })


@fixture_app.get("/api/workbench/query-lab/options")
async def fixture_query_options() -> JSONResponse:
    return JSONResponse({"profiles": [{"profileId": "browser-query", "updatedAt": "2026-09-13T00:00:00Z"}],
                         "indexes": [{"id": _ARTIFACT, "summary": "fixture indexed Artifact"}]})


@fixture_app.post("/api/workbench/query-lab/preflights")
async def fixture_query_preflight() -> JSONResponse:
    return JSONResponse({"token": "query-token", "planDigest": "f" * 64,
                         "stages": [{"stageId": "keyword", "kind": "retrieve", "pluginId": "retriever.keyword@1"}],
                         "disclosure": {"externalStages": [{"stage": "generate", "capability": "generation.default"}]}})


@fixture_app.post("/api/workbench/query-lab/preflights/query-token/runs")
async def fixture_query_submit() -> JSONResponse:
    return JSONResponse({"runId": "12345678-1234-5678-1234-567812345689", "planDigest": "f" * 64}, status_code=202)


@fixture_app.get("/api/workbench/query-runs/{run_id}")
async def fixture_query_run(run_id: str) -> JSONResponse:
    assert run_id == "12345678-1234-5678-1234-567812345689"
    locator = {"kind": "pdf", "page_number": 1, "x0": 0, "y0": 0, "x1": .5, "y1": .5}
    return JSONResponse({"id": run_id, "state": "SUCCEEDED", "terminalState": "SUCCEEDED", "actions": {"stop": False},
                         "stages": [{"stageKey": "keyword", "attempt": 1, "state": "SUCCEEDED", "pluginId": "retriever.keyword@1"}],
                         "candidates": [{"stageId": "keyword", "available": True, "rows": [{"chunk_id": "chk_fixture", "safe_score": .8}]}],
                         "evidence": [{"citationKey": "cit_fixture", "excerpt": "Long fixture evidence " * 80, "documentId": "doc_fixture", "chunkId": "chk_fixture", "locators": [locator], "contributors": [{"contributor_id": "keyword", "safe_score": .8}], "hierarchy": [], "tableElementIds": [], "sourceArtifactId": _ARTIFACT, "sourceLocator": locator}],
                         "details": [{"kind": "verification", "outcome": "pass", "failureCodes": [], "missingCitationKeys": []}],
                         "final": {"state": "ANSWERED", "answer": "Evidence-bound fixture answer", "citationKeys": ["cit_fixture"], "action": None}})


def _evaluation_dataset() -> dict[str, object]:
    slices = {"format":"pdf","processing_class":"native","native_ocr":"native","structure":"prose","language":"zh","question_class":"lookup","difficulty":"low","criticality":"high"}
    return {"id": _EVALUATION_DATASET, "revision": 1, "revisionId": "12345678-1234-5678-1234-567812345692", "digest": "e" * 64,
            "createdAt": "2026-09-13T00:00:00Z", "annotationCount": 0, "queryCaseCount": 1, "reviewedCount": 0, "caseCount": 1,
            "validation": {"qcase_0123456789abcdef": []}, "content": {"schema_revision": "GoldenDataset/v1", "taxonomy": {"schema_version":"SliceTaxonomy/v1", "dimensions": {}}, "annotations": [],
            "query_cases": [{"id":"qcase_0123456789abcdef", "source":{"id":_ARTIFACT,"content_digest":"a" * 64,"schema_revision":"v1","artifact_type":"canonical.document"}, "slices":slices,
            "provenance":{"origin":"generated","operation":"generated","created_at":"2026-09-13T00:00:00Z"}, "reviews":[], "question":"fixture question", "evidence":None, "answerability":"unanswerable", "expected_facts":[], "forbidden_facts":[], "relevant_evidence_ids":[], "required_citation_keys":[], "deterministic_answer":None}]}}


@fixture_app.get("/api/workbench/evaluation-datasets")
async def fixture_evaluation_datasets() -> JSONResponse:
    item = _evaluation_dataset()
    return JSONResponse([{key: item[key] for key in ("id", "revision", "revisionId", "digest", "createdAt", "annotationCount", "queryCaseCount", "reviewedCount", "caseCount")}])


@fixture_app.get("/api/workbench/evaluation-datasets/{dataset_id}")
async def fixture_evaluation_dataset(dataset_id: str) -> JSONResponse:
    assert dataset_id == _EVALUATION_DATASET
    return JSONResponse(_evaluation_dataset())


@fixture_app.put("/api/workbench/evaluation-datasets/{dataset_id}")
async def fixture_evaluation_dataset_save(dataset_id: str, request: Request) -> JSONResponse:
    assert dataset_id == _EVALUATION_DATASET
    assert "GoldenDataset/v1" in (await request.body()).decode()
    return JSONResponse({"valid": True, "dataset": _evaluation_dataset()})


@fixture_app.post("/api/workbench/evaluation-datasets/{dataset_id}/revisions/{revision}/cases/{case_id}/review")
async def fixture_evaluation_review(dataset_id: str, revision: int, case_id: str, request: Request) -> JSONResponse:
    assert (dataset_id, revision, case_id) == (_EVALUATION_DATASET, 1, "qcase_0123456789abcdef")
    assert (await request.json())["reviewer"] == "fixture.reviewer"
    return JSONResponse({"valid": True, "dataset": _evaluation_dataset()})


@fixture_app.get("/api/workbench/evaluation-runs")
async def fixture_evaluation_runs() -> JSONResponse:
    return JSONResponse([{ "id": _EVALUATION_RUN, "state": "FAILED", "terminalState": "FAILED", "createdAt": "2026-09-13T00:00:00Z", "startedAt": "2026-09-13T00:00:00Z", "endedAt": "2026-09-13T00:01:00Z", "planDigest": "f" * 64 }])


@fixture_app.get("/api/workbench/evaluation-runs/{run_id}")
async def fixture_evaluation_run(run_id: str) -> JSONResponse:
    assert run_id == _EVALUATION_RUN
    return JSONResponse({"id": run_id, "state": "FAILED", "terminalState": "FAILED", "planDigest": "f" * 64,
        "manifest": {"artifactId": _ARTIFACT, "digest": "a" * 64, "value": {"schema_version":"EvaluationManifest/v1", "dataset_snapshot_digest":"d" * 64}},
        "report": {"artifactId": _ARTIFACT, "digest": "a" * 64, "value": {"layers":{"ingestion":["m1"],"retrieval":["m2"],"answer":["m3"],"citation":[],"decision":["m4"],"latency":["m5"],"resources":["m6"]}, "gate_results":[{"state":"FAILED","state_counts":{"insufficient_labels":1}}]}},
        "navigation": {"artifactId": _ARTIFACT, "digest": "a" * 64, "value": {"links":[{"case_id":"qcase_0123456789abcdef", "source_artifact_id":_ARTIFACT, "evidence_artifact_id":_ARTIFACT, "generation_artifact_id":_ARTIFACT, "verification_artifact_id":_ARTIFACT}]}}, "unavailable": []})


@fixture_app.get("/workbench/assets/{asset_name}")
async def fixture_asset(asset_name: str) -> FileResponse:
    media_type = {"workbench.js": "text/javascript", "workbench.css": "text/css", "artifact.css": "text/css"}.get(asset_name)
    if media_type is None:
        return FileResponse(STATIC_ROOT / "index.html", status_code=404, media_type="text/html")
    return FileResponse(STATIC_ROOT / asset_name, media_type=media_type)


@fixture_app.get("/workbench/{path:path}")
async def fixture_shell(path: str) -> FileResponse:
    return FileResponse(STATIC_ROOT / "index.html", media_type="text/html")


def _cdp(port: int, expression: str, *, await_promise: bool = False, target_url: str | None = None) -> object:
    for _ in range(60):
        try:
            pages = httpx.get(f"http://127.0.0.1:{port}/json", timeout=0.2).json()
            if any(page.get("type") == "page" and (page.get("url") == target_url if target_url else "/workbench/" in page.get("url", "")) for page in pages):
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    else:
        pytest.fail("Chrome DevTools endpoint did not start")
    page = next(page for page in pages if page.get("type") == "page" and (page.get("url") == target_url if target_url else "/workbench/" in page.get("url", "")))
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


def _capture_cdp(port: int, target: Path, *, target_url: str | None = None) -> None:
    pages = httpx.get(f"http://127.0.0.1:{port}/json", timeout=1).json()
    page = next(page for page in pages if page.get("type") == "page" and (page.get("url") == target_url if target_url else "/workbench/" in page.get("url", "")))
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


def _free_local_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _launch_isolated_chrome(arguments: list[str]) -> subprocess.Popen[str]:
    """Start an isolated Chrome instance rather than handing off to macOS's app singleton."""
    command = [str(CHROME), *arguments]
    if sys.platform == "darwin":
        command = ["open", "-na", "Google Chrome", "--args", *arguments]
    return subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _close_isolated_chrome(port: int, browser: subprocess.Popen[str]) -> tuple[str, str]:
    """Close the CDP-owned app on macOS; the launcher process may already have exited."""
    try:
        version = httpx.get(f"http://127.0.0.1:{port}/json/version", timeout=1).json()
        socket = websocket.create_connection(version["webSocketDebuggerUrl"], origin="http://localhost")
        try:
            socket.send(json.dumps({"id": 1, "method": "Browser.close"}))
            socket.recv()
        finally:
            socket.close()
    except (httpx.HTTPError, OSError, KeyError, websocket.WebSocketException):
        pass
    if browser.poll() is None:
        browser.terminate()
    try:
        return browser.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        browser.kill()
        return browser.communicate(timeout=10)


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


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for browser shell evidence",
)
@pytest.mark.parametrize("width", (1440, 644))
def test_fixture_backed_ingestion_artifact_inspector_sync_and_escape(tmp_path: Path, width: int) -> None:
    """Validate S-024 stable object/source selection and narrow drawer closure."""
    port, debug_port = "8896", "9227"
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", port],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment,
    )
    browser = subprocess.Popen(
        [str(CHROME), "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--remote-allow-origins=*", f"--remote-debugging-port={debug_port}", f"--window-size={width},900", f"--user-data-dir={tmp_path / 'artifact'}", f"http://127.0.0.1:{port}/workbench/runs?run={_INGESTION_RUN}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        expression = """(async () => { const wait = async predicate => { for (let i = 0; i < 100; i++) { const value = predicate(); if (value) return value; await new Promise(r => setTimeout(r, 25)); } throw new Error('Artifact fixture did not become ready'); }; const action = await wait(() => [...document.querySelectorAll('button')].find(x => x.textContent.includes('Artifact canonical.document'))); action.click(); const sourcePane = await wait(() => document.querySelector('.artifact-inspector .source-view')); const drawer = sourcePane.closest('.artifact-inspector'); const source = sourcePane.querySelector('button'); const object = drawer.querySelector('.inspector-list button'); source.click(); const sourceSync = drawer.querySelectorAll('[data-stable-id].source-selected').length === 2; object.click(); const objectSync = drawer.querySelectorAll('[data-stable-id].source-selected').length === 2; return {sourceSync, objectSync, panes: !!drawer.querySelector('.inspector-list') && !!drawer.querySelector('.source-view'), overflow: document.documentElement.scrollWidth <= innerWidth, modal: innerWidth >= 900 || document.querySelector('.artifact-inspector').getAttribute('role') === 'dialog'}; })()"""
        assert _cdp(int(debug_port), expression, await_promise=True) == {"sourceSync": True, "objectSync": True, "panes": True, "overflow": True, "modal": True}
        _capture_cdp(int(debug_port), tmp_path / f"ingestion-artifact-{width}.png")
        assert _cdp(int(debug_port), "(async () => { document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true})); await new Promise(r => setTimeout(r, 30)); return {closed: !document.querySelector('.artifact-inspector'), focusReturned: document.activeElement.textContent.includes('Artifact canonical.document')}; })()", await_promise=True) == {"closed": True, "focusReturned": True}
        assert _cdp(int(debug_port), "window.prompt = () => 'fixture-ingestion'; [...document.querySelectorAll('button')].find(x => x.textContent === '重新运行').click(); true") is True
        for _ in range(100):
            pages = httpx.get(f"http://127.0.0.1:{debug_port}/json", timeout=1).json()
            if any(page.get("url", "").endswith("/workbench/documents") for page in pages):
                break
            time.sleep(.025)
        else:
            pytest.fail("Rerun handoff did not navigate to Documents")
        assert _cdp(int(debug_port), "({ready:document.body.innerText.includes('rerun-token'),source:document.body.innerText.includes('12345678-1234-5678-1234-567812345681'),profile:document.querySelector('input[aria-label=\"Ingestion Profile Set ID\"]')?.value === 'fixture-ingestion',confirmable:[...document.querySelectorAll('button')].some(x => x.textContent === '创建新 Run'),overflow:document.documentElement.scrollWidth <= innerWidth})") == {"ready": True, "source": True, "profile": True, "confirmable": True, "overflow": True}
    finally:
        browser.terminate()
        browser.wait(timeout=10)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for S-024 visual evidence",
)
@pytest.mark.parametrize("width", (1440, 644))
def test_fixture_backed_document_preflight_and_ingestion_state_matrix(tmp_path: Path, width: int) -> None:
    """Capture the shipped Documents and Runs workflows against API projections."""
    port, debug_port = "8897", "9228"
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", port],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment,
    )
    browser = subprocess.Popen(
        [str(CHROME), "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--remote-allow-origins=*", f"--remote-debugging-port={debug_port}", f"--window-size={width},900", f"--user-data-dir={tmp_path / 'documents'}", f"http://127.0.0.1:{port}/workbench/documents"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        preflight = """(async () => { const wait = async predicate => { for (let i = 0; i < 100; i++) { const value = predicate(); if (value) return value; await new Promise(r => setTimeout(r, 25)); } throw new Error('Documents fixture did not become ready'); }; await wait(() => document.querySelector('input[aria-label="Ingestion Profile Set ID"]') && document.querySelector('input[type=file]')); const profile = document.querySelector('input[aria-label="Ingestion Profile Set ID"]'); profile.value = 'fixture-ingestion'; const file = document.querySelector('input[type=file]'); const transfer = new DataTransfer(); transfer.items.add(new File(['%PDF-fixture'], 'fixture.pdf', {type:'application/pdf'})); Object.defineProperty(file, 'files', {value: transfer.files, configurable: true}); [...document.querySelectorAll('button')].find(x => x.textContent === '预检').click(); await wait(() => document.body.innerText.includes('预检与自动选择')); let choice=document.querySelector('select[aria-label="显式 Ingestion Profile"]'); const automatic=choice.value==='fixture-ingestion' && [...choice.options].some(x=>x.value==='fixture-default'); choice.value='fixture-default'; [...document.querySelectorAll('button')].find(x => x.textContent === '预检').click(); await wait(() => document.querySelector('select[aria-label="显式 Ingestion Profile"]')?.value === 'fixture-ingestion'); choice=document.querySelector('select[aria-label="显式 Ingestion Profile"]'); choice.value='fixture-default'; return {automatic, explicit:choice.value==='fixture-default', preserved:profile.value==='fixture-ingestion' && document.body.innerText.includes('Profile Set: fixture-ingestion'), submit: !![...document.querySelectorAll('button')].find(x => x.textContent === '创建新 Run'), overflow: document.documentElement.scrollWidth <= innerWidth}; })()"""
        assert _cdp(int(debug_port), preflight, await_promise=True) == {"automatic": True, "explicit": True, "preserved": True, "submit": True, "overflow": True}
        _capture_cdp(int(debug_port), tmp_path / f"document-preflight-automatic-{width}.png")

        assert _cdp(int(debug_port), "[...document.querySelectorAll('button')].find(x => x.textContent === '创建新 Run').click(); true") is True
        for _ in range(100):
            pages = httpx.get(f"http://127.0.0.1:{debug_port}/json", timeout=1).json()
            if any(page.get("url", "").endswith(f"/workbench/runs?run={_VISUAL_RUN}") for page in pages):
                break
            time.sleep(.025)
        else:
            pytest.fail("Explicit Profile Run receipt navigation did not occur")
        assert _cdp(int(debug_port), "location.href='/workbench/documents'; true") is True
        for _ in range(100):
            pages = httpx.get(f"http://127.0.0.1:{debug_port}/json", timeout=1).json()
            if any(page.get("url", "").endswith("/workbench/documents") for page in pages):
                break
            time.sleep(.025)
        else:
            pytest.fail("Documents did not reopen after explicit Profile submission")

        external = """(async () => { const profile = document.querySelector('input[aria-label="Ingestion Profile Set ID"]'), file=document.querySelector('input[type=file]'), transfer=new DataTransfer(); transfer.items.add(new File(['%PDF-fixture'], 'fixture.pdf', {type:'application/pdf'})); Object.defineProperty(file, 'files', {value: transfer.files, configurable: true}); profile.value = 'external-ingestion'; [...document.querySelectorAll('button')].find(x => x.textContent === '预检').click(); for (let i = 0; i < 100; i++) { const checkbox = document.querySelector('input[aria-label="确认外部阶段披露"]'); const submit = [...document.querySelectorAll('button')].find(x => x.textContent === '创建新 Run'); if (checkbox && submit) { const blocked = submit.disabled; checkbox.click(); return {external: document.body.innerText.includes('parser.external@1'), blocked, enabled: !submit.disabled}; } await new Promise(r => setTimeout(r, 25)); } throw new Error('External disclosure did not render'); })()"""
        assert _cdp(int(debug_port), external, await_promise=True) == {"external": True, "blocked": True, "enabled": True}

        assert _cdp(int(debug_port), "[...document.querySelectorAll('button')].find(x => x.textContent === '创建新 Run').click(); true") is True
        for _ in range(100):
            pages = httpx.get(f"http://127.0.0.1:{debug_port}/json", timeout=1).json()
            if any(page.get("url", "").endswith(f"/workbench/runs?run={_VISUAL_RUN}") for page in pages):
                break
            time.sleep(.025)
        else:
            pytest.fail("Run receipt navigation did not occur")
        states = """(async () => { for (let i = 0; i < 100; i++) { const text = document.body.innerText, buttons = [...document.querySelectorAll('button')].map(x => x.textContent); if (text.includes('Run RUNNING') && text.includes('FAILED') && text.includes('SKIPPED') && text.includes('accepted') && text.includes('rejected') && text.includes('parser.fixture@1') && text.includes('structure.fixture@1') && text.includes('chunker.fixture@1') && text.includes('latency_ms') && text.includes('parse_quality') && text.includes('2026-09-13T01:02:03Z')) return {matrix:true, actions:buttons.includes('停止') && buttons.includes('重新运行') && buttons.some(x => x.includes('Artifact canonical.document')) && !buttons.includes('重试'), overflow:document.documentElement.scrollWidth <= innerWidth}; await new Promise(r => setTimeout(r, 25)); } throw new Error('Run-state matrix did not render'); })()"""
        assert _cdp(int(debug_port), states, await_promise=True) == {"matrix": True, "actions": True, "overflow": True}
        _capture_cdp(int(debug_port), tmp_path / f"ingestion-running-failed-skipped-fallback-retry-{width}.png")
    finally:
        browser.terminate()
        browser.wait(timeout=10)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for S-025 visual evidence",
)
@pytest.mark.parametrize("width", (1440, 644))
def test_fixture_backed_query_lab_evidence_locator_and_narrow_layout(tmp_path: Path, width: int) -> None:
    port, debug_port = "8898", _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", port], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
    try:
        for _ in range(60):
            try:
                if httpx.get(f"http://127.0.0.1:{port}/api/workbench/query-lab/options", timeout=.2).is_success:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(.05)
        else:
            pytest.fail("Query Lab fixture server did not start")
    except BaseException:
        server.terminate()
        server.wait(timeout=10)
        raise
    url = f"http://127.0.0.1:{port}/workbench/query"
    for _ in range(60):
        try:
            if httpx.get(url, timeout=.2).is_success:
                break
        except httpx.HTTPError:
            pass
        time.sleep(.05)
    else:
        server.terminate()
        server.wait(timeout=10)
        pytest.fail("Query Lab fixture shell did not start")
    browser = _launch_isolated_chrome([
        "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run",
        "--remote-allow-origins=*", f"--remote-debugging-port={debug_port}",
        f"--window-size={width},900", f"--user-data-dir={tmp_path / 'query-profile'}", url,
    ])
    try:
        expression = """(async () => { const wait = async (label,p) => { for(let i=0;i<100;i++){const v=p();if(v)return v;await new Promise(r=>setTimeout(r,25));}throw new Error(`Query Lab fixture did not render: ${label}`); }; await wait('initial controls',()=>document.querySelector('textarea[aria-label="问题"]') && document.querySelector('select[aria-label="已索引 Artifact"] option')); document.querySelector('textarea[aria-label="问题"]').value='long question'; [...document.querySelectorAll('button')].find(x=>x.textContent==='预检').click(); await wait('preflight',()=>document.body.innerText.includes('已解析计划')); const ack=document.querySelector('input[aria-label="确认外部阶段披露"]'),submit=[...document.querySelectorAll('button')].find(x=>x.textContent==='创建 Query Run'); const blocked=submit.disabled; ack.click(); submit.click(); const citation=await wait('run result',()=>[...document.querySelectorAll('button')].find(x=>x.textContent==='cit_fixture')); citation.click(); const drawer=await wait('source inspector',()=>document.querySelector('.artifact-inspector')); const selected=await wait('source locator selection',()=>drawer.querySelectorAll('.source-selected').length===2); return {blocked, answer:document.body.innerText.includes('Evidence-bound fixture answer'), candidates:document.body.innerText.includes('chk_fixture'), selected, overflow:document.documentElement.scrollWidth<=innerWidth}; })()"""
        assert _cdp(int(debug_port), expression, await_promise=True, target_url=url) == {"blocked": True, "answer": True, "candidates": True, "selected": True, "overflow": True}
        _capture_cdp(int(debug_port), tmp_path / f"query-evidence-{width}.png", target_url=url)
        assert _cdp(int(debug_port), "(async()=>{document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await new Promise(r=>setTimeout(r,30));return !document.querySelector('.artifact-inspector')})()", await_promise=True, target_url=url) is True
    finally:
        stdout, stderr = _close_isolated_chrome(int(debug_port), browser)
        assert not stdout and not stderr
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for S-026 visual evidence",
)
@pytest.mark.parametrize("width", (1440, 644))
def test_fixture_backed_evaluation_dataset_and_run_states(tmp_path: Path, width: int) -> None:
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
    dataset_url = f"http://127.0.0.1:{port}/workbench/evaluation-dataset"
    browser = _launch_isolated_chrome(["--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--remote-allow-origins=*", f"--remote-debugging-port={debug_port}", f"--window-size={width},900", f"--user-data-dir={tmp_path / 'evaluation'}", dataset_url])
    try:
        dataset = """(async()=>{const wait=async p=>{for(let i=0;i<100;i++){const v=p();if(v)return v;await new Promise(r=>setTimeout(r,25));}throw new Error('dataset did not render')};const row=await wait(()=>[...document.querySelectorAll('button')].find(x=>x.textContent.includes('r1 / 0/1')));row.click();await wait(()=>document.querySelector('textarea[aria-label=\"评估数据集 Schema\"]'));window.prompt=()=> 'fixture.reviewer';[...document.querySelectorAll('button')].find(x=>x.textContent==='标记已审核').click();return {generated:document.body.innerText.includes('待审核'),review:document.body.innerText.includes('标记已审核'),overflow:document.documentElement.scrollWidth<=innerWidth}})()"""
        assert _cdp(debug_port, dataset, await_promise=True, target_url=dataset_url) == {"generated": True, "review": True, "overflow": True}
        _capture_cdp(debug_port, tmp_path / f"evaluation-dataset-{width}.png", target_url=dataset_url)
        run_url = f"http://127.0.0.1:{port}/workbench/evaluation-run?run={_EVALUATION_RUN}"
        assert _cdp(debug_port, f"location.href='{run_url}'; true", target_url=dataset_url) is True
        run = """(async()=>{for(let i=0;i<100;i++){const text=document.body.innerText;if(text.includes('不可变 Manifest')&&text.includes('ingestion: 1 个报告')&&text.includes('质量门禁与 Judge 校准'))return {failed:text.includes('FAILED'),evidence:[...document.querySelectorAll('button')].some(x=>x.textContent==='source_artifact_id'),overflow:document.documentElement.scrollWidth<=innerWidth};await new Promise(r=>setTimeout(r,25));}throw new Error('run did not render')})()"""
        assert _cdp(debug_port, run, await_promise=True, target_url=run_url) == {"failed": True, "evidence": True, "overflow": True}
        _capture_cdp(debug_port, tmp_path / f"evaluation-run-{width}.png", target_url=run_url)
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)
