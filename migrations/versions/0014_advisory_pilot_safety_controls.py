"""Add time-bounded activation and emergency-stop control."""

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "0014_advisory_safety"
down_revision = "0013_advisory_activation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("advisory_pilot_activation") as batch:
        batch.add_column(
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
        )
    op.create_table(
        "advisory_pilot_safety_control",
        sa.Column("id", sa.String(length=20), nullable=False),
        sa.Column(
            "emergency_stop",
            sa.Boolean(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("stop_reason", sa.String(length=300), nullable=True),
        sa.Column("stopped_by", sa.String(length=36), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restored_by", sa.String(length=36), nullable=True),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["stopped_by"], ["app_user.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["restored_by"], ["app_user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    control = sa.table(
        "advisory_pilot_safety_control",
        sa.column("id", sa.String),
        sa.column("emergency_stop", sa.Boolean),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        control,
        [
            {
                "id": "GLOBAL",
                "emergency_stop": False,
                "updated_at": datetime.now(UTC),
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("advisory_pilot_safety_control")
    with op.batch_alter_table("advisory_pilot_activation") as batch:
        batch.drop_column("expires_at")
