from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timezone

from kb2_runtime.indexing.embedding import HashingEmbedder
from kb2_runtime.indexing.hybrid import _terms
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode

from .contracts import HierarchyRetrieverConfig, RetrievalCandidate, RetrievalCandidateSet, RetrieverRequest, StructuralProjection
from .serializer import candidate_id, candidate_set_id


def _check_active(request: RetrieverRequest) -> None:
    if request.cancellation and request.cancellation.is_set():
        raise PluginError(PluginErrorCode.CANCELLED)
    if request.deadline_at and datetime.now(timezone.utc) >= request.deadline_at:
        raise PluginError(PluginErrorCode.TIMEOUT)


def _eligible(request: RetrieverRequest):
    filters = request.configuration.filters
    for document in request.index.documents:
        _check_active(request)
        metadata = document.metadata.model_dump(mode="json")
        if ((filters.language and document.language != filters.language)
                or (filters.document_class and (document.enrichments.get("document_class") is None or document.enrichments["document_class"].value != filters.document_class))
                or any(metadata.get(key) != value for key, value in filters.metadata.items())
                or any(document.enrichments.get(key) is None or document.enrichments[key].value != value for key, value in filters.enrichments.items())):
            continue
        yield document


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    maximum = max(scores.values(), default=0.0)
    return {key: max(0.0, min(1.0, value / maximum if maximum > 0 else 0.0)) for key, value in scores.items()}


def _lexical_scores(request: RetrieverRequest, documents, hierarchy: bool = False) -> dict[str, float]:
    documents = tuple(documents)
    if not documents:
        return {}
    query = Counter(_terms(request.query))
    total = len(documents)
    lengths = {}
    for item in documents:
        _check_active(request)
        lengths[item.chunk_id] = max(1, len(_terms((" ".join(item.hierarchy_context) + " " if hierarchy else "") + item.keyword_text)))
    average = sum(lengths.values()) / total
    scores: dict[str, float] = {}
    for item in documents:
        _check_active(request)
        text = (" ".join(item.hierarchy_context) + " " if hierarchy else "") + item.keyword_text
        frequencies = Counter(_terms(text)); score = 0.0
        for term, count in query.items():
            _check_active(request)
            frequency = frequencies.get(term, 0)
            if frequency:
                df = 0
                for candidate in documents:
                    _check_active(request)
                    if term in _terms((" ".join(candidate.hierarchy_context) + " " if hierarchy else "") + candidate.keyword_text):
                        df += 1
                idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
                score += count * idf * frequency * 2.2 / (frequency + 1.2 * (1 - 0.75 + 0.75 * lengths[item.chunk_id] / average))
        scores[item.chunk_id] = score
    return scores


class _LocalRetriever:
    score_kind = "lexical"

    def _select(self, request: RetrieverRequest):
        return tuple(_eligible(request)), "self"

    def _scores(self, request: RetrieverRequest, documents) -> dict[str, float]:
        return _lexical_scores(request, documents)

    def retrieve(self, request: RetrieverRequest) -> RetrievalCandidateSet:
        _check_active(request)
        documents, relation = self._select(request)
        scores = _normalize(self._scores(request, documents))
        _check_active(request)
        ranked = sorted(documents, key=lambda item: (-scores[item.chunk_id], item.chunk_id))[:request.configuration.limit]
        candidates = tuple(self._candidate_with_activity_check(request, document, scores[document.chunk_id], rank, relation) for rank, document in enumerate(ranked, 1))
        filtered_count = request.index.document_count - len(documents)
        return RetrievalCandidateSet(candidate_set_id=candidate_set_id(request.index_binding, request.index.index_id, request.plugin_id, request.implementation_digest, request.contributor_id, request.configuration_digest, filtered_count, candidates), index=request.index_binding, index_id=request.index.index_id, document_id=request.index.documents[0].document_id, retriever_plugin_id=request.plugin_id, implementation_digest=request.implementation_digest, contributor_id=request.contributor_id, configuration_digest=request.configuration_digest, filtered_count=filtered_count, candidates=candidates)

    def _candidate_with_activity_check(self, request: RetrieverRequest, document, score: float, rank: int, relation: str) -> RetrievalCandidate:
        _check_active(request)
        return self._candidate(request, document, score, rank, relation)

    def _candidate(self, request: RetrieverRequest, document, score: float, rank: int, relation: str) -> RetrievalCandidate:
        projection: dict[str, object] = {}
        if document.hierarchy_context:
            projection["hierarchy_path"] = document.hierarchy_context
        if relation != "self":
            projection["relation"] = relation
        return RetrievalCandidate(candidate_id=candidate_id(request.index.index_id, request.contributor_id, document.chunk_id), document_id=document.document_id, chunk_id=document.chunk_id, element_ids=tuple(item.element_id for item in document.citations), locators=tuple(item.locator for item in document.citations), rank=rank, safe_score=score, score_kind=self.score_kind, structural_projection=StructuralProjection.model_validate(projection))


class KeywordRetriever(_LocalRetriever):
    score_kind = "bm25"


class VectorRetriever(_LocalRetriever):
    score_kind = "cosine"

    def _scores(self, request: RetrieverRequest, documents) -> dict[str, float]:
        vector = HashingEmbedder().embed_text(request.query)
        if any(len(item.embedding.values) != len(vector) for item in documents):
            raise PluginError(PluginErrorCode.RETRIEVAL_INPUT_INVALID)
        scores = {}
        for item in documents:
            _check_active(request)
            scores[item.chunk_id] = sum(left * right for left, right in zip(vector, item.embedding.values, strict=True))
        return scores


class HierarchyRetriever(_LocalRetriever):
    score_kind = "hierarchy_bm25"

    def _select(self, request: RetrieverRequest):
        config = HierarchyRetrieverConfig.model_validate(request.configuration.model_dump(mode="json"))
        source = {item.chunk_id: item for item in _eligible(request)}
        if config.relation_mode == "self":
            return tuple(source.values()), "self"
        selected = {}
        for item in source.values():
            _check_active(request)
            linked = ((item.parent_chunk_id,) if item.parent_chunk_id else ()) if config.relation_mode == "parent" else item.child_chunk_ids
            for chunk_id in linked:
                _check_active(request)
                if chunk_id in source:
                    selected[chunk_id] = source[chunk_id]
        return tuple(selected.values()), config.relation_mode

    def _scores(self, request: RetrieverRequest, documents) -> dict[str, float]:
        return _lexical_scores(request, documents, hierarchy=True)


class TableRetriever(_LocalRetriever):
    score_kind = "table_bm25"

    def _select(self, request: RetrieverRequest):
        return tuple(item for item in _eligible(request) if any(citation.locator.kind == "spreadsheet" for citation in item.citations)), "self"

    def _candidate(self, request: RetrieverRequest, document, score: float, rank: int, relation: str) -> RetrievalCandidate:
        candidate = super()._candidate(request, document, score, rank, relation)
        projection = candidate.structural_projection.model_dump(mode="json")
        projection["table_element_ids"] = tuple(item.element_id for item in document.citations if item.locator.kind == "spreadsheet")
        return RetrievalCandidate.model_validate({**candidate.model_dump(mode="json"), "structural_projection": projection})


class MetadataRetriever(_LocalRetriever):
    score_kind = "metadata_bm25"

    def _candidate(self, request: RetrieverRequest, document, score: float, rank: int, relation: str) -> RetrievalCandidate:
        candidate = super()._candidate(request, document, score, rank, relation)
        projection = candidate.structural_projection.model_dump(mode="json")
        projection["matched_filter_keys"] = tuple(sorted((*request.configuration.filters.metadata, *request.configuration.filters.enrichments, *(('language',) if request.configuration.filters.language else ()), *(('document_class',) if request.configuration.filters.document_class else ()))))
        return RetrievalCandidate.model_validate({**candidate.model_dump(mode="json"), "structural_projection": projection})
