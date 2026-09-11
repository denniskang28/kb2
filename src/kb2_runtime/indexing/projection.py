from __future__ import annotations

from kb2_runtime.chunking.contracts import ChunkSet
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode

from .contracts import EmbeddingSet, SearchDocument, SearchDocumentSet
from .serializer import digest


def project_search_documents(chunk_set: ChunkSet, embeddings: EmbeddingSet) -> SearchDocumentSet:
    try:
        if embeddings.source_chunk_set_digest != digest(chunk_set):
            raise ValueError("source digest mismatch")
        by_id = {record.chunk_id: record for record in embeddings.records}
        if tuple(by_id) != tuple(chunk.chunk_id for chunk in chunk_set.chunks) or embeddings.dimension != len(next(iter(by_id.values())).values):
            raise ValueError("embedding records do not align")
        documents = tuple(SearchDocument(document_id=chunk_set.document_id, chunk_id=chunk.chunk_id, keyword_text=chunk.content, hierarchy_context=chunk.hierarchy_context, language=chunk.language or chunk_set.language, metadata=chunk_set.metadata, enrichments=chunk.enrichments, citations=chunk.citations, embedding=by_id[chunk.chunk_id]) for chunk in chunk_set.chunks)
        return SearchDocumentSet(source_chunk_set_digest=digest(chunk_set), source_embedding_set_digest=digest(embeddings), document_id=chunk_set.document_id, embedding_plugin_id=embeddings.plugin_id, embedding_implementation_digest=embeddings.implementation_digest, embedding_model_id=embeddings.model_id, dimension=embeddings.dimension, documents=documents)
    except (ValueError, TypeError, StopIteration) as exc:
        raise PluginError(PluginErrorCode.EMBEDDING_RECORD_INVALID) from exc
