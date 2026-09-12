"""Add append-only Golden Dataset catalog and review provenance."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_golden_dataset_catalog"
down_revision = "0003_ingestion_trace_inputs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid, json = postgresql.UUID(as_uuid=True), postgresql.JSONB(astext_type=sa.Text())
    op.create_table("golden_datasets", sa.Column("id", uuid, primary_key=True), sa.Column("taxonomy_json", json, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
    op.create_table("golden_dataset_revisions", sa.Column("id", uuid, primary_key=True), sa.Column("dataset_id", uuid, sa.ForeignKey("golden_datasets.id", ondelete="RESTRICT"), nullable=False), sa.Column("revision", sa.Integer, nullable=False), sa.Column("parent_revision_id", uuid, sa.ForeignKey("golden_dataset_revisions.id", ondelete="RESTRICT")), sa.Column("content_json", json, nullable=False), sa.Column("content_digest", sa.String(64), nullable=False), sa.Column("operation", sa.String(16), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")), sa.UniqueConstraint("dataset_id", "revision", name="golden_dataset_revision_unique"), sa.CheckConstraint("operation IN ('create', 'edit', 'import')", name="golden_dataset_revision_operation_check"))
    op.create_table("golden_dataset_reviews", sa.Column("id", uuid, primary_key=True), sa.Column("dataset_revision_id", uuid, sa.ForeignKey("golden_dataset_revisions.id", ondelete="RESTRICT"), nullable=False), sa.Column("case_id", sa.String(72), nullable=False), sa.Column("operation", sa.String(32), nullable=False), sa.Column("reviewer", sa.String(64), nullable=False), sa.Column("reviewed_content_digest", sa.String(64), nullable=False), sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False), sa.CheckConstraint("operation = 'mark_reviewed'", name="golden_dataset_review_operation_check"))


def downgrade() -> None:
    op.drop_table("golden_dataset_reviews")
    op.drop_table("golden_dataset_revisions")
    op.drop_table("golden_datasets")
