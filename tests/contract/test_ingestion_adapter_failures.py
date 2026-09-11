from __future__ import annotations

import asyncio
import io
import json
import zipfile
from uuid import uuid4

import pytest

from kb2_runtime.plugins.errors import PluginError, PluginErrorCode
from kb2_runtime.plugins.bootstrap import NATIVE_OOXML_PARSER_DESCRIPTOR, bootstrap_registry
from kb2_runtime.plugins.executor import PluginExecutor
from kb2_runtime.plugins.registry import PluginRegistry
from kb2_runtime.plugins.runner import InProcessRunner
from kb2_runtime.plugins.contracts import PluginContext, PluginInvocationResult, RunnerType
from kb2_runtime.canonical.normalizer import CanonicalNormalizerConfig

from test_ingestion_adapters import Artifacts, Runs, invoke, native_docx


@pytest.mark.parametrize(
    ("plugin_id", "schema", "payload", "configuration", "code"),
    [
        ("parser.native-ooxml@1", "source.native-ooxml", b"not-a-zip", {}, PluginErrorCode.RESULT_INVALID),
        ("ocr.scanned-exchange@1", "source.scanned-ocr-exchange", b'{"model_id":"fixture-ocr-v1","pages":[]}', {}, PluginErrorCode.RESULT_INVALID),
        ("ocr.scanned-exchange@1", "source.scanned-ocr-exchange", json.dumps({"model_id":"missing","pages":[{"page_number":1,"items":[{"order":0,"text":"x","language":"en","bbox":[0,0,1,1],"confidence":1,"layout":"paragraph"}]}]}).encode(), {"model_id": "missing"}, PluginErrorCode.UNAVAILABLE),
    ],
)
def test_invalid_or_unavailable_adapter_inputs_fail_without_commits(plugin_id: str, schema: str, payload: bytes, configuration: dict[str, object], code: PluginErrorCode) -> None:
    async def exercise() -> tuple[Artifacts, Runs]:
        from kb2_runtime.plugins.bootstrap import bootstrap_registry
        from kb2_runtime.plugins.executor import PluginExecutor
        from kb2_runtime.plugins.runner import InProcessRunner
        from kb2_runtime.plugins.contracts import RunnerType
        artifacts, runs = Artifacts(schema, payload), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "failure", plugin_id, configuration, (artifacts.id,))
        assert raised.value.code is code
        return artifacts, runs
    artifacts, runs = asyncio.run(exercise())
    assert not artifacts.commits and len(runs.failures) == 1 and runs.failures[0].code.value == code.value


def test_zip_traversal_is_rejected_before_document_extraction() -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as value:
        value.writestr("../escape.xml", b"x")
        value.writestr("word/document.xml", b"<x/>")
    with pytest.raises(PluginError, match="PLUGIN_RESULT_INVALID"):
        invoke("parser.native-ooxml@1", "source.native-ooxml", archive.getvalue())


def test_incomplete_docx_package_fails_one_trace_attempt_without_provider_output() -> None:
    async def exercise() -> tuple[Artifacts, Runs]:
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as value:
            value.writestr("[Content_Types].xml", b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
            value.writestr("word/document.xml", b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>')
        artifacts, runs = Artifacts("source.native-ooxml", archive.getvalue()), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "parse", "parser.native-ooxml@1", {}, (artifacts.id,))
        assert raised.value.code is PluginErrorCode.RESULT_INVALID
        return artifacts, runs
    artifacts, runs = asyncio.run(exercise())
    assert not artifacts.commits
    assert runs.failed_attempt_ids == [runs.attempt]
    assert runs.failures[0].code.value == PluginErrorCode.RESULT_INVALID.value
    assert runs.failure_summaries == [""]


def test_invalid_wordprocessingml_root_with_embedded_paragraph_fails_without_outputs() -> None:
    async def exercise() -> tuple[Artifacts, Runs]:
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as value:
            value.writestr("[Content_Types].xml", b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
            value.writestr("_rels/.rels", b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
            value.writestr("word/document.xml", b'<invalid xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>must not parse</w:t></w:r></w:p></invalid>')
        artifacts, runs = Artifacts("source.native-ooxml", archive.getvalue()), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "parse", "parser.native-ooxml@1", {}, (artifacts.id,))
        assert raised.value.code is PluginErrorCode.RESULT_INVALID
        return artifacts, runs
    artifacts, runs = asyncio.run(exercise())
    assert not artifacts.commits
    assert runs.failed_attempt_ids == [runs.attempt]
    assert [failure.code for failure in runs.failures] == [PluginErrorCode.RESULT_INVALID]


class SlowNativeParser:
    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        await asyncio.sleep(.05)
        raise AssertionError("the runner should cancel or time out first")


class CrashNativeParser:
    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        raise RuntimeError("credential canary must not enter trace evidence")


class InvalidProviderNativeParser:
    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        from kb2_runtime.ingestion_adapters.adapters import _provider_bytes
        source = await context.input(context.invocation.inputs[0].id)
        _provider_bytes({"adapter_id": "parser.native-ooxml@1", "source_content_digest": source.reference.content_digest, "elements": []})
        raise AssertionError("provider validation should fail before this point")


def _native_executor(implementation: type[object], *, timeout_seconds: float = 1) -> tuple[PluginExecutor, Artifacts, Runs]:
    registry = PluginRegistry(lambda _: True, lambda _: True)
    registry.register(NATIVE_OOXML_PARSER_DESCRIPTOR.model_copy(update={"timeout_seconds": timeout_seconds}), implementation, CanonicalNormalizerConfig)  # type: ignore[arg-type]
    artifacts, runs = Artifacts("source.native-ooxml", native_docx()), Runs()
    return PluginExecutor(registry, {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts), artifacts, runs  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("implementation", "timeout_seconds", "expected"),
    [
        (CrashNativeParser, 1, PluginErrorCode.CRASHED),
        (InvalidProviderNativeParser, 1, PluginErrorCode.RESULT_INVALID),
        (SlowNativeParser, .001, PluginErrorCode.TIMEOUT),
    ],
)
def test_adapter_terminal_failures_persist_one_safe_trace_without_outputs(
    implementation: type[object], timeout_seconds: float, expected: PluginErrorCode
) -> None:
    async def exercise() -> tuple[Artifacts, Runs]:
        executor, artifacts, runs = _native_executor(implementation, timeout_seconds=timeout_seconds)
        run_id = uuid4()
        with pytest.raises(PluginError) as raised:
            await executor.invoke(run_id, "adapter", "parser.native-ooxml@1", {}, (artifacts.id,))
        assert raised.value.code is expected
        assert runs.started == [(run_id, "adapter")]
        return artifacts, runs
    artifacts, runs = asyncio.run(exercise())
    assert not artifacts.commits
    assert runs.failed_attempt_ids == [runs.attempt]
    assert [item.code.value for item in runs.failures] == [expected.value]
    assert runs.failures[0].message == "plugin invocation failed"
    assert "credential" not in runs.failures[0].message
    assert "canary" not in runs.failures[0].message


def test_midflight_adapter_cancellation_persists_one_failed_trace_without_output() -> None:
    async def exercise() -> tuple[Artifacts, Runs]:
        executor, artifacts, runs = _native_executor(SlowNativeParser)
        token = asyncio.Event()
        task = asyncio.create_task(executor.invoke(uuid4(), "adapter", "parser.native-ooxml@1", {}, (artifacts.id,), token))
        await asyncio.sleep(.005)
        token.set()
        with pytest.raises(PluginError) as raised:
            await task
        assert raised.value.code is PluginErrorCode.CANCELLED
        return artifacts, runs
    artifacts, runs = asyncio.run(exercise())
    assert not artifacts.commits
    assert runs.failed_attempt_ids == [runs.attempt]
    assert [item.code.value for item in runs.failures] == [PluginErrorCode.CANCELLED.value]


def test_pre_cancelled_adapter_execution_fails_once_without_committing() -> None:
    async def exercise() -> None:
        from kb2_runtime.plugins.bootstrap import bootstrap_registry
        from kb2_runtime.plugins.executor import PluginExecutor
        from kb2_runtime.plugins.contracts import RunnerType
        from kb2_runtime.plugins.runner import InProcessRunner
        token = asyncio.Event()
        token.set()
        artifacts, runs = Artifacts("source.native-ooxml", b"not-a-zip"), Runs()
        executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)  # type: ignore[arg-type]
        with pytest.raises(PluginError) as raised:
            await executor.invoke(uuid4(), "cancel", "parser.native-ooxml@1", {}, (artifacts.id,), token)
        assert raised.value.code is PluginErrorCode.CANCELLED
        assert not artifacts.commits and len(runs.failures) == 1
    asyncio.run(exercise())
