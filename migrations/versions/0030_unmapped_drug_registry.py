"""Add the privacy-minimal unresolved Khanza drug registry.

Revision ID: 0030_unmapped_drug_registry
Revises: 0029_kfa_identity
"""
from alembic import op
import sqlalchemy as sa

revision = "0030_unmapped_drug_registry"
down_revision = "0029_kfa_identity"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "unmapped_drug_registry" not in inspector.get_table_names():
        op.create_table("unmapped_drug_registry",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("source_drug_code", sa.String(50), nullable=False, unique=True),
            sa.Column("source_drug_name", sa.String(200), nullable=False),
            sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
            sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("resolved_drug_id", sa.String(36), sa.ForeignKey("drug_master.id", ondelete="SET NULL")),
            sa.Column("resolved_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
        op.create_index("ix_unmapped_drug_registry_active_frequency", "unmapped_drug_registry", ["resolved_at", "occurrence_count"])
    if "unmapped_drug_occurrence" not in inspector.get_table_names():
        op.create_table("unmapped_drug_occurrence",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("registry_id", sa.String(36), sa.ForeignKey("unmapped_drug_registry.id", ondelete="CASCADE"), nullable=False),
            sa.Column("occurrence_key", sa.String(64), nullable=False),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("registry_id", "occurrence_key", name="uq_unmapped_drug_occurrence_once"))


def downgrade():
    pass
