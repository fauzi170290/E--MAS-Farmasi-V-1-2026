"""Sprint 8: duplicate therapy, polypharmacy, high-alert, and LASA."""

from alembic import op
import sqlalchemy as sa

revision = "0008_sprint8"
down_revision = "0007_sprint7"
branch_labels = None
depends_on = None


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("validated_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "medication_safety_policy",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("polypharmacy_threshold", sa.Integer(), server_default="5", nullable=False),
        sa.Column("hyperpolypharmacy_threshold", sa.Integer(), server_default="10", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("validated_by", sa.String(36), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["validated_by"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_medication_safety_policy"),
    )
    op.execute(sa.text("INSERT INTO medication_safety_policy (id, polypharmacy_threshold, hyperpolypharmacy_threshold, is_active, updated_at) VALUES (1, 5, 10, 1, CURRENT_TIMESTAMP)"))

    op.create_table(
        "ingredient_therapy_profile",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("ingredient_id", sa.String(36), nullable=False),
        sa.Column("therapeutic_class", sa.String(160), nullable=False),
        sa.Column("therapeutic_subclass", sa.String(160), nullable=True),
        sa.Column("atc_code", sa.String(30), nullable=True),
        sa.Column("route_context", sa.String(100), nullable=True),
        sa.Column("dosage_form", sa.String(100), nullable=True),
        sa.Column("source", sa.String(250), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        *_audit_columns(),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["ingredient_id"], ["active_ingredient.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["validated_by"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_ingredient_therapy_profile"),
        sa.UniqueConstraint("ingredient_id", name="uq_ingredient_therapy_profile_ingredient_id"),
    )
    op.create_index("ix_therapy_profile_class", "ingredient_therapy_profile", ["therapeutic_class", "is_active"])

    op.create_table(
        "high_alert_medication",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("drug_id", sa.String(36), nullable=False),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("unit_scope", sa.String(150), server_default="*", nullable=False),
        sa.Column("app_severity", sa.String(30), server_default="REVIEW", nullable=False),
        sa.Column("requires_double_check", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("source", sa.String(250), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("validated_by", sa.String(36), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["drug_id"], ["drug_master.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["validated_by"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_high_alert_medication"),
        sa.UniqueConstraint("drug_id", "unit_scope", name="uq_high_alert_drug_unit"),
    )
    op.create_index("ix_high_alert_active_unit", "high_alert_medication", ["is_active", "unit_scope"])

    op.create_table(
        "lasa_pair",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("drug_low_id", sa.String(36), nullable=False),
        sa.Column("drug_high_id", sa.String(36), nullable=False),
        sa.Column("lasa_type", sa.String(40), nullable=False),
        sa.Column("unit_scope", sa.String(150), server_default="*", nullable=False),
        sa.Column("app_severity", sa.String(30), server_default="REVIEW", nullable=False),
        sa.Column("requires_double_check", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("source", sa.String(250), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("validated_by", sa.String(36), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["drug_low_id"], ["drug_master.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["drug_high_id"], ["drug_master.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["validated_by"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_lasa_pair"),
        sa.UniqueConstraint("drug_low_id", "drug_high_id", "lasa_type", "unit_scope", name="uq_lasa_pair_type_unit"),
    )
    op.create_index("ix_lasa_active_unit", "lasa_pair", ["is_active", "unit_scope"])
    with op.batch_alter_table("screening_issue") as batch:
        batch.add_column(sa.Column("app_severity", sa.String(30), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("screening_issue") as batch:
        batch.drop_column("app_severity")
    op.drop_index("ix_lasa_active_unit", table_name="lasa_pair")
    op.drop_table("lasa_pair")
    op.drop_index("ix_high_alert_active_unit", table_name="high_alert_medication")
    op.drop_table("high_alert_medication")
    op.drop_index("ix_therapy_profile_class", table_name="ingredient_therapy_profile")
    op.drop_table("ingredient_therapy_profile")
    op.drop_table("medication_safety_policy")
