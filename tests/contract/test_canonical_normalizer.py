from __future__ import annotations

import asyncio
import hashlib
import json
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from kb2_runtime.canonical.contracts import ProviderFixture
from kb2_runtime.canonical.normalizer import MAX_PROVIDER_FIXTURE_BYTES
from kb2_runtime.plugins.bootstrap import bootstrap_registry
from kb2_runtime.plugins.contracts import ArtifactInput as PluginArtifactInput, RunnerType
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode
from kb2_runtime.plugins.executor import PluginExecutor
from kb2_runtime.plugins.runner import InProcessRunner
from kb2_runtime.trace.contracts import ArtifactManifest, SafeError



def fixture() -> dict[str, object]:
    source_digest = hashlib.sha256(b"representative source").hexdigest()
    return {
        "adapter_id": "fixture.parser@1", "source_content_digest": source_digest,
        "elements": [
            {"kind": "heading", "reading_order": 0, "locator": {"kind": "pdf", "page_number": 1, "x0": 0, "y0": 0, "x1": 1, "y1": 1}, "level": 1, "text": "Title"},
            {"kind": "caption", "reading_order": 1, "locator": {"kind": "html", "path": "main/caption", "anchor": "caption"}, "text": "Caption"},
            {"kind": "table", "reading_order": 2, "locator": {"kind": "spreadsheet", "sheet_name": "Sheet1", "range": "A1:B2"}},
        ],
        "tables": [{
            "element_reading_order": 2, "rows": 2, "columns": 2,
            "locator": {"kind": "spreadsheet", "sheet_name": "Sheet1", "range": "A1:B2"},
            "cells": [
                {"text": "H1", "row": 0, "column": 0, "row_span": 1, "column_span": 1, "is_header": True},
                {"text": "H2", "row": 0, "column": 1, "row_span": 1, "column_span": 1, "is_header": True},
                {"text": "A", "row": 1, "column": 0, "row_span": 1, "column_span": 1},
                {"text": "B", "row": 1, "column": 1, "row_span": 1, "column_span": 1},
            ], "header_cell_positions": [[0, 0], [0, 1]], "caption_reading_order": 1,
        }],
    }


class Runs:
    def __init__(self) -> None:
        self.attempt = uuid4()
        self.failures: list[SafeError] = []

    async def start_attempt(self, run_id: UUID, stage_key: str) -> tuple[UUID, int]:
        return self.attempt, 1

    async def fail_attempt(self, attempt_id: UUID, error: SafeError, summary: str = "") -> None:
        self.failures.append(error)


class Artifacts:
    def __init__(self, content: bytes) -> None:
        self.id = uuid4()
        self.content = content
        self.manifest = ArtifactManifest(
            id=self.id, artifact_type="provider.parse-result-fixture", schema_revision="v1",
            content_digest=hashlib.sha256(content).hexdigest(), byte_size=len(content), summary="fixture",
            storage_locator="sha256/aa/fixture", producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(),
            producing_plugin_id="parser.fixture@1", configuration_digest="a" * 64,
        )
        self.commits: list[tuple[object, dict[str, object]]] = []

    async def get_artifact_manifest(self, artifact_id: UUID) -> ArtifactManifest | None:
        return self.manifest if artifact_id == self.id else None

    async def read_content(self, artifact_id: UUID) -> bytes:
        return self.content

    async def complete_with_outputs(self, run_id: UUID, attempt_id: UUID, outputs: object, **kwargs: object) -> tuple[UUID, ...]:
        self.commits.append((outputs, kwargs))
        return (uuid4(),)


def test_normalizer_executes_through_registry_and_commits_exact_parent_lineage() -> None:
    async def exercise() -> tuple[bytes, bytes, object, Artifacts, Runs]:
        source = json.dumps(fixture(), sort_keys=True, separators=(",", ":")).encode()
        artifacts, runs = Artifacts(source), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        await executor.invoke(uuid4(), "normalize", "normalizer.canonical@1", {}, (artifacts.id,))
        await executor.invoke(uuid4(), "normalize", "normalizer.canonical@1", {}, (artifacts.id,))
        stored, content = artifacts.commits[0][0][0]
        _, repeated = artifacts.commits[1][0][0]
        return content, repeated, stored, artifacts, runs

    first, second, stored, artifacts, runs = asyncio.run(exercise())
    assert first == second
    assert stored.artifact_type == "canonical.document"
    assert stored.schema_revision == "v1"
    assert stored.parent_artifact_ids == (artifacts.id,)
    assert stored.producing_plugin_id == "normalizer.canonical@1"
    assert not runs.failures
    document = json.loads(first)
    assert document["schema_version"] == "CanonicalDocument/v1"
    assert "provider_sdk" not in first.decode()


def test_provider_object_cannot_cross_the_plugin_or_canonical_boundary() -> None:
    with pytest.raises(ValidationError):
        PluginArtifactInput.model_validate({"reference": {"id": uuid4(), "artifact_type": "provider.parse-result-fixture", "schema_revision": "v1", "content_digest": "a" * 64, "byte_size": 1, "summary": ""}, "content": object()})
    raw = fixture()
    raw["provider_object"] = {"sdk": "forbidden"}
    with pytest.raises(ValidationError):
        ProviderFixture.model_validate(raw)


def test_unbounded_provider_field_fails_safely_without_committing_an_artifact() -> None:
    async def exercise() -> tuple[Artifacts, Runs]:
        raw = fixture()
        raw["elements"][0]["text"] = "x" * 16_385
        source = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
        artifacts, runs = Artifacts(source), Runs()
        executor = PluginExecutor(
            bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts
        )  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "normalize", "normalizer.canonical@1", {}, (artifacts.id,))
        assert raised.value.code is PluginErrorCode.CANONICAL_FIELD_UNBOUNDED
        return artifacts, runs

    artifacts, runs = asyncio.run(exercise())
    assert artifacts.commits == []
    assert [failure.code for failure in runs.failures] == [PluginErrorCode.CANONICAL_FIELD_UNBOUNDED]


@pytest.mark.parametrize("input_count", [0, 2])
def test_normalizer_rejects_any_input_count_other_than_its_single_declared_parent(input_count: int) -> None:
    async def exercise() -> tuple[Artifacts, Runs]:
        source = json.dumps(fixture(), sort_keys=True, separators=(",", ":")).encode()
        artifacts, runs = Artifacts(source), Runs()
        executor = PluginExecutor(
            bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts
        )  # type: ignore[arg-type]
        input_ids = () if input_count == 0 else (artifacts.id, artifacts.id)
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "normalize", "normalizer.canonical@1", {}, input_ids)
        assert raised.value.code is PluginErrorCode.RESULT_INVALID
        return artifacts, runs

    artifacts, runs = asyncio.run(exercise())
    assert artifacts.commits == []
    assert runs.failures == []


def test_raw_fixture_over_limit_fails_before_decode_without_committing_an_artifact() -> None:
    async def exercise() -> tuple[Artifacts, Runs]:
        valid_json = json.dumps(fixture(), sort_keys=True, separators=(",", ":")).encode()
        source = valid_json + (b" " * (MAX_PROVIDER_FIXTURE_BYTES - len(valid_json) + 1))
        artifacts, runs = Artifacts(source), Runs()
        executor = PluginExecutor(
            bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts
        )  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "normalize", "normalizer.canonical@1", {}, (artifacts.id,))
        assert raised.value.code is PluginErrorCode.CANONICAL_FIELD_UNBOUNDED
        return artifacts, runs

    artifacts, runs = asyncio.run(exercise())
    assert artifacts.commits == []
    assert [failure.code for failure in runs.failures] == [PluginErrorCode.CANONICAL_FIELD_UNBOUNDED]
