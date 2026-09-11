from __future__ import annotations

import time

from pydantic import ValidationError

from kb2_runtime.chunking.contracts import ChunkSet
from kb2_runtime.plugins.contracts import PluginContext, PluginInvocationResult, PluginOutput
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode

from .contracts import LocalHybridConfig
from .embedding import embed_chunk_set
from .hybrid import build_index
from .projection import project_search_documents
from .serializer import embedding_set_bytes, search_document_set_bytes, search_index_result_bytes


class HashingEmbeddingPlugin:
    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        try:
            chunk_set = ChunkSet.model_validate_json((await context.input(context.invocation.inputs[0].id)).content)
        except (ValidationError, ValueError, TypeError) as exc:
            raise PluginError(PluginErrorCode.EMBEDDING_RECORD_INVALID) from exc
        result = embed_chunk_set(chunk_set, context.invocation.implementation_digest)
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="embedding.set", schema_revision="v1", content=embedding_set_bytes(result), summary="embeddings created", metrics=({"name": "embedding_records", "value": len(result.records)}, {"name": "embedding_dimension", "value": result.dimension}), quality_signals=({"name": "embedding_validation", "status": "PASS", "summary": "validated"},)),), summary="embeddings created")


class SearchDocumentProjectorPlugin:
    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        from .contracts import EmbeddingSet
        try:
            chunk_set = ChunkSet.model_validate_json((await context.input(context.invocation.inputs[0].id)).content)
            embeddings = EmbeddingSet.model_validate_json((await context.input(context.invocation.inputs[1].id)).content)
        except (ValidationError, ValueError, TypeError) as exc:
            raise PluginError(PluginErrorCode.EMBEDDING_RECORD_INVALID) from exc
        result = project_search_documents(chunk_set, embeddings)
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="search.document.set", schema_revision="v1", content=search_document_set_bytes(result), summary="search documents created", metrics=({"name": "search_documents", "value": len(result.documents)},), quality_signals=({"name": "search_document_validation", "status": "PASS", "summary": "validated"},)),), summary="search documents created")


class LocalHybridIndexPlugin:
    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        from .contracts import SearchDocumentSet
        started = time.monotonic()
        try:
            documents = SearchDocumentSet.model_validate_json((await context.input(context.invocation.inputs[0].id)).content)
        except (ValidationError, ValueError, TypeError) as exc:
            raise PluginError(PluginErrorCode.INDEX_INPUT_INVALID) from exc
        result = await build_index(documents, LocalHybridConfig.model_validate(context.invocation.validated_configuration), context.cancellation, context.invocation.implementation_digest)
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="search.index.result", schema_revision="v1", content=search_index_result_bytes(result), summary="local hybrid index created", metrics=({"name": "index_terms", "value": len(result.term_postings)}, {"name": "index_vectors", "value": result.document_count}, {"name": "index_build_ms", "value": int((time.monotonic() - started) * 1000)}, {"name": "index_reused", "value": 0}), quality_signals=({"name": "index_validation", "status": "PASS", "summary": "validated"},)),), summary="local hybrid index created")
