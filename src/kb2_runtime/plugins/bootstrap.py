"""Repository-owned Plugin allowlist shared by executor and fixed sidecar."""
from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from .contracts import PluginContext, PluginDescriptor, PluginInvocationResult, PluginOutput, ResourceHints, RunnerType
from .registry import PluginRegistry
from kb2_runtime.canonical.normalizer import CanonicalNormalizer, CanonicalNormalizerConfig
from kb2_runtime.ingestion_adapters import (
    NativeOoxmlParser,
    OcrExchangeConfig,
    ScannedOcrExchangeAdapter,
)
from kb2_runtime.structure import CanonicalStructurePlugin, StructureConfig
from kb2_runtime.chunking import CanonicalChunkerPlugin, ChunkMetadataEnricherPlugin, ChunkerConfig, EnricherConfig
from kb2_runtime.indexing.plugin import HashingEmbeddingPlugin, LocalHybridIndexPlugin, SearchDocumentProjectorPlugin
from kb2_runtime.indexing.contracts import LocalHybridConfig
from kb2_runtime.indexing.embedding import HASHING_IMPLEMENTATION_DIGEST
from kb2_runtime.indexing.hybrid import INDEXER_IMPLEMENTATION_DIGEST


class SyntheticTransformConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    suffix: str = ""


class EmptyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


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


CANONICAL_STRUCTURE_DESCRIPTOR = PluginDescriptor(
    plugin_id="structure.canonical@1", kind="structure", implementation_digest="f" * 64,
    runner=RunnerType.IN_PROCESS, configuration_schema=StructureConfig.model_json_schema(),
    input_schemas=(("canonical.document", "v1"),), output_schemas=(("canonical.document", "v1"),),
    input_ports=({"name": "canonical_document", "artifact_type": "canonical.document", "schema_revision": "v1"},),
    output_ports=({"name": "structured_document", "artifact_type": "canonical.document", "schema_revision": "v1"},),
    quality_signal_names=("structure_validation", "hierarchy_validation", "reading_order_validation", "table_validation"),
    resource_hints=ResourceHints(max_output_bytes=16 * 1024 * 1024),
    timeout_seconds=10,
)


CANONICAL_CHUNKER_DESCRIPTOR = PluginDescriptor(
    plugin_id="chunker.canonical@1", kind="chunker", implementation_digest="1" * 64,
    runner=RunnerType.IN_PROCESS, configuration_schema=ChunkerConfig.model_json_schema(),
    input_schemas=(("canonical.document", "v1"),), output_schemas=(("chunk.set", "v1"),),
    input_ports=({"name": "canonical_document", "artifact_type": "canonical.document", "schema_revision": "v1"},),
    output_ports=({"name": "chunk_set", "artifact_type": "chunk.set", "schema_revision": "v1"},),
    quality_signal_names=("chunk_validation", "citation_validation"), timeout_seconds=10,
)


CHUNK_METADATA_ENRICHER_DESCRIPTOR = PluginDescriptor(
    plugin_id="enricher.chunk-metadata@1", kind="enricher", implementation_digest="2" * 64,
    runner=RunnerType.IN_PROCESS, configuration_schema=EnricherConfig.model_json_schema(),
    input_schemas=(("chunk.set", "v1"),), output_schemas=(("chunk.set", "v1"),),
    input_ports=({"name": "chunk_set", "artifact_type": "chunk.set", "schema_revision": "v1"},),
    output_ports=({"name": "enriched_chunk_set", "artifact_type": "chunk.set", "schema_revision": "v1"},),
    quality_signal_names=("chunk_validation", "citation_validation", "enrichment_validation"), timeout_seconds=10,
)

EMBEDDER_HASHING_DESCRIPTOR = PluginDescriptor(
    plugin_id="embedder.hashing@1", kind="embedder", implementation_digest=HASHING_IMPLEMENTATION_DIGEST,
    runner=RunnerType.IN_PROCESS, configuration_schema=EmptyConfig.model_json_schema(),
    input_schemas=(("chunk.set", "v1"),), output_schemas=(("embedding.set", "v1"),),
    input_ports=({"name": "chunk_set", "artifact_type": "chunk.set", "schema_revision": "v1"},),
    output_ports=({"name": "embedding_set", "artifact_type": "embedding.set", "schema_revision": "v1"},),
    quality_signal_names=("embedding_validation",), timeout_seconds=10,
)

SEARCH_DOCUMENT_PROJECTOR_DESCRIPTOR = PluginDescriptor(
    plugin_id="search-document.projector@1", kind="projector", implementation_digest="5" * 64,
    runner=RunnerType.IN_PROCESS, configuration_schema=EmptyConfig.model_json_schema(),
    input_schemas=(("chunk.set", "v1"), ("embedding.set", "v1")), output_schemas=(("search.document.set", "v1"),),
    input_ports=({"name": "chunk_set", "artifact_type": "chunk.set", "schema_revision": "v1"}, {"name": "embedding_set", "artifact_type": "embedding.set", "schema_revision": "v1"}),
    output_ports=({"name": "search_document_set", "artifact_type": "search.document.set", "schema_revision": "v1"},),
    quality_signal_names=("search_document_validation",), timeout_seconds=10,
)

LOCAL_HYBRID_INDEXER_DESCRIPTOR = PluginDescriptor(
    plugin_id="indexer.local-hybrid@1", kind="indexer", implementation_digest=INDEXER_IMPLEMENTATION_DIGEST,
    runner=RunnerType.IN_PROCESS, configuration_schema=LocalHybridConfig.model_json_schema(),
    input_schemas=(("search.document.set", "v1"),), output_schemas=(("search.index.result", "v1"),),
    input_ports=({"name": "search_document_set", "artifact_type": "search.document.set", "schema_revision": "v1"},),
    output_ports=({"name": "search_index_result", "artifact_type": "search.index.result", "schema_revision": "v1"},),
    quality_signal_names=("index_validation",), timeout_seconds=10,
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
    registry.register(CANONICAL_STRUCTURE_DESCRIPTOR, CanonicalStructurePlugin, StructureConfig)
    registry.register(CANONICAL_CHUNKER_DESCRIPTOR, CanonicalChunkerPlugin, ChunkerConfig)
    registry.register(CHUNK_METADATA_ENRICHER_DESCRIPTOR, ChunkMetadataEnricherPlugin, EnricherConfig)
    registry.register(EMBEDDER_HASHING_DESCRIPTOR, HashingEmbeddingPlugin, EmptyConfig)
    registry.register(SEARCH_DOCUMENT_PROJECTOR_DESCRIPTOR, SearchDocumentProjectorPlugin, EmptyConfig)
    registry.register(LOCAL_HYBRID_INDEXER_DESCRIPTOR, LocalHybridIndexPlugin, LocalHybridConfig)
    return registry
