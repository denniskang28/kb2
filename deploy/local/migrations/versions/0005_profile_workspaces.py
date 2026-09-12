"""Add mutable local workbench Profile workspace storage."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_profile_workspaces"
down_revision = "0004_golden_dataset_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profile_workspaces",
        sa.Column("profile_id", sa.String(48), primary_key=True),
        sa.Column("profile_kind", sa.String(16), nullable=False),
        sa.Column("source_document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("profile_kind IN ('ingestion', 'query')", name="profile_workspace_kind_check"),
    )


def downgrade() -> None:
    op.drop_table("profile_workspaces")
