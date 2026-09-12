from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from uuid import UUID
from uuid import uuid4

import pytest
from pydantic import ValidationError

from kb2_runtime.chunking.contracts import ChunkerConfig
from kb2_runtime.chunking.processor import process
from kb2_runtime.evidence.contracts import ContextAssemblerConfig, ContextAssemblyRequest, EvidenceSet
from kb2_runtime.evidence.local import LocalContextAssembler
from kb2_runtime.evidence.serializer import evidence_id, evidence_set_bytes
from kb2_runtime.indexing.embedding import embed_chunk_set
from kb2_runtime.indexing.hybrid import build_index
from kb2_runtime.indexing.projection import project_search_documents
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode
from kb2_runtime.plugins.bootstrap import bootstrap_registry
from kb2_runtime.plugins.contracts import RunnerType
from kb2_runtime.plugins.executor import PluginExecutor
from kb2_runtime.plugins.runner import InProcessRunner
from kb2_runtime.retrieval.contracts import IndexArtifactBinding, RetrieverConfig, RetrieverRequest
from kb2_runtime.retrieval.local import KeywordRetriever, TableRetriever
from kb2_runtime.retrieval.contracts import RetrievalCandidateSet
from kb2_runtime.retrieval.serializer import candidate_set_id, retrieval_candidate_set_bytes
from kb2_runtime.indexing.serializer import search_index_result_bytes
from kb2_runtime.trace.contracts import ArtifactManifest, SafeError


def _index(name: str = "table-heavy-canonical.json"):
    source = (Path(__file__).parents[1] / "fixtures" / "ingestion" / name).read_bytes()
    chunks = process(source, ChunkerConfig(strategy="table" if name.startswith("table") else "parent_child", max_tokens=64))
    return asyncio.run(build_index(project_search_documents(chunks, embed_chunk_set(chunks))))


def _request(index, candidate, config=ContextAssemblerConfig()):
    return ContextAssemblyRequest(candidates=candidate, index=index, index_binding=IndexArtifactBinding(id=UUID("12345678-1234-5678-1234-567812345678"), content_digest="a" * 64), configuration=config, configuration_digest="b" * 64, plugin_id="context.from-retrieval@1", implementation_digest="d" * 64)


def _candidates(index, query="revenue", table=False):
    request = RetrieverRequest(query=query, index=index, index_binding=IndexArtifactBinding(id=UUID("12345678-1234-5678-1234-567812345678"), content_digest="a" * 64), contributor_id="keyword", configuration=RetrieverConfig(limit=8), configuration_digest="b" * 64, plugin_id="retriever.keyword@1", implementation_digest="6" * 64)
    return (TableRetriever() if table else KeywordRetriever()).retrieve(request)


def test_evidence_items_are_deterministic_citation_ready_and_table_bound() -> None:
    index = _index(); candidates = _candidates(index, table=True)
    first = LocalContextAssembler().assemble(_request(index, candidates, ContextAssemblerConfig(structural_rule="table", max_items=8, max_tokens=2048, max_excerpt_chars=64)))
    second = LocalContextAssembler().assemble(_request(index, candidates, ContextAssemblerConfig(structural_rule="table", max_items=8, max_tokens=2048, max_excerpt_chars=64)))
    assert evidence_set_bytes(first) == evidence_set_bytes(second)
    assert first.items and all(item.citation_key.startswith("cit_") and item.element_ids and item.locators and len(item.excerpt) <= 64 for item in first.items)
    assert all(item.table_element_ids for item in first.items)
    assert first.source_candidate_set_id == candidates.candidate_set_id
    assert all(item.contributors[0].contributor_id == "keyword" for item in first.items)


def test_evidence_budget_shortage_and_source_validation_are_explicit() -> None:
    index = _index(); candidates = _candidates(index)
    result = LocalContextAssembler().assemble(_request(index, candidates, ContextAssemblerConfig(max_items=1, max_tokens=1, max_excerpt_chars=64, minimum_items=1)))
    assert result.items == () and result.shortage.reason == "budget_exhausted"
    assert any(item.reason == "excluded_budget" for item in result.decisions)
    forged = candidates.model_copy(update={"index_id": "idx_" + "0" * 32})
    with pytest.raises(PluginError) as raised:
        LocalContextAssembler().assemble(_request(index, forged))
    assert raised.value.code is PluginErrorCode.CONTEXT_INPUT_INVALID


def test_hierarchy_expansion_decisions_are_deterministic_and_deduplicated() -> None:
    index = _index("long-hierarchy-canonical.json")
    candidates = _candidates(index, query="child detail")
    config = ContextAssemblerConfig(
        structural_rule="hierarchy", expand_parent=True, neighbor_window=1,
        max_items=8, max_tokens=2048, max_excerpt_chars=64,
    )
    first = LocalContextAssembler().assemble(_request(index, candidates, config))
    second = LocalContextAssembler().assemble(_request(index, candidates, config))
    assert evidence_set_bytes(first) == evidence_set_bytes(second)
    assert {item.reason for item in first.decisions} >= {"included", "deduplicated"}
    assert {item.chunk_id for item in first.items} == {item.chunk_id for item in candidates.candidates}


def test_evidence_contract_rejects_duplicate_citations_and_invalid_config() -> None:
    index = _index(); result = LocalContextAssembler().assemble(_request(index, _candidates(index)))
    payload = result.model_dump(mode="json")
    payload["items"] = [payload["items"][0], payload["items"][0]]
    with pytest.raises(ValidationError):
        EvidenceSet.model_validate(payload)
    with pytest.raises(ValidationError):
        ContextAssemblerConfig(max_items=1, minimum_items=2)
    with pytest.raises(ValidationError):
        ContextAssemblerConfig(expand_parent=True)


def test_evidence_contract_rejects_a_forged_item_identity() -> None:
    index = _index()
    result = LocalContextAssembler().assemble(_request(index, _candidates(index)))
    payload = result.model_dump(mode="json")
    assert payload["items"][0]["evidence_id"] == evidence_id(payload["items"][0]["citation_key"])
    payload["items"][0]["evidence_id"] = "evd_" + "0" * 32
    with pytest.raises(ValidationError):
        EvidenceSet.model_validate(payload)
    payload = result.model_dump(mode="json")
    payload["items"][0]["citation_key"] = "cit_" + "0" * 32
    payload["items"][0]["evidence_id"] = evidence_id(payload["items"][0]["citation_key"])
    with pytest.raises(ValidationError):
        EvidenceSet.model_validate(payload)


class _Runs:
    def __init__(self) -> None: self.failures: list[SafeError] = []
    async def start_attempt(self, run_id, stage_key, *args): return uuid4(), 1
    async def fail_attempt(self, attempt_id, error, summary=""): self.failures.append(error)


class _Artifacts:
    def __init__(self) -> None: self.contents = {}; self.manifests = {}; self.commits = []
    def add(self, artifact_type, content):
        item = uuid4(); self.contents[item] = content
        self.manifests[item] = ArtifactManifest(id=item, artifact_type=artifact_type, schema_revision="v1", content_digest=hashlib.sha256(content).hexdigest(), byte_size=len(content), summary="fixture", storage_locator="sha256/fixture", producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture.source@1", configuration_digest="a" * 64)
        return item
    async def get_artifact_manifest(self, item): return self.manifests.get(item)
    async def read_content(self, item): return self.contents[item]
    async def complete_with_outputs(self, run_id, attempt_id, outputs, **kwargs):
        result = tuple(self.add(value.artifact_type, content) for value, content in outputs); self.commits.append(result); return result


def test_context_plugins_accept_each_typed_ranked_input_and_publish_evidence() -> None:
    async def exercise():
        artifacts, runs = _Artifacts(), _Runs()
        source = (Path(__file__).parents[1] / "fixtures" / "ingestion" / "table-heavy-canonical.json").read_bytes()
        chunks = process(source, ChunkerConfig(strategy="table", max_tokens=64))
        index = await build_index(project_search_documents(chunks, embed_chunk_set(chunks)))
        index_id = artifacts.add("search.index.result", search_index_result_bytes(index)); question = artifacts.add("opaque.bytes", b"revenue metrics")
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)
        keyword = (await executor.invoke(uuid4(), "keyword", "retriever.keyword@1", {"limit": 8}, (question, index_id)))[0]
        vector = (await executor.invoke(uuid4(), "vector", "retriever.vector@1", {"limit": 8}, (question, index_id)))[0]
        retrieval_evidence = (await executor.invoke(uuid4(), "context", "context.from-retrieval@1", {"max_items": 2, "max_tokens": 2048, "max_excerpt_chars": 128}, (keyword, index_id)))[0]
        fusion = (await executor.invoke(uuid4(), "fuse", "fusion.reciprocal-rank@1", {"limit": 8}, (keyword, vector)))[0]
        fusion_evidence = (await executor.invoke(uuid4(), "context", "context.from-fusion@1", {"max_items": 2, "max_tokens": 2048, "max_excerpt_chars": 128}, (fusion, index_id)))[0]
        reranked = (await executor.invoke(uuid4(), "rerank", "reranker.lexical-overlap@1", {"limit": 2}, (question, fusion, index_id)))[0]
        rerank_evidence = (await executor.invoke(uuid4(), "context", "context.from-rerank@1", {"max_items": 2, "max_tokens": 2048, "max_excerpt_chars": 128}, (reranked, index_id)))[0]
        return artifacts, runs, (retrieval_evidence, fusion_evidence, rerank_evidence)
    artifacts, runs, output_ids = asyncio.run(exercise())
    results = [EvidenceSet.model_validate_json(artifacts.contents[item]) for item in output_ids]
    assert all(result.items and result.index.id for result in results)
    assert not runs.failures


def test_context_plugin_failure_paths_never_publish_evidence() -> None:
    async def fixture():
        artifacts, runs = _Artifacts(), _Runs()
        source = (Path(__file__).parents[1] / "fixtures" / "ingestion" / "table-heavy-canonical.json").read_bytes()
        chunks = process(source, ChunkerConfig(strategy="table", max_tokens=64))
        index = await build_index(project_search_documents(chunks, embed_chunk_set(chunks)))
        index_id = artifacts.add("search.index.result", search_index_result_bytes(index))
        question = artifacts.add("opaque.bytes", b"revenue metrics")
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)
        candidates_id = (await executor.invoke(uuid4(), "keyword", "retriever.keyword@1", {"limit": 8}, (question, index_id)))[0]
        return artifacts, runs, executor, candidates_id, index_id

    async def exercise():
        artifacts, runs, executor, candidates_id, index_id = await fixture()
        candidates = RetrievalCandidateSet.model_validate_json(artifacts.contents[candidates_id])
        source_candidate = candidates.candidates[0]
        forged_locator = source_candidate.locators[0].model_copy(update={"range": "Z1:Z2"})
        malformed_candidate = source_candidate.model_copy(
            update={"locators": (forged_locator, *source_candidate.locators[1:])}
        )
        malformed_candidates = candidates.model_copy(update={"candidates": (malformed_candidate,)})
        malformed_candidates = malformed_candidates.model_copy(update={"candidate_set_id": candidate_set_id(
            malformed_candidates.index, malformed_candidates.index_id, malformed_candidates.retriever_plugin_id,
            malformed_candidates.implementation_digest, malformed_candidates.contributor_id,
            malformed_candidates.configuration_digest, malformed_candidates.filtered_count,
            malformed_candidates.candidates,
        )})
        malformed_id = artifacts.add("retrieval.candidate.set", retrieval_candidate_set_bytes(malformed_candidates))
        commits = len(artifacts.commits)
        with pytest.raises(PluginError) as malformed_error:
            await executor.invoke(uuid4(), "context", "context.from-retrieval@1", {}, (malformed_id, index_id))

        artifacts.manifests[candidates_id] = artifacts.manifests[candidates_id].model_copy(update={"content_digest": "f" * 64})
        with pytest.raises(PluginError) as stale_error:
            await executor.invoke(uuid4(), "context", "context.from-retrieval@1", {}, (candidates_id, index_id))

        cancellation = asyncio.Event(); cancellation.set()
        with pytest.raises(PluginError) as cancelled_error:
            await executor.invoke(uuid4(), "context", "context.from-retrieval@1", {}, (malformed_id, index_id), cancellation)

        unavailable = PluginExecutor(bootstrap_registry(runner_ready=lambda _: False), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)
        with pytest.raises(PluginError) as unavailable_error:
            await unavailable.invoke(uuid4(), "context", "context.from-retrieval@1", {}, (malformed_id, index_id))
        return commits, artifacts, malformed_error.value, stale_error.value, cancelled_error.value, unavailable_error.value

    commits, artifacts, malformed, stale, cancelled, unavailable = asyncio.run(exercise())
    assert malformed.code is PluginErrorCode.CONTEXT_INPUT_INVALID
    assert stale.code is PluginErrorCode.CONTEXT_INPUT_INVALID
    assert cancelled.code is PluginErrorCode.CANCELLED
    assert unavailable.code is PluginErrorCode.UNAVAILABLE
    assert len(artifacts.commits) == commits
