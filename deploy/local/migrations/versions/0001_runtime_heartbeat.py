"""Create the local runtime heartbeat substrate."""

from alembic import op
import sqlalchemy as sa


revision = "0001_runtime_heartbeat"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "runtime_worker_heartbeat",
        sa.Column("worker_id", sa.String(length=64), primary_key=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("runtime_worker_heartbeat")
