import asyncio
import json
from pathlib import Path
from time import monotonic
from uuid import uuid4

from kb2_runtime.generation.contracts import FinalResponse
from kb2_runtime.query_engine import QueryEngine
from kb2_runtime.trace.contracts import ArtifactManifest
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
    first = QueryWorkbenchService._candidate_rows({"candidates": [{"chunk_id": "one"}]})
    second = QueryWorkbenchService._candidate_rows({"candidates": [{"chunk_id": "two"}]})
    assert first == [{"chunk_id": "one"}]
    assert second == [{"chunk_id": "two"}]


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


def test_query_preflight_appends_plan_preview_before_submit_controls() -> None:
    source = Path("src/kb2_runtime/workbench/static/workbench.js").read_text()
    assert "preview=el('section','',{class:'query-preflight'});preview.append(el('h2','已解析计划')" in source
    assert "surface.replaceChildren(preview)" in source


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
