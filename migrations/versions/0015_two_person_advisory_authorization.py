"""Add two-person Advisory authorization and shift handover."""

from alembic import op
import sqlalchemy as sa


revision = "0015_two_person_advisory"
down_revision = "0014_advisory_safety"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("advisory_pilot_activation") as batch:
        batch.add_column(sa.Column("clinical_owner_id", sa.String(36), nullable=True))
        batch.add_column(
            sa.Column("technical_authorizer_id", sa.String(36), nullable=True)
        )
        batch.add_column(
            sa.Column("authorization_request_id", sa.String(36), nullable=True)
        )
        batch.create_foreign_key(
            "fk_advisory_activation_clinical_owner",
            "app_user",
            ["clinical_owner_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_advisory_activation_technical_authorizer",
            "app_user",
            ["technical_authorizer_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_table(
        "advisory_pilot_authorization_request",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("application_version", sa.String(30), nullable=False),
        sa.Column("validation_campaign_id", sa.String(36), nullable=False),
        sa.Column("uat_session_id", sa.String(36), nullable=False),
        sa.Column("pharmacist_approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("it_approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_hours", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.String(36), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("technical_approved_by", sa.String(36), nullable=True),
        sa.Column("technical_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinical_approved_by", sa.String(36), nullable=True),
        sa.Column("clinical_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handover_from_activation_id", sa.String(36), nullable=True),
        sa.Column("resulting_activation_id", sa.String(36), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.String(160), nullable=True),
        sa.ForeignKeyConstraint(["validation_campaign_id"], ["validation_campaign.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["uat_session_id"], ["uat_session.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["technical_approved_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["clinical_approved_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["handover_from_activation_id"], ["advisory_pilot_activation.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resulting_activation_id"], ["advisory_pilot_activation.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_advisory_authorization_request_status",
        "advisory_pilot_authorization_request",
        ["status", "requested_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_advisory_authorization_request_status",
        table_name="advisory_pilot_authorization_request",
    )
    op.drop_table("advisory_pilot_authorization_request")
    with op.batch_alter_table("advisory_pilot_activation") as batch:
        batch.drop_constraint(
            "fk_advisory_activation_technical_authorizer", type_="foreignkey"
        )
        batch.drop_constraint(
            "fk_advisory_activation_clinical_owner", type_="foreignkey"
        )
        batch.drop_column("authorization_request_id")
        batch.drop_column("technical_authorizer_id")
        batch.drop_column("clinical_owner_id")
