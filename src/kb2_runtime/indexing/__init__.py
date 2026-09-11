from .contracts import (
    EmbeddingPort,
    EmbeddingRecord,
    EmbeddingSet,
    HybridSearchPort,
    SearchDocument,
    SearchDocumentSet,
    SearchHit,
    SearchIndexResult,
    SearchRequest,
)
from .embedding import HashingEmbedder, embed_chunk_set
from .hybrid import LocalHybridIndex, build_index, search
from .projection import project_search_documents

__all__ = [
    "EmbeddingPort", "EmbeddingRecord", "EmbeddingSet", "HashingEmbedder",
    "HybridSearchPort", "LocalHybridIndex", "SearchDocument", "SearchDocumentSet",
    "SearchHit", "SearchIndexResult", "SearchRequest", "build_index",
    "embed_chunk_set", "project_search_documents", "search",
]
