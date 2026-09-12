from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from kb2_runtime.chunking.contracts import ChunkerConfig
from kb2_runtime.chunking.processor import process
from kb2_runtime.fusion.contracts import FusionCandidateSet
from kb2_runtime.indexing.embedding import embed_chunk_set
from kb2_runtime.indexing.hybrid import build_index
from kb2_runtime.indexing.projection import project_search_documents
from kb2_runtime.indexing.serializer import search_index_result_bytes
from kb2_runtime.plugins.bootstrap import bootstrap_registry
from kb2_runtime.plugins.bootstrap import FUSION_RRF_DESCRIPTOR, RERANKER_LEXICAL_DESCRIPTOR
from kb2_runtime.plugins.contracts import RunnerType
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode
from kb2_runtime.plugins.executor import PluginExecutor
from kb2_runtime.plugins.runner import InProcessRunner
from kb2_runtime.plugins.registry import PluginRegistry
from kb2_runtime.fusion.contracts import FusionConfig
from kb2_runtime.fusion.local import ReciprocalRankFusion
from kb2_runtime.fusion.plugin import FusionPlugin
from kb2_runtime.reranking.contracts import RerankerConfig
from kb2_runtime.reranking.local import LexicalOverlapReranker
from kb2_runtime.reranking.plugin import RerankingPlugin
from kb2_runtime.reranking.contracts import RerankedCandidateSet
from kb2_runtime.trace.contracts import ArtifactManifest, SafeError


class Runs:
    def __init__(self) -> None: self.failures: list[SafeError] = []
    async def start_attempt(self, run_id: UUID, stage_key: str, *args) -> tuple[UUID, int]: return uuid4(), 1
    async def fail_attempt(self, attempt_id: UUID, error: SafeError, summary: str = "") -> None: self.failures.append(error)


class Artifacts:
    def __init__(self) -> None: self.contents: dict[UUID, bytes] = {}; self.manifests = {}; self.commits = []
    def add(self, artifact_type: str, content: bytes, digest: str | None = None) -> UUID:
        item = uuid4(); self.contents[item] = content
        self.manifests[item] = ArtifactManifest(id=item, artifact_type=artifact_type, schema_revision="v1", content_digest=digest or hashlib.sha256(content).hexdigest(), byte_size=len(content), summary="fixture", storage_locator="sha256/fixture", producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture.source@1", configuration_digest="a" * 64)
        return item
    async def get_artifact_manifest(self, item: UUID): return self.manifests.get(item)
    async def read_content(self, item: UUID) -> bytes: return self.contents[item]
    async def complete_with_outputs(self, run_id, attempt_id, outputs, **kwargs):
        identifiers = tuple(self.add(value.artifact_type, content) for value, content in outputs); self.commits.append(identifiers); return identifiers


async def index_bytes() -> bytes:
    source = (Path(__file__).parents[1] / "fixtures" / "ingestion" / "table-heavy-canonical.json").read_bytes()
    chunks = process(source, ChunkerConfig(strategy="table", max_tokens=64))
    return search_index_result_bytes(await build_index(project_search_documents(chunks, embed_chunk_set(chunks))))


def test_fusion_and_rerank_preserve_attribution_and_upstream_bytes() -> None:
    async def exercise():
        artifacts, runs = Artifacts(), Runs(); index = await index_bytes(); index_id = artifacts.add("search.index.result", index); question_id = artifacts.add("opaque.bytes", b"revenue metrics")
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        keyword = (await executor.invoke(uuid4(), "keyword", "retriever.keyword@1", {"limit": 8}, (question_id, index_id)))[0]
        vector = (await executor.invoke(uuid4(), "vector", "retriever.vector@1", {"limit": 8}, (question_id, index_id)))[0]
        original = (artifacts.contents[keyword], artifacts.contents[vector])
        fused_id = (await executor.invoke(uuid4(), "fuse", "fusion.reciprocal-rank@1", {"limit": 8}, (keyword, vector)))[0]
        reranked_id = (await executor.invoke(uuid4(), "rerank", "reranker.lexical-overlap@1", {"limit": 1}, (question_id, fused_id, index_id)))[0]
        return artifacts, runs, original, keyword, vector, fused_id, reranked_id
    artifacts, runs, original, keyword, vector, fused_id, reranked_id = asyncio.run(exercise())
    fused = FusionCandidateSet.model_validate_json(artifacts.contents[fused_id]); reranked = RerankedCandidateSet.model_validate_json(artifacts.contents[reranked_id])
    assert all(len(item.contributions) == 2 for item in fused.candidates)
    assert [item.rank for item in fused.candidates] == list(range(1, len(fused.candidates) + 1))
    assert [item.reason for item in reranked.decisions].count("included") == min(1, len(fused.candidates))
    assert original == (artifacts.contents[keyword], artifacts.contents[vector])
    assert not runs.failures


def test_fusion_rejects_mixed_or_cancelled_inputs_without_publication() -> None:
    async def exercise():
        artifacts, runs = Artifacts(), Runs(); first_index = artifacts.add("search.index.result", await index_bytes()); second_index = artifacts.add("search.index.result", await index_bytes()); question = artifacts.add("opaque.bytes", b"revenue")
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)
        first = (await executor.invoke(uuid4(), "first", "retriever.keyword@1", {"limit": 2}, (question, first_index)))[0]
        second = (await executor.invoke(uuid4(), "second", "retriever.vector@1", {"limit": 2}, (question, second_index)))[0]
        commits = len(artifacts.commits)
        with pytest.raises(PluginError) as mixed: await executor.invoke(uuid4(), "fuse", "fusion.reciprocal-rank@1", {}, (first, second))
        cancelled = asyncio.Event(); cancelled.set()
        with pytest.raises(PluginError) as cancelled_error: await executor.invoke(uuid4(), "fuse", "fusion.reciprocal-rank@1", {}, (first,), cancelled)
        return artifacts, runs, commits, mixed.value, cancelled_error.value
    artifacts, runs, commits, mixed, cancelled = asyncio.run(exercise())
    assert mixed.code is PluginErrorCode.FUSION_INPUT_INVALID and cancelled.code is PluginErrorCode.CANCELLED
    assert len(artifacts.commits) == commits and len(runs.failures) == 2


def test_rerank_contract_requires_a_decision_for_every_fused_candidate() -> None:
    async def exercise():
        artifacts, runs = Artifacts(), Runs()
        index = await index_bytes()
        index_id = artifacts.add("search.index.result", index)
        question_id = artifacts.add("opaque.bytes", b"revenue metrics")
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        keyword = (await executor.invoke(uuid4(), "keyword", "retriever.keyword@1", {"limit": 8}, (question_id, index_id)))[0]
        vector = (await executor.invoke(uuid4(), "vector", "retriever.vector@1", {"limit": 8}, (question_id, index_id)))[0]
        fused_id = (await executor.invoke(uuid4(), "fuse", "fusion.reciprocal-rank@1", {"limit": 8}, (keyword, vector)))[0]
        reranked_id = (await executor.invoke(uuid4(), "rerank", "reranker.lexical-overlap@1", {"limit": 1}, (question_id, fused_id, index_id)))[0]
        return artifacts.contents[reranked_id]

    payload = RerankedCandidateSet.model_validate_json(asyncio.run(exercise())).model_dump(mode="json")
    assert len(payload["decisions"]) > 1

    with pytest.raises(ValidationError):
        RerankedCandidateSet.model_validate({**payload, "decisions": payload["decisions"][:-1]})


def test_reranker_rejects_a_fused_artifact_with_a_stale_content_digest() -> None:
    async def exercise():
        artifacts, runs = Artifacts(), Runs()
        index = await index_bytes()
        index_id = artifacts.add("search.index.result", index)
        question_id = artifacts.add("opaque.bytes", b"revenue metrics")
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        keyword = (await executor.invoke(uuid4(), "keyword", "retriever.keyword@1", {"limit": 8}, (question_id, index_id)))[0]
        vector = (await executor.invoke(uuid4(), "vector", "retriever.vector@1", {"limit": 8}, (question_id, index_id)))[0]
        fused_id = (await executor.invoke(uuid4(), "fuse", "fusion.reciprocal-rank@1", {"limit": 8}, (keyword, vector)))[0]
        artifacts.contents[fused_id] += b" "
        commits = len(artifacts.commits)
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "rerank", "reranker.lexical-overlap@1", {"limit": 1}, (question_id, fused_id, index_id))
        return artifacts, runs, commits, raised.value

    artifacts, runs, commits, error = asyncio.run(exercise())
    assert error.code is PluginErrorCode.RERANK_INPUT_INVALID
    assert len(artifacts.commits) == commits
    assert [failure.code.value for failure in runs.failures] == [PluginErrorCode.RERANK_INPUT_INVALID.value]


def test_reranker_rejects_a_digest_consistent_fused_artifact_with_forged_identity() -> None:
    async def exercise():
        artifacts, runs = Artifacts(), Runs(); index = await index_bytes(); index_id = artifacts.add("search.index.result", index); question_id = artifacts.add("opaque.bytes", b"revenue metrics")
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        keyword = (await executor.invoke(uuid4(), "keyword", "retriever.keyword@1", {"limit": 8}, (question_id, index_id)))[0]
        vector = (await executor.invoke(uuid4(), "vector", "retriever.vector@1", {"limit": 8}, (question_id, index_id)))[0]
        fused_id = (await executor.invoke(uuid4(), "fuse", "fusion.reciprocal-rank@1", {"limit": 8}, (keyword, vector)))[0]
        payload = FusionCandidateSet.model_validate_json(artifacts.contents[fused_id]).model_dump(mode="json"); payload["candidate_set_id"] = "fcs_" + "0" * 32
        content = __import__("json").dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        artifacts.contents[fused_id] = content; artifacts.manifests[fused_id] = artifacts.manifests[fused_id].model_copy(update={"content_digest": hashlib.sha256(content).hexdigest(), "byte_size": len(content)})
        commits = len(artifacts.commits)
        with pytest.raises(PluginError) as raised: await executor.invoke(uuid4(), "rerank", "reranker.lexical-overlap@1", {"limit": 1}, (question_id, fused_id, index_id))
        return artifacts, runs, commits, raised.value
    artifacts, runs, commits, error = asyncio.run(exercise())
    assert error.code is PluginErrorCode.RERANK_INPUT_INVALID and len(artifacts.commits) == commits
    assert [failure.code.value for failure in runs.failures] == [PluginErrorCode.RERANK_INPUT_INVALID.value]


def test_fusion_and_reranker_reject_forged_compatible_port_results() -> None:
    class ForgedFusion:
        def fuse(self, request): return ReciprocalRankFusion().fuse(request).model_copy(update={"candidate_set_id": "fcs_" + "0" * 32})
    class ForgedReranker:
        def rerank(self, request): return LexicalOverlapReranker().rerank(request).model_copy(update={"candidate_set_id": "rrs_" + "0" * 32})
    async def exercise():
        artifacts, runs = Artifacts(), Runs(); index = await index_bytes(); index_id = artifacts.add("search.index.result", index); question = artifacts.add("opaque.bytes", b"revenue metrics")
        base = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        keyword = (await base.invoke(uuid4(), "keyword", "retriever.keyword@1", {"limit": 8}, (question, index_id)))[0]; vector = (await base.invoke(uuid4(), "vector", "retriever.vector@1", {"limit": 8}, (question, index_id)))[0]
        fusion_registry = PluginRegistry(lambda _: True, lambda _: True); fusion_descriptor = FUSION_RRF_DESCRIPTOR.model_copy(update={"plugin_id": "fusion.forged@1"}); fusion_registry.register(fusion_descriptor, lambda: FusionPlugin(ForgedFusion()), FusionConfig)
        forged_fusion = PluginExecutor(fusion_registry, {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)
        before = len(artifacts.commits)
        with pytest.raises(PluginError) as fusion_error: await forged_fusion.invoke(uuid4(), "fuse", "fusion.forged@1", {}, (keyword, vector))
        fused = (await base.invoke(uuid4(), "fuse", "fusion.reciprocal-rank@1", {}, (keyword, vector)))[0]
        rerank_registry = PluginRegistry(lambda _: True, lambda _: True); rerank_descriptor = RERANKER_LEXICAL_DESCRIPTOR.model_copy(update={"plugin_id": "reranker.forged@1"}); rerank_registry.register(rerank_descriptor, lambda: RerankingPlugin(ForgedReranker()), RerankerConfig)
        forged_rerank = PluginExecutor(rerank_registry, {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)
        with pytest.raises(PluginError) as rerank_error: await forged_rerank.invoke(uuid4(), "rerank", "reranker.forged@1", {}, (question, fused, index_id))
        return artifacts, runs, before, fusion_error.value, rerank_error.value
    artifacts, runs, before, fusion_error, rerank_error = asyncio.run(exercise())
    assert fusion_error.code is PluginErrorCode.FUSION_CANDIDATE_INVALID and rerank_error.code is PluginErrorCode.RERANK_CANDIDATE_INVALID
    assert len(artifacts.commits) == before + 1


def test_fusion_unavailability_and_timeout_publish_no_output() -> None:
    class SlowFusion:
        async def invoke(self, context): await asyncio.sleep(0.1)
    async def exercise():
        artifacts, runs = Artifacts(), Runs(); unavailable = PluginExecutor(bootstrap_registry(runner_ready=lambda _: False), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)
        with pytest.raises(PluginError) as unavailable_error: await unavailable.invoke(uuid4(), "fuse", "fusion.reciprocal-rank@1", {}, ())
        source = artifacts.add("retrieval.candidate.set", b"{}")
        registry = PluginRegistry(lambda _: True, lambda _: True); descriptor = FUSION_RRF_DESCRIPTOR.model_copy(update={"plugin_id": "fusion.slow@1", "timeout_seconds": 0.001}); registry.register(descriptor, SlowFusion, FusionConfig)
        timed = PluginExecutor(registry, {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)
        with pytest.raises(PluginError) as timeout_error: await timed.invoke(uuid4(), "fuse", "fusion.slow@1", {}, (source,))
        return artifacts, runs, unavailable_error.value, timeout_error.value
    artifacts, runs, unavailable_error, timeout_error = asyncio.run(exercise())
    assert unavailable_error.code is PluginErrorCode.UNAVAILABLE and timeout_error.code is PluginErrorCode.TIMEOUT
    assert artifacts.commits == [] and [item.code.value for item in runs.failures] == [PluginErrorCode.UNAVAILABLE.value, PluginErrorCode.TIMEOUT.value]


def test_fusion_rejects_malformed_and_nonfinite_candidate_content_without_publication() -> None:
    async def exercise():
        artifacts, runs = Artifacts(), Runs(); index = await index_bytes(); index_id = artifacts.add("search.index.result", index); question = artifacts.add("opaque.bytes", b"revenue metrics")
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        valid = (await executor.invoke(uuid4(), "keyword", "retriever.keyword@1", {"limit": 8}, (question, index_id)))[0]
        malformed = artifacts.add("retrieval.candidate.set", b"{}")
        payload = json.loads(artifacts.contents[valid]); payload["candidates"][0]["safe_score"] = float("nan")
        nonfinite_content = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        nonfinite = artifacts.add("retrieval.candidate.set", nonfinite_content)
        commits = len(artifacts.commits)
        with pytest.raises(PluginError) as malformed_error: await executor.invoke(uuid4(), "fuse", "fusion.reciprocal-rank@1", {}, (malformed,))
        with pytest.raises(PluginError) as nonfinite_error: await executor.invoke(uuid4(), "fuse", "fusion.reciprocal-rank@1", {}, (nonfinite,))
        return artifacts, runs, commits, malformed_error.value, nonfinite_error.value
    artifacts, runs, commits, malformed_error, nonfinite_error = asyncio.run(exercise())
    assert malformed_error.code is PluginErrorCode.FUSION_INPUT_INVALID and nonfinite_error.code is PluginErrorCode.FUSION_INPUT_INVALID
    assert len(artifacts.commits) == commits
    assert [item.code.value for item in runs.failures] == [PluginErrorCode.FUSION_INPUT_INVALID.value, PluginErrorCode.FUSION_INPUT_INVALID.value]
