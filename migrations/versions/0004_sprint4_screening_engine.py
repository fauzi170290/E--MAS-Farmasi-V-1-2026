"""Sprint 4: prescription revision dan hasil DDI engine."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_sprint4"
down_revision = "0003_sprint3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prescription",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_no_resep", sa.String(length=80), nullable=False),
        sa.Column("patient_id", sa.String(length=100), nullable=True),
        sa.Column("patient_name", sa.String(length=200), nullable=True),
        sa.Column("service_unit", sa.String(length=150), nullable=True),
        sa.Column("prescriber_name", sa.String(length=200), nullable=True),
        sa.Column("is_mock", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_prescription"),
        sa.UniqueConstraint(
            "source_no_resep", name="uq_prescription_source_no_resep"
        ),
    )
    op.create_index(
        "ix_prescription_source_updated",
        "prescription",
        ["source_no_resep", "updated_at"],
    )

    op.create_table(
        "prescription_revision",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("prescription_id", sa.String(length=36), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("prescription_hash", sa.String(length=64), nullable=False),
        sa.Column("knowledge_base_version_id", sa.String(length=36), nullable=False),
        sa.Column("is_mock", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["knowledge_base_version_id"],
            ["knowledge_base_version.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prescription_id"], ["prescription.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_prescription_revision"),
        sa.UniqueConstraint(
            "prescription_id",
            "prescription_hash",
            "knowledge_base_version_id",
            "is_mock",
            name="uq_prescription_revision_identity",
        ),
        sa.UniqueConstraint(
            "prescription_id",
            "revision_number",
            name="uq_prescription_revision_number",
        ),
    )
    op.create_index(
        "ix_prescription_revision_hash_version",
        "prescription_revision",
        ["prescription_hash", "knowledge_base_version_id"],
    )

    op.create_table(
        "prescription_item",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("source_item_key", sa.String(length=100), nullable=False),
        sa.Column("khanza_code", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=250), nullable=False),
        sa.Column("quantity", sa.String(length=80), nullable=True),
        sa.Column("directions", sa.Text(), nullable=True),
        sa.Column("route", sa.String(length=100), nullable=True),
        sa.Column("compound_group", sa.String(length=100), nullable=True),
        sa.Column("mapping_status", sa.String(length=30), nullable=False),
        sa.Column("active_ingredients_json", sa.Text(), server_default="[]", nullable=False),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["prescription_revision.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_prescription_item"),
        sa.UniqueConstraint(
            "revision_id",
            "source_item_key",
            name="uq_prescription_item_source",
        ),
    )
    op.create_index(
        "ix_prescription_item_khanza_code",
        "prescription_item",
        ["khanza_code"],
    )

    op.create_table(
        "screening",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("knowledge_base_version_id", sa.String(length=36), nullable=False),
        sa.Column("risk_status", sa.String(length=30), nullable=False),
        sa.Column("completeness_status", sa.String(length=30), nullable=False),
        sa.Column("overall_status", sa.String(length=30), nullable=False),
        sa.Column("highest_severity_rank", sa.Integer(), server_default="0", nullable=False),
        sa.Column("ingredient_count", sa.Integer(), nullable=False),
        sa.Column("pair_count", sa.Integer(), nullable=False),
        sa.Column("interaction_count", sa.Integer(), nullable=False),
        sa.Column("assessed_no_interaction_count", sa.Integer(), nullable=False),
        sa.Column("not_assessed_count", sa.Integer(), nullable=False),
        sa.Column("unmapped_drug_count", sa.Integer(), nullable=False),
        sa.Column("is_mock", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("engine_version", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_base_version_id"],
            ["knowledge_base_version.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["prescription_revision.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_screening"),
        sa.UniqueConstraint("revision_id", name="uq_screening_revision_id"),
    )
    op.create_index(
        "ix_screening_status_completed",
        "screening",
        ["overall_status", "completed_at"],
    )

    op.create_table(
        "screening_pair",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("screening_id", sa.String(length=36), nullable=False),
        sa.Column("pair_key", sa.String(length=450), nullable=False),
        sa.Column("ingredient_low", sa.String(length=200), nullable=False),
        sa.Column("ingredient_high", sa.String(length=200), nullable=False),
        sa.Column("khanza_codes_json", sa.Text(), nullable=False),
        sa.Column("classification", sa.String(length=40), nullable=False),
        sa.Column("ddi_rule_id", sa.String(length=36), nullable=True),
        sa.Column("severity_code", sa.String(length=30), nullable=True),
        sa.Column("severity_rank", sa.Integer(), server_default="0", nullable=False),
        sa.Column("app_severity", sa.String(length=30), nullable=True),
        sa.Column("clinical_effect", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("monitoring", sa.Text(), nullable=True),
        sa.Column("source_validation_status", sa.String(length=80), nullable=True),
        sa.ForeignKeyConstraint(
            ["ddi_rule_id"], ["ddi_rule.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["screening_id"], ["screening.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_screening_pair"),
        sa.UniqueConstraint(
            "screening_id", "pair_key", name="uq_screening_pair_key"
        ),
    )
    op.create_index(
        "ix_screening_pair_classification",
        "screening_pair",
        ["classification"],
    )

    op.create_table(
        "screening_issue",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("screening_id", sa.String(length=36), nullable=False),
        sa.Column("issue_type", sa.String(length=40), nullable=False),
        sa.Column("khanza_code", sa.String(length=50), nullable=True),
        sa.Column("display_name", sa.String(length=250), nullable=True),
        sa.Column("pair_key", sa.String(length=450), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["screening_id"], ["screening.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_screening_issue"),
    )
    op.create_index(
        "ix_screening_issue_type", "screening_issue", ["issue_type"]
    )


def downgrade() -> None:
    op.drop_index("ix_screening_issue_type", table_name="screening_issue")
    op.drop_table("screening_issue")
    op.drop_index(
        "ix_screening_pair_classification", table_name="screening_pair"
    )
    op.drop_table("screening_pair")
    op.drop_index("ix_screening_status_completed", table_name="screening")
    op.drop_table("screening")
    op.drop_index(
        "ix_prescription_item_khanza_code", table_name="prescription_item"
    )
    op.drop_table("prescription_item")
    op.drop_index(
        "ix_prescription_revision_hash_version",
        table_name="prescription_revision",
    )
    op.drop_table("prescription_revision")
    op.drop_index(
        "ix_prescription_source_updated", table_name="prescription"
    )
    op.drop_table("prescription")

