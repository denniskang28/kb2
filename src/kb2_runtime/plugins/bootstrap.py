"""Repository-owned Plugin allowlist shared by executor and fixed sidecar."""
from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from .contracts import PluginContext, PluginDescriptor, PluginInvocationResult, PluginOutput, RunnerType
from .registry import PluginRegistry
from kb2_runtime.canonical.normalizer import CanonicalNormalizer, CanonicalNormalizerConfig
from kb2_runtime.ingestion_adapters import (
    NativeOoxmlParser,
    OcrExchangeConfig,
    ScannedOcrExchangeAdapter,
)


class SyntheticTransformConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    suffix: str = ""


class SyntheticTransform:
    """Deterministic contract plugin; it is not a production parser or model."""
    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        source = await context.input(context.invocation.inputs[0].id)
        suffix = context.invocation.validated_configuration["suffix"].encode("utf-8")
        return PluginInvocationResult(
            outputs=(PluginOutput(artifact_type="opaque.bytes", schema_revision="v1", content=source.content + suffix),),
            summary="synthetic transform completed",
        )


SYNTHETIC_TRANSFORM_DESCRIPTOR = PluginDescriptor(
    plugin_id="transform.synthetic@1",
    kind="transform",
    implementation_digest="a" * 64,
    runner=RunnerType.CONTAINER,
    configuration_schema=SyntheticTransformConfig.model_json_schema(),
    input_schemas=(("opaque.bytes", "v1"),),
    output_schemas=(("opaque.bytes", "v1"),),
    input_ports=({"name": "source", "artifact_type": "opaque.bytes", "schema_revision": "v1"},),
    output_ports=({"name": "result", "artifact_type": "opaque.bytes", "schema_revision": "v1"},),
    timeout_seconds=10,
)


CANONICAL_NORMALIZER_DESCRIPTOR = PluginDescriptor(
    plugin_id="normalizer.canonical@1",
    kind="normalizer",
    implementation_digest="c" * 64,
    runner=RunnerType.IN_PROCESS,
    configuration_schema=CanonicalNormalizerConfig.model_json_schema(),
    input_schemas=(("provider.parse-result-fixture", "v1"),),
    output_schemas=(("canonical.document", "v1"),),
    input_ports=({"name": "provider_result", "artifact_type": "provider.parse-result-fixture", "schema_revision": "v1"},),
    output_ports=({"name": "canonical_document", "artifact_type": "canonical.document", "schema_revision": "v1"},),
    timeout_seconds=10,
)


NATIVE_OOXML_PARSER_DESCRIPTOR = PluginDescriptor(
    plugin_id="parser.native-ooxml@1", kind="parser", implementation_digest="d" * 64,
    runner=RunnerType.IN_PROCESS, configuration_schema=CanonicalNormalizerConfig.model_json_schema(),
    input_schemas=(("source.native-ooxml", "v1"),), output_schemas=(("provider.native-ooxml-result", "v1"),),
    input_ports=({"name": "source", "artifact_type": "source.native-ooxml", "schema_revision": "v1"},),
    output_ports=({"name": "provider_result", "artifact_type": "provider.native-ooxml-result", "schema_revision": "v1"},),
    quality_signal_names=("layout_detected", "languages_observed"), timeout_seconds=10,
)


SCANNED_OCR_EXCHANGE_DESCRIPTOR = PluginDescriptor(
    plugin_id="ocr.scanned-exchange@1", kind="ocr", implementation_digest="e" * 64,
    runner=RunnerType.IN_PROCESS, configuration_schema=OcrExchangeConfig.model_json_schema(),
    input_schemas=(("source.scanned-ocr-exchange", "v1"),), output_schemas=(("provider.scanned-ocr-result", "v1"),),
    input_ports=({"name": "source", "artifact_type": "source.scanned-ocr-exchange", "schema_revision": "v1"},),
    output_ports=({"name": "provider_result", "artifact_type": "provider.scanned-ocr-result", "schema_revision": "v1"},),
    quality_signal_names=("layout_detected", "languages_observed", "ocr_model_id", "ocr_confidence_bucket"), timeout_seconds=10,
)


NATIVE_OOXML_NORMALIZER_DESCRIPTOR = PluginDescriptor(
    plugin_id="normalizer.native-ooxml@1", kind="normalizer", implementation_digest="c" * 64,
    runner=RunnerType.IN_PROCESS, configuration_schema=CanonicalNormalizerConfig.model_json_schema(),
    input_schemas=(("provider.native-ooxml-result", "v1"),), output_schemas=(("canonical.document", "v1"),),
    input_ports=({"name": "provider_result", "artifact_type": "provider.native-ooxml-result", "schema_revision": "v1"},),
    output_ports=({"name": "canonical_document", "artifact_type": "canonical.document", "schema_revision": "v1"},), timeout_seconds=10,
)


SCANNED_OCR_NORMALIZER_DESCRIPTOR = PluginDescriptor(
    plugin_id="normalizer.scanned-ocr@1", kind="normalizer", implementation_digest="c" * 64,
    runner=RunnerType.IN_PROCESS, configuration_schema=CanonicalNormalizerConfig.model_json_schema(),
    input_schemas=(("provider.scanned-ocr-result", "v1"),), output_schemas=(("canonical.document", "v1"),),
    input_ports=({"name": "provider_result", "artifact_type": "provider.scanned-ocr-result", "schema_revision": "v1"},),
    output_ports=({"name": "canonical_document", "artifact_type": "canonical.document", "schema_revision": "v1"},), timeout_seconds=10,
)


def bootstrap_registry(
    capability_check: Callable[[str], bool] = lambda _: True,
    runner_ready: Callable[[RunnerType], bool] = lambda _: True,
) -> PluginRegistry:
    registry = PluginRegistry(capability_check, runner_ready)
    registry.register(SYNTHETIC_TRANSFORM_DESCRIPTOR, SyntheticTransform, SyntheticTransformConfig)
    registry.register(CANONICAL_NORMALIZER_DESCRIPTOR, CanonicalNormalizer, CanonicalNormalizerConfig)
    registry.register(NATIVE_OOXML_PARSER_DESCRIPTOR, NativeOoxmlParser, CanonicalNormalizerConfig)
    registry.register(SCANNED_OCR_EXCHANGE_DESCRIPTOR, ScannedOcrExchangeAdapter, OcrExchangeConfig)
    registry.register(NATIVE_OOXML_NORMALIZER_DESCRIPTOR, CanonicalNormalizer, CanonicalNormalizerConfig)
    registry.register(SCANNED_OCR_NORMALIZER_DESCRIPTOR, CanonicalNormalizer, CanonicalNormalizerConfig)
    return registry
