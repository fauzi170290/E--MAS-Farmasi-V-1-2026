"""Sprint 10: clinical validation, UAT, and pilot gates."""

from alembic import op
import sqlalchemy as sa

revision = "0009_sprint10"
down_revision = "0008_sprint8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "validation_campaign",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("phase", sa.String(30), server_default="CLINICAL_VALIDATION", nullable=False),
        sa.Column("status", sa.String(30), server_default="IN_PROGRESS", nullable=False),
        sa.Column("source_filename", sa.String(260), nullable=True),
        sa.Column("source_checksum", sa.String(64), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_validation_campaign"),
    )
    op.create_index("ix_validation_campaign_status", "validation_campaign", ["status", "created_at"])
    op.create_table(
        "clinical_validation_case",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("case_code", sa.String(80), nullable=False),
        sa.Column("drug_list", sa.Text(), nullable=False),
        sa.Column("clinical_context", sa.Text(), nullable=True),
        sa.Column("expected_pairs", sa.Text(), nullable=True),
        sa.Column("expected_highest_severity", sa.String(30), nullable=False),
        sa.Column("expected_duplicate_therapy", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("expected_polypharmacy", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("expected_high_alert", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("expected_lasa", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("expected_unmapped", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("expected_alert", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("checks_compound", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("checks_revision", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("actual_result", sa.Text(), nullable=True),
        sa.Column("actual_highest_severity", sa.String(30), nullable=True),
        sa.Column("actual_overall_status", sa.String(30), nullable=True),
        sa.Column("actual_duplicate_therapy", sa.Boolean(), nullable=True),
        sa.Column("actual_polypharmacy", sa.Boolean(), nullable=True),
        sa.Column("actual_high_alert", sa.Boolean(), nullable=True),
        sa.Column("actual_lasa", sa.Boolean(), nullable=True),
        sa.Column("actual_unmapped", sa.Boolean(), nullable=True),
        sa.Column("actual_alert", sa.Boolean(), nullable=True),
        sa.Column("duplicate_output_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("compound_pass", sa.Boolean(), nullable=True),
        sa.Column("revision_pass", sa.Boolean(), nullable=True),
        sa.Column("match", sa.Boolean(), nullable=True),
        sa.Column("review_status", sa.String(30), server_default="NOT_REVIEWED", nullable=False),
        sa.Column("reviewer", sa.String(120), nullable=True),
        sa.Column("review_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["validation_campaign.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_clinical_validation_case"),
        sa.UniqueConstraint("campaign_id", "case_code", name="uq_validation_case_campaign_code"),
    )
    op.create_index("ix_validation_case_gate", "clinical_validation_case", ["campaign_id", "review_status", "match"])
    op.create_table(
        "uat_session",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(30), server_default="IN_PROGRESS", nullable=False),
        sa.Column("pharmacist_approved", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("pharmacist_approved_by", sa.String(36), nullable=True),
        sa.Column("pharmacist_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("it_approved", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("it_approved_by", sa.String(36), nullable=True),
        sa.Column("it_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pharmacist_approved_by"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["it_approved_by"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_uat_session"),
    )
    op.create_index("ix_uat_session_status", "uat_session", ["status", "created_at"])
    op.create_table(
        "uat_checklist_item",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("item_code", sa.String(40), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("expected_result", sa.Text(), nullable=False),
        sa.Column("owner_role", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), server_default="NOT_TESTED", nullable=False),
        sa.Column("actual_result", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("tester", sa.String(120), nullable=True),
        sa.Column("tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["uat_session.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_uat_checklist_item"),
        sa.UniqueConstraint("session_id", "item_code", name="uq_uat_item_session_code"),
    )
    op.create_index("ix_uat_item_status", "uat_checklist_item", ["session_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_uat_item_status", table_name="uat_checklist_item")
    op.drop_table("uat_checklist_item")
    op.drop_index("ix_uat_session_status", table_name="uat_session")
    op.drop_table("uat_session")
    op.drop_index("ix_validation_case_gate", table_name="clinical_validation_case")
    op.drop_table("clinical_validation_case")
    op.drop_index("ix_validation_campaign_status", table_name="validation_campaign")
    op.drop_table("validation_campaign")
