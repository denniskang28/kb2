from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

from kb2_runtime.plugins.bootstrap import bootstrap_registry
from kb2_runtime.plugins.contracts import RunnerType
from kb2_runtime.plugins.executor import PluginExecutor
from kb2_runtime.plugins.runner import InProcessRunner

from kb2_runtime.trace.contracts import ArtifactManifest, SafeError


def native_docx() -> bytes:
    import io
    import zipfile
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        archive.writestr("[Content_Types].xml", b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr("_rels/.rels", b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr("word/document.xml", b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Native integration text.</w:t></w:r></w:p></w:body></w:document>')
    return result.getvalue()


class Runs:
    def __init__(self) -> None:
        self.attempt, self.failures = uuid4(), []

    async def start_attempt(self, run_id: UUID, stage_key: str) -> tuple[UUID, int]:
        return self.attempt, 1

    async def fail_attempt(self, attempt: UUID, error: SafeError, summary: str = "") -> None:
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


def test_native_and_scanned_adapters_normalize_through_registered_schema_specific_plugins() -> None:
    async def chain(source_schema: str, source: bytes, adapter: str, normalizer: str) -> tuple[object, object, object, Runs]:
        source_artifacts, runs = Artifacts(source_schema, source), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, source_artifacts)  # type: ignore[arg-type]
        await executor.invoke(uuid4(), "adapter", adapter, {}, (source_artifacts.id,))
        provider_input = source_artifacts.commits[0][0][0]
        provider_artifacts = Artifacts(provider_input[0].artifact_type, provider_input[1])
        normalizer_executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, provider_artifacts)  # type: ignore[arg-type]
        await normalizer_executor.invoke(uuid4(), "normalize", normalizer, {}, (provider_artifacts.id,))
        return source_artifacts, provider_input, provider_artifacts.commits[0][0][0], runs

    async def exercise() -> tuple[tuple[object, object, object, Runs], tuple[object, object, object, Runs]]:
        ocr = (Path(__file__).parents[1] / "fixtures" / "ingestion" / "scanned-bilingual-ocr.json").read_bytes()
        return await chain("source.native-ooxml", native_docx(), "parser.native-ooxml@1", "normalizer.native-ooxml@1"), await chain("source.scanned-ocr-exchange", ocr, "ocr.scanned-exchange@1", "normalizer.scanned-ocr@1")
    native, scanned = asyncio.run(exercise())
    for source, provider, canonical, runs in (native, scanned):
        assert provider[0].parent_artifact_ids == (source.id,)
        assert canonical[0].artifact_type == "canonical.document"
        assert canonical[0].parent_artifact_ids
        assert not runs.failures
    assert native[1][0].producing_plugin_id == "parser.native-ooxml@1"
    assert native[2][0].producing_plugin_id == "normalizer.native-ooxml@1"
    assert scanned[1][0].producing_plugin_id == "ocr.scanned-exchange@1"
    assert scanned[2][0].producing_plugin_id == "normalizer.scanned-ocr@1"
    scanned_document = json.loads(scanned[2][1])
    assert [item["text"] for item in scanned_document["elements"]] == ["扫描测试", "English evidence survives OCR."]
    assert scanned_document["elements"][0]["locator"]["page_number"] == 1
    assert scanned_document["provenance"]["adapter_id"] == "ocr.scanned-exchange@1"
