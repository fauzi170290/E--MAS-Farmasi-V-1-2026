"""Sprint 5: antrean operasional dan alert per resep."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_sprint5"
down_revision = "0004_sprint4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processing_queue",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("screening_id", sa.String(length=36), nullable=True),
        sa.Column("prescription_id", sa.String(length=36), nullable=True),
        sa.Column("source_no_resep", sa.String(length=80), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=True),
        sa.Column("patient_id", sa.String(length=100), nullable=True),
        sa.Column("patient_name", sa.String(length=200), nullable=True),
        sa.Column("service_unit", sa.String(length=150), nullable=True),
        sa.Column(
            "processing_status",
            sa.String(length=30),
            server_default="QUEUED",
            nullable=False,
        ),
        sa.Column(
            "review_status",
            sa.String(length=30),
            server_default="NEW",
            nullable=False,
        ),
        sa.Column(
            "risk_status",
            sa.String(length=30),
            server_default="SAFE",
            nullable=False,
        ),
        sa.Column(
            "completeness_status",
            sa.String(length=30),
            server_default="ERROR",
            nullable=False,
        ),
        sa.Column(
            "overall_status",
            sa.String(length=30),
            server_default="ERROR",
            nullable=False,
        ),
        sa.Column(
            "alert_level",
            sa.String(length=30),
            server_default="ERROR",
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "hold_recommended",
            sa.Boolean(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "max_attempts", sa.Integer(), server_default="3", nullable=False
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "is_mock", sa.Boolean(), server_default="0", nullable=False
        ),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["prescription_id"], ["prescription.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["app_user.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["screening_id"], ["screening.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_processing_queue"),
        sa.UniqueConstraint(
            "screening_id", name="uq_processing_queue_screening_id"
        ),
    )
    op.create_index(
        "ix_processing_queue_operational",
        "processing_queue",
        ["processing_status", "priority", "detected_at"],
    )
    op.create_index(
        "ix_processing_queue_unit_review",
        "processing_queue",
        ["service_unit", "review_status"],
    )

    op.create_table(
        "alert_event",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("queue_item_id", sa.String(length=36), nullable=False),
        sa.Column("screening_id", sa.String(length=36), nullable=True),
        sa.Column("level", sa.String(length=30), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="NEW",
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "hold_recommended",
            sa.Boolean(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shown_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["acknowledged_by"], ["app_user.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["queue_item_id"], ["processing_queue.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["screening_id"], ["screening.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_alert_event"),
    )
    op.create_index(
        "ix_alert_event_status_created",
        "alert_event",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_alert_event_status_created", table_name="alert_event")
    op.drop_table("alert_event")
    op.drop_index(
        "ix_processing_queue_unit_review", table_name="processing_queue"
    )
    op.drop_index(
        "ix_processing_queue_operational", table_name="processing_queue"
    )
    op.drop_table("processing_queue")
