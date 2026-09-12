from __future__ import annotations

import asyncio
from collections.abc import Callable
import hashlib
import json
from typing import Any
from uuid import UUID

from kb2_runtime.ingestion_profiles import CompiledProfileSet, ProfileResolver, ResolutionRecord, evaluate_condition
from kb2_runtime.plugins.executor import PluginExecutor
from kb2_runtime.plugins.registry import PluginRegistry
from kb2_runtime.trace.contracts import ArtifactInput, EngineKind, IngestionEvidence, QualitySignal, SafeError
from kb2_runtime.trace.errors import TraceError, TraceErrorCode
from kb2_runtime.trace.service import ArtifactService, RunService

from .contracts import IngestionReceipt, SourceSubmission
from .errors import IngestionError, IngestionErrorCode


class IngestionEngine:
    """Execute the complete immutable Profile plan in its declared linear order."""

    def __init__(
        self,
        registry: PluginRegistry,
        executor: PluginExecutor,
        runs: RunService,
        artifacts: ArtifactService,
        resolver: ProfileResolver | None = None,
    ) -> None:
        self.registry = registry
        self.executor = executor
        self.runs = runs
        self.artifacts = artifacts
        self.resolver = resolver or ProfileResolver()

    async def submit(
        self,
        compiled: CompiledProfileSet,
        source: SourceSubmission,
        resolution: Any,
        cancellation: asyncio.Event | None = None,
        on_run_created: Callable[[UUID], None] | None = None,
    ) -> IngestionReceipt:
        record = self.resolver.resolve(compiled, resolution)
        self._validate_source(record, source)
        plan = record.plan.canonical_payload
        run_id = await self.runs.create_run(EngineKind.INGESTION, plan)
        if on_run_created is not None:
            on_run_created(run_id)
        try:
            await self.runs.record_ingestion_evidence(run_id, self._evidence(record))
            logical = {"document.source": await self._materialize_source(run_id, source)}
            quality: dict[str, Any] = {}
            for stage in plan["stages"]:
                for sub_stage in stage["sub_stages"]:
                    await self._execute_sub_stage(run_id, stage["axis"], sub_stage, stage.get("legacy_alias", False), logical, quality, resolution.observables(), cancellation)
            await self.runs.finish_run(run_id, succeeded=True)
            return IngestionReceipt(run_id=run_id, profile_id=record.selected_profile_id, plan_digest=record.plan.digest, outputs=dict(logical))
        except Exception:
            await self._finish_failed(run_id)
            raise

    def _validate_source(self, record: ResolutionRecord, source: SourceSubmission) -> None:
        if "source" not in record.plan.canonical_payload.get("document_inputs", {}):
            raise IngestionError(IngestionErrorCode.SOURCE_SCHEMA_MISMATCH)
        profile_schema = record.plan.canonical_payload.get("document_inputs", {}).get("source")
        if profile_schema and (source.source_schema.artifact_type, source.source_schema.schema_revision) != (profile_schema["artifact_type"], profile_schema["schema_revision"]):
            raise IngestionError(IngestionErrorCode.SOURCE_SCHEMA_MISMATCH)

    async def _materialize_source(self, run_id: UUID, source: SourceSubmission) -> UUID:
        attempt_id, _ = await self.runs.start_attempt(run_id, "ingestion.source")
        digest = hashlib.sha256(source.content).hexdigest()
        configuration = json.dumps(source.source_schema.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        artifact = ArtifactInput(
            artifact_type=source.source_schema.artifact_type,
            schema_revision=source.source_schema.schema_revision,
            content_digest=digest,
            byte_size=len(source.content),
            producing_plugin_id="ingestion.source@1",
            configuration_digest=hashlib.sha256(configuration).hexdigest(),
            summary="submitted ingestion source",
        )
        return (await self.artifacts.complete_with_outputs(run_id, attempt_id, [(artifact, source.content)]))[0]

    async def _execute_sub_stage(
        self, run_id: UUID, axis: str, sub_stage: dict[str, Any], legacy_axis: bool, logical: dict[str, UUID], quality: dict[str, Any], document: dict[str, Any], cancellation: asyncio.Event | None
    ) -> None:
        accepted = False
        for candidate_number, candidate in enumerate(sub_stage["candidates"], start=1):
            stage_key = f"{axis}.{sub_stage['stage_id']}.candidate-{candidate_number}"
            input_ids = self._input_ids(candidate, logical)
            if not evaluate_condition(candidate.get("when"), document, quality):
                attempt_id, _ = await self.runs.start_attempt(run_id, stage_key, input_ids)
                await self.runs.skip_attempt(attempt_id, "candidate condition did not match")
                await self._record_selection(attempt_id, "rejected")
                continue
            if cancellation is not None and cancellation.is_set():
                attempt_id, _ = await self.runs.start_attempt(run_id, stage_key, input_ids)
                await self.runs.fail_attempt(
                    attempt_id,
                    SafeError(code=TraceErrorCode.PLUGIN_INVOCATION_CANCELLED, category="lifecycle", message="ingestion was cancelled"),
                )
                raise IngestionError(IngestionErrorCode.STAGE_EXHAUSTED)
            if not self._descriptor_matches(candidate):
                await self._record_drift(run_id, stage_key, input_ids)
                raise IngestionError(IngestionErrorCode.PLAN_IMPLEMENTATION_DRIFT)
            for retry in range(2):
                try:
                    receipt = await self.executor.invoke_with_receipt(
                        run_id, stage_key, candidate["plugin_id"], candidate["configuration"], input_ids, cancellation
                    )
                except Exception:
                    if cancellation is not None and cancellation.is_set():
                        raise IngestionError(IngestionErrorCode.STAGE_EXHAUSTED) from None
                    if retry == 0 and await self._retryable(run_id, stage_key):
                        continue
                    break
                if not await self._outputs_match(receipt.output_ids, candidate):
                    await self.runs.invalidate_attempt(
                        receipt.attempt_id,
                        SafeError(
                            code=TraceErrorCode.STAGE_OUTPUT_INVALID,
                            category="validation",
                            message="published output did not match the pinned contract",
                        ),
                    )
                    await self._record_selection(receipt.attempt_id, "rejected")
                    break
                status, values = self._quality(receipt.quality_signals)
                self._record_quality(quality, axis, sub_stage["stage_id"], values, legacy_axis)
                if status in candidate["accept_quality"]:
                    await self._record_selection(receipt.attempt_id, "accepted")
                    for output, artifact_id in zip(candidate["outputs"], receipt.output_ids, strict=True):
                        logical[f"{axis}.{sub_stage['stage_id']}.{output['name']}"] = artifact_id
                        if legacy_axis:
                            logical[f"{axis}.{output['name']}"] = artifact_id
                    accepted = True
                    break
                await self._record_selection(receipt.attempt_id, "rejected")
                break
            if accepted:
                return
        raise IngestionError(IngestionErrorCode.STAGE_EXHAUSTED)

    @staticmethod
    def _input_ids(candidate: dict[str, Any], logical: dict[str, UUID]) -> tuple[UUID, ...]:
        try:
            return tuple(logical[item["source"]] for item in candidate["inputs"])
        except KeyError as exc:
            raise IngestionError(IngestionErrorCode.OUTPUT_INVALID) from exc

    def _descriptor_matches(self, candidate: dict[str, Any]) -> bool:
        try:
            descriptor = self.registry.get(candidate["plugin_id"]).descriptor
        except Exception:
            return False
        return (
            descriptor.plugin_id == candidate["plugin_id"]
            and descriptor.implementation_digest == candidate["implementation_digest"]
            and descriptor.runner.value == candidate["runner"]
            and [(port.name, port.artifact_type, port.schema_revision) for port in descriptor.input_ports]
            == [(item["name"], item["artifact_type"], item["schema_revision"]) for item in candidate["inputs"]]
            and [(port.name, port.artifact_type, port.schema_revision) for port in descriptor.output_ports]
            == [(item["name"], item["artifact_type"], item["schema_revision"]) for item in candidate["outputs"]]
        )

    async def _outputs_match(self, output_ids: tuple[UUID, ...], candidate: dict[str, Any]) -> bool:
        if len(output_ids) != len(candidate["outputs"]):
            return False
        manifests = [await self.artifacts.get_artifact_manifest(artifact_id) for artifact_id in output_ids]
        return all(manifest is not None and (manifest.artifact_type, manifest.schema_revision) == (output["artifact_type"], output["schema_revision"])
                   for manifest, output in zip(manifests, candidate["outputs"], strict=True))

    @staticmethod
    def _quality(signals: tuple[QualitySignal, ...]) -> tuple[str, dict[str, Any]]:
        rank = {"PASS": 0, "WARN": 1, "FAIL": 2}
        worst = max((signal.status for signal in signals), key=lambda value: rank[value], default="PASS")
        return worst, {signal.name: signal.value for signal in signals}

    @staticmethod
    def _record_quality(quality: dict[str, Any], axis: str, stage_id: str, values: dict[str, Any], legacy: bool) -> None:
        for name, value in values.items():
            quality[f"quality.{axis}.{stage_id}.{name}"] = value
            if legacy:
                quality[f"quality.{axis}.{name}"] = value

    async def _record_selection(self, attempt_id: UUID, value: str) -> None:
        await self.runs.record_attempt_observations(
            attempt_id, quality_signals=(QualitySignal(name="engine.candidate-selection", status="PASS" if value == "accepted" else "WARN", value=value, summary="candidate selection"),)
        )

    async def _retryable(self, run_id: UUID, stage_key: str) -> bool:
        trace = await self.runs.get_run_trace(run_id)
        if trace is None:
            return False
        stages = [stage for stage in trace.stages if stage.stage_key == stage_key]
        return bool(stages and stages[-1].safe_error and stages[-1].safe_error.retryable)

    async def _record_drift(self, run_id: UUID, stage_key: str, input_ids: tuple[UUID, ...]) -> None:
        attempt_id, _ = await self.runs.start_attempt(run_id, stage_key, input_ids)
        await self.runs.fail_attempt(attempt_id, SafeError(code=TraceErrorCode.PLAN_IMPLEMENTATION_DRIFT, category="validation", message="pinned implementation differs from registry"))

    async def _finish_failed(self, run_id: UUID) -> None:
        try:
            await self.runs.finish_run(run_id, succeeded=False)
        except TraceError:
            pass

    @staticmethod
    def _evidence(record: ResolutionRecord) -> IngestionEvidence:
        return IngestionEvidence(
            candidate_profile_ids=record.candidate_profile_ids,
            evaluated_rules=record.evaluated_rules,
            observables=record.observables,
            selected_profile_id=record.selected_profile_id,
            selection_tier=record.selection_tier,
            plan_digest=record.plan.digest,
        )
