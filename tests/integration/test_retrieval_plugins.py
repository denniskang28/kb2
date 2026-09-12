from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from kb2_runtime.chunking.contracts import ChunkerConfig
from kb2_runtime.chunking.processor import process
from kb2_runtime.indexing.embedding import embed_chunk_set
from kb2_runtime.indexing.hybrid import build_index
from kb2_runtime.indexing.projection import project_search_documents
from kb2_runtime.indexing.serializer import search_index_result_bytes
from kb2_runtime.plugins.bootstrap import RETRIEVER_KEYWORD_DESCRIPTOR, bootstrap_registry
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode
from kb2_runtime.plugins.executor import PluginExecutor
from kb2_runtime.plugins.registry import PluginRegistry
from kb2_runtime.plugins.runner import InProcessRunner
from kb2_runtime.plugins.contracts import RunnerType
from kb2_runtime.retrieval.contracts import IndexArtifactBinding, RetrievalCandidateSet, RetrieverConfig
from kb2_runtime.retrieval.local import KeywordRetriever
from kb2_runtime.retrieval.plugin import RetrievalPlugin
from kb2_runtime.trace.contracts import ArtifactManifest, SafeError


class Runs:
    def __init__(self) -> None: self.failures: list[SafeError] = []
    async def start_attempt(self, run_id: UUID, stage_key: str, *args) -> tuple[UUID, int]: return uuid4(), 1
    async def fail_attempt(self, attempt_id: UUID, error: SafeError, summary: str = "") -> None: self.failures.append(error)


class Artifacts:
    def __init__(self) -> None: self.contents = {}; self.manifests = {}; self.commits = []; self.output_observability = []
    def add(self, artifact_type: str, content: bytes, digest: str | None = None) -> UUID:
        artifact_id = uuid4(); self.contents[artifact_id] = content
        self.manifests[artifact_id] = ArtifactManifest(id=artifact_id, artifact_type=artifact_type, schema_revision="v1", content_digest=digest or hashlib.sha256(content).hexdigest(), byte_size=len(content), summary="fixture", storage_locator="sha256/fixture", producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture.source@1", configuration_digest="a" * 64)
        return artifact_id
    async def get_artifact_manifest(self, artifact_id: UUID): return self.manifests.get(artifact_id)
    async def read_content(self, artifact_id: UUID) -> bytes: return self.contents[artifact_id]
    async def complete_with_outputs(self, run_id, attempt_id, outputs, **kwargs):
        identifiers = tuple(self.add(item.artifact_type, content) for item, content in outputs)
        self.commits.append(identifiers)
        self.output_observability.extend((item.metrics, item.quality_signals) for item, _ in outputs)
        return identifiers


async def search_index() -> bytes:
    source = (Path(__file__).parents[1] / "fixtures" / "ingestion" / "table-heavy-canonical.json").read_bytes()
    chunks = process(source, ChunkerConfig(strategy="table", max_tokens=64))
    return search_index_result_bytes(await build_index(project_search_documents(chunks, embed_chunk_set(chunks))))


def test_all_registered_retrievers_publish_separate_candidate_artifacts_with_trace_metrics() -> None:
    async def exercise():
        artifacts, runs = Artifacts(), Runs(); index_content = await search_index(); index_id = artifacts.add("search.index.result", index_content); question_id = artifacts.add("opaque.bytes", b"revenue metrics")
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        output_ids = []
        for number, plugin_id in enumerate(("retriever.keyword@1", "retriever.vector@1", "retriever.hierarchy@1", "retriever.table@1", "retriever.metadata@1")):
            output_ids.extend(await executor.invoke(uuid4(), f"retrieve_{number}", plugin_id, {"limit": 2}, (question_id, index_id)))
        return artifacts, runs, output_ids, index_content
    artifacts, runs, output_ids, index_content = asyncio.run(exercise())
    values = [RetrievalCandidateSet.model_validate_json(artifacts.contents[item]) for item in output_ids]
    assert len(output_ids) == 5 and all(artifacts.manifests[item].artifact_type == "retrieval.candidate.set" for item in output_ids)
    assert len({item.retriever_plugin_id for item in values}) == 5 and all(item.index.content_digest == hashlib.sha256(index_content).hexdigest() for item in values)
    assert all({item.name for item in metrics} == {"retrieval_candidates", "retrieval_filtered", "retrieval_duration_ms"} for metrics, _ in artifacts.output_observability)
    assert all({item.name for item in signals} == {"retrieval_validation", "retrieval_strategy", "no_candidates"} for _, signals in artifacts.output_observability)
    assert not runs.failures


def test_stale_index_and_cancelled_retrieval_publish_no_candidate_artifact() -> None:
    async def exercise():
        artifacts, runs = Artifacts(), Runs(); stale = artifacts.add("search.index.result", await search_index(), "f" * 64); question = artifacts.add("opaque.bytes", b"revenue")
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)
        with pytest.raises(PluginError) as stale_error:
            await executor.invoke(uuid4(), "retrieve", "retriever.keyword@1", {"limit": 2}, (question, stale))
        cancellation = asyncio.Event(); cancellation.set()
        valid = artifacts.add("search.index.result", await search_index())
        with pytest.raises(PluginError) as cancel_error:
            await executor.invoke(uuid4(), "retrieve", "retriever.keyword@1", {"limit": 2}, (question, valid), cancellation)
        return artifacts, runs, stale_error.value, cancel_error.value
    artifacts, runs, stale, cancelled = asyncio.run(exercise())
    assert stale.code is PluginErrorCode.RETRIEVAL_INDEX_IDENTITY_STALE and cancelled.code is PluginErrorCode.CANCELLED
    assert not artifacts.commits and len(runs.failures) == 2


def test_synthetic_retriever_uses_only_the_public_port_and_publishes_candidates() -> None:
    class SyntheticRetriever:
        def retrieve(self, request):
            return KeywordRetriever().retrieve(request)

    async def exercise():
        artifacts, runs = Artifacts(), Runs()
        index_id = artifacts.add("search.index.result", await search_index())
        question_id = artifacts.add("opaque.bytes", b"revenue metrics")
        registry = PluginRegistry(lambda _: True, lambda _: True)
        descriptor = RETRIEVER_KEYWORD_DESCRIPTOR.model_copy(
            update={"plugin_id": "retriever.synthetic@1", "implementation_digest": "e" * 64}
        )
        registry.register(descriptor, lambda: RetrievalPlugin(SyntheticRetriever(), RetrieverConfig), RetrieverConfig)
        executor = PluginExecutor(registry, {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        output_ids = await executor.invoke(uuid4(), "synthetic", "retriever.synthetic@1", {"limit": 2}, (question_id, index_id))
        return artifacts, runs, output_ids

    artifacts, runs, output_ids = asyncio.run(exercise())
    candidate_set = RetrievalCandidateSet.model_validate_json(artifacts.contents[output_ids[0]])
    assert candidate_set.retriever_plugin_id == "retriever.synthetic@1"
    assert not runs.failures


def test_retriever_timeout_and_unavailability_never_publish_candidate_artifacts() -> None:
    class SlowRetrieverPlugin:
        async def invoke(self, context):
            await asyncio.sleep(0.1)
            raise AssertionError("timeout should cancel the retriever before it can publish")

    async def exercise_timeout():
        artifacts, runs = Artifacts(), Runs()
        index_id = artifacts.add("search.index.result", await search_index())
        question_id = artifacts.add("opaque.bytes", b"revenue")
        registry = PluginRegistry(lambda _: True, lambda _: True)
        descriptor = RETRIEVER_KEYWORD_DESCRIPTOR.model_copy(
            update={"plugin_id": "retriever.slow@1", "implementation_digest": "d" * 64, "timeout_seconds": 0.001}
        )
        registry.register(descriptor, SlowRetrieverPlugin, RetrieverConfig)
        executor = PluginExecutor(registry, {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "timeout", "retriever.slow@1", {"limit": 2}, (question_id, index_id))
        return artifacts, runs, raised.value

    async def exercise_unavailable():
        artifacts, runs = Artifacts(), Runs()
        index_id = artifacts.add("search.index.result", await search_index())
        question_id = artifacts.add("opaque.bytes", b"revenue")
        executor = PluginExecutor(
            bootstrap_registry(runner_ready=lambda _: False), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts
        )  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "unavailable", "retriever.keyword@1", {"limit": 2}, (question_id, index_id))
        return artifacts, runs, raised.value

    timeout_artifacts, timeout_runs, timeout = asyncio.run(exercise_timeout())
    unavailable_artifacts, unavailable_runs, unavailable = asyncio.run(exercise_unavailable())
    assert timeout.code is PluginErrorCode.TIMEOUT
    assert timeout_artifacts.commits == [] and [failure.code.value for failure in timeout_runs.failures] == [PluginErrorCode.TIMEOUT.value]
    assert unavailable.code is PluginErrorCode.UNAVAILABLE
    assert unavailable_artifacts.commits == [] and [failure.code.value for failure in unavailable_runs.failures] == [PluginErrorCode.UNAVAILABLE.value]


def test_malformed_retriever_output_is_a_safe_candidate_failure_without_artifact() -> None:
    class MalformedRetriever:
        def retrieve(self, request):
            return object()

    async def exercise():
        artifacts, runs = Artifacts(), Runs()
        index_id = artifacts.add("search.index.result", await search_index())
        question_id = artifacts.add("opaque.bytes", b"revenue")
        registry = PluginRegistry(lambda _: True, lambda _: True)
        descriptor = RETRIEVER_KEYWORD_DESCRIPTOR.model_copy(
            update={"plugin_id": "retriever.malformed@1", "implementation_digest": "f" * 64}
        )
        registry.register(descriptor, lambda: RetrievalPlugin(MalformedRetriever(), RetrieverConfig), RetrieverConfig)
        executor = PluginExecutor(registry, {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "malformed", "retriever.malformed@1", {"limit": 2}, (question_id, index_id))
        return artifacts, runs, raised.value

    artifacts, runs, error = asyncio.run(exercise())
    assert error.code is PluginErrorCode.RETRIEVAL_CANDIDATE_INVALID
    assert artifacts.commits == [] and [failure.code.value for failure in runs.failures] == [PluginErrorCode.RETRIEVAL_CANDIDATE_INVALID.value]


def test_forged_schema_valid_retriever_result_cannot_publish_candidates() -> None:
    class ForgedRetriever:
        def retrieve(self, request):
            valid = KeywordRetriever().retrieve(request)
            candidate = valid.candidates[0]
            # model_copy deliberately bypasses Pydantic validation to simulate
            # an untrusted compatible port returning forged indexed evidence.
            forged_candidate = candidate.model_copy(update={"chunk_id": "chk_" + "0" * 32})
            return valid.model_copy(update={"candidates": (forged_candidate,)})

    async def exercise():
        artifacts, runs = Artifacts(), Runs()
        index_id = artifacts.add("search.index.result", await search_index())
        question_id = artifacts.add("opaque.bytes", b"revenue")
        registry = PluginRegistry(lambda _: True, lambda _: True)
        descriptor = RETRIEVER_KEYWORD_DESCRIPTOR.model_copy(
            update={"plugin_id": "retriever.forged@1", "implementation_digest": "f" * 64}
        )
        registry.register(descriptor, lambda: RetrievalPlugin(ForgedRetriever(), RetrieverConfig), RetrieverConfig)
        executor = PluginExecutor(registry, {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "forged", "retriever.forged@1", {"limit": 2}, (question_id, index_id))
        return artifacts, runs, raised.value

    artifacts, runs, error = asyncio.run(exercise())
    assert error.code is PluginErrorCode.RETRIEVAL_CANDIDATE_INVALID
    assert artifacts.commits == [] and [failure.code.value for failure in runs.failures] == [PluginErrorCode.RETRIEVAL_CANDIDATE_INVALID.value]


@pytest.mark.parametrize("identity_field", ["candidate_id", "candidate_set_id"])
def test_forged_semantic_retrieval_ids_cannot_publish(identity_field: str) -> None:
    class ForgedIdentityRetriever:
        def retrieve(self, request):
            valid = KeywordRetriever().retrieve(request)
            if identity_field == "candidate_id":
                forged = valid.candidates[0].model_copy(update={"candidate_id": "rcd_" + "0" * 32})
                return valid.model_copy(update={"candidates": (forged,)})
            return valid.model_copy(update={"candidate_set_id": "rcs_" + "0" * 32})

    async def exercise():
        artifacts, runs = Artifacts(), Runs()
        index_id = artifacts.add("search.index.result", await search_index())
        question_id = artifacts.add("opaque.bytes", b"revenue")
        registry = PluginRegistry(lambda _: True, lambda _: True)
        descriptor = RETRIEVER_KEYWORD_DESCRIPTOR.model_copy(
            update={"plugin_id": "retriever.forged-identity@1", "implementation_digest": "f" * 64}
        )
        registry.register(descriptor, lambda: RetrievalPlugin(ForgedIdentityRetriever(), RetrieverConfig), RetrieverConfig)
        executor = PluginExecutor(registry, {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "forged", "retriever.forged-identity@1", {"limit": 2}, (question_id, index_id))
        return artifacts, runs, raised.value

    artifacts, runs, error = asyncio.run(exercise())
    assert error.code is PluginErrorCode.RETRIEVAL_CANDIDATE_INVALID
    assert artifacts.commits == [] and [failure.code.value for failure in runs.failures] == [PluginErrorCode.RETRIEVAL_CANDIDATE_INVALID.value]


def test_candidate_set_from_another_index_binding_cannot_publish() -> None:
    class WrongIndexRetriever:
        def retrieve(self, request):
            valid = KeywordRetriever().retrieve(request)
            return valid.model_copy(update={"index": IndexArtifactBinding(id=uuid4(), content_digest="d" * 64)})

    async def exercise():
        artifacts, runs = Artifacts(), Runs()
        index_id = artifacts.add("search.index.result", await search_index())
        question_id = artifacts.add("opaque.bytes", b"revenue")
        registry = PluginRegistry(lambda _: True, lambda _: True)
        descriptor = RETRIEVER_KEYWORD_DESCRIPTOR.model_copy(
            update={"plugin_id": "retriever.wrong-index@1", "implementation_digest": "e" * 64}
        )
        registry.register(descriptor, lambda: RetrievalPlugin(WrongIndexRetriever(), RetrieverConfig), RetrieverConfig)
        executor = PluginExecutor(registry, {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "wrong-index", "retriever.wrong-index@1", {"limit": 2}, (question_id, index_id))
        return artifacts, runs, raised.value

    artifacts, runs, error = asyncio.run(exercise())
    assert error.code is PluginErrorCode.RETRIEVAL_CANDIDATE_INVALID
    assert artifacts.commits == [] and [failure.code.value for failure in runs.failures] == [PluginErrorCode.RETRIEVAL_CANDIDATE_INVALID.value]
