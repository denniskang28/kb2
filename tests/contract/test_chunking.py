from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from kb2_runtime.chunking.contracts import ChunkSet, ChunkerConfig
from kb2_runtime.chunking.processor import canonical_bytes, enrich, process
from kb2_runtime.plugins.bootstrap import bootstrap_registry
from kb2_runtime.plugins.contracts import RunnerType
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode
from kb2_runtime.plugins.executor import PluginExecutor
from kb2_runtime.plugins.runner import InProcessRunner
from kb2_runtime.trace.contracts import ArtifactManifest, SafeError


FIXTURES = Path(__file__).parents[1] / "fixtures" / "ingestion"


class Runs:
    def __init__(self) -> None:
        self.attempt, self.failures = uuid4(), []

    async def start_attempt(self, run_id: UUID, stage_key: str) -> tuple[UUID, int]: return self.attempt, 1
    async def fail_attempt(self, attempt: UUID, error: SafeError, summary: str = "") -> None: self.failures.append(error)


class Artifacts:
    def __init__(self, content: bytes, artifact_type: str = "canonical.document") -> None:
        self.id, self.content, self.commits = uuid4(), content, []
        self.manifest = ArtifactManifest(id=self.id, artifact_type=artifact_type, schema_revision="v1", content_digest=hashlib.sha256(content).hexdigest(), byte_size=len(content), summary="fixture", storage_locator="sha256/aa/fixture", producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture.source@1", configuration_digest="a" * 64)

    async def get_artifact_manifest(self, artifact_id: UUID) -> ArtifactManifest | None: return self.manifest if artifact_id == self.id else None
    async def read_content(self, artifact_id: UUID) -> bytes: return self.content
    async def complete_with_outputs(self, run_id: UUID, attempt_id: UUID, outputs: object, **kwargs: object) -> tuple[UUID, ...]:
        self.commits.append((outputs, kwargs)); return (uuid4(),)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.mark.parametrize(("strategy", "name"), [("fixed_window", "long-hierarchy-canonical.json"), ("parent_child", "long-hierarchy-canonical.json"), ("hierarchy", "long-hierarchy-canonical.json"), ("table", "table-heavy-canonical.json")])
def test_strategies_produce_deterministic_bounded_citation_preserving_chunksets(strategy: str, name: str) -> None:
    config = ChunkerConfig(strategy=strategy, max_tokens=64)
    first, second = process(fixture(name), config), process(fixture(name), config)
    assert canonical_bytes(first) == canonical_bytes(second)
    assert ChunkSet.model_validate_json(canonical_bytes(first)) == first
    assert all(chunk.token_count <= config.max_tokens and chunk.source_element_ids and chunk.citations for chunk in first.chunks)
    if strategy == "parent_child":
        assert any(chunk.child_chunk_ids for chunk in first.chunks)
        assert all(child.parent_chunk_id == parent.chunk_id for parent in first.chunks for child in first.chunks if child.chunk_id in parent.child_chunk_ids)
    if strategy == "table":
        table_id = "elm_0000000000000022"
        assert any(table_id in chunk.source_element_ids for chunk in first.chunks)


def test_enrichment_is_additive_bounded_and_provenance_linked() -> None:
    original = process(fixture("long-hierarchy-canonical.json"), ChunkerConfig(strategy="fixed_window", max_tokens=64))
    enriched = enrich(canonical_bytes(original), {"document_class": "report", "priority": 2}, "enricher.chunk-metadata@1", "b" * 64)
    assert [chunk.chunk_id for chunk in enriched.chunks] == [chunk.chunk_id for chunk in original.chunks]
    assert enriched.chunks[0].enrichments["document_class"].provenance.source_chunk_id == enriched.chunks[0].chunk_id
    with pytest.raises(PluginError):
        enrich(canonical_bytes(enriched), {"document_class": "other"}, "enricher.chunk-metadata@1", "b" * 64)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")], ids=["nan", "positive-infinity", "negative-infinity"])
def test_enricher_configuration_rejects_non_finite_field_values_before_commit(value: float) -> None:
    initial = process(fixture("long-hierarchy-canonical.json"), ChunkerConfig(strategy="fixed_window", max_tokens=64))

    async def exercise() -> tuple[Artifacts, Runs]:
        artifacts, runs = Artifacts(canonical_bytes(initial), "chunk.set"), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "enrichment", "enricher.chunk-metadata@1", {"fields": {"score": value}}, (artifacts.id,))
        assert raised.value.code is PluginErrorCode.DESCRIPTOR_INVALID
        return artifacts, runs

    artifacts, runs = asyncio.run(exercise())
    assert artifacts.commits == [] and runs.failures == []


def test_table_strategy_repeats_caption_and_headers_for_bounded_row_groups() -> None:
    raw = json.loads(fixture("table-heavy-canonical.json"))
    for index in range(3, 15):
        raw["tables"][0]["cells"].extend([
            {"id": f"cel_{index:016x}", "text": f"Q{index}", "row": index, "column": 0, "row_span": 1, "column_span": 1, "is_header": False},
            {"id": f"cel_{index + 100:016x}", "text": "100", "row": index, "column": 1, "row_span": 1, "column_span": 1, "is_header": False},
            {"id": f"cel_{index + 200:016x}", "text": "10", "row": index, "column": 2, "row_span": 1, "column_span": 1, "is_header": False},
        ])
    raw["tables"][0]["rows"] = 15
    chunk_set = process(json.dumps(raw).encode(), ChunkerConfig(strategy="table", max_tokens=64))
    table_chunks = [chunk for chunk in chunk_set.chunks if "elm_0000000000000022" in chunk.source_element_ids]
    assert len(table_chunks) > 1 and all("Headers: Revenue | Margin" in chunk.content for chunk in table_chunks)


@pytest.mark.parametrize("strategy", ["fixed_window", "parent_child", "hierarchy", "table"])
def test_windowing_strategies_drop_overlap_that_cannot_fit_with_the_next_valid_segment(strategy: str) -> None:
    raw = json.loads(fixture("long-hierarchy-canonical.json"))
    raw["elements"] = [
        {"id": f"elm_{index:016x}", "kind": "paragraph", "locator": {"kind": "word_processing", "heading_anchor": "root", "paragraph_index": index}, "reading_order": index - 1, "text": " ".join([f"word{index}"] * 40)}
        for index in range(1, 4)
    ]
    chunks = process(json.dumps(raw).encode(), ChunkerConfig(strategy=strategy, max_tokens=64, overlap_tokens=32)).chunks
    assert all(chunk.token_count <= 64 for chunk in chunks)
    assert ("elm_0000000000000002",) in [chunk.source_element_ids for chunk in chunks]


@pytest.mark.parametrize("mutate", [
    lambda payload: payload["chunks"][0].update(citations=[]),
    lambda payload: payload["chunks"][0].update(parent_chunk_id="chk_" + "a" * 32),
    lambda payload: payload["chunks"][0].update(content="x" * 16_385),
])
def test_invalid_chunkset_is_ineligible_and_enricher_cannot_commit(mutate: object) -> None:
    raw = process(fixture("long-hierarchy-canonical.json"), ChunkerConfig(strategy="fixed_window", max_tokens=64)).model_dump(mode="json")
    mutate(raw)  # type: ignore[operator]
    async def exercise() -> tuple[Artifacts, Runs]:
        artifacts, runs = Artifacts(json.dumps(raw).encode(), "chunk.set"), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "enrichment", "enricher.chunk-metadata@1", {"fields": {"label": "x"}}, (artifacts.id,))
        assert raised.value.code is PluginErrorCode.CANONICAL_INPUT_INVALID
        return artifacts, runs
    artifacts, runs = asyncio.run(exercise())
    assert artifacts.commits == [] and [item.code.value for item in runs.failures] == ["CANONICAL_INPUT_INVALID"]


@pytest.mark.parametrize("mutate", [
    lambda payload: payload["chunks"][0].update(token_count=99),
    lambda payload: payload["chunks"][0]["enrichments"]["classifier"]["provenance"].update(source_chunk_id="chk_" + "a" * 32),
])
def test_derived_chunk_fields_and_existing_enrichment_provenance_are_validated_before_commit(mutate: object) -> None:
    initial = process(fixture("long-hierarchy-canonical.json"), ChunkerConfig(strategy="fixed_window", max_tokens=64))
    enriched = enrich(canonical_bytes(initial), {"classifier": "fixture"}, "enricher.chunk-metadata@1", "b" * 64)
    raw = enriched.model_dump(mode="json")
    mutate(raw)  # type: ignore[operator]

    async def exercise() -> tuple[Artifacts, Runs]:
        artifacts, runs = Artifacts(json.dumps(raw).encode(), "chunk.set"), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "enrichment", "enricher.chunk-metadata@1", {"fields": {"label": "x"}}, (artifacts.id,))
        assert raised.value.code is PluginErrorCode.CANONICAL_INPUT_INVALID
        return artifacts, runs

    artifacts, runs = asyncio.run(exercise())
    assert artifacts.commits == [] and [item.code.value for item in runs.failures] == ["CANONICAL_INPUT_INVALID"]


@pytest.mark.parametrize("mutate", [
    lambda payload: payload["chunks"][0]["citations"][0].pop("locator"),
    lambda payload: _make_parent_cycle(payload),
])
def test_missing_locator_and_cyclic_parent_links_are_safe_ineligibility_failures(mutate: object) -> None:
    raw = process(fixture("long-hierarchy-canonical.json"), ChunkerConfig(strategy="parent_child", max_tokens=64)).model_dump(mode="json")
    mutate(raw)  # type: ignore[operator]

    async def exercise() -> tuple[Artifacts, Runs]:
        artifacts, runs = Artifacts(json.dumps(raw).encode(), "chunk.set"), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "enrichment", "enricher.chunk-metadata@1", {"fields": {"label": "x"}}, (artifacts.id,))
        assert raised.value.code is PluginErrorCode.CANONICAL_INPUT_INVALID
        return artifacts, runs

    artifacts, runs = asyncio.run(exercise())
    assert artifacts.commits == [] and [item.code.value for item in runs.failures] == ["CANONICAL_INPUT_INVALID"]


def _make_parent_cycle(payload: dict[str, object]) -> None:
    parent, child = payload["chunks"]  # type: ignore[index]
    parent["parent_chunk_id"] = child["chunk_id"]
    child["child_chunk_ids"] = [parent["chunk_id"]]


def test_stale_canonical_table_source_reference_fails_before_chunk_commit() -> None:
    raw = json.loads(fixture("table-heavy-canonical.json"))
    raw["tables"][0]["caption_element_id"] = "elm_00000000000000ff"

    async def exercise() -> tuple[Artifacts, Runs]:
        artifacts, runs = Artifacts(json.dumps(raw).encode()), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "chunking", "chunker.canonical@1", {"strategy": "table", "max_tokens": 64}, (artifacts.id,))
        assert raised.value.code is PluginErrorCode.CANONICAL_INPUT_INVALID
        return artifacts, runs

    artifacts, runs = asyncio.run(exercise())
    assert artifacts.commits == [] and [item.code.value for item in runs.failures] == ["CANONICAL_INPUT_INVALID"]


def test_registered_chunker_commits_chunkset_with_canonical_parent_lineage() -> None:
    async def exercise() -> tuple[object, Artifacts, Runs]:
        artifacts, runs = Artifacts(fixture("long-hierarchy-canonical.json")), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        await executor.invoke(uuid4(), "chunking", "chunker.canonical@1", {"strategy": "hierarchy", "max_tokens": 64}, (artifacts.id,))
        return artifacts.commits[0][0][0][0], artifacts, runs
    stored, artifacts, runs = asyncio.run(exercise())
    assert stored.artifact_type == "chunk.set" and stored.parent_artifact_ids == (artifacts.id,)
    assert {item.name for item in stored.quality_signals} == {"chunk_validation", "citation_validation"} and not runs.failures
