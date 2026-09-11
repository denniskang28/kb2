from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from kb2_runtime.chunking.contracts import ChunkerConfig
from kb2_runtime.chunking.processor import process
from kb2_runtime.indexing.contracts import EmbeddingPort, LocalHybridConfig, SearchHit, SearchRequest
from kb2_runtime.indexing.embedding import HashingEmbedder, embed_chunk_set
from kb2_runtime.indexing.hybrid import LocalHybridIndex, build_index, search
from kb2_runtime.indexing.projection import project_search_documents
from kb2_runtime.indexing.serializer import embedding_set_bytes, search_document_set_bytes, search_index_result_bytes
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode


FIXTURES = Path(__file__).parents[1] / "fixtures" / "ingestion"


def chunks(name: str = "table-heavy-canonical.json"):
    return process((FIXTURES / name).read_bytes(), ChunkerConfig(strategy="table" if name.startswith("table") else "hierarchy", max_tokens=64))


def test_embeddings_are_deterministic_chunk_bound_and_do_not_duplicate_content() -> None:
    source = chunks()
    first, second = embed_chunk_set(source), embed_chunk_set(source)
    assert embedding_set_bytes(first) == embedding_set_bytes(second)
    assert [item.chunk_id for item in first.records] == [item.chunk_id for item in source.chunks]
    assert first.dimension == 256 and all(abs(sum(value * value for value in item.values) - 1.0) < 1e-6 for item in first.records)
    assert "content" not in first.records[0].model_dump()


def test_projection_preserves_table_hierarchy_language_metadata_enrichments_and_locators() -> None:
    source = chunks()
    embedding = embed_chunk_set(source)
    projected = project_search_documents(source, embedding)
    assert search_document_set_bytes(projected) == search_document_set_bytes(project_search_documents(source, embedding))
    assert [item.chunk_id for item in projected.documents] == [item.chunk_id for item in source.chunks]
    table = next(item for item in projected.documents if "elm_0000000000000022" in [citation.element_id for citation in item.citations])
    assert table.citations and table.embedding.chunk_id == table.chunk_id
    assert table.metadata == source.metadata and table.language == source.language


def test_projection_rejects_cross_chunkset_embedding_alignment() -> None:
    source, other = chunks(), chunks("long-hierarchy-canonical.json")
    with pytest.raises(PluginError) as raised:
        project_search_documents(source, embed_chunk_set(other))
    assert raised.value.code is PluginErrorCode.EMBEDDING_RECORD_INVALID


def test_index_identity_replay_and_changed_configuration_are_distinct() -> None:
    documents = project_search_documents(chunks("long-hierarchy-canonical.json"), embed_chunk_set(chunks("long-hierarchy-canonical.json")))
    first = asyncio.run(build_index(documents))
    second = asyncio.run(build_index(documents))
    changed = asyncio.run(build_index(documents, LocalHybridConfig(lexical_weight=1, vector_weight=0)))
    assert first.index_id == second.index_id and search_index_result_bytes(first) == search_index_result_bytes(second)
    assert first.index_id != changed.index_id


def test_index_identity_changes_for_source_or_embedding_implementation() -> None:
    source = chunks("long-hierarchy-canonical.json")
    alternate_source = chunks("table-heavy-canonical.json")
    default_documents = project_search_documents(source, embed_chunk_set(source))
    replacement_documents = project_search_documents(source, embed_chunk_set(source, "9" * 64))
    alternate_documents = project_search_documents(alternate_source, embed_chunk_set(alternate_source))

    default = asyncio.run(build_index(default_documents))
    replacement = asyncio.run(build_index(replacement_documents))
    alternate = asyncio.run(build_index(alternate_documents))

    assert len({default.index_id, replacement.index_id, alternate.index_id}) == 3


def test_local_and_synthetic_embedding_ports_share_query_contract() -> None:
    documents = project_search_documents(chunks("long-hierarchy-canonical.json"), embed_chunk_set(chunks("long-hierarchy-canonical.json")))
    result = asyncio.run(build_index(documents))
    for index in (LocalHybridIndex(), _SyntheticHybridIndex()):
        for port in (HashingEmbedder(), _SyntheticEmbedding()):
            hits = index.search(result, SearchRequest(query="hierarchy document", top_k=3), port)
            assert hits and all(hit.citations and hit.chunk_id for hit in hits)
    tied = search(result, SearchRequest(query="not-present-token", top_k=100, lexical_weight=1, vector_weight=0), HashingEmbedder())
    assert [item.chunk_id for item in tied] == sorted(item.chunk_id for item in tied)


def test_dimension_mismatch_cancellation_and_malformed_index_inputs_fail_safely() -> None:
    documents = project_search_documents(chunks("long-hierarchy-canonical.json"), embed_chunk_set(chunks("long-hierarchy-canonical.json")))
    result = asyncio.run(build_index(documents))
    with pytest.raises(PluginError) as raised:
        search(result, SearchRequest(query="query"), _WrongDimensionEmbedding())
    assert raised.value.code is PluginErrorCode.EMBEDDING_DIMENSION_MISMATCH
    cancelled = asyncio.Event(); cancelled.set()
    with pytest.raises(PluginError) as raised:
        asyncio.run(build_index(documents, cancellation=cancelled))
    assert raised.value.code is PluginErrorCode.CANCELLED
    assert asyncio.run(build_index(documents)).index_id == result.index_id
    raw = documents.model_dump(mode="json"); raw["documents"][0]["embedding"]["values"] = [0.0] * 256
    with pytest.raises(Exception):
        type(documents).model_validate(raw)


def test_same_identity_locked_segment_has_no_second_successful_build() -> None:
    documents = project_search_documents(chunks("long-hierarchy-canonical.json"), embed_chunk_set(chunks("long-hierarchy-canonical.json")))
    async def concurrently_build():
        return await asyncio.gather(build_index(documents), build_index(documents))
    with pytest.raises(PluginError) as raised:
        asyncio.run(concurrently_build())
    assert raised.value.code is PluginErrorCode.INDEX_SEGMENT_LOCKED


def test_non_ascii_chunk_content_builds_an_empty_lexicon_and_remains_vector_queryable() -> None:
    raw = json.loads((FIXTURES / "long-hierarchy-canonical.json").read_text(encoding="utf-8"))
    raw["elements"] = [{**raw["elements"][0], "kind": "paragraph", "text": "中文检索内容", "level": None}]
    source = process(json.dumps(raw, ensure_ascii=False).encode("utf-8"), ChunkerConfig(strategy="fixed_window", max_tokens=64))
    documents = project_search_documents(source, embed_chunk_set(source))
    result = asyncio.run(build_index(documents))
    hits = search(result, SearchRequest(query="中文检索", lexical_weight=0, vector_weight=1), HashingEmbedder())
    assert result.term_postings == {} and len(hits) == 1 and hits[0].citations


class _SyntheticEmbedding:
    def embed_text(self, text: str) -> tuple[float, ...]:
        values = [0.0] * 256
        values[sum(ord(character) for character in text) % 256] = 1.0
        return tuple(values)


class _WrongDimensionEmbedding:
    def embed_text(self, text: str) -> tuple[float, ...]:
        return (1.0,)


class _SyntheticHybridIndex:
    def search(self, result, request, embedder) -> tuple[SearchHit, ...]:
        query = embedder.embed_text(request.query)
        hits = tuple(
            SearchHit(document_id=document.document_id, chunk_id=document.chunk_id,
                      score=sum(left * right for left, right in zip(query, document.embedding.values, strict=True)),
                      lexical_score=0, vector_score=sum(left * right for left, right in zip(query, document.embedding.values, strict=True)),
                      hierarchy_context=document.hierarchy_context, language=document.language,
                      metadata=document.metadata, citations=document.citations)
            for document in result.documents if request.language is None or document.language == request.language
        )
        return tuple(sorted(hits, key=lambda hit: (-hit.score, hit.chunk_id))[:request.top_k])
