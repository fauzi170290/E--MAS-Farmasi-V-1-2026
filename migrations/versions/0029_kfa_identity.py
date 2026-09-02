"""Add portable SATUSEHAT KFA identities without changing clinical rules.

Revision ID: 0029_kfa_identity
Revises: 0028_pharmacy_scope
"""

from alembic import op
import sqlalchemy as sa


revision = "0029_kfa_identity"
down_revision = "0028_pharmacy_scope"
branch_labels = None
depends_on = None


def _columns(inspector, table):
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    ingredient_columns = _columns(inspector, "active_ingredient")
    if "kfa_bza_code" not in ingredient_columns:
        op.add_column("active_ingredient", sa.Column("kfa_bza_code", sa.String(8), nullable=True))
    if "kfa_validation_status" not in ingredient_columns:
        op.add_column("active_ingredient", sa.Column(
            "kfa_validation_status", sa.String(20), nullable=False, server_default="NOT_SET"))

    inspector = sa.inspect(bind)
    drug_columns = _columns(inspector, "drug_master")
    if "source_system" not in drug_columns:
        op.add_column("drug_master", sa.Column(
            "source_system", sa.String(40), nullable=False, server_default="KHANZA"))
        op.execute("UPDATE drug_master SET source_system='LOCAL' WHERE khanza_code LIKE 'LOCAL:%'")
    if "kfa_product_code" not in drug_columns:
        op.add_column("drug_master", sa.Column("kfa_product_code", sa.String(8), nullable=True))
    if "kfa_product_type" not in drug_columns:
        op.add_column("drug_master", sa.Column("kfa_product_type", sa.String(4), nullable=True))
    if "kfa_validation_status" not in drug_columns:
        op.add_column("drug_master", sa.Column(
            "kfa_validation_status", sa.String(20), nullable=False, server_default="NOT_SET"))

    inspector = sa.inspect(bind)
    ingredient_indexes = {index["name"] for index in inspector.get_indexes("active_ingredient")}
    if "uq_active_ingredient_kfa_bza_code" not in ingredient_indexes:
        op.create_index(
            "uq_active_ingredient_kfa_bza_code", "active_ingredient", ["kfa_bza_code"], unique=True)
    drug_indexes = {index["name"] for index in inspector.get_indexes("drug_master")}
    if "ix_drug_master_kfa_product" not in drug_indexes:
        op.create_index("ix_drug_master_kfa_product", "drug_master", ["kfa_product_code"])


def downgrade():
    # Additive identity metadata is deliberately preserved.  Older binaries
    # ignore these columns, while dropping them would discard reviewed mapping.
    pass
