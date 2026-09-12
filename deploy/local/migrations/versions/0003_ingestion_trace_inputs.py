"""Persist ordered stage inputs and frozen ingestion resolver evidence."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0003_ingestion_trace_inputs"
down_revision = "0002_artifact_run_trace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "stage_attempt_inputs",
        sa.Column("stage_attempt_id", uuid, sa.ForeignKey("stage_attempts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("ordinal", sa.Integer, primary_key=True),
        sa.Column("artifact_id", uuid, sa.ForeignKey("artifacts.id", ondelete="RESTRICT"), nullable=False),
    )
    op.create_table(
        "ingestion_run_evidence",
        sa.Column("run_id", uuid, sa.ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("resolution_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ingestion_run_evidence")
    op.drop_table("stage_attempt_inputs")
