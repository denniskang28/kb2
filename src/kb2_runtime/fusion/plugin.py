from __future__ import annotations
import asyncio, hashlib, time
from pydantic import ValidationError
from kb2_runtime.plugins.contracts import PluginContext, PluginInvocationResult, PluginOutput, configuration_digest
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode
from kb2_runtime.retrieval.contracts import RetrievalCandidateSet
from kb2_runtime.retrieval.serializer import candidate_set_id as retrieval_set_id
from .contracts import FusionCandidateSet, FusionConfig, FusionRequest
from .local import ReciprocalRankFusion
from .serializer import candidate_set_id, fusion_candidate_set_bytes

def _valid_source(value: RetrievalCandidateSet) -> bool:
    return value.candidate_set_id == retrieval_set_id(value.index, value.index_id, value.retriever_plugin_id, value.implementation_digest, value.contributor_id, value.configuration_digest, value.filtered_count, value.candidates)

class FusionPlugin:
    def __init__(self, port: object | None = None) -> None:
        self.port = port or ReciprocalRankFusion()

    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        started = time.monotonic()
        try:
            values = []
            for reference in context.invocation.inputs:
                item = await context.input(reference.id)
                if (item.reference.artifact_type, item.reference.schema_revision) != ("retrieval.candidate.set", "v1") or hashlib.sha256(item.content).hexdigest() != item.reference.content_digest: raise PluginError(PluginErrorCode.FUSION_INPUT_INVALID)
                value = RetrievalCandidateSet.model_validate_json(item.content)
                if not _valid_source(value): raise PluginError(PluginErrorCode.FUSION_CANDIDATE_INVALID)
                values.append(value)
            config = FusionConfig.model_validate(context.invocation.validated_configuration)
            request = FusionRequest(candidate_sets=tuple(values), configuration=config, configuration_digest=configuration_digest(config.model_dump(mode="json")), plugin_id=context.invocation.plugin_id, implementation_digest=context.invocation.implementation_digest, cancellation=context.cancellation, deadline_at=context.invocation.deadline_at)
            result = await asyncio.to_thread(self.port.fuse, request)  # type: ignore[union-attr]
            expected = candidate_set_id(result.index, result.index_id, request.plugin_id, request.implementation_digest, request.configuration_digest, result.contributor_set_ids, result.candidates)
            if result.candidate_set_id != expected: raise PluginError(PluginErrorCode.FUSION_CANDIDATE_INVALID)
        except PluginError: raise
        except (ValidationError, ValueError, TypeError) as exc: raise PluginError(PluginErrorCode.FUSION_INPUT_INVALID) from exc
        metrics = ({"name": "fusion_input_sets", "value": len(values)}, {"name": "fusion_input_candidates", "value": sum(len(item.candidates) for item in values)}, {"name": "fusion_deduplicated", "value": sum(len(item.candidates) for item in values) - len(result.candidates)}, {"name": "fusion_duration_ms", "value": int((time.monotonic() - started) * 1000)})
        signals = ({"name": "fusion_validation", "status": "PASS", "summary": "validated"}, {"name": "no_candidates", "status": "PASS", "value": not result.candidates, "summary": "none" if not result.candidates else "candidates found"})
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="fusion.candidate.set", schema_revision="v1", content=fusion_candidate_set_bytes(result), summary="fusion candidates created", metrics=metrics, quality_signals=signals),), summary="fusion candidates created")
