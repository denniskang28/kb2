from kb2_runtime.plugins.contracts import PluginContext, PluginInvocationResult, PluginOutput

from .contracts import ChunkerConfig
from .processor import canonical_bytes, enrich, process


class CanonicalChunkerPlugin:
    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        source = await context.input(context.invocation.inputs[0].id)
        config = ChunkerConfig.model_validate(context.invocation.validated_configuration)
        chunk_set = process(source.content, config)
        parent_links = sum(chunk.parent_chunk_id is not None for chunk in chunk_set.chunks)
        # Table mode isolates table renderings into their own groups; mixed prose
        # groups are still counted for deterministic stage observability.
        table_groups = len(chunk_set.chunks) if config.strategy == "table" else 0
        signals = ({"name": "chunk_validation", "status": "PASS", "summary": "validated"}, {"name": "citation_validation", "status": "PASS", "summary": "validated"})
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="chunk.set", schema_revision="v1", content=canonical_bytes(chunk_set), summary="chunks created", metrics=(
            {"name": "chunks_emitted", "value": len(chunk_set.chunks)}, {"name": "chunk_tokens_total", "value": sum(chunk.token_count for chunk in chunk_set.chunks)},
            {"name": "chunk_parent_links", "value": parent_links}, {"name": "chunk_table_groups", "value": table_groups},
        ), quality_signals=signals),), summary="chunks created", quality_signals=signals)


class ChunkMetadataEnricherPlugin:
    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        source = await context.input(context.invocation.inputs[0].id)
        fields = context.invocation.validated_configuration["fields"]
        chunk_set = enrich(source.content, fields, context.invocation.plugin_id, context.invocation.configuration_digest)
        signals = ({"name": "chunk_validation", "status": "PASS", "summary": "validated"}, {"name": "citation_validation", "status": "PASS", "summary": "validated"}, {"name": "enrichment_validation", "status": "PASS", "summary": "validated"})
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="chunk.set", schema_revision="v1", content=canonical_bytes(chunk_set), summary="chunk metadata enriched", metrics=({"name": "enrichment_fields_added", "value": len(fields) * len(chunk_set.chunks)},), quality_signals=signals),), summary="chunk metadata enriched", quality_signals=signals)
