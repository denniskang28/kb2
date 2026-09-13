from __future__ import annotations

import base64
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
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
S022_BASELINE_ROOT = Path(__file__).parents[2] / "tests" / "visual" / "baselines" / "s022"
S022_CAPTURE = json.loads((S022_BASELINE_ROOT / "manifest.json").read_text(encoding="utf-8"))["captureConditions"]
S024_BASELINE_ROOT = Path(__file__).parents[2] / "tests" / "visual" / "baselines" / "s024"
S024_MANIFEST = json.loads((S024_BASELINE_ROOT / "manifest.json").read_text(encoding="utf-8"))
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
_ingestion_stop_requests: list[str] = []
_INGESTION_RUN = "12345678-1234-5678-1234-567812345680"
_ARTIFACT = "12345678-1234-5678-1234-567812345681"
_VISUAL_RUN = "12345678-1234-5678-1234-567812345682"
_CHUNK_ARTIFACT = "12345678-1234-5678-1234-567812345684"
_EVALUATION_DATASET = "12345678-1234-5678-1234-567812345690"
_EVALUATION_RUN = "12345678-1234-5678-1234-567812345691"
_COMPARISON = "12345678-1234-5678-1234-567812345693"
_COMPARISON_BASELINE = "12345678-1234-5678-1234-567812345694"
_COMPARISON_CANDIDATE = "12345678-1234-5678-1234-567812345695"
_HISTORY_QUERY = "12345678-1234-5678-1234-567812345696"


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
    assert await request.json() == {"workspaceProfileId": "fixture-ingestion"}
    return JSONResponse({"token": "rerun-token", "workspaceProfileId": "fixture-ingestion", "sourceArtifactId": _ARTIFACT,
                         "automatic": {"selectedProfileId": "fixture-ingestion"},
                         "disclosure": {"externalStages": []}, "stages": [], "planDigest": "e" * 64})


@fixture_app.get("/api/workbench/artifacts/{artifact_id}")
async def fixture_artifact(artifact_id: str) -> JSONResponse:
    locator_a = {"kind": "pdf", "page_number": 1, "x0": 0, "y0": 0, "x1": .5, "y1": .5}
    locator_b = {"kind": "pdf", "page_number": 1, "x0": .5, "y0": .5, "x1": 1, "y1": 1}
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
                             "cells": [{"row_index": 0, "column_index": 0, "text": "Cell fixture", "row_span": 1, "column_span": 1}]}]},
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


def _comparison_fixture() -> dict[str, object]:
    return {"schema_version": "EvaluationComparison/v1", "baseline_report_id": _COMPARISON_BASELINE,
            "candidate_report_id": _COMPARISON_CANDIDATE, "mode": "MULTI_AXIS_NON_CAUSAL",
            "axis": None, "changes": ["ingestion.plugin", "query.plugin"],
            "quality": {"deltas": [{"key": ["answer", "expected-fact-coverage"],
                         "delta": {"baseline": 0.0, "candidate": 0.2, "absolute": 0.2,
                                   "relative": None, "relative_state": "UNDEFINED_BASELINE_ZERO"}}]},
            "confidence": {"baseline": {"state": "UNAVAILABLE"}, "candidate": {"state": "VALUE", "samples": 12}},
            "gates": {"baseline": [{"gate_id": "gate.answer", "state": "FAIL"}], "candidate": []},
            "failed_cases": {"baseline": [{"case_id": "qcase_0123456789abcdef", "evidence_artifact_id": _ARTIFACT}], "candidate": []},
            "latency": {"baseline": 8, "candidate": 9},
            "resources": {"baseline": {"availability": "AVAILABLE"}, "candidate": {"availability": "PARTIAL"}},
            "recommendation": "BASELINE_RETAINED"}


@fixture_app.get("/api/workbench/comparisons/eligible")
async def fixture_comparison_eligible() -> JSONResponse:
    return JSONResponse([{"reportId": _COMPARISON_BASELINE, "runId": _EVALUATION_RUN, "manifestId": _ARTIFACT,
                          "datasetDigest": "a" * 64, "inputCatalogDigest": "b" * 64, "state": "SUCCEEDED"},
                         {"reportId": _COMPARISON_CANDIDATE, "runId": _EVALUATION_RUN, "manifestId": _ARTIFACT,
                          "datasetDigest": "a" * 64, "inputCatalogDigest": "b" * 64, "state": "SUCCEEDED"}])


@fixture_app.post("/api/workbench/comparisons")
async def fixture_comparison_create(request: Request) -> JSONResponse:
    payload = await request.json()
    if payload == {"baselineReportId": _COMPARISON_BASELINE, "candidateReportId": _COMPARISON_BASELINE}:
        return JSONResponse({"contractVersion": "workbench-problem/v1", "code": "COMPARISON_INCOMPATIBLE", "reason": "PINNED_INPUTS_NOT_EQUIVALENT"}, status_code=409)
    assert payload == {"baselineReportId": _COMPARISON_BASELINE, "candidateReportId": _COMPARISON_CANDIDATE}
    return JSONResponse({"valid": True, "runId": _EVALUATION_RUN, "artifactId": _COMPARISON,
                         "comparison": {"artifactId": _COMPARISON, "comparison": _comparison_fixture()}}, status_code=201)


@fixture_app.get("/api/workbench/runs")
async def fixture_run_history(runType: str = "", state: str = "", q: str = "") -> JSONResponse:
    rows = [{"id": _HISTORY_QUERY, "type": "QUERY", "state": "RUNNING", "terminalState": None,
             "createdAt": "2026-09-13T00:00:00Z", "startedAt": "2026-09-13T00:00:00Z", "endedAt": None,
             "planDigest": "f" * 64},
            {"id": _EVALUATION_RUN, "type": "COMPARISON", "state": "SUCCEEDED", "terminalState": "SUCCEEDED",
             "createdAt": "2026-09-12T00:00:00Z", "startedAt": "2026-09-12T00:00:00Z", "endedAt": "2026-09-12T00:01:00Z",
             "planDigest": "e" * 64}]
    return JSONResponse([row for row in rows if (not runType or row["type"] == runType) and (not state or row["state"] == state) and (not q or q.lower() in row["id"] or q.lower() in row["planDigest"])])


@fixture_app.get("/api/workbench/runs/{run_id}")
async def fixture_run_history_detail(run_id: str) -> JSONResponse:
    assert run_id == _HISTORY_QUERY
    return JSONResponse({"id": run_id, "type": "QUERY", "state": "RUNNING", "planDigest": "f" * 64,
                         "stages": [{"stageKey": "evidence", "attempt": 1, "state": "RUNNING",
                                     "artifacts": [{"id": _ARTIFACT, "artifactType": "evidence.set"}]}],
                         "actions": {"stop": True}})


@fixture_app.post("/api/workbench/query-runs/{run_id}/stop")
async def fixture_stop_query_run(run_id: str) -> JSONResponse:
    assert run_id == _HISTORY_QUERY
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

        assert _cdp(debug_port, "location.href='/workbench/documents'; true", target_url=f"http://127.0.0.1:{port}/workbench/runs?run={_VISUAL_RUN}") is True
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
    url = f"http://127.0.0.1:{port}/workbench/runs?run={_INGESTION_RUN}"
    _wait_for_fixture(f"http://127.0.0.1:{port}/workbench/runs")
    browser = _launch_isolated_chrome([*S022_CHROME_FLAGS, f"--remote-debugging-port={debug_port}", f"--window-size={width},900", f"--user-data-dir={tmp_path / 'artifact'}", url])
    try:
        _prepare_s022_capture_environment(debug_port, url, width)
        expression = """(async () => { const wait = async predicate => { for (let i = 0; i < 100; i++) { const value = predicate(); if (value) return value; await new Promise(r => setTimeout(r, 25)); } throw new Error('Artifact fixture did not become ready'); }; await wait(()=>document.querySelector('.run-tabs'));const runTabs=[...document.querySelectorAll('.run-tabs button')];runTabs.find(x=>x.textContent==='Run 指标').click();const emptyRunSignals=[...document.querySelectorAll('.run-tab-panel dd')].map(x=>x.textContent);runTabs.find(x=>x.textContent==='Profile 解析').click();const action = [...document.querySelectorAll('button')].find(x => x.textContent.includes('Artifact canonical.document')); action.click(); const sourcePane = await wait(() => document.querySelector('.artifact-inspector .source-view')); const drawer = sourcePane.closest('.artifact-inspector'); const source = sourcePane.querySelector('button'); const object = drawer.querySelector('.inspector-list button'); source.click(); const sourceSync = drawer.querySelectorAll('[data-stable-id].source-selected').length === 2; object.click(); const objectSync = drawer.querySelectorAll('[data-stable-id].source-selected').length === 2; [...drawer.querySelectorAll('[role=tab]')].find(x=>x.textContent==='表格').click();const tableSource=drawer.querySelector('.source-view button'),tableObject=drawer.querySelector('.artifact-table > button');tableSource.click();const tableSourceSync=drawer.querySelectorAll('[data-stable-id].source-selected').length===2;tableObject.click();const tableObjectSync=drawer.querySelectorAll('[data-stable-id].source-selected').length===2,summary=drawer.querySelector('.locator-summary'),tableSummary=summary?.textContent.includes('tbl_fixture / pdf / 第 1 页'),tableSummaryLive=summary?.getAttribute('aria-live')==='polite';[...drawer.querySelectorAll('[role=tab]')].find(x=>x.textContent==='Lineage').click();const lineage=drawer.innerText.includes('生产者 Run ID：12345678-1234-5678-1234-567812345680')&&drawer.innerText.includes('生产者 Plugin ID：parser.fixture@1')&&!drawer.innerText.includes('[object Object]');[...drawer.querySelectorAll('[role=tab]')].find(x=>x.textContent==='Canonical').click();drawer.querySelector('.source-view button').click(); return {sourceSync, objectSync, tableSourceSync, tableObjectSync, tableSummary, tableSummaryLive, lineage, emptyRunSignals:emptyRunSignals.length===2&&emptyRunSignals.every(x=>x==='不可用'), rawArrayAbsent:!document.body.innerText.includes('[]'), panes: !!drawer.querySelector('.inspector-list') && !!drawer.querySelector('.source-view'), overflow: document.documentElement.scrollWidth <= innerWidth, modal: innerWidth >= 900 || document.querySelector('.artifact-inspector').getAttribute('role') === 'dialog'}; })()"""
        result = _cdp(int(debug_port), expression, await_promise=True)
        assert result == {"sourceSync": True, "objectSync": True, "tableSourceSync": True, "tableObjectSync": True, "tableSummary": True, "tableSummaryLive": True, "lineage": True, "emptyRunSignals": True, "rawArrayAbsent": True, "panes": True, "overflow": True, "modal": True}
        geometry = _cdp(debug_port, f"(()=>{{const drawer=document.querySelector('.artifact-inspector'),first=drawer.querySelector('[role=tab]');first.focus();first.dispatchEvent(new KeyboardEvent('keydown',{{key:'ArrowRight',bubbles:true}}));const selected=drawer.querySelector('[role=tab][aria-selected=true]');drawer.querySelector('[role=tablist]').dispatchEvent(new KeyboardEvent('keydown',{{key:'Home',bubbles:true}}));drawer.querySelector('.source-view button').click();drawer.focus();return {{width:Math.round(drawer.getBoundingClientRect().width),inert:document.querySelector('#workbench-shell').hasAttribute('inert'),tabs:drawer.querySelectorAll('[role=tab]').length,keyboard:selected?.textContent==='结构树',rawAbsent:![...drawer.querySelectorAll('[role=tab]')].some(x=>x.textContent==='原始文本'),url:location.pathname+location.search}}}})()", target_url=url)
        assert geometry == {"width": 1080 if width >= 900 else 644, "inert": True, "tabs": 5, "keyboard": True, "rawAbsent": True, "url": f"/workbench/runs?run={_INGESTION_RUN}"}
        _assert_root_scroll_locked(debug_port, target_url=url)
        _capture_cdp(debug_port, tmp_path / f"artifact-canonical-source-{width}.png", target_url=url)
        _assert_manifest_visual(debug_port, tmp_path / f"artifact-canonical-source-{width}.png", f"artifact-canonical-source-{width}.png", target_url=url, baseline_root=S024_BASELINE_ROOT, story="S-024")
        assert _cdp(int(debug_port), "(async () => { document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true})); await new Promise(r => setTimeout(r, 30)); return {closed: !document.querySelector('.artifact-inspector'), focusReturned: document.activeElement.textContent.includes('Artifact canonical.document'),rootUnlocked:!document.documentElement.classList.contains('modal-open')&&!document.body.classList.contains('modal-open')}; })()", await_promise=True) == {"closed": True, "focusReturned": True, "rootUnlocked": True}
        chunks = """(async()=>{const wait=async p=>{for(let i=0;i<100;i++){const value=p();if(value)return value;await new Promise(r=>setTimeout(r,25))}throw new Error('Chunk inspector did not render')};const action=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('Artifact chunk.set'));action.click();const drawer=await wait(()=>document.querySelector('.artifact-inspector .source-view')?.closest('.artifact-inspector'));const citations=drawer.querySelectorAll('.inspector-list button').length===2&&drawer.querySelectorAll('.source-view button').length===2,source=drawer.querySelector('.source-view button'),object=drawer.querySelector('.inspector-list button');source.click();const sourceSync=drawer.querySelectorAll('[data-stable-id].source-selected').length===2;object.click();const objectSync=drawer.querySelectorAll('[data-stable-id].source-selected').length===2;[...drawer.querySelectorAll('[role=tab]')].find(x=>x.textContent==='元数据').click();const metadata=[...drawer.querySelectorAll('.metadata-grid dd')].map(x=>x.textContent);document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await new Promise(r=>setTimeout(r,20));return {sourceSync,objectSync,citations,metadataUnavailable:metadata.slice(-2).every(x=>x==='不可用'),closed:!document.querySelector('.artifact-inspector'),focusReturned:document.activeElement===action}})()"""
        assert _cdp(debug_port, chunks, await_promise=True, target_url=url) == {"sourceSync": True, "objectSync": True, "citations": True, "metadataUnavailable": True, "closed": True, "focusReturned": True}
        assert _cdp(int(debug_port), "window.prompt = () => 'fixture-ingestion'; [...document.querySelectorAll('button')].find(x => x.textContent === '重新运行').click(); true") is True
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

        external = """(async () => { [...document.querySelectorAll('button')].find(x => x.textContent.includes('上传并预检')).click(); const profile = document.querySelector('input[aria-label="Ingestion Profile Set ID"]'), file=document.querySelector('input[type=file]'), transfer=new DataTransfer(); transfer.items.add(new File(['%PDF-fixture'], 'fixture.pdf', {type:'application/pdf'})); Object.defineProperty(file, 'files', {value: transfer.files, configurable: true}); profile.value = 'external-ingestion'; [...document.querySelectorAll('button')].find(x => x.textContent === '预检').click(); for (let i = 0; i < 100; i++) { const checkbox = document.querySelector('input[aria-label="确认外部阶段披露"]'); const submit = [...document.querySelectorAll('button')].find(x => x.textContent === '创建新 Run'); if (checkbox && submit) { const blocked = submit.disabled; checkbox.click(); return {external: document.body.innerText.includes('parser.external@1'), blocked, enabled: !submit.disabled}; } await new Promise(r => setTimeout(r, 25)); } throw new Error('External disclosure did not render'); })()"""
        assert _cdp(int(debug_port), external, await_promise=True) == {"external": True, "blocked": True, "enabled": True}

        assert _cdp(int(debug_port), "[...document.querySelectorAll('button')].find(x => x.textContent === '创建新 Run').click(); true") is True
        for _ in range(100):
            pages = httpx.get(f"http://127.0.0.1:{debug_port}/json", timeout=1).json()
            if any(page.get("url", "").endswith(f"/workbench/runs?run={_VISUAL_RUN}") for page in pages):
                break
            time.sleep(.025)
        else:
            pytest.fail("Run receipt navigation did not occur")
        states = """(async () => { for (let i = 0; i < 100; i++) { const text = document.body.innerText, buttons = [...document.querySelectorAll('button')].map(x => x.textContent); if (text.includes('Ingestion Run') && text.includes('失败') && text.includes('已跳过') && text.includes('accepted') && text.includes('rejected') && text.includes('parser.primary@1') && text.includes('PLUGIN_TIMEOUT')) {const cards=[...document.querySelectorAll('.stage-card')],emptySignals=[...document.querySelectorAll('.stage-signal-grid dd')].map(x=>x.textContent);cards[1].click();const fallback=document.querySelector('.stage-inspector').innerText.includes('parser.fallback@1')&&document.querySelector('.stage-inspector').innerText.includes('accepted')&&document.querySelector('.stage-inspector').innerText.includes('latency_ms');cards[0].click();const root=document.documentElement;return {matrix:true, fallback, emptySignals:emptySignals.length===2&&emptySignals.every(x=>x==='不可用'), rawArrayAbsent:!document.querySelector('.stage-inspector').innerText.includes('[]'), actions:buttons.includes('停止') && buttons.includes('重新运行') && !buttons.includes('重试'), rail:cards.length===4, selected:document.querySelector('.stage-card[aria-pressed="true"]')?.innerText.includes('失败'), overflow:root.scrollWidth <= innerWidth,rootClass:root.classList.contains('modal-open'),bodyClass:document.body.classList.contains('modal-open'),rootOverflow:getComputedStyle(root).overflowY,bodyOverflow:getComputedStyle(document.body).overflowY,rootScrollbarWidth:innerWidth-root.clientWidth}; } await new Promise(r => setTimeout(r, 25)); } throw new Error('Run-state matrix did not render'); })()"""
        assert _cdp(int(debug_port), states, await_promise=True) == {"matrix": True, "fallback": True, "emptySignals": True, "rawArrayAbsent": True, "actions": True, "rail": True, "selected": True, "overflow": True, "rootClass": False, "bodyClass": False, "rootOverflow": "auto", "bodyOverflow": "auto", "rootScrollbarWidth": 0}
        run_url = f"http://127.0.0.1:{port}/workbench/runs?run={_VISUAL_RUN}"
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
        dataset = """(async()=>{const wait=async p=>{for(let i=0;i<200;i++){const v=p();if(v)return v;await new Promise(r=>setTimeout(r,25));}throw new Error('dataset did not render')};const row=await wait(()=>[...document.querySelectorAll('button')].find(x=>x.textContent.includes('r1 / 0/1')));row.click();await wait(()=>document.querySelector('textarea[aria-label=\"评估数据集 Schema\"]'));window.prompt=()=> 'fixture.reviewer';[...document.querySelectorAll('button')].find(x=>x.textContent==='标记已审核').click();return {generated:document.body.innerText.includes('待审核'),review:document.body.innerText.includes('标记已审核'),overflow:document.documentElement.scrollWidth<=innerWidth}})()"""
        assert _cdp(debug_port, dataset, await_promise=True, target_url=dataset_url) == {"generated": True, "review": True, "overflow": True}
        _capture_cdp(debug_port, tmp_path / f"evaluation-dataset-{width}.png", target_url=dataset_url)
        run_url = f"http://127.0.0.1:{port}/workbench/evaluation-run?run={_EVALUATION_RUN}"
        assert _cdp(debug_port, f"location.href='{run_url}'; true", target_url=dataset_url) is True
        run = """(async()=>{for(let i=0;i<200;i++){const text=document.body.innerText;if(text.includes('不可变 Manifest')&&text.includes('ingestion: 1 个报告')&&text.includes('质量门禁与 Judge 校准'))return {failed:text.includes('FAILED'),evidence:[...document.querySelectorAll('button')].some(x=>x.textContent==='source_artifact_id'),overflow:document.documentElement.scrollWidth<=innerWidth};await new Promise(r=>setTimeout(r,25));}throw new Error('run did not render')})()"""
        assert _cdp(debug_port, run, await_promise=True, target_url=run_url) == {"failed": True, "evidence": True, "overflow": True}
        _capture_cdp(debug_port, tmp_path / f"evaluation-run-{width}.png", target_url=run_url)
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
    browser = subprocess.Popen([str(CHROME), "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--remote-allow-origins=*", f"--remote-debugging-port={debug_port}", f"--window-size={width},900", f"--user-data-dir={tmp_path / 's027'}", compare_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        compare = """(async()=>{const wait=async p=>{for(let i=0;i<120;i++){const v=p();if(v)return v;await new Promise(r=>setTimeout(r,25));}throw new Error('comparison did not render: '+document.body.innerText)};const base=await wait(()=>{const x=document.querySelector('select[aria-label="基准 Evaluation Report"]');return x&&x.options.length===3&&x});const candidate=document.querySelector('select[aria-label="候选 Evaluation Report"]'),submit=[...document.querySelectorAll('button')].find(x=>x.textContent==='创建固定比较');base.value='12345678-1234-5678-1234-567812345694';candidate.value=base.value;submit.click();await wait(()=>document.body.innerText.includes('PINNED_INPUTS_NOT_EQUIVALENT'));const safeReason=document.body.innerText.includes('COMPARISON_INCOMPATIBLE')&&!document.body.innerText.includes('comparison inputs are not pinned-equivalent');candidate.value='12345678-1234-5678-1234-567812345695';submit.click();await wait(()=>document.body.innerText.includes('MULTI_AXIS_NON_CAUSAL'));const text=document.body.innerText,table=document.querySelector('.dense-table');return {safeReason,nonCausal:text.includes('MULTI_AXIS_NON_CAUSAL')&&!text.includes('单轴变化'),bands:text.includes('质量门禁')&&text.includes('失败案例')&&text.includes('延迟（独立）')&&text.includes('本地资源（独立）'),confidence:text.includes('UNAVAILABLE')&&text.includes('samples'),zeroBaseline:text.includes('UNDEFINED_BASELINE_ZERO'),tableScrollable:table.parentElement.scrollWidth>table.parentElement.clientWidth,overflow:document.documentElement.scrollWidth<=innerWidth,controls:[...document.querySelectorAll('main button,main select,main input')].every(x=>x.getBoundingClientRect().width>0&&x.getBoundingClientRect().height>0)}})()"""
        assert _cdp(debug_port, compare, await_promise=True, target_url=compare_url) == {"safeReason": True, "nonCausal": True, "bands": True, "confidence": True, "zeroBaseline": True, "tableScrollable": width < 900, "overflow": True, "controls": True}
        _capture_cdp(debug_port, tmp_path / f"s027-comparison-{width}.png", target_url=compare_url)

        history_url = f"http://127.0.0.1:{port}/workbench/runs?runType=QUERY&runState=RUNNING&q=12345678"
        assert _cdp(debug_port, f"location.href={json.dumps(history_url)}", target_url=compare_url) == history_url
        history = """(async()=>{const wait=async p=>{for(let i=0;i<120;i++){const v=p();if(v)return v;await new Promise(r=>setTimeout(r,25));}throw new Error('history did not render')};const trace=await wait(()=>[...document.querySelectorAll('button')].find(x=>x.textContent==='Trace'));trace.click();await wait(()=>document.body.innerText.includes('evidence.set'));const stop=[...document.querySelectorAll('button')].find(x=>x.textContent==='停止');const ownerAction=!!stop&&!document.body.innerText.includes('重新运行');stop.click();return {filters:document.querySelector('select[aria-label="Run 类型"]').value==='QUERY'&&document.querySelector('select[aria-label="Run 状态"]').value==='RUNNING',artifact:[...document.querySelectorAll('button')].some(x=>x.textContent.includes('Artifact evidence.set')),ownerAction,selected:location.search.includes('run=12345678-1234-5678-1234-567812345696')&&location.search.includes('runType=QUERY')&&location.search.includes('runState=RUNNING'),overflow:document.documentElement.scrollWidth<=innerWidth,controls:[...document.querySelectorAll('main button,main select,main input')].every(x=>x.getBoundingClientRect().width>0&&x.getBoundingClientRect().height>0)}})()"""
        assert _cdp(debug_port, history, await_promise=True, target_url=history_url) == {"filters": True, "artifact": True, "ownerAction": True, "selected": True, "overflow": True, "controls": True}
        context = """(async()=>{const wait=async p=>{for(let i=0;i<120;i++){const v=p();if(v)return v;await new Promise(r=>setTimeout(r,25));}throw new Error('context flow did not render')};const artifact=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('Artifact evidence.set'));artifact.click();await wait(()=>document.querySelector('.artifact-inspector'));const drawerPreserves=location.search.includes('run=12345678-1234-5678-1234-567812345696')&&location.search.includes('q=12345678');document.querySelector('.artifact-inspector button').click();[...document.querySelectorAll('a')].find(x=>x.textContent==='比较').click();return drawerPreserves})()"""
        assert _cdp(debug_port, context, await_promise=True) is True
        assert _cdp(debug_port, "({compare:location.pathname.endsWith('/compare'),run:new URL(location).searchParams.get('run'),type:new URL(location).searchParams.get('runType'),state:new URL(location).searchParams.get('runState'),q:new URL(location).searchParams.get('q')})") == {"compare": True, "run": _HISTORY_QUERY, "type": "QUERY", "state": "RUNNING", "q": "12345678"}
        _capture_cdp(debug_port, tmp_path / f"s027-history-{width}.png")
    finally:
        browser.terminate()
        browser.wait(timeout=10)
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
        result = _cdp(debug_port, f"""(async()=>{{const wait=async p=>{{for(let i=0;i<120;i++){{const x=p();if(x)return x;await new Promise(r=>setTimeout(r,25))}}throw new Error('comparison flow did not become ready')}};const base=await wait(()=>document.querySelector('select[aria-label="基准 Evaluation Report"]')?.options.length===3&&document.querySelector('select[aria-label="基准 Evaluation Report"]'));const candidate=document.querySelector('select[aria-label="候选 Evaluation Report"]');base.value={json.dumps(_COMPARISON_BASELINE)};candidate.value={json.dumps(_COMPARISON_CANDIDATE)};[...document.querySelectorAll('button')].find(x=>x.textContent==='创建固定比较').click();await wait(()=>document.body.innerText.includes('MULTI_AXIS_NON_CAUSAL'));return {{mode:document.body.innerText.includes('MULTI_AXIS_NON_CAUSAL'),quality:document.body.innerText.includes('UNDEFINED_BASELINE_ZERO'),bands:['质量门禁','失败案例','延迟（独立）','本地资源（独立）'].every(x=>document.body.innerText.includes(x)),recommendation:document.body.innerText.includes('BASELINE_RETAINED')}}}})()""", await_promise=True, target_url=url)
        assert result == {"mode": True, "quality": True, "bands": True, "recommendation": True}
    finally:
        _close_isolated_chrome(debug_port, browser)
        server.terminate()
        server.wait(timeout=10)
