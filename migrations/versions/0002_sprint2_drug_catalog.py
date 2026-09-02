"""Sprint 2: master obat, alias, komponen, dan staging impor."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_sprint2"
down_revision = "0001_sprint1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "active_ingredient",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("standard_name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_active_ingredient"),
        sa.UniqueConstraint(
            "normalized_name", name="uq_active_ingredient_normalized_name"
        ),
    )

    op.create_table(
        "import_batch",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("import_type", sa.String(length=40), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_version", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("requested_by", sa.String(length=36), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("valid_rows", sa.Integer(), nullable=False),
        sa.Column("invalid_rows", sa.Integer(), nullable=False),
        sa.Column("inserted_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "unchanged_rows", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("summary_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["app_user.id"],
            name="fk_import_batch_requested_by_app_user",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_import_batch"),
    )
    op.create_index(
        "ix_import_batch_status_created",
        "import_batch",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_import_batch_checksum", "import_batch", ["source_sha256"]
    )

    op.create_table(
        "drug_master",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("khanza_code", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("source_version", sa.String(length=80), nullable=False),
        sa.Column("source_mapping_status", sa.String(length=30), nullable=False),
        sa.Column(
            "review_status",
            sa.String(length=30),
            server_default="PENDING_REVIEW",
            nullable=False,
        ),
        sa.Column("mapping_method", sa.String(length=100), nullable=False),
        sa.Column("mapping_note", sa.Text(), nullable=True),
        sa.Column("component_count", sa.Integer(), nullable=False),
        sa.Column("rx_row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("episode_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("name_variants_raw", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("last_import_batch_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["last_import_batch_id"],
            ["import_batch.id"],
            name="fk_drug_master_last_import_batch_id_import_batch",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_drug_master"),
        sa.UniqueConstraint("khanza_code", name="uq_drug_master_khanza_code"),
    )
    op.create_index(
        "ix_drug_master_normalized_name", "drug_master", ["normalized_name"]
    )
    op.create_index(
        "ix_drug_master_mapping_review",
        "drug_master",
        ["source_mapping_status", "review_status"],
    )

    op.create_table(
        "drug_alias",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("drug_id", sa.String(length=36), nullable=False),
        sa.Column("alias_name", sa.String(length=200), nullable=False),
        sa.Column("normalized_alias", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("is_preferred", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["drug_id"],
            ["drug_master.id"],
            name="fk_drug_alias_drug_id_drug_master",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_drug_alias"),
        sa.UniqueConstraint(
            "drug_id",
            "normalized_alias",
            name="uq_drug_alias_drug_normalized",
        ),
    )
    op.create_index(
        "ix_drug_alias_normalized", "drug_alias", ["normalized_alias"]
    )

    op.create_table(
        "drug_component_mapping",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("drug_id", sa.String(length=36), nullable=False),
        sa.Column("ingredient_id", sa.String(length=36), nullable=False),
        sa.Column("component_order", sa.Integer(), nullable=False),
        sa.Column("source_mapping_status", sa.String(length=30), nullable=False),
        sa.Column("mapping_method", sa.String(length=100), nullable=False),
        sa.Column(
            "review_status",
            sa.String(length=30),
            server_default="PENDING_REVIEW",
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("source_version", sa.String(length=80), nullable=False),
        sa.Column("last_import_batch_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["drug_id"],
            ["drug_master.id"],
            name="fk_drug_component_mapping_drug_id_drug_master",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["active_ingredient.id"],
            name="fk_drug_component_mapping_ingredient_id_active_ingredient",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["last_import_batch_id"],
            ["import_batch.id"],
            name="fk_drug_component_mapping_last_import_batch_id_import_batch",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["app_user.id"],
            name="fk_drug_component_mapping_reviewed_by_app_user",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_drug_component_mapping"),
        sa.UniqueConstraint(
            "drug_id",
            "component_order",
            name="uq_drug_component_mapping_order",
        ),
        sa.UniqueConstraint(
            "drug_id",
            "ingredient_id",
            name="uq_drug_component_mapping_ingredient",
        ),
    )
    op.create_index(
        "ix_drug_component_mapping_review",
        "drug_component_mapping",
        ["review_status", "is_active"],
    )

    op.create_table(
        "import_staging_row",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("sheet_name", sa.String(length=80), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("raw_json", sa.Text(), nullable=False),
        sa.Column("normalized_json", sa.Text(), nullable=True),
        sa.Column("validation_status", sa.String(length=20), nullable=False),
        sa.Column("errors_json", sa.Text(), server_default="[]", nullable=False),
        sa.Column("proposed_action", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["import_batch.id"],
            name="fk_import_staging_row_batch_id_import_batch",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_import_staging_row"),
    )
    op.create_index(
        "ix_import_staging_batch_status",
        "import_staging_row",
        ["batch_id", "validation_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_import_staging_batch_status", table_name="import_staging_row"
    )
    op.drop_table("import_staging_row")
    op.drop_index(
        "ix_drug_component_mapping_review",
        table_name="drug_component_mapping",
    )
    op.drop_table("drug_component_mapping")
    op.drop_index("ix_drug_alias_normalized", table_name="drug_alias")
    op.drop_table("drug_alias")
    op.drop_index("ix_drug_master_mapping_review", table_name="drug_master")
    op.drop_index("ix_drug_master_normalized_name", table_name="drug_master")
    op.drop_table("drug_master")
    op.drop_index("ix_import_batch_checksum", table_name="import_batch")
    op.drop_index("ix_import_batch_status_created", table_name="import_batch")
    op.drop_table("import_batch")
    op.drop_table("active_ingredient")

