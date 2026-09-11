"""Create immutable artifact, run, and stage trace records."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_artifact_run_trace"
down_revision = "0001_runtime_heartbeat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    json = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "execution_plan_snapshots",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("plan_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("plan_json", json, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_table(
        "runs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("engine_kind", sa.String(16), nullable=False),
        sa.Column("plan_snapshot_id", uuid, sa.ForeignKey("execution_plan_snapshots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("terminal_state", sa.String(16)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("engine_kind IN ('ingestion', 'query', 'evaluation')", name="runs_engine_kind_check"),
        sa.CheckConstraint("state IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')", name="runs_state_check"),
    )
    op.create_index("ix_runs_plan_snapshot", "runs", ["plan_snapshot_id"])
    op.create_table(
        "stage_attempts",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("run_id", uuid, sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_key", sa.String(64), nullable=False),
        sa.Column("attempt_number", sa.Integer, nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("result", sa.String(16)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("summary", sa.String(1024), nullable=False, server_default=""),
        sa.Column("safe_error", json),
        sa.UniqueConstraint("run_id", "stage_key", "attempt_number", name="stage_attempt_number_unique"),
        sa.CheckConstraint("attempt_number >= 1", name="stage_attempt_number_check"),
        sa.CheckConstraint("state IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'SKIPPED')", name="stage_attempt_state_check"),
    )
    op.create_index("ix_stage_attempts_run_stage", "stage_attempts", ["run_id", "stage_key", "attempt_number"])
    op.create_table(
        "artifacts",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("artifact_type", sa.String(64), nullable=False),
        sa.Column("schema_revision", sa.String(64), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.BigInteger, nullable=False),
        sa.Column("storage_locator", sa.String(128), nullable=False),
        sa.Column("producing_run_id", uuid, sa.ForeignKey("runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("producing_stage_attempt_id", uuid, sa.ForeignKey("stage_attempts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("producing_plugin_id", sa.String(64), nullable=False),
        sa.Column("configuration_digest", sa.String(64), nullable=False),
        sa.Column("summary", sa.String(1024), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("producing_stage_attempt_id", "producing_plugin_id", "configuration_digest", "content_digest", name="artifact_production_unique"),
        sa.CheckConstraint("byte_size >= 0", name="artifact_byte_size_check"),
    )
    op.create_index("ix_artifacts_content_digest", "artifacts", ["content_digest"])
    op.create_table("artifact_lineage", sa.Column("artifact_id", uuid, sa.ForeignKey("artifacts.id", ondelete="CASCADE"), primary_key=True), sa.Column("ordinal", sa.Integer, primary_key=True), sa.Column("parent_artifact_id", uuid, sa.ForeignKey("artifacts.id", ondelete="RESTRICT"), nullable=False), sa.UniqueConstraint("artifact_id", "parent_artifact_id", name="artifact_parent_unique"), sa.CheckConstraint("artifact_id <> parent_artifact_id", name="artifact_not_own_parent"))
    op.create_table("stage_attempt_outputs", sa.Column("stage_attempt_id", uuid, sa.ForeignKey("stage_attempts.id", ondelete="CASCADE"), primary_key=True), sa.Column("ordinal", sa.Integer, primary_key=True), sa.Column("artifact_id", uuid, sa.ForeignKey("artifacts.id", ondelete="RESTRICT"), nullable=False), sa.UniqueConstraint("stage_attempt_id", "artifact_id", name="stage_output_unique"))
    for table, owner, fk in (("run_metrics", "run_id", "runs.id"), ("stage_attempt_metrics", "stage_attempt_id", "stage_attempts.id"), ("artifact_metrics", "artifact_id", "artifacts.id")):
        op.create_table(table, sa.Column(owner, uuid, sa.ForeignKey(fk, ondelete="CASCADE"), primary_key=True), sa.Column("name", sa.String(64), primary_key=True), sa.Column("value", sa.Float, nullable=False))
    for table, owner, fk in (("run_quality_signals", "run_id", "runs.id"), ("stage_attempt_quality_signals", "stage_attempt_id", "stage_attempts.id"), ("artifact_quality_signals", "artifact_id", "artifacts.id")):
        op.create_table(table, sa.Column(owner, uuid, sa.ForeignKey(fk, ondelete="CASCADE"), primary_key=True), sa.Column("name", sa.String(64), primary_key=True), sa.Column("status", sa.String(8), nullable=False), sa.Column("value", json), sa.Column("summary", sa.String(512), nullable=False, server_default=""), sa.CheckConstraint("status IN ('PASS', 'WARN', 'FAIL')", name=f"{table}_status_check"))


def downgrade() -> None:
    for table in ("artifact_quality_signals", "stage_attempt_quality_signals", "run_quality_signals", "artifact_metrics", "stage_attempt_metrics", "run_metrics", "stage_attempt_outputs", "artifact_lineage", "artifacts", "stage_attempts", "runs", "execution_plan_snapshots"):
        op.drop_table(table)
