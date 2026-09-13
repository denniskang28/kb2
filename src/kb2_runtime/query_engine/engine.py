from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from uuid import UUID

from kb2_runtime.plugins.executor import PluginExecutor
from kb2_runtime.plugins.errors import PluginError
from kb2_runtime.generation.contracts import VerificationResult
from kb2_runtime.query_profiles.compiler import ResolvedQueryPlan
from kb2_runtime.trace.contracts import ArtifactInput, EngineKind
from kb2_runtime.trace.service import ArtifactService, RunService


@dataclass(frozen=True)
class QueryReceipt:
    run_id: UUID
    profile_id: str
    plan_digest: str
    outputs: dict[str, UUID]


class QueryEngine:
    """Run only the precompiled linear plan; all graph binding is already frozen."""
    def __init__(self, executor: PluginExecutor, runs: RunService, artifacts: ArtifactService) -> None:
        self.executor, self.runs, self.artifacts = executor, runs, artifacts

    async def execute(self, plan: ResolvedQueryPlan, question_artifact: UUID, search_artifact: UUID, cancellation: asyncio.Event | None = None) -> QueryReceipt:
        payload = plan.canonical_payload
        manifest = await self.artifacts.get_artifact_manifest(search_artifact)
        binding = payload["search_artifact"]
        if manifest is None or str(manifest.id) != binding["artifact_id"] or manifest.content_digest != binding["content_digest"]:
            raise ValueError("search artifact does not match compiled plan")
        run_id = await self.runs.create_run(EngineKind.QUERY, payload)
        return await self._execute_created(plan, run_id, question_artifact, search_artifact, cancellation)

    async def submit(self, plan: ResolvedQueryPlan, question: str, search_artifact: UUID,
                     cancellation: asyncio.Event | None = None, on_created=None) -> QueryReceipt:
        """Create a query Run and materialize a bounded question in its lineage.

        The question is deliberately absent from the frozen plan and all safe
        summaries.  Existing ``execute`` callers continue to supply their own
        already-published question Artifact.
        """
        normalized = question.strip()
        try:
            content = normalized.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("QUERY_QUESTION_INVALID") from exc
        if not normalized or len(content) > 8 * 1024:
            raise ValueError("QUERY_QUESTION_INVALID")
        payload = plan.canonical_payload
        manifest = await self.artifacts.get_artifact_manifest(search_artifact)
        binding = payload["search_artifact"]
        if manifest is None or str(manifest.id) != binding["artifact_id"] or manifest.content_digest != binding["content_digest"]:
            raise ValueError("search artifact does not match compiled plan")
        run_id = await self.runs.create_run(EngineKind.QUERY, payload)
        if on_created is not None:
            on_created(run_id)
        try:
            attempt_id, _ = await self.runs.start_attempt(run_id, "query.input")
            digest = hashlib.sha256(content).hexdigest()
            question_artifact = (await self.artifacts.complete_with_outputs(
                run_id, attempt_id,
                ((ArtifactInput(artifact_type="opaque.bytes", schema_revision="v1", content_digest=digest,
                                byte_size=len(content), producing_plugin_id="query.input@1",
                                configuration_digest=hashlib.sha256(b"query.input/v1").hexdigest(),
                                summary="bounded query input"), content),),
                summary="bounded query input materialized",
            ))[0]
        except Exception:
            await self.runs.finish_run(run_id, succeeded=False)
            raise
        return await self._execute_created(plan, run_id, question_artifact, search_artifact, cancellation)

    async def _execute_created(self, plan: ResolvedQueryPlan, run_id: UUID, question_artifact: UUID,
                               search_artifact: UUID, cancellation: asyncio.Event | None) -> QueryReceipt:
        payload = plan.canonical_payload
        logical: dict[str, UUID] = {"query.question": question_artifact, "search.index": search_artifact}
        try:
            for stage in payload["stages"]:
                if stage["kind"] == "repair":
                    try:
                        await self._repair(run_id, stage, payload["stages"], logical, question_artifact, cancellation)
                    except PluginError as error:
                        if error.code.value not in {"GENERATION_UNAVAILABLE", "GENERATION_PROVIDER_FAILED", "PLUGIN_DESCRIPTOR_INVALID", "PLUGIN_UNAVAILABLE"}:
                            raise
                        final = next(item for item in payload["stages"] if item["kind"] == "final_state")
                        evidence = next(value for key, value in logical.items() if key.endswith(".evidence"))
                        logical["final.response"] = (await self.executor.invoke(run_id, f"{final['stage_id']}.repair-failure", final["plugin_id"], final["configuration"], (evidence,), cancellation))[0]
                        await self.runs.finish_run(run_id, succeeded=True)
                        return QueryReceipt(run_id, plan.profile_id, plan.digest, dict(logical))
                    continue
                inputs: list[UUID] = []
                for port in stage["inputs"]:
                    sources = port["source"] if isinstance(port["source"], list) else [port["source"]]
                    inputs.extend(logical[source] for source in sources)
                try:
                    output_ids = await self.executor.invoke(run_id, stage["stage_id"], stage["plugin_id"], stage["configuration"], tuple(inputs), cancellation)
                except PluginError as error:
                    if stage["kind"] != "generate" or error.code.value not in {"GENERATION_UNAVAILABLE", "GENERATION_PROVIDER_FAILED", "PLUGIN_DESCRIPTOR_INVALID", "PLUGIN_UNAVAILABLE"}:
                        raise
                    final = next(item for item in payload["stages"] if item["kind"] == "final_state")
                    evidence = next(value for key, value in logical.items() if key.endswith(".evidence"))
                    response = (await self.executor.invoke(run_id, f"{final['stage_id']}.generation-failure", final["plugin_id"], final["configuration"], (evidence,), cancellation))[0]
                    logical["final.response"] = response
                    await self.runs.finish_run(run_id, succeeded=True)
                    return QueryReceipt(run_id, plan.profile_id, plan.digest, dict(logical))
                for output, artifact_id in zip(stage["outputs"], output_ids, strict=True):
                    logical[f"{stage['stage_id']}.{output['name']}"] = artifact_id
            await self.runs.finish_run(run_id, succeeded=True)
            return QueryReceipt(run_id, plan.profile_id, plan.digest, dict(logical))
        except Exception:
            await self.runs.finish_run(run_id, succeeded=False)
            raise


    async def _repair(self, run_id: UUID, repair: dict[str, object], stages: list[dict[str, object]], logical: dict[str, UUID], question: UUID, cancellation: asyncio.Event | None) -> None:
        """The sole loop is compiler-authorized and reuses the initial generator/verifier bindings."""
        generate = next(stage for stage in stages if stage["kind"] == "generate")
        verify = next(stage for stage in stages if stage["kind"] == "verify")
        evidence_source = next(item["source"] for item in repair["inputs"] if item["name"] == "evidence")
        evidence = logical[evidence_source]
        answer_source = next(item["source"] for item in repair["inputs"] if item["name"] == "answer")
        answer = logical[answer_source]
        verification_source = next(item["source"] for item in repair["inputs"] if item["name"] == "verification")
        verification = logical[verification_source]
        result = VerificationResult.model_validate_json(await self.artifacts.read_content(verification))
        if result.outcome != "repairable":
            logical[f"{repair['stage_id']}.answer"] = answer
            logical[f"{repair['stage_id']}.verification"] = verification
            return
        for attempt in range(1, int(repair["max_attempts"]) + 1):
            # A repair is never allowed to use the repair stage's input graph for retrieval.
            answer = (await self.executor.invoke(run_id, f"{repair['stage_id']}.generate-{attempt}", generate["plugin_id"], generate["configuration"], (question, evidence), cancellation))[0]
            verification = (await self.executor.invoke(run_id, f"{repair['stage_id']}.verify-{attempt}", verify["plugin_id"], verify["configuration"], (answer, evidence), cancellation))[0]
            logical[f"{repair['stage_id']}.answer"] = answer
            logical[f"{repair['stage_id']}.verification"] = verification
            result = VerificationResult.model_validate_json(await self.artifacts.read_content(verification))
            if result.outcome != "repairable":
                return
