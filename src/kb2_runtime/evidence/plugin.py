from __future__ import annotations
import asyncio, hashlib, time
from pydantic import ValidationError
from kb2_runtime.fusion.contracts import FusionCandidateSet
from kb2_runtime.fusion.serializer import candidate_set_id as fusion_id
from kb2_runtime.indexing.contracts import SearchIndexResult
from kb2_runtime.plugins.contracts import PluginContext, PluginInvocationResult, PluginOutput, configuration_digest
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode
from kb2_runtime.reranking.contracts import RerankedCandidateSet
from kb2_runtime.reranking.serializer import candidate_set_id as rerank_id
from kb2_runtime.retrieval.contracts import IndexArtifactBinding, RetrievalCandidateSet
from kb2_runtime.retrieval.serializer import candidate_set_id as retrieval_id
from .contracts import ContextAssemblerConfig, ContextAssemblyRequest, EvidenceSet
from .local import LocalContextAssembler
from .serializer import evidence_set_bytes, evidence_set_id


class ContextAssemblerPlugin:
    def __init__(self, source_type: str, port: object | None = None) -> None: self.source_type, self.port = source_type, port or LocalContextAssembler()
    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        started = time.monotonic()
        try:
            candidate_input = await context.input(context.invocation.inputs[0].id); index_input = await context.input(context.invocation.inputs[1].id)
            if ((candidate_input.reference.artifact_type, candidate_input.reference.schema_revision) != (self.source_type, "v1") or (index_input.reference.artifact_type, index_input.reference.schema_revision) != ("search.index.result", "v1") or hashlib.sha256(candidate_input.content).hexdigest() != candidate_input.reference.content_digest or hashlib.sha256(index_input.content).hexdigest() != index_input.reference.content_digest): raise PluginError(PluginErrorCode.CONTEXT_INPUT_INVALID)
            kind = {"retrieval.candidate.set": RetrievalCandidateSet, "fusion.candidate.set": FusionCandidateSet, "rerank.candidate.set": RerankedCandidateSet}[self.source_type]
            candidates = kind.model_validate_json(candidate_input.content); index = SearchIndexResult.model_validate_json(index_input.content)
            if isinstance(candidates, RetrievalCandidateSet): expected = retrieval_id(candidates.index, candidates.index_id, candidates.retriever_plugin_id, candidates.implementation_digest, candidates.contributor_id, candidates.configuration_digest, candidates.filtered_count, candidates.candidates)
            elif isinstance(candidates, FusionCandidateSet): expected = fusion_id(candidates.index, candidates.index_id, candidates.fusion_plugin_id, candidates.implementation_digest, candidates.configuration_digest, candidates.contributor_set_ids, candidates.candidates)
            else: expected = rerank_id(candidates.fusion_candidate_set_id, candidates.index, candidates.reranker_plugin_id, candidates.implementation_digest, candidates.configuration_digest, candidates.input_candidates, candidates.candidates, candidates.decisions)
            if candidates.candidate_set_id != expected: raise PluginError(PluginErrorCode.CONTEXT_INPUT_INVALID)
            config = ContextAssemblerConfig.model_validate(context.invocation.validated_configuration); binding = IndexArtifactBinding(id=index_input.reference.id, content_digest=index_input.reference.content_digest)
            request = ContextAssemblyRequest(candidates=candidates, index=index, index_binding=binding, configuration=config, configuration_digest=configuration_digest(config.model_dump(mode="json")), plugin_id=context.invocation.plugin_id, implementation_digest=context.invocation.implementation_digest, cancellation=context.cancellation, deadline_at=context.invocation.deadline_at)
            result = await asyncio.to_thread(self.port.assemble, request)  # type: ignore[union-attr]
            if not isinstance(result, EvidenceSet) or result.evidence_set_id != evidence_set_id(candidates.candidate_set_id, binding, index.index_id, request.plugin_id, request.implementation_digest, request.configuration_digest, result.items, result.decisions, result.shortage): raise PluginError(PluginErrorCode.CONTEXT_CANDIDATE_INVALID)
        except PluginError: raise
        except (ValidationError, ValueError, TypeError) as exc: raise PluginError(PluginErrorCode.CONTEXT_INPUT_INVALID) from exc
        metrics = ({"name": "context_selected", "value": len(result.items)}, {"name": "context_excluded", "value": sum(item.reason == "excluded_budget" for item in result.decisions)}, {"name": "context_duration_ms", "value": int((time.monotonic() - started) * 1000)})
        signals = ({"name": "context_validation", "status": "PASS", "summary": "validated"}, {"name": "context_shortage", "status": "WARN" if result.shortage.reason != "none" else "PASS", "value": result.shortage.reason, "summary": result.shortage.reason})
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="evidence.set", schema_revision="v1", content=evidence_set_bytes(result), summary="evidence context assembled", metrics=metrics, quality_signals=signals),), summary="evidence context assembled")
