"""Sprint 3: master DDI dan workflow knowledge base."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_sprint3"
down_revision = "0002_sprint2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_base_version",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("version_code", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="DRAFT", nullable=False),
        sa.Column("based_on_version_id", sa.String(length=36), nullable=True),
        sa.Column("source_checksum", sa.String(length=64), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(length=36), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.String(length=36), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_by", sa.String(length=36), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["approved_by"], ["app_user.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["based_on_version_id"],
            ["knowledge_base_version.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["app_user.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["published_by"], ["app_user.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["retired_by"], ["app_user.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["app_user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_base_version"),
        sa.UniqueConstraint(
            "version_code", name="uq_knowledge_base_version_version_code"
        ),
    )
    op.create_index(
        "ix_knowledge_base_status_created",
        "knowledge_base_version",
        ["status", "created_at"],
    )

    op.create_table(
        "knowledge_base_transition",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("knowledge_base_version_id", sa.String(length=36), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["app_user.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_version_id"],
            ["knowledge_base_version.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_base_transition"),
    )
    op.create_index(
        "ix_kb_transition_version_time",
        "knowledge_base_transition",
        ["knowledge_base_version_id", "occurred_at"],
    )

    op.create_table(
        "ddi_rule",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("knowledge_base_version_id", sa.String(length=36), nullable=False),
        sa.Column("external_pair_id", sa.String(length=80), nullable=True),
        sa.Column("ingredient_low_id", sa.String(length=36), nullable=False),
        sa.Column("ingredient_high_id", sa.String(length=36), nullable=False),
        sa.Column("pair_key", sa.String(length=450), nullable=False),
        sa.Column("interaction_status", sa.String(length=40), nullable=False),
        sa.Column("severity_code", sa.String(length=30), nullable=False),
        sa.Column("severity_label", sa.String(length=100), nullable=True),
        sa.Column("severity_rank", sa.Integer(), server_default="0", nullable=False),
        sa.Column("app_severity", sa.String(length=30), nullable=True),
        sa.Column("clinical_effect", sa.Text(), nullable=True),
        sa.Column("mechanism", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("monitoring", sa.Text(), nullable=True),
        sa.Column("population_risk", sa.Text(), nullable=True),
        sa.Column("source_name", sa.String(length=250), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column("source_accessed_at", sa.Date(), nullable=True),
        sa.Column("source_batch", sa.Text(), nullable=True),
        sa.Column("source_evidence_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source_validation_status", sa.String(length=80), nullable=True),
        sa.Column("source_final_code", sa.String(length=100), nullable=True),
        sa.Column("activation_status", sa.String(length=60), server_default="DRAFT", nullable=False),
        sa.Column("clinical_review_required", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("clinical_review_resolved", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("record_status", sa.String(length=20), server_default="DRAFT", nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("validated_by_name", sa.String(length=150), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["app_user.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_high_id"], ["active_ingredient.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_low_id"], ["active_ingredient.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_version_id"],
            ["knowledge_base_version.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["app_user.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ddi_rule"),
        sa.UniqueConstraint(
            "knowledge_base_version_id",
            "ingredient_low_id",
            "ingredient_high_id",
            name="uq_ddi_rule_version_canonical_pair",
        ),
    )
    op.create_index("ix_ddi_rule_pair_key", "ddi_rule", ["pair_key"])
    op.create_index(
        "ix_ddi_rule_version_status",
        "ddi_rule",
        ["knowledge_base_version_id", "record_status"],
    )
    op.create_index(
        "ix_ddi_rule_clinical_hold",
        "ddi_rule",
        ["clinical_review_required", "clinical_review_resolved"],
    )


def downgrade() -> None:
    op.drop_index("ix_ddi_rule_clinical_hold", table_name="ddi_rule")
    op.drop_index("ix_ddi_rule_version_status", table_name="ddi_rule")
    op.drop_index("ix_ddi_rule_pair_key", table_name="ddi_rule")
    op.drop_table("ddi_rule")
    op.drop_index(
        "ix_kb_transition_version_time", table_name="knowledge_base_transition"
    )
    op.drop_table("knowledge_base_transition")
    op.drop_index(
        "ix_knowledge_base_status_created", table_name="knowledge_base_version"
    )
    op.drop_table("knowledge_base_version")
