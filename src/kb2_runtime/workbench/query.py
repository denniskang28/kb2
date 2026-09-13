"""Server-owned Query Lab selection, submission, and trace projection."""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID, uuid4

from kb2_runtime.evidence.contracts import EvidenceSet
from kb2_runtime.fusion.contracts import FusionCandidateSet
from kb2_runtime.generation.contracts import FinalResponse, VerificationResult
from kb2_runtime.plugins.registry import PluginRegistry
from kb2_runtime.query_engine import QueryEngine
from kb2_runtime.query_profiles import QueryArtifactBinding, QueryProfileCompiler, QueryProfileParser
from kb2_runtime.reranking.contracts import RerankedCandidateSet
from kb2_runtime.retrieval.contracts import RetrievalCandidateSet
from kb2_runtime.trace.contracts import EngineKind
from kb2_runtime.trace.errors import TraceError
from kb2_runtime.trace.service import ArtifactService, RunService
from .documents import DocumentWorkbenchService


class ProfileReader(Protocol):
    async def get_profile(self, profile_id: str) -> Any: ...
    async def list_profiles(self, kind: str | None = None, query: str = "") -> Any: ...


@dataclass
class _Preflight:
    question: str
    profile_id: str
    index_id: UUID
    expires_at: float


class QueryWorkbenchService:
    def __init__(self, profiles: ProfileReader, registry: PluginRegistry, engine: QueryEngine,
                 runs: RunService, artifacts: ArtifactService, *, ttl_seconds: int = 300,
                 external_capabilities: frozenset[str] = frozenset()) -> None:
        self._profiles, self._registry, self._engine = profiles, registry, engine
        self._runs, self._artifacts, self._ttl = runs, artifacts, ttl_seconds
        self._external = external_capabilities
        self._preflights: dict[str, _Preflight] = {}
        self._consuming: set[str] = set()
        self._jobs: dict[UUID, asyncio.Event] = {}

    async def options(self) -> dict[str, Any]:
        profiles = await self._profiles.list_profiles("query")
        manifests = await self._artifacts.repository.list_artifact_manifests("search.index.result", "v1", 100)
        return {"contractVersion": "workbench-query-options/v1",
                "profiles": [{"profileId": x.profileId, "updatedAt": x.updatedAt} for x in profiles],
                "indexes": [self._artifact(x) for x in manifests]}

    async def preflight(self, question: str, profile_id: str, index_id: UUID) -> dict[str, Any]:
        plan, binding = await self._resolve(question, profile_id, index_id)
        token = uuid4().hex
        self._preflights[token] = _Preflight(question, profile_id, index_id, time.monotonic() + self._ttl)
        stages = self._stages(plan.canonical_payload)
        return {"contractVersion": "workbench-query-preflight/v1", "token": token,
                "profileId": profile_id, "index": binding.model_dump(mode="json"), "planDigest": plan.digest,
                "stages": stages, "disclosure": self._disclosure(stages)}

    async def submit(self, token: str, acknowledged: bool) -> dict[str, Any]:
        item = self._preflights.get(token)
        if item is None or token in self._consuming or item.expires_at < time.monotonic():
            self._preflights.pop(token, None)
            raise LookupError("QUERY_PREFLIGHT_UNAVAILABLE")
        # Claim before recompilation awaits so two browser requests cannot turn
        # one preflight into two immutable Runs.
        self._consuming.add(token)
        consumed = False
        try:
            plan, _ = await self._resolve(item.question, item.profile_id, item.index_id)
            disclosure = self._disclosure(self._stages(plan.canonical_payload))
            if disclosure["externalStages"] and not acknowledged:
                raise PermissionError("EXTERNAL_DISCLOSURE_REQUIRED")
            self._preflights.pop(token, None)
            consumed = True
            cancellation = asyncio.Event()
            created: asyncio.Future[UUID] = asyncio.get_running_loop().create_future()
            task = asyncio.create_task(self._engine.submit(plan, item.question, item.index_id, cancellation,
                                                            lambda run_id: not created.done() and created.set_result(run_id)))
            done, _ = await asyncio.wait({created, task}, return_when=asyncio.FIRST_COMPLETED)
            if task in done and not created.done():
                raise RuntimeError("QUERY_SUBMISSION_UNAVAILABLE")
            run_id = created.result()
            self._jobs[run_id] = cancellation
            task.add_done_callback(lambda _: self._jobs.pop(run_id, None))
            return {"contractVersion": "workbench-query-receipt/v1", "runId": str(run_id),
                    "profileId": plan.profile_id, "planDigest": plan.digest}
        finally:
            self._consuming.discard(token)
            if not consumed and token not in self._preflights:
                self._preflights[token] = item

    async def stop(self, run_id: UUID) -> bool:
        event = self._jobs.get(run_id)
        if event is None:
            return False
        event.set()
        return True

    async def run(self, run_id: UUID) -> dict[str, Any] | None:
        trace = await self._runs.get_run_trace(run_id)
        if trace is None or trace.engine_kind != EngineKind.QUERY:
            return None
        plan = await self._runs.get_run_plan(run_id)
        stages, candidates, evidence, detail, final, evidence_artifact_ids = [], [], [], [], None, set()
        ordered_rows = sorted(enumerate(trace.stages), key=lambda item: self._stage_sort_key(plan, item[1].stage_key, item[0]))
        for _, row in ordered_rows:
            stages.append({"id": str(row.id), "stageKey": row.stage_key, "attempt": row.attempt_number,
                           "state": row.state.value, "result": row.result.value if row.result else None,
                           "startedAt": row.started_at, "endedAt": row.ended_at, "pluginId": self._plugin(plan, row.stage_key),
                           "inputs": [self._artifact(x) for x in row.inputs], "outputs": [self._artifact(x) for x in row.outputs],
                           "metrics": [x.model_dump(mode="json") for x in row.metrics],
                           "quality": [x.model_dump(mode="json") for x in row.quality_signals],
                           "failure": row.safe_error.model_dump(mode="json") if row.safe_error else None})
            for output in row.outputs:
                parsed = await self._read(output.id, output.artifact_type, output.schema_revision)
                if output.artifact_type in {"retrieval.candidate.set", "fusion.candidate.set", "rerank.candidate.set"}:
                    candidates.append({"stageId": row.stage_key, "artifact": self._artifact(output), "available": parsed is not None,
                                       "rows": self._candidate_rows(parsed)})
                elif output.artifact_type == "evidence.set" and isinstance(parsed, EvidenceSet):
                    evidence_artifact_ids.add(str(output.id))
                    for item in parsed.items:
                        locators = [x.model_dump(mode="json") for x in item.locators]
                        source_id = await self._source_for_evidence(parsed.index.id, locators)
                        evidence.append({"citationKey": item.citation_key, "excerpt": item.excerpt, "documentId": item.document_id,
                        "chunkId": item.chunk_id, "elementIds": list(item.element_ids), "locators": [x.model_dump(mode="json") for x in item.locators],
                        "contributors": [x.model_dump(mode="json") for x in item.contributors], "hierarchy": list(item.hierarchy_context),
                        "tableElementIds": list(item.table_element_ids), "sourceArtifactId": source_id,
                        "sourceLocator": locators[0] if locators else None})
                    detail.append({"kind": "context", "shortage": parsed.shortage.model_dump(mode="json"),
                                   "decisions": [x.model_dump(mode="json") for x in parsed.decisions]})
                elif output.artifact_type == "verification.result" and isinstance(parsed, VerificationResult):
                    detail.append({"kind": "verification", "outcome": parsed.outcome, "failureCodes": list(parsed.failure_codes),
                                   "missingCitationKeys": list(parsed.missing_citation_keys)})
                elif output.artifact_type == "final.response" and isinstance(parsed, FinalResponse):
                    final = self._final(parsed, evidence, evidence_artifact_ids)
        return {"contractVersion": "workbench-query-run/v1", "id": str(trace.id), "state": trace.state.value,
                "terminalState": trace.terminal_state.value if trace.terminal_state else None, "planDigest": trace.plan_digest,
                "stages": stages, "candidates": candidates, "evidence": evidence, "details": detail, "final": final,
                "actions": {"stop": run_id in self._jobs and trace.state.value in {"PENDING", "RUNNING"}}}

    async def _resolve(self, question: str, profile_id: str, index_id: UUID):
        try:
            data = question.strip().encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("QUERY_QUESTION_INVALID") from exc
        if not question.strip() or len(data) > 8 * 1024:
            raise ValueError("QUERY_QUESTION_INVALID")
        saved = await self._profiles.get_profile(profile_id)
        if saved is None or saved.kind != "query":
            raise LookupError("QUERY_PROFILE_NOT_FOUND")
        manifest = await self._artifacts.get_artifact_manifest(index_id)
        if manifest is None:
            raise LookupError("QUERY_INDEX_NOT_FOUND")
        binding = QueryArtifactBinding.from_reference(manifest)
        profile_set = QueryProfileParser.parse(json.dumps(saved.document), "application/json")
        return QueryProfileCompiler(self._registry).compile(profile_set, binding).get(profile_id), binding

    async def _read(self, artifact_id: UUID, kind: str, revision: str) -> Any:
        try:
            raw = await self._artifacts.read_content(artifact_id)
            if (kind, revision) == ("evidence.set", "v1"): return EvidenceSet.model_validate_json(raw)
            if (kind, revision) == ("verification.result", "v1"): return VerificationResult.model_validate_json(raw)
            if (kind, revision) == ("final.response", "v1"): return FinalResponse.model_validate_json(raw)
            candidate_contract = {
                "retrieval.candidate.set": RetrievalCandidateSet,
                "fusion.candidate.set": FusionCandidateSet,
                "rerank.candidate.set": RerankedCandidateSet,
            }.get(kind)
            return candidate_contract.model_validate_json(raw) if candidate_contract else None
        except (TraceError, ValueError, json.JSONDecodeError):
            return None

    def _stages(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"stageId": x["stage_id"], "kind": x["kind"], "pluginId": x["plugin_id"],
                 "capabilities": list(self._registry.get(x["plugin_id"]).descriptor.capabilities)} for x in payload["stages"]]

    def _disclosure(self, stages: list[dict[str, Any]]) -> dict[str, Any]:
        external = [{"stage": x["stageId"], "capability": capability,
                     "message": "问题和 Evidence 内容可能发送到所选外部提供方。"}
                    for x in stages for capability in x["capabilities"] if capability in self._external]
        return {"externalStages": external}

    @staticmethod
    def _artifact(item: Any) -> dict[str, Any]:
        return {"id": str(item.id), "artifactType": item.artifact_type, "schemaRevision": item.schema_revision,
                "contentDigest": item.content_digest, "byteSize": item.byte_size, "summary": item.summary}

    @staticmethod
    def _candidate_rows(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, RetrievalCandidateSet):
            return [{
                "rank": item.rank, "chunkId": item.chunk_id, "safeScore": item.safe_score,
                "scoreKind": item.score_kind,
                "locators": [locator.model_dump(mode="json") for locator in item.locators],
                "contributions": [{"contributorId": value.contributor_id, "originalRank": item.rank,
                                   "safeScore": item.safe_score, "scoreKind": item.score_kind}],
            } for item in value.candidates]
        if isinstance(value, (FusionCandidateSet, RerankedCandidateSet)):
            decisions = {item.chunk_id: item for item in getattr(value, "decisions", ())}
            return [{
                "rank": item.rank, "chunkId": item.chunk_id, "safeScore": item.safe_score,
                "locators": [locator.model_dump(mode="json")
                             for contribution in item.contributions for locator in contribution.candidate.locators],
                "contributions": [{
                    "contributorId": contribution.contributor_id,
                    "originalRank": contribution.original_rank,
                    "safeScore": contribution.candidate.safe_score,
                    "scoreKind": contribution.candidate.score_kind,
                } for contribution in item.contributions],
                "decision": decisions[item.chunk_id].model_dump(mode="json") if item.chunk_id in decisions else None,
            } for item in value.candidates]
        return []

    async def _source_for_evidence(self, index_id: UUID, locators: list[dict[str, Any]]) -> str | None:
        """Find the lineage-owned inspector Artifact that actually contains a locator.

        Query stage inputs contain candidate sets, not source documents.  Walk
        only the persisted index lineage and return a source Artifact only when
        its existing inspector view proves it contains an Evidence locator.
        """
        pending, visited = [index_id], set()
        while pending and len(visited) < 64:
            artifact_id = pending.pop(0)
            if artifact_id in visited:
                continue
            visited.add(artifact_id)
            manifest = await self._artifacts.get_artifact_manifest(artifact_id)
            if manifest is None:
                continue
            if (manifest.artifact_type, manifest.schema_revision) in {("chunk.set", "v1"), ("canonical.document", "v1")}:
                try:
                    view = DocumentWorkbenchService._artifact_view(manifest.artifact_type, manifest.schema_revision,
                                                                    await self._artifacts.read_content(artifact_id))
                except (TraceError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
                    view = {"available": False}
                if self._view_has_locator(view, locators):
                    return str(artifact_id)
            pending.extend(parent for parent in manifest.parent_artifact_ids if parent not in visited)
        return None

    @staticmethod
    def _view_has_locator(view: dict[str, Any], locators: list[dict[str, Any]]) -> bool:
        requested = {json.dumps(value, sort_keys=True, separators=(",", ":")) for value in locators}
        for chunk in view.get("chunks", []):
            for citation in chunk.get("citations", []):
                if json.dumps(citation.get("locator"), sort_keys=True, separators=(",", ":")) in requested:
                    return True
        for element in view.get("elements", []):
            if json.dumps(element.get("locator"), sort_keys=True, separators=(",", ":")) in requested:
                return True
        return any(json.dumps(table.get("locator"), sort_keys=True, separators=(",", ":")) in requested
                   for table in view.get("tables", []))

    @staticmethod
    def _plugin(plan: dict[str, Any] | None, stage_key: str) -> str | None:
        if stage_key == "query.input": return "query.input@1"
        if not isinstance(plan, dict): return None
        found = QueryWorkbenchService._stage_plan_entry(plan, stage_key)
        return found.get("plugin_id") if isinstance(found, dict) else None

    @staticmethod
    def _stage_plan_entry(plan: dict[str, Any], stage_key: str) -> dict[str, Any] | None:
        matches = [item for item in plan.get("stages", []) if isinstance(item, dict)
                   and isinstance(item.get("stage_id"), str)
                   and (stage_key == item["stage_id"] or stage_key.startswith(item["stage_id"] + "."))]
        return max(matches, key=lambda item: len(item["stage_id"])) if matches else None

    @staticmethod
    def _stage_sort_key(plan: dict[str, Any] | None, stage_key: str, trace_position: int) -> tuple[int, int]:
        if stage_key == "query.input":
            return (-1, trace_position)
        if not isinstance(plan, dict):
            return (10_000, trace_position)
        entry = QueryWorkbenchService._stage_plan_entry(plan, stage_key)
        if entry is None:
            return (10_000, trace_position)
        return (next((index for index, item in enumerate(plan.get("stages", [])) if item is entry), 10_000), trace_position)

    @staticmethod
    def _final(value: FinalResponse, evidence: list[dict[str, Any]], evidence_artifact_ids: set[str] | None = None) -> dict[str, Any]:
        keys = {item["citationKey"] for item in evidence}
        binding_valid = evidence_artifact_ids is None or str(value.evidence_artifact_id) in evidence_artifact_ids
        valid = value.state == "ANSWERED" and binding_valid and bool(value.answer) and set(value.citation_keys).issubset(keys)
        return {"state": value.state, "action": value.action,
                "answer": value.answer if valid else None, "citationKeys": list(value.citation_keys) if valid else [],
                "available": valid if value.state == "ANSWERED" else True}
