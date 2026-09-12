from __future__ import annotations
from datetime import datetime, timezone
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode
from .contracts import CandidateContribution, FusedCandidate, FusionCandidateSet, FusionRequest
from .serializer import candidate_set_id

def _active(request: FusionRequest) -> None:
    if request.cancellation and request.cancellation.is_set(): raise PluginError(PluginErrorCode.CANCELLED)
    if request.deadline_at and datetime.now(timezone.utc) >= request.deadline_at: raise PluginError(PluginErrorCode.TIMEOUT)

class ReciprocalRankFusion:
    def fuse(self, request: FusionRequest) -> FusionCandidateSet:
        _active(request); sets = request.candidate_sets
        first = sets[0]
        if len({item.candidate_set_id for item in sets}) != len(sets) or any(item.index != first.index or item.index_id != first.index_id or item.document_id != first.document_id for item in sets):
            raise PluginError(PluginErrorCode.FUSION_INPUT_INVALID)
        grouped: dict[str, list[CandidateContribution]] = {}
        scores: dict[str, float] = {}
        for candidate_set in sets:
            for candidate in candidate_set.candidates:
                _active(request)
                grouped.setdefault(candidate.chunk_id, []).append(CandidateContribution(contributor_id=candidate_set.contributor_id, original_rank=candidate.rank, candidate=candidate))
                scores[candidate.chunk_id] = scores.get(candidate.chunk_id, 0.0) + 1.0 / (request.configuration.rank_constant + candidate.rank)
        maximum = max(scores.values(), default=0.0)
        ordered = sorted(grouped, key=lambda item: (-(scores[item] / maximum if maximum else 0.0), item))[:request.configuration.limit]
        candidates = tuple(FusedCandidate(document_id=first.document_id, chunk_id=chunk_id, rank=rank, safe_score=scores[chunk_id] / maximum if maximum else 0.0, contributions=tuple(grouped[chunk_id])) for rank, chunk_id in enumerate(ordered, 1))
        contributor_ids = tuple(item.candidate_set_id for item in sets)
        return FusionCandidateSet(candidate_set_id=candidate_set_id(first.index, first.index_id, request.plugin_id, request.implementation_digest, request.configuration_digest, contributor_ids, candidates), index=first.index, index_id=first.index_id, document_id=first.document_id, fusion_plugin_id=request.plugin_id, implementation_digest=request.implementation_digest, configuration_digest=request.configuration_digest, contributor_set_ids=contributor_ids, candidates=candidates)
