import asyncio
import json
from pathlib import Path
from time import monotonic
from uuid import uuid4

from kb2_runtime.evidence.contracts import ContextDecision, EvidenceItem, EvidenceScore, EvidenceSet, EvidenceShortage
from kb2_runtime.evidence.serializer import citation_key, evidence_id
from kb2_runtime.generation.contracts import FinalResponse
from kb2_runtime.indexing.contracts import EmbeddingRecord, LocalHybridConfig, SearchDocument, SearchIndexResult
from kb2_runtime.retrieval.contracts import IndexArtifactBinding, RetrievalCandidate, RetrievalCandidateSet
from kb2_runtime.query_engine import QueryEngine
from kb2_runtime.trace.contracts import ArtifactManifest, EngineKind, RunState, StageResult, StageState
from kb2_runtime.workbench.query import QueryWorkbenchService, _Preflight


def test_answer_projection_requires_evidence_bound_citations() -> None:
    response = FinalResponse(
        response_id="fin_0123456789abcdef0123456789abcdef",
        state="ANSWERED",
        evidence_artifact_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        answer="Supported answer",
        citation_keys=("cit_0123456789abcdef0123456789abcdef",),
    )
    missing = QueryWorkbenchService._final(response, [])
    present = QueryWorkbenchService._final(response, [{"citationKey": response.citation_keys[0]}])
    assert missing == {"state": "ANSWERED", "action": None, "answer": None, "citationKeys": [], "available": False}
    assert present["answer"] == "Supported answer"
    assert present["citationKeys"] == ["cit_0123456789abcdef0123456789abcdef"]
    assert QueryWorkbenchService._final(response, [{"citationKey": response.citation_keys[0]}], {str(uuid4())})["answer"] is None


def test_candidate_projection_does_not_merge_stage_sets() -> None:
    index = IndexArtifactBinding(id=uuid4(), content_digest="a" * 64)
    def candidate_set(suffix: str) -> RetrievalCandidateSet:
        candidate = RetrievalCandidate(
            candidate_id="rcd_" + suffix * 32, document_id="doc_" + "1" * 32,
            chunk_id="chk_" + suffix * 32, element_ids=("elm_" + suffix * 32,),
            locators=({"kind":"pdf","page_number":1,"x0":0,"y0":0,"x1":1,"y1":1},),
            rank=1, safe_score=.8, score_kind="fixture.normalized",
        )
        return RetrievalCandidateSet(
            candidate_set_id="rcs_" + suffix * 32, index=index, index_id="idx_" + "1" * 32,
            document_id=candidate.document_id, retriever_plugin_id="retriever.fixture@1",
            implementation_digest="b" * 64, contributor_id=f"fixture.{suffix}",
            configuration_digest="c" * 64, candidates=(candidate,),
        )
    first, second = map(QueryWorkbenchService._candidate_rows, (candidate_set("1"), candidate_set("2")))
    assert first[0]["chunkId"] == "chk_" + "1" * 32
    assert second[0]["chunkId"] == "chk_" + "2" * 32
    assert first[0]["locators"][0]["kind"] == "pdf"
    assert first[0]["contributions"] == [{"contributorId":"fixture.1","originalRank":1,"safeScore":.8,"scoreKind":"fixture.normalized"}]
    assert QueryWorkbenchService._candidate_rows({"candidates": [{"chunk_id": "untyped"}]}) == []


def test_evidence_source_resolution_walks_index_lineage_to_locator_owner() -> None:
    async def exercise() -> None:
        index_id, source_id = uuid4(), uuid4()
        locator = {"kind": "pdf", "page_number": 1, "x0": 0, "y0": 0, "x1": 1, "y1": 1}
        content = json.dumps({"elements": [{"id": "elm_fixture", "kind": "paragraph", "locator": locator, "text": "source"}], "tables": []}).encode()
        def manifest(identifier, artifact_type, parents=()):
            return ArtifactManifest(id=identifier, artifact_type=artifact_type, schema_revision="v1", content_digest="a" * 64,
                                    byte_size=1, summary="fixture", storage_locator="fixture", producing_run_id=uuid4(),
                                    producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture.source@1",
                                    configuration_digest="b" * 64, parent_artifact_ids=parents)
        class Artifacts:
            manifests = {index_id: manifest(index_id, "search.index.result", (source_id,)), source_id: manifest(source_id, "canonical.document")}
            async def get_artifact_manifest(self, identifier): return self.manifests.get(identifier)
            async def read_content(self, identifier): return content if identifier == source_id else b""
        service = QueryWorkbenchService.__new__(QueryWorkbenchService)
        service._artifacts = Artifacts()
        assert await service._source_for_evidence(index_id, [locator]) == str(source_id)
    asyncio.run(exercise())


def test_document_label_uses_registered_opaque_source_behind_inspector_artifact() -> None:
    async def exercise() -> None:
        from types import SimpleNamespace
        inspector_id, source_id = uuid4(), uuid4()
        def manifest(identifier, parents=()):
            return ArtifactManifest(id=identifier, artifact_type="canonical.document", schema_revision="v1",
                content_digest="a" * 64, byte_size=1, summary="fixture", storage_locator="fixture",
                producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture.source@1",
                configuration_digest="b" * 64, parent_artifact_ids=parents)
        class Repository:
            requested = None
            async def get_document_submissions_by_source_ids(self, ids, *, limit):
                self.requested = (tuple(ids), limit)
                return (SimpleNamespace(source_artifact_id=source_id, display_filename="已登记来源.pdf"),)
        class Artifacts:
            repository = Repository()
            manifests = {inspector_id: manifest(inspector_id, (source_id,)), source_id: manifest(source_id)}
            async def get_artifact_manifest(self, identifier): return self.manifests.get(identifier)
        service = QueryWorkbenchService.__new__(QueryWorkbenchService)
        service._artifacts = Artifacts()
        labels = await service._document_labels([str(inspector_id)])
        assert labels == {str(inspector_id): "已登记来源.pdf"}
        assert service._artifacts.repository.requested == ((inspector_id, source_id), 64)
    asyncio.run(exercise())


def test_query_preflight_appends_plan_preview_before_submit_controls() -> None:
    source = Path("src/kb2_runtime/workbench/static/workbench.js").read_text()
    assert 'class: "query-preflight"' in source
    assert 'el("h2", "已解析计划")' in source
    assert "plan.append(submit);" in source and "preview.replaceChildren(plan);" in source


def test_evidence_contributor_projection_keeps_score_and_explicit_unavailable_fallbacks() -> None:
    source = Path("src/kb2_runtime/workbench/static/workbench.js").read_text()
    assert 'c.contributor_id ?? c.contributorId ?? "不可用"' in source
    assert 'c.safe_score ?? c.safeScore ?? "不可用"' in source
    assert "贡献者 / safe_score" in source


def test_query_display_projection_is_bounded_and_friendly() -> None:
    assert QueryWorkbenchService._excerpt("  一段\n\t内容  ") == "一段 内容"
    assert QueryWorkbenchService._excerpt("甲" * 281) == "甲" * 280 + "..."
    assert QueryWorkbenchService._locator_label({
        "kind": "spreadsheet", "sheet_name": "年度预算", "cell_range": "B7:D7",
    }) == "SPREADSHEET / 工作表 年度预算 / 单元格 B7:D7"
    assert QueryWorkbenchService._locator_label({"kind": "pdf", "page_number": 3}) == "PDF / 第 3 页"
    assert QueryWorkbenchService._document_label("doc_0123456789abcdef0123456789abcdef", None, {}) == "Document 456789abcdef"


def test_candidate_rank_is_never_reconstructed_from_display_order() -> None:
    source = Path("src/kb2_runtime/workbench/static/workbench.js").read_text()
    assert 'row.rank ?? "不可用"' in source
    assert "row.rank ?? i + 1" not in source


def test_decision_path_preserves_stage_membership_without_rescoring() -> None:
    candidates = [
        {"stageId": "retrieve.keyword", "rows": [{"documentId": "doc_a", "chunkId": "chk_a", "rank": 1,
          "safeScore": .7, "contributions": [{"scoreKind": "fixture.score"}], "decision": None,
          "documentLabel": "来源.pdf", "excerpt": "原始摘录", "locatorLabel": "PDF / 第 1 页"}]},
        {"stageId": "rerank", "rows": []},
    ]
    path = QueryWorkbenchService._decision_path(candidates, [], {}, {}, {})
    assert [item["stageId"] for item in path["columns"]] == ["retrieve.keyword", "rerank", "context"]
    assert path["rows"][0]["stages"]["retrieve.keyword"] == {
        "state": "PRESENT", "rank": 1, "safeScore": .7, "scoreKind": "fixture.score",
        "contributors": [{"scoreKind": "fixture.score"}], "decision": None,
    }
    assert path["rows"][0]["stages"]["rerank"] == {"state": "NOT_PRESENT"}
    assert path["rows"][0]["stages"]["context"] == {"state": "NOT_PRESENT"}


def test_evidence_context_decisions_are_joined_by_document_and_chunk_identity() -> None:
    source = Path("src/kb2_runtime/workbench/query.py").read_text()
    assert "(value.document_id, decision.chunk_id): decision" in source
    assert "context_decisions.get((item.document_id, item.chunk_id))" in source


def test_attempt_duration_is_wall_time_and_never_negative() -> None:
    from datetime import datetime, timedelta, timezone
    started = datetime(2026, 9, 14, tzinfo=timezone.utc)
    assert QueryWorkbenchService._duration_ms(started, started + timedelta(milliseconds=17.9)) == 17
    assert QueryWorkbenchService._duration_ms(started, started - timedelta(seconds=1)) == 0
    assert QueryWorkbenchService._duration_ms(started, None) is None


def test_decision_path_context_join_uses_document_and_chunk_identity() -> None:
    from types import SimpleNamespace
    shared_chunk = "chk_" + "4" * 32
    candidates = [
        {"stageId": "first", "rows": [{"documentId": "doc_first", "chunkId": shared_chunk, "rank": 1}]},
        {"stageId": "second", "rows": [{"documentId": "doc_second", "chunkId": shared_chunk, "rank": 1}]},
    ]
    decision = SimpleNamespace(chunk_id=shared_chunk, model_dump=lambda **_: {"chunk_id": shared_chunk, "reason": "included"})
    evidence = SimpleNamespace(document_id="doc_second", decisions=(decision,))
    path = QueryWorkbenchService._decision_path(candidates, [evidence], {}, {}, {})
    by_document = {row["documentId"]: row for row in path["rows"]}
    assert by_document["doc_first"]["stages"]["context"] == {"state": "NOT_PRESENT"}
    assert by_document["doc_second"]["stages"]["context"]["reason"] == "included"


def test_run_projects_sources_only_when_every_index_binding_is_pinned() -> None:
    async def project(plan_digest: str, *, mismatch: str | None = None) -> tuple[dict, list, list, list]:
        from datetime import datetime, timezone
        from types import SimpleNamespace
        index_id, candidate_id, evidence_artifact_id, final_id, run_id = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
        digest = "a" * 64
        binding = IndexArtifactBinding(id=index_id, content_digest=digest)
        locator = {"kind": "pdf", "page_number": 2, "x0": 0, "y0": 0, "x1": 1, "y1": 1}
        document_id, chunk_id = "doc_" + "2" * 32, "chk_" + "2" * 32
        candidate = RetrievalCandidate(candidate_id="rcd_" + "2" * 32, document_id=document_id,
            chunk_id=chunk_id, element_ids=("elm_" + "2" * 32,), locators=(locator,), rank=1,
            safe_score=.8, score_kind="fixture.normalized")
        candidate_set = RetrievalCandidateSet(candidate_set_id="rcs_" + "2" * 32, index=binding,
            index_id="idx_" + "2" * 32, document_id=document_id, retriever_plugin_id="retriever.fixture@1",
            implementation_digest="b" * 64, contributor_id="fixture", configuration_digest="c" * 64,
            candidates=(candidate,))
        embedding = EmbeddingRecord(chunk_id=chunk_id, values=(1.0,) + (0.0,) * 255)
        document = SearchDocument(document_id=document_id, chunk_id=chunk_id, keyword_text="固定索引中的可信摘录",
            citations=({"element_id": "elm_" + "2" * 32, "locator": locator},), embedding=embedding)
        index = SearchIndexResult(index_id="idx_" + "2" * 32, implementation_id="fixture",
            implementation_digest="d" * 64, configuration=LocalHybridConfig(), search_document_set_digest="e" * 64,
            embedding_set_digest="f" * 64, document_count=1, term_postings={}, document_lengths={chunk_id: 1}, documents=(document,))
        element_ids = ("elm_" + "2" * 32,)
        locators = (document.citations[0].locator,)
        key = citation_key(document_id, chunk_id, element_ids, locators)
        evidence_binding = IndexArtifactBinding(
            id=uuid4() if mismatch == "evidence_identity" else index_id,
            content_digest="0" * 64 if mismatch == "evidence_digest" else digest,
        )
        evidence_item = EvidenceItem(evidence_id=evidence_id(key), citation_key=key, document_id=document_id,
            chunk_id=chunk_id, element_ids=element_ids, locators=locators, excerpt="Evidence 自报摘录",
            contributors=(EvidenceScore(contributor_id="fixture", safe_score=.8),))
        evidence_value = EvidenceSet(evidence_set_id="evs_" + "2" * 32,
            source_candidate_set_id=candidate_set.candidate_set_id, index=evidence_binding,
            index_id=index.index_id, document_id=document_id, context_plugin_id="context.fixture@1",
            implementation_digest="6" * 64, configuration_digest="5" * 64, items=(evidence_item,),
            decisions=(ContextDecision(chunk_id=chunk_id, source_rank=1, reason="included", safe_score=.8),),
            shortage=EvidenceShortage(minimum_items=1, selected_items=1, selected_tokens=4, reason="none"))
        final_value = FinalResponse(response_id="fin_" + "2" * 32, state="ANSWERED",
            evidence_artifact_id=evidence_artifact_id, answer="不应由未固定 Evidence 支持", citation_keys=(key,))
        def manifest(identifier, artifact_type, content_digest=digest):
            return ArtifactManifest(id=identifier, artifact_type=artifact_type, schema_revision="v1",
                content_digest=content_digest, byte_size=1, summary="fixture", storage_locator="fixture",
                producing_run_id=run_id, producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture.source@1",
                configuration_digest="9" * 64)
        output = manifest(candidate_id, "retrieval.candidate.set", "8" * 64)
        evidence_output = manifest(evidence_artifact_id, "evidence.set", "4" * 64)
        final_output = manifest(final_id, "final.response", "3" * 64)
        index_manifest = manifest(
            index_id,
            "canonical.document" if mismatch == "manifest_type" else "search.index.result",
            "0" * 64 if mismatch == "manifest_digest" else digest,
        )
        if mismatch == "manifest_schema":
            index_manifest = index_manifest.model_copy(update={"schema_revision": "v2"})
        now = datetime(2026, 9, 14, tzinfo=timezone.utc)
        stage = SimpleNamespace(id=uuid4(), stage_key="retrieve", attempt_number=1, state=StageState.SUCCEEDED,
            result=StageResult.SUCCEEDED, started_at=now, ended_at=now, inputs=(),
            outputs=(output, evidence_output, final_output), metrics=(),
            quality_signals=(), safe_error=None)
        trace = SimpleNamespace(id=run_id, engine_kind=EngineKind.QUERY, stages=(stage,), state=RunState.SUCCEEDED,
            terminal_state=RunState.SUCCEEDED, plan_digest="7" * 64)
        plan = {"search_artifact": {
            "artifact_id": str(uuid4() if mismatch == "identity" else index_id),
            "artifact_type": "canonical.document" if mismatch == "binding_type" else "search.index.result",
            "schema_revision": "v2" if mismatch == "binding_schema" else "v1",
            "content_digest": plan_digest,
        }, "stages": [{"stage_id": "retrieve", "plugin_id": "retriever.fixture@1"}]}
        reads, source_calls, label_calls = [], [], []
        class Runs:
            async def get_run_trace(self, _): return trace
            async def get_run_plan(self, _): return plan
        class Artifacts:
            repository = object()
            async def get_artifact_manifest(self, identifier): return index_manifest if identifier == index_id else None
        service = QueryWorkbenchService.__new__(QueryWorkbenchService)
        service._runs, service._artifacts, service._jobs = Runs(), Artifacts(), {}
        async def read(identifier, *_):
            reads.append(identifier)
            return ({candidate_id: candidate_set, evidence_artifact_id: evidence_value,
                     final_id: final_value, index_id: index}).get(identifier)
        async def source_for_evidence(identifier, locators):
            source_calls.append((identifier, locators))
            return str(uuid4())
        async def document_labels(source_ids):
            label_calls.append(tuple(source_ids))
            return {source_id: "不应泄漏.pdf" for source_id in source_ids}
        service._read = read
        service._source_for_evidence = source_for_evidence
        service._document_labels = document_labels
        return await service.run(run_id), reads, source_calls, label_calls
    matching, matching_reads, matching_sources, matching_labels = asyncio.run(project("a" * 64))
    assert matching["candidates"][0]["rows"][0]["excerpt"] == "固定索引中的可信摘录"
    assert matching["evidence"][0]["excerpt"] == "Evidence 自报摘录"
    assert matching["final"]["citationKeys"] == [matching["evidence"][0]["citationKey"]]
    assert len(matching_reads) == 4 and matching_sources and matching_labels
    mismatches = ("identity", "digest", "evidence_identity", "evidence_digest", "binding_type", "binding_schema",
                  "manifest_digest", "manifest_type", "manifest_schema")
    for mismatch in mismatches:
        projected, reads, source_calls, label_calls = asyncio.run(
            project("0" * 64 if mismatch == "digest" else "a" * 64, mismatch=mismatch)
        )
        assert len(reads) == 3
        assert projected["candidates"] == []
        assert projected["evidence"] == []
        assert projected["decisionPath"] == {"columns": [], "rows": []}
        assert all(item["kind"] != "context" for item in projected["details"])
        assert projected["final"] == {"state": "ANSWERED", "action": None, "answer": None,
                                      "citationKeys": [], "available": False}
        assert source_calls == []
        assert label_calls == []


def test_non_answered_final_states_never_project_answer_or_citations() -> None:
    for state in ("CLARIFICATION_REQUIRED", "ABSTAINED", "FAILED"):
        response = FinalResponse(
            response_id="fin_0123456789abcdef0123456789abcdef", state=state,
            evidence_artifact_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", action="Follow the recorded safe action.",
        )
        assert QueryWorkbenchService._final(response, [{"citationKey": "cit_0123456789abcdef0123456789abcdef"}]) == {
            "state": state, "action": "Follow the recorded safe action.", "answer": None,
            "citationKeys": [], "available": True,
        }


def test_expired_preflight_and_unowned_cancellation_are_safe() -> None:
    async def exercise() -> None:
        service = QueryWorkbenchService.__new__(QueryWorkbenchService)
        service._preflights = {"expired": _Preflight("question", "profile", uuid4(), monotonic() - 1)}
        service._consuming = set()
        service._jobs = {}
        try:
            await service.submit("expired", False)
        except LookupError as error:
            assert str(error) == "QUERY_PREFLIGHT_UNAVAILABLE"
        else:
            raise AssertionError("expired preflight must not submit")
        assert "expired" not in service._preflights
        assert await service.stop(uuid4()) is False
        run_id, event = uuid4(), asyncio.Event()
        service._jobs[run_id] = event
        assert await service.stop(run_id) is True and event.is_set()
    asyncio.run(exercise())


def test_successful_preflight_is_single_use_before_starting_a_new_run() -> None:
    async def exercise() -> None:
        run_id = uuid4()
        class Runner:
            async def submit(self, _plan, _question, _index, _cancellation, on_created):
                on_created(run_id)
        service = QueryWorkbenchService.__new__(QueryWorkbenchService)
        service._preflights = {"once": _Preflight("question", "profile", uuid4(), monotonic() + 60)}
        service._consuming, service._jobs, service._engine = set(), {}, Runner()
        async def resolve(*_args): return type("Plan", (), {"profile_id": "profile", "digest": "a" * 64, "canonical_payload": {}})(), None
        service._resolve = resolve
        service._stages = lambda _payload: []
        service._disclosure = lambda _stages: {"externalStages": []}
        receipt = await service.submit("once", False)
        assert receipt["runId"] == str(run_id) and "once" not in service._preflights
        try:
            await service.submit("once", False)
        except LookupError as error:
            assert str(error) == "QUERY_PREFLIGHT_UNAVAILABLE"
        else:
            raise AssertionError("consumed preflight must not create another Run")
    asyncio.run(exercise())


def test_dotted_stage_ids_use_longest_plan_match_and_frozen_order() -> None:
    plan = {"stages": [
        {"stage_id": "retrieve", "plugin_id": "retriever.base@1"},
        {"stage_id": "retrieve.table", "plugin_id": "retriever.table@1"},
        {"stage_id": "context.final", "plugin_id": "context.fixture@1"},
    ]}
    assert QueryWorkbenchService._plugin(plan, "retrieve.table.attempt-2") == "retriever.table@1"
    assert QueryWorkbenchService._plugin(plan, "context.final") == "context.fixture@1"
    keys = ["context.final", "retrieve.table.attempt-2", "query.input", "retrieve"]
    assert [key for _, key in sorted(enumerate(keys), key=lambda item: QueryWorkbenchService._stage_sort_key(plan, item[1], item[0]))] == [
        "query.input", "retrieve", "retrieve.table.attempt-2", "context.final",
    ]


def test_concurrent_submit_claims_preflight_before_recompile_await() -> None:
    async def exercise() -> None:
        run_id, entered, release = uuid4(), asyncio.Event(), asyncio.Event()
        class Runner:
            async def submit(self, _plan, _question, _index, _cancellation, on_created): on_created(run_id)
        service = QueryWorkbenchService.__new__(QueryWorkbenchService)
        service._preflights = {"once": _Preflight("question", "profile", uuid4(), monotonic() + 60)}
        service._consuming, service._jobs, service._engine = set(), {}, Runner()
        async def resolve(*_args):
            entered.set(); await release.wait()
            return type("Plan", (), {"profile_id": "profile", "digest": "a" * 64, "canonical_payload": {}})(), None
        service._resolve, service._stages, service._disclosure = resolve, lambda _payload: [], lambda _stages: {"externalStages": []}
        first = asyncio.create_task(service.submit("once", False))
        await entered.wait()
        second = await asyncio.gather(service.submit("once", False), return_exceptions=True)
        assert isinstance(second[0], LookupError) and str(second[0]) == "QUERY_PREFLIGHT_UNAVAILABLE"
        release.set()
        assert (await first)["runId"] == str(run_id)
    asyncio.run(exercise())


def test_query_engine_rejects_empty_and_oversized_question_before_creating_run() -> None:
    async def exercise() -> None:
        engine = QueryEngine(None, None, None)  # type: ignore[arg-type]
        for question in (" \t ", "x" * (8 * 1024 + 1)):
            try:
                await engine.submit(None, question, uuid4())  # type: ignore[arg-type]
            except ValueError as error:
                assert str(error) == "QUERY_QUESTION_INVALID"
            else:
                raise AssertionError("invalid query question must be rejected")
    asyncio.run(exercise())
