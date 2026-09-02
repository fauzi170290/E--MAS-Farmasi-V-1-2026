"""Add fail-safe quarantine for pilot ledger integrity failures."""

from alembic import op
import sqlalchemy as sa


revision = "0017_pilot_ledger_quarantine"
down_revision = "0016_shift_closeout_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("advisory_pilot_safety_control") as batch:
        batch.add_column(
            sa.Column(
                "ledger_quarantine",
                sa.Boolean(),
                server_default="0",
                nullable=False,
            )
        )
        batch.add_column(
            sa.Column("ledger_quarantine_reason", sa.String(300), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "ledger_quarantined_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column("ledger_detected_head_hash", sa.String(64), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "ledger_quarantine_cleared_by", sa.String(36), nullable=True
            )
        )
        batch.add_column(
            sa.Column(
                "ledger_quarantine_cleared_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch.create_foreign_key(
            "fk_pilot_safety_ledger_quarantine_cleared_by",
            "app_user",
            ["ledger_quarantine_cleared_by"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("advisory_pilot_safety_control") as batch:
        batch.drop_constraint(
            "fk_pilot_safety_ledger_quarantine_cleared_by",
            type_="foreignkey",
        )
        batch.drop_column("ledger_quarantine_cleared_at")
        batch.drop_column("ledger_quarantine_cleared_by")
        batch.drop_column("ledger_detected_head_hash")
        batch.drop_column("ledger_quarantined_at")
        batch.drop_column("ledger_quarantine_reason")
        batch.drop_column("ledger_quarantine")
