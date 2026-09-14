from __future__ import annotations

import base64
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
import pytest
import websocket
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from kb2_runtime.evaluation.datasets.contracts import DEFAULT_TAXONOMY, DatasetContent
from kb2_runtime.evaluation.ingestion import MetricReport, MetricStatus, metric_report_bytes
from kb2_runtime.evaluation.runs.contracts import (
    ArtifactBinding, ConfidencePolicy, EvaluationManifest, EvaluationSubject, FailedCaseLink,
    GateResult, GateState, LayeredReport, NavigationIndex, OperationReport, PlanIdentity,
    QualityGate, RuntimeSummary, canonical_bytes, digest,
)
from kb2_runtime.evaluation.runs.service import EvaluationService
from kb2_runtime.evidence.contracts import ContextDecision, EvidenceShortage
from kb2_runtime.fusion.contracts import CandidateContribution, FusedCandidate, FusionCandidateSet
from kb2_runtime.reranking.contracts import RerankDecision, RerankInputCandidate, RerankedCandidateSet
from kb2_runtime.retrieval.contracts import IndexArtifactBinding, RetrievalCandidate, RetrievalCandidateSet
from kb2_runtime.workbench.evaluation import EvaluationWorkbenchService
from kb2_runtime.workbench.diagnosis import RunHistoryWorkbenchService
from kb2_runtime.workbench.query import QueryWorkbenchService
from kb2_runtime.trace.contracts import ArtifactInput, ArtifactManifest, ArtifactReference, EngineKind, RunState, RunTrace, StageState, StageTrace


CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
STATIC_ROOT = Path(__file__).parents[2] / "src" / "kb2_runtime" / "workbench" / "static"
S022_BASELINE_ROOT = Path(__file__).parents[2] / "tests" / "visual" / "baselines" / "s022"
S022_CAPTURE = json.loads((S022_BASELINE_ROOT / "manifest.json").read_text(encoding="utf-8"))["captureConditions"]
S024_BASELINE_ROOT = Path(__file__).parents[2] / "tests" / "visual" / "baselines" / "s024"
S024_MANIFEST = json.loads((S024_BASELINE_ROOT / "manifest.json").read_text(encoding="utf-8"))
S025_BASELINE_ROOT = Path(__file__).parents[2] / "tests" / "visual" / "baselines" / "s025"
S026_BASELINE_ROOT = Path(__file__).parents[2] / "tests" / "visual" / "baselines" / "s026"
S027_BASELINE_ROOT = Path(__file__).parents[2] / "tests" / "visual" / "baselines" / "s027"
S028_BASELINE_ROOT = Path(__file__).parents[2] / "tests" / "visual" / "baselines" / "s028"
S022_CHROME_FLAGS = (
    f"--headless={S022_CAPTURE['browser']['headlessMode']}",
    "--no-sandbox",
    "--disable-gpu" if S022_CAPTURE["browser"]["gpu"] == "disabled" else "--enable-gpu",
    "--no-first-run",
    f"--lang={S022_CAPTURE['locale']['browser']}",
    "--remote-allow-origins=*",
)
_CAPTURE_CONNECTIONS: dict[int, websocket.WebSocket] = {}
_CDP_REQUEST_ID = 100

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
    payload = {
        "contractVersion": "workbench-overview/v1",
        "checkedAt": "2026-09-12T12:00:00Z",
        "coreStatus": "not_ready" if unavailable else "ready",
        "core": [
            {"id": "postgres", "status": "unavailable" if unavailable else "ready", "code": "CONNECTION_REFUSED" if unavailable else "OK"},
            {"id": "artifact-store", "status": "ready", "code": "OK"},
        ],
        "optionalCapabilities": [
            {"id": "deepseek", "status": "not_configured", "code": "NOT_CONFIGURED", "provider": "deepseek", "model": None, "latencyMs": 0},
            {"id": "runner.container", "status": "unavailable" if unavailable else "ready", "code": "RUNNER_UNAVAILABLE" if unavailable else "OK", "provider": None, "model": None, "latencyMs": 0},
        ],
        "plugins": [
            {"pluginId": "parser.pdf@1", "runnable": not unavailable, "reason": "RUNNER_UNAVAILABLE" if unavailable else None},
            {"pluginId": "retriever.keyword@1", "runnable": True, "reason": None},
        ],
        "activeRunCount": 1,
        "recentRuns": [
            {"id": "12345678-1234-5678-1234-567812345678", "engineKind": "evaluation", "state": "FAILED", "terminalState": "FAILED", "createdAt": "2026-09-12T12:00:00Z", "startedAt": "2026-09-12T11:59:00Z", "endedAt": "2026-09-12T12:00:00Z", "planDigest": "a" * 64, "failure": {"code": "TRACE_STORAGE_FAILURE", "retryable": True}},
            {"id": "22345678-1234-5678-1234-567812345678", "engineKind": "query", "state": "SUCCEEDED", "terminalState": "SUCCEEDED", "createdAt": "2026-09-12T11:00:00Z", "startedAt": "2026-09-12T11:00:00Z", "endedAt": "2026-09-12T11:00:01Z", "planDigest": "b" * 64, "failure": None},
            {"id": "32345678-1234-5678-1234-567812345678", "engineKind": "ingestion", "state": "FAILED", "terminalState": "FAILED", "createdAt": "2026-09-12T10:00:00Z", "startedAt": None, "endedAt": None, "planDigest": "c" * 64, "failure": {"code": "INPUT_INVALID", "retryable": False}},
        ],
        "recentComparisons": [{"artifactId": "12345678-1234-5678-1234-567812345679", "runId": "12345678-1234-5678-1234-567812345678", "createdAt": "2026-09-12T12:00:00Z", "mode": "candidate", "axis": "quality", "recommendation": "CANDIDATE_ELIGIBLE"}],
    }
    if state == "empty":
        payload["activeRunCount"] = 0
        payload["recentRuns"] = []
        payload["recentComparisons"] = []
    return payload


# Test-only transport: production never returns these sample values. The static
# shell is served byte-for-byte from the implementation under test.
fixture_app = FastAPI()
compatible_requests: list[dict[str, object]] = []
_overview_request_count = 0
_overview_release = asyncio.Event()
_retry_preflight_attempts = 0
_preflight_serial = 0
_fixture_preflights: dict[str, dict[str, object]] = {}
_fixture_preflight_receipts: list[dict[str, object]] = []
_document_list_requests = 0
_document_list_stale_armed = False
_document_list_stale_requests = 0
_document_list_completions: list[int] = []
_document_list_release = asyncio.Event()
_ingestion_stop_requests: list[str] = []
_INGESTION_RUN = "12345678-1234-5678-1234-567812345680"
_ARTIFACT = "12345678-1234-5678-1234-567812345681"
_VISUAL_RUN = "12345678-1234-5678-1234-567812345682"
_CHUNK_ARTIFACT = "12345678-1234-5678-1234-567812345684"
_EVALUATION_DATASET = "12345678-1234-5678-1234-567812345690"
_EVALUATION_RUN = "12345678-1234-5678-1234-567812345691"
_QUERY_RUNS = {
    "answered": "12345678-1234-5678-1234-567812345701",
    "clarification": "12345678-1234-5678-1234-567812345702",
    "abstained": "12345678-1234-5678-1234-567812345703",
    "failed": "12345678-1234-5678-1234-567812345704",
    "active": "12345678-1234-5678-1234-567812345708",
    "submit-error": "12345678-1234-5678-1234-567812345710",
    "delayed-submit": "12345678-1234-5678-1234-567812345711",
    "fact-answered": "12345678-1234-5678-1234-567812345712",
    "table-answered-inspector": "12345678-1234-5678-1234-567812345713",
    "hierarchy-answered": "12345678-1234-5678-1234-567812345714",
    "clarification-required": "12345678-1234-5678-1234-567812345715",
    "repair-answered": "12345678-1234-5678-1234-567812345716",
    "repair-exhausted": "12345678-1234-5678-1234-567812345717",
}
_EVALUATION_RUNS = {
    "failed-gates": _EVALUATION_RUN,
    "running": "12345678-1234-5678-1234-567812345705",
    "passed-gates": "12345678-1234-5678-1234-567812345706",
    "invalid-dataset": "12345678-1234-5678-1234-567812345707",
    "status-matrix": "12345678-1234-5678-1234-567812345709",
}
_query_scenarios: dict[str, str] = {}
_active_query_stopped = False
_active_query_reads = 0
_QUERY_CHUNK = "chk_" + "1" * 32
_QUERY_CHUNK_PARENT = "chk_" + "3" * 32
_QUERY_DOCUMENT = "doc_" + "1" * 32
_COMPARISON = "12345678-1234-5678-1234-567812345693"
_COMPARISON_BASELINE = "12345678-1234-5678-1234-567812345694"
_COMPARISON_CANDIDATE = "12345678-1234-5678-1234-567812345695"
_HISTORY_QUERY = "12345678-1234-5678-1234-567812345696"
_COMPARISON_SINGLE = "12345678-1234-5678-1234-567812345697"
_HISTORY_COMPARISON = "12345678-1234-5678-1234-567812345698"
_HISTORY_CONTRACT = "12345678-1234-5678-1234-567812345699"


def _fixture_preview(profile: str, *, selected: str | None = None, tier: str = "preflight") -> dict[str, object]:
    global _preflight_serial
    automatic_selected = "switch-local-profile" if profile == "switch-local" else "switch-external-profile" if profile == "switch-external" else profile
    candidates = {
        "fixture-ingestion": ["fixture-default", "fixture-ingestion"],
        "switch-local": ["switch-local-profile", "switch-external-profile", "switch-delayed", "switch-error"],
        "switch-external": ["switch-external-profile", "switch-local-profile"],
    }.get(profile, [profile])
    selected = selected or automatic_selected
    external = selected in {"external-ingestion", "switch-external-profile"}
    plugin_id = "parser.external@1" if external else "parser.default@1" if selected == "fixture-default" else "parser.fixture@1"
    _preflight_serial += 1
    token = f"fixture-token-{_preflight_serial}-{selected}"
    payload: dict[str, object] = {
        "contractVersion": "workbench-document-preflight/v1", "token": token, "workspaceProfileId": profile,
        "detected": {"media_type": "application/pdf", "extension": "pdf", "byte_size": 12},
        "automatic": {"candidateProfileIds": candidates, "evaluatedRules": [{"rule_id": "pdf", "matched": True}], "selectedProfileId": automatic_selected, "selectionTier": "preflight"},
        "selection": {"profileId": selected, "selectionTier": tier},
        "planDigest": (("e" if external else "d") * 64),
        "stages": [{"key": "extraction.parse", "candidates": [{"pluginId": plugin_id, "capabilities": (["external.fixture"] if external else [])}]}],
        "disclosure": {"externalStages": ([{"stage": "extraction.parse", "pluginId": plugin_id, "capability": "external.fixture", "message": "文档内容可能发送到该外部提供方。"}] if external else []), "localPersistence": "提交后内容作为本地 Artifact 持久化。"},
    }
    _fixture_preflights[token] = {"profileId": selected, "workspaceProfile": profile, "external": external, "planDigest": payload["planDigest"]}
    return payload


@fixture_app.put("/api/workbench/documents/preflight")
async def fixture_document_preflight(request: Request) -> JSONResponse:
    global _retry_preflight_attempts
    profile = request.headers["x-profile-id"]
    assert profile in {"fixture-ingestion", "external-ingestion", "retry-ingestion", "delayed-ingestion", "switch-local", "switch-external"}
    assert request.headers["x-filename"] == "fixture.pdf"
    assert await request.body() == b"%PDF-fixture"
    replaced = request.headers.get("x-replaces-preflight-token")
    if replaced:
        _fixture_preflights.pop(replaced, None)
    if profile == "retry-ingestion":
        _retry_preflight_attempts += 1
        await asyncio.sleep(0.2)
        if _retry_preflight_attempts == 1:
            return JSONResponse({"code": "PREFLIGHT_UNAVAILABLE"}, status_code=503)
    if profile == "delayed-ingestion":
        await asyncio.sleep(0.2)
    return JSONResponse(_fixture_preview(profile))


@fixture_app.post("/api/workbench/documents/preflights/{token}/selection")
async def fixture_document_selection(token: str, request: Request) -> JSONResponse:
    claimed = _fixture_preflights.pop(token, None)
    if claimed is None:
        return JSONResponse({"code": "PREFLIGHT_UNAVAILABLE"}, status_code=404)
    value = await request.json()
    profile_id = value["profileId"]
    if profile_id == "switch-error":
        await asyncio.sleep(0.2)
        return JSONResponse({"code": "PREFLIGHT_SELECTION_UNAVAILABLE"}, status_code=503)
    if profile_id == "switch-delayed":
        await asyncio.sleep(0.2)
    workspace_profile = str(claimed["workspaceProfile"])
    return JSONResponse(_fixture_preview(workspace_profile, selected=profile_id, tier="explicit"))


@fixture_app.post("/api/workbench/documents/preflights/{token}/runs")
async def fixture_document_submit(token: str, request: Request) -> JSONResponse:
    claimed = _fixture_preflights.pop(token, None)
    if claimed is None:
        return JSONResponse({"code": "PREFLIGHT_UNAVAILABLE"}, status_code=404)
    value = await request.json()
    assert value["profileId"] == claimed["profileId"]
    assert value["acknowledgeExternal"] is claimed["external"]
    _fixture_preflight_receipts.append({"token": token, **value})
    return JSONResponse({"contractVersion": "workbench-ingestion-receipt/v1", "runId": _VISUAL_RUN, "profileId": value["profileId"], "planDigest": claimed["planDigest"]}, status_code=202)


@fixture_app.get("/api/fixture/document-preflights")
async def fixture_document_preflights() -> JSONResponse:
    return JSONResponse({"tokens": list(_fixture_preflights), "receipts": _fixture_preflight_receipts})


def _document_list_fixture() -> list[dict[str, object]]:
    return [
        {"sourceArtifactId": _ARTIFACT, "filename": "contract-framework-sample.pdf", "mediaType": "application/pdf", "format": "pdf", "byteSize": 4404019, "documentClass": "native_long_hierarchical", "profileId": "ing.contract-long@3", "registeredAt": "2026-09-14T08:05:00Z", "latestRun": {"id": _INGESTION_RUN, "state": "SUCCEEDED"}, "actions": {"sourceArtifactId": _ARTIFACT, "outputArtifactId": _CHUNK_ARTIFACT}},
        {"sourceArtifactId": "22345678-1234-5678-1234-567812345681", "filename": "equipment-maintenance-scan.pdf", "mediaType": "application/pdf", "format": "pdf", "byteSize": 13421773, "documentClass": "scanned_mixed_zh_en", "profileId": "ing.ocr-mixed@2", "registeredAt": "2026-09-14T08:04:00Z", "latestRun": {"id": _VISUAL_RUN, "state": "FAILED"}, "actions": {"sourceArtifactId": "22345678-1234-5678-1234-567812345681", "outputArtifactId": None}},
        {"sourceArtifactId": "32345678-1234-5678-1234-567812345681", "filename": "quarterly-operations-data.xlsx", "mediaType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "format": "xlsx", "byteSize": 901120, "documentClass": "table_heavy_multi_sheet", "profileId": "ing.table-heavy@1", "registeredAt": "2026-09-14T08:03:00Z", "latestRun": {"id": "32345678-1234-5678-1234-567812345680", "state": "RUNNING"}, "actions": {"sourceArtifactId": "32345678-1234-5678-1234-567812345681", "outputArtifactId": None}},
        {"sourceArtifactId": "42345678-1234-5678-1234-567812345681", "filename": "product-architecture-deck.pptx", "mediaType": "application/vnd.openxmlformats-officedocument.presentationml.presentation", "format": "pptx", "byteSize": 6396313, "documentClass": None, "profileId": "ing.slide-object@1", "registeredAt": "2026-09-14T08:02:00Z", "latestRun": {"id": "42345678-1234-5678-1234-567812345680", "state": "PENDING"}, "actions": {"sourceArtifactId": "42345678-1234-5678-1234-567812345681", "outputArtifactId": None}},
    ]


@fixture_app.get("/api/workbench/documents")
async def fixture_document_list(cursor: str = "") -> JSONResponse:
    global _document_list_requests, _document_list_stale_requests
    _document_list_requests += 1
    state = os.getenv("KB2_DOCUMENT_FIXTURE_STATE", "empty")
    request_number = _document_list_requests
    stale_request_number = None
    if state == "stale" and _document_list_stale_armed:
        _document_list_stale_requests += 1
        stale_request_number = _document_list_stale_requests
    if state == "loading":
        await asyncio.sleep(5)
    if stale_request_number == 1:
        return RedirectResponse("/api/fixture/document-list-stale-pending", status_code=307)
    if state == "error" or (state == "paging" and cursor and _document_list_requests == 2):
        return JSONResponse({"contractVersion": "workbench-problem/v1", "code": "DOCUMENT_LIST_UNAVAILABLE"}, status_code=503)
    rows = _document_list_fixture() if state in {"populated", "paging", "stale"} else []
    if state == "stale":
        rows = [{**rows[0], "filename": "stale-response.pdf" if stale_request_number == 1 else "fresh-response.pdf"}]
    if state == "paging":
        rows = rows[:2] if not cursor else rows[2:]
    if stale_request_number is not None:
        _document_list_completions.append(stale_request_number)
    return JSONResponse({"contractVersion": "workbench-document-list/v1", "items": rows,
                         "page": {"limit": 25, "nextCursor": "fixture-next" if state == "paging" and not cursor else None}})


@fixture_app.get("/api/fixture/document-list-stale-pending")
async def fixture_document_list_stale_pending() -> JSONResponse:
    await _document_list_release.wait()
    _document_list_completions.append(1)
    rows = [{**_document_list_fixture()[0], "filename": "stale-response.pdf"}]
    return JSONResponse({"contractVersion": "workbench-document-list/v1", "items": rows,
                         "page": {"limit": 25, "nextCursor": None}})


@fixture_app.get("/api/fixture/document-list-state")
async def fixture_document_list_state() -> JSONResponse:
    return JSONResponse({"requests": _document_list_stale_requests, "completions": _document_list_completions})


@fixture_app.post("/api/fixture/document-list-arm")
async def fixture_document_list_arm() -> JSONResponse:
    global _document_list_stale_armed, _document_list_stale_requests
    _document_list_stale_armed = True
    _document_list_stale_requests = 0
    _document_list_completions.clear()
    _document_list_release.clear()
    return JSONResponse({"armed": True})


@fixture_app.post("/api/fixture/document-list-release")
async def fixture_document_list_release() -> JSONResponse:
    _document_list_release.set()
    return JSONResponse({"released": True})


@fixture_app.get("/api/workbench/overview")
async def fixture_overview(request: Request) -> JSONResponse:
    global _overview_request_count
    state = os.getenv("KB2_WORKBENCH_FIXTURE_STATE", "populated")
    _overview_request_count += 1
    if state == "loading":
        await _overview_release.wait()
    if state == "first-error" and _overview_request_count == 1:
        return JSONResponse({"code": "OVERVIEW_UNAVAILABLE"}, status_code=503)
    if state == "refresh-error" and _overview_request_count == 2:
        return JSONResponse({"code": "OVERVIEW_UNAVAILABLE"}, status_code=503)
    return JSONResponse(_fixture(state if state in {"dependency", "empty"} else "populated"))


@fixture_app.post("/api/workbench/overview/release")
async def fixture_overview_release() -> JSONResponse:
    _overview_release.set()
    return JSONResponse({"released": True})


@fixture_app.get("/api/fixture/overview-request-count")
async def fixture_overview_request_count() -> JSONResponse:
    return JSONResponse({"count": _overview_request_count})


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
            "resolution": {"selected_profile_id": "fixture-ingestion", "selection_tier": "preflight",
                           "observables": {"extension": "pdf", "media_type": "application/pdf"},
                           "candidate_profile_ids": ["fixture-default", "fixture-ingestion"],
                           "evaluated_rules": [{"rule_id": "pdf", "matched": True}]},
            "metrics": [{"name": "total_stages", "value": 4}],
            "quality": [{"name": "ingestion_quality", "status": "PASS"}],
            "stages": [
                {"stageKey": "extraction.parse", "attempt": 1, "state": "FAILED", "result": "FAILED", "selection": "rejected", "pluginId": "parser.primary@1", "failure": {"code": "PLUGIN_TIMEOUT"}, "outputs": []},
                {"stageKey": "extraction.parse", "attempt": 2, "state": "SUCCEEDED", "result": "SUCCEEDED", "selection": "accepted", "pluginId": "parser.fallback@1", "inputs": [{"id": "12345678-1234-5678-1234-567812345683", "artifactType": "opaque.bytes"}], "startedAt": "2026-09-13T01:02:03Z", "endedAt": "2026-09-13T01:02:04Z", "metrics": [{"name": "latency_ms", "value": 12}], "quality": [{"name": "parse_quality", "status": "PASS", "value": "native"}], "failure": None, "outputs": [{"id": _ARTIFACT, "artifactType": "canonical.document"}]},
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
                    }, {"id": _CHUNK_ARTIFACT, "artifactType": "chunk.set"}]}],
    })


@fixture_app.post("/api/workbench/ingestion-runs/{run_id}/stop")
async def fixture_stop_ingestion_run(run_id: str) -> JSONResponse:
    assert run_id == _VISUAL_RUN
    _ingestion_stop_requests.append(run_id)
    return JSONResponse({"stopped": True})


@fixture_app.get("/api/fixture/ingestion-stop-requests")
async def fixture_ingestion_stop_requests() -> JSONResponse:
    return JSONResponse(_ingestion_stop_requests)


@fixture_app.post("/api/workbench/ingestion-runs/{run_id}/rerun-preflight")
async def fixture_rerun_preflight(run_id: str, request: Request) -> JSONResponse:
    assert run_id == _INGESTION_RUN
    payload = await request.json()
    assert payload["workspaceProfileId"] in {"fixture-ingestion", "delayed-ingestion"}
    if payload["workspaceProfileId"] == "delayed-ingestion":
        await asyncio.sleep(.3)
    return JSONResponse({"token": "rerun-token", "workspaceProfileId": "fixture-ingestion", "sourceArtifactId": _ARTIFACT,
                         "automatic": {"selectedProfileId": "fixture-ingestion"},
                         "disclosure": {"externalStages": []}, "stages": [], "planDigest": "e" * 64})


@fixture_app.get("/api/workbench/artifacts/{artifact_id}")
async def fixture_artifact(artifact_id: str) -> JSONResponse:
    locator_a = {"kind": "pdf", "page_number": 1, "x0": 0, "y0": 0, "x1": .5, "y1": .5}
    locator_b = {"kind": "pdf", "page_number": 1, "x0": .5, "y0": .5, "x1": 1, "y1": 1}
    table_locator = {"kind": "spreadsheet", "sheet_name": "华东预算", "range": "B7"}
    if artifact_id == _CHUNK_ARTIFACT:
        return JSONResponse({
            "artifactType": "chunk.set", "schemaRevision": "v1", "summary": "fixture chunks",
            "metrics": [], "quality": [], "parents": [_ARTIFACT],
            "producer": {"runId": _INGESTION_RUN, "pluginId": "chunker.fixture@1"},
            "view": {"available": True, "tabs": ["chunks", "metadata", "lineage"], "chunks": [{
                "id": "chk_fixture", "text": "Chunk fixture", "sourceElementIds": ["elm_a", "elm_b"],
                "citations": [{"elementId": "elm_a", "locator": locator_a}, {"elementId": "elm_b", "locator": locator_b}],
            }]},
        })
    assert artifact_id == _ARTIFACT
    return JSONResponse({
        "artifactType": "canonical.document", "schemaRevision": "v1",
        "summary": "fixture canonical", "metrics": [], "quality": [], "parents": [],
        "producer": {"runId": _INGESTION_RUN, "pluginId": "parser.fixture@1"},
        "view": {"available": True, "tabs": ["canonical", "tree", "table", "metadata", "lineage"],
                 "elements": [{"id": "elm_a", "text": "First", "locator": locator_a},
                              {"id": "elm_b", "text": "Second", "locator": locator_b}],
                 "tables": [{"id": "tbl_fixture", "elementId": "elm_b", "locator": locator_b,
                             "cells": [{"row_index": 0, "column_index": 0, "text": "Cell fixture", "row_span": 1, "column_span": 1}]},
                            {"id": "tbl_budget", "elementId": "elm_budget", "locator": table_locator,
                             "cells": [{"id": "cell_budget_b7", "row_index": 6, "column_index": 1, "text": "128 万元", "row_span": 1, "column_span": 1}]}]},
    })


@fixture_app.get("/api/workbench/query-lab/options")
async def fixture_query_options(request: Request) -> JSONResponse:
    referer = request.headers.get("referer", "")
    if "fixture=options-error" in referer:
        return JSONResponse({"code": "QUERY_OPTIONS_UNAVAILABLE"}, status_code=503)
    if "fixture=options-empty" in referer:
        return JSONResponse({"profiles": [], "indexes": []})
    if "fixture=options-loading" in referer:
        await asyncio.sleep(.8)
    return JSONResponse({"profiles": [{"profileId": "browser-query", "updatedAt": "2026-09-13T00:00:00Z"}],
                         "indexes": [{"id": _ARTIFACT, "summary": "fixture indexed Artifact"}]})


@fixture_app.post("/api/workbench/query-lab/preflights")
async def fixture_query_preflight(request: Request) -> JSONResponse:
    global _active_query_stopped, _active_query_reads
    question = str((await request.json()).get("question", "answered")).lower()
    if "preflight-error" in question:
        return JSONResponse({"code": "QUERY_PREFLIGHT_UNAVAILABLE"}, status_code=503)
    if "stale-old" in question:
        await asyncio.sleep(.2)
    scenario = next((name for name in sorted(_QUERY_RUNS, key=len, reverse=True) if name in question), "answered")
    if scenario == "active":
        _active_query_stopped = False
        _active_query_reads = 0
    token = f"query-token-{scenario}"
    _query_scenarios[token] = scenario
    return JSONResponse({"token": token, "planDigest": "f" * 64,
                         "stages": [{"stageId": "keyword", "kind": "retrieve", "pluginId": "retriever.keyword@1"},
                                    {"stageId": "fusion", "kind": "fuse", "pluginId": "fusion.rrf@1"},
                                    {"stageId": "context", "kind": "context", "pluginId": "context.fixture@1"}],
                         "disclosure": {"externalStages": [] if "local" in question else [{"stage": "generate", "capability": "generation.default"}]}})


@fixture_app.post("/api/workbench/query-lab/preflights/{token}/runs")
async def fixture_query_submit(token: str) -> JSONResponse:
    scenario = _query_scenarios[token]
    if scenario == "submit-error":
        return JSONResponse({"code": "QUERY_SUBMIT_REJECTED"}, status_code=409)
    if scenario == "delayed-submit":
        await asyncio.sleep(.35)
    return JSONResponse({"runId": _QUERY_RUNS[scenario], "planDigest": "f" * 64}, status_code=202)


def _query_candidate_contracts(locator: dict[str, object]) -> tuple[RetrievalCandidateSet, FusionCandidateSet, RerankedCandidateSet]:
    index = IndexArtifactBinding(id=UUID(_ARTIFACT), content_digest="a" * 64)
    keyword = RetrievalCandidate(
        candidate_id="rcd_" + "1" * 32, document_id=_QUERY_DOCUMENT, chunk_id=_QUERY_CHUNK,
        element_ids=("elm_" + "1" * 32,), locators=(locator,), rank=1, safe_score=.8,
        score_kind="bm25.normalized",
    )
    vector = keyword.model_copy(update={"candidate_id": "rcd_" + "2" * 32, "safe_score": .7, "score_kind": "cosine.normalized"})
    keyword_set = RetrievalCandidateSet(
        candidate_set_id="rcs_" + "1" * 32, index=index, index_id="idx_" + "1" * 32,
        document_id=_QUERY_DOCUMENT, retriever_plugin_id="retriever.keyword@1",
        implementation_digest="b" * 64, contributor_id="keyword", configuration_digest="c" * 64,
        candidates=(keyword,),
    )
    fused = FusedCandidate(
        document_id=_QUERY_DOCUMENT, chunk_id=_QUERY_CHUNK, rank=1, safe_score=.75,
        contributions=(CandidateContribution(contributor_id="keyword", original_rank=1, candidate=keyword),
                       CandidateContribution(contributor_id="vector", original_rank=1, candidate=vector)),
    )
    fusion_set = FusionCandidateSet(
        candidate_set_id="fcs_" + "1" * 32, index=index, index_id="idx_" + "1" * 32,
        document_id=_QUERY_DOCUMENT, fusion_plugin_id="fusion.rrf@1",
        implementation_digest="d" * 64, configuration_digest="e" * 64,
        contributor_set_ids=("rcs_" + "1" * 32, "rcs_" + "2" * 32), candidates=(fused,),
    )
    reranked_set = RerankedCandidateSet(
        candidate_set_id="rrs_" + "1" * 32, fusion_candidate_set_id=fusion_set.candidate_set_id,
        index=index, index_id="idx_" + "1" * 32, document_id=_QUERY_DOCUMENT,
        reranker_plugin_id="reranker.lexical@1", implementation_digest="f" * 64,
        configuration_digest="1" * 64,
        input_candidates=(RerankInputCandidate(chunk_id=_QUERY_CHUNK, input_rank=1),),
        candidates=(fused,), decisions=(RerankDecision(chunk_id=_QUERY_CHUNK, input_rank=1,
        output_rank=1, safe_score=.75, reason="included"),),
    )
    return keyword_set, fusion_set, reranked_set


@fixture_app.get("/api/workbench/query-runs/{run_id}")
async def fixture_query_run(run_id: str) -> JSONResponse:
    global _active_query_stopped, _active_query_reads
    scenario = "answered" if run_id == _HISTORY_QUERY else next(name for name, identifier in _QUERY_RUNS.items() if identifier == run_id)
    locator = ({"kind": "spreadsheet", "sheet_name": "华东预算", "range": "B7"}
               if scenario == "table-answered-inspector" else
               {"kind": "pdf", "page_number": 1, "x0": 0, "y0": 0, "x1": .5, "y1": .5})
    finals = {
        "answered": {"state": "ANSWERED", "answer": "Evidence-bound fixture answer", "citationKeys": ["cit_fixture"], "action": None},
        "fact-answered": {"state": "ANSWERED", "answer": "试点系统于 2026 年 6 月完成验收。", "citationKeys": ["cit_fixture"], "action": None},
        "table-answered-inspector": {"state": "ANSWERED", "answer": "华东区第二季度预算为 128 万元。", "citationKeys": ["cit_fixture"], "action": None},
        "hierarchy-answered": {"state": "ANSWERED", "answer": "风险分为交付风险与数据质量风险。", "citationKeys": ["cit_fixture", "cit_parent"], "action": None},
        "clarification": {"state": "CLARIFICATION_REQUIRED", "answer": None, "citationKeys": [], "action": "请明确目标文档范围。"},
        "clarification-required": {"state": "CLARIFICATION_REQUIRED", "answer": None, "citationKeys": [], "action": "请明确是查询项目预算还是部门预算。"},
        "abstained": {"state": "ABSTAINED", "answer": None, "citationKeys": [], "action": "可用 Evidence 不足，未生成答案。"},
        "failed": {"state": "FAILED", "answer": None, "citationKeys": [], "action": "验证失败，未发布答案。"},
        "repair-answered": {"state": "ANSWERED", "answer": "修复后的答案保持同一 Evidence 引用。", "citationKeys": ["cit_fixture"], "action": None},
        "repair-exhausted": {"state": "FAILED", "answer": None, "citationKeys": [], "action": "有限修复已耗尽，未发布答案。"},
    }
    if scenario == "active" and not _active_query_stopped:
        _active_query_reads += 1
        if _active_query_reads >= 2:
            await asyncio.sleep(.5)
        return JSONResponse({"id": run_id, "state": "RUNNING", "terminalState": None, "actions": {"stop": True}, "stages": [], "candidates": [], "decisionPath": {"columns": [], "rows": []}, "evidence": [], "details": [], "final": None})
    projected_scenario = "answered" if scenario == "active" else scenario
    verification = {
        "answered": {"kind": "verification", "outcome": "pass", "failureCodes": [], "missingCitationKeys": []},
        "clarification": {"kind": "verification", "outcome": "clarification_required", "failureCodes": [], "missingCitationKeys": []},
        "abstained": {"kind": "verification", "outcome": "abstain", "failureCodes": ["EVIDENCE_INSUFFICIENT"], "missingCitationKeys": []},
        "failed": {"kind": "verification", "outcome": "failed", "failureCodes": ["CITATION_VALIDATION_FAILED"], "missingCitationKeys": ["cit_missing"]},
        "fact-answered": {"kind": "verification", "outcome": "pass", "failureCodes": [], "missingCitationKeys": []},
        "table-answered-inspector": {"kind": "verification", "outcome": "pass", "failureCodes": [], "missingCitationKeys": []},
        "hierarchy-answered": {"kind": "verification", "outcome": "pass", "failureCodes": [], "missingCitationKeys": []},
        "clarification-required": {"kind": "verification", "outcome": "clarification_required", "failureCodes": [], "missingCitationKeys": []},
        "repair-answered": {"kind": "verification", "outcome": "pass_after_repair", "failureCodes": [], "missingCitationKeys": []},
        "repair-exhausted": {"kind": "verification", "outcome": "failed", "failureCodes": ["CITATION_VALIDATION_FAILED", "REPAIR_EXHAUSTED"], "missingCitationKeys": ["cit_missing"]},
    }[projected_scenario]
    contracts = _query_candidate_contracts(locator)
    candidate_sets = []
    for name, value in zip(("keyword", "fusion", "rerank"), contracts, strict=True):
        rows = QueryWorkbenchService._candidate_rows(value)
        for row in rows:
            row.update(documentLabel="项目验收与预算说明.pdf", excerpt="试点系统于 2026 年 6 月完成验收；华东区第二季度预算为 128 万元。", locatorLabel="SPREADSHEET / 工作表 华东预算 / 范围 B7" if projected_scenario == "table-answered-inspector" else "PDF / 第 1 页")
        candidate_sets.append({"stageId": name, "available": True, "rows": rows})
    context_decision = {"chunk_id": _QUERY_CHUNK, "source_rank": 1, "reason": "included", "safe_score": .8}
    decision_path = {"columns": [{"stageId": name, "kind": "candidate"} for name in ("keyword", "fusion", "rerank")] + [{"stageId": "context", "kind": "context"}],
                     "rows": [{"documentId": _QUERY_DOCUMENT, "documentLabel": "项目验收与预算说明.pdf", "chunkId": _QUERY_CHUNK, "excerpt": "试点系统于 2026 年 6 月完成验收；华东区第二季度预算为 128 万元。", "locatorLabel": "SPREADSHEET / 工作表 华东预算 / 范围 B7" if projected_scenario == "table-answered-inspector" else "PDF / 第 1 页", "stages": {
                         "keyword": {"state": "PRESENT", "rank": 1, "safeScore": .8}, "fusion": {"state": "PRESENT", "rank": 1, "safeScore": .75},
                         "rerank": {"state": "PRESENT", "rank": 1, "safeScore": .75, "decision": {"reason": "included"}}, "context": {"state": "PRESENT", **context_decision}}}]}
    failed = projected_scenario in {"failed", "repair-exhausted"}
    details = [_fixture_context_detail()]
    if projected_scenario == "repair-answered":
        details.extend([{"kind": "verification", "outcome": "failed", "failureCodes": ["CITATION_VALIDATION_FAILED"], "missingCitationKeys": ["cit_missing"]}, verification])
    else:
        details.append(verification)
    evidence_rows = [{"citationKey": "cit_fixture", "excerpt": "华东区第二季度预算为 128 万元。" if projected_scenario == "table-answered-inspector" else "试点系统于 2026 年 6 月完成验收，相关结论来自已固定的来源段落。", "documentId": _QUERY_DOCUMENT, "documentLabel": "项目验收与预算说明.pdf", "chunkId": _QUERY_CHUNK, "locators": [locator], "locatorLabel": "SPREADSHEET / 工作表 华东预算 / 范围 B7" if projected_scenario == "table-answered-inspector" else "PDF / 第 1 页", "contributors": [{"contributor_id": "keyword", "safe_score": .8}], "hierarchy": ["项目报告", "验收结论"] if projected_scenario == "hierarchy-answered" else [], "tableElementIds": ["elm_budget"] if projected_scenario == "table-answered-inspector" else [], "sourceArtifactId": _ARTIFACT, "sourceLocator": locator, "contextDecision": context_decision}]
    if projected_scenario == "hierarchy-answered":
        parent_decision = {"chunk_id": _QUERY_CHUNK_PARENT, "source_rank": 2, "reason": "expanded_parent", "safe_score": .68}
        evidence_rows.append({"citationKey": "cit_parent", "excerpt": "数据质量风险包括字段缺失与表格结构错误，需要在验收前完成核查。", "documentId": _QUERY_DOCUMENT, "documentLabel": "项目验收与预算说明.pdf", "chunkId": _QUERY_CHUNK_PARENT, "locators": [locator], "locatorLabel": "PDF / 第 1 页", "contributors": [{"contributor_id": "hierarchy", "safe_score": .68}], "hierarchy": ["项目报告", "风险", "数据质量"], "tableElementIds": [], "sourceArtifactId": _ARTIFACT, "sourceLocator": locator, "contextDecision": parent_decision})
        decision_path["rows"].append({"documentId": _QUERY_DOCUMENT, "documentLabel": "项目验收与预算说明.pdf", "chunkId": _QUERY_CHUNK_PARENT, "excerpt": evidence_rows[-1]["excerpt"], "locatorLabel": "PDF / 第 1 页", "stages": {"keyword": {"state": "NOT_PRESENT"}, "fusion": {"state": "NOT_PRESENT"}, "rerank": {"state": "NOT_PRESENT"}, "context": {"state": "PRESENT", **parent_decision}}})
        details[0] = {"kind": "context", "decisions": [context_decision, parent_decision], "shortage": {"minimum_items": 2, "selected_items": 2, "selected_tokens": 164, "reason": "none"}}
    return JSONResponse({"id": run_id, "state": "FAILED" if failed else "SUCCEEDED", "terminalState": "FAILED" if failed else "SUCCEEDED", "actions": {"stop": False},
                         "stages": [{"stageKey": "keyword", "attempt": 1, "state": "SUCCEEDED", "pluginId": "retriever.keyword@1", "startedAt": "2026-09-13T00:00:00Z", "endedAt": "2026-09-13T00:00:00.120Z", "durationMs": 120},
                                    {"stageKey": "fusion", "attempt": 1, "state": "SUCCEEDED", "pluginId": "fusion.rrf@1", "startedAt": "2026-09-13T00:00:00.120Z", "endedAt": "2026-09-13T00:00:00.180Z", "durationMs": 60},
                                    {"stageKey": "rerank", "attempt": 1, "state": "SUCCEEDED", "pluginId": "reranker.lexical@1", "startedAt": "2026-09-13T00:00:00.180Z", "endedAt": "2026-09-13T00:00:00.210Z", "durationMs": 30}],
                         "candidates": candidate_sets, "decisionPath": decision_path,
                         "evidence": evidence_rows,
                         "details": details, "final": finals[projected_scenario]})


def _fixture_context_detail() -> dict[str, object]:
    decisions = [{"chunk_id": _QUERY_CHUNK, "source_rank": 1, "reason": "included", "safe_score": .8},
                 {"chunk_id": "chk_" + "2" * 32, "source_rank": 2, "reason": "excluded_budget", "safe_score": .6}]
    return {"kind": "context", "decisions": decisions,
            "shortage": {"minimum_items": 3, "selected_items": 1, "selected_tokens": 96, "reason": "below_minimum"}}


def _evaluation_dataset() -> dict[str, object]:
    slices = {"format":"pdf","processing_class":"native","native_ocr":"native","structure":"prose","language":"zh","question_class":"lookup","difficulty":"low","criticality":"high"}
    source = {"id":_ARTIFACT,"content_digest":"a" * 64,"schema_revision":"v1","artifact_type":"canonical.document"}
    evidence = {"id":"12345678-1234-5678-1234-567812345699","content_digest":"9" * 64,"schema_revision":"v1","artifact_type":"evidence.set"}
    def query_case(case_id: str, *, origin: str, reviewed: bool = False, question: str = "fixture question") -> dict[str, object]:
        reviews = [{"operation":"mark_reviewed","reviewer":"fixture.reviewer","reviewed_at":"2026-09-13T00:10:00Z","content_digest":"b" * 64}] if reviewed else []
        operation = {"generated":"generated", "manual":"create", "imported":"import"}[origin]
        return {"id":case_id,"source":source,"slices":slices,"provenance":{"origin":origin,"operation":operation,"created_at":"2026-09-13T00:00:00Z"},"reviews":reviews,"question":question,"evidence":evidence,"answerability":"answerable","expected_facts":["fixture fact"],"forbidden_facts":["forbidden fixture"],"relevant_evidence_ids":["evd_"+"1"*32],"required_citation_keys":["cit_"+"2"*32],"deterministic_answer":"fixture answer"}
    annotation = {"id":"ann_0123456789abcdef","source":source,"slices":slices,"provenance":{"origin":"manual","operation":"create","created_at":"2026-09-13T00:00:00Z"},"reviews":[],"target":{"kind":"cell","element_id":"elm_0123456789abcdef","table_id":"tbl_0123456789abcdef","cell_id":"cell_0123456789abcdef","locator":{"kind":"pdf","page_number":1,"x0":0,"y0":0,"x1":.5,"y1":.5},"start":2,"end":8},"label":"fixture annotation"}
    rows = [query_case("qcase_0123456789abcdef", origin="generated"), query_case("qcase_1123456789abcdef", origin="manual", reviewed=True), query_case("qcase_2123456789abcdef", origin="imported"), query_case("qcase_3123456789abcdef", origin="manual")]
    return {"id": _EVALUATION_DATASET, "revision": 1, "revisionId": "12345678-1234-5678-1234-567812345692", "digest": "e" * 64,
            "createdAt": "2026-09-13T00:00:00Z", "annotationCount": 1, "queryCaseCount": 4, "reviewedCount": 1, "caseCount": 5,
            "validation": {"ann_0123456789abcdef": [], "qcase_0123456789abcdef": [], "qcase_1123456789abcdef": [], "qcase_2123456789abcdef": ["CASE_INVALID"], "qcase_3123456789abcdef": ["CASE_INCOMPLETE"]}, "content": {"schema_revision": "GoldenDataset/v1", "taxonomy": DEFAULT_TAXONOMY.model_dump(mode="json"), "annotations": [annotation], "query_cases": rows}}


def test_s025_s026_browser_fixtures_use_production_contract_shapes() -> None:
    detail = _fixture_context_detail()
    assert [ContextDecision.model_validate(item).reason for item in detail["decisions"]] == ["included", "excluded_budget"]
    assert EvidenceShortage.model_validate(detail["shortage"]).reason == "below_minimum"
    candidate_sets = _query_candidate_contracts({"kind": "pdf", "page_number": 1, "x0": 0, "y0": 0, "x1": .5, "y1": .5})
    assert [type(value) for value in candidate_sets] == [RetrievalCandidateSet, FusionCandidateSet, RerankedCandidateSet]
    assert QueryWorkbenchService._candidate_rows(candidate_sets[0])[0]["contributions"][0]["scoreKind"] == "bm25.normalized"
    assert [item["contributorId"] for item in QueryWorkbenchService._candidate_rows(candidate_sets[1])[0]["contributions"]] == ["keyword", "vector"]
    assert QueryWorkbenchService._candidate_rows(candidate_sets[2])[0]["decision"]["reason"] == "included"
    content = DatasetContent.model_validate(_evaluation_dataset()["content"])
    assert content.annotations[0].target.model_dump(mode="json", exclude_none=True) == _evaluation_dataset()["content"]["annotations"][0]["target"]
    assert content.query_cases[0].evidence and content.query_cases[0].evidence.artifact_type == "evidence.set"
    manifest, report, navigation = _evaluation_contracts(_EVALUATION_RUN, "failed-gates")
    assert manifest.subjects[0].ingestion_plan_digest == digest(manifest.subjects[0].ingestion_plan)
    assert manifest.subjects[0].query_plan_digest == digest(manifest.subjects[0].query_plan)
    assert manifest.gates[0].selector == {"criticality": "high"} and manifest.gates[0].threshold == .7
    assert report.operation.elapsed_ms == 60000 and report.operation.cpu_ms == 120
    assert navigation.links[0].evaluation_run_id == UUID(_EVALUATION_RUN)


def test_s026_fixture_projects_persisted_metric_reports_through_workbench_service() -> None:
    manifest, report, _ = _evaluation_contracts(_EVALUATION_RUNS["status-matrix"], "status-matrix")
    persisted = _evaluation_metric_reports(_EVALUATION_RUNS["status-matrix"], "status-matrix")
    assert report.report_ids == tuple(sorted(persisted, key=str))
    assert set(manifest.metric_ids) == {metric.metric_id for metric in persisted.values()}
    assert all(set(metric.slices) == set(DEFAULT_TAXONOMY.dimensions) for metric in persisted.values())
    assert all(metric.slices["question_class"] == "multi_evidence" for metric in persisted.values())
    assert all(set(gate.selected_report_ids) <= set(report.report_ids) for gate in report.gate_results)

    projected = asyncio.run(_evaluation_fixture_service(_EVALUATION_RUNS["status-matrix"], "status-matrix").run(UUID(_EVALUATION_RUNS["status-matrix"])))
    assert projected is not None
    rows = projected["metrics"]
    assert {row["owner"] for row in rows} == {"ingestion", "retrieval", "context", "answer", "citation", "decision", "judge"}
    assert all(UUID(row["artifactId"]) in report.report_ids for row in rows)
    assert all(set(row["slices"]) == set(DEFAULT_TAXONOMY.dimensions) for row in rows)
    judges = [row for row in rows if row["owner"] == "judge"]
    assert {row["eligibility"] for row in judges} == {"ELIGIBLE", "ADVISORY", "INELIGIBLE", "DRIFTED"}
    assert all(row["calibrationReportArtifactId"] == _COMPARISON for row in judges)
    assert not any(row["artifactId"].startswith("metric-") for row in rows)


@fixture_app.get("/api/workbench/evaluation-datasets")
async def fixture_evaluation_datasets(q: str = "") -> JSONResponse:
    if q == "empty":
        return JSONResponse([])
    item = _evaluation_dataset()
    return JSONResponse([{key: item[key] for key in ("id", "revision", "revisionId", "digest", "createdAt", "annotationCount", "queryCaseCount", "reviewedCount", "caseCount")}])


@fixture_app.get("/api/workbench/evaluation-datasets/{dataset_id}")
async def fixture_evaluation_dataset(dataset_id: str) -> JSONResponse:
    assert dataset_id == _EVALUATION_DATASET
    return JSONResponse(_evaluation_dataset())


@fixture_app.put("/api/workbench/evaluation-datasets/{dataset_id}")
async def fixture_evaluation_dataset_save(dataset_id: str, request: Request) -> JSONResponse:
    assert dataset_id == _EVALUATION_DATASET
    payload = await request.json()
    assert payload["schema_revision"] == "GoldenDataset/v1"
    annotation = payload["annotations"][0]
    assert set(annotation["target"]) == {"kind", "element_id", "table_id", "cell_id", "locator", "start", "end"}
    assert set(payload["query_cases"][0]["evidence"]) == {"id", "content_digest", "schema_revision", "artifact_type"}
    if payload["query_cases"][0]["question"] == "trigger-save-failure":
        return JSONResponse({"code": "DATASET_SAVE_FAILED"}, status_code=503)
    return JSONResponse({"valid": True, "dataset": _evaluation_dataset()})


@fixture_app.post("/api/workbench/evaluation-datasets/{dataset_id}/revisions/{revision}/cases/{case_id}/review")
async def fixture_evaluation_review(dataset_id: str, revision: int, case_id: str, request: Request) -> JSONResponse:
    assert (dataset_id, revision, case_id) == (_EVALUATION_DATASET, 1, "qcase_0123456789abcdef")
    reviewer = (await request.json())["reviewer"]
    if reviewer == "fail.review":
        return JSONResponse({"code": "CASE_REVIEW_FAILED"}, status_code=503)
    assert reviewer == "fixture.reviewer"
    return JSONResponse({"valid": True, "dataset": _evaluation_dataset()})


@fixture_app.get("/api/workbench/evaluation-runs")
async def fixture_evaluation_runs() -> JSONResponse:
    return JSONResponse([{ "id": identifier, "state": "RUNNING" if name == "running" else "FAILED" if name in {"failed-gates", "invalid-dataset"} else "SUCCEEDED", "terminalState": None if name == "running" else "FAILED" if name in {"failed-gates", "invalid-dataset"} else "SUCCEEDED", "createdAt": "2026-09-13T00:00:00Z", "startedAt": "2026-09-13T00:00:00Z", "endedAt": None if name == "running" else "2026-09-13T00:01:00Z", "planDigest": "f" * 64 } for name, identifier in _EVALUATION_RUNS.items()])


def _evaluation_fixture_id(run_id: str, role: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"kb2-workbench-evaluation-fixture:{run_id}:{role}")


def _evaluation_metric_reports(run_id: str, scenario: str) -> dict[UUID, MetricReport]:
    case_id = "qcase_0123456789abcdef"
    slices = {
        "format": "pdf", "processing_class": "mixed", "native_ocr": "ocr",
        "structure": "layout_rich", "language": "multilingual",
        "question_class": "multi_evidence", "difficulty": "high", "criticality": "high",
    }
    reference = lambda role: _evaluation_fixture_id(run_id, role)
    reports: dict[UUID, MetricReport] = {}

    def add(role: str, metric_id: str, owner: str, *, status: MetricStatus = MetricStatus.VALUE,
            value: float | None = .8, eligibility: str | None = None) -> None:
        fields: dict[str, object] = {
            "metric_id": metric_id, "owner": owner, "snapshot_artifact_id": reference("snapshot"),
            "taxonomy_digest": digest(DEFAULT_TAXONOMY), "slices": slices, "status": status,
            "value": value if status is MetricStatus.VALUE else None, "elapsed_ms": 5,
            "labelled_count": 1, "matched_count": 1 if status is MetricStatus.VALUE else 0,
            "sample_count": 1 if status is MetricStatus.VALUE else 0,
        }
        if owner == "ingestion":
            fields.update(required_annotation_kinds=("cell",), document_id=_QUERY_DOCUMENT,
                          expected_artifact_id=reference("expected-document"), observed_artifact_id=reference("observed-document"))
        elif owner in {"retrieval", "context"}:
            fields.update(metric_family_id=metric_id, case_id=case_id, question_source_artifact_id=reference("question-source"),
                          label_evidence_artifact_id=reference("label-evidence"), stage_kind="context" if owner == "context" else "retrieval",
                          measured_artifact_id=reference(f"{owner}-measured"), k=5)
        elif owner in {"answer", "citation"}:
            fields.update(metric_family_id=metric_id, case_id=case_id, question_source_artifact_id=reference("question-source"),
                          label_evidence_artifact_id=reference("label-evidence"), stage_kind="verification",
                          answer_artifact_id=reference("answer"), verification_artifact_id=reference("verification"),
                          final_response_artifact_id=reference("final-response"))
        elif owner == "decision":
            fields.update(metric_family_id=metric_id, case_id=case_id, label_evidence_artifact_id=reference("label-evidence"),
                          stage_kind="final_state", final_response_artifact_id=reference("final-response"))
        elif owner == "judge":
            fields.update(method="llm_judge", metric_family_id=metric_id, case_id=case_id,
                          question_source_artifact_id=reference("question-source"), label_evidence_artifact_id=reference("label-evidence"),
                          stage_kind="final_state", final_response_artifact_id=reference("final-response"),
                          judge_result_artifact_id=reference(f"{role}-result"), calibration_report_artifact_id=UUID(_COMPARISON),
                          judge_definition_digest="6" * 64, calibration_policy_digest="7" * 64, eligibility=eligibility)
        identifier = reference(f"metric:{role}")
        reports[identifier] = MetricReport(**fields)

    answer_value = .8 if scenario in {"passed-gates", "status-matrix"} else .3
    add("ingestion", "ingestion.fixture@1", "ingestion")
    add("retrieval", "retrieval.fixture@1", "retrieval")
    add("context", "context.fixture@1", "context")
    add("answer", "answer.coverage@1", "answer", value=answer_value)
    add("citation", "citation.fixture@1", "citation", status=MetricStatus.INSUFFICIENT_LABELS)
    add("decision", "decision.fixture@1", "decision")
    add("judge-ineligible", "judge.ineligible@1", "judge", status=MetricStatus.NOT_APPLICABLE, eligibility="INELIGIBLE")
    if scenario == "status-matrix":
        add("answer-failure", "answer.failure@1", "answer", value=.3)
        add("judge-eligible", "judge.eligible@1", "judge", value=.7, eligibility="ELIGIBLE")
        add("judge-advisory", "judge.advisory@1", "judge", value=.7, eligibility="ADVISORY")
        add("judge-drifted", "judge.drifted@1", "judge", value=.7, eligibility="DRIFTED")
    return reports


def _evaluation_contracts(run_id: str, scenario: str) -> tuple[EvaluationManifest, LayeredReport, NavigationIndex]:
    case_id = "qcase_0123456789abcdef"
    metric_reports = _evaluation_metric_reports(run_id, scenario)
    metric_by_id = {report.metric_id: identifier for identifier, report in metric_reports.items()}
    ingestion_plan, query_plan = {"plugin": "fixture.ingestion@1"}, {"plugin": "fixture.query@1"}
    binding = ArtifactBinding(role="evidence", artifact_id=UUID(_ARTIFACT), artifact_type="evidence.set",
                              content_digest="9" * 64, case_id=case_id)
    identities = (
        PlanIdentity(plugin_id="fixture.ingestion@1", implementation_digest="1" * 64, configuration_digest="2" * 64),
        PlanIdentity(plugin_id="fixture.query@1", implementation_digest="3" * 64, configuration_digest="4" * 64,
                     provider_id="fixture.local", model="fixture-model", prompt_digest="5" * 64),
    )
    subjects = tuple(EvaluationSubject(
        subject=name, ingestion_plan=ingestion_plan, ingestion_plan_digest=digest(ingestion_plan),
        query_plan=query_plan, query_plan_digest=digest(query_plan), bindings=(binding,),
        declared_identities=identities,
    ) for name in ("baseline", "candidate"))
    gate_specs = (
        (("gate.pass", "answer.coverage@1", "answer", "PASS"),
         ("gate.fail", "answer.failure@1", "answer", "FAIL"),
         ("gate.insufficient", "citation.fixture@1", "citation", "INSUFFICIENT"),
         ("gate.ineligible", "judge.ineligible@1", "judge", "INELIGIBLE"))
        if scenario == "status-matrix" else
        (("gate.answer", "answer.coverage@1", "answer", "PASS" if scenario == "passed-gates" else "FAIL"),)
    )
    configured = tuple(QualityGate(
        gate_id=gate_id, metric_id=metric_id, owner=owner, selector={"criticality": "high"}, aggregation="mean",
        minimum_samples=1, direction="higher_is_better", threshold=.7, severity="hard",
    ) for gate_id, metric_id, owner, _ in gate_specs)
    manifest = EvaluationManifest(
        dataset_snapshot_id=_evaluation_fixture_id(run_id, "snapshot"), dataset_snapshot_digest="d" * 64,
        taxonomy_digest=digest(DEFAULT_TAXONOMY), input_catalog_digest="c" * 64, case_ids=(case_id,),
        subjects=subjects, metric_ids=tuple(sorted(metric_by_id)), gates=configured,
        runtime=RuntimeSummary(runtime_digest="a" * 64, package_digest="b" * 64,
        implementation_digest="c" * 64, os_family="linux", architecture="x86_64",
        resource_sampler_version="fixture.sampler.v1"),
    )
    results = tuple(GateResult(
        gate_id=gate_id, state=state, reason="threshold_result", subject="candidate",
        selected_report_ids=(metric_by_id[metric_id],), matched_case_ids=(case_id,) if state in {"PASS", "FAIL"} else (),
        sample_count=1 if state in {"PASS", "FAIL"} else 0,
        value=.8 if state == "PASS" else .3 if state == "FAIL" else None,
        state_counts={"insufficient_labels": 1} if state == "INSUFFICIENT" else {"not_applicable": 1} if state == "INELIGIBLE" else {"value": 1},
    ) for gate_id, metric_id, _, state in gate_specs)
    manifest_id = _evaluation_fixture_id(run_id, "manifest")
    report_id = _evaluation_fixture_id(run_id, "report")
    answer_metric_id = metric_by_id["answer.coverage@1"]
    link = FailedCaseLink(
        case_id=case_id, subject="candidate", gate_id="gate.answer", metric_report_id=answer_metric_id,
        ingestion_artifact_id=UUID(_ARTIFACT), retrieval_artifact_id=UUID(_ARTIFACT),
        fusion_artifact_id=UUID(_ARTIFACT), rerank_artifact_id=UUID(_ARTIFACT),
        source_artifact_id=UUID(_ARTIFACT), evidence_artifact_id=UUID(_ARTIFACT),
        generation_artifact_id=UUID(_ARTIFACT), verification_artifact_id=UUID(_ARTIFACT),
        final_response_artifact_id=UUID(_ARTIFACT), evaluation_run_id=UUID(run_id),
    )
    failed = (link,) if scenario == "failed-gates" else ()
    layers = {name: [] for name in ("ingestion", "retrieval", "answer", "citation", "decision", "judge", "latency", "resources")}
    for identifier, metric in metric_reports.items():
        layers["retrieval" if metric.owner == "context" else metric.owner].append(identifier)
    report = LayeredReport(
        manifest_artifact_id=manifest_id, manifest_digest=hashlib.sha256(canonical_bytes(manifest)).hexdigest(),
        report_ids=tuple(sorted(metric_reports, key=str)), report_subjects={identifier: "candidate" for identifier in metric_reports},
        layers={name: tuple(sorted(identifiers, key=str)) for name, identifiers in layers.items()},
        gate_results=results, operation=OperationReport(elapsed_ms=60000, cpu_ms=120,
        peak_rss=1048576, io_bytes=4096, availability="AVAILABLE"), failed_cases=failed,
    )
    navigation = NavigationIndex(evaluation_report_id=report_id, evaluation_run_id=UUID(run_id), links=failed)
    return manifest, report, navigation


def _evaluation_fixture_service(run_id: str, scenario: str) -> EvaluationWorkbenchService:
    manifest, report, navigation = _evaluation_contracts(run_id, scenario)
    identifiers = {
        "manifest": _evaluation_fixture_id(run_id, "manifest"),
        "report": _evaluation_fixture_id(run_id, "report"),
        "navigation": _evaluation_fixture_id(run_id, "navigation"),
    }
    payloads = {
        identifiers["manifest"]: canonical_bytes(manifest),
        identifiers["report"]: canonical_bytes(report),
        identifiers["navigation"]: canonical_bytes(navigation),
        **{identifier: metric_report_bytes(metric) for identifier, metric in _evaluation_metric_reports(run_id, scenario).items()},
    }
    types = {identifiers["manifest"]: "evaluation.manifest", identifiers["report"]: "evaluation.report",
             identifiers["navigation"]: "evaluation.navigation.index",
             **{identifier: "metric.report" for identifier in _evaluation_metric_reports(run_id, scenario)}}
    if scenario == "invalid-dataset":
        payloads[identifiers["manifest"]] = b'{"schema_version":"EvaluationManifest/v1"}'

    class Traces:
        async def list_evaluation_workbench_runs(self):
            state = "RUNNING" if scenario == "running" else "FAILED" if scenario in {"failed-gates", "invalid-dataset"} else "SUCCEEDED"
            now = datetime(2026, 9, 13, tzinfo=timezone.utc)
            return [{"id": UUID(run_id), "state": state, "terminal_state": None if scenario == "running" else state,
                     "created_at": now, "started_at": now, "ended_at": None if scenario == "running" else now,
                     "plan_digest": "f" * 64}]

        async def list_run_artifacts(self, requested):
            selected = (identifiers["manifest"],) if scenario in {"running", "invalid-dataset"} else tuple(payloads)
            return [SimpleNamespace(id=identifier, artifact_type=types[identifier],
                                    content_digest=hashlib.sha256(payloads[identifier]).hexdigest()) for identifier in selected]

    class Artifacts:
        async def read_content(self, identifier):
            return payloads[identifier]

        async def get_artifact_manifest(self, identifier):
            return SimpleNamespace(artifact_type=types[identifier], content_digest=hashlib.sha256(payloads[identifier]).hexdigest())

    return EvaluationWorkbenchService(object(), Traces(), Artifacts())


@fixture_app.get("/api/workbench/evaluation-runs/{run_id}")
async def fixture_evaluation_run(run_id: str) -> JSONResponse:
    scenario = next(name for name, identifier in _EVALUATION_RUNS.items() if identifier == run_id)
    projected = await _evaluation_fixture_service(run_id, scenario).run(UUID(run_id))
    assert projected is not None
    return JSONResponse(projected)


async def _comparison_fixture(mode: str = "MULTI_AXIS_NON_CAUSAL") -> dict[str, object]:
    """Exercise S-021 persistence, then validate its real comparison bytes."""
    from kb2_runtime.workbench.diagnosis import ComparisonWorkbenchService
    base_manifest, report, _ = _evaluation_contracts(_EVALUATION_RUNS["failed-gates"], "failed-gates")
    baseline_subject, candidate_subject = base_manifest.subjects
    candidate_query = dict(candidate_subject.query_plan) | {"plugin": "query.candidate@1"}
    candidate_ingestion = dict(candidate_subject.ingestion_plan)
    if mode == "MULTI_AXIS_NON_CAUSAL":
        candidate_ingestion |= {"plugin": "ingestion.candidate@1"}
    identities = (*candidate_subject.declared_identities,
                  PlanIdentity(plugin_id="query.candidate@1", implementation_digest="8" * 64),
                  *((PlanIdentity(plugin_id="ingestion.candidate@1", implementation_digest="7" * 64),)
                    if mode == "MULTI_AXIS_NON_CAUSAL" else ()))
    candidate_subject = candidate_subject.model_copy(update={
        "query_plan": candidate_query, "query_plan_digest": digest(candidate_query),
        "ingestion_plan": candidate_ingestion, "ingestion_plan_digest": digest(candidate_ingestion),
        "declared_identities": identities,
    })
    confidence_policy = ConfidencePolicy(kind="wilson", level=.95) if mode == "MULTI_AXIS_NON_CAUSAL" else ConfidencePolicy(kind="none")
    base_manifest = base_manifest.model_copy(update={"confidence_policy": confidence_policy})
    candidate_manifest = base_manifest.model_copy(update={"subjects": (baseline_subject, candidate_subject), "experiment_name": "fixture-parity"})
    metric = next(item for item in _evaluation_metric_reports(_EVALUATION_RUNS["failed-gates"], "failed-gates").values() if item.owner == "citation")
    baseline_metric = metric.model_copy(update={"status": MetricStatus.VALUE, "value": 0.0, "sample_count": 12, "labelled_count": 12, "matched_count": 0})
    candidate_metric = metric.model_copy(update={"status": MetricStatus.VALUE, "value": .3, "sample_count": 12, "labelled_count": 12, "matched_count": 8})
    baseline_metric_id, candidate_metric_id = uuid5(NAMESPACE_URL, f"s027:{mode}:baseline-metric"), uuid5(NAMESPACE_URL, f"s027:{mode}:candidate-metric")
    baseline_manifest_id, candidate_manifest_id = uuid5(NAMESPACE_URL, f"s027:{mode}:baseline-manifest"), uuid5(NAMESPACE_URL, f"s027:{mode}:candidate-manifest")
    baseline_report = report.model_copy(update={"manifest_artifact_id": baseline_manifest_id,
        "manifest_digest": hashlib.sha256(canonical_bytes(base_manifest)).hexdigest(), "report_ids": (baseline_metric_id,),
        "report_subjects": {baseline_metric_id: "baseline"}, "layers": {key: (baseline_metric_id,) if key == "answer" else () for key in report.layers},
        "gate_results": tuple(item.model_copy(update={"subject": "baseline"}) for item in report.gate_results),
        "failed_cases": tuple(item.model_copy(update={"subject": "baseline", "evaluation_run_id": UUID(_EVALUATION_RUN)}) for item in report.failed_cases)})
    candidate_report = report.model_copy(update={"manifest_artifact_id": candidate_manifest_id,
        "manifest_digest": hashlib.sha256(canonical_bytes(candidate_manifest)).hexdigest(), "report_ids": (candidate_metric_id,),
        "report_subjects": {candidate_metric_id: "candidate"}, "layers": {key: (candidate_metric_id,) if key == "answer" else () for key in report.layers},
        "gate_results": tuple(item.model_copy(update={"subject": "candidate", "state": GateState.PASS, "reason": "THRESHOLD", "value": .8}) for item in report.gate_results),
        "failed_cases": (), "operation": report.operation.model_copy(update={"elapsed_ms": 54000})})
    contents = {baseline_manifest_id: canonical_bytes(base_manifest), candidate_manifest_id: canonical_bytes(candidate_manifest),
                UUID(_COMPARISON_BASELINE): canonical_bytes(baseline_report),
                UUID(_COMPARISON_SINGLE if mode == "SINGLE_AXIS" else _COMPARISON_CANDIDATE): canonical_bytes(candidate_report),
                baseline_metric_id: metric_report_bytes(baseline_metric), candidate_metric_id: metric_report_bytes(candidate_metric)}
    types = {baseline_manifest_id: "evaluation.manifest", candidate_manifest_id: "evaluation.manifest",
             UUID(_COMPARISON_BASELINE): "evaluation.report", UUID(_COMPARISON_SINGLE if mode == "SINGLE_AXIS" else _COMPARISON_CANDIDATE): "evaluation.report",
             baseline_metric_id: "metric.report", candidate_metric_id: "metric.report"}
    class Runs:
        async def create_run(self, *_args): return UUID(_EVALUATION_RUN)
        async def start_attempt(self, *_args): return uuid5(NAMESPACE_URL, f"s027:{mode}:attempt"), 1
        async def finish_run(self, *_args): return None
    class Artifacts:
        async def get_artifact_manifest(self, identifier):
            raw = contents.get(identifier)
            return (ArtifactManifest(id=identifier, artifact_type=types[identifier], schema_revision="v1", content_digest=hashlib.sha256(raw).hexdigest(), byte_size=len(raw), summary="typed fixture", storage_locator="fixture", producing_run_id=UUID(_EVALUATION_RUN), producing_stage_attempt_id=uuid5(NAMESPACE_URL, f"s027:{mode}:producer"), producing_plugin_id="fixture@1", configuration_digest="a" * 64) if raw else None)
        async def read_content(self, identifier): return contents[identifier]
        async def complete_with_outputs(self, _run, _attempt, outputs, **_kwargs):
            item, raw = outputs[0]; contents[UUID(_COMPARISON)] = raw; types[UUID(_COMPARISON)] = item.artifact_type
            return (UUID(_COMPARISON),)
    candidate_id = UUID(_COMPARISON_SINGLE if mode == "SINGLE_AXIS" else _COMPARISON_CANDIDATE)
    artifacts = Artifacts()
    await EvaluationService().compare(UUID(_COMPARISON_BASELINE), candidate_id, Runs(), artifacts)
    return await ComparisonWorkbenchService(object(), artifacts).detail(UUID(_COMPARISON))


def _comparison_reports(candidate_id: str) -> dict[str, object]:
    manifest, report, _ = _evaluation_contracts(_EVALUATION_RUNS["failed-gates"], "failed-gates")
    summary = lambda report_id, run_id: {"reportId": report_id, "runId": run_id, "manifest": {
        "artifactId": str(report.manifest_artifact_id), "digest": report.manifest_digest,
        "datasetSnapshotId": str(manifest.dataset_snapshot_id), "datasetDigest": manifest.dataset_snapshot_digest,
        "taxonomyDigest": manifest.taxonomy_digest, "inputCatalogDigest": manifest.input_catalog_digest,
        "caseCount": len(manifest.case_ids), "metricCount": len(manifest.metric_ids)}}
    return {"baseline": summary(_COMPARISON_BASELINE, _EVALUATION_RUN), "candidate": summary(candidate_id, _EVALUATION_RUNS["passed-gates"])}


@fixture_app.get("/api/workbench/comparisons/eligible")
async def fixture_comparison_eligible(baselineReportId: str = "") -> JSONResponse:
    reports = _comparison_reports(_COMPARISON_CANDIDATE)
    rows = [reports["baseline"], reports["candidate"], _comparison_reports(_COMPARISON_SINGLE)["candidate"]]
    for row in rows:
        row["state"] = "SUCCEEDED"
        if baselineReportId:
            row["compatibility"] = {"state": "BASELINE" if row["reportId"] == baselineReportId else "COMPATIBLE", "reason": None}
    return JSONResponse(rows)


@fixture_app.post("/api/workbench/comparisons")
async def fixture_comparison_create(request: Request) -> JSONResponse:
    payload = await request.json()
    if payload == {"baselineReportId": _COMPARISON_BASELINE, "candidateReportId": _COMPARISON_BASELINE}:
        return JSONResponse({"contractVersion": "workbench-problem/v1", "code": "COMPARISON_INCOMPATIBLE", "reason": "SAME_REPORT"}, status_code=409)
    assert payload["baselineReportId"] == _COMPARISON_BASELINE and payload["candidateReportId"] in {_COMPARISON_CANDIDATE, _COMPARISON_SINGLE}
    if payload["candidateReportId"] == _COMPARISON_CANDIDATE:
        await asyncio.sleep(.3)
    mode = "SINGLE_AXIS" if payload["candidateReportId"] == _COMPARISON_SINGLE else "MULTI_AXIS_NON_CAUSAL"
    return JSONResponse({"valid": True, "runId": _EVALUATION_RUN, "artifactId": _COMPARISON,
                         "comparison": await _comparison_fixture(mode)}, status_code=201)


@fixture_app.get("/api/workbench/comparisons/{artifact_id}")
async def fixture_comparison_detail(artifact_id: str) -> JSONResponse:
    if artifact_id != _COMPARISON:
        return JSONResponse({"code": "COMPARISON_ARTIFACT_UNAVAILABLE"}, status_code=404)
    return JSONResponse(await _comparison_fixture())


@fixture_app.get("/api/workbench/runs")
async def fixture_run_history(runType: str = "", state: str = "", q: str = "") -> JSONResponse:
    if q == "slow-query" and not runType:
        await asyncio.sleep(.3)
        q = "browser-query"
    elif q == "slow-query":
        q = ""
    return JSONResponse(await _history_fixture_service().list(runType, state, q))


@fixture_app.get("/api/workbench/runs/{run_id}")
async def fixture_run_history_detail(run_id: str) -> JSONResponse:
    if run_id == _INGESTION_RUN:
        await asyncio.sleep(.25)
    detail = await _history_fixture_service().detail(UUID(run_id))
    if detail is None:
        return JSONResponse({"code": "RUN_NOT_FOUND"}, status_code=404)
    detail["actions"] = ({"stop": True} if run_id == _HISTORY_QUERY and not _active_query_stopped else
                         {"rerun": True} if run_id == _INGESTION_RUN else {})
    return JSONResponse(detail)


def _history_fixture_service() -> RunHistoryWorkbenchService:
    now = datetime(2026, 9, 13, tzinfo=timezone.utc)
    identifiers = {
        "INGESTION": _INGESTION_RUN, "QUERY": _HISTORY_QUERY, "EVALUATION": _EVALUATION_RUNS["passed-gates"],
        "COMPARISON": _HISTORY_COMPARISON, "CONTRACT_TEST": _HISTORY_CONTRACT,
    }
    plans = {
        UUID(identifiers["INGESTION"]): {"schema_version": "v1", "profile_id": "fixture-ingestion", "stages": [{"axis": "extraction", "sub_stages": [{"stage_id": "parse", "candidates": [{"plugin_id": "parser.fixture@1"}]}]}]},
        UUID(identifiers["QUERY"]): {"schema_version": "v1", "profile_id": "browser-query", "search_artifact": {"artifact_id": _ARTIFACT}, "stages": [{"stage_id": "evidence", "plugin_id": "context.fixture@1"}]},
        UUID(identifiers["EVALUATION"]): {"kind": "evaluation_run", "manifest_id": str(_evaluation_fixture_id(_EVALUATION_RUNS["passed-gates"], "manifest"))},
        UUID(identifiers["COMPARISON"]): {"kind": "evaluation_comparison", "baseline": _COMPARISON_BASELINE, "candidate": _COMPARISON_CANDIDATE},
        UUID(identifiers["CONTRACT_TEST"]): {"kind": "contract_test", "contract_id": "fixture.contract.v1", "plugin_id": "retriever.keyword@1"},
    }
    engine = {"INGESTION": "ingestion", "QUERY": "query", "EVALUATION": "evaluation", "COMPARISON": "evaluation", "CONTRACT_TEST": "evaluation"}
    state = {"QUERY": "RUNNING", "INGESTION": "FAILED", "EVALUATION": "SUCCEEDED", "COMPARISON": "SUCCEEDED", "CONTRACT_TEST": "SUCCEEDED"}
    rows = []
    for index, (kind, identifier) in enumerate(identifiers.items()):
        started = now.replace(minute=index)
        terminal = None if kind == "QUERY" else state[kind]
        rows.append({"id": UUID(identifier), "engine_kind": engine[kind], "state": state[kind], "terminal_state": terminal,
                     "created_at": started, "started_at": started, "ended_at": None if kind == "QUERY" else started.replace(second=2 + index),
                     "plan_digest": str(index + 1) * 64, "plan_json": plans[UUID(identifier)]})
    traces = {}
    for index, (kind, identifier) in enumerate(identifiers.items()):
        running = kind == "QUERY"
        engine_kind = {"ingestion": EngineKind.INGESTION, "query": EngineKind.QUERY, "evaluation": EngineKind.EVALUATION}[engine[kind]]
        input_ref = ArtifactReference(id=UUID(_ARTIFACT), artifact_type="fixture.input", schema_revision="v1", content_digest="8" * 64, byte_size=256, summary=f"{kind.lower()} input")
        output_id, output_type = ((UUID(_COMPARISON), "evaluation.comparison") if kind == "COMPARISON" else
                                  (UUID(_ARTIFACT), "evidence.set") if kind == "QUERY" else
                                  (UUID(_ARTIFACT), f"{kind.lower()}.result"))
        output_ref = ArtifactReference(id=output_id, artifact_type=output_type, schema_revision="v1", content_digest="9" * 64, byte_size=512, summary="citation-ready Evidence" if kind == "QUERY" else f"{kind.lower()} output")
        traces[UUID(identifier)] = RunTrace(id=UUID(identifier), engine_kind=engine_kind, plan_digest=str(index + 1) * 64,
            state=RunState.RUNNING if running else RunState(state[kind]), terminal_state=None if running else RunState(state[kind]),
            created_at=now.replace(minute=index), started_at=now.replace(minute=index), ended_at=None if running else now.replace(minute=index, second=2 + index),
            stages=(StageTrace(id=_evaluation_fixture_id(identifier, "stage"), stage_key="evidence" if kind == "QUERY" else f"{kind.lower()}.execute", attempt_number=1,
                state=StageState.RUNNING if running else StageState.SUCCEEDED, result=None, started_at=now.replace(minute=index),
                ended_at=None if running else now.replace(minute=index, second=2 + index), summary=f"{kind.lower()} trace", safe_error=None,
                inputs=(input_ref,), outputs=(output_ref,)),))
    class Traces:
        async def list_workbench_run_history(self, limit):
            assert limit == 100
            return rows
        async def get_run_trace(self, identifier):
            return traces.get(identifier)
        async def get_run_plan(self, identifier):
            return plans.get(identifier)
    return RunHistoryWorkbenchService(Traces())


@fixture_app.post("/api/workbench/query-runs/{run_id}/stop")
async def fixture_stop_query_run(run_id: str) -> JSONResponse:
    global _active_query_stopped
    assert run_id in {_HISTORY_QUERY, _QUERY_RUNS["active"]}
    if run_id == _HISTORY_QUERY:
        await asyncio.sleep(.3)
    _active_query_stopped = True
    return JSONResponse({"stopped": True})


@fixture_app.get("/workbench/assets/{asset_name}")
async def fixture_asset(asset_name: str) -> FileResponse:
    media_type = {
        "workbench.js": "text/javascript",
        "workbench.css": "text/css",
        "artifact.css": "text/css",
        "archivo-400.woff2": "font/woff2",
        "archivo-600.woff2": "font/woff2",
        "archivo-800.woff2": "font/woff2",
    }.get(asset_name)
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
    page = next(page for page in reversed(pages) if page.get("type") == "page" and (page.get("url") == target_url if target_url else "/workbench/" in page.get("url", "")))
    if port in _CAPTURE_CONNECTIONS:
        result = _send_cdp(_CAPTURE_CONNECTIONS[port], "Runtime.evaluate", {"expression": expression, "awaitPromise": await_promise, "returnByValue": True})
        if "exceptionDetails" in result:
            pytest.fail(result["exceptionDetails"]["exception"]["description"])
        return result["result"].get("value")
    protocol_error: object = None
    for attempt in range(3):
        connection = websocket.create_connection(page["webSocketDebuggerUrl"], origin="http://localhost")
        request_id = attempt + 1
        try:
            connection.send(json.dumps({"id": request_id, "method": "Runtime.evaluate", "params": {"expression": expression, "awaitPromise": await_promise, "returnByValue": True}}))
            while True:
                message = json.loads(connection.recv())
                if message.get("id") != request_id:
                    continue
                if "error" in message:
                    protocol_error = message["error"]
                    break
                if "exceptionDetails" in message.get("result", {}):
                    pytest.fail(message["result"]["exceptionDetails"]["exception"]["description"])
                return message["result"]["result"].get("value")
        finally:
            connection.close()
        time.sleep(.05)
    pytest.fail(f"Chrome DevTools evaluation did not return a result: {protocol_error}")


def _capture_cdp(port: int, target: Path, *, target_url: str | None = None) -> None:
    pages = httpx.get(f"http://127.0.0.1:{port}/json", timeout=1).json()
    page = next(page for page in reversed(pages) if page.get("type") == "page" and (page.get("url") == target_url if target_url else "/workbench/" in page.get("url", "")))
    socket = _CAPTURE_CONNECTIONS.get(port) or websocket.create_connection(page["webSocketDebuggerUrl"], origin="http://localhost")
    owned = port not in _CAPTURE_CONNECTIONS
    try:
        result = _send_cdp(socket, "Page.captureScreenshot", {"format": S022_CAPTURE["screenshotFormat"]})
        target.write_bytes(base64.b64decode(result["data"]))
    finally:
        if owned:
            socket.close()


def _assert_root_scroll_locked(port: int, *, target_url: str) -> None:
    """Wait for modal layout to settle and reject captures with a root scrollbar."""
    state = _cdp(
        port,
        "(async()=>{await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));const root=document.documentElement;return {rootClass:root.classList.contains('modal-open'),bodyClass:document.body.classList.contains('modal-open'),rootOverflow:getComputedStyle(root).overflowY,bodyOverflow:getComputedStyle(document.body).overflowY,viewportWidth:innerWidth,rootClientWidth:root.clientWidth,rootScrollbarWidth:innerWidth-root.clientWidth}})()",
        await_promise=True,
        target_url=target_url,
    )
    assert isinstance(state, dict)
    assert state["viewportWidth"] in {1440, 644}
    assert state == {
        "rootClass": True,
        "bodyClass": True,
        "rootOverflow": "hidden",
        "bodyOverflow": "hidden",
        "viewportWidth": state["viewportWidth"],
        "rootClientWidth": state["viewportWidth"],
        "rootScrollbarWidth": 0,
    }


def _assert_root_scroll_unlocked(port: int, *, target_url: str) -> None:
    """Settle a non-modal capture and reject leaked modal scroll state."""
    state = _cdp(
        port,
        "(async()=>{await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));const root=document.documentElement;return {rootClass:root.classList.contains('modal-open'),bodyClass:document.body.classList.contains('modal-open'),rootOverflow:getComputedStyle(root).overflowY,bodyOverflow:getComputedStyle(document.body).overflowY,viewportWidth:innerWidth,rootClientWidth:root.clientWidth,rootScrollbarWidth:innerWidth-root.clientWidth}})()",
        await_promise=True,
        target_url=target_url,
    )
    assert isinstance(state, dict)
    assert state["viewportWidth"] in {1440, 644}
    assert state == {
        "rootClass": False,
        "bodyClass": False,
        "rootOverflow": "auto",
        "bodyOverflow": "auto",
        "viewportWidth": state["viewportWidth"],
        "rootClientWidth": state["viewportWidth"],
        "rootScrollbarWidth": 0,
    }


def _send_cdp(connection: websocket.WebSocket, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
    global _CDP_REQUEST_ID
    _CDP_REQUEST_ID += 1
    request_id = _CDP_REQUEST_ID
    connection.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
    while True:
        message = json.loads(connection.recv())
        if message.get("id") != request_id:
            continue
        if "error" in message:
            pytest.fail(f"Chrome DevTools command failed: {message['error']}")
        return message.get("result", {})


def _assert_manifest_visual(
    port: int,
    current: Path,
    baseline_name: str,
    *,
    target_url: str,
    baseline_root: Path = S022_BASELINE_ROOT,
    story: str = "S-022",
) -> None:
    """Decode through Chrome and compare RGBA pixels without mutating baselines."""
    baseline = baseline_root / baseline_name
    assert baseline.is_file(), f"missing reviewed {story} baseline: {baseline}"
    current_url = "data:image/png;base64," + base64.b64encode(current.read_bytes()).decode("ascii")
    baseline_url = "data:image/png;base64," + base64.b64encode(baseline.read_bytes()).decode("ascii")
    expression = f"""(async()=>{{
      const load=source=>new Promise((resolve,reject)=>{{const image=new Image();image.onload=()=>resolve(image);image.onerror=reject;image.src=source}});
      const [expected,actual]=await Promise.all([load({json.dumps(baseline_url)}),load({json.dumps(current_url)})]);
      if(expected.width!==actual.width||expected.height!==actual.height)return {{dimensions:[expected.width,expected.height,actual.width,actual.height],ratio:1,bounds:null,diffPng:null}};
      const canvas=document.createElement('canvas'),other=document.createElement('canvas');canvas.width=other.width=expected.width;canvas.height=other.height=expected.height;
      const expectedPixels=canvas.getContext('2d',{{willReadFrequently:true}}),actualPixels=other.getContext('2d',{{willReadFrequently:true}});expectedPixels.drawImage(expected,0,0);actualPixels.drawImage(actual,0,0);
      const before=expectedPixels.getImageData(0,0,canvas.width,canvas.height).data,after=actualPixels.getImageData(0,0,canvas.width,canvas.height).data;
      const diff=expectedPixels.createImageData(canvas.width,canvas.height);let count=0,minX=canvas.width,minY=canvas.height,maxX=-1,maxY=-1;
      for(let offset=0,pixel=0;offset<before.length;offset+=4,pixel++){{let changed=false;for(let channel=0;channel<4;channel++)if(Math.abs(before[offset+channel]-after[offset+channel])>12)changed=true;if(changed){{count++;const x=pixel%canvas.width,y=Math.floor(pixel/canvas.width);minX=Math.min(minX,x);minY=Math.min(minY,y);maxX=Math.max(maxX,x);maxY=Math.max(maxY,y);diff.data.set([236,48,19,255],offset)}}else diff.data.set([before[offset]/3,before[offset+1]/3,before[offset+2]/3,72],offset)}}
      const ratio=count/(canvas.width*canvas.height);let diffPng=null;if(ratio>0.005){{expectedPixels.putImageData(diff,0,0);diffPng=canvas.toDataURL('image/png').split(',')[1]}}
      return {{dimensions:[expected.width,expected.height,actual.width,actual.height],ratio,bounds:count?[minX,minY,maxX,maxY]:null,diffPng}};
    }})()"""
    result = _cdp(port, expression, await_promise=True, target_url=target_url)
    assert isinstance(result, dict)
    if result["ratio"] > 0.005:
        current_diagnostic = current.with_name(f"{baseline.stem}-current.png")
        diff_diagnostic = current.with_name(f"{baseline.stem}-diff.png")
        shutil.copyfile(current, current_diagnostic)
        if result["diffPng"]:
            diff_diagnostic.write_bytes(base64.b64decode(result["diffPng"]))
        pytest.fail(
            f"{story} visual difference {result['ratio']:.4%} exceeds 0.5% "
            f"(channel tolerance 12, dimensions {result['dimensions']}, bounds {result['bounds']}); "
            f"current={current_diagnostic}, diff={diff_diagnostic}"
        )


def _cdp_command(
    port: int,
    method: str,
    params: dict[str, object] | None = None,
    *,
    target_url: str | None = None,
) -> dict[str, object]:
    if connection := _CAPTURE_CONNECTIONS.get(port):
        return _send_cdp(connection, method, params)
    for _ in range(60):
        try:
            pages = httpx.get(f"http://127.0.0.1:{port}/json", timeout=0.2).json()
            if any(
                page.get("type") == "page"
                and (page.get("url") == target_url if target_url else "/workbench/" in page.get("url", ""))
                for page in pages
            ):
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    else:
        pytest.fail("Chrome DevTools endpoint did not start")
    page = next(
        page
        for page in pages
        if page.get("type") == "page"
        and (page.get("url") == target_url if target_url else "/workbench/" in page.get("url", ""))
    )
    connection = websocket.create_connection(page["webSocketDebuggerUrl"], origin="http://localhost")
    try:
        connection.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
        while True:
            message = json.loads(connection.recv())
            if message.get("id") != 1:
                continue
            if "error" in message:
                pytest.fail(f"Chrome DevTools command failed: {message['error']}")
            return message.get("result", {})
    finally:
        connection.close()


def _assert_s022_visual(port: int, current: Path, baseline_name: str, *, target_url: str) -> None:
    _assert_manifest_visual(port, current, baseline_name, target_url=target_url)


def _prepare_s022_capture_environment(port: int, target_url: str, width: int) -> None:
    """Apply and verify every rendering condition recorded with the goldens."""
    device = S022_CAPTURE["device"]
    media = S022_CAPTURE["media"]
    for _ in range(60):
        try:
            pages = httpx.get(f"http://127.0.0.1:{port}/json", timeout=0.2).json()
            page = next(page for page in pages if page.get("type") == "page" and page.get("url") == target_url)
            break
        except (httpx.HTTPError, StopIteration):
            time.sleep(0.1)
    else:
        pytest.fail("Chrome DevTools endpoint did not start")
    connection = websocket.create_connection(page["webSocketDebuggerUrl"], origin="http://localhost")
    _CAPTURE_CONNECTIONS[port] = connection
    _send_cdp(
        connection,
        "Emulation.setDeviceMetricsOverride",
        {
            "width": width,
            "height": 900,
            "deviceScaleFactor": device["deviceScaleFactor"],
            "mobile": device["mobile"],
        },
    )
    _send_cdp(
        connection,
        "Emulation.setEmulatedMedia",
        {
            "media": media["type"],
            "features": [
                {"name": "prefers-color-scheme", "value": media["colorScheme"]},
                {"name": "forced-colors", "value": media["forcedColors"]},
                {"name": "prefers-reduced-motion", "value": media["reducedMotion"]},
            ],
        },
    )
    _send_cdp(
        connection,
        "Emulation.setLocaleOverride",
        {"locale": S022_CAPTURE["locale"]["browser"]},
    )

    version = httpx.get(f"http://127.0.0.1:{port}/json/version", timeout=1).json()
    browser = S022_CAPTURE["browser"]
    assert {
        "product": version["Browser"],
        "protocolVersion": version["Protocol-Version"],
        "userAgent": version["User-Agent"],
        "javascriptRuntime": f"V8 {version['V8-Version']}",
        "renderingEngine": version["WebKit-Version"],
    } == {key: browser[key] for key in ("product", "protocolVersion", "userAgent", "javascriptRuntime", "renderingEngine")}

    conditions = _cdp(
        port,
        """(async()=>{
          for(let i=0;i<100&&document.readyState!=='complete';i++)await new Promise(resolve=>setTimeout(resolve,20));
          let stability=document.querySelector('#s022-capture-stability');if(!stability){stability=document.createElement('style');stability.id='s022-capture-stability';stability.textContent='*{animation:none!important;transition:none!important;caret-color:transparent!important}';document.head.append(stability)}
          await document.fonts.ready;const resources=performance.getEntriesByType('resource'),faces=[...document.fonts].filter(face=>face.family.replaceAll('"','')==='Archivo').map(face=>[Number(face.weight),face.status]).sort((a,b)=>a[0]-b[0]);
          return {viewport:[innerWidth,innerHeight,devicePixelRatio],locale:[navigator.language,document.documentElement.lang],media:[matchMedia('(prefers-color-scheme: light)').matches,!matchMedia('(forced-colors: active)').matches,matchMedia('(prefers-reduced-motion: no-preference)').matches],ready:[document.readyState,faces,[400,600,800].every(weight=>resources.some(resource=>resource.name.endsWith(`/workbench/assets/archivo-${weight}.woff2`)))],stability:stability.textContent};
        })()""",
        await_promise=True,
        target_url=target_url,
    )
    assert conditions == {
        "viewport": [width, 900, device["deviceScaleFactor"]],
        "locale": [S022_CAPTURE["locale"]["browser"], S022_CAPTURE["locale"]["document"]],
        "media": [True, True, True],
        "ready": [
            S022_CAPTURE["readiness"]["document"],
            [[weight, S022_CAPTURE["readiness"]["archivoFaceStatus"]] for weight in S022_CAPTURE["readiness"]["archivoWeights"]],
            S022_CAPTURE["readiness"]["assetResourceTimingRequired"],
        ],
        "stability": "*{animation:none!important;transition:none!important;caret-color:transparent!important}",
    }


def _free_local_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_fixture(url: str) -> None:
    for _ in range(60):
        try:
            if httpx.get(url, timeout=0.2).is_success:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.05)
    pytest.fail("Fixture server did not start")


def _launch_isolated_chrome(arguments: list[str]) -> subprocess.Popen[str]:
    """Start an isolated Chrome instance rather than handing off to macOS's app singleton."""
    return subprocess.Popen([str(CHROME), *arguments], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)


def _close_isolated_chrome(port: int, browser: subprocess.Popen[str]) -> tuple[str | None, str | None]:
    """Close the CDP-owned app on macOS; the launcher process may already have exited."""
    capture_connection = _CAPTURE_CONNECTIONS.pop(port, None)
    if capture_connection is not None:
        capture_connection.close()
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


def test_s024_visual_manifest_is_pinned_and_baselines_are_reviewed_assets() -> None:
    assert S024_MANIFEST["captureConditions"] == S022_CAPTURE
    assert S024_MANIFEST["comparison"] == {
        "colorSpace": "RGBA", "channelTolerance": 12,
        "maximumDifferingPixelRatio": 0.005, "baselineUpdatesAutomatic": False,
    }
    assert len(S024_MANIFEST["baselines"]) == 6
    for record in S024_MANIFEST["baselines"]:
        baseline = S024_BASELINE_ROOT / record["file"]
        assert baseline.is_file()
        assert hashlib.sha256(baseline.read_bytes()).hexdigest() == record["sha256"]


def test_s025_s026_s027_visual_manifests_are_pinned_and_complete() -> None:
    expectations = ((S025_BASELINE_ROOT, "S-025", {"UI-005", "UI-008", "UI-013"}, 14),
                    (S026_BASELINE_ROOT, "S-026", {"UI-009", "UI-010", "UI-013"}, 10),
                    (S027_BASELINE_ROOT, "S-027", {"UI-011", "UI-012", "UI-013"}, 6))
    for root, story, anchors, count in expectations:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["story"] == story
        assert set(manifest["uiAnchors"]) == anchors
        assert manifest["prototypeSha256"] == hashlib.sha256(Path("docs/ui/kb_ui.zip").read_bytes()).hexdigest()
        assert manifest["captureConditions"] == S022_CAPTURE
        assert manifest["comparison"] == {"colorSpace": "RGBA", "channelTolerance": 12, "maximumDifferingPixelRatio": .005, "baselineUpdatesAutomatic": False}
        assert len(manifest["baselines"]) == count
        assert {tuple(record["viewport"]) for record in manifest["baselines"]} == {(1440, 900), (644, 900)}
        for record in manifest["baselines"]:
            baseline = root / record["file"]
            assert hashlib.sha256(baseline.read_bytes()).hexdigest() == record["sha256"]


def test_s028_visual_manifest_is_pinned_and_complete() -> None:
    manifest = json.loads((S028_BASELINE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["story"] == "S-028"
    assert set(manifest["uiAnchors"]) == {"UI-003", "UI-005", "UI-013"}
    assert manifest["prototypeSha256"] == hashlib.sha256(Path("docs/ui/kb_ui.zip").read_bytes()).hexdigest()
    assert manifest["captureConditions"] == S022_CAPTURE
    assert manifest["comparison"] == {"colorSpace": "RGBA", "channelTolerance": 12, "maximumDifferingPixelRatio": .005, "baselineUpdatesAutomatic": False}
    assert len(manifest["baselines"]) == 8
    assert {record["scenario"] for record in manifest["baselines"]} == {"populated", "empty", "loading", "error"}
    assert {tuple(record["viewport"]) for record in manifest["baselines"]} == {(1440, 900), (644, 900)}
    for record in manifest["baselines"]:
        baseline = S028_BASELINE_ROOT / record["file"]
        assert hashlib.sha256(baseline.read_bytes()).hexdigest() == record["sha256"]


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for browser shell evidence",
)
@pytest.mark.parametrize(
    ("fixture_state", "expected_state", "width"),
    (
        ("populated", "populated", 1440),
        ("empty", "populated", 1440),
        ("dependency", "populated", 1440),
        ("loading", "loading", 1440),
        ("first-error", "error", 1440),
        ("refresh-error", "populated", 1440),
        ("populated", "populated", 644),
    ),
)
def test_fixture_backed_workbench_shell_renders_deterministic_overview_states(
    tmp_path: Path, fixture_state: str, expected_state: str, width: int
) -> None:
    """Exercise semantic state, geometry, and visual evidence from shipped assets."""
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    environment["KB2_WORKBENCH_FIXTURE_STATE"] = fixture_state
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment,
    )
    url = f"http://127.0.0.1:{port}/workbench/overview?workspace=local_demo"
    browser: subprocess.Popen[str] | None = None
    try:
        for _ in range(80):
            try:
                if httpx.get(url, timeout=0.2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            pytest.fail("FastAPI workbench shell did not start")
        browser = _launch_isolated_chrome([
            *S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}",
            f"--window-size={width},900", f"--user-data-dir={tmp_path / fixture_state}", url,
        ])
        _prepare_s022_capture_environment(debug_port, url, width)
        wait_for_state = f"""(async()=>{{for(let i=0;i<160;i++){{if(document.querySelector('[data-overview-state="{expected_state}"]'))return true;await new Promise(r=>setTimeout(r,25))}}throw new Error('overview state did not render')}})()"""
        assert _cdp(debug_port, wait_for_state, await_promise=True, target_url=url) is True
        if fixture_state == "loading":
            assert _cdp(debug_port, "document.querySelectorAll('.skeleton-line').length >= 6", target_url=url) is True
        if fixture_state == "first-error":
            assert _cdp(debug_port, "document.querySelector('[role=alert]').textContent.includes('无法刷新概览')", target_url=url) is True
            unavailable_context = _cdp(
                debug_port,
                "[...document.querySelectorAll('.context-bar .context-group')].map(x=>[x.querySelector('.context-label')?.textContent,x.querySelector('.status-tag')?.textContent,x.querySelector('.context-skeleton')===null])",
                target_url=url,
            )
            assert unavailable_context == [
                ["核心", "状态不可用", True],
                ["外部能力", "状态不可用", True],
                ["Plugin", "状态不可用", True],
                ["活动 Run", "状态不可用", True],
            ]
            unavailable_regions = _cdp(
                debug_port,
                """(()=>{const surface=document.querySelector('.overview-surface'),regions=[surface.querySelector(':scope > .dependency-band'),surface.querySelector(':scope > .overview-grid > .overview-runs'),surface.querySelector(':scope > .overview-grid > .overview-side > .overview-failures'),surface.querySelector(':scope > .overview-grid > .overview-side > .overview-comparisons')];return {commands:[...document.querySelectorAll('.overview-commands .command-link')].map(link=>link.pathname),grid:!!surface.querySelector(':scope > .overview-grid > .overview-side'),regions:regions.map(region=>({labelledby:region.getAttribute('aria-labelledby'),heading:region.querySelector('h2').textContent,meta:region.querySelector('.section-meta').textContent,unavailable:region.querySelector('.empty-state strong').textContent,retry:region.querySelector('.empty-state button').textContent}))}})()""",
                target_url=url,
            )
            assert unavailable_regions == {
                "commands": [
                    "/workbench/documents", "/workbench/studio", "/workbench/query",
                    "/workbench/evaluation-dataset",
                ],
                "grid": True,
                "regions": [
                    {"labelledby": "dependency-title", "heading": "依赖状态", "meta": "不可用", "unavailable": "依赖状态不可用", "retry": "重新刷新"},
                    {"labelledby": "recent-runs-title", "heading": "最近运行", "meta": "不可用", "unavailable": "最近运行不可用", "retry": "重新刷新"},
                    {"labelledby": "failed-runs-title", "heading": "失败分诊", "meta": "不可用", "unavailable": "失败分诊不可用", "retry": "重新刷新"},
                    {"labelledby": "comparisons-title", "heading": "最近比较", "meta": "不可用", "unavailable": "最近比较不可用", "retry": "重新刷新"},
                ],
            }
            assert _cdp(debug_port, "[...document.querySelectorAll('button')].find(x=>x.textContent==='重新刷新').click(); true", target_url=url) is True
            assert _cdp(debug_port, "(async()=>{for(let i=0;i<100;i++){if(document.querySelector('[data-overview-state=populated]'))return true;await new Promise(r=>setTimeout(r,25))}return false})()", await_promise=True, target_url=url) is True
        if fixture_state == "refresh-error":
            assert _cdp(debug_port, "document.querySelector('[aria-label=\"刷新概览\"]').click(); true", target_url=url) is True
            assert _cdp(debug_port, "(async()=>{for(let i=0;i<100;i++){if(document.querySelector('[data-overview-state=stale]'))return document.body.innerText.includes('TRACE_STORAGE_FAILURE');await new Promise(r=>setTimeout(r,25))}return false})()", await_promise=True, target_url=url) is True

        evidence = _cdp(debug_port, f"""(async()=>{{
          await document.fonts.ready;
          const sidebar=document.querySelector('.sidebar'), shell=document.querySelector('.shell'), top=document.querySelector('.top'), command=document.querySelector('.command-link');command.focus();
          const paths=[...document.querySelectorAll('.sidebar .nav-link')].map(x=>x.pathname);
          const drawerPaths=[...document.querySelectorAll('#drawer .nav-link')].map(x=>x.pathname);
          const commands=[...document.querySelectorAll('.overview-commands .command-link')].map(x=>x.pathname);
          const overviewRequests=(await fetch('/api/fixture/overview-request-count').then(x=>x.json())).count;
          const resources=performance.getEntriesByType('resource');
          const archivoFaces=[...document.fonts].filter(face=>face.family.replaceAll('"','')==='Archivo').map(face=>[Number(face.weight),face.status]).sort((a,b)=>a[0]-b[0]);
          return {{desktopLinks:document.querySelectorAll('.sidebar .nav-link').length,drawerLinks:document.querySelectorAll('#drawer .nav-link').length,paths,drawerPaths,commands,workspace:[...document.querySelectorAll('.nav-link,.command-link')].every(x=>new URL(x.href).searchParams.get('workspace')==='local_demo'),contexts:document.querySelectorAll('.context-bar .context-group').length,overviewRequests,fontAssets:[400,600,800].every(weight=>resources.some(resource=>resource.name.endsWith(`/workbench/assets/archivo-${{weight}}.woff2`))),archivoFaces,overflow:document.documentElement.scrollWidth<=innerWidth,viewport:[innerWidth,innerHeight,devicePixelRatio],sidebar:{'true' if width >= 900 else 'false'}?Math.abs(sidebar.getBoundingClientRect().width-220)<=1:getComputedStyle(sidebar).display==='none',menu:{'true' if width < 900 else 'false'}?getComputedStyle(document.querySelector('.menu')).display!=='none':getComputedStyle(document.querySelector('.menu')).display==='none',body:{'true' if width >= 900 else 'false'}?Math.abs(shell.children[1].getBoundingClientRect().left-220)<=1:true,sticky:getComputedStyle(top).position==='sticky',radius:getComputedStyle(command).borderRadius==='0px',focus:getComputedStyle(command).outlineWidth==='2px',prototype:!document.body.innerText.includes('Prototype control')&&!document.querySelector('[aria-label*=语言]')}}
        }})()""", await_promise=True, target_url=url)
        expected_paths = [
            "/workbench/overview", "/workbench/documents", "/workbench/studio",
            "/workbench/query", "/workbench/evaluation-dataset", "/workbench/compare",
            "/workbench/runs", "/workbench/plugins",
        ]
        assert evidence == {
            "desktopLinks": 8,
            "drawerLinks": 8,
            "paths": expected_paths,
            "drawerPaths": expected_paths,
            "commands": [
                "/workbench/documents", "/workbench/studio", "/workbench/query",
                "/workbench/evaluation-dataset",
            ],
            "workspace": True,
            "contexts": 4,
            "overviewRequests": 2 if fixture_state in {"first-error", "refresh-error"} else 1,
            "fontAssets": True,
            "archivoFaces": [[400, "loaded"], [600, "loaded"], [800, "loaded"]],
            "overflow": True,
            "viewport": [width, 900, 1],
            "sidebar": True,
            "menu": True,
            "body": True,
            "sticky": True,
            "radius": True,
            "focus": True,
            "prototype": True,
        }

        text_state = _cdp(debug_port, "document.body.innerText", target_url=url)
        if fixture_state in {"populated", "refresh-error"}:
            assert "TRACE_STORAGE_FAILURE" in text_state
            assert "CANDIDATE_ELIGIBLE" in text_state
            assert _cdp(debug_port, "document.querySelectorAll('.recovery-action').length", target_url=url) == 1
        elif fixture_state == "empty":
            assert "尚无运行记录" in text_state and "尚无比较结果" in text_state
        elif fixture_state == "dependency":
            assert "部分依赖不可用" in text_state and "RUNNER_UNAVAILABLE" in text_state

        image = tmp_path / f"s022-{fixture_state}-{width}.png"
        _capture_cdp(debug_port, image, target_url=url)
        assert image.stat().st_size > 1_000
        baseline_names = {
            ("populated", 1440): "overview-populated-1440.png",
            ("empty", 1440): "overview-empty-1440.png",
            ("dependency", 1440): "overview-dependency-1440.png",
            ("loading", 1440): "overview-loading-1440.png",
            ("refresh-error", 1440): "overview-refresh-error-1440.png",
            ("populated", 644): "overview-populated-644.png",
        }
        if baseline_name := baseline_names.get((fixture_state, width)):
            _assert_s022_visual(debug_port, image, baseline_name, target_url=url)

        if fixture_state == "populated" and width == 1440:
            keyboard_contract = _cdp(
                debug_port,
                "(()=>{const links=[...document.querySelectorAll('.sidebar .nav-link')];const target=links.find(x=>x.pathname==='/workbench/documents');target.focus();return {native:links.every(x=>x.tagName==='A'&&x.tabIndex===0),focused:document.activeElement===target,labels:links.map(x=>x.textContent)}})()",
                target_url=url,
            )
            assert keyboard_contract == {
                "native": True,
                "focused": True,
                "labels": ["概览", "文档", "Profile Studio", "Query Lab", "评估数据集", "比较", "运行记录", "插件注册表"],
            }
            _cdp_command(
                debug_port,
                "Input.dispatchKeyEvent",
                {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13},
                target_url=url,
            )
            document_url = f"http://127.0.0.1:{port}/workbench/documents?workspace=local_demo"
            assert _cdp(debug_port, "location.pathname", target_url=document_url) == "/workbench/documents"
            evaluation_url = f"http://127.0.0.1:{port}/workbench/evaluation-run?workspace=local_demo&run={_EVALUATION_RUN}"
            _cdp(debug_port, f"location.assign({json.dumps(evaluation_url)}); true", target_url=document_url)
            child_route = _cdp(
                debug_port,
                "(async()=>{for(let i=0;i<100;i++){const current=[...document.querySelectorAll('.nav-link[aria-current=page]')];if(current.length===2)return {paths:current.map(x=>x.pathname),crumb:document.querySelector('.crumb [aria-current=page]').textContent};await new Promise(r=>setTimeout(r,25))}return null})()",
                await_promise=True,
                target_url=evaluation_url,
            )
            assert child_route == {
                "paths": ["/workbench/evaluation-dataset", "/workbench/evaluation-dataset"],
                "crumb": "评估运行",
            }
        if fixture_state == "loading":
            httpx.post(f"http://127.0.0.1:{port}/api/workbench/overview/release", timeout=1).raise_for_status()
    finally:
        if browser is not None:
            _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for drawer evidence",
)
def test_fixture_backed_narrow_drawer_geometry_and_focus_contract(tmp_path: Path) -> None:
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}", "KB2_WORKBENCH_FIXTURE_STATE": "populated"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
    url = f"http://127.0.0.1:{port}/workbench/overview?workspace=local_demo"
    browser: subprocess.Popen[str] | None = None
    try:
        for _ in range(80):
            try:
                if httpx.get(url, timeout=.2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(.1)
        browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", "--window-size=644,900", f"--user-data-dir={tmp_path / 'drawer'}", url])
        _prepare_s022_capture_environment(debug_port, url, 644)
        open_drawer = """(async()=>{for(let i=0;i<120;i++){if(document.querySelector('[data-overview-state=populated]'))break;await new Promise(r=>setTimeout(r,25))}const menu=document.querySelector('[aria-label="打开导航"]');menu.focus();menu.click();const modal=document.querySelector('#drawer'),panel=document.querySelector('.drawer-panel'),links=[...modal.querySelectorAll('.nav-link')],focusables=[...modal.querySelectorAll('button,a')];focusables.at(-1).focus();document.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',bubbles:true}));return {width:Math.abs(panel.getBoundingClientRect().width-220)<=1,left:Math.abs(panel.getBoundingClientRect().left)<=1,inert:document.querySelector('#workbench-shell').hasAttribute('inert'),modal:modal.getAttribute('aria-modal')==='true',looped:document.activeElement===focusables[0],links:links.length,viewport:[innerWidth,innerHeight,devicePixelRatio],overflow:document.documentElement.scrollWidth<=innerWidth}})()"""
        assert _cdp(debug_port, open_drawer, await_promise=True, target_url=url) == {"width": True, "left": True, "inert": True, "modal": True, "looped": True, "links": 8, "viewport": [644, 900, 1], "overflow": True}
        image = tmp_path / "s022-populated-drawer-open-644.png"
        _capture_cdp(debug_port, image, target_url=url)
        _assert_s022_visual(debug_port, image, "overview-drawer-open-644.png", target_url=url)
        close_drawer = """(async()=>{const menu=document.querySelector('[aria-label="打开导航"]'),modal=document.querySelector('#drawer');document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await new Promise(r=>setTimeout(r,20));return {closed:!modal.classList.contains('open'),focusReturned:document.activeElement===menu,inertRemoved:!document.querySelector('#workbench-shell').hasAttribute('inert')}})()"""
        assert _cdp(debug_port, close_drawer, await_promise=True, target_url=url) == {"closed": True, "focusReturned": True, "inertRemoved": True}
    finally:
        if browser is not None:
            _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for breakpoint evidence",
)
def test_fixture_backed_navigation_survives_both_breakpoint_resize_directions(tmp_path: Path) -> None:
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}", "KB2_WORKBENCH_FIXTURE_STATE": "populated"}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
    )
    url = f"http://127.0.0.1:{port}/workbench/overview?workspace=local_demo"
    browser: subprocess.Popen[str] | None = None
    try:
        for _ in range(80):
            try:
                if httpx.get(url, timeout=.2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(.1)
        else:
            pytest.fail("FastAPI workbench shell did not start")
        browser = _launch_isolated_chrome([
            *S022_CHROME_FLAGS,
            f"--remote-debugging-port={debug_port}",
            "--window-size=1440,900",
            f"--user-data-dir={tmp_path / 'resize'}",
            url,
        ])
        _prepare_s022_capture_environment(debug_port, url, 1440)
        assert _cdp(
            debug_port,
            """(async()=>{for(let i=0;i<120;i++){if(document.querySelector('[data-overview-state=populated]'))break;await new Promise(resolve=>setTimeout(resolve,25))}const current=document.querySelector('.sidebar .nav-link[aria-current=page]');current.focus();return {sidebar:getComputedStyle(document.querySelector('.sidebar')).display!=='none',menu:getComputedStyle(document.querySelector('.menu')).display==='none',focused:document.activeElement===current,inert:document.querySelector('#workbench-shell').hasAttribute('inert')}})()""",
            await_promise=True,
            target_url=url,
        ) == {"sidebar": True, "menu": True, "focused": True, "inert": False}

        device = S022_CAPTURE["device"]
        _cdp_command(
            debug_port,
            "Emulation.setDeviceMetricsOverride",
            {"width": 644, "height": 900, "deviceScaleFactor": device["deviceScaleFactor"], "mobile": device["mobile"]},
            target_url=url,
        )
        assert _cdp(debug_port, "(async()=>{for(let i=0;i<160;i++){if(innerWidth===644){window.dispatchEvent(new Event('resize'));return true}await new Promise(resolve=>setTimeout(resolve,25))}return false})()", await_promise=True, target_url=url) is True
        narrow = _cdp(
            debug_port,
            """(async()=>{for(let i=0;i<160;i++){const menu=document.querySelector('.menu');if(innerWidth===644&&getComputedStyle(menu).display!=='none'&&document.activeElement===menu)return {viewport:[innerWidth,innerHeight,devicePixelRatio],sidebar:getComputedStyle(document.querySelector('.sidebar')).display==='none',menu:true,close:!!document.querySelector('[aria-label="关闭导航"]'),drawerOpen:document.querySelector('#drawer').classList.contains('open'),inert:document.querySelector('#workbench-shell').hasAttribute('inert'),focus:'menu'};await new Promise(resolve=>setTimeout(resolve,25))}return null})()""",
            await_promise=True,
            target_url=url,
        )
        assert narrow == {"viewport": [644, 900, 1], "sidebar": True, "menu": True, "close": True, "drawerOpen": False, "inert": False, "focus": "menu"}

        opened = _cdp(
            debug_port,
            """(()=>{document.querySelector('.menu').click();const drawer=document.querySelector('#drawer'),close=document.querySelector('[aria-label="关闭导航"]');return {open:drawer.classList.contains('open'),ariaHidden:drawer.getAttribute('aria-hidden'),inert:document.querySelector('#workbench-shell').hasAttribute('inert'),focus:document.activeElement===close}})()""",
            target_url=url,
        )
        assert opened == {"open": True, "ariaHidden": None, "inert": True, "focus": True}

        _cdp_command(
            debug_port,
            "Emulation.setDeviceMetricsOverride",
            {"width": 1440, "height": 900, "deviceScaleFactor": device["deviceScaleFactor"], "mobile": device["mobile"]},
            target_url=url,
        )
        assert _cdp(debug_port, "(async()=>{for(let i=0;i<160;i++){if(innerWidth===1440){window.dispatchEvent(new Event('resize'));return true}await new Promise(resolve=>setTimeout(resolve,25))}return false})()", await_promise=True, target_url=url) is True
        desktop = _cdp(
            debug_port,
            """(async()=>{for(let i=0;i<160;i++){const drawer=document.querySelector('#drawer'),current=document.querySelector('.sidebar .nav-link[aria-current=page]');if(innerWidth===1440&&!drawer.classList.contains('open')&&!document.querySelector('#workbench-shell').hasAttribute('inert')&&document.activeElement===current)return {viewport:[innerWidth,innerHeight,devicePixelRatio],sidebar:getComputedStyle(document.querySelector('.sidebar')).display!=='none',menu:getComputedStyle(document.querySelector('.menu')).display==='none',closed:drawer.getAttribute('aria-hidden')==='true',inert:false,focus:'current-desktop-route'};await new Promise(resolve=>setTimeout(resolve,25))}return null})()""",
            await_promise=True,
            target_url=url,
        )
        assert desktop == {"viewport": [1440, 900, 1], "sidebar": True, "menu": True, "closed": True, "inert": False, "focus": "current-desktop-route"}

        assert _cdp(
            debug_port,
            "(()=>{const command=document.querySelector('.command-link');command.focus();return document.activeElement===command})()",
            target_url=url,
        ) is True
        _cdp_command(
            debug_port,
            "Emulation.setDeviceMetricsOverride",
            {"width": 644, "height": 900, "deviceScaleFactor": device["deviceScaleFactor"], "mobile": device["mobile"]},
            target_url=url,
        )
        content_focus = _cdp(
            debug_port,
            """(async()=>{for(let i=0;i<160;i++){if(innerWidth===644){window.dispatchEvent(new Event('resize'));const command=document.querySelector('.command-link'),menu=document.querySelector('.menu');if(getComputedStyle(menu).display!=='none')return {focused:document.activeElement===command,menu:true}}await new Promise(resolve=>setTimeout(resolve,25))}return null})()""",
            await_promise=True,
            target_url=url,
        )
        assert content_focus == {"focused": True, "menu": True}
    finally:
        if browser is not None:
            _close_isolated_chrome(debug_port, browser)
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
        [sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)],
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
        [sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)],
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
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for real Registry evidence",
)
@pytest.mark.parametrize("width", (1440, 644))
def test_real_app_registry_remains_populated_without_database_run_history(tmp_path: Path, width: int) -> None:
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {
        **os.environ,
        "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}",
        "KB2_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
        "KB2_DATABASE_PASSWORD_FILE": str(tmp_path / "missing-database-password"),
        "KB2_PROBE_TIMEOUT_SECONDS": "0.1",
    }
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "kb2_runtime.api:app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment,
    )
    browser = subprocess.Popen(
        [str(CHROME), "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--remote-allow-origins=*", f"--remote-debugging-port={debug_port}", f"--window-size={width},900", f"--user-data-dir={tmp_path / f'real-registry-{width}'}", f"http://127.0.0.1:{port}/workbench/plugins"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        expression = """(async () => { const wait = async predicate => { for (let i = 0; i < 120; i++) { const value = predicate(); if (value) return value; await new Promise(r => setTimeout(r, 50)); } throw new Error('Real Registry did not become ready'); }; const rows = await wait(() => { const values = [...document.querySelectorAll('.registry-select')]; return values.length > 1 ? values : null; }); rows.find(x => x.textContent === 'retriever.keyword@1').click(); const detail = await wait(() => { const value = document.querySelector('.registry-detail'); return value?.innerText.includes('输出端口') ? value : null; }); return {rows: rows.length, actualDescriptor: rows.some(x => x.textContent === 'retriever.keyword@1'), detail: detail.innerText.includes('配置 Schema') && detail.innerText.includes('安全示例'), failureAbsent: !document.body.innerText.includes('PLUGIN_REGISTRY_UNAVAILABLE'), overflow: document.documentElement.scrollWidth <= innerWidth, modal: innerWidth >= 900 || detail.getAttribute('role') === 'dialog'}; })()"""
        result = _cdp(int(debug_port), expression, await_promise=True)
        assert result["rows"] > 1
        assert result == {"rows": result["rows"], "actualDescriptor": True, "detail": True, "failureAbsent": True, "overflow": True, "modal": True}
        _capture_cdp(int(debug_port), tmp_path / f"real-registry-populated-{width}.png")
    finally:
        browser.terminate()
        browser.wait(timeout=10)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for document preflight state evidence",
)
def test_fixture_backed_document_preflight_loading_error_retry_and_modal_keyboard(tmp_path: Path) -> None:
    """Keep a selected upload recoverable while exposing deterministic request state."""
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment,
    )
    url = f"http://127.0.0.1:{port}/workbench/documents"
    _wait_for_fixture(url)
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", "--window-size=1440,900", f"--user-data-dir={tmp_path / 'preflight-states'}", url])
    try:
        _prepare_s022_capture_environment(debug_port, url, 1440)
        modal = """(async()=>{const wait=async p=>{for(let i=0;i<100;i++){const value=p();if(value)return value;await new Promise(r=>setTimeout(r,25))}throw new Error('Documents modal did not render')};const opener=await wait(()=>[...document.querySelectorAll('button')].find(x=>x.textContent.includes('上传并预检')));opener.click();const dialog=await wait(()=>document.querySelector('.upload-dialog'));const enabled=[...dialog.querySelectorAll('button,input')].filter(x=>!x.disabled);enabled.at(-1).focus();document.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',bubbles:true}));const trapped=document.activeElement===enabled[0];document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await new Promise(r=>setTimeout(r,20));const escaped=!document.querySelector('.upload-dialog')&&document.activeElement===opener,rootUnlocked=!document.documentElement.classList.contains('modal-open')&&!document.body.classList.contains('modal-open');opener.click();await wait(()=>document.querySelector('.upload-dialog'));const profile=document.querySelector('input[aria-label="Ingestion Profile Set ID"]'),file=document.querySelector('input[type=file]'),transfer=new DataTransfer();profile.value='fixture-ingestion';transfer.items.add(new File(['%PDF-fixture'],'fixture.pdf',{type:'application/pdf'}));Object.defineProperty(file,'files',{value:transfer.files,configurable:true});const action=[...document.querySelectorAll('button')].find(x=>x.textContent==='预检');action.click();await wait(()=>[...document.querySelectorAll('button')].find(x=>x.textContent==='创建新 Run'));const old=(await (await fetch('/api/fixture/document-preflights')).json()).tokens.at(-1),changed=new DataTransfer();changed.items.add(new File(['%PDF-fixture'],'fixture.pdf',{type:'application/pdf'}));Object.defineProperty(file,'files',{value:changed.files,configurable:true});file.dispatchEvent(new Event('change',{bubbles:true}));const fileChanged=file.files===changed.files;profile.value='retry-ingestion';profile.dispatchEvent(new Event('input',{bubbles:true}));const invalidated=![...document.querySelectorAll('button')].some(x=>x.textContent==='创建新 Run')&&!document.body.innerText.includes('Profile 解析依据');action.click();const status=document.querySelector('[role=status]');return {trapped,escaped,rootUnlocked,fileChanged,invalidated,loading:status?.textContent.includes('正在预检'),live:status?.getAttribute('aria-live')==='polite',disabled:action.disabled,old};})()"""
        state = _cdp(debug_port, modal, await_promise=True, target_url=url)
        old_token = state.pop("old")
        assert state == {"trapped": True, "escaped": True, "rootUnlocked": True, "fileChanged": True, "invalidated": True, "loading": True, "live": True, "disabled": True}
        _assert_root_scroll_locked(debug_port, target_url=url)
        failure = """(async()=>{for(let i=0;i<100;i++){const action=[...document.querySelectorAll('button')].find(x=>x.textContent==='预检'),profile=document.querySelector('input[aria-label="Ingestion Profile Set ID"]'),file=document.querySelector('input[type=file]'),status=document.querySelector('[role=status]');if(document.body.innerText.includes('请检查 Profile Set 和文档后重试。'))return {error:status?.textContent==='预检失败，可重试',enabled:!action.disabled,profile:profile.value,file:file.files?.[0]?.name,noSubmit:![...document.querySelectorAll('button')].some(x=>x.textContent==='创建新 Run'),previewGone:!document.body.innerText.includes('Profile 解析依据')};await new Promise(r=>setTimeout(r,25))}throw new Error('Preflight failure did not render')})()"""
        assert _cdp(debug_port, failure, await_promise=True, target_url=url) == {"error": True, "enabled": True, "profile": "retry-ingestion", "file": "fixture.pdf", "noSubmit": True, "previewGone": True}
        assert old_token not in httpx.get(f"http://127.0.0.1:{port}/api/fixture/document-preflights").json()["tokens"]
        assert _cdp(debug_port, "(()=>{const action=[...document.querySelectorAll('button')].find(x=>x.textContent==='预检');action.click();return {loading:document.querySelector('[role=status]').textContent.includes('正在预检'),disabled:action.disabled}})()", target_url=url) == {"loading": True, "disabled": True}
        success = """(async()=>{for(let i=0;i<100;i++){const action=[...document.querySelectorAll('button')].find(x=>x.textContent==='预检'),status=document.querySelector('[role=status]');if(document.body.innerText.includes('Profile 解析依据'))return {complete:status?.textContent==='预检完成',enabled:!action.disabled,profile:document.querySelector('input[aria-label="Ingestion Profile Set ID"]').value,file:document.querySelector('input[type=file]').files?.[0]?.name};await new Promise(r=>setTimeout(r,25))}throw new Error('Preflight retry did not complete')})()"""
        assert _cdp(debug_port, success, await_promise=True, target_url=url) == {"complete": True, "enabled": True, "profile": "retry-ingestion", "file": "fixture.pdf"}
        delayed_guard = """(async()=>{const profile=document.querySelector('input[aria-label="Ingestion Profile Set ID"]'),file=document.querySelector('input[type=file]'),action=[...document.querySelectorAll('button')].find(x=>x.textContent==='预检');profile.value='delayed-ingestion';profile.dispatchEvent(new Event('input',{bubbles:true}));action.click();const pending=action.disabled&&document.querySelector('[role=status]')?.textContent.includes('正在预检')&&![...document.querySelectorAll('button')].some(x=>x.textContent==='创建新 Run'),changed=new DataTransfer();changed.items.add(new File(['%PDF-fixture'],'fixture.pdf',{type:'application/pdf'}));Object.defineProperty(file,'files',{value:changed.files,configurable:true});file.dispatchEvent(new Event('change',{bubbles:true}));await new Promise(r=>setTimeout(r,350));return {pending,fileChanged:file.files===changed.files,previewGone:!document.body.innerText.includes('Profile 解析依据'),noSubmit:![...document.querySelectorAll('button')].some(x=>x.textContent==='创建新 Run'),notCompleted:document.querySelector('[role=status]')?.textContent!=='预检完成'};})()"""
        assert _cdp(debug_port, delayed_guard, await_promise=True, target_url=url) == {"pending": True, "fileChanged": True, "previewGone": True, "noSubmit": True, "notCompleted": True}
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for candidate selection evidence",
)
def test_fixture_backed_document_candidate_selection_rotates_preview_and_submit_binding(tmp_path: Path) -> None:
    """Bind every displayed plan and disclosure to the server-selected candidate."""
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment,
    )
    url = f"http://127.0.0.1:{port}/workbench/documents"
    _wait_for_fixture(url)
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", "--window-size=1440,900", f"--user-data-dir={tmp_path / 'candidate-selection'}", url])
    try:
        _prepare_s022_capture_environment(debug_port, url, 1440)
        local_to_external = """(async()=>{const wait=async p=>{for(let i=0;i<120;i++){const value=p();if(value)return value;await new Promise(r=>setTimeout(r,25))}throw new Error('candidate preview timeout')};(await wait(()=>[...document.querySelectorAll('button')].find(x=>x.textContent.includes('上传并预检')))).click();const profile=await wait(()=>document.querySelector('input[aria-label="Ingestion Profile Set ID"]')),file=document.querySelector('input[type=file]'),transfer=new DataTransfer();profile.value='switch-local';transfer.items.add(new File(['%PDF-fixture'],'fixture.pdf',{type:'application/pdf'}));Object.defineProperty(file,'files',{value:transfer.files,configurable:true});[...document.querySelectorAll('button')].find(x=>x.textContent==='预检').click();await wait(()=>document.querySelector('input[value="switch-external-profile"]'));const before=await (await fetch('/api/fixture/document-preflights')).json(),old=before.tokens.at(-1),choice=document.querySelector('input[value="switch-external-profile"]');choice.click();const pending=![...document.querySelectorAll('button')].some(x=>x.textContent==='创建新 Run')&&!document.body.innerText.includes('parser.fixture@1');await wait(()=>document.body.innerText.includes('parser.external@1')&&document.querySelector('input[aria-label="确认外部阶段披露"]'));const after=await (await fetch('/api/fixture/document-preflights')).json(),submit=[...document.querySelectorAll('button')].find(x=>x.textContent==='创建新 Run'),ack=document.querySelector('input[aria-label="确认外部阶段披露"]'),blocked=submit.disabled;ack.click();const enabled=!submit.disabled,rotated=after.tokens.at(-1);submit.click();return {pending,blocked,enabled,checked:choice.checked,oldInvalid:!after.tokens.includes(old),rotated:rotated!==old,disclosed:document.body.innerText.includes('外部阶段披露')};})()"""
        assert _cdp(debug_port, local_to_external, await_promise=True, target_url=url) == {"pending": True, "blocked": True, "enabled": True, "checked": True, "oldInvalid": True, "rotated": True, "disclosed": True}
        for _ in range(100):
            receipts = httpx.get(f"http://127.0.0.1:{port}/api/fixture/document-preflights").json()["receipts"]
            if receipts:
                break
            time.sleep(.025)
        assert receipts[-1]["profileId"] == "switch-external-profile"
        assert receipts[-1]["acknowledgeExternal"] is True

        assert _cdp(debug_port, "location.href='/workbench/documents'; true", target_url=f"http://127.0.0.1:{port}/workbench/runs?run={_VISUAL_RUN}&legacy=ingestion") is True
        external_to_local = """(async()=>{const wait=async p=>{for(let i=0;i<120;i++){const value=p();if(value)return value;await new Promise(r=>setTimeout(r,25))}throw new Error('reverse candidate preview timeout')};(await wait(()=>[...document.querySelectorAll('button')].find(x=>x.textContent.includes('上传并预检')))).click();const profile=await wait(()=>document.querySelector('input[aria-label="Ingestion Profile Set ID"]')),file=document.querySelector('input[type=file]'),transfer=new DataTransfer();profile.value='switch-external';transfer.items.add(new File(['%PDF-fixture'],'fixture.pdf',{type:'application/pdf'}));Object.defineProperty(file,'files',{value:transfer.files,configurable:true});[...document.querySelectorAll('button')].find(x=>x.textContent==='预检').click();await wait(()=>document.querySelector('input[value="switch-local-profile"]'));const initiallyExternal=document.body.innerText.includes('parser.external@1')&&!!document.querySelector('input[aria-label="确认外部阶段披露"]'),choice=document.querySelector('input[value="switch-local-profile"]');choice.click();const pending=![...document.querySelectorAll('button')].some(x=>x.textContent==='创建新 Run');await wait(()=>document.body.innerText.includes('parser.fixture@1')&&[...document.querySelectorAll('button')].some(x=>x.textContent==='创建新 Run'));const automaticLabel=document.querySelector('input[value="switch-external-profile"]')?.closest('label')?.innerText.includes('自动选中');return {initiallyExternal,pending,checked:document.querySelector('input[value="switch-local-profile"]')?.checked,local:!document.querySelector('input[aria-label="确认外部阶段披露"]'),enabled:![...document.querySelectorAll('button')].find(x=>x.textContent==='创建新 Run').disabled,automaticLabel};})()"""
        assert _cdp(debug_port, external_to_local, await_promise=True, target_url=url) == {"initiallyExternal": True, "pending": True, "checked": True, "local": True, "enabled": True, "automaticLabel": True}

        delayed_selection_guard = """(async()=>{const wait=async p=>{for(let i=0;i<120;i++){const value=p();if(value)return value;await new Promise(r=>setTimeout(r,25))}throw new Error('delayed selection timeout')};const profile=document.querySelector('input[aria-label="Ingestion Profile Set ID"]'),file=document.querySelector('input[type=file]');profile.value='switch-local';profile.dispatchEvent(new Event('input',{bubbles:true}));[...document.querySelectorAll('button')].find(x=>x.textContent==='预检').click();await wait(()=>document.querySelector('input[value="switch-delayed"]'));document.querySelector('input[value="switch-delayed"]').click();const pending=document.querySelector('[role=status]')?.textContent.includes('正在切换 Profile 预览')&&![...document.querySelectorAll('button')].some(x=>x.textContent==='创建新 Run'),changed=new DataTransfer();changed.items.add(new File(['%PDF-fixture'],'fixture.pdf',{type:'application/pdf'}));Object.defineProperty(file,'files',{value:changed.files,configurable:true});file.dispatchEvent(new Event('change',{bubbles:true}));await new Promise(r=>setTimeout(r,350));return {pending,fileChanged:file.files===changed.files,previewGone:!document.body.innerText.includes('Profile 解析依据'),noSubmit:![...document.querySelectorAll('button')].some(x=>x.textContent==='创建新 Run'),notUpdated:document.querySelector('[role=status]')?.textContent!=='Profile 预览已更新'};})()"""
        assert _cdp(debug_port, delayed_selection_guard, await_promise=True, target_url=url) == {"pending": True, "fileChanged": True, "previewGone": True, "noSubmit": True, "notUpdated": True}

        selection_failure = """(async()=>{const wait=async p=>{for(let i=0;i<120;i++){const value=p();if(value)return value;await new Promise(r=>setTimeout(r,25))}throw new Error('selection failure timeout')};const profile=document.querySelector('input[aria-label="Ingestion Profile Set ID"]');profile.value='switch-local';profile.dispatchEvent(new Event('input',{bubbles:true}));[...document.querySelectorAll('button')].find(x=>x.textContent==='预检').click();await wait(()=>document.querySelector('input[value="switch-error"]'));document.querySelector('input[value="switch-error"]').click();const pending=![...document.querySelectorAll('button')].some(x=>x.textContent==='创建新 Run');await wait(()=>document.body.innerText.includes('旧预检已失效'));return {pending,failed:document.querySelector('[role=status]')?.textContent.includes('切换失败'),noSubmit:![...document.querySelectorAll('button')].some(x=>x.textContent==='创建新 Run'),selectionGone:!document.body.innerText.includes('Profile 解析依据')};})()"""
        assert _cdp(debug_port, selection_failure, await_promise=True, target_url=url) == {"pending": True, "failed": True, "noSubmit": True, "selectionGone": True}
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for browser shell evidence",
)
@pytest.mark.parametrize("width", (1440, 644))
def test_fixture_backed_ingestion_artifact_inspector_sync_and_escape(tmp_path: Path, width: int) -> None:
    """Validate S-024 stable object/source selection and narrow drawer closure."""
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment,
    )
    url = f"http://127.0.0.1:{port}/workbench/runs?run={_INGESTION_RUN}&legacy=ingestion"
    _wait_for_fixture(f"http://127.0.0.1:{port}/workbench/runs")
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", f"--window-size={width},900", f"--user-data-dir={tmp_path / 'artifact'}", url])
    try:
        _prepare_s022_capture_environment(debug_port, url, width)
        expression = """(async () => { const wait = async predicate => { for (let i = 0; i < 100; i++) { const value = predicate(); if (value) return value; await new Promise(r => setTimeout(r, 25)); } throw new Error('Artifact fixture did not become ready'); }; await wait(()=>document.querySelector('.run-tabs'));const runTabs=[...document.querySelectorAll('.run-tabs button')];runTabs.find(x=>x.textContent==='Run 指标').click();const emptyRunSignals=[...document.querySelectorAll('.run-tab-panel dd')].map(x=>x.textContent);runTabs.find(x=>x.textContent==='Profile 解析').click();const action = [...document.querySelectorAll('button')].find(x => x.textContent.includes('Artifact canonical.document')); action.click(); const sourcePane = await wait(() => document.querySelector('.artifact-inspector .source-view')); const drawer = sourcePane.closest('.artifact-inspector'); const source = sourcePane.querySelector('button'); const object = drawer.querySelector('.inspector-list button'); source.click(); const sourceSync = drawer.querySelectorAll('[data-stable-id].source-selected').length === 2; object.click(); const objectSync = drawer.querySelectorAll('[data-stable-id].source-selected').length === 2; [...drawer.querySelectorAll('[role=tab]')].find(x=>x.textContent==='表格').click();const tableSource=drawer.querySelector('.source-view button'),tableObject=drawer.querySelector('.artifact-table > button');tableSource.click();const tableSourceSync=drawer.querySelectorAll('[data-stable-id].source-selected').length===2;tableObject.click();const tableObjectSync=drawer.querySelectorAll('[data-stable-id].source-selected').length===2,summary=drawer.querySelector('.locator-summary'),tableSummary=summary?.textContent.includes('tbl_fixture / pdf / 第 1 页'),tableSummaryLive=summary?.getAttribute('aria-live')==='polite';[...drawer.querySelectorAll('[role=tab]')].find(x=>x.textContent==='Lineage').click();const lineage=drawer.innerText.includes('生产者 Run ID：12345678-1234-5678-1234-567812345680')&&drawer.innerText.includes('生产者 Plugin ID：parser.fixture@1')&&!drawer.innerText.includes('[object Object]');[...drawer.querySelectorAll('[role=tab]')].find(x=>x.textContent==='Canonical').click();drawer.querySelector('.source-view button').click(); return {sourceSync, objectSync, tableSourceSync, tableObjectSync, tableSummary, tableSummaryLive, lineage, emptyRunSignals:emptyRunSignals.length===2&&emptyRunSignals.every(x=>x==='不可用'), rawArrayAbsent:!document.body.innerText.includes('[]'), panes: !!drawer.querySelector('.inspector-list') && !!drawer.querySelector('.source-view'), overflow: document.documentElement.scrollWidth <= innerWidth, modal: innerWidth >= 900 || document.querySelector('.artifact-inspector').getAttribute('role') === 'dialog'}; })()"""
        result = _cdp(int(debug_port), expression, await_promise=True)
        assert result == {"sourceSync": True, "objectSync": True, "tableSourceSync": True, "tableObjectSync": True, "tableSummary": True, "tableSummaryLive": True, "lineage": True, "emptyRunSignals": True, "rawArrayAbsent": True, "panes": True, "overflow": True, "modal": True}
        geometry = _cdp(debug_port, f"(()=>{{const drawer=document.querySelector('.artifact-inspector'),first=drawer.querySelector('[role=tab]');first.focus();first.dispatchEvent(new KeyboardEvent('keydown',{{key:'ArrowRight',bubbles:true}}));const selected=drawer.querySelector('[role=tab][aria-selected=true]');drawer.querySelector('[role=tablist]').dispatchEvent(new KeyboardEvent('keydown',{{key:'Home',bubbles:true}}));drawer.querySelector('.source-view button').click();drawer.focus();return {{width:Math.round(drawer.getBoundingClientRect().width),inert:document.querySelector('#workbench-shell').hasAttribute('inert'),tabs:drawer.querySelectorAll('[role=tab]').length,keyboard:selected?.textContent==='结构树',rawAbsent:![...drawer.querySelectorAll('[role=tab]')].some(x=>x.textContent==='原始文本'),url:location.pathname+location.search}}}})()", target_url=url)
        assert geometry == {"width": 1080 if width >= 900 else 644, "inert": True, "tabs": 5, "keyboard": True, "rawAbsent": True, "url": f"/workbench/runs?run={_INGESTION_RUN}&legacy=ingestion"}
        _assert_root_scroll_locked(debug_port, target_url=url)
        _capture_cdp(debug_port, tmp_path / f"artifact-canonical-source-{width}.png", target_url=url)
        _assert_manifest_visual(debug_port, tmp_path / f"artifact-canonical-source-{width}.png", f"artifact-canonical-source-{width}.png", target_url=url, baseline_root=S024_BASELINE_ROOT, story="S-024")
        assert _cdp(int(debug_port), "(async () => { document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true})); await new Promise(r => setTimeout(r, 30)); return {closed: !document.querySelector('.artifact-inspector'), focusReturned: document.activeElement.textContent.includes('Artifact canonical.document'),rootUnlocked:!document.documentElement.classList.contains('modal-open')&&!document.body.classList.contains('modal-open')}; })()", await_promise=True) == {"closed": True, "focusReturned": True, "rootUnlocked": True}
        chunks = """(async()=>{const wait=async p=>{for(let i=0;i<100;i++){const value=p();if(value)return value;await new Promise(r=>setTimeout(r,25))}throw new Error('Chunk inspector did not render')};const action=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('Artifact chunk.set'));action.click();const drawer=await wait(()=>document.querySelector('.artifact-inspector .source-view')?.closest('.artifact-inspector'));const citations=drawer.querySelectorAll('.inspector-list button').length===2&&drawer.querySelectorAll('.source-view button').length===2,source=drawer.querySelector('.source-view button'),object=drawer.querySelector('.inspector-list button');source.click();const sourceSync=drawer.querySelectorAll('[data-stable-id].source-selected').length===2;object.click();const objectSync=drawer.querySelectorAll('[data-stable-id].source-selected').length===2;[...drawer.querySelectorAll('[role=tab]')].find(x=>x.textContent==='元数据').click();const metadata=[...drawer.querySelectorAll('.metadata-grid dd')].map(x=>x.textContent);document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await new Promise(r=>setTimeout(r,20));return {sourceSync,objectSync,citations,metadataUnavailable:metadata.slice(-2).every(x=>x==='不可用'),closed:!document.querySelector('.artifact-inspector'),focusReturned:document.activeElement===action}})()"""
        assert _cdp(debug_port, chunks, await_promise=True, target_url=url) == {"sourceSync": True, "objectSync": True, "citations": True, "metadataUnavailable": True, "closed": True, "focusReturned": True}
        assert _cdp(int(debug_port), "(()=>{[...document.querySelectorAll('button')].find(x=>x.textContent==='重新运行').click();const profile=document.querySelector('input[aria-label=\"重新运行 Profile Set ID\"]');profile.value='fixture-ingestion';[...document.querySelectorAll('button')].find(x=>x.textContent==='确认重新运行').click();return true})()") is True
        for _ in range(100):
            pages = httpx.get(f"http://127.0.0.1:{debug_port}/json", timeout=1).json()
            if any(page.get("url", "").endswith("/workbench/documents") for page in pages):
                break
            time.sleep(.025)
        else:
            pytest.fail("Rerun handoff did not navigate to Documents")
        assert _cdp(int(debug_port), "({dialog:document.querySelector('.upload-dialog')?.getAttribute('aria-modal')==='true',source:document.body.innerText.includes('12345678-1234-5678-1234-567812345681'),profile:document.querySelector('input[aria-label=\"Ingestion Profile Set ID\"]')?.value === 'fixture-ingestion',confirmable:[...document.querySelectorAll('button')].some(x => x.textContent === '创建新 Run'),overflow:document.documentElement.scrollWidth <= innerWidth})") == {"dialog": True, "source": True, "profile": True, "confirmable": True, "overflow": True}
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for S-024 visual evidence",
)
@pytest.mark.parametrize("width", (1440, 644))
def test_fixture_backed_document_preflight_and_ingestion_state_matrix(tmp_path: Path, width: int) -> None:
    """Capture the shipped Documents and Runs workflows against API projections."""
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment,
    )
    url = f"http://127.0.0.1:{port}/workbench/documents"
    _wait_for_fixture(url)
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", f"--window-size={width},900", f"--user-data-dir={tmp_path / 'documents'}", url])
    try:
        _prepare_s022_capture_environment(debug_port, url, width)
        preflight = """(async () => { const wait = async predicate => { for (let i = 0; i < 100; i++) { const value = predicate(); if (value) return value; await new Promise(r => setTimeout(r, 25)); } throw new Error('Documents fixture did not become ready'); }; const opener=await wait(() => [...document.querySelectorAll('button')].find(x => x.textContent.includes('上传并预检'))); opener.click(); await wait(() => document.querySelector('input[aria-label="Ingestion Profile Set ID"]') && document.querySelector('input[type=file]')); const profile = document.querySelector('input[aria-label="Ingestion Profile Set ID"]'); profile.value = 'fixture-ingestion'; const file = document.querySelector('input[type=file]'); const transfer = new DataTransfer(); transfer.items.add(new File(['%PDF-fixture'], 'fixture.pdf', {type:'application/pdf'})); Object.defineProperty(file, 'files', {value: transfer.files, configurable: true}); [...document.querySelectorAll('button')].find(x => x.textContent === '预检').click(); await wait(() => document.body.innerText.includes('Profile 解析依据')); const choices=[...document.querySelectorAll('input[name="ingestion-profile"]')]; return {automatic:choices.find(x=>x.value==='fixture-ingestion')?.checked && choices.some(x=>x.value==='fixture-default'), preserved:profile.value==='fixture-ingestion' && document.body.innerText.includes('fixture-ingestion'), matched:document.body.innerText.includes('pdf：匹配'), submit: !![...document.querySelectorAll('button')].find(x => x.textContent === '创建新 Run'), modal:document.querySelector('.upload-dialog')?.getAttribute('aria-modal')==='true', overflow: document.documentElement.scrollWidth <= innerWidth}; })()"""
        assert _cdp(debug_port, preflight, await_promise=True, target_url=url) == {"automatic": True, "preserved": True, "matched": True, "submit": True, "modal": True, "overflow": True}
        assert _cdp(debug_port, "(()=>{const dialog=document.querySelector('.upload-dialog'),body=dialog.querySelector('.upload-dialog-body');return {inert:document.querySelector('#workbench-shell').hasAttribute('inert'),fit:dialog.getBoundingClientRect().height<=innerHeight-16,focus:dialog.contains(document.activeElement),bodyOverflow:['auto','scroll'].includes(getComputedStyle(body).overflowY)}})()", target_url=url) == {"inert": True, "fit": True, "focus": True, "bodyOverflow": True}
        _assert_root_scroll_locked(debug_port, target_url=url)
        _capture_cdp(debug_port, tmp_path / f"documents-preflight-automatic-{width}.png", target_url=url)
        _assert_manifest_visual(debug_port, tmp_path / f"documents-preflight-automatic-{width}.png", f"documents-preflight-automatic-{width}.png", target_url=url, baseline_root=S024_BASELINE_ROOT, story="S-024")
        explicit = """(async()=>{const old=(await (await fetch('/api/fixture/document-preflights')).json()).tokens.at(-1),choice=[...document.querySelectorAll('input[name="ingestion-profile"]')].find(x=>x.value==='fixture-default');choice.click();const pending=![...document.querySelectorAll('button')].some(x=>x.textContent==='创建新 Run')&&!document.body.innerText.includes('解析后的阶段');for(let i=0;i<100;i++){const submit=[...document.querySelectorAll('button')].find(x=>x.textContent==='创建新 Run');if(submit){const state=await (await fetch('/api/fixture/document-preflights')).json();return {pending,checked:document.querySelector('input[value="fixture-default"]')?.checked,plugin:document.body.innerText.includes('parser.default@1'),oldInvalid:!state.tokens.includes(old),submit:!!submit}}await new Promise(r=>setTimeout(r,25))}throw new Error('Explicit candidate preview did not render')})()"""
        assert _cdp(debug_port, explicit, await_promise=True, target_url=url) == {"pending": True, "checked": True, "plugin": True, "oldInvalid": True, "submit": True}
        assert _cdp(int(debug_port), "[...document.querySelectorAll('button')].find(x => x.textContent === '创建新 Run').click(); true") is True
        for _ in range(100):
            pages = httpx.get(f"http://127.0.0.1:{debug_port}/json", timeout=1).json()
            if any(page.get("url", "").endswith(f"/workbench/runs?run={_VISUAL_RUN}&legacy=ingestion") for page in pages):
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

        external = """(async () => { [...document.querySelectorAll('button')].find(x => x.textContent.includes('上传并预检')).click(); const profile = document.querySelector('input[aria-label="Ingestion Profile Set ID"]'), file=document.querySelector('input[type=file]'), transfer=new DataTransfer(); transfer.items.add(new File(['%PDF-fixture'], 'fixture.pdf', {type:'application/pdf'})); Object.defineProperty(file, 'files', {value: transfer.files, configurable: true}); profile.value = 'external-ingestion'; [...document.querySelectorAll('button')].find(x => x.textContent === '预检').click(); for (let i = 0; i < 100; i++) { const checkbox = document.querySelector('input[aria-label="确认外部阶段披露"]'); const submit = [...document.querySelectorAll('button')].find(x => x.textContent === '创建新 Run'); if (checkbox && submit) { const blocked = submit.disabled; checkbox.click(); return {external: document.body.innerText.includes('parser.external@1'), blocked, enabled: !submit.disabled}; } await new Promise(r => setTimeout(r, 25)); } throw new Error('External disclosure did not render'); })()"""
        assert _cdp(int(debug_port), external, await_promise=True) == {"external": True, "blocked": True, "enabled": True}

        assert _cdp(int(debug_port), "[...document.querySelectorAll('button')].find(x => x.textContent === '创建新 Run').click(); true") is True
        for _ in range(100):
            pages = httpx.get(f"http://127.0.0.1:{debug_port}/json", timeout=1).json()
            if any(page.get("url", "").endswith(f"/workbench/runs?run={_VISUAL_RUN}&legacy=ingestion") for page in pages):
                break
            time.sleep(.025)
        else:
            pytest.fail("Run receipt navigation did not occur")
        states = """(async () => { for (let i = 0; i < 100; i++) { const text = document.body.innerText, buttons = [...document.querySelectorAll('button')].map(x => x.textContent); if (text.includes('Ingestion Run') && text.includes('失败') && text.includes('已跳过') && text.includes('accepted') && text.includes('rejected') && text.includes('parser.primary@1') && text.includes('PLUGIN_TIMEOUT')) {const cards=[...document.querySelectorAll('.stage-card')],emptySignals=[...document.querySelectorAll('.stage-signal-grid dd')].map(x=>x.textContent);cards[1].click();const fallback=document.querySelector('.stage-inspector').innerText.includes('parser.fallback@1')&&document.querySelector('.stage-inspector').innerText.includes('accepted')&&document.querySelector('.stage-inspector').innerText.includes('latency_ms');cards[0].click();const root=document.documentElement;return {matrix:true, fallback, emptySignals:emptySignals.length===2&&emptySignals.every(x=>x==='不可用'), rawArrayAbsent:!document.querySelector('.stage-inspector').innerText.includes('[]'), actions:buttons.includes('停止') && buttons.includes('重新运行') && !buttons.includes('重试'), rail:cards.length===4, selected:document.querySelector('.stage-card[aria-pressed="true"]')?.innerText.includes('失败'), overflow:root.scrollWidth <= innerWidth,rootClass:root.classList.contains('modal-open'),bodyClass:document.body.classList.contains('modal-open'),rootOverflow:getComputedStyle(root).overflowY,bodyOverflow:getComputedStyle(document.body).overflowY,rootScrollbarWidth:innerWidth-root.clientWidth}; } await new Promise(r => setTimeout(r, 25)); } throw new Error('Run-state matrix did not render'); })()"""
        assert _cdp(int(debug_port), states, await_promise=True) == {"matrix": True, "fallback": True, "emptySignals": True, "rawArrayAbsent": True, "actions": True, "rail": True, "selected": True, "overflow": True, "rootClass": False, "bodyClass": False, "rootOverflow": "auto", "bodyOverflow": "auto", "rootScrollbarWidth": 0}
        run_url = f"http://127.0.0.1:{port}/workbench/runs?run={_VISUAL_RUN}&legacy=ingestion"
        _assert_root_scroll_unlocked(debug_port, target_url=run_url)
        _capture_cdp(int(debug_port), tmp_path / f"ingestion-state-matrix-{width}.png", target_url=run_url)
        _assert_manifest_visual(debug_port, tmp_path / f"ingestion-state-matrix-{width}.png", f"ingestion-state-matrix-{width}.png", target_url=run_url, baseline_root=S024_BASELINE_ROOT, story="S-024")
        stop = """(async()=>{[...document.querySelectorAll('button')].find(x=>x.textContent==='停止').click();for(let i=0;i<100;i++){const requests=await fetch('/api/fixture/ingestion-stop-requests').then(r=>r.json());if(requests.length)return requests;await new Promise(r=>setTimeout(r,25))}return []})()"""
        assert _cdp(debug_port, stop, await_promise=True, target_url=run_url) == [_VISUAL_RUN]
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for S-028 visual evidence",
)
@pytest.mark.parametrize("width", (1440, 644))
@pytest.mark.parametrize("scenario", ("populated", "empty", "loading", "error"))
def test_s028_document_list_visual_matrix(tmp_path: Path, width: int, scenario: str) -> None:
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}", "KB2_DOCUMENT_FIXTURE_STATE": scenario}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
    url = f"http://127.0.0.1:{port}/workbench/documents"
    _wait_for_fixture(url)
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", f"--window-size={width},900", f"--user-data-dir={tmp_path / f's028-{scenario}-{width}'}", url])
    try:
        _prepare_s022_capture_environment(debug_port, url, width)
        selectors = {"populated": ".document-table", "empty": ".documents-surface .empty-state", "loading": ".document-list-loading", "error": ".documents-surface .notice-failure"}
        ready = f"(async()=>{{for(let i=0;i<120;i++){{if(document.querySelector('{selectors[scenario]}'))return true;await new Promise(r=>setTimeout(r,25))}}return false}})()"
        assert _cdp(debug_port, ready, await_promise=True, target_url=url) is True
        geometry = _cdp(debug_port, "(()=>{const wrap=document.querySelector('.document-table-wrap'),commands=[...document.querySelectorAll('.documents-commands button')];return {pageOverflow:document.documentElement.scrollWidth<=innerWidth,upload:commands.some(x=>x.textContent.includes('上传并预检')),refresh:commands.some(x=>x.getAttribute('aria-label')==='刷新文档列表'),scoped:wrap?wrap.scrollWidth>wrap.clientWidth:null,actions:[...document.querySelectorAll('.document-actions .icon-button')].every(x=>Math.round(x.getBoundingClientRect().width)>=30&&Math.round(x.getBoundingClientRect().height)>=30)}})()", target_url=url)
        assert geometry["pageOverflow"] and geometry["upload"] and geometry["refresh"] and geometry["actions"]
        if scenario == "populated":
            assert geometry["scoped"] is (width < 900)
            text_state = _cdp(debug_port, "document.body.innerText", target_url=url)
            assert "contract-framework-sample.pdf" in text_state and "不可用" in text_state
            assert "NOT_INGESTED" not in text_state and "删除" not in text_state
        image = tmp_path / f"documents-{scenario}-{width}.png"
        _capture_cdp(debug_port, image, target_url=url)
        _assert_manifest_visual(debug_port, image, image.name, target_url=url, baseline_root=S028_BASELINE_ROOT, story="S-028")
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for S-028 interactions",
)
def test_s028_document_list_paging_retry_and_actions(tmp_path: Path) -> None:
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}", "KB2_DOCUMENT_FIXTURE_STATE": "paging"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
    url = f"http://127.0.0.1:{port}/workbench/documents"
    _wait_for_fixture(url)
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", "--window-size=1440,900", f"--user-data-dir={tmp_path / 's028-actions'}", url])
    try:
        _prepare_s022_capture_environment(debug_port, url, 1440)
        result = _cdp(debug_port, """(async()=>{const wait=async p=>{for(let i=0;i<160;i++){const x=p();if(x)return x;await new Promise(r=>setTimeout(r,25))}throw new Error('document list timeout')};await wait(()=>document.querySelectorAll('.document-table tbody tr').length===2);const firstIds=[...document.querySelectorAll('.document-identity code')].map(x=>x.textContent);[...document.querySelectorAll('button')].find(x=>x.textContent==='加载更多').click();await wait(()=>document.body.innerText.includes('无法加载更多文档'));const retained=document.querySelectorAll('.document-table tbody tr').length===2;[...document.querySelectorAll('button')].find(x=>x.textContent==='重试').click();await wait(()=>document.querySelectorAll('.document-table tbody tr').length===4);const ids=[...document.querySelectorAll('.document-identity code')].map(x=>x.textContent),unique=new Set(ids).size===ids.length,run=document.querySelector('.document-run-link'),runUrl=new URL(run.href).pathname+new URL(run.href).search,source=document.querySelector('[aria-label="检查 Source Artifact"]');source.click();const drawer=await wait(()=>document.querySelector('.artifact-inspector'));const inspected=drawer.getAttribute('aria-label')==='Artifact 检查器';document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));const focusReturned=document.activeElement===source;document.querySelector('[aria-label="刷新文档列表"]').click();await wait(()=>document.querySelectorAll('.document-table tbody tr').length===2);return {firstIds,retained,count:ids.length,unique,runUrl,inspected,focusReturned,refreshed:document.querySelectorAll('.document-table tbody tr').length===2,upload:!![...document.querySelectorAll('button')].find(x=>x.textContent.includes('上传并预检'))}})()""", await_promise=True, target_url=url)
        assert result["retained"] and result["count"] == 4 and result["unique"] and result["inspected"] and result["focusReturned"] and result["refreshed"] and result["upload"]
        assert result["runUrl"] == f"/workbench/runs?run={_INGESTION_RUN}&legacy=ingestion"
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for S-028 stale response evidence",
)
def test_s028_document_list_suppresses_stale_refresh_and_restores_output_inspector_focus(tmp_path: Path) -> None:
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}", "KB2_DOCUMENT_FIXTURE_STATE": "stale"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
    url = f"http://127.0.0.1:{port}/workbench/documents"
    _wait_for_fixture(url)
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", "--window-size=1440,900", f"--user-data-dir={tmp_path / 's028-stale'}", url])
    try:
        _prepare_s022_capture_environment(debug_port, url, 1440)
        def wait_for_state(predicate) -> dict[str, object]:
            deadline = time.monotonic() + 4
            state: dict[str, object] = {}
            while time.monotonic() < deadline:
                state = httpx.get(f"http://127.0.0.1:{port}/api/fixture/document-list-state", timeout=1).json()
                if predicate(state):
                    return state
                time.sleep(.025)
            pytest.fail(f"Document list fixture did not reach the expected overlap state: {state}")

        initial_resources = _cdp(debug_port, "performance.getEntriesByType('resource').filter(x=>new URL(x.name).pathname==='/api/workbench/documents'&&x.responseEnd>0).length", target_url=url)
        assert httpx.post(f"http://127.0.0.1:{port}/api/fixture/document-list-arm", timeout=1).json() == {"armed": True}
        assert _cdp(debug_port, "(()=>{const x=document.querySelector('[aria-label=\"刷新文档列表\"]'),enabled=!x.disabled;x.click();return enabled})()", target_url=url) is True
        assert wait_for_state(lambda state: state == {"requests": 1, "completions": []})
        assert _cdp(debug_port, "(()=>{const x=document.querySelector('[aria-label=\"刷新文档列表\"]');return {disabled:x.disabled,connected:x.isConnected,dispatched:x.dispatchEvent(new MouseEvent('click',{bubbles:true}))}})()", target_url=url) == {"disabled": False, "connected": True, "dispatched": True}
        assert wait_for_state(lambda state: state["requests"] >= 2 and 2 in state["completions"] and 1 not in state["completions"])
        assert _cdp(debug_port, "(async()=>{for(let i=0;i<160;i++){if(document.body.innerText.includes('fresh-response.pdf'))return true;await new Promise(r=>setTimeout(r,25))}return false})()", await_promise=True, target_url=url) is True
        assert httpx.post(f"http://127.0.0.1:{port}/api/fixture/document-list-release", timeout=1).json() == {"released": True}
        assert wait_for_state(lambda state: 1 in state["completions"] and 2 in state["completions"])
        result = _cdp(debug_port, f"""(async()=>{{const wait=async p=>{{for(let i=0;i<160;i++){{const x=p();if(x)return x;await new Promise(r=>setTimeout(r,25))}}throw new Error('stale list timeout')}};await wait(()=>performance.getEntriesByType('resource').filter(x=>new URL(x.name).pathname==='/api/workbench/documents'&&x.responseEnd>0).length>={initial_resources + 2});await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));const staleSuppressed=!document.body.innerText.includes('stale-response.pdf')&&document.body.innerText.includes('fresh-response.pdf'),output=document.querySelector('[aria-label="检查最新输出 Artifact"]');output.click();const lineage=await wait(()=>[...document.querySelectorAll('.artifact-inspector [role=tab]')].find(x=>x.textContent==='Lineage')),drawer=lineage.closest('.artifact-inspector');lineage.click();const identity=drawer.innerText.includes('当前 Artifact：{_CHUNK_ARTIFACT}');document.dispatchEvent(new KeyboardEvent('keydown',{{key:'Escape',bubbles:true}}));return {{staleSuppressed,identity,closed:!document.querySelector('.artifact-inspector'),focusReturned:document.activeElement===output}}}})()""", await_promise=True, target_url=url)
        assert result == {"staleSuppressed": True, "identity": True, "closed": True, "focusReturned": True}
    finally:
        try:
            httpx.post(f"http://127.0.0.1:{port}/api/fixture/document-list-release", timeout=1)
        except httpx.HTTPError:
            pass
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for S-025 visual evidence",
)
@pytest.mark.parametrize("width", (1440, 644))
def test_fixture_backed_query_lab_evidence_locator_and_narrow_layout(tmp_path: Path, width: int) -> None:
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
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
        expression = """(async () => { const wait = async (label,p) => { for(let i=0;i<100;i++){const v=p();if(v)return v;await new Promise(r=>setTimeout(r,25));}throw new Error(`Query Lab fixture did not render: ${label}`); }; await wait('initial controls',()=>document.querySelector('textarea[aria-label="问题"]') && document.querySelector('select[aria-label="已索引 Artifact"] option')); const q=document.querySelector('textarea[aria-label="问题"]');q.value='answered';q.dispatchEvent(new Event('input',{bubbles:true})); [...document.querySelectorAll('button')].find(x=>x.textContent==='预检').click(); await wait('preflight',()=>document.body.innerText.includes('已解析计划')); const ack=document.querySelector('input[aria-label="确认外部阶段披露"]'),submit=[...document.querySelectorAll('button')].find(x=>x.textContent==='创建 Query Run'); const blocked=submit.disabled; ack.click(); submit.click(); const citation=await wait('run result',()=>[...document.querySelectorAll('button')].find(x=>x.textContent==='cit_fixture')); citation.click(); const drawer=await wait('source inspector',()=>document.querySelector('.artifact-inspector')); const selected=await wait('source locator selection',()=>drawer.querySelectorAll('.source-selected').length===2); return {blocked, answer:document.body.innerText.includes('Evidence-bound fixture answer'), candidates:document.body.innerText.includes('chk_fixture'), selected, overflow:document.documentElement.scrollWidth<=innerWidth}; })()"""
        expression = expression.replace("'chk_fixture'", json.dumps(_QUERY_CHUNK))
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
    _wait_for_fixture(dataset_url)
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", f"--window-size={width},900", f"--user-data-dir={tmp_path / 'evaluation'}", dataset_url])
    try:
        _prepare_s022_capture_environment(debug_port, dataset_url, width)
        dataset = """(async()=>{for(let i=0;i<200;i++){const editor=document.querySelector('.dataset-case-editor textarea[aria-label=\"问题\"]');if(editor){const text=document.body.innerText,selected=document.querySelector('.dataset-case-row[aria-pressed=true] strong')?.textContent;return {generated:selected==='qcase_0123456789abcdef'&&text.includes('待审核'),review:!!document.querySelector('input[aria-label=\"Reviewer ID\"]'),states:text.includes('已审核')&&text.includes('无效')&&text.includes('不完整'),evidence:['Evidence Artifact ID','Evidence digest','Evidence schema','Evidence type'].every(x=>document.querySelector(`[aria-label=\"${x}\"]`)),slices:['format','processing_class','native_ocr','structure','language','question_class','difficulty','criticality'].every(x=>document.querySelector(`[aria-label=\"${x}\"]`)),overflow:document.documentElement.scrollWidth<=innerWidth}}await new Promise(r=>setTimeout(r,25))}throw new Error('dataset did not render')})()"""
        assert _cdp(debug_port, dataset, await_promise=True, target_url=dataset_url) == {"generated": True, "review": True, "states": True, "evidence": True, "slices": True, "overflow": True}
        if width == 644:
            _cdp(debug_port, "document.querySelector('.dataset-case-editor').scrollIntoView(); true", target_url=dataset_url)
        dataset_image = tmp_path / f"evaluation-dataset-editor-{width}.png"
        _capture_cdp(debug_port, dataset_image, target_url=dataset_url)
        _assert_manifest_visual(debug_port, dataset_image, dataset_image.name, target_url=dataset_url, baseline_root=S026_BASELINE_ROOT, story="S-026")
        run_url = f"http://127.0.0.1:{port}/workbench/evaluation-run?run={_EVALUATION_RUN}"
        assert _cdp(debug_port, f"location.href='{run_url}'; true", target_url=dataset_url) is True
        run = """(async()=>{for(let i=0;i<200;i++){const text=document.body.innerText;if(text.includes('不可变 Manifest')&&text.includes('质量门禁与适用性'))return {failed:text.includes('失败'),evidence:[...document.querySelectorAll('.evidence-chain-actions button')].some(x=>x.textContent==='Source'),owners:['Ingestion','Retrieval','Context','Answer','Citation','Decision','Judge','Latency','Resources'].every(x=>text.includes(x)),overflow:document.documentElement.scrollWidth<=innerWidth};await new Promise(r=>setTimeout(r,25));}throw new Error('run did not render')})()"""
        assert _cdp(debug_port, run, await_promise=True, target_url=run_url) == {"failed": True, "evidence": True, "owners": True, "overflow": True}
        _capture_cdp(debug_port, tmp_path / f"evaluation-run-{width}.png", target_url=run_url)
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1", reason="set KB2_BROWSER_TESTS=1 for S-025 behavior")
def test_s025_query_options_stale_preflight_poll_stop_and_terminal_cleanup(tmp_path: Path) -> None:
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
    url = f"http://127.0.0.1:{port}/workbench/query?fixture=options-loading"
    _wait_for_fixture(url)
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", "--window-size=1440,900", f"--user-data-dir={tmp_path / 'query-behavior'}", url])
    try:
        _prepare_s022_capture_environment(debug_port, url, 1440)
        options = _cdp(debug_port, """(async()=>{const initial=document.querySelector('.query-status')?.textContent;for(let i=0;i<100;i++){if(document.querySelector('.query-status')?.textContent==='Query Lab 已就绪。')return {initial,ready:true};await new Promise(r=>setTimeout(r,25))}return {initial,ready:false}})()""", await_promise=True, target_url=url)
        assert options == {"initial": "加载 Query Lab 选项…", "ready": True}
        empty_url = f"http://127.0.0.1:{port}/workbench/query?fixture=options-empty"
        assert _cdp(debug_port, f"location.href={json.dumps(empty_url)};true", target_url=url) is True
        assert _cdp(debug_port, """(async()=>{for(let i=0;i<100;i++){if(document.querySelector('.query-status')?.textContent==='没有可执行的 Query Profile 或索引。')return document.querySelectorAll('select option[value=""]').length===2;await new Promise(r=>setTimeout(r,25))}return false})()""", await_promise=True, target_url=empty_url) is True
        error_url = f"http://127.0.0.1:{port}/workbench/query?fixture=options-error"
        assert _cdp(debug_port, f"location.href={json.dumps(error_url)};true", target_url=empty_url) is True
        assert _cdp(debug_port, """(async()=>{for(let i=0;i<100;i++){const s=document.querySelector('.query-status');if(s?.textContent==='Query Lab 选项不可用。')return s.getAttribute('role')==='alert';await new Promise(r=>setTimeout(r,25))}return false})()""", await_promise=True, target_url=error_url) is True
        ready_url = f"http://127.0.0.1:{port}/workbench/query"
        assert _cdp(debug_port, f"location.href={json.dumps(ready_url)};true", target_url=error_url) is True
        behavior = """(async()=>{const wait=async p=>{for(let i=0;i<240;i++){const v=p();if(v)return v;await new Promise(r=>setTimeout(r,25))}throw new Error('query behavior timed out')},setQuestion=value=>{q.value=value;q.dispatchEvent(new Event('input',{bubbles:true}))},preflight=()=>[...document.querySelectorAll('button')].find(x=>x.textContent==='预检'&&!x.disabled)?.click();const q=await wait(()=>document.querySelector('textarea[aria-label="问题"]')&&document.querySelector('.query-status')?.textContent==='Query Lab 已就绪。'&&document.querySelector('textarea[aria-label="问题"]'));setQuestion('preflight-error');preflight();await wait(()=>document.querySelector('.query-status')?.textContent==='预检失败，输入与选择已保留。');const preflightError=q.value==='preflight-error'&&!document.querySelector('.query-preflight')&&![...document.querySelectorAll('button')].some(x=>x.textContent==='创建 Query Run')&&!![...document.querySelectorAll('button')].find(x=>x.textContent==='预检'&&!x.disabled);setQuestion('submit-error');preflight();let ack=await wait(()=>document.querySelector('input[aria-label="确认外部阶段披露"]'));ack.click();let submit=[...document.querySelectorAll('button')].find(x=>x.textContent==='创建 Query Run');submit.click();await wait(()=>document.querySelector('.query-status')?.textContent==='Query Run 创建失败，可重试或重新预检。');const submitError=!!document.querySelector('.query-preflight')&&ack.checked&&!submit.disabled;setQuestion('stale-old');preflight();await new Promise(r=>setTimeout(r,30));setQuestion('local');(await wait(()=>[...document.querySelectorAll('button')].find(x=>x.textContent==='预检'&&!x.disabled))).click();await wait(()=>document.querySelector('.query-preflight'));await new Promise(r=>setTimeout(r,250));const localOnly=!document.querySelector('input[aria-label="确认外部阶段披露"]')&&!document.body.innerText.includes('外部生成边界');setQuestion('delayed-submit');(await wait(()=>[...document.querySelectorAll('button')].find(x=>x.textContent==='预检'&&!x.disabled))).click();ack=await wait(()=>document.querySelector('input[aria-label="确认外部阶段披露"]'));ack.click();[...document.querySelectorAll('button')].find(x=>x.textContent==='创建 Query Run').click();setQuestion('changed while submit pending');await new Promise(r=>setTimeout(r,450));const delayedSubmit=q.value==='changed while submit pending'&&document.querySelector('.query-status')?.textContent==='输入已更改，请重新预检。'&&!document.querySelector('.final-state')&&!document.querySelector('.query-stop-host button)&&!![...document.querySelectorAll('button')].find(x=>x.textContent==='预检'&&!x.disabled);setQuestion('active');(await wait(()=>[...document.querySelectorAll('button')].find(x=>x.textContent==='预检'&&!x.disabled))).click();ack=await wait(()=>document.querySelector('input[aria-label="确认外部阶段披露"]'));ack.click();[...document.querySelectorAll('button')].find(x=>x.textContent==='创建 Query Run').click();await wait(()=>[...document.querySelectorAll('.query-stop-host button')].find(x=>x.textContent==='停止'));await new Promise(r=>setTimeout(r,1100));const oneStop=document.querySelectorAll('.query-stop-host button').length===1;document.querySelector('.query-stop-host button').click();await wait(()=>document.querySelector('.final-state')?.innerText.includes('ANSWERED')&&!document.querySelector('.query-stop-host button'));await new Promise(r=>setTimeout(r,650));const evidence=document.querySelector('.evidence-row')?.innerText||'',body=document.body.innerText;return {preflightError,submitError,localOnly,delayedSubmit,oneStop,terminalCleanup:!document.querySelector('.query-stop-host button')&&document.querySelector('.final-state')?.innerText.includes('ANSWERED'),citation:!![...document.querySelectorAll('.evidence-row button')].find(x=>x.textContent==='cit_fixture'),score:body.includes('keyword / 0.8'),decision:evidence.includes('included')&&evidence.includes('决策理由 / reason'),candidate:body.includes('vector #1 / 0.7 (cosine.normalized)')&&body.includes('Rerank 决策')&&body.includes('定位不可用')===false}})()"""
        delayed_start, delayed_end = behavior.index("setQuestion('delayed-submit')"), behavior.index("setQuestion('active')")
        behavior = behavior[:delayed_start] + behavior[delayed_end:]
        behavior = behavior.replace("preflightError,submitError,localOnly,delayedSubmit,oneStop", "preflightError,submitError,localOnly,oneStop")
        behavior = behavior.replace(
            "const evidence=document.querySelector('.evidence-row')?.innerText||'',body=document.body.innerText;return",
            "const evidence=document.querySelector('.evidence-row')?.innerText||'',candidateTabs=[...document.querySelectorAll('.candidate-tabs button')];candidateTabs.find(x=>x.textContent==='fusion').click();const fusionText=document.querySelector('.candidate-panel').innerText;candidateTabs.find(x=>x.textContent==='rerank').click();const rerankText=document.querySelector('.candidate-panel').innerText,body=document.body.innerText,candidateProjection=fusionText.includes('vector #1 / 0.7 (cosine.normalized)')&&fusionText.includes('PDF / 第 1 页')&&rerankText.includes('included / 1->1'),sourcePreview=[...document.querySelectorAll('.evidence-row button')].some(x=>x.textContent==='源预览');return",
        ).replace(
            "candidate:body.includes('vector #1 / 0.7 (cosine.normalized)')&&body.includes('Rerank 决策')&&body.includes('定位不可用')===false",
            "candidate:candidateProjection",
        ).replace("citation:!![...document.querySelectorAll('.evidence-row button')].find(x=>x.textContent==='cit_fixture')", "citation:!![...document.querySelectorAll('.citation-actions button')].find(x=>x.textContent==='cit_fixture'),sourcePreview").replace("evidence.includes('决策理由 / reason')", "evidence.includes('决策理由')").replace("const oneStop=document.querySelectorAll('.query-stop-host button').length===1;", "const oneStop=document.querySelectorAll('.query-stop-host button').length===1,pendingNeutral=!document.querySelector('.final-state')&&!document.body.innerText.includes('UNAVAILABLE')&&document.body.innerText.includes('Query Run 正在执行');").replace("oneStop,terminalCleanup", "oneStop,pendingNeutral,terminalCleanup")
        assert _cdp(debug_port, behavior, await_promise=True, target_url=ready_url) == {"preflightError": True, "submitError": True, "localOnly": True, "oneStop": True, "pendingNeutral": True, "terminalCleanup": True, "citation": True, "sourcePreview": True, "score": True, "decision": True, "candidate": True}
        delayed_submit = """(async()=>{const wait=async p=>{for(let i=0;i<160;i++){const v=p();if(v)return v;await new Promise(r=>setTimeout(r,25))}throw new Error('delayed submit timeout')};const q=document.querySelector('textarea[aria-label="问题"]');q.value='delayed-submit';q.dispatchEvent(new Event('input',{bubbles:true}));(await wait(()=>[...document.querySelectorAll('button')].find(x=>x.textContent==='预检'&&!x.disabled))).click();const ack=await wait(()=>document.querySelector('input[aria-label="确认外部阶段披露"]'));ack.click();[...document.querySelectorAll('button')].find(x=>x.textContent==='创建 Query Run').click();q.value='changed while submit pending';q.dispatchEvent(new Event('input',{bubbles:true}));await new Promise(r=>setTimeout(r,450));return {question:q.value,status:document.querySelector('.query-status')?.textContent,preview:!!document.querySelector('.query-preflight'),final:!!document.querySelector('.final-state'),stop:!!document.querySelector('.query-stop-host button'),preflight:!![...document.querySelectorAll('button')].find(x=>x.textContent==='预检'&&!x.disabled)}})()"""
        assert _cdp(debug_port, delayed_submit, await_promise=True, target_url=ready_url) == {"question": "changed while submit pending", "status": "输入已更改，请重新预检。", "preview": False, "final": False, "stop": False, "preflight": True}
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1", reason="set KB2_BROWSER_TESTS=1 for S-025 source preview")
def test_s025_non_answered_source_preview_sync_escape_focus_and_url_context(tmp_path: Path) -> None:
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
    url = f"http://127.0.0.1:{port}/workbench/query?workspace=fixture&q=diagnosis-context"
    _wait_for_fixture(url)
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", "--window-size=1440,900", f"--user-data-dir={tmp_path / 'query-non-answer-preview'}", url])
    try:
        _prepare_s022_capture_environment(debug_port, url, 1440)
        result = _cdp(debug_port, """(async()=>{const wait=async p=>{for(let i=0;i<180;i++){const value=p();if(value)return value;await new Promise(r=>setTimeout(r,25))}throw new Error('source preview unavailable')};const before=location.href,q=await wait(()=>document.querySelector('textarea[aria-label="问题"]'));q.value='clarification-required';q.dispatchEvent(new Event('input',{bubbles:true}));(await wait(()=>[...document.querySelectorAll('button')].find(x=>x.textContent==='预检'&&!x.disabled))).click();const submit=await wait(()=>[...document.querySelectorAll('button')].find(x=>x.textContent==='创建 Query Run'));document.querySelector('input[aria-label="确认外部阶段披露"]').click();submit.click();await wait(()=>document.querySelector('.final-state')?.innerText.includes('CLARIFICATION_REQUIRED'));const preview=await wait(()=>[...document.querySelectorAll('.evidence-row button')].find(x=>x.textContent==='源预览'));preview.click();await wait(()=>document.querySelector('.artifact-inspector .source-selected'));const synchronized=document.querySelector('.locator-summary')?.textContent.includes('pdf / 第 1 页'),noCitation=!document.querySelector('.citation-actions button'),unchangedOpen=location.href===before;document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await new Promise(r=>setTimeout(r,50));return {synchronized,noCitation,unchangedOpen,closed:!document.querySelector('.artifact-inspector'),focusReturned:document.activeElement===preview,unchangedClosed:location.href===before}})()""", await_promise=True, target_url=url)
        assert result == {"synchronized": True, "noCitation": True, "unchangedOpen": True, "closed": True, "focusReturned": True, "unchangedClosed": True}
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1", reason="set KB2_BROWSER_TESTS=1 for S-026 dataset behavior")
def test_s026_dataset_round_trip_failures_empty_and_filter(tmp_path: Path) -> None:
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
    url = f"http://127.0.0.1:{port}/workbench/evaluation-dataset"
    _wait_for_fixture(url)
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", "--window-size=1440,900", f"--user-data-dir={tmp_path / 'dataset-behavior'}", url])
    try:
        _prepare_s022_capture_environment(debug_port, url, 1440)
        result = _cdp(debug_port, """(async()=>{const wait=async p=>{for(let i=0;i<160;i++){const v=p();if(v)return v;await new Promise(r=>setTimeout(r,25))}throw new Error('dataset behavior timed out')};await wait(()=>document.querySelector('.dataset-case-row[aria-pressed=true] strong')?.textContent==='qcase_0123456789abcdef');const queryFields=['Evidence Artifact ID','Evidence digest','Evidence schema','Evidence type'].every(x=>document.querySelector(`[aria-label="${x}"]`)),states=['已审核','无效','不完整'].every(x=>document.body.innerText.includes(x));[...document.querySelectorAll('.dataset-case-row')].find(x=>x.innerText.includes('ann_0123456789abcdef')).click();const targetFields=['Target kind','Target element ID','Target table ID','Target cell ID','Target locator','Target start','Target end'].every(x=>document.querySelector(`[aria-label="${x}"]`)),locator=await wait(()=>document.querySelector('[aria-label="Target locator"]')),save=()=>[...document.querySelectorAll('button')].find(x=>x.textContent==='验证并保存');locator.value='{"kind":';locator.dispatchEvent(new Event('input',{bubbles:true}));const invalidLocator=locator.value==='{"kind":'&&save().disabled&&document.querySelector('.field-error')?.textContent.includes('有效 JSON');locator.value='{"kind":"pdf","page_number":1,"x0":0,"y0":0,"x1":0.5,"y1":0.5}';locator.dispatchEvent(new Event('input',{bubbles:true}));const correctedLocator=!save().disabled&&!document.querySelector('.field-error')?.textContent;const end=await wait(()=>document.querySelector('[aria-label="Target end"]'));end.value='9';end.dispatchEvent(new Event('input',{bubbles:true}));save().click();const question=await wait(()=>document.querySelector('textarea[aria-label="问题"]'));question.value='trigger-save-failure';question.dispatchEvent(new Event('input',{bubbles:true}));[...document.querySelectorAll('button')].find(x=>x.textContent==='验证并保存').click();await wait(()=>document.querySelector('.dataset-status')?.textContent==='保存失败，编辑已保留。');const reviewer=await wait(()=>document.querySelector('input[aria-label="Reviewer ID"]'));reviewer.value='fail.review';reviewer.dispatchEvent(new Event('input',{bubbles:true}));[...document.querySelectorAll('button')].find(x=>x.textContent==='标记已审核').click();await wait(()=>document.querySelector('.dataset-status')?.textContent==='审核失败，Reviewer ID 已保留。');const filter=await wait(()=>document.querySelector('input[aria-label="筛选评估数据集"]'));filter.value='empty';filter.dispatchEvent(new Event('input',{bubbles:true}));await wait(()=>document.body.innerText.includes('没有匹配数据集'));const empty=document.body.innerText.includes('没有可编辑数据集');filter.value='';filter.dispatchEvent(new Event('input',{bubbles:true}));await wait(()=>document.querySelector('.dataset-case-row[aria-pressed=true] strong')?.textContent==='qcase_0123456789abcdef'&&document.querySelector('[aria-label="Evidence Artifact ID"]'));return {queryFields,targetFields,invalidLocator,correctedLocator,saveFailure:question.value==='trigger-save-failure',reviewFailure:reviewer.value==='fail.review',empty,states,restored:document.querySelector('.dataset-detail-header h2')?.textContent==='评估数据集 / r1'&&document.querySelectorAll('.dataset-case-row').length===5}})()""", await_promise=True, target_url=url)
        assert result == {"queryFields": True, "targetFields": True, "invalidLocator": True, "correctedLocator": True, "saveFailure": True, "reviewFailure": True, "empty": True, "states": True, "restored": True}
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1", reason="set KB2_BROWSER_TESTS=1 for S-026 gate and judge behavior")
def test_s026_gate_and_judge_authoritative_state_matrix(tmp_path: Path) -> None:
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
    url = f"http://127.0.0.1:{port}/workbench/evaluation-run?run={_EVALUATION_RUNS['status-matrix']}"
    _wait_for_fixture(url)
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", "--window-size=1440,900", f"--user-data-dir={tmp_path / 'evaluation-status'}", url])
    try:
        _prepare_s022_capture_environment(debug_port, url, 1440)
        result = _cdp(debug_port, f"""(async()=>{{for(let i=0;i<160;i++){{if(document.querySelectorAll('.gate-row').length===4){{const text=document.body.innerText,gates=[...document.querySelectorAll('.gate-row')].map(x=>x.innerText),judge=[...document.querySelectorAll('.evaluation-diagnostic-pane dd')].map(x=>x.textContent),latency=document.querySelector('[data-owner="latency"]')?.innerText||'',resources=document.querySelector('[data-owner="resources"]')?.innerText||'',bindings=[['gate.pass','answer.coverage@1'],['gate.fail','answer.failure@1'],['gate.insufficient','citation.fixture@1'],['gate.ineligible','judge.ineligible@1']];return {{gates:['PASS','FAIL','INSUFFICIENT','INELIGIBLE'].every(x=>gates.some(row=>row.includes(x))),configured:bindings.every(([gate,metric])=>gates.some(row=>row.includes(gate)&&row.includes(metric)&&row.includes('criticality')&&row.includes('higher_is_better 0.7'))),metricNotApplicable:text.includes('NOT_APPLICABLE'),judge:['ELIGIBLE','ADVISORY','INELIGIBLE','DRIFTED'].every(x=>judge.some(row=>row.includes(x))),calibration:text.includes({json.dumps(_COMPARISON)}),manifest:text.includes('Ingestion plan digest')&&text.includes('Query plan digest')&&text.includes('fixture.ingestion@1')&&text.includes('fixture.query@1')&&text.includes('Package digest')&&text.includes('Resource sampler'),operation:latency.includes('Elapsed ms')&&!latency.includes('CPU ms')&&resources.includes('CPU ms')&&resources.includes('Peak RSS')&&resources.includes('IO bytes')&&!resources.includes('Elapsed ms')}}}}await new Promise(r=>setTimeout(r,25))}}return null}})()""", await_promise=True, target_url=url)
        assert result == {"gates": True, "configured": True, "metricNotApplicable": True, "judge": True, "calibration": True, "manifest": True, "operation": True}
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1", reason="set KB2_BROWSER_TESTS=1 for S-025 visuals")
@pytest.mark.parametrize("scenario", ("fact-answered", "table-answered-inspector", "hierarchy-answered", "clarification-required", "abstained", "repair-answered", "repair-exhausted"))
@pytest.mark.parametrize("width", (1440, 644))
def test_s025_query_final_state_visual_matrix(tmp_path: Path, width: int, scenario: str) -> None:
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
    url = f"http://127.0.0.1:{port}/workbench/query"
    _wait_for_fixture(url)
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", f"--window-size={width},900", f"--user-data-dir={tmp_path / 'query-matrix'}", url])
    try:
        _prepare_s022_capture_environment(debug_port, url, width)
        expected = "FAILED" if scenario == "repair-exhausted" else "CLARIFICATION_REQUIRED" if scenario == "clarification-required" else "ABSTAINED" if scenario == "abstained" else "ANSWERED"
        answered = expected == "ANSWERED"
        expression = f"""(async()=>{{const wait=async p=>{{for(let i=0;i<160;i++){{const v=p();if(v)return v;await new Promise(r=>setTimeout(r,25))}}throw new Error('query state did not render')}};const q=await wait(()=>document.querySelector('textarea[aria-label="问题"]'));q.value={json.dumps(scenario)};q.dispatchEvent(new Event('input',{{bubbles:true}}));const pre=await wait(()=>[...document.querySelectorAll('button')].find(x=>x.textContent==='预检'&&!x.disabled));pre.click();const submit=await wait(()=>[...document.querySelectorAll('button')].find(x=>x.textContent==='创建 Query Run'));const blocked=submit.disabled;document.querySelector('input[aria-label="确认外部阶段披露"]').click();submit.click();await wait(()=>document.querySelector('.final-state')?.innerText.includes({json.dumps(expected)}));const tabs=[...document.querySelectorAll('[role=tab]')];tabs[0].focus();tabs[0].dispatchEvent(new KeyboardEvent('keydown',{{key:'ArrowRight',bubbles:true}}));const body=document.body.innerText,evidence=document.querySelector('.evidence-row')?.innerText||'',citation=[...document.querySelectorAll('.citation-actions button')].some(x=>x.textContent==='cit_fixture'),preview=[...document.querySelectorAll('.evidence-row button')].some(x=>x.textContent==='源预览');return {{blocked,threePanes:document.querySelector('.query-workspace').children.length===3,tabbed:tabs.length===3&&tabs[1].getAttribute('aria-selected')==='true',decisionPath:body.includes('决策路径')&&body.includes('项目验收与预算说明.pdf')&&body.includes('included'),duration:body.includes('120 ms'),shortage:{str(scenario == 'hierarchy-answered').lower()}?body.includes('none')&&body.includes('164'):body.includes('below_minimum')&&body.includes('96'),multiEvidence:{str(scenario != 'hierarchy-answered').lower()}||document.querySelectorAll('.evidence-row').length===2&&document.querySelectorAll('.citation-actions button').length===2,candidate:body.includes('vector #1 / 0.7 (cosine.normalized)')&&body.includes({json.dumps('SPREADSHEET / 工作表 华东预算 / 范围 B7' if scenario == 'table-answered-inspector' else 'PDF / 第 1 页')}),labelledOverflow:[...document.querySelectorAll('.query-retrieval-pane .table-wrap[role=region]')].filter(x=>x.getAttribute('aria-label')).length>=2,preview,citationCommand:citation==={str(answered).lower()},noAnswer:{str(answered).lower()}||!document.querySelector('.answer-copy'),collapsed:[...document.querySelectorAll('.evidence-details,.verification-attempt,.query-attempt')].every(x=>!x.open),noRaw:!body.includes('[object Object]')&&!body.includes('"chunk_id"'),overflow:document.documentElement.scrollWidth<=innerWidth}}}})()"""
        assert _cdp(debug_port, expression, await_promise=True, target_url=url) == {"blocked": True, "threePanes": True, "tabbed": True, "decisionPath": True, "duration": True, "shortage": True, "multiEvidence": True, "candidate": True, "labelledOverflow": True, "preview": True, "citationCommand": True, "noAnswer": True, "collapsed": True, "noRaw": True, "overflow": True}
        if scenario == "table-answered-inspector":
            assert _cdp(debug_port, "[...document.querySelectorAll('.evidence-row button')].find(x=>x.textContent==='源预览').click();true", target_url=url) is True
            table_sync = _cdp(debug_port, "(async()=>{const state=()=>{const selected=document.querySelector('.artifact-table .source-selected');return {tab:document.querySelector('[role=tab][data-tab=table]')?.getAttribute('aria-selected')==='true',selected:selected?.textContent.includes('tbl_budget')===true,summary:document.querySelector('.locator-summary')?.textContent.includes('华东预算 / B7')===true,cell:selected?.closest('.artifact-table')?.textContent.includes('128 万元')===true}};for(let i=0;i<160;i++){const result=state();if(Object.values(result).every(Boolean))return result;await new Promise(r=>setTimeout(r,25))}return state()})()", await_promise=True, target_url=url)
            assert table_sync == {"tab": True, "selected": True, "summary": True, "cell": True}
        elif width == 644:
            assert _cdp(debug_port, "document.querySelector('.final-state').scrollIntoView();true", target_url=url) is True
        image = tmp_path / f"query-{scenario}-{width}.png"
        _capture_cdp(debug_port, image, target_url=url)
        _assert_manifest_visual(debug_port, image, image.name, target_url=url, baseline_root=S025_BASELINE_ROOT, story="S-025")
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1", reason="set KB2_BROWSER_TESTS=1 for S-026 visuals")
@pytest.mark.parametrize("scenario", ("running", "failed-gates", "passed-gates", "invalid-dataset"))
@pytest.mark.parametrize("width", (1440, 644))
def test_s026_evaluation_run_visual_matrix(tmp_path: Path, width: int, scenario: str) -> None:
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
    url = f"http://127.0.0.1:{port}/workbench/evaluation-run?run={_EVALUATION_RUNS[scenario]}"
    _wait_for_fixture(url)
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", f"--window-size={width},900", f"--user-data-dir={tmp_path / 'evaluation-matrix'}", url])
    try:
        _prepare_s022_capture_environment(debug_port, url, width)
        has_report = scenario in {"failed-gates", "passed-gates"}
        state = _cdp(debug_port, f"""(async()=>{{for(let i=0;i<160;i++){{if(document.querySelector('.evaluation-run-header')){{const text=document.body.innerText,latency=document.querySelector('[data-owner="latency"]')?.innerText||'',resources=document.querySelector('[data-owner="resources"]')?.innerText||'';return {{manifest:text.includes('不可变 Manifest')&&text.includes('Ingestion plan digest')&&text.includes('Query plan digest')&&text.includes('Declared identities')&&text.includes('Bindings')&&text.includes('Package digest'),layers:{str(not has_report).lower()}||['Ingestion','Retrieval','Context','Answer','Citation','Decision','Judge','Latency','Resources'].every(x=>text.includes(x)),operation:{str(not has_report).lower()}||(latency.includes('Elapsed ms')&&!latency.includes('CPU ms')&&resources.includes('CPU ms')&&!resources.includes('Elapsed ms')),configured:{str(not has_report).lower()}||text.includes('criticality')&&text.includes('higher_is_better 0.7'),permanent:{str(not has_report).lower()}||text.includes('质量门禁与适用性'),safeInvalid:{str(scenario != 'invalid-dataset').lower()}||text.includes('EVALUATION_ARTIFACT_UNAVAILABLE'),running:{str(scenario != 'running').lower()}||text.includes('指标将在不可变报告生成后显示'),noOverall:!text.includes('总体分数'),overflow:document.documentElement.scrollWidth<=innerWidth}}}}await new Promise(r=>setTimeout(r,25))}}throw new Error('evaluation run did not render')}})()""", await_promise=True, target_url=url)
        assert state == {"manifest": scenario != "invalid-dataset", "layers": True, "operation": True, "configured": True, "permanent": True, "safeInvalid": True, "running": True, "noOverall": True, "overflow": True}
        if has_report:
            target = ".evaluation-diagnostic-pane" if width == 644 else ".evaluation-metric-pane"
            _cdp(debug_port, f"document.querySelector({json.dumps(target)}).scrollIntoView(); true", target_url=url)
        image = tmp_path / f"evaluation-run-{scenario}-{width}.png"
        _capture_cdp(debug_port, image, target_url=url)
        _assert_manifest_visual(debug_port, image, image.name, target_url=url, baseline_root=S026_BASELINE_ROOT, story="S-026")
        if scenario == "failed-gates":
            assert _cdp(debug_port, "(()=>{const owner=document.querySelector('select[aria-label=\"指标 Owner\"]');owner.value='answer';owner.dispatchEvent(new Event('change',{bubbles:true}));return document.body.innerText.includes('gate.answer')&&document.body.innerText.includes('INELIGIBLE')})()", target_url=url) is True
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for S-027 visual evidence",
)
@pytest.mark.parametrize("width", (1440, 644))
def test_fixture_backed_comparison_and_mixed_history_diagnosis_matrix(tmp_path: Path, width: int) -> None:
    """S-027 visual matrix: comparison bands, non-causal state, and Run drilldown."""
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
    compare_url = f"http://127.0.0.1:{port}/workbench/compare"
    for _ in range(60):
        try:
            if httpx.get(compare_url, timeout=.2).is_success:
                break
        except httpx.HTTPError:
            pass
        time.sleep(.05)
    else:
        server.terminate()
        server.wait(timeout=10)
        pytest.fail("S-027 fixture shell did not start")
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", f"--window-size={width},900", f"--user-data-dir={tmp_path / 's027'}", compare_url])
    try:
        _prepare_s022_capture_environment(debug_port, compare_url, width)
        compare = f"""(async()=>{{const wait=async p=>{{for(let i=0;i<160;i++){{const v=p();if(v)return v;await new Promise(r=>setTimeout(r,25));}}throw new Error('comparison did not render: '+document.body.innerText)}};const base=await wait(()=>{{const x=document.querySelector('select[aria-label="基准 Evaluation Report"]');return x&&x.options.length===4&&x}});base.value={json.dumps(_COMPARISON_BASELINE)};base.dispatchEvent(new Event('change',{{bubbles:true}}));const candidate=await wait(()=>{{const x=document.querySelector('select[aria-label="候选 Evaluation Report"]');return x&&x.options.length===4&&!x.disabled&&x}});candidate.value={json.dumps(_COMPARISON_CANDIDATE)};candidate.dispatchEvent(new Event('change',{{bubbles:true}}));const submit=[...document.querySelectorAll('button')].find(x=>x.textContent==='创建固定比较');await wait(()=>!submit.disabled);submit.click();await wait(()=>document.body.innerText.includes('MULTI_AXIS_NON_CAUSAL'));const text=document.body.innerText,wrap=document.querySelector('.comparison-band .table-wrap');return {{nonCausal:text.includes('非因果比较')&&!text.includes('唯一变化'),identity:['Manifest digest','Dataset digest','Taxonomy','Input catalog'].every(x=>text.includes(x)),bands:['质量与变化','样本与置信区间','质量门禁','失败案例','延迟（独立）','本地资源（独立）'].every(x=>text.includes(x)),confidence:text.includes('wilson')&&text.includes('0.95'),qualitySides:['基准主体','基准状态','基准标签','基准匹配','候选主体','候选状态','候选标签','候选匹配'].every(x=>text.includes(x))&&text.includes('baseline')&&text.includes('candidate'),zeroBaseline:text.includes('UNDEFINED_BASELINE_ZERO'),tableScrollable:wrap.scrollWidth>wrap.clientWidth,overflow:document.documentElement.scrollWidth<=innerWidth,raw:!document.querySelector('main pre'),controls:[...document.querySelectorAll('main button,main select,main input')].every(x=>x.getBoundingClientRect().width>0&&x.getBoundingClientRect().height>0)}}}})()"""
        assert _cdp(debug_port, compare, await_promise=True, target_url=compare_url) == {"nonCausal": True, "identity": True, "bands": True, "confidence": True, "qualitySides": True, "zeroBaseline": True, "tableScrollable": width < 900, "overflow": True, "raw": True, "controls": True}
        multi_image = tmp_path / f"comparison-multi-axis-{width}.png"
        _cdp(debug_port, "scrollTo(0,0); true", target_url=compare_url)
        multi_visibility = _cdp(
            debug_port,
            "Object.fromEntries([['controls',document.querySelector('.comparison-controls')],['axis',document.querySelector('.comparison-axis')],['identity',document.querySelector('.comparison-identity')],...['comparison-quality-title','comparison-confidence-title','comparison-gates-title','comparison-cases-title','comparison-latency-title','comparison-resources-title'].flatMap(id=>[[id,document.getElementById(id)],[id+'-rows',document.getElementById(id).closest('.comparison-band').querySelector('tbody')]])].map(([key,node])=>{const r=node.getBoundingClientRect();return [key,{top:Math.round(r.top),bottom:Math.round(r.bottom),visible:r.bottom>0&&r.top<innerHeight}]}))",
            target_url=compare_url,
        )
        if not all(item["visible"] for item in multi_visibility.values()):
            pytest.fail(f"S-027 multi-axis evidence outside viewport: {json.dumps(multi_visibility, sort_keys=True)}")
        _capture_cdp(debug_port, multi_image, target_url=compare_url)
        _assert_manifest_visual(debug_port, multi_image, multi_image.name, target_url=compare_url, baseline_root=S027_BASELINE_ROOT, story="S-027")
        single = f"""(async()=>{{const candidate=document.querySelector('select[aria-label="候选 Evaluation Report"]'),submit=[...document.querySelectorAll('button')].find(x=>x.textContent==='创建固定比较');candidate.value={json.dumps(_COMPARISON_SINGLE)};candidate.dispatchEvent(new Event('change',{{bubbles:true}}));submit.click();for(let i=0;i<160;i++){{if(document.body.innerText.includes('唯一变化：query.plugin'))return {{single:document.body.innerText.includes('SINGLE_AXIS')&&!document.body.innerText.includes('非因果比较'),recommendation:document.body.innerText.includes('CANDIDATE_ELIGIBLE'),policyNone:document.body.innerText.includes('POLICY_NONE'),overflow:document.documentElement.scrollWidth<=innerWidth}};await new Promise(r=>setTimeout(r,25))}}throw new Error('single axis did not render')}})()"""
        assert _cdp(debug_port, single, await_promise=True, target_url=compare_url) == {"single": True, "recommendation": True, "policyNone": True, "overflow": True}
        single_image = tmp_path / f"comparison-single-axis-{width}.png"
        _cdp(debug_port, "scrollTo(0,0); true", target_url=compare_url)
        single_visibility = _cdp(
            debug_port,
            "Object.fromEntries([['controls',document.querySelector('.comparison-controls')],['axis',document.querySelector('.comparison-axis')],['identity',document.querySelector('.comparison-identity')],...['comparison-quality-title','comparison-confidence-title','comparison-gates-title','comparison-cases-title','comparison-latency-title','comparison-resources-title'].flatMap(id=>[[id,document.getElementById(id)],[id+'-rows',document.getElementById(id).closest('.comparison-band').querySelector('tbody')]]),['recommendation',document.querySelector('.comparison-recommendation')]].map(([key,node])=>{const r=node.getBoundingClientRect();return [key,{top:Math.round(r.top),bottom:Math.round(r.bottom),visible:r.bottom>0&&r.top<innerHeight}]}))",
            target_url=compare_url,
        )
        if not all(item["visible"] for item in single_visibility.values()):
            pytest.fail(f"S-027 single-axis evidence outside viewport: {json.dumps(single_visibility, sort_keys=True)}")
        _capture_cdp(debug_port, single_image, target_url=compare_url)
        _assert_manifest_visual(debug_port, single_image, single_image.name, target_url=compare_url, baseline_root=S027_BASELINE_ROOT, story="S-027")

        history_url = f"http://127.0.0.1:{port}/workbench/runs?run={_HISTORY_QUERY}"
        assert _cdp(debug_port, f"location.href={json.dumps(history_url)}", target_url=compare_url) == history_url
        history = """(async()=>{const wait=async p=>{for(let i=0;i<160;i++){const v=p();if(v)return v;await new Promise(r=>setTimeout(r,25));}throw new Error('history did not render: '+document.body.innerText)};await wait(()=>document.querySelectorAll('.run-select').length===5);await wait(()=>document.body.innerText.includes('citation-ready Evidence'));const stop=[...document.querySelectorAll('button')].find(x=>x.textContent==='停止'),text=document.body.innerText;return {types:['INGESTION','QUERY','EVALUATION','COMPARISON','CONTRACT_TEST'].every(x=>text.includes(x)),identity:text.includes('browser-query')&&text.includes('context.fixture@1')&&text.includes('artifact / 12345678'),artifact:[...document.querySelectorAll('button')].some(x=>x.textContent.includes('evidence.set')),ownerAction:!!stop&&!text.includes('重新运行'),selected:location.search.includes('run=12345678-1234-5678-1234-567812345696'),overflow:document.documentElement.scrollWidth<=innerWidth,controls:[...document.querySelectorAll('main button,main select,main input')].every(x=>x.getBoundingClientRect().width>0&&x.getBoundingClientRect().height>0)}})()"""
        assert _cdp(debug_port, history, await_promise=True, target_url=history_url) == {"types": True, "identity": True, "artifact": True, "ownerAction": True, "selected": True, "overflow": True, "controls": True}
        context = """(async()=>{const wait=async p=>{for(let i=0;i<120;i++){const v=p();if(v)return v;await new Promise(r=>setTimeout(r,25));}throw new Error('context flow did not render')};const artifact=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('evidence.set'));artifact.click();await wait(()=>document.querySelector('.artifact-inspector'));const drawerPreserves=location.search.includes('run=12345678-1234-5678-1234-567812345696');document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await wait(()=>!document.querySelector('.artifact-inspector'));[...document.querySelectorAll('a')].find(x=>x.textContent==='比较').click();return drawerPreserves})()"""
        assert _cdp(debug_port, context, await_promise=True) is True
        assert _cdp(debug_port, "({compare:location.pathname.endsWith('/compare'),run:new URL(location).searchParams.get('run')})") == {"compare": True, "run": _HISTORY_QUERY}
        assert _cdp(debug_port, f"history.back(); true") is True
        history_image = tmp_path / f"run-history-mixed-selected-{width}.png"
        for _ in range(80):
            if _cdp(debug_port, "location.pathname.endsWith('/runs')&&document.body.innerText.includes('citation-ready Evidence')"):
                break
            time.sleep(.025)
        _cdp(debug_port, "scrollTo(0,0); true")
        history_visibility = _cdp(debug_port, "(()=>{const nodes=[...document.querySelectorAll('.run-select'),document.querySelector('.run-detail-head'),...document.querySelectorAll('.run-stage > button')];return {count:document.querySelectorAll('.run-select').length,all:nodes.every(node=>{const r=node.getBoundingClientRect();return r.bottom>0&&r.top<innerHeight}),stageButtons:document.querySelectorAll('.run-stage > button').length}})()")
        assert history_visibility == {"count": 5, "all": True, "stageButtons": 2}
        _capture_cdp(debug_port, history_image)
        _assert_manifest_visual(debug_port, history_image, history_image.name, target_url=history_url, baseline_root=S027_BASELINE_ROOT, story="S-027")
    finally:
        browser.terminate()
        browser.wait(timeout=10)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for S-027 interaction evidence",
)
def test_s027_run_filters_retain_selection_and_recovery_tracks_owner(tmp_path: Path) -> None:
    """Filtered-out detail remains stable and Stop disappears after owner loss."""
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment,
    )
    url = f"http://127.0.0.1:{port}/workbench/runs?run={_HISTORY_QUERY}"
    _wait_for_fixture(url)
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", "--window-size=1440,900", f"--user-data-dir={tmp_path / 's027-interactions'}", url])
    try:
        result = _cdp(debug_port, """(async()=>{const wait=async p=>{for(let i=0;i<160;i++){const value=p();if(value)return value;await new Promise(r=>setTimeout(r,25))}throw new Error('Run interaction did not settle: '+document.body.innerText)};await wait(()=>document.body.innerText.includes('citation-ready Evidence'));const type=document.querySelector('select[aria-label="Run 类型"]');type.value='EVALUATION';type.dispatchEvent(new Event('change',{bubbles:true}));await wait(()=>document.querySelectorAll('.run-select').length===1&&document.body.innerText.includes('当前筛选范围外'));const retained=document.body.innerText.includes('QUERY / RUNNING')&&new URL(location).searchParams.get('runType')==='EVALUATION'&&new URL(location).searchParams.get('run')==='12345678-1234-5678-1234-567812345696';[...document.querySelectorAll('button')].find(x=>x.textContent==='清除筛选').click();await wait(()=>document.querySelectorAll('.run-select').length===5&&!document.body.innerText.includes('当前筛选范围外'));const stop=[...document.querySelectorAll('button')].find(x=>x.textContent==='停止');stop.click();await wait(()=>document.body.innerText.includes('QUERY / RUNNING')&&![...document.querySelectorAll('button')].some(x=>x.textContent==='停止'));return {retained,cleared:new URL(location).searchParams.get('runType')===null,ownerLost:![...document.querySelectorAll('button')].some(x=>x.textContent==='停止'),selected:new URL(location).searchParams.get('run')==='12345678-1234-5678-1234-567812345696'}})()""", await_promise=True, target_url=url)
        assert result == {"retained": True, "cleared": True, "ownerLost": True, "selected": True}
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 for S-027 stale and destination evidence",
)
def test_s027_stale_guards_url_rehydration_and_five_type_destinations(tmp_path: Path) -> None:
    """Latest requests win and every stored Run type exposes only real destinations."""
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment,
    )
    url = f"http://127.0.0.1:{port}/workbench/runs?run={_HISTORY_QUERY}&runType=QUERY&runState=RUNNING&q=browser-query"
    _wait_for_fixture(url)
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", "--window-size=1440,900", f"--user-data-dir={tmp_path / 's027-stale'}", url])
    try:
        identifiers = {"INGESTION": _INGESTION_RUN, "QUERY": _HISTORY_QUERY, "EVALUATION": _EVALUATION_RUNS["passed-gates"],
                       "COMPARISON": _HISTORY_COMPARISON, "CONTRACT_TEST": _HISTORY_CONTRACT}
        script = f"""(async()=>{{const wait=async p=>{{for(let i=0;i<200;i++){{const value=p();if(value)return value;await new Promise(r=>setTimeout(r,25))}}throw new Error('S027 state did not settle: '+document.body.innerText)}};await wait(()=>document.body.innerText.includes('citation-ready Evidence'));const type=document.querySelector('select[aria-label="Run 类型"]'),state=document.querySelector('select[aria-label="Run 状态"]'),q=document.querySelector('input[aria-label="筛选 Run"]');const rehydrated=type.value==='QUERY'&&state.value==='RUNNING'&&q.value==='browser-query'&&document.querySelectorAll('.run-select').length===1&&location.search.includes('run={_HISTORY_QUERY}');type.value='';state.value='';q.value='slow-query';q.dispatchEvent(new Event('input',{{bubbles:true}}));await new Promise(r=>setTimeout(r,180));type.value='EVALUATION';type.dispatchEvent(new Event('change',{{bubbles:true}}));await wait(()=>document.querySelectorAll('.run-select').length===1&&document.querySelector('.run-select')?.textContent==={json.dumps(_EVALUATION_RUNS['passed-gates'])});await new Promise(r=>setTimeout(r,350));const staleListGuard=document.querySelectorAll('.run-select').length===1&&document.querySelector('.run-select')?.textContent==={json.dumps(_EVALUATION_RUNS['passed-gates'])};[...document.querySelectorAll('button')].find(x=>x.textContent==='清除筛选').click();await wait(()=>document.querySelectorAll('.run-select').length===5);const select=id=>[...document.querySelectorAll('.run-select')].find(x=>x.textContent===id).click();select({json.dumps(_INGESTION_RUN)});select({json.dumps(_HISTORY_QUERY)});await wait(()=>document.querySelector('.run-detail-head')?.textContent.includes('QUERY'));await new Promise(r=>setTimeout(r,350));const staleDetailGuard=document.querySelector('.run-detail-head')?.textContent.includes('QUERY');const ids={json.dumps(identifiers)},matrix={{}};for(const [kind,id] of Object.entries(ids)){{select(id);await wait(()=>document.querySelector('.run-detail-head')?.textContent.includes(kind));const pane=document.querySelector('.run-detail'),links=[...pane.querySelectorAll('.run-destinations a')],buttons=[...pane.querySelectorAll('button')].map(x=>x.textContent);matrix[kind]={{trace:links.some(x=>x.textContent==='Trace'&&new URL(x.href).searchParams.get('run')===id),input:buttons.some(x=>x.startsWith('输入 ')),output:buttons.some(x=>x.startsWith('输出 ')),stop:buttons.includes('停止'),rerun:buttons.includes('重新运行'),destination:[...pane.querySelectorAll('.run-destinations a,.run-destinations span')].map(x=>x.textContent)}}}}select({json.dumps(_HISTORY_COMPARISON)});await wait(()=>document.querySelector('.run-detail-head')?.textContent.includes('COMPARISON'));const comparisonHref=[...document.querySelectorAll('.run-destinations a')].find(x=>x.textContent==='Comparison')?.href||'';return {{rehydrated,staleListGuard,staleDetailGuard,matrix,comparisonHref}}}})()"""
        result = _cdp(debug_port, script, await_promise=True, target_url=url)
        assert result["rehydrated"] is True
        assert result["staleListGuard"] is True and result["staleDetailGuard"] is True
        assert f"comparison={_COMPARISON}" in result["comparisonHref"]
        assert result["matrix"] == {
            "INGESTION": {"trace": True, "input": True, "output": True, "stop": False, "rerun": True, "destination": ["Trace", "Documents"]},
            "QUERY": {"trace": True, "input": True, "output": True, "stop": True, "rerun": False, "destination": ["Trace", "Query / Evidence"]},
            "EVALUATION": {"trace": True, "input": True, "output": True, "stop": False, "rerun": False, "destination": ["Trace", "Evaluation"]},
            "COMPARISON": {"trace": True, "input": True, "output": True, "stop": False, "rerun": False, "destination": ["Trace", "Comparison"]},
            "CONTRACT_TEST": {"trace": True, "input": True, "output": True, "stop": False, "rerun": False, "destination": ["Trace"]},
        }
        assert _cdp(debug_port, f"location.href={json.dumps(result['comparisonHref'])}; true") is True
        deep_link = """(async()=>{for(let i=0;i<160;i++){if(document.body.innerText.includes('MULTI_AXIS_NON_CAUSAL'))return {comparison:new URL(location).searchParams.get('comparison'),run:new URL(location).searchParams.get('run'),quality:document.body.innerText.includes('基准主体')};await new Promise(r=>setTimeout(r,25))}throw new Error('comparison deep link did not render')})()"""
        assert _cdp(debug_port, deep_link, await_promise=True) == {"comparison": _COMPARISON, "run": _HISTORY_COMPARISON, "quality": True}
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 for S-027 exact destination evidence",
)
def test_s027_destinations_load_exact_query_run_and_evaluation_case(tmp_path: Path) -> None:
    """Runs and Comparison links resolve the requested persisted entity and case."""
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment,
    )
    runs_url = f"http://127.0.0.1:{port}/workbench/runs?run={_HISTORY_QUERY}&q=browser-query"
    _wait_for_fixture(runs_url)
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", "--window-size=1440,900", f"--user-data-dir={tmp_path / 's027-exact'}", runs_url])
    try:
        query_href = _cdp(debug_port, """(async()=>{for(let i=0;i<160;i++){const link=[...document.querySelectorAll('.run-destinations a')].find(x=>x.textContent==='Query / Evidence');if(link)return link.href;await new Promise(r=>setTimeout(r,25))}throw new Error('Query destination unavailable')})()""", await_promise=True, target_url=runs_url)
        assert _cdp(debug_port, f"location.href={json.dumps(query_href)}; true") is True
        query_state = """(async()=>{for(let i=0;i<200;i++){if(document.querySelector('.final-state')?.innerText.includes('ANSWERED'))return {run:new URL(location).searchParams.get('run'),q:new URL(location).searchParams.get('q'),identity:document.querySelector('.query-status').textContent.includes(new URL(location).searchParams.get('run')),evidence:document.body.innerText.includes('Evidence-bound fixture answer')};await new Promise(r=>setTimeout(r,25))}throw new Error('requested Query Run did not render')})()"""
        assert _cdp(debug_port, query_state, await_promise=True) == {"run": _HISTORY_QUERY, "q": "browser-query", "identity": True, "evidence": True}

        compare_url = f"http://127.0.0.1:{port}/workbench/compare?comparison={_COMPARISON}&run={_HISTORY_COMPARISON}"
        assert _cdp(debug_port, f"location.href={json.dumps(compare_url)}; true") is True
        case_href = _cdp(debug_port, """(async()=>{for(let i=0;i<200;i++){const link=[...document.querySelectorAll('a')].find(x=>x.textContent==='案例诊断');if(link)return link.href;await new Promise(r=>setTimeout(r,25))}throw new Error('case destination unavailable')})()""", await_promise=True)
        assert _cdp(debug_port, f"location.href={json.dumps(case_href)}; true") is True
        case_state = """(async()=>{for(let i=0;i<200;i++){const selected=document.querySelector('.failed-case-row[aria-pressed="true"]');if(selected)return {run:new URL(location).searchParams.get('run'),q:new URL(location).searchParams.get('q'),comparison:new URL(location).searchParams.get('comparison'),selected:selected.dataset.case,chain:document.querySelector('.evidence-chain')?.innerText.includes('gate.answer')};await new Promise(r=>setTimeout(r,25))}throw new Error('requested Evaluation case did not render')})()"""
        assert _cdp(debug_port, case_state, await_promise=True) == {"run": _EVALUATION_RUN, "q": "qcase_0123456789abcdef", "comparison": _COMPARISON, "selected": "qcase_0123456789abcdef", "chain": True}
        missing_url = f"http://127.0.0.1:{port}/workbench/evaluation-run?run={_EVALUATION_RUN}&q=qcase_missing&comparison={_COMPARISON}"
        assert _cdp(debug_port, f"location.href={json.dumps(missing_url)}; true") is True
        assert _cdp(debug_port, """(async()=>{for(let i=0;i<200;i++){if(document.body.innerText.includes('请求案例未找到'))return !document.querySelector('.failed-case-row[aria-pressed="true"]')&&new URL(location).searchParams.get('comparison')!==null;await new Promise(r=>setTimeout(r,25))}return false})()""", await_promise=True) is True
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 for S-027 stale create evidence",
)
def test_s027_delayed_comparison_create_cannot_replace_changed_selection(tmp_path: Path) -> None:
    """Every selector change invalidates an in-flight immutable comparison create."""
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
    url = f"http://127.0.0.1:{port}/workbench/compare"
    _wait_for_fixture(url)
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", "--window-size=1440,900", f"--user-data-dir={tmp_path / 's027-create'}", url])
    try:
        result = _cdp(debug_port, f"""(async()=>{{const wait=async p=>{{for(let i=0;i<200;i++){{const value=p();if(value)return value;await new Promise(r=>setTimeout(r,25))}}throw new Error('comparison controls unavailable')}};const base=await wait(()=>document.querySelector('select[aria-label="基准 Evaluation Report"]')?.options.length===4&&document.querySelector('select[aria-label="基准 Evaluation Report"]'));base.value={json.dumps(_COMPARISON_BASELINE)};base.dispatchEvent(new Event('change',{{bubbles:true}}));const candidate=await wait(()=>document.querySelector('select[aria-label="候选 Evaluation Report"]')?.options.length===4&&!document.querySelector('select[aria-label="候选 Evaluation Report"]').disabled&&document.querySelector('select[aria-label="候选 Evaluation Report"]'));candidate.value={json.dumps(_COMPARISON_CANDIDATE)};candidate.dispatchEvent(new Event('change',{{bubbles:true}}));const create=await wait(()=>[...document.querySelectorAll('button')].find(x=>x.textContent==='创建固定比较'&&!x.disabled));create.click();const disabled=base.disabled&&candidate.disabled&&create.disabled;candidate.value={json.dumps(_COMPARISON_SINGLE)};candidate.dispatchEvent(new Event('change',{{bubbles:true}}));await new Promise(r=>setTimeout(r,450));return {{disabled,selected:candidate.value,stale:document.body.innerText.includes('MULTI_AXIS_NON_CAUSAL'),changed:document.body.innerText.includes('候选已更改'),enabled:!create.disabled}}}})()""", await_promise=True, target_url=url)
        assert result == {"disabled": True, "selected": _COMPARISON_SINGLE, "stale": False, "changed": True, "enabled": True}
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 for S-027 close/action stale evidence",
)
def test_s027_close_invalidates_pending_detail_and_recovery_actions(tmp_path: Path) -> None:
    """Closing diagnosis removes run context and blocks late Stop/rerun effects."""
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
    url = f"http://127.0.0.1:{port}/workbench/runs?run={_HISTORY_QUERY}&runType=QUERY&q=browser-query"
    _wait_for_fixture(url)
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", "--window-size=1440,900", f"--user-data-dir={tmp_path / 's027-close'}", url])
    try:
        stop = _cdp(debug_port, """(async()=>{const wait=async p=>{for(let i=0;i<200;i++){const value=p();if(value)return value;await new Promise(r=>setTimeout(r,25))}throw new Error('stop action unavailable')};const action=await wait(()=>[...document.querySelectorAll('.run-actions button')].find(x=>x.textContent==='停止'));action.click();document.querySelector('button[aria-label="关闭 Run 诊断"]').click();await new Promise(r=>setTimeout(r,450));return {run:new URL(location).searchParams.get('run'),type:new URL(location).searchParams.get('runType'),q:new URL(location).searchParams.get('q'),empty:document.body.innerText.includes('未选择 Run'),reopened:!!document.querySelector('.run-detail-head')};})()""", await_promise=True, target_url=url)
        assert stop == {"run": None, "type": "QUERY", "q": "browser-query", "empty": True, "reopened": False}
        rerun = _cdp(debug_port, f"""(async()=>{{const wait=async p=>{{for(let i=0;i<200;i++){{const value=p();if(value)return value;await new Promise(r=>setTimeout(r,25))}}throw new Error('rerun action unavailable')}};document.querySelector('select[aria-label="Run 类型"]').value='';document.querySelector('select[aria-label="Run 类型"]').dispatchEvent(new Event('change',{{bubbles:true}}));document.querySelector('input[aria-label="筛选 Run"]').value='';document.querySelector('input[aria-label="筛选 Run"]').dispatchEvent(new Event('input',{{bubbles:true}}));const row=await wait(()=>[...document.querySelectorAll('.run-select')].find(x=>x.textContent==={json.dumps(_INGESTION_RUN)}));row.click();const input=await wait(()=>document.querySelector('input[aria-label="重新运行 Profile Set ID"]'));input.value='delayed-ingestion';[...document.querySelectorAll('.run-actions button')].find(x=>x.textContent==='重新运行').click();document.querySelector('button[aria-label="关闭 Run 诊断"]').click();await new Promise(r=>setTimeout(r,450));return {{path:location.pathname,run:new URL(location).searchParams.get('run'),empty:document.body.innerText.includes('未选择 Run'),handoff:sessionStorage.getItem('kb2.rerun-preflight')}}}})()""", await_promise=True)
        assert rerun == {"path": "/workbench/runs", "run": None, "empty": True, "handoff": None}
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for browser end-to-end evidence",
)
@pytest.mark.skip(reason="Covered by the stable parameterized Query Lab workflow below.")
def test_e2e_query_submission_renders_answer_and_opens_evidence(tmp_path: Path) -> None:
    """A submitted Query Run renders its final state and follows a cited Evidence link."""
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
    url = f"http://127.0.0.1:{port}/workbench/query"
    _wait_for_fixture(url)
    browser = _launch_isolated_chrome(["--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--remote-allow-origins=*", f"--remote-debugging-port={debug_port}", "--window-size=1440,900", f"--user-data-dir={tmp_path / 'query-e2e'}", url])
    try:
        result = _cdp(debug_port, """(async()=>{const wait=async p=>{for(let i=0;i<120;i++){const x=p();if(x)return x;await new Promise(r=>setTimeout(r,25))}throw new Error('query flow did not become ready')};const question=await wait(()=>document.querySelector('textarea[aria-label="问题"]'));question.value='fixture question';[...document.querySelectorAll('button')].find(x=>x.textContent==='预检').click();const acknowledge=await wait(()=>document.querySelector('input[aria-label="确认外部阶段披露"]'));acknowledge.click();[...document.querySelectorAll('button')].find(x=>x.textContent==='创建 Query Run').click();const citation=await wait(()=>[...document.querySelectorAll('button')].find(x=>x.textContent==='cit_fixture'));citation.click();await wait(()=>document.querySelector('.artifact-inspector .source-view'));return {answered:document.body.innerText.includes('ANSWERED')&&document.body.innerText.includes('Evidence-bound fixture answer'),citation:document.body.innerText.includes('cit_fixture'),inspector:!!document.querySelector('.artifact-inspector .source-view')}})()""".replace("source-view)}})", "source-view')}})"), await_promise=True, target_url=url)
        assert result == {"answered": True, "citation": True, "inspector": True}
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for browser end-to-end evidence",
)
def test_e2e_profile_studio_loads_compatible_plugins_and_validates(tmp_path: Path) -> None:
    """Profile Studio uses the compatibility and validation APIs for an editable Profile."""
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
    url = f"http://127.0.0.1:{port}/workbench/studio"
    _wait_for_fixture(url)
    browser = _launch_isolated_chrome(["--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--remote-allow-origins=*", f"--remote-debugging-port={debug_port}", "--window-size=1440,900", f"--user-data-dir={tmp_path / 'studio-e2e'}", url])
    time.sleep(0.5)
    try:
        result = _cdp(debug_port, """(async()=>{const wait=async p=>{for(let i=0;i<120;i++){const x=p();if(x)return x;await new Promise(r=>setTimeout(r,25))}throw new Error('studio flow did not become ready')};const profile=await wait(()=>[...document.querySelectorAll('button')].find(x=>x.textContent==='browser-query'));profile.click();const plugin=await wait(()=>document.querySelector('select[aria-label="keyword 插件"]'));await wait(()=>[...plugin.options].some(x=>x.value==='retriever.keyword@1'));[...document.querySelectorAll('button')].find(x=>x.textContent==='验证').click();await wait(()=>document.body.innerText.includes('配置有效'));return {compatible:[...plugin.options].every(x=>x.value==='retriever.keyword@1'),schema:!!document.querySelector('input[aria-label="keyword limit"]'),valid:document.body.innerText.includes('配置有效')}})()""", await_promise=True, target_url=url)
        assert result == {"compatible": True, "schema": True, "valid": True}
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(
    not CHROME.exists() or os.getenv("KB2_BROWSER_TESTS") != "1",
    reason="set KB2_BROWSER_TESTS=1 with an isolated Chrome headless runtime for browser end-to-end evidence",
)
def test_e2e_comparison_submission_renders_engine_provided_bands(tmp_path: Path) -> None:
    """The browser submits pinned report IDs and displays the API comparison without recalculating it."""
    port, debug_port = _free_local_port(), _free_local_port()
    environment = {**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}:{Path.cwd()}"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.contract.test_workbench_browser:fixture_app", "--host", "127.0.0.1", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
    url = f"http://127.0.0.1:{port}/workbench/compare"
    _wait_for_fixture(url)
    browser = _launch_isolated_chrome(["--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--remote-allow-origins=*", f"--remote-debugging-port={debug_port}", "--window-size=1440,900", f"--user-data-dir={tmp_path / 'comparison-e2e'}", url])
    time.sleep(0.5)
    try:
        result = _cdp(debug_port, f"""(async()=>{{const wait=async p=>{{for(let i=0;i<160;i++){{const x=p();if(x)return x;await new Promise(r=>setTimeout(r,25))}}throw new Error('comparison flow did not become ready')}};const base=await wait(()=>document.querySelector('select[aria-label="基准 Evaluation Report"]')?.options.length===4&&document.querySelector('select[aria-label="基准 Evaluation Report"]'));base.value={json.dumps(_COMPARISON_BASELINE)};base.dispatchEvent(new Event('change',{{bubbles:true}}));const candidate=await wait(()=>document.querySelector('select[aria-label="候选 Evaluation Report"]')?.options.length===4&&!document.querySelector('select[aria-label="候选 Evaluation Report"]').disabled&&document.querySelector('select[aria-label="候选 Evaluation Report"]'));candidate.value={json.dumps(_COMPARISON_CANDIDATE)};candidate.dispatchEvent(new Event('change',{{bubbles:true}}));const submit=[...document.querySelectorAll('button')].find(x=>x.textContent==='创建固定比较');await wait(()=>!submit.disabled);submit.click();await wait(()=>document.body.innerText.includes('MULTI_AXIS_NON_CAUSAL'));return {{mode:document.body.innerText.includes('MULTI_AXIS_NON_CAUSAL'),quality:document.body.innerText.includes('UNDEFINED_BASELINE_ZERO'),bands:['质量门禁','失败案例','延迟（独立）','本地资源（独立）'].every(x=>document.body.innerText.includes(x)),recommendation:document.body.innerText.includes('CANDIDATE_ELIGIBLE')}}}})()""", await_promise=True, target_url=url)
        assert result == {"mode": True, "quality": True, "bands": True, "recommendation": True}
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)
