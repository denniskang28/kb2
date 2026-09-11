from __future__ import annotations

import asyncio
import hashlib
import math
import re
from collections import Counter, defaultdict

from kb2_runtime.plugins.errors import PluginError, PluginErrorCode

from .contracts import EmbeddingPort, LocalHybridConfig, SearchDocumentSet, SearchHit, SearchIndexResult, SearchRequest
from .serializer import canonical_bytes, digest


TERM = re.compile(r"[a-z0-9]+")
INDEXER_ID = "indexer.local-hybrid@1"
INDEXER_IMPLEMENTATION_DIGEST = "4" * 64
_locks: dict[str, asyncio.Lock] = {}


def _terms(text: str) -> list[str]: return TERM.findall(text.lower())


async def build_index(documents: SearchDocumentSet, config: LocalHybridConfig = LocalHybridConfig(), cancellation: asyncio.Event | None = None, implementation_digest: str = INDEXER_IMPLEMENTATION_DIGEST) -> SearchIndexResult:
    try:
        if not documents.documents or any(len(item.embedding.values) != documents.dimension for item in documents.documents):
            raise ValueError("invalid search documents")
        identity = {"schema": "SearchIndexResult/v1", "implementation": implementation_digest, "configuration": config.model_dump(mode="json"), "documents": digest(documents), "embedding": {"plugin": documents.embedding_plugin_id, "model": documents.embedding_model_id, "dimension": documents.dimension}, "embedding_set": documents.source_embedding_set_digest}
        index_id = "idx_" + hashlib.sha256(canonical_bytes(identity)).hexdigest()[:32]
        lock = _locks.setdefault(index_id, asyncio.Lock())
        if lock.locked():
            raise PluginError(PluginErrorCode.INDEX_SEGMENT_LOCKED)
        async with lock:
            # Yield after acquiring the keyed lock so concurrent callers receive
            # the explicit retryable lock result rather than observing a partial build.
            await asyncio.sleep(0)
            if cancellation and cancellation.is_set():
                raise PluginError(PluginErrorCode.CANCELLED)
            postings: dict[str, list[tuple[str, int]]] = defaultdict(list)
            lengths = {}
            for document in documents.documents:
                frequencies = Counter(_terms(document.keyword_text)); lengths[document.chunk_id] = sum(frequencies.values())
                for term, count in frequencies.items(): postings[term].append((document.chunk_id, count))
            result = SearchIndexResult(index_id=index_id, implementation_id=INDEXER_ID, implementation_digest=implementation_digest, configuration=config, search_document_set_digest=digest(documents), embedding_set_digest=documents.source_embedding_set_digest, document_count=len(documents.documents), term_postings={term: tuple(sorted(items)) for term, items in sorted(postings.items())}, document_lengths=dict(sorted(lengths.items())), documents=documents.documents)
            if cancellation and cancellation.is_set():
                raise PluginError(PluginErrorCode.CANCELLED)
            return result
    except PluginError:
        raise
    except (ValueError, TypeError) as exc:
        raise PluginError(PluginErrorCode.INDEX_INPUT_INVALID) from exc


def search(result: SearchIndexResult, request: SearchRequest, embedder: EmbeddingPort) -> tuple[SearchHit, ...]:
    eligible = tuple(item for item in result.documents if request.language is None or item.language == request.language)
    if not eligible:
        return ()
    query_terms = Counter(_terms(request.query)); query_vector = embedder.embed_text(request.query)
    if len(query_vector) != len(eligible[0].embedding.values):
        raise PluginError(PluginErrorCode.EMBEDDING_DIMENSION_MISMATCH)
    total, average = len(eligible), sum(result.document_lengths[item.chunk_id] for item in eligible) / len(eligible)
    lexical: dict[str, float] = {}; vector: dict[str, float] = {}
    for document in eligible:
        score = 0.0
        for term, query_count in query_terms.items():
            posting = dict(result.term_postings.get(term, ())); frequency = posting.get(document.chunk_id, 0)
            if frequency:
                df = len(result.term_postings[term]); idf = math.log(1 + (total - df + 0.5) / (df + 0.5)); score += query_count * idf * frequency * 2.2 / (frequency + 1.2 * (1 - 0.75 + 0.75 * result.document_lengths[document.chunk_id] / average))
        lexical[document.chunk_id] = score
        vector[document.chunk_id] = sum(left * right for left, right in zip(query_vector, document.embedding.values, strict=True))
    def normalize(values: dict[str, float]) -> dict[str, float]:
        maximum = max(values.values()); return {key: value / maximum if maximum > 0 else 0.0 for key, value in values.items()}
    lexical, vector = normalize(lexical), normalize(vector)
    hits = [SearchHit(document_id=item.document_id, chunk_id=item.chunk_id, score=request.lexical_weight * lexical[item.chunk_id] + request.vector_weight * vector[item.chunk_id], lexical_score=lexical[item.chunk_id], vector_score=vector[item.chunk_id], hierarchy_context=item.hierarchy_context, language=item.language, metadata=item.metadata, citations=item.citations) for item in eligible]
    return tuple(sorted(hits, key=lambda item: (-item.score, item.chunk_id))[:request.top_k])


class LocalHybridIndex:
    def search(self, result: SearchIndexResult, request: SearchRequest, embedder: EmbeddingPort) -> tuple[SearchHit, ...]:
        return search(result, request, embedder)
