"""Add explicit, evidence-bound Advisory Pilot activation."""

from alembic import op
import sqlalchemy as sa


revision = "0013_advisory_activation"
down_revision = "0012_uat_campaign"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "advisory_pilot_activation",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column("application_version", sa.String(length=30), nullable=False),
        sa.Column("validation_campaign_id", sa.String(length=36), nullable=False),
        sa.Column("uat_session_id", sa.String(length=36), nullable=False),
        sa.Column(
            "pharmacist_approved_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("it_approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_by", sa.String(length=36), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_by", sa.String(length=36), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(length=160), nullable=True),
        sa.ForeignKeyConstraint(
            ["validation_campaign_id"],
            ["validation_campaign.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uat_session_id"], ["uat_session.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["activated_by"], ["app_user.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by"], ["app_user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_advisory_pilot_activation_status",
        "advisory_pilot_activation",
        ["status", "activated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_advisory_pilot_activation_status",
        table_name="advisory_pilot_activation",
    )
    op.drop_table("advisory_pilot_activation")
