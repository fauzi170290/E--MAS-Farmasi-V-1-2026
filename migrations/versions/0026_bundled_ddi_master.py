"""bundled validated DDI master seed provenance"""

from alembic import op
import sqlalchemy as sa


revision = "0026_bundled_ddi_master"
down_revision = "0025_uat_execution_acceptance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bundled_ddi_seed_application",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("bundle_id", sa.String(100), nullable=False),
        sa.Column("bundle_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("semantic_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("source_knowledge_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("knowledge_base_version_id", sa.String(36), nullable=False),
        sa.Column("ingredient_count", sa.Integer(), nullable=False),
        sa.Column("rule_count", sa.Integer(), nullable=False),
        sa.Column("reused_ingredient_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("applied_by", sa.String(36), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("entry_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_base_version_id"],
            ["knowledge_base_version.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["applied_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bundle_id", name="uq_bundled_ddi_seed_bundle"),
        sa.UniqueConstraint(
            "knowledge_base_version_id", name="uq_bundled_ddi_seed_knowledge_version"
        ),
        sa.UniqueConstraint("previous_hash", name="uq_bundled_ddi_seed_previous_hash"),
        sa.UniqueConstraint("entry_hash", name="uq_bundled_ddi_seed_entry_hash"),
    )
    op.execute(
        "CREATE TRIGGER trg_bundled_ddi_seed_no_update "
        "BEFORE UPDATE ON bundled_ddi_seed_application "
        "BEGIN SELECT RAISE(ABORT, 'bundled DDI seed ledger is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_bundled_ddi_seed_no_delete "
        "BEFORE DELETE ON bundled_ddi_seed_application "
        "BEGIN SELECT RAISE(ABORT, 'bundled DDI seed ledger is immutable'); END"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_bundled_ddi_seed_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_bundled_ddi_seed_no_update")
    op.drop_table("bundled_ddi_seed_application")
