from __future__ import annotations

from collections.abc import Sequence
import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .contracts import ArtifactInput, ArtifactManifest, ArtifactReference, EngineKind, IngestionEvidence, Metric, QualitySignal, RunState, RunTrace, SafeError, StageResult, StageState, StageTrace, metadata_contains_sensitive_text, safe_metadata_text
from .errors import TraceError, TraceErrorCode


class TraceRepository:
    """PostgreSQL persistence boundary. All writes use one explicit transaction."""

    def __init__(self, connection: psycopg.AsyncConnection[Any]) -> None:
        self.connection = connection

    @classmethod
    async def connect(cls, **kwargs: Any) -> "TraceRepository":
        return cls(await psycopg.AsyncConnection.connect(row_factory=dict_row, **kwargs))

    async def close(self) -> None:
        await self.connection.close()

    async def create_plan(self, digest: str, plan: dict[str, Any]) -> UUID:
        try:
            canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        except (TypeError, ValueError) as exc:
            raise TraceError(TraceErrorCode.PLAN_SNAPSHOT_INVALID) from exc
        if metadata_contains_sensitive_text(plan) or hashlib.sha256(canonical).hexdigest() != digest:
            raise TraceError(TraceErrorCode.PLAN_SNAPSHOT_INVALID)
        async with self.connection.cursor() as cursor:
            await cursor.execute("SELECT id, plan_json FROM execution_plan_snapshots WHERE plan_digest = %s", (digest,))
            existing = await cursor.fetchone()
            if existing:
                if existing["plan_json"] != plan:
                    raise TraceError(TraceErrorCode.PLAN_SNAPSHOT_INVALID)
                return existing["id"]
            identifier = uuid4()
            await cursor.execute("INSERT INTO execution_plan_snapshots (id, plan_digest, plan_json) VALUES (%s, %s, %s)", (identifier, digest, Jsonb(plan)))
        await self.connection.commit()
        return identifier

    async def create_run(self, engine_kind: EngineKind, plan_snapshot_id: UUID) -> UUID:
        async with self.connection.cursor() as cursor:
            await cursor.execute("SELECT id FROM execution_plan_snapshots WHERE id = %s", (plan_snapshot_id,))
            if not await cursor.fetchone():
                raise TraceError(TraceErrorCode.PLAN_SNAPSHOT_INVALID)
            identifier = uuid4()
            await cursor.execute("INSERT INTO runs (id, engine_kind, plan_snapshot_id) VALUES (%s, %s, %s)", (identifier, engine_kind.value, plan_snapshot_id))
        await self.connection.commit()
        return identifier

    async def start_attempt(self, run_id: UUID, stage_key: str, input_ids: Sequence[UUID] = ()) -> tuple[UUID, int]:
        async with self.connection.cursor() as cursor:
            await cursor.execute("SELECT terminal_state FROM runs WHERE id = %s FOR UPDATE", (run_id,))
            run = await cursor.fetchone()
            if not run or run["terminal_state"] is not None:
                raise TraceError(TraceErrorCode.RUN_TRANSITION_INVALID)
            await cursor.execute("SELECT COALESCE(MAX(attempt_number), 0) + 1 AS number FROM stage_attempts WHERE run_id = %s AND stage_key = %s", (run_id, stage_key))
            number = (await cursor.fetchone())["number"]
            identifier = uuid4()
            await cursor.execute("INSERT INTO stage_attempts (id, run_id, stage_key, attempt_number, state, started_at) VALUES (%s, %s, %s, %s, 'RUNNING', CURRENT_TIMESTAMP)", (identifier, run_id, stage_key, number))
            for ordinal, artifact_id in enumerate(input_ids):
                await cursor.execute("SELECT a.id FROM artifacts a JOIN stage_attempts s ON s.id=a.producing_stage_attempt_id WHERE a.id=%s AND s.state='SUCCEEDED'", (artifact_id,))
                if not await cursor.fetchone():
                    raise TraceError(TraceErrorCode.ARTIFACT_LINEAGE_INVALID)
                await cursor.execute("INSERT INTO stage_attempt_inputs (stage_attempt_id, ordinal, artifact_id) VALUES (%s,%s,%s)", (identifier, ordinal, artifact_id))
            await cursor.execute("UPDATE runs SET state = 'RUNNING', started_at = COALESCE(started_at, CURRENT_TIMESTAMP) WHERE id = %s", (run_id,))
        await self.connection.commit()
        return identifier, number

    async def finish_run(self, run_id: UUID, result: StageResult) -> None:
        if result not in (StageResult.SUCCEEDED, StageResult.FAILED):
            raise TraceError(TraceErrorCode.RUN_TRANSITION_INVALID)
        async with self.connection.cursor() as cursor:
            await cursor.execute("SELECT terminal_state FROM runs WHERE id = %s FOR UPDATE", (run_id,))
            row = await cursor.fetchone()
            if not row or row["terminal_state"] is not None:
                raise TraceError(TraceErrorCode.RUN_TRANSITION_INVALID)
            await cursor.execute("UPDATE runs SET state=%s, terminal_state=%s, ended_at=CURRENT_TIMESTAMP WHERE id=%s", (result.value, result.value, run_id))
        await self.connection.commit()

    async def record_run_observations(
        self, run_id: UUID, metrics: Sequence[Metric] = (), signals: Sequence[QualitySignal] = ()
    ) -> None:
        async with self.connection.cursor() as cursor:
            await cursor.execute("SELECT id FROM runs WHERE id=%s FOR UPDATE", (run_id,))
            if not await cursor.fetchone():
                raise TraceError(TraceErrorCode.RUN_TRANSITION_INVALID)
            await self._metrics(cursor, "run_metrics", "run_id", run_id, metrics)
            await self._signals(cursor, "run_quality_signals", "run_id", run_id, signals)
        await self.connection.commit()

    async def record_attempt_observations(
        self, attempt_id: UUID, metrics: Sequence[Metric] = (), signals: Sequence[QualitySignal] = ()
    ) -> None:
        async with self.connection.cursor() as cursor:
            await cursor.execute("SELECT id FROM stage_attempts WHERE id=%s FOR UPDATE", (attempt_id,))
            if not await cursor.fetchone():
                raise TraceError(TraceErrorCode.STAGE_TRANSITION_INVALID)
            await self._metrics(cursor, "stage_attempt_metrics", "stage_attempt_id", attempt_id, metrics)
            await self._signals(cursor, "stage_attempt_quality_signals", "stage_attempt_id", attempt_id, signals)
        await self.connection.commit()

    async def record_ingestion_evidence(self, run_id: UUID, evidence: IngestionEvidence) -> None:
        evidence = IngestionEvidence.model_validate(evidence.model_dump(mode="python"))
        serialized = evidence.model_dump(mode="json")
        # Keep the verified digest first in the stored JSON too. This has no
        # semantic effect for JSONB and makes the immutable plan binding
        # immediately inspectable in bounded diagnostics.
        payload = {"plan_digest": serialized["plan_digest"], **{
            key: value for key, value in serialized.items() if key != "plan_digest"
        }}
        # plan_digest is validated by IngestionEvidence as a fixed SHA-256
        # digest. Scan every resolver-provided value, but do not classify that
        # opaque digest as a provider-body-shaped string.
        resolver_evidence = {key: value for key, value in payload.items() if key != "plan_digest"}
        if metadata_contains_sensitive_text(resolver_evidence):
            raise TraceError(TraceErrorCode.PLAN_SNAPSHOT_INVALID)
        async with self.connection.cursor() as cursor:
            await cursor.execute("SELECT id FROM runs WHERE id=%s AND engine_kind='ingestion' FOR UPDATE", (run_id,))
            if not await cursor.fetchone():
                raise TraceError(TraceErrorCode.RUN_TRANSITION_INVALID)
            await cursor.execute("INSERT INTO ingestion_run_evidence (run_id, resolution_json) VALUES (%s,%s)", (run_id, Jsonb(payload)))
        await self.connection.commit()

    async def finish_attempt(self, attempt_id: UUID, result: StageResult, summary: str, safe_error: SafeError | None = None, metrics: Sequence[Metric] = (), signals: Sequence[QualitySignal] = ()) -> None:
        state = result.value
        summary = safe_metadata_text(summary)
        safe_error = self._safe_error(safe_error) if safe_error else None
        async with self.connection.cursor() as cursor:
            await cursor.execute("SELECT s.state, r.terminal_state FROM stage_attempts s JOIN runs r ON r.id=s.run_id WHERE s.id = %s FOR UPDATE", (attempt_id,))
            row = await cursor.fetchone()
            if not row or row["state"] != StageState.RUNNING.value or row["terminal_state"] is not None:
                raise TraceError(TraceErrorCode.STAGE_TRANSITION_INVALID)
            await cursor.execute("UPDATE stage_attempts SET state=%s, result=%s, summary=%s, safe_error=%s, ended_at=CURRENT_TIMESTAMP WHERE id=%s", (state, result.value, summary, Jsonb(safe_error.model_dump(mode="json")) if safe_error else None, attempt_id))
            await self._metrics(cursor, "stage_attempt_metrics", "stage_attempt_id", attempt_id, metrics)
            await self._signals(cursor, "stage_attempt_quality_signals", "stage_attempt_id", attempt_id, signals)
        await self.connection.commit()

    async def invalidate_attempt(self, attempt_id: UUID, safe_error: SafeError, summary: str = "") -> None:
        """Make a completed publication ineligible after a bounded contract recheck."""
        summary = safe_metadata_text(summary)
        safe_error = self._safe_error(safe_error)
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                "SELECT s.state, r.terminal_state FROM stage_attempts s JOIN runs r ON r.id=s.run_id WHERE s.id=%s FOR UPDATE",
                (attempt_id,),
            )
            row = await cursor.fetchone()
            if not row or row["state"] != StageState.SUCCEEDED.value or row["terminal_state"] is not None:
                raise TraceError(TraceErrorCode.STAGE_TRANSITION_INVALID)
            await cursor.execute(
                "UPDATE stage_attempts SET state='FAILED', result='FAILED', summary=%s, safe_error=%s, ended_at=CURRENT_TIMESTAMP WHERE id=%s",
                (summary, Jsonb(safe_error.model_dump(mode="json")), attempt_id),
            )
        await self.connection.commit()

    async def complete_outputs(self, attempt_id: UUID, run_id: UUID, items: Sequence[tuple[UUID, ArtifactInput, str]], summary: str, metrics: Sequence[Metric] = (), signals: Sequence[QualitySignal] = ()) -> None:
        summary = safe_metadata_text(summary)
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """SELECT s.state, s.run_id, r.terminal_state FROM stage_attempts s
                JOIN runs r ON r.id=s.run_id WHERE s.id=%s FOR UPDATE""",
                (attempt_id,),
            )
            attempt = await cursor.fetchone()
            if (
                not attempt
                or attempt["run_id"] != run_id
                or attempt["state"] != "RUNNING"
                or attempt["terminal_state"] is not None
            ):
                raise TraceError(TraceErrorCode.STAGE_TRANSITION_INVALID)
            for ordinal, (artifact_id, manifest, locator) in enumerate(items):
                manifest = self._safe_artifact(manifest)
                await cursor.execute("INSERT INTO artifacts (id, artifact_type, schema_revision, content_digest, byte_size, storage_locator, producing_run_id, producing_stage_attempt_id, producing_plugin_id, configuration_digest, summary) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (artifact_id, manifest.artifact_type, manifest.schema_revision, manifest.content_digest, manifest.byte_size, locator, run_id, attempt_id, manifest.producing_plugin_id, manifest.configuration_digest, manifest.summary))
                for parent_ordinal, parent_id in enumerate(manifest.parent_artifact_ids):
                    await cursor.execute("SELECT a.id FROM artifacts a JOIN stage_attempts s ON s.id=a.producing_stage_attempt_id WHERE a.id=%s AND s.state='SUCCEEDED'", (parent_id,))
                    if not await cursor.fetchone():
                        raise TraceError(TraceErrorCode.ARTIFACT_LINEAGE_INVALID)
                    await cursor.execute("INSERT INTO artifact_lineage (artifact_id, ordinal, parent_artifact_id) VALUES (%s,%s,%s)", (artifact_id, parent_ordinal, parent_id))
                await self._metrics(cursor, "artifact_metrics", "artifact_id", artifact_id, manifest.metrics)
                await self._signals(cursor, "artifact_quality_signals", "artifact_id", artifact_id, manifest.quality_signals)
                await cursor.execute("INSERT INTO stage_attempt_outputs (stage_attempt_id, ordinal, artifact_id) VALUES (%s,%s,%s)", (attempt_id, ordinal, artifact_id))
            await cursor.execute("UPDATE stage_attempts SET state='SUCCEEDED', result='SUCCEEDED', summary=%s, ended_at=CURRENT_TIMESTAMP WHERE id=%s", (summary, attempt_id))
            await self._metrics(cursor, "stage_attempt_metrics", "stage_attempt_id", attempt_id, metrics)
            await self._signals(cursor, "stage_attempt_quality_signals", "stage_attempt_id", attempt_id, signals)
        await self.connection.commit()

    async def eligible_artifact_location(self, artifact_id: UUID) -> tuple[str, str] | None:
        locations = await self.eligible_artifact_locations(artifact_id)
        return locations[0] if locations else None

    async def eligible_artifact_locations(self, artifact_id: UUID) -> tuple[tuple[str, str], ...] | None:
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """WITH RECURSIVE lineage AS (
                    SELECT id, content_digest, storage_locator, producing_stage_attempt_id FROM artifacts WHERE id=%s
                    UNION
                    SELECT parent.id, parent.content_digest, parent.storage_locator, parent.producing_stage_attempt_id
                    FROM artifact_lineage l JOIN artifacts parent ON parent.id=l.parent_artifact_id
                    JOIN lineage child ON child.id=l.artifact_id
                ) SELECT l.content_digest, l.storage_locator,
                    (SELECT COUNT(*) FROM lineage) AS lineage_count FROM lineage l
                JOIN stage_attempts s ON s.id=l.producing_stage_attempt_id
                WHERE s.state='SUCCEEDED' AND s.result='SUCCEEDED'""",
                (artifact_id,),
            )
            rows = await cursor.fetchall()
        if not rows or len(rows) != rows[0]["lineage_count"]:
            return None
        return tuple((row["content_digest"], row["storage_locator"]) for row in rows)

    async def get_artifact_manifest(self, artifact_id: UUID) -> ArtifactManifest | None:
        async with self.connection.cursor() as cursor:
            await cursor.execute("""SELECT id, artifact_type, schema_revision, content_digest, byte_size,
                storage_locator, producing_run_id, producing_stage_attempt_id, producing_plugin_id,
                configuration_digest, summary FROM artifacts WHERE id=%s""", (artifact_id,))
            artifact = await cursor.fetchone()
            if not artifact:
                return None
            await cursor.execute("SELECT parent_artifact_id FROM artifact_lineage WHERE artifact_id=%s ORDER BY ordinal", (artifact_id,))
            parents = tuple(row["parent_artifact_id"] for row in await cursor.fetchall())
            await cursor.execute("SELECT name, value FROM artifact_metrics WHERE artifact_id=%s ORDER BY name", (artifact_id,))
            metrics = tuple(Metric(**row) for row in await cursor.fetchall())
            await cursor.execute("SELECT name,status,value,summary FROM artifact_quality_signals WHERE artifact_id=%s ORDER BY name", (artifact_id,))
            signals = tuple(QualitySignal(**row) for row in await cursor.fetchall())
        return ArtifactManifest(parent_artifact_ids=parents, metrics=metrics, quality_signals=signals, **artifact)

    async def list_artifact_manifests(self, artifact_type: str, schema_revision: str, limit: int = 100) -> tuple[ArtifactManifest, ...]:
        """Bounded catalog read for workbench selectors; storage locations stay private."""
        async with self.connection.cursor() as cursor:
            await cursor.execute("""SELECT id FROM artifacts WHERE artifact_type=%s AND schema_revision=%s
                                  ORDER BY id DESC LIMIT %s""", (artifact_type, schema_revision, limit))
            identifiers = [row["id"] for row in await cursor.fetchall()]
        return tuple(item for identifier in identifiers if (item := await self.get_artifact_manifest(identifier)) is not None)

    async def get_run_trace(self, run_id: UUID) -> RunTrace | None:
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """SELECT r.*, p.plan_digest FROM runs r
                JOIN execution_plan_snapshots p ON p.id=r.plan_snapshot_id WHERE r.id=%s""",
                (run_id,),
            )
            run = await cursor.fetchone()
            if not run:
                return None
            await cursor.execute("SELECT * FROM stage_attempts WHERE run_id=%s ORDER BY stage_key, attempt_number", (run_id,))
            attempts = await cursor.fetchall()
            await cursor.execute("SELECT name, value FROM run_metrics WHERE run_id=%s ORDER BY name", (run_id,))
            run_metrics = tuple(Metric(**item) for item in await cursor.fetchall())
            await cursor.execute("SELECT name, status, value, summary FROM run_quality_signals WHERE run_id=%s ORDER BY name", (run_id,))
            run_signals = tuple(QualitySignal(**item) for item in await cursor.fetchall())
            stages: list[StageTrace] = []
            for attempt in attempts:
                await cursor.execute(
                    """SELECT a.id, a.artifact_type, a.schema_revision, a.content_digest, a.byte_size, a.summary
                    FROM stage_attempt_inputs i JOIN artifacts a ON a.id=i.artifact_id
                    WHERE i.stage_attempt_id=%s ORDER BY i.ordinal""",
                    (attempt["id"],),
                )
                inputs = tuple(ArtifactReference(**item) for item in await cursor.fetchall())
                await cursor.execute(
                    """SELECT a.id, a.artifact_type, a.schema_revision, a.content_digest, a.byte_size, a.summary
                    FROM stage_attempt_outputs o JOIN artifacts a ON a.id=o.artifact_id
                    WHERE o.stage_attempt_id=%s ORDER BY o.ordinal""",
                    (attempt["id"],),
                )
                outputs = tuple(ArtifactReference(**item) for item in await cursor.fetchall())
                await cursor.execute("SELECT name, value FROM stage_attempt_metrics WHERE stage_attempt_id=%s ORDER BY name", (attempt["id"],))
                metrics = tuple(Metric(**item) for item in await cursor.fetchall())
                await cursor.execute("SELECT name, status, value, summary FROM stage_attempt_quality_signals WHERE stage_attempt_id=%s ORDER BY name", (attempt["id"],))
                signals = tuple(QualitySignal(**item) for item in await cursor.fetchall())
                stages.append(StageTrace(
                    id=attempt["id"], stage_key=attempt["stage_key"], attempt_number=attempt["attempt_number"],
                    state=attempt["state"], result=attempt["result"], started_at=attempt["started_at"], ended_at=attempt["ended_at"],
                    summary=attempt["summary"], safe_error=SafeError(**attempt["safe_error"]) if attempt["safe_error"] else None,
                    inputs=inputs, outputs=outputs, metrics=metrics, quality_signals=signals,
                ))
            await cursor.execute("SELECT resolution_json FROM ingestion_run_evidence WHERE run_id=%s", (run_id,))
            evidence = await cursor.fetchone()
        return RunTrace(
            id=run["id"], engine_kind=run["engine_kind"], plan_digest=run["plan_digest"], state=RunState(run["state"]),
            terminal_state=RunState(run["terminal_state"]) if run["terminal_state"] else None,
            created_at=run["created_at"], started_at=run["started_at"], ended_at=run["ended_at"], stages=tuple(stages),
            metrics=run_metrics, quality_signals=run_signals,
            ingestion_evidence=IngestionEvidence(**evidence["resolution_json"]) if evidence else None,
        )

    async def get_run_plan(self, run_id: UUID) -> dict[str, Any] | None:
        """Return the immutable plan snapshot only for server-side projections."""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                "SELECT p.plan_json FROM runs r JOIN execution_plan_snapshots p ON p.id=r.plan_snapshot_id WHERE r.id=%s",
                (run_id,),
            )
            row = await cursor.fetchone()
        return row["plan_json"] if row else None

    async def list_workbench_runs(self, limit: int = 8) -> tuple[dict[str, Any], ...]:
        """Bounded chronological lifecycle projection for the operator console."""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """SELECT r.id, r.engine_kind, r.state, r.terminal_state, r.created_at,
                    r.started_at, r.ended_at, p.plan_digest, failure.safe_error
                FROM runs r JOIN execution_plan_snapshots p ON p.id=r.plan_snapshot_id
                LEFT JOIN LATERAL (
                    SELECT safe_error FROM stage_attempts s
                    WHERE s.run_id=r.id AND s.state='FAILED' AND s.safe_error IS NOT NULL
                    ORDER BY s.ended_at DESC NULLS LAST, s.id DESC LIMIT 1
                ) failure ON TRUE
                ORDER BY r.created_at DESC, r.id DESC LIMIT %s""",
                (min(max(limit, 1), 8),),
            )
            return tuple(await cursor.fetchall())

    async def count_active_runs(self) -> int:
        async with self.connection.cursor() as cursor:
            await cursor.execute("SELECT COUNT(*) AS count FROM runs WHERE state IN ('PENDING', 'RUNNING')")
            return int((await cursor.fetchone())["count"])

    async def list_workbench_comparisons(self, limit: int = 4) -> tuple[dict[str, Any], ...]:
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """SELECT a.id, a.producing_run_id, a.created_at, a.content_digest, a.storage_locator
                FROM artifacts a JOIN runs r ON r.id=a.producing_run_id
                JOIN stage_attempts s ON s.id=a.producing_stage_attempt_id
                WHERE a.artifact_type='evaluation.comparison' AND a.schema_revision='v1'
                  AND r.state='SUCCEEDED' AND r.terminal_state='SUCCEEDED'
                  AND s.state='SUCCEEDED' AND s.result='SUCCEEDED'
                ORDER BY a.created_at DESC, a.id DESC LIMIT %s""",
                (min(max(limit, 1), 4),),
            )
            return tuple(await cursor.fetchall())

    async def list_evaluation_workbench_runs(self, limit: int = 50) -> tuple[dict[str, Any], ...]:
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                "SELECT r.id, r.state, r.terminal_state, r.created_at, r.started_at, r.ended_at, p.plan_digest "
                "FROM runs r JOIN execution_plan_snapshots p ON p.id=r.plan_snapshot_id "
                "WHERE r.engine_kind='evaluation' ORDER BY r.created_at DESC LIMIT %s",
                (max(1, min(limit, 100)),),
            )
            return tuple(await cursor.fetchall())

    async def list_workbench_run_history(self, limit: int = 50) -> tuple[dict[str, Any], ...]:
        """Bounded raw facts for the mixed history projection.

        The workbench classifies only these stored plan facts; it must not infer
        a run category from labels, errors, or artifact bodies.
        """
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                "SELECT r.id,r.engine_kind,r.state,r.terminal_state,r.created_at,r.started_at,r.ended_at,"
                "p.plan_digest,p.plan_json FROM runs r JOIN execution_plan_snapshots p ON p.id=r.plan_snapshot_id "
                "ORDER BY r.created_at DESC,r.id DESC LIMIT %s",
                (max(1, min(limit, 100)),),
            )
            return tuple(await cursor.fetchall())

    async def list_run_artifacts(self, run_id: UUID) -> tuple[ArtifactManifest, ...]:
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                "SELECT a.id, a.artifact_type, a.schema_revision, a.content_digest, a.byte_size, a.summary, "
                "a.storage_locator, a.producing_run_id, a.producing_stage_attempt_id, a.producing_plugin_id, "
                "a.configuration_digest, a.parent_artifact_ids "
                "FROM artifacts a WHERE a.producing_run_id=%s ORDER BY a.created_at",
                (run_id,),
            )
            return tuple(ArtifactManifest.model_validate(row) for row in await cursor.fetchall())

    async def list_plugin_workbench_runs(self, plugin_id: str, limit: int = 8) -> tuple[dict[str, Any], ...]:
        """Safe, bounded lifecycle facts only; no attempt error/configuration/artifact content."""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                "SELECT DISTINCT r.id,r.engine_kind,r.state,r.terminal_state,r.created_at "
                "FROM stage_attempts s JOIN runs r ON r.id=s.run_id "
                "WHERE s.plugin_id=%s ORDER BY r.created_at DESC,r.id DESC LIMIT %s",
                (plugin_id, min(max(limit, 1), 8)),
            )
            return tuple(await cursor.fetchall())

    async def list_profile_workspaces(self, kind: str | None = None, query: str = "") -> tuple[dict[str, Any], ...]:
        """Mutable local workbench values; deliberately no revision/history table."""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                "SELECT profile_id, profile_kind, updated_at FROM profile_workspaces "
                "WHERE (%s IS NULL OR profile_kind=%s) AND profile_id ILIKE %s "
                "ORDER BY profile_kind, profile_id LIMIT 64",
                (kind, kind, f"%{query}%"),
            )
            return tuple(await cursor.fetchall())

    async def get_profile_workspace(self, profile_id: str) -> dict[str, Any] | None:
        async with self.connection.cursor() as cursor:
            await cursor.execute("SELECT profile_id, profile_kind, source_document, updated_at FROM profile_workspaces WHERE profile_id=%s", (profile_id,))
            return await cursor.fetchone()

    async def save_profile_workspace(self, profile_id: str, kind: str, document: dict[str, Any]) -> dict[str, Any]:
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                "INSERT INTO profile_workspaces (profile_id, profile_kind, source_document) VALUES (%s,%s,%s) "
                "ON CONFLICT (profile_id) DO UPDATE SET profile_kind=EXCLUDED.profile_kind, source_document=EXCLUDED.source_document, updated_at=CURRENT_TIMESTAMP "
                "RETURNING profile_id, profile_kind, source_document, updated_at",
                (profile_id, kind, Jsonb(document)),
            )
            row = await cursor.fetchone()
        await self.connection.commit()
        assert row is not None
        return row

    async def _metrics(self, cursor: Any, table: str, owner: str, identifier: UUID, metrics: Sequence[Metric]) -> None:
        for metric in metrics:
            await cursor.execute(f"INSERT INTO {table} ({owner}, name, value) VALUES (%s, %s, %s)", (identifier, metric.name, metric.value))

    async def _signals(self, cursor: Any, table: str, owner: str, identifier: UUID, signals: Sequence[QualitySignal]) -> None:
        for signal in signals:
            signal = self._safe_signal(signal)
            await cursor.execute(f"INSERT INTO {table} ({owner}, name, status, value, summary) VALUES (%s, %s, %s, %s, %s)", (identifier, signal.name, signal.status, Jsonb(signal.value), signal.summary))

    @staticmethod
    def _safe_artifact(value: ArtifactInput) -> ArtifactInput:
        return ArtifactInput.model_validate(value.model_dump(mode="python"))

    @staticmethod
    def _safe_signal(value: QualitySignal) -> QualitySignal:
        return QualitySignal.model_validate(value.model_dump(mode="python"))

    @staticmethod
    def _safe_error(value: SafeError) -> SafeError:
        return SafeError.model_validate(value.model_dump(mode="python"))
