from __future__ import annotations
from datetime import datetime, timezone
from kb2_runtime.fusion.contracts import FusionCandidateSet
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode
from kb2_runtime.reranking.contracts import RerankedCandidateSet
from kb2_runtime.retrieval.contracts import RetrievalCandidate, RetrievalCandidateSet
from .contracts import ContextAssemblyRequest, ContextDecision, EvidenceItem, EvidenceScore, EvidenceSet, EvidenceShortage
from .serializer import citation_key, evidence_id, evidence_set_id


def _active(request: ContextAssemblyRequest) -> None:
    if request.cancellation and request.cancellation.is_set(): raise PluginError(PluginErrorCode.CANCELLED)
    if request.deadline_at and datetime.now(timezone.utc) >= request.deadline_at: raise PluginError(PluginErrorCode.TIMEOUT)


def _tokens(value: str) -> int: return len(value.split())


class LocalContextAssembler:
    def assemble(self, request: ContextAssemblyRequest) -> EvidenceSet:
        _active(request)
        candidate_set = request.candidates
        if not isinstance(candidate_set, (RetrievalCandidateSet, FusionCandidateSet, RerankedCandidateSet)):
            raise PluginError(PluginErrorCode.CONTEXT_INPUT_INVALID)
        if (candidate_set.index != request.index_binding or candidate_set.index_id != request.index.index_id
                or candidate_set.document_id != request.index.documents[0].document_id):
            raise PluginError(PluginErrorCode.CONTEXT_INPUT_INVALID)
        documents = {item.chunk_id: item for item in request.index.documents}
        normalized: list[tuple[int, RetrievalCandidate, tuple[EvidenceScore, ...]]] = []
        if isinstance(candidate_set, RetrievalCandidateSet):
            normalized = [(item.rank, item, (EvidenceScore(contributor_id=candidate_set.contributor_id, safe_score=item.safe_score),)) for item in candidate_set.candidates]
        else:
            for item in candidate_set.candidates:
                contributions = item.contributions
                candidate = contributions[0].candidate
                scores = tuple(EvidenceScore(contributor_id=value.contributor_id, safe_score=value.candidate.safe_score) for value in contributions)
                normalized.append((item.rank, candidate, scores))
        for _, candidate, _ in normalized:
            source = documents.get(candidate.chunk_id)
            citations = {(item.element_id, item.locator.model_dump_json()) for item in source.citations} if source else set()
            if source is None or source.document_id != candidate.document_id or any((element, locator.model_dump_json()) not in citations for element, locator in zip(candidate.element_ids, candidate.locators, strict=True)):
                raise PluginError(PluginErrorCode.CONTEXT_INPUT_INVALID)
        items: list[EvidenceItem] = []; decisions: list[ContextDecision] = []; selected_chunks: set[str] = set(); selected_documents: set[str] = set(); used_tokens = 0
        def add(rank: int, candidate: RetrievalCandidate, scores: tuple[EvidenceScore, ...], reason: str) -> bool:
            nonlocal used_tokens
            _active(request); source = documents[candidate.chunk_id]
            if candidate.chunk_id in selected_chunks:
                decisions.append(ContextDecision(chunk_id=candidate.chunk_id, source_rank=rank, reason="deduplicated", safe_score=candidate.safe_score)); return False
            if request.configuration.source_diversity == "document" and candidate.document_id in selected_documents:
                decisions.append(ContextDecision(chunk_id=candidate.chunk_id, source_rank=rank, reason="excluded_diversity", safe_score=candidate.safe_score)); return False
            excerpt = source.keyword_text[:request.configuration.max_excerpt_chars]
            count = _tokens(excerpt)
            if len(items) >= request.configuration.max_items or used_tokens + count > request.configuration.max_tokens:
                decisions.append(ContextDecision(chunk_id=candidate.chunk_id, source_rank=rank, reason="excluded_budget", safe_score=candidate.safe_score)); return False
            key = citation_key(candidate.document_id, candidate.chunk_id, candidate.element_ids, candidate.locators)
            table_ids = tuple(item for item in candidate.structural_projection.table_element_ids if item in candidate.element_ids)
            items.append(EvidenceItem(evidence_id=evidence_id(key), citation_key=key, document_id=candidate.document_id, chunk_id=candidate.chunk_id, element_ids=candidate.element_ids, locators=candidate.locators, excerpt=excerpt, contributors=scores, hierarchy_context=source.hierarchy_context, table_element_ids=table_ids))
            selected_chunks.add(candidate.chunk_id); selected_documents.add(candidate.document_id); used_tokens += count
            decisions.append(ContextDecision(chunk_id=candidate.chunk_id, source_rank=rank, reason=reason, safe_score=candidate.safe_score)); return True
        for rank, candidate, scores in sorted(normalized, key=lambda value: (value[0], value[1].chunk_id)):
            add(rank, candidate, scores, "included")
        if request.configuration.structural_rule != "none":
            next_rank = len(normalized) + 1
            for _, candidate, scores in tuple(normalized):
                source = documents[candidate.chunk_id]
                expansion_ids: list[tuple[str, str]] = []
                if request.configuration.expand_parent and source.parent_chunk_id: expansion_ids.append((source.parent_chunk_id, "expanded_parent"))
                ordered = list(request.index.documents); position = ordered.index(source)
                for offset in range(1, request.configuration.neighbor_window + 1):
                    for neighbor in (position - offset, position + offset):
                        if 0 <= neighbor < len(ordered): expansion_ids.append((ordered[neighbor].chunk_id, "expanded_neighbor"))
                for chunk_id, reason in expansion_ids:
                    expanded = documents[chunk_id]
                    candidate_copy = candidate.model_copy(update={"chunk_id": expanded.chunk_id, "document_id": expanded.document_id, "element_ids": tuple(item.element_id for item in expanded.citations), "locators": tuple(item.locator for item in expanded.citations), "safe_score": candidate.safe_score})
                    add(next_rank, candidate_copy, scores, reason); next_rank += 1
        if not items: shortage_reason = "no_candidates" if not normalized else "budget_exhausted"
        elif len(items) < request.configuration.minimum_items: shortage_reason = "below_minimum"
        elif any(item.reason == "excluded_budget" for item in decisions): shortage_reason = "budget_exhausted"
        else: shortage_reason = "none"
        shortage = EvidenceShortage(minimum_items=request.configuration.minimum_items, selected_items=len(items), selected_tokens=used_tokens, reason=shortage_reason)
        return EvidenceSet(evidence_set_id=evidence_set_id(candidate_set.candidate_set_id, request.index_binding, request.index.index_id, request.plugin_id, request.implementation_digest, request.configuration_digest, tuple(items), tuple(decisions), shortage), source_candidate_set_id=candidate_set.candidate_set_id, index=request.index_binding, index_id=request.index.index_id, document_id=candidate_set.document_id, context_plugin_id=request.plugin_id, implementation_digest=request.implementation_digest, configuration_digest=request.configuration_digest, items=tuple(items), decisions=tuple(decisions), shortage=shortage)
