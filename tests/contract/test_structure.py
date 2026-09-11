from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from kb2_runtime.canonical.contracts import CanonicalDocument
from kb2_runtime.plugins.bootstrap import bootstrap_registry
from kb2_runtime.plugins.contracts import RunnerType
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode
from kb2_runtime.plugins.executor import PluginExecutor
from kb2_runtime.plugins.runner import InProcessRunner
from kb2_runtime.trace.contracts import ArtifactManifest, SafeError


FIXTURES = Path(__file__).parents[1] / "fixtures" / "ingestion"


class Runs:
    def __init__(self) -> None:
        self.attempt = uuid4()
        self.failures: list[SafeError] = []

    async def start_attempt(self, run_id: UUID, stage_key: str) -> tuple[UUID, int]:
        return self.attempt, 1

    async def fail_attempt(self, attempt: UUID, error: SafeError, summary: str = "") -> None:
        self.failures.append(error)


class Artifacts:
    def __init__(self, content: bytes) -> None:
        self.id, self.content, self.commits = uuid4(), content, []
        self.manifest = ArtifactManifest(
            id=self.id, artifact_type="canonical.document", schema_revision="v1",
            content_digest=hashlib.sha256(content).hexdigest(), byte_size=len(content), summary="canonical",
            storage_locator="sha256/aa/canonical", producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(),
            producing_plugin_id="normalizer.fixture@1", configuration_digest="a" * 64,
        )

    async def get_artifact_manifest(self, artifact_id: UUID) -> ArtifactManifest | None:
        return self.manifest if artifact_id == self.id else None

    async def read_content(self, artifact_id: UUID) -> bytes:
        return self.content

    async def complete_with_outputs(self, run_id: UUID, attempt_id: UUID, outputs: object, **kwargs: object) -> tuple[UUID, ...]:
        self.commits.append((outputs, kwargs))
        return (uuid4(),)


def invoke(content: bytes, strategy: str) -> tuple[bytes, object, Artifacts, Runs]:
    async def exercise() -> tuple[bytes, object, Artifacts, Runs]:
        artifacts, runs = Artifacts(content), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        await executor.invoke(uuid4(), "structure", "structure.canonical@1", {"strategy": strategy}, (artifacts.id,))
        stored, output = artifacts.commits[0][0][0]
        return output, stored, artifacts, runs
    return asyncio.run(exercise())


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_hierarchy_derives_links_without_changing_identity_or_locators() -> None:
    content = fixture("long-hierarchy-canonical.json")
    output, stored, artifacts, runs = invoke(content, "hierarchy")
    document = CanonicalDocument.model_validate_json(output)
    original = CanonicalDocument.model_validate_json(content)
    assert [(item.id, item.locator) for item in document.elements] == [(item.id, item.locator) for item in original.elements]
    assert [item.parent_id for item in document.elements] == [None, original.elements[0].id, original.elements[0].id, original.elements[2].id]
    assert stored.parent_artifact_ids == (artifacts.id,) and not runs.failures
    assert {item.name for item in stored.quality_signals} == {"structure_validation", "hierarchy_validation", "reading_order_validation", "table_validation"}


def test_layout_normalizes_pdf_reading_order_without_rewriting_other_references() -> None:
    content = fixture("pdf-layout-canonical.json")
    output, _, _, _ = invoke(content, "layout")
    document = CanonicalDocument.model_validate_json(output)
    original = CanonicalDocument.model_validate_json(content)
    assert [item.id for item in document.elements] == ["elm_0000000000000012", "elm_0000000000000011", "elm_0000000000000013"]
    assert [item.reading_order for item in document.elements] == [0, 1, 2]
    assert [item.model_dump(exclude={"reading_order"}) for item in document.elements] == [
        item.model_dump(exclude={"reading_order"})
        for item in sorted(original.elements, key=lambda item: (item.locator.page_number, item.locator.y0, item.locator.x0, item.reading_order))  # type: ignore[union-attr]
    ]
    assert CanonicalDocument.model_validate_json(output) == document


def test_table_fixture_round_trips_losslessly_through_a_fresh_canonical_parse() -> None:
    content = fixture("table-heavy-canonical.json")
    output, _, _, _ = invoke(content, "table")
    original, restored = CanonicalDocument.model_validate_json(content), CanonicalDocument.model_validate_json(output)
    assert restored == original
    assert CanonicalDocument.model_validate_json(output).tables[0].cells[0].column_span == 2


@pytest.mark.parametrize("strategy", ["hierarchy", "table"])
@pytest.mark.parametrize("mutate", [
    lambda value: value["tables"][0].update(caption_element_id="elm_0000000000000022"),
    lambda value: value["tables"][0].update(related_element_ids=["elm_0000000000000022"]),
    lambda value: value["tables"][0].update(locator={"kind": "spreadsheet", "sheet_name": "Metrics", "range": "A7:C9"}),
])
def test_table_semantics_fail_for_every_compatible_strategy(strategy: str, mutate: object) -> None:
    async def exercise() -> Artifacts:
        raw = json.loads(fixture("table-heavy-canonical.json"))
        mutate(raw)  # type: ignore[operator]
        artifacts, runs = Artifacts(json.dumps(raw, separators=(",", ":")).encode()), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "structure", "structure.canonical@1", {"strategy": strategy}, (artifacts.id,))
        assert raised.value.code is PluginErrorCode.CANONICAL_DOCUMENT_INVALID
        assert [item.code.value for item in runs.failures] == ["CANONICAL_DOCUMENT_INVALID"]
        return artifacts
    assert asyncio.run(exercise()).commits == []


def test_layout_strategy_validates_table_semantics_after_ordering() -> None:
    async def exercise() -> Artifacts:
        raw = json.loads(fixture("table-heavy-canonical.json"))
        for index, element in enumerate(raw["elements"]):
            element["locator"] = {"kind": "pdf", "page_number": 1, "x0": 0, "y0": index / 10, "x1": 1, "y1": (index + 1) / 10}
        raw["tables"][0]["locator"] = raw["elements"][1]["locator"]
        raw["tables"][0]["related_element_ids"] = [raw["tables"][0]["element_id"]]
        artifacts, runs = Artifacts(json.dumps(raw, separators=(",", ":")).encode()), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "structure", "structure.canonical@1", {"strategy": "layout"}, (artifacts.id,))
        assert raised.value.code is PluginErrorCode.CANONICAL_DOCUMENT_INVALID
        assert [item.code.value for item in runs.failures] == ["CANONICAL_DOCUMENT_INVALID"]
        return artifacts
    assert asyncio.run(exercise()).commits == []


@pytest.mark.parametrize(("strategy", "mutate", "code"), [
    ("hierarchy", lambda value: value["elements"][2].update(level=4), PluginErrorCode.CANONICAL_DOCUMENT_INVALID),
    ("layout", lambda value: value["elements"][0].update(locator={"kind": "word_processing", "heading_anchor": "x", "paragraph_index": 1}), PluginErrorCode.CANONICAL_DOCUMENT_INVALID),
    ("table", lambda value: value["tables"][0].update(locator={"kind": "spreadsheet", "sheet_name": "Metrics", "range": "A7:C9"}), PluginErrorCode.CANONICAL_DOCUMENT_INVALID),
])
def test_invalid_structure_fails_with_safe_evidence_and_no_commit(strategy: str, mutate: object, code: PluginErrorCode) -> None:
    async def exercise() -> tuple[Artifacts, Runs]:
        raw = json.loads(fixture("table-heavy-canonical.json") if strategy == "table" else fixture("long-hierarchy-canonical.json"))
        mutate(raw)  # type: ignore[operator]
        artifacts, runs = Artifacts(json.dumps(raw, separators=(",", ":")).encode()), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "structure", "structure.canonical@1", {"strategy": strategy}, (artifacts.id,))
        assert raised.value.code is code
        return artifacts, runs
    artifacts, runs = asyncio.run(exercise())
    assert artifacts.commits == [] and [item.code.value for item in runs.failures] == [code.value]


def test_malformed_and_unbounded_canonical_inputs_fail_without_output() -> None:
    async def exercise(content: bytes) -> Artifacts:
        artifacts, runs = Artifacts(content), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError):
            await executor.invoke(uuid4(), "structure", "structure.canonical@1", {"strategy": "table"}, (artifacts.id,))
        assert runs.failures
        return artifacts
    assert asyncio.run(exercise(b"not-json")).commits == []
    assert asyncio.run(exercise(b" " * (16 * 1024 * 1024 + 1))).commits == []


def test_closed_strategy_configuration_rejects_unknown_or_undeclared_values() -> None:
    async def exercise(configuration: dict[str, str]) -> Artifacts:
        artifacts, runs = Artifacts(fixture("long-hierarchy-canonical.json")), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "structure", "structure.canonical@1", configuration, (artifacts.id,))
        assert raised.value.code is PluginErrorCode.DESCRIPTOR_INVALID
        assert runs.failures == []
        return artifacts
    assert asyncio.run(exercise({"strategy": "unknown"})).commits == []
    assert asyncio.run(exercise({"strategy": "table", "path": "forbidden"})).commits == []
