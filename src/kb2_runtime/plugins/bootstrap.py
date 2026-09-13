"""Repository-owned Plugin allowlist shared by executor and fixed sidecar."""
from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from .contracts import PluginContext, PluginDescriptor, PluginInvocationResult, PluginOutput, ResourceHints, RunnerType
from .registry import PluginRegistry
from kb2_runtime.canonical.normalizer import MAX_PROVIDER_FIXTURE_BYTES, CanonicalNormalizer, CanonicalNormalizerConfig
from kb2_runtime.ingestion_adapters import (
    LocalPdfParser,
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
from kb2_runtime.retrieval.contracts import HierarchyRetrieverConfig, RetrieverConfig
from kb2_runtime.retrieval.plugin import hierarchy_plugin, keyword_plugin, metadata_plugin, table_plugin, vector_plugin
from kb2_runtime.fusion.contracts import FusionConfig
from kb2_runtime.fusion.plugin import FusionPlugin
from kb2_runtime.reranking.contracts import RerankerConfig
from kb2_runtime.reranking.plugin import RerankingPlugin
from kb2_runtime.evidence.contracts import ContextAssemblerConfig
from kb2_runtime.evidence.plugin import ContextAssemblerPlugin
from kb2_runtime.generation import DeepSeekGenerator, DefaultGenerationConfig, FinalStatePlugin, GenerationConfig, HighPrecisionGenerationConfig, LocalVerifier, RepairConfig, VerificationConfig
from kb2_runtime.generation.contracts import FinalStateConfig
from kb2_runtime.evaluation.ingestion import IngestionMetricPlugin, METRICS
from kb2_runtime.evaluation.retrieval import RetrievalMetricConfig, RetrievalMetricPlugin
from kb2_runtime.evaluation.answer import AnswerMetricConfig, AnswerMetricPlugin, CITATION_METRICS, DECISION_METRICS, FACT_METRICS
from kb2_runtime.evaluation.judges import DeepSeekJudge, JudgeConfig


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
    resource_hints=ResourceHints(max_output_bytes=MAX_PROVIDER_FIXTURE_BYTES), timeout_seconds=10,
)


NATIVE_OOXML_PARSER_DESCRIPTOR = PluginDescriptor(
    plugin_id="parser.native-ooxml@1", kind="parser", implementation_digest="d" * 64,
    runner=RunnerType.IN_PROCESS, configuration_schema=CanonicalNormalizerConfig.model_json_schema(),
    input_schemas=(("source.native-ooxml", "v1"),), output_schemas=(("provider.native-ooxml-result", "v1"),),
    input_ports=({"name": "source", "artifact_type": "source.native-ooxml", "schema_revision": "v1"},),
    output_ports=({"name": "provider_result", "artifact_type": "provider.native-ooxml-result", "schema_revision": "v1"},),
    quality_signal_names=("layout_detected", "languages_observed"), timeout_seconds=10,
)


LOCAL_PDF_PARSER_DESCRIPTOR = PluginDescriptor(
    plugin_id="parser.local-pdf@1", kind="parser", implementation_digest="4" * 64,
    runner=RunnerType.IN_PROCESS, configuration_schema=CanonicalNormalizerConfig.model_json_schema(),
    input_schemas=(("opaque.bytes", "v1"),), output_schemas=(("provider.parse-result-fixture", "v1"),),
    input_ports=({"name": "source", "artifact_type": "opaque.bytes", "schema_revision": "v1"},),
    output_ports=({"name": "provider_result", "artifact_type": "provider.parse-result-fixture", "schema_revision": "v1"},),
    quality_signal_names=("layout_detected", "languages_observed"),
    resource_hints=ResourceHints(max_output_bytes=MAX_PROVIDER_FIXTURE_BYTES), timeout_seconds=30,
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
    quality_signal_names=("chunk_validation", "citation_validation"), resource_hints=ResourceHints(max_output_bytes=16 * 1024 * 1024), timeout_seconds=10,
)


CHUNK_METADATA_ENRICHER_DESCRIPTOR = PluginDescriptor(
    plugin_id="enricher.chunk-metadata@1", kind="enricher", implementation_digest="2" * 64,
    runner=RunnerType.IN_PROCESS, configuration_schema=EnricherConfig.model_json_schema(),
    input_schemas=(("chunk.set", "v1"),), output_schemas=(("chunk.set", "v1"),),
    input_ports=({"name": "chunk_set", "artifact_type": "chunk.set", "schema_revision": "v1"},),
    output_ports=({"name": "enriched_chunk_set", "artifact_type": "chunk.set", "schema_revision": "v1"},),
    quality_signal_names=("chunk_validation", "citation_validation", "enrichment_validation"), resource_hints=ResourceHints(max_output_bytes=16 * 1024 * 1024), timeout_seconds=10,
)

EMBEDDER_HASHING_DESCRIPTOR = PluginDescriptor(
    plugin_id="embedder.hashing@1", kind="embedder", implementation_digest=HASHING_IMPLEMENTATION_DIGEST,
    runner=RunnerType.IN_PROCESS, configuration_schema=EmptyConfig.model_json_schema(),
    input_schemas=(("chunk.set", "v1"),), output_schemas=(("embedding.set", "v1"),),
    input_ports=({"name": "chunk_set", "artifact_type": "chunk.set", "schema_revision": "v1"},),
    output_ports=({"name": "embedding_set", "artifact_type": "embedding.set", "schema_revision": "v1"},),
    quality_signal_names=("embedding_validation",), resource_hints=ResourceHints(max_output_bytes=16 * 1024 * 1024), timeout_seconds=10,
)

SEARCH_DOCUMENT_PROJECTOR_DESCRIPTOR = PluginDescriptor(
    plugin_id="search-document.projector@1", kind="projector", implementation_digest="5" * 64,
    runner=RunnerType.IN_PROCESS, configuration_schema=EmptyConfig.model_json_schema(),
    input_schemas=(("chunk.set", "v1"), ("embedding.set", "v1")), output_schemas=(("search.document.set", "v1"),),
    input_ports=({"name": "chunk_set", "artifact_type": "chunk.set", "schema_revision": "v1"}, {"name": "embedding_set", "artifact_type": "embedding.set", "schema_revision": "v1"}),
    output_ports=({"name": "search_document_set", "artifact_type": "search.document.set", "schema_revision": "v1"},),
    quality_signal_names=("search_document_validation",), resource_hints=ResourceHints(max_output_bytes=16 * 1024 * 1024), timeout_seconds=10,
)

LOCAL_HYBRID_INDEXER_DESCRIPTOR = PluginDescriptor(
    plugin_id="indexer.local-hybrid@1", kind="indexer", implementation_digest=INDEXER_IMPLEMENTATION_DIGEST,
    runner=RunnerType.IN_PROCESS, configuration_schema=LocalHybridConfig.model_json_schema(),
    input_schemas=(("search.document.set", "v1"),), output_schemas=(("search.index.result", "v1"),),
    input_ports=({"name": "search_document_set", "artifact_type": "search.document.set", "schema_revision": "v1"},),
    output_ports=({"name": "search_index_result", "artifact_type": "search.index.result", "schema_revision": "v1"},),
    quality_signal_names=("index_validation",), resource_hints=ResourceHints(max_output_bytes=16 * 1024 * 1024), timeout_seconds=10,
)


def _retriever_descriptor(plugin_id: str, digest: str, configuration: type[BaseModel]) -> PluginDescriptor:
    return PluginDescriptor(
        plugin_id=plugin_id, kind="retriever", implementation_digest=digest, runner=RunnerType.IN_PROCESS,
        configuration_schema=configuration.model_json_schema(),
        input_schemas=(("opaque.bytes", "v1"), ("search.index.result", "v1")),
        output_schemas=(("retrieval.candidate.set", "v1"),),
        input_ports=({"name": "question", "artifact_type": "opaque.bytes", "schema_revision": "v1"}, {"name": "index", "artifact_type": "search.index.result", "schema_revision": "v1"}),
        output_ports=({"name": "candidates", "artifact_type": "retrieval.candidate.set", "schema_revision": "v1"},),
        quality_signal_names=("retrieval_validation", "retrieval_strategy", "no_candidates"), timeout_seconds=10,
    )


RETRIEVER_KEYWORD_DESCRIPTOR = _retriever_descriptor("retriever.keyword@1", "6" * 64, RetrieverConfig)
RETRIEVER_VECTOR_DESCRIPTOR = _retriever_descriptor("retriever.vector@1", "7" * 64, RetrieverConfig)
RETRIEVER_HIERARCHY_DESCRIPTOR = _retriever_descriptor("retriever.hierarchy@1", "8" * 64, HierarchyRetrieverConfig)
RETRIEVER_TABLE_DESCRIPTOR = _retriever_descriptor("retriever.table@1", "9" * 64, RetrieverConfig)
RETRIEVER_METADATA_DESCRIPTOR = _retriever_descriptor("retriever.metadata@1", "a" * 64, RetrieverConfig)

FUSION_RRF_DESCRIPTOR = PluginDescriptor(
    plugin_id="fusion.reciprocal-rank@1", kind="fusion", implementation_digest="b" * 64,
    runner=RunnerType.IN_PROCESS, configuration_schema=FusionConfig.model_json_schema(),
    input_schemas=(("retrieval.candidate.set", "v1"),), output_schemas=(("fusion.candidate.set", "v1"),),
    input_ports=({"name": "candidate_sets", "artifact_type": "retrieval.candidate.set", "schema_revision": "v1", "min_items": 1, "max_items": 8},),
    output_ports=({"name": "fused_candidates", "artifact_type": "fusion.candidate.set", "schema_revision": "v1"},),
    quality_signal_names=("fusion_validation", "no_candidates"), timeout_seconds=10,
)
RERANKER_LEXICAL_DESCRIPTOR = PluginDescriptor(
    plugin_id="reranker.lexical-overlap@1", kind="reranker", implementation_digest="c" * 64,
    runner=RunnerType.IN_PROCESS, configuration_schema=RerankerConfig.model_json_schema(),
    input_schemas=(("opaque.bytes", "v1"), ("fusion.candidate.set", "v1"), ("search.index.result", "v1")), output_schemas=(("rerank.candidate.set", "v1"),),
    input_ports=({"name": "question", "artifact_type": "opaque.bytes", "schema_revision": "v1"}, {"name": "fused_candidates", "artifact_type": "fusion.candidate.set", "schema_revision": "v1"}, {"name": "index", "artifact_type": "search.index.result", "schema_revision": "v1"}),
    output_ports=({"name": "reranked_candidates", "artifact_type": "rerank.candidate.set", "schema_revision": "v1"},),
    quality_signal_names=("rerank_validation", "no_candidates"), timeout_seconds=10,
)


def _context_descriptor(plugin_id: str, candidate_type: str, digest: str) -> PluginDescriptor:
    return PluginDescriptor(
        plugin_id=plugin_id, kind="context", implementation_digest=digest, runner=RunnerType.IN_PROCESS,
        configuration_schema=ContextAssemblerConfig.model_json_schema(),
        input_schemas=((candidate_type, "v1"), ("search.index.result", "v1")), output_schemas=(("evidence.set", "v1"),),
        input_ports=({"name": "candidates", "artifact_type": candidate_type, "schema_revision": "v1"}, {"name": "index", "artifact_type": "search.index.result", "schema_revision": "v1"}),
        output_ports=({"name": "evidence", "artifact_type": "evidence.set", "schema_revision": "v1"},),
        quality_signal_names=("context_validation", "context_shortage"), timeout_seconds=10,
    )


CONTEXT_FROM_RETRIEVAL_DESCRIPTOR = _context_descriptor("context.from-retrieval@1", "retrieval.candidate.set", "d" * 64)
CONTEXT_FROM_FUSION_DESCRIPTOR = _context_descriptor("context.from-fusion@1", "fusion.candidate.set", "e" * 64)
CONTEXT_FROM_RERANK_DESCRIPTOR = _context_descriptor("context.from-rerank@1", "rerank.candidate.set", "f" * 64)

GENERATOR_DEEPSEEK_DESCRIPTOR = PluginDescriptor(
    plugin_id="generator.deepseek@1", kind="generate", implementation_digest="1" * 64,
    runner=RunnerType.IN_PROCESS, configuration_schema=DefaultGenerationConfig.model_json_schema(),
    input_schemas=(("opaque.bytes", "v1"), ("evidence.set", "v1")), output_schemas=(("generated.answer", "v1"),),
    input_ports=({"name": "question", "artifact_type": "opaque.bytes", "schema_revision": "v1"}, {"name": "evidence", "artifact_type": "evidence.set", "schema_revision": "v1"}),
    output_ports=({"name": "answer", "artifact_type": "generated.answer", "schema_revision": "v1"},),
    quality_signal_names=("generation_validation",), capabilities=("generation.default",), timeout_seconds=30,
)
GENERATOR_DEEPSEEK_HIGH_PRECISION_DESCRIPTOR = GENERATOR_DEEPSEEK_DESCRIPTOR.model_copy(update={
    "plugin_id": "generator.deepseek-high-precision@1", "implementation_digest": "2" * 64, "capabilities": ("generation.high_precision",), "configuration_schema": HighPrecisionGenerationConfig.model_json_schema(),
})
JUDGE_DEEPSEEK_DESCRIPTOR = PluginDescriptor(
    plugin_id="judge.deepseek@1", kind="judge", implementation_digest="9" * 64,
    runner=RunnerType.IN_PROCESS, configuration_schema=JudgeConfig.model_json_schema(),
    input_schemas=(("judge.calibration.snapshot", "v1"), ("evidence.set", "v1"), ("final.response", "v1")),
    output_schemas=(("judge.result", "v1"),),
    input_ports=(
        {"name": "calibration_snapshot", "artifact_type": "judge.calibration.snapshot", "schema_revision": "v1"},
        {"name": "reviewed_evidence", "artifact_type": "evidence.set", "schema_revision": "v1"},
        {"name": "final_response", "artifact_type": "final.response", "schema_revision": "v1"},
    ), output_ports=({"name": "result", "artifact_type": "judge.result", "schema_revision": "v1"},),
    capabilities=("judge.semantic",), timeout_seconds=30,
)
VERIFIER_GROUNDED_DESCRIPTOR = PluginDescriptor(
    plugin_id="verifier.grounded@1", kind="verify", implementation_digest="3" * 64,
    runner=RunnerType.IN_PROCESS, configuration_schema=VerificationConfig.model_json_schema(),
    input_schemas=(("generated.answer", "v1"), ("evidence.set", "v1")), output_schemas=(("verification.result", "v1"),),
    input_ports=({"name": "answer", "artifact_type": "generated.answer", "schema_revision": "v1"}, {"name": "evidence", "artifact_type": "evidence.set", "schema_revision": "v1"}),
    output_ports=({"name": "verification", "artifact_type": "verification.result", "schema_revision": "v1"},),
    quality_signal_names=("verification_validation",), timeout_seconds=10,
)
FINAL_STATE_DESCRIPTOR = PluginDescriptor(
    plugin_id="query.final-state@1", kind="final_state", implementation_digest="4" * 64,
    runner=RunnerType.IN_PROCESS, configuration_schema=FinalStateConfig.model_json_schema(),
    input_schemas=(("evidence.set", "v1"), ("verification.result", "v1"), ("generated.answer", "v1")), output_schemas=(("final.response", "v1"),),
    input_ports=({"name": "evidence", "artifact_type": "evidence.set", "schema_revision": "v1"}, {"name": "verification", "artifact_type": "verification.result", "schema_revision": "v1", "min_items": 0}, {"name": "answer", "artifact_type": "generated.answer", "schema_revision": "v1", "min_items": 0}),
    output_ports=({"name": "response", "artifact_type": "final.response", "schema_revision": "v1"},),
    quality_signal_names=("final_state_validation",), timeout_seconds=10,
)
REPAIR_CONTROL_DESCRIPTOR = PluginDescriptor(
    plugin_id="query.repair-control@1", kind="repair", implementation_digest="5" * 64,
    runner=RunnerType.IN_PROCESS, configuration_schema=RepairConfig.model_json_schema(),
    input_schemas=(("evidence.set", "v1"), ("generated.answer", "v1"), ("verification.result", "v1")), output_schemas=(("generated.answer", "v1"), ("verification.result", "v1")),
    input_ports=({"name": "evidence", "artifact_type": "evidence.set", "schema_revision": "v1"}, {"name": "answer", "artifact_type": "generated.answer", "schema_revision": "v1"}, {"name": "verification", "artifact_type": "verification.result", "schema_revision": "v1"}),
    output_ports=({"name": "answer", "artifact_type": "generated.answer", "schema_revision": "v1"}, {"name": "verification", "artifact_type": "verification.result", "schema_revision": "v1"}),
    quality_signal_names=("repair_validation",), timeout_seconds=10,
)


def _metric_descriptor(plugin_id: str, evidence: bool) -> PluginDescriptor:
    observed = "chunk.set" if evidence else "canonical.document"
    return PluginDescriptor(
        plugin_id=plugin_id, kind="metric", implementation_digest="6" * 64,
        runner=RunnerType.IN_PROCESS, configuration_schema=EmptyConfig.model_json_schema(),
        input_schemas=(("golden.dataset.snapshot", "v1"), ("canonical.document", "v1"), (observed, "v1")),
        output_schemas=(("metric.report", "v1"),),
        input_ports=(
            {"name": "snapshot", "artifact_type": "golden.dataset.snapshot", "schema_revision": "v1"},
            {"name": "expected_document", "artifact_type": "canonical.document", "schema_revision": "v1"},
            {"name": "observed_output", "artifact_type": observed, "schema_revision": "v1"},
        ), output_ports=({"name": "report", "artifact_type": "metric.report", "schema_revision": "v1"},), timeout_seconds=10,
    )


INGESTION_METRIC_DESCRIPTORS = tuple(_metric_descriptor(metric_id, metric_id.endswith("evidence-preservation@1")) for metric_id in METRICS)


def _retrieval_metric_descriptor(metric_id: str, source: str) -> PluginDescriptor:
    return PluginDescriptor(
        plugin_id=metric_id, kind="metric", implementation_digest="7" * 64,
        runner=RunnerType.IN_PROCESS, configuration_schema=RetrievalMetricConfig.model_json_schema(),
        input_schemas=(("golden.dataset.snapshot", "v1"), ("evidence.set", "v1"), (source, "v1")),
        output_schemas=(("metric.report", "v1"),),
        input_ports=(
            {"name": "snapshot", "artifact_type": "golden.dataset.snapshot", "schema_revision": "v1"},
            {"name": "label_evidence", "artifact_type": "evidence.set", "schema_revision": "v1"},
            {"name": "measured_stage", "artifact_type": source, "schema_revision": "v1"},
        ), output_ports=({"name": "report", "artifact_type": "metric.report", "schema_revision": "v1"},),
        resource_hints=ResourceHints(max_output_bytes=16 * 1024 * 1024), timeout_seconds=10,
    )


RETRIEVAL_METRIC_DESCRIPTORS = tuple(
    _retrieval_metric_descriptor(f"metric.retrieval.{('hit' if family == 'evidence-hit-rate' else family)}.from-{source.split('.')[0]}@1", source)
    for family in ("recall", "mrr", "ndcg", "evidence-hit-rate")
    for source in ("retrieval.candidate.set", "fusion.candidate.set", "rerank.candidate.set")
) + tuple(
    _retrieval_metric_descriptor(f"metric.context.{family}.from-evidence@1", "evidence.set")
    for family in ("precision", "recall")
)


def _answer_metric_descriptor(metric_id: str, decision: bool = False) -> PluginDescriptor:
    inputs = (("golden.dataset.snapshot", "v1"), ("evidence.set", "v1"), ("final.response", "v1")) if decision else (
        ("golden.dataset.snapshot", "v1"), ("evidence.set", "v1"), ("generated.answer", "v1"), ("verification.result", "v1"), ("final.response", "v1"),
    )
    names = ("snapshot", "label_evidence", "final_response") if decision else ("snapshot", "label_evidence", "generated_answer", "verification", "final_response")
    return PluginDescriptor(
        plugin_id=metric_id, kind="metric", implementation_digest="8" * 64, runner=RunnerType.IN_PROCESS,
        configuration_schema=AnswerMetricConfig.model_json_schema(), input_schemas=inputs,
        output_schemas=(("metric.report", "v1"),),
        input_ports=tuple({"name": name, "artifact_type": schema[0], "schema_revision": schema[1]} for name, schema in zip(names, inputs)),
        output_ports=({"name": "report", "artifact_type": "metric.report", "schema_revision": "v1"},), timeout_seconds=10,
    )


ANSWER_METRIC_DESCRIPTORS = tuple(_answer_metric_descriptor(metric_id) for metric_id in sorted(FACT_METRICS | CITATION_METRICS)) + tuple(
    _answer_metric_descriptor(metric_id, decision=True) for metric_id in sorted(DECISION_METRICS)
)


def bootstrap_registry(
    capability_check: Callable[[str], bool] = lambda _: True,
    runner_ready: Callable[[RunnerType], bool] = lambda _: True,
) -> PluginRegistry:
    registry = PluginRegistry(capability_check, runner_ready)
    registry.register(SYNTHETIC_TRANSFORM_DESCRIPTOR, SyntheticTransform, SyntheticTransformConfig)
    registry.register(CANONICAL_NORMALIZER_DESCRIPTOR, CanonicalNormalizer, CanonicalNormalizerConfig)
    registry.register(NATIVE_OOXML_PARSER_DESCRIPTOR, NativeOoxmlParser, CanonicalNormalizerConfig)
    registry.register(LOCAL_PDF_PARSER_DESCRIPTOR, LocalPdfParser, CanonicalNormalizerConfig)
    registry.register(SCANNED_OCR_EXCHANGE_DESCRIPTOR, ScannedOcrExchangeAdapter, OcrExchangeConfig)
    registry.register(NATIVE_OOXML_NORMALIZER_DESCRIPTOR, CanonicalNormalizer, CanonicalNormalizerConfig)
    registry.register(SCANNED_OCR_NORMALIZER_DESCRIPTOR, CanonicalNormalizer, CanonicalNormalizerConfig)
    registry.register(CANONICAL_STRUCTURE_DESCRIPTOR, CanonicalStructurePlugin, StructureConfig)
    registry.register(CANONICAL_CHUNKER_DESCRIPTOR, CanonicalChunkerPlugin, ChunkerConfig)
    registry.register(CHUNK_METADATA_ENRICHER_DESCRIPTOR, ChunkMetadataEnricherPlugin, EnricherConfig)
    registry.register(EMBEDDER_HASHING_DESCRIPTOR, HashingEmbeddingPlugin, EmptyConfig)
    registry.register(SEARCH_DOCUMENT_PROJECTOR_DESCRIPTOR, SearchDocumentProjectorPlugin, EmptyConfig)
    registry.register(LOCAL_HYBRID_INDEXER_DESCRIPTOR, LocalHybridIndexPlugin, LocalHybridConfig)
    registry.register(RETRIEVER_KEYWORD_DESCRIPTOR, keyword_plugin, RetrieverConfig)
    registry.register(RETRIEVER_VECTOR_DESCRIPTOR, vector_plugin, RetrieverConfig)
    registry.register(RETRIEVER_HIERARCHY_DESCRIPTOR, hierarchy_plugin, HierarchyRetrieverConfig)
    registry.register(RETRIEVER_TABLE_DESCRIPTOR, table_plugin, RetrieverConfig)
    registry.register(RETRIEVER_METADATA_DESCRIPTOR, metadata_plugin, RetrieverConfig)
    registry.register(FUSION_RRF_DESCRIPTOR, FusionPlugin, FusionConfig)
    registry.register(RERANKER_LEXICAL_DESCRIPTOR, RerankingPlugin, RerankerConfig)
    registry.register(CONTEXT_FROM_RETRIEVAL_DESCRIPTOR, lambda: ContextAssemblerPlugin("retrieval.candidate.set"), ContextAssemblerConfig)
    registry.register(CONTEXT_FROM_FUSION_DESCRIPTOR, lambda: ContextAssemblerPlugin("fusion.candidate.set"), ContextAssemblerConfig)
    registry.register(CONTEXT_FROM_RERANK_DESCRIPTOR, lambda: ContextAssemblerPlugin("rerank.candidate.set"), ContextAssemblerConfig)
    registry.register(GENERATOR_DEEPSEEK_DESCRIPTOR, DeepSeekGenerator, DefaultGenerationConfig)
    registry.register(GENERATOR_DEEPSEEK_HIGH_PRECISION_DESCRIPTOR, DeepSeekGenerator, HighPrecisionGenerationConfig)
    registry.register(JUDGE_DEEPSEEK_DESCRIPTOR, DeepSeekJudge, JudgeConfig)
    registry.register(VERIFIER_GROUNDED_DESCRIPTOR, LocalVerifier, VerificationConfig)
    registry.register(FINAL_STATE_DESCRIPTOR, FinalStatePlugin, FinalStateConfig)
    registry.register(REPAIR_CONTROL_DESCRIPTOR, FinalStatePlugin, RepairConfig)
    for descriptor in INGESTION_METRIC_DESCRIPTORS:
        registry.register(descriptor, lambda descriptor=descriptor: IngestionMetricPlugin(descriptor.plugin_id), EmptyConfig)
    for descriptor in RETRIEVAL_METRIC_DESCRIPTORS:
        registry.register(descriptor, lambda descriptor=descriptor: RetrievalMetricPlugin(descriptor.plugin_id), RetrievalMetricConfig)
    for descriptor in ANSWER_METRIC_DESCRIPTORS:
        registry.register(descriptor, lambda descriptor=descriptor: AnswerMetricPlugin(descriptor.plugin_id), AnswerMetricConfig)
    return registry
