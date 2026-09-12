from __future__ import annotations
import asyncio, hashlib, time
from pydantic import ValidationError
from kb2_runtime.fusion.contracts import FusionCandidateSet
from kb2_runtime.fusion.serializer import candidate_set_id as fusion_candidate_set_id
from kb2_runtime.indexing.contracts import SearchIndexResult
from kb2_runtime.plugins.contracts import PluginContext, PluginInvocationResult, PluginOutput, configuration_digest
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode
from kb2_runtime.retrieval.contracts import IndexArtifactBinding
from .contracts import RerankedCandidateSet, RerankerConfig, RerankerRequest
from .local import LexicalOverlapReranker
from .serializer import candidate_set_id, reranked_candidate_set_bytes
class RerankingPlugin:
    def __init__(self, port: object | None = None) -> None:
        self.port = port or LexicalOverlapReranker()

    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        started = time.monotonic()
        try:
            question = await context.input(context.invocation.inputs[0].id)
            fused = await context.input(context.invocation.inputs[1].id)
            index_input = await context.input(context.invocation.inputs[2].id)
            if (question.reference.artifact_type, question.reference.schema_revision) != ("opaque.bytes", "v1") or (fused.reference.artifact_type, fused.reference.schema_revision) != ("fusion.candidate.set", "v1") or (index_input.reference.artifact_type, index_input.reference.schema_revision) != ("search.index.result", "v1"): raise PluginError(PluginErrorCode.RERANK_INPUT_INVALID)
            query = question.content.decode("utf-8")
            if (not query or len(query) > 4096
                    or hashlib.sha256(fused.content).hexdigest() != fused.reference.content_digest
                    or hashlib.sha256(index_input.content).hexdigest() != index_input.reference.content_digest):
                raise PluginError(PluginErrorCode.RERANK_INPUT_INVALID)
            value = FusionCandidateSet.model_validate_json(fused.content); index = SearchIndexResult.model_validate_json(index_input.content); config = RerankerConfig.model_validate(context.invocation.validated_configuration)
            if value.candidate_set_id != fusion_candidate_set_id(value.index, value.index_id, value.fusion_plugin_id, value.implementation_digest, value.configuration_digest, value.contributor_set_ids, value.candidates):
                raise PluginError(PluginErrorCode.RERANK_INPUT_INVALID)
            binding = IndexArtifactBinding(id=index_input.reference.id, content_digest=index_input.reference.content_digest)
            request = RerankerRequest(question=query, fused=value, index=index, index_binding=binding, configuration=config, configuration_digest=configuration_digest(config.model_dump(mode="json")), plugin_id=context.invocation.plugin_id, implementation_digest=context.invocation.implementation_digest, cancellation=context.cancellation, deadline_at=context.invocation.deadline_at)
            result = await asyncio.to_thread(self.port.rerank, request)  # type: ignore[union-attr]
            if result.candidate_set_id != candidate_set_id(value.candidate_set_id, binding, request.plugin_id, request.implementation_digest, request.configuration_digest, result.input_candidates, result.candidates, result.decisions): raise PluginError(PluginErrorCode.RERANK_CANDIDATE_INVALID)
        except PluginError: raise
        except (UnicodeDecodeError, ValidationError, ValueError, TypeError) as exc: raise PluginError(PluginErrorCode.RERANK_INPUT_INVALID) from exc
        metrics = ({"name": "rerank_input_candidates", "value": len(value.candidates)}, {"name": "rerank_included", "value": len(result.candidates)}, {"name": "rerank_excluded", "value": len(value.candidates) - len(result.candidates)}, {"name": "rerank_duration_ms", "value": int((time.monotonic() - started) * 1000)})
        signals = ({"name": "rerank_validation", "status": "PASS", "summary": "validated"}, {"name": "no_candidates", "status": "PASS", "value": not result.candidates, "summary": "none" if not result.candidates else "candidates found"})
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="rerank.candidate.set", schema_revision="v1", content=reranked_candidate_set_bytes(result), summary="reranked candidates created", metrics=metrics, quality_signals=signals),), summary="reranked candidates created")
