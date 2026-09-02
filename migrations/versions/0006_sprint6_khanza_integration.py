"""Sprint 6: status koneksi dan histori polling Khanza."""

from alembic import op
import sqlalchemy as sa

revision = "0006_sprint6"
down_revision = "0005_sprint5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_state",
        sa.Column("adapter_code", sa.String(30), nullable=False),
        sa.Column("connection_status", sa.String(30), nullable=False),
        sa.Column("cursor_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cursor_no_resep", sa.String(80), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(80), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("adapter_code", name="pk_integration_state"),
    )
    op.create_table(
        "polling_run",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("adapter_code", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("detected_count", sa.Integer(), nullable=False),
        sa.Column("stable_count", sa.Integer(), nullable=False),
        sa.Column("processed_count", sa.Integer(), nullable=False),
        sa.Column("incomplete_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("cursor_before", sa.String(160), nullable=True),
        sa.Column("cursor_after", sa.String(160), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_polling_run"),
    )
    op.create_index(
        "ix_polling_run_started_status", "polling_run", ["started_at", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_polling_run_started_status", table_name="polling_run")
    op.drop_table("polling_run")
    op.drop_table("integration_state")
