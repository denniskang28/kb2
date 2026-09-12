from __future__ import annotations

import asyncio
import hashlib
import time

from pydantic import ValidationError

from kb2_runtime.indexing.contracts import SearchIndexResult
from kb2_runtime.plugins.contracts import PluginContext, PluginInvocationResult, PluginOutput, configuration_digest
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode

from .contracts import HierarchyRetrieverConfig, IndexArtifactBinding, RetrievalCandidateSet, RetrieverConfig, RetrieverRequest
from .local import HierarchyRetriever, KeywordRetriever, MetadataRetriever, TableRetriever, VectorRetriever
from .serializer import candidate_id, candidate_set_id, retrieval_candidate_set_bytes


def _validate_result(result: RetrievalCandidateSet, request: RetrieverRequest) -> None:
    if (result.index != request.index_binding or result.index_id != request.index.index_id
            or result.document_id != request.index.documents[0].document_id
            or result.retriever_plugin_id != request.plugin_id
            or result.implementation_digest != request.implementation_digest
            or result.contributor_id != request.contributor_id
            or result.configuration_digest != request.configuration_digest
            or result.filtered_count > request.index.document_count):
        raise PluginError(PluginErrorCode.RETRIEVAL_CANDIDATE_INVALID)
    documents = {item.chunk_id: item for item in request.index.documents}
    for candidate in result.candidates:
        source = documents.get(candidate.chunk_id)
        if (source is None or candidate.document_id != source.document_id
                or candidate.candidate_id != candidate_id(request.index.index_id, request.contributor_id, candidate.chunk_id)):
            raise PluginError(PluginErrorCode.RETRIEVAL_CANDIDATE_INVALID)
        citations = {(item.element_id, item.locator.model_dump_json()) for item in source.citations}
        if any((element_id, locator.model_dump_json()) not in citations for element_id, locator in zip(candidate.element_ids, candidate.locators, strict=True)):
            raise PluginError(PluginErrorCode.RETRIEVAL_CANDIDATE_INVALID)
    if result.candidate_set_id != candidate_set_id(
        request.index_binding, request.index.index_id, request.plugin_id,
        request.implementation_digest, request.contributor_id,
        request.configuration_digest, result.filtered_count, result.candidates,
    ):
        raise PluginError(PluginErrorCode.RETRIEVAL_CANDIDATE_INVALID)


class RetrievalPlugin:
    def __init__(self, port: object, config_model: type[RetrieverConfig]) -> None:
        self.port, self.config_model = port, config_model

    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        started = time.monotonic()
        try:
            question_input = await context.input(context.invocation.inputs[0].id)
            index_input = await context.input(context.invocation.inputs[1].id)
            if (question_input.reference.artifact_type, question_input.reference.schema_revision) != ("opaque.bytes", "v1") or (index_input.reference.artifact_type, index_input.reference.schema_revision) != ("search.index.result", "v1"):
                raise ValueError("invalid retrieval schemas")
            query = question_input.content.decode("utf-8")
            if not query or len(query) > 4096:
                raise ValueError("invalid query")
            if hashlib.sha256(index_input.content).hexdigest() != index_input.reference.content_digest:
                raise PluginError(PluginErrorCode.RETRIEVAL_INDEX_IDENTITY_STALE)
            index = SearchIndexResult.model_validate_json(index_input.content)
            config = self.config_model.model_validate(context.invocation.validated_configuration)
            request = RetrieverRequest(query=query, index=index, index_binding=IndexArtifactBinding(id=index_input.reference.id, artifact_type=index_input.reference.artifact_type, schema_revision=index_input.reference.schema_revision, content_digest=index_input.reference.content_digest), contributor_id=context.invocation.stage_key, configuration=config, configuration_digest=configuration_digest(config.model_dump(mode="json")), plugin_id=context.invocation.plugin_id, implementation_digest=context.invocation.implementation_digest, cancellation=context.cancellation, deadline_at=context.invocation.deadline_at)
            result = await asyncio.to_thread(self.port.retrieve, request)  # type: ignore[union-attr]
            if not isinstance(result, RetrievalCandidateSet):
                raise PluginError(PluginErrorCode.RETRIEVAL_CANDIDATE_INVALID)
            _validate_result(result, request)
        except PluginError:
            raise
        except (UnicodeDecodeError, ValidationError, ValueError, TypeError) as exc:
            raise PluginError(PluginErrorCode.RETRIEVAL_INPUT_INVALID) from exc
        metrics = ({"name": "retrieval_candidates", "value": len(result.candidates)}, {"name": "retrieval_filtered", "value": result.filtered_count}, {"name": "retrieval_duration_ms", "value": int((time.monotonic() - started) * 1000)})
        signals = ({"name": "retrieval_validation", "status": "PASS", "summary": "validated"}, {"name": "retrieval_strategy", "status": "PASS", "value": context.invocation.plugin_id, "summary": "selected"}, {"name": "no_candidates", "status": "PASS", "value": not result.candidates, "summary": "none" if not result.candidates else "candidates found"})
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="retrieval.candidate.set", schema_revision="v1", content=retrieval_candidate_set_bytes(result), summary="retrieval candidates created", metrics=metrics, quality_signals=signals),), summary="retrieval candidates created")


def keyword_plugin() -> RetrievalPlugin: return RetrievalPlugin(KeywordRetriever(), RetrieverConfig)
def vector_plugin() -> RetrievalPlugin: return RetrievalPlugin(VectorRetriever(), RetrieverConfig)
def hierarchy_plugin() -> RetrievalPlugin: return RetrievalPlugin(HierarchyRetriever(), HierarchyRetrieverConfig)
def table_plugin() -> RetrievalPlugin: return RetrievalPlugin(TableRetriever(), RetrieverConfig)
def metadata_plugin() -> RetrievalPlugin: return RetrievalPlugin(MetadataRetriever(), RetrieverConfig)
