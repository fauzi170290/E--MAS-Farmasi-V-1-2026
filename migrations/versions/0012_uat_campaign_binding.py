"""Bind UAT approvals to a specific validation campaign."""

from alembic import op
import sqlalchemy as sa


revision = "0012_uat_campaign"
down_revision = "0011_validation_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("uat_session") as batch:
        batch.add_column(
            sa.Column(
                "pharmacist_approved_campaign_id",
                sa.String(length=36),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "it_approved_campaign_id",
                sa.String(length=36),
                nullable=True,
            )
        )
        batch.create_foreign_key(
            "fk_uat_pharmacist_approved_campaign",
            "validation_campaign",
            ["pharmacist_approved_campaign_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_uat_it_approved_campaign",
            "validation_campaign",
            ["it_approved_campaign_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("uat_session") as batch:
        batch.drop_constraint(
            "fk_uat_it_approved_campaign", type_="foreignkey"
        )
        batch.drop_constraint(
            "fk_uat_pharmacist_approved_campaign", type_="foreignkey"
        )
        batch.drop_column("it_approved_campaign_id")
        batch.drop_column("pharmacist_approved_campaign_id")
