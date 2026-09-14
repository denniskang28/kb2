"""Add the durable catalog of confirmed document submissions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006_document_submissions"
down_revision = "0005_profile_workspaces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "document_submissions",
        sa.Column("source_artifact_id", uuid, sa.ForeignKey("artifacts.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("run_id", uuid, sa.ForeignKey("runs.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("display_filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(128), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "ix_document_submissions_keyset",
        "document_submissions",
        [sa.text("registered_at DESC"), sa.text("source_artifact_id DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_document_submissions_keyset", table_name="document_submissions")
    op.drop_table("document_submissions")
