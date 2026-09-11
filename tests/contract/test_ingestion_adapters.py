from __future__ import annotations

import asyncio
import hashlib
import io
import json
import zipfile
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

from kb2_runtime.canonical.contracts import ProviderFixture
from kb2_runtime.ingestion_adapters import NativeOoxmlParser
from kb2_runtime.plugins.bootstrap import bootstrap_registry
from kb2_runtime.plugins.contracts import PluginDescriptor, PluginInvocationResult, PluginOutput, RunnerType
from kb2_runtime.plugins.executor import PluginExecutor
from kb2_runtime.plugins.registry import PluginRegistry
from kb2_runtime.plugins.runner import InProcessRunner
from kb2_runtime.trace.contracts import ArtifactManifest, SafeError
from kb2_runtime.trace.schemas import schema_is_supported


def native_docx() -> bytes:
    document = b'''<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Native Title</w:t></w:r></w:p><w:p><w:r><w:t>Native English text.</w:t></w:r></w:p></w:body></w:document>'''
    content_types = b'''<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'''
    relationships = b'''<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'''
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document)
    return result.getvalue()


class Runs:
    def __init__(self) -> None:
        self.attempt = uuid4()
        self.failures: list[SafeError] = []
        self.started: list[tuple[UUID, str]] = []
        self.failed_attempt_ids: list[UUID] = []
        self.failure_summaries: list[str] = []

    async def start_attempt(self, run_id: UUID, stage_key: str) -> tuple[UUID, int]:
        self.started.append((run_id, stage_key))
        return self.attempt, 1

    async def fail_attempt(self, attempt: UUID, error: SafeError, summary: str = "") -> None:
        self.failed_attempt_ids.append(attempt)
        self.failure_summaries.append(summary)
        self.failures.append(error)


class Artifacts:
    def __init__(self, artifact_type: str, content: bytes) -> None:
        self.id, self.content, self.commits = uuid4(), content, []
        self.manifest = ArtifactManifest(id=self.id, artifact_type=artifact_type, schema_revision="v1", content_digest=hashlib.sha256(content).hexdigest(), byte_size=len(content), summary="source", storage_locator="sha256/aa/source", producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(), producing_plugin_id="source.fixture@1", configuration_digest="a" * 64)

    async def get_artifact_manifest(self, artifact_id: UUID) -> ArtifactManifest | None:
        return self.manifest if artifact_id == self.id else None

    async def read_content(self, artifact_id: UUID) -> bytes:
        return self.content

    async def complete_with_outputs(self, run_id: UUID, attempt_id: UUID, outputs: object, **kwargs: object) -> tuple[UUID, ...]:
        self.commits.append((outputs, kwargs))
        return (uuid4(),)


def invoke(plugin_id: str, artifact_type: str, content: bytes, config: dict[str, object] | None = None) -> tuple[Artifacts, Runs]:
    async def exercise() -> tuple[Artifacts, Runs]:
        artifacts, runs = Artifacts(artifact_type, content), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        await executor.invoke(uuid4(), "parse", plugin_id, config or {}, (artifacts.id,))
        return artifacts, runs
    return asyncio.run(exercise())


def test_adapter_schemas_descriptors_and_native_provider_result_are_typed_and_deterministic() -> None:
    assert all(schema_is_supported(*pair) for pair in (
        ("source.native-ooxml", "v1"), ("source.scanned-ocr-exchange", "v1"),
        ("provider.native-ooxml-result", "v1"), ("provider.scanned-ocr-result", "v1"),
    ))
    registry = bootstrap_registry()
    descriptors = {item.plugin_id: registry.get(item.plugin_id).descriptor for item in registry.inspect()}
    assert descriptors["parser.native-ooxml@1"].quality_signal_names == ("layout_detected", "languages_observed")
    assert descriptors["ocr.scanned-exchange@1"].quality_signal_names[-2:] == ("ocr_model_id", "ocr_confidence_bucket")
    first, _ = invoke("parser.native-ooxml@1", "source.native-ooxml", native_docx())
    second, _ = invoke("parser.native-ooxml@1", "source.native-ooxml", native_docx())
    first_output, first_bytes = first.commits[0][0][0]
    _, second_bytes = second.commits[0][0][0]
    fixture = ProviderFixture.model_validate_json(first_bytes)
    assert first_output.artifact_type == "provider.native-ooxml-result"
    assert first_bytes == second_bytes
    assert [item.text for item in fixture.elements] == ["Native Title", "Native English text."]
    assert fixture.elements[0].locator.kind == "word_processing"
    assert fixture.source_content_digest == first.manifest.content_digest
    assert not first.commits[0][1]["summary"].startswith("{")
    assert first_output.producing_plugin_id == "parser.native-ooxml@1"
    assert first_output.parent_artifact_ids == (first.id,)
    assert first_output.configuration_digest == hashlib.sha256(b"{}").hexdigest()


def test_scanned_ocr_fixture_is_bilingual_and_only_safe_evidence_is_emitted() -> None:
    content = (Path(__file__).parents[1] / "fixtures" / "ingestion" / "scanned-bilingual-ocr.json").read_bytes()
    artifacts, runs = invoke("ocr.scanned-exchange@1", "source.scanned-ocr-exchange", content)
    output, payload = artifacts.commits[0][0][0]
    fixture = ProviderFixture.model_validate_json(payload)
    assert output.artifact_type == "provider.scanned-ocr-result"
    assert [item.text for item in fixture.elements] == ["扫描测试", "English evidence survives OCR."]
    assert fixture.elements[0].locator.kind == "pdf"
    assert fixture.elements[0].locator.page_number == 1
    assert fixture.quality_signals[2].value == "fixture-ocr-v1"
    assert {signal.name for signal in output.quality_signals} == {"layout_detected", "languages_observed", "ocr_model_id", "ocr_confidence_bucket"}
    assert not runs.failures and "credential" not in payload.decode()


class SyntheticConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SyntheticParser:
    async def invoke(self, context: object) -> PluginInvocationResult:
        source = await context.input(context.invocation.inputs[0].id)  # type: ignore[attr-defined]
        payload = {"adapter_id": "parser.synthetic@1", "source_content_digest": source.reference.content_digest, "elements": [{"kind": "paragraph", "reading_order": 0, "locator": {"kind": "word_processing", "heading_anchor": "test", "paragraph_index": 1}, "text": "synthetic"}]}
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="provider.native-ooxml-result", schema_revision="v1", content=json.dumps(payload, sort_keys=True).encode()),))


def test_synthetic_adapter_extends_registry_without_executor_or_normalizer_changes() -> None:
    async def exercise() -> None:
        registry = PluginRegistry(lambda _: True, lambda _: True)
        descriptor = PluginDescriptor(plugin_id="parser.synthetic@1", kind="parser", implementation_digest="f" * 64, runner=RunnerType.IN_PROCESS, configuration_schema=SyntheticConfig.model_json_schema(), input_schemas=(("source.native-ooxml", "v1"),), output_schemas=(("provider.native-ooxml-result", "v1"),), timeout_seconds=1)
        registry.register(descriptor, SyntheticParser, SyntheticConfig)
        artifacts, runs = Artifacts("source.native-ooxml", b"test"), Runs()
        executor = PluginExecutor(registry, {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        await executor.invoke(uuid4(), "synthetic", "parser.synthetic@1", {}, (artifacts.id,))
        assert ProviderFixture.model_validate_json(artifacts.commits[0][0][0][1]).adapter_id == "parser.synthetic@1"
        assert not runs.failures
    asyncio.run(exercise())
