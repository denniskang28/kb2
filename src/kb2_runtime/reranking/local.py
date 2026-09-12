from __future__ import annotations
from datetime import datetime, timezone
from kb2_runtime.indexing.hybrid import _terms
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode
from .contracts import RerankDecision, RerankInputCandidate, RerankedCandidateSet, RerankerRequest
from .serializer import candidate_set_id
def _active(request: RerankerRequest) -> None:
    if request.cancellation and request.cancellation.is_set(): raise PluginError(PluginErrorCode.CANCELLED)
    if request.deadline_at and datetime.now(timezone.utc) >= request.deadline_at: raise PluginError(PluginErrorCode.TIMEOUT)
class LexicalOverlapReranker:
    def rerank(self, request: RerankerRequest) -> RerankedCandidateSet:
        _active(request)
        if request.fused.index != request.index_binding or request.fused.index_id != request.index.index_id or request.fused.document_id != request.index.documents[0].document_id: raise PluginError(PluginErrorCode.RERANK_INPUT_INVALID)
        documents = {item.chunk_id: item for item in request.index.documents}; terms = set(_terms(request.question)); raw = {}
        for candidate in request.fused.candidates:
            _active(request); document = documents.get(candidate.chunk_id)
            if not document or document.document_id != candidate.document_id: raise PluginError(PluginErrorCode.RERANK_INPUT_INVALID)
            words = set(_terms(document.keyword_text)); raw[candidate.chunk_id] = len(terms & words) / len(terms) if terms else 0.0
        maximum = max(raw.values(), default=0.0); scores = {key: value / maximum if maximum else 0.0 for key, value in raw.items()}
        ranked = sorted(request.fused.candidates, key=lambda item: (-scores[item.chunk_id], item.rank, item.chunk_id)); selected = ranked[:request.configuration.limit]
        output = tuple(item.model_copy(update={"rank": position}) for position, item in enumerate(selected, 1))
        output_ranks = {item.chunk_id: item.rank for item in output}
        decisions = tuple(RerankDecision(chunk_id=item.chunk_id, input_rank=item.rank, output_rank=output_ranks.get(item.chunk_id), safe_score=scores[item.chunk_id], reason="included" if item.chunk_id in output_ranks else "limit_excluded") for item in request.fused.candidates)
        inputs = tuple(RerankInputCandidate(chunk_id=item.chunk_id, input_rank=item.rank) for item in request.fused.candidates)
        return RerankedCandidateSet(candidate_set_id=candidate_set_id(request.fused.candidate_set_id, request.index_binding, request.plugin_id, request.implementation_digest, request.configuration_digest, inputs, output, decisions), fusion_candidate_set_id=request.fused.candidate_set_id, index=request.index_binding, index_id=request.index.index_id, document_id=request.fused.document_id, reranker_plugin_id=request.plugin_id, implementation_digest=request.implementation_digest, configuration_digest=request.configuration_digest, input_candidates=inputs, candidates=output, decisions=decisions)
