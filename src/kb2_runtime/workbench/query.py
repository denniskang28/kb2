"""Server-owned Query Lab selection, submission, and trace projection."""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID, uuid4

from psycopg import Error as PsycopgError
from kb2_runtime.evidence.contracts import EvidenceSet
from kb2_runtime.fusion.contracts import FusionCandidateSet
from kb2_runtime.generation.contracts import FinalResponse, VerificationResult
from kb2_runtime.indexing.contracts import SearchIndexResult
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
                "profiles": [x.model_dump(mode="json", include={"profileId", "updatedAt"}) for x in profiles],
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
        stages, candidate_values, evidence_sets, detail, final_value, evidence_artifact_ids = [], [], [], [], None, set()
        ordered_rows = sorted(enumerate(trace.stages), key=lambda item: self._stage_sort_key(plan, item[1].stage_key, item[0]))
        for _, row in ordered_rows:
            stages.append({"id": str(row.id), "stageKey": row.stage_key, "attempt": row.attempt_number,
                           "state": row.state.value, "result": row.result.value if row.result else None,
                           "startedAt": row.started_at, "endedAt": row.ended_at,
                           "durationMs": self._duration_ms(row.started_at, row.ended_at),
                           "pluginId": self._plugin(plan, row.stage_key),
                           "inputs": [self._artifact(x) for x in row.inputs], "outputs": [self._artifact(x) for x in row.outputs],
                           "metrics": [x.model_dump(mode="json") for x in row.metrics],
                           "quality": [x.model_dump(mode="json") for x in row.quality_signals],
                           "failure": row.safe_error.model_dump(mode="json") if row.safe_error else None})
            for output in row.outputs:
                parsed = await self._read(output.id, output.artifact_type, output.schema_revision)
                if output.artifact_type in {"retrieval.candidate.set", "fusion.candidate.set", "rerank.candidate.set"}:
                    candidate_values.append((row.stage_key, self._artifact(output), parsed))
                elif output.artifact_type == "evidence.set" and isinstance(parsed, EvidenceSet):
                    evidence_artifact_ids.add(str(output.id))
                    evidence_sets.append(parsed)
                    detail.append({"kind": "context", "shortage": parsed.shortage.model_dump(mode="json"),
                                   "decisions": [x.model_dump(mode="json") for x in parsed.decisions]})
                elif output.artifact_type == "verification.result" and isinstance(parsed, VerificationResult):
                    detail.append({"kind": "verification", "outcome": parsed.outcome, "failureCodes": list(parsed.failure_codes),
                                   "missingCitationKeys": list(parsed.missing_citation_keys)})
                elif output.artifact_type == "final.response" and isinstance(parsed, FinalResponse):
                    final_value = parsed
        index_ids = {value.index.id for _, _, value in candidate_values
                     if isinstance(value, (RetrievalCandidateSet, FusionCandidateSet, RerankedCandidateSet))}
        index_ids.update(value.index.id for value in evidence_sets)
        index_id = await self._validated_index_id(plan, index_ids, candidate_values, evidence_sets)
        trusted_index = index_id is not None
        index = await self._read(index_id, "search.index.result", "v1") if index_id else None
        index = index if isinstance(index, SearchIndexResult) else None
        document_map = {(item.document_id, item.chunk_id): item for item in index.documents} if index else {}
        source_by_document: dict[str, str | None] = {}
        first_document: dict[str, Any] = {}
        for document in index.documents if index else ():
            first_document.setdefault(document.document_id, document)
        for document_id, document in first_document.items():
            locators = [citation.locator.model_dump(mode="json") for citation in document.citations[:1]]
            source_by_document[document_id] = await self._source_for_evidence(index_id, locators) if locators else None
        trusted_evidence_sets = evidence_sets if trusted_index else []
        for value in trusted_evidence_sets:
            for item in value.items:
                if item.document_id not in source_by_document:
                    locators = [x.model_dump(mode="json") for x in item.locators]
                    source_by_document[item.document_id] = await self._source_for_evidence(value.index.id, locators)
        labels = await self._document_labels(source_by_document.values()) if trusted_index else {}
        candidates = [{"stageId": stage_id, "artifact": artifact, "available": value is not None,
                       "rows": self._candidate_rows(value, document_map, source_by_document, labels)}
                      for stage_id, artifact, value in candidate_values] if trusted_index else []
        evidence = []
        context_decisions = {(value.document_id, decision.chunk_id): decision
                             for value in trusted_evidence_sets for decision in value.decisions}
        for value in trusted_evidence_sets:
            for item in value.items:
                locators = [x.model_dump(mode="json") for x in item.locators]
                source_id = source_by_document.get(item.document_id)
                decision = context_decisions.get((item.document_id, item.chunk_id))
                evidence.append({"citationKey": item.citation_key, "excerpt": item.excerpt,
                    "documentId": item.document_id, "documentLabel": self._document_label(item.document_id, source_id, labels),
                    "chunkId": item.chunk_id, "elementIds": list(item.element_ids), "locators": locators,
                    "locatorLabel": self._locator_label(locators[0] if locators else None),
                    "contributors": [x.model_dump(mode="json") for x in item.contributors], "hierarchy": list(item.hierarchy_context),
                    "tableElementIds": list(item.table_element_ids), "sourceArtifactId": source_id,
                    "sourceLocator": locators[0] if locators else None,
                    "contextDecision": decision.model_dump(mode="json") if decision else None})
        if not trusted_index:
            detail = [item for item in detail if item.get("kind") != "context"]
        final = self._final(final_value, evidence, evidence_artifact_ids if trusted_index else set()) if final_value else None
        decision_path = (self._decision_path(candidates, trusted_evidence_sets, document_map, source_by_document, labels)
                         if trusted_index else {"columns": [], "rows": []})
        return {"contractVersion": "workbench-query-run/v1", "id": str(trace.id), "state": trace.state.value,
                "terminalState": trace.terminal_state.value if trace.terminal_state else None, "planDigest": trace.plan_digest,
                "stages": stages, "candidates": candidates, "decisionPath": decision_path,
                "evidence": evidence, "details": detail, "final": final,
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
            if (kind, revision) == ("search.index.result", "v1"): return SearchIndexResult.model_validate_json(raw)
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
    def _candidate_rows(value: Any, documents: dict[tuple[str, str], Any] | None = None,
                        sources: dict[str, str | None] | None = None,
                        labels: dict[str, str] | None = None) -> list[dict[str, Any]]:
        documents, sources, labels = documents or {}, sources or {}, labels or {}
        def display(document_id: str, chunk_id: str, locators: list[dict[str, Any]]) -> dict[str, Any]:
            document = documents.get((document_id, chunk_id))
            return {"documentId": document_id,
                    "documentLabel": QueryWorkbenchService._document_label(document_id, sources.get(document_id), labels),
                    "excerpt": QueryWorkbenchService._excerpt(document.keyword_text) if document else None,
                    "locatorLabel": QueryWorkbenchService._locator_label(locators[0] if locators else None)}
        if isinstance(value, RetrievalCandidateSet):
            rows = [{
                "rank": item.rank, "chunkId": item.chunk_id, "safeScore": item.safe_score,
                "scoreKind": item.score_kind,
                "locators": [locator.model_dump(mode="json") for locator in item.locators],
                "contributions": [{"contributorId": value.contributor_id, "originalRank": item.rank,
                                   "safeScore": item.safe_score, "scoreKind": item.score_kind}],
            } for item in value.candidates]
            for row, item in zip(rows, value.candidates): row.update(display(item.document_id, item.chunk_id, row["locators"]))
            return rows
        if isinstance(value, (FusionCandidateSet, RerankedCandidateSet)):
            decisions = {item.chunk_id: item for item in getattr(value, "decisions", ())}
            rows = [{
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
            for row, item in zip(rows, value.candidates): row.update(display(item.document_id, item.chunk_id, row["locators"]))
            return rows
        return []

    async def _document_labels(self, source_ids: Any) -> dict[str, str]:
        lineage_by_owner: dict[str, tuple[UUID, ...]] = {}
        ids: list[UUID] = []
        for value in source_ids:
            if not value or value in lineage_by_owner:
                continue
            try: owner = UUID(value)
            except ValueError: continue
            lineage = await self._lineage_ids(owner)
            lineage_by_owner[value] = lineage
            ids.extend(lineage)
        lookup = getattr(getattr(self._artifacts, "repository", None), "get_document_submissions_by_source_ids", None)
        if not ids or lookup is None:
            return {}
        try:
            records = await lookup(ids, limit=64)
        except (TraceError, ValueError, RuntimeError, PsycopgError):
            return {}
        registered = {item.source_artifact_id: item.display_filename for item in records}
        return {owner: next((registered[item] for item in lineage if item in registered), "")
                for owner, lineage in lineage_by_owner.items()}

    async def _validated_index_id(self, plan: dict[str, Any] | None, index_ids: set[UUID],
                                  candidate_values: list[tuple[str, dict[str, Any], Any]],
                                  evidence_sets: list[EvidenceSet]) -> UUID | None:
        binding = plan.get("search_artifact") if isinstance(plan, dict) else None
        if not isinstance(binding, dict) or len(index_ids) != 1:
            return None
        try:
            pinned_id = UUID(binding["artifact_id"])
        except (KeyError, TypeError, ValueError):
            return None
        digest = binding.get("content_digest")
        if (pinned_id not in index_ids or not isinstance(digest, str)
                or binding.get("artifact_type") != "search.index.result"
                or binding.get("schema_revision") != "v1"):
            return None
        values = [value for _, _, value in candidate_values
                  if isinstance(value, (RetrievalCandidateSet, FusionCandidateSet, RerankedCandidateSet))]
        values.extend(evidence_sets)
        if any(value.index.id != pinned_id or value.index.content_digest != digest for value in values):
            return None
        manifest = await self._artifacts.get_artifact_manifest(pinned_id)
        if (manifest is None or manifest.id != pinned_id or manifest.content_digest != digest
                or manifest.artifact_type != "search.index.result" or manifest.schema_revision != "v1"):
            return None
        return pinned_id

    async def _lineage_ids(self, artifact_id: UUID) -> tuple[UUID, ...]:
        pending, visited = [artifact_id], []
        while pending and len(visited) < 64:
            current = pending.pop(0)
            if current in visited:
                continue
            visited.append(current)
            manifest = await self._artifacts.get_artifact_manifest(current)
            if manifest:
                pending.extend(parent for parent in manifest.parent_artifact_ids if parent not in visited)
        return tuple(visited)

    @staticmethod
    def _document_label(document_id: str, source_id: str | None, labels: dict[str, str]) -> str:
        return labels.get(source_id or "") or f"Document {document_id[-12:]}"

    @staticmethod
    def _excerpt(value: str, limit: int = 280) -> str:
        normalized = re.sub(r"\s+", " ", value).strip()
        return normalized if len(normalized) <= limit else normalized[:limit].rstrip() + "..."

    @staticmethod
    def _locator_label(locator: dict[str, Any] | None) -> str:
        if not locator:
            return "定位不可用"
        parts: list[str] = []
        kind = locator.get("kind")
        if kind: parts.append(str(kind).upper())
        for key, prefix in (("page_number", "第 {} 页"), ("slide_number", "第 {} 张"),
                            ("sheet_name", "工作表 {}"), ("cell_range", "单元格 {}"),
                            ("range", "范围 {}"), ("paragraph_number", "第 {} 段"),
                            ("line_number", "第 {} 行"), ("table_id", "表格 {}"), ("cell_id", "单元格 {}")):
            if locator.get(key) is not None: parts.append(prefix.format(locator[key]))
        path = locator.get("heading_path") or locator.get("section_path")
        if isinstance(path, (list, tuple)) and path: parts.append(" / ".join(str(x) for x in path[:4]))
        return " / ".join(parts[:6]) or f"{kind or '未知'} Locator"

    @staticmethod
    def _duration_ms(started_at: Any, ended_at: Any) -> int | None:
        return max(0, int((ended_at - started_at).total_seconds() * 1000)) if started_at and ended_at else None

    @staticmethod
    def _decision_path(candidates: list[dict[str, Any]], evidence_sets: list[EvidenceSet],
                       documents: dict[tuple[str, str], Any], sources: dict[str, str | None],
                       labels: dict[str, str]) -> dict[str, Any]:
        columns = [{"stageId": item["stageId"], "kind": "candidate"} for item in candidates]
        columns.append({"stageId": "context", "kind": "context"})
        rows: dict[tuple[str, str], dict[str, Any]] = {}
        order: list[tuple[str, str]] = []
        for candidate_set in candidates:
            for item in candidate_set["rows"]:
                key = (item.get("documentId") or "UNRESOLVED", item.get("chunkId") or "UNRESOLVED")
                if key not in rows:
                    rows[key] = {"documentId": key[0], "chunkId": key[1], "documentLabel": item.get("documentLabel"),
                                 "excerpt": item.get("excerpt"), "locatorLabel": item.get("locatorLabel"), "stages": {}}
                    order.append(key)
                rows[key]["stages"][candidate_set["stageId"]] = {"state": "PRESENT", "rank": item.get("rank"),
                    "safeScore": item.get("safeScore"), "scoreKind": next((x.get("scoreKind") for x in item.get("contributions", []) if x.get("scoreKind")), None),
                    "contributors": item.get("contributions", []), "decision": item.get("decision")}
        for evidence_set in evidence_sets:
            for decision in evidence_set.decisions:
                key = (evidence_set.document_id, decision.chunk_id)
                if key not in rows:
                    document = documents.get(key)
                    locators = [x.locator.model_dump(mode="json") for x in document.citations[:1]] if document else []
                    rows[key] = {"documentId": key[0], "chunkId": key[1],
                        "documentLabel": QueryWorkbenchService._document_label(key[0], sources.get(key[0]), labels),
                        "excerpt": QueryWorkbenchService._excerpt(document.keyword_text) if document else None,
                        "locatorLabel": QueryWorkbenchService._locator_label(locators[0] if locators else None), "stages": {}}
                    order.append(key)
                rows[key]["stages"]["context"] = {"state": "PRESENT", **decision.model_dump(mode="json")}
        for row in rows.values():
            for column in columns: row["stages"].setdefault(column["stageId"], {"state": "NOT_PRESENT"})
        return {"columns": columns, "rows": [rows[key] for key in order]}

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
