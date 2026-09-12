from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

from .contracts import ArtifactInput, ArtifactManifest, EngineKind, IngestionEvidence, Metric, QualitySignal, RunTrace, SafeError, StageResult
from .errors import TraceError, TraceErrorCode
from .repositories import TraceRepository
from .schemas import schema_is_supported
from .storage import ArtifactStore


def plan_digest(plan: dict[str, Any]) -> str:
    """Digest canonical declarative plan data; reject non-JSON values and oversized snapshots."""
    try:
        encoded = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    except (TypeError, ValueError) as exc:
        raise TraceError(TraceErrorCode.PLAN_SNAPSHOT_INVALID) from exc
    if len(encoded) > 64 * 1024:
        raise TraceError(TraceErrorCode.PLAN_SNAPSHOT_INVALID)
    return hashlib.sha256(encoded).hexdigest()


class RunService:
    def __init__(self, repository: TraceRepository) -> None:
        self.repository = repository

    async def create_run(self, engine_kind: EngineKind, resolved_plan: dict[str, Any]) -> UUID:
        digest = plan_digest(resolved_plan)
        snapshot_id = await self.repository.create_plan(digest, resolved_plan)
        return await self.repository.create_run(engine_kind, snapshot_id)

    async def start_attempt(self, run_id: UUID, stage_key: str, input_ids: Sequence[UUID] = ()) -> tuple[UUID, int]:
        if not stage_key or len(stage_key) > 64:
            raise TraceError(TraceErrorCode.STAGE_TRANSITION_INVALID)
        return await self.repository.start_attempt(run_id, stage_key, input_ids)

    async def fail_attempt(self, attempt_id: UUID, error: SafeError, summary: str = "") -> None:
        await self.repository.finish_attempt(attempt_id, StageResult.FAILED, summary, error)

    async def invalidate_attempt(self, attempt_id: UUID, error: SafeError, summary: str = "") -> None:
        """Invalidate a published attempt whose post-publication contract check failed."""
        await self.repository.invalidate_attempt(attempt_id, error, summary)

    async def skip_attempt(self, attempt_id: UUID, summary: str = "") -> None:
        await self.repository.finish_attempt(attempt_id, StageResult.SKIPPED, summary)

    async def complete_attempt(self, attempt_id: UUID, summary: str = "") -> None:
        """Complete a control stage whose typed contract intentionally has no outputs."""
        await self.repository.finish_attempt(attempt_id, StageResult.SUCCEEDED, summary)

    async def finish_run(self, run_id: UUID, succeeded: bool) -> None:
        await self.repository.finish_run(
            run_id, StageResult.SUCCEEDED if succeeded else StageResult.FAILED
        )

    async def record_run_observations(
        self, run_id: UUID, metrics: Sequence[Metric] = (), quality_signals: Sequence[QualitySignal] = ()
    ) -> None:
        await self.repository.record_run_observations(run_id, metrics, quality_signals)

    async def record_attempt_observations(
        self, attempt_id: UUID, metrics: Sequence[Metric] = (), quality_signals: Sequence[QualitySignal] = ()
    ) -> None:
        await self.repository.record_attempt_observations(attempt_id, metrics, quality_signals)

    async def record_ingestion_evidence(self, run_id: UUID, evidence: IngestionEvidence) -> None:
        await self.repository.record_ingestion_evidence(run_id, evidence)

    async def get_run_trace(self, run_id: UUID) -> RunTrace | None:
        return await self.repository.get_run_trace(run_id)

    async def get_run_plan(self, run_id: UUID) -> dict[str, Any] | None:
        return await self.repository.get_run_plan(run_id)


class ArtifactService:
    def __init__(self, repository: TraceRepository, store: ArtifactStore) -> None:
        self.repository = repository
        self.store = store

    async def complete_with_outputs(
        self,
        run_id: UUID,
        attempt_id: UUID,
        outputs: Sequence[tuple[ArtifactInput, bytes]],
        *,
        summary: str = "",
        metrics: Sequence[Metric] = (),
        quality_signals: Sequence[QualitySignal] = (),
    ) -> tuple[UUID, ...]:
        if not outputs:
            raise TraceError(TraceErrorCode.STAGE_OUTPUT_INVALID)
        published: list[tuple[UUID, ArtifactInput, str]] = []
        try:
            for manifest, content in outputs:
                if not schema_is_supported(manifest.artifact_type, manifest.schema_revision):
                    raise TraceError(TraceErrorCode.ARTIFACT_SCHEMA_UNSUPPORTED)
                locator = self.store.publish(content, manifest.content_digest, manifest.byte_size)
                published.append((uuid4(), manifest, locator))
            await self.repository.complete_outputs(
                attempt_id, run_id, published, summary, metrics, quality_signals
            )
        except TraceError as exc:
            await self.repository.connection.rollback()
            await self._record_safe_failure(attempt_id, exc.code)
            raise
        except Exception as exc:
            await self.repository.connection.rollback()
            await self._record_safe_failure(attempt_id, TraceErrorCode.TRACE_STORAGE_FAILURE)
            raise TraceError(TraceErrorCode.TRACE_STORAGE_FAILURE) from exc
        return tuple(item[0] for item in published)

    async def read_content(self, artifact_id: UUID) -> bytes:
        locations = await self.repository.eligible_artifact_locations(artifact_id)
        if locations is None:
            raise TraceError(TraceErrorCode.ARTIFACT_CONTENT_MISSING)
        content: bytes | None = None
        for location in locations:
            checked = self.store.read(*location)
            if content is None:
                content = checked
        return content or b""

    async def get_artifact_manifest(self, artifact_id: UUID) -> ArtifactManifest | None:
        return await self.repository.get_artifact_manifest(artifact_id)

    async def _record_safe_failure(self, attempt_id: UUID, code: TraceErrorCode) -> None:
        categories = {
            TraceErrorCode.ARTIFACT_DIGEST_MISMATCH: "storage",
            TraceErrorCode.ARTIFACT_CONTENT_MISSING: "storage",
            TraceErrorCode.TRACE_STORAGE_FAILURE: "storage",
        }
        try:
            await self.repository.finish_attempt(
                attempt_id,
                StageResult.FAILED,
                "artifact output was rejected",
                SafeError(
                    code=code,
                    category=categories.get(code, "validation"),
                    message="artifact output was rejected",
                    retryable=code == TraceErrorCode.TRACE_STORAGE_FAILURE,
                ),
            )
        except Exception:
            # The original safe domain failure remains the authoritative caller result.
            await self.repository.connection.rollback()
