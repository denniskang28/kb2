from __future__ import annotations

import asyncio
import hashlib
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from kb2_runtime.chunking.contracts import ChunkerConfig
from kb2_runtime.chunking.contracts import EnrichmentField, EnrichmentProvenance
from kb2_runtime.chunking.processor import process
from kb2_runtime.indexing.embedding import embed_chunk_set
from kb2_runtime.indexing.hybrid import build_index
from kb2_runtime.indexing.projection import project_search_documents
from kb2_runtime.retrieval.contracts import HierarchyRetrieverConfig, IndexArtifactBinding, RetrievalCandidate, RetrieverConfig, RetrieverRequest
from kb2_runtime.retrieval.local import HierarchyRetriever, KeywordRetriever, MetadataRetriever, TableRetriever, VectorRetriever
from kb2_runtime.retrieval import local
from kb2_runtime.retrieval.serializer import retrieval_candidate_set_bytes
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode


def index(name: str = "table-heavy-canonical.json"):
    source = (Path(__file__).parents[1] / "fixtures" / "ingestion" / name).read_bytes()
    chunks = process(source, ChunkerConfig(strategy="table" if name.startswith("table") else "parent_child", max_tokens=64))
    return asyncio.run(build_index(project_search_documents(chunks, embed_chunk_set(chunks))))


def request(result, config: RetrieverConfig = RetrieverConfig(), query: str = "metrics") -> RetrieverRequest:
    return RetrieverRequest(query=query, index=result, index_binding=IndexArtifactBinding(id=UUID("12345678-1234-5678-1234-567812345678"), content_digest="a" * 64), contributor_id="retrieve", configuration=config, configuration_digest="b" * 64, plugin_id="retriever.keyword@1", implementation_digest="6" * 64)


def test_candidate_sets_are_canonical_ranked_and_citation_bound() -> None:
    result = index()
    first = KeywordRetriever().retrieve(request(result))
    second = KeywordRetriever().retrieve(request(result))
    assert retrieval_candidate_set_bytes(first) == retrieval_candidate_set_bytes(second)
    assert first.index.index_id if hasattr(first.index, "index_id") else first.index_id == result.index_id
    assert [item.rank for item in first.candidates] == list(range(1, len(first.candidates) + 1))
    assert all(item.document_id == result.documents[0].document_id and item.element_ids and item.locators and 0 <= item.safe_score <= 1 for item in first.candidates)
    assert b"term_postings" not in retrieval_candidate_set_bytes(first) and b"embedding" not in retrieval_candidate_set_bytes(first)


def test_strategies_remain_independent_with_table_and_metadata_projections() -> None:
    result = index()
    keyword = KeywordRetriever().retrieve(request(result, query="revenue"))
    vector_request = request(result, query="revenue").model_copy(update={"plugin_id": "retriever.vector@1", "implementation_digest": "7" * 64, "contributor_id": "vector"})
    vector = VectorRetriever().retrieve(vector_request)
    table_request = request(result, query="revenue").model_copy(update={"plugin_id": "retriever.table@1"})
    table = TableRetriever().retrieve(table_request)
    metadata = MetadataRetriever().retrieve(request(result, RetrieverConfig(metadata={"media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}), "revenue"))
    assert keyword.retriever_plugin_id != vector.retriever_plugin_id and keyword.contributor_id != vector.contributor_id
    assert all(item.structural_projection.table_element_ids for item in table.candidates)
    assert all(item.structural_projection.matched_filter_keys for item in metadata.candidates)


def test_hierarchy_filters_limits_and_cancellation_are_safe() -> None:
    result = index("long-hierarchy-canonical.json")
    limited = HierarchyRetriever().retrieve(request(result, RetrieverConfig(limit=1), "child"))
    assert len(limited.candidates) <= 1
    no_match = KeywordRetriever().retrieve(request(result, RetrieverConfig(language="fr"), "child"))
    assert no_match.candidates == ()
    cancelled = request(result).model_copy(update={"cancellation": asyncio.Event()})
    cancelled.cancellation.set()  # type: ignore[union-attr]
    with pytest.raises(PluginError) as raised:
        KeywordRetriever().retrieve(cancelled)
    assert raised.value.code is PluginErrorCode.CANCELLED


def test_document_class_filter_uses_declared_enrichment_label_not_media_type() -> None:
    result = index()
    documents = tuple(document.model_copy(update={"enrichments": {
        **document.enrichments,
        "document_class": EnrichmentField(
            value="financial-report",
            provenance=EnrichmentProvenance(
                producer_plugin_id="enricher.chunk-metadata@1", configuration_digest="a" * 64,
                source_chunk_id=document.chunk_id,
            ),
        ),
    }}) for document in result.documents)
    labelled = result.model_copy(update={"documents": documents})

    assert KeywordRetriever().retrieve(request(labelled, RetrieverConfig(document_class="financial-report"))).candidates
    assert not KeywordRetriever().retrieve(request(labelled, RetrieverConfig(document_class=documents[0].metadata.media_type))).candidates


def test_local_scoring_observes_cancellation_and_deadline_during_work(monkeypatch) -> None:
    result = index()
    expired = request(result).model_copy(update={"deadline_at": datetime.now(timezone.utc) - timedelta(milliseconds=1)})
    with pytest.raises(PluginError) as raised:
        KeywordRetriever().retrieve(expired)
    assert raised.value.code is PluginErrorCode.TIMEOUT

    original_terms = local._terms
    event = asyncio.Event()
    def slow_terms(text: str):
        time.sleep(0.01)
        return original_terms(text)
    timer = threading.Timer(0.001, event.set)
    monkeypatch.setattr(local, "_terms", slow_terms)
    timer.start()
    try:
        with pytest.raises(PluginError) as raised:
            KeywordRetriever().retrieve(request(result).model_copy(update={"cancellation": event}))
    finally:
        timer.cancel()
    assert raised.value.code is PluginErrorCode.CANCELLED


def test_hierarchy_relation_modes_emit_only_the_declared_linked_chunks() -> None:
    result = index("long-hierarchy-canonical.json")
    parent = HierarchyRetriever().retrieve(
        request(result, HierarchyRetrieverConfig(limit=10, relation_mode="parent"), "child")
    )
    children = HierarchyRetriever().retrieve(
        request(result, HierarchyRetrieverConfig(limit=10, relation_mode="children"), "child")
    )

    assert [item.chunk_id for item in parent.candidates] == [result.documents[0].chunk_id]
    assert all(item.structural_projection.relation == "parent" for item in parent.candidates)
    assert [item.chunk_id for item in children.candidates] == [result.documents[1].chunk_id]
    assert all(item.structural_projection.relation == "children" for item in children.candidates)


def test_candidate_contract_rejects_nonfinite_scores_and_duplicate_ranks() -> None:
    result = index()
    candidate = KeywordRetriever().retrieve(request(result)).candidates[0]
    with pytest.raises(ValidationError):
        candidate.model_copy(update={"safe_score": float("nan")}).__class__.model_validate({**candidate.model_dump(mode="json"), "safe_score": float("nan")})
    with pytest.raises(ValidationError):
        KeywordRetriever().retrieve(request(result)).model_copy(update={"candidates": (candidate, candidate.model_copy(update={"candidate_id": "rcd_" + hashlib.sha256(b"two").hexdigest()[:32], "rank": 1}))}).__class__.model_validate({**KeywordRetriever().retrieve(request(result)).model_dump(mode="json"), "candidates": [candidate.model_dump(mode="json"), candidate.model_copy(update={"candidate_id": "rcd_" + hashlib.sha256(b"two").hexdigest()[:32], "rank": 1}).model_dump(mode="json")]})


def test_candidate_contract_rejects_native_or_unbounded_structural_projection() -> None:
    candidate = KeywordRetriever().retrieve(request(index())).candidates[0]
    payload = candidate.model_dump(mode="json")
    with pytest.raises(ValidationError):
        RetrievalCandidate.model_validate({**payload, "structural_projection": {"provider_payload": "forbidden"}})
    with pytest.raises(ValidationError):
        RetrievalCandidate.model_validate({**payload, "structural_projection": {"hierarchy_path": ["x" * 257]}})
