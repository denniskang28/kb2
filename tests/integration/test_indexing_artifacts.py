from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from kb2_runtime.plugins.bootstrap import bootstrap_registry
from kb2_runtime.plugins.bootstrap import EmptyConfig
from kb2_runtime.plugins.contracts import PluginDescriptor, RunnerType
from kb2_runtime.plugins.executor import PluginExecutor
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode
from kb2_runtime.plugins.registry import PluginRegistry
from kb2_runtime.plugins.runner import InProcessRunner
from kb2_runtime.trace.contracts import ArtifactInput, ArtifactManifest, SafeError
from kb2_runtime.trace.errors import TraceError, TraceErrorCode
from kb2_runtime.trace.service import ArtifactService


class Runs:
    def __init__(self) -> None: self.failures: list[SafeError] = []
    async def start_attempt(self, run_id: UUID, stage_key: str) -> tuple[UUID, int]: return uuid4(), 1
    async def fail_attempt(self, attempt_id: UUID, error: SafeError, summary: str = "") -> None: self.failures.append(error)


class Artifacts:
    def __init__(self, content: bytes) -> None:
        self.contents: dict[UUID, bytes] = {}; self.manifests: dict[UUID, ArtifactManifest] = {}; self.commits = []; self.fail_publish = False
        self.source = self.add("chunk.set", content, ())

    def add(self, artifact_type: str, content: bytes, parents: tuple[UUID, ...]) -> UUID:
        artifact_id = uuid4(); self.contents[artifact_id] = content
        self.manifests[artifact_id] = ArtifactManifest(id=artifact_id, artifact_type=artifact_type, schema_revision="v1", content_digest=hashlib.sha256(content).hexdigest(), byte_size=len(content), summary="fixture", storage_locator="sha256/aa/fixture", producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture.source@1", configuration_digest="a" * 64, parent_artifact_ids=parents)
        return artifact_id

    async def get_artifact_manifest(self, artifact_id: UUID): return self.manifests.get(artifact_id)
    async def read_content(self, artifact_id: UUID) -> bytes: return self.contents[artifact_id]
    async def complete_with_outputs(self, run_id: UUID, attempt_id: UUID, outputs: object, **kwargs: object) -> tuple[UUID, ...]:
        if self.fail_publish:
            self.fail_publish = False
            raise TraceError(TraceErrorCode.TRACE_STORAGE_FAILURE)
        ids = tuple(self.add(item.artifact_type, content, item.parent_artifact_ids) for item, content in outputs)  # type: ignore[union-attr]
        self.commits.append((outputs, kwargs)); return ids


class CancelAfterResultRunner:
    async def invoke(self, implementation, invocation, context):
        result = await implementation.invoke(context)
        context.cancellation.set()
        return result


def test_registered_embedding_projection_and_index_plugins_commit_immutable_lineage() -> None:
    async def exercise():
        content = (Path(__file__).parents[1] / "fixtures" / "ingestion" / "table-heavy-canonical.json").read_bytes()
        # Feed an already-produced ChunkSet because this Story starts at the chunk boundary.
        from kb2_runtime.chunking.contracts import ChunkerConfig
        from kb2_runtime.chunking.processor import canonical_bytes, process
        artifacts, runs = Artifacts(canonical_bytes(process(content, ChunkerConfig(strategy="table", max_tokens=64)))), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        run_id = uuid4()
        embedding_id = (await executor.invoke(run_id, "embedding", "embedder.hashing@1", {}, (artifacts.source,)))[0]
        documents_id = (await executor.invoke(run_id, "projection", "search-document.projector@1", {}, (artifacts.source, embedding_id)))[0]
        index_id = (await executor.invoke(run_id, "index", "indexer.local-hybrid@1", {}, (documents_id,)))[0]
        return artifacts, runs, embedding_id, documents_id, index_id
    artifacts, runs, embedding_id, documents_id, index_id = asyncio.run(exercise())
    assert artifacts.manifests[embedding_id].artifact_type == "embedding.set"
    assert artifacts.manifests[documents_id].parent_artifact_ids == (artifacts.source, embedding_id)
    assert artifacts.manifests[index_id].artifact_type == "search.index.result"
    assert not runs.failures


def test_invalid_chunk_payload_fails_before_any_embedding_artifact_is_committed() -> None:
    async def exercise():
        artifacts, runs = Artifacts(b"{}"), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        try:
            await executor.invoke(uuid4(), "embedding", "embedder.hashing@1", {}, (artifacts.source,))
        except PluginError as error:
            return artifacts, runs, error
        raise AssertionError("invalid chunk payload unexpectedly succeeded")
    artifacts, runs, error = asyncio.run(exercise())
    assert error.code is PluginErrorCode.EMBEDDING_RECORD_INVALID
    assert artifacts.commits == [] and [failure.code.value for failure in runs.failures] == ["EMBEDDING_RECORD_INVALID"]


def test_cancellation_after_index_build_before_commit_cannot_publish_output() -> None:
    async def exercise():
        from kb2_runtime.chunking.contracts import ChunkerConfig
        from kb2_runtime.chunking.processor import canonical_bytes, process
        source = (Path(__file__).parents[1] / "fixtures" / "ingestion" / "table-heavy-canonical.json").read_bytes()
        artifacts, runs = Artifacts(canonical_bytes(process(source, ChunkerConfig(strategy="table", max_tokens=64)))), Runs()
        ordinary = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        run_id = uuid4()
        embedding = (await ordinary.invoke(run_id, "embedding", "embedder.hashing@1", {}, (artifacts.source,)))[0]
        documents = (await ordinary.invoke(run_id, "projection", "search-document.projector@1", {}, (artifacts.source, embedding)))[0]
        commits_before = len(artifacts.commits)
        racing = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: CancelAfterResultRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await racing.invoke(run_id, "index", "indexer.local-hybrid@1", {}, (documents,), asyncio.Event())
        return artifacts, runs, commits_before, raised.value
    artifacts, runs, commits_before, error = asyncio.run(exercise())
    assert error.code is PluginErrorCode.CANCELLED and len(artifacts.commits) == commits_before
    assert not [item for item in artifacts.manifests.values() if item.artifact_type == "search.index.result"]
    assert [failure.code.value for failure in runs.failures] == ["PLUGIN_INVOCATION_CANCELLED"]


def test_unavailable_optional_indexer_is_registered_but_cannot_publish_an_index() -> None:
    async def exercise():
        from kb2_runtime.chunking.contracts import ChunkerConfig
        from kb2_runtime.chunking.processor import canonical_bytes, process
        source = (Path(__file__).parents[1] / "fixtures" / "ingestion" / "table-heavy-canonical.json").read_bytes()
        artifacts, runs = Artifacts(canonical_bytes(process(source, ChunkerConfig(strategy="table", max_tokens=64)))), Runs()
        registry = PluginRegistry(lambda capability: capability != "search.optional", lambda _: True)
        descriptor = PluginDescriptor(plugin_id="indexer.optional@1", kind="indexer", implementation_digest="f" * 64, runner=RunnerType.IN_PROCESS, configuration_schema=EmptyConfig.model_json_schema(), input_schemas=(("search.document.set", "v1"),), output_schemas=(("search.index.result", "v1"),), timeout_seconds=10, capabilities=("search.optional",))
        registry.register(descriptor, object, EmptyConfig)  # type: ignore[arg-type]
        executor = PluginExecutor(registry, {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        try:
            await executor.invoke(uuid4(), "optional-index", "indexer.optional@1", {}, (artifacts.source,))
        except PluginError as error:
            return artifacts, runs, registry, error
        raise AssertionError("unavailable indexer unexpectedly succeeded")
    artifacts, runs, registry, error = asyncio.run(exercise())
    availability = registry.inspect("indexer.optional@1")[0]
    assert error.code is PluginErrorCode.UNAVAILABLE
    assert availability.registered and not availability.runnable and availability.reason == "CAPABILITY_UNAVAILABLE"
    assert artifacts.commits == [] and [failure.code.value for failure in runs.failures] == ["PLUGIN_UNAVAILABLE"]


def test_transient_artifact_publish_failure_exposes_no_index_and_a_retry_recovers() -> None:
    async def exercise():
        from kb2_runtime.chunking.contracts import ChunkerConfig
        from kb2_runtime.chunking.processor import canonical_bytes, process
        source = (Path(__file__).parents[1] / "fixtures" / "ingestion" / "table-heavy-canonical.json").read_bytes()
        artifacts, runs = Artifacts(canonical_bytes(process(source, ChunkerConfig(strategy="table", max_tokens=64)))), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        run_id = uuid4()
        embedding = (await executor.invoke(run_id, "embedding", "embedder.hashing@1", {}, (artifacts.source,)))[0]
        documents = (await executor.invoke(run_id, "projection", "search-document.projector@1", {}, (artifacts.source, embedding)))[0]
        artifacts.fail_publish = True
        try:
            await executor.invoke(run_id, "index", "indexer.local-hybrid@1", {}, (documents,))
        except PluginError as error:
            failed = error
        else:
            raise AssertionError("failed publish unexpectedly succeeded")
        recovered = (await executor.invoke(run_id, "index", "indexer.local-hybrid@1", {}, (documents,)))[0]
        return artifacts, runs, failed, recovered
    artifacts, runs, failed, recovered = asyncio.run(exercise())
    assert failed.code is PluginErrorCode.RESULT_INVALID
    assert artifacts.manifests[recovered].artifact_type == "search.index.result"
    assert len([item for item in artifacts.manifests.values() if item.artifact_type == "search.index.result"]) == 1
    assert [failure.code.value for failure in runs.failures] == ["PLUGIN_RESULT_INVALID"]


def test_artifact_service_repository_partial_write_has_no_visible_index_and_recovers() -> None:
    class Connection:
        def __init__(self, repository: object) -> None:
            self.repository = repository; self.rollbacks = 0
        async def rollback(self) -> None:
            self.rollbacks += 1
            self.repository.staged.clear()  # type: ignore[attr-defined]
    class Repository:
        def __init__(self) -> None:
            self.fail = True; self.visible: list[object] = []; self.staged: list[object] = []; self.failures = []
            self.connection = Connection(self)
        async def complete_outputs(self, attempt_id, run_id, outputs, summary, metrics, signals) -> None:
            self.staged.extend(outputs)
            if self.fail:
                self.fail = False
                raise TraceError(TraceErrorCode.TRACE_STORAGE_FAILURE)
            self.visible.extend(self.staged)
            self.staged.clear()
        async def finish_attempt(self, *args) -> None: self.failures.append(args)
    class Store:
        def publish(self, content: bytes, digest: str, size: int) -> str:
            assert len(content) == size and hashlib.sha256(content).hexdigest() == digest
            return f"sha256/aa/{digest}"
    async def exercise():
        repository = Repository(); service = ArtifactService(repository, Store())  # type: ignore[arg-type]
        content = b'{"schema_version":"SearchIndexResult/v1"}'
        manifest = ArtifactInput(artifact_type="search.index.result", schema_revision="v1", content_digest=hashlib.sha256(content).hexdigest(), byte_size=len(content), producing_plugin_id="indexer.local-hybrid@1", configuration_digest="4" * 64)
        try:
            await service.complete_with_outputs(uuid4(), uuid4(), [(manifest, content)])
        except TraceError as error:
            assert error.code is TraceErrorCode.TRACE_STORAGE_FAILURE
        else:
            raise AssertionError("repository partial write unexpectedly succeeded")
        assert repository.visible == [] and repository.staged == []
        recovered = await service.complete_with_outputs(uuid4(), uuid4(), [(manifest, content)])
        return repository, recovered
    repository, recovered = asyncio.run(exercise())
    assert repository.connection.rollbacks == 1 and len(repository.visible) == 1 and not repository.staged and len(recovered) == 1
    assert len(repository.failures) == 1 and repository.failures[0][1].value == "FAILED"
