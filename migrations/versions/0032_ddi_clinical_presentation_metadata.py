"""Add Medscape clinical presentation metadata without changing DDI rules."""

from alembic import op
import sqlalchemy as sa


revision = "0032_ddi_clinical_presentation_metadata"
down_revision = "0031_commissioning_source"
branch_labels = None
depends_on = None


def _add_missing(table: str, columns: tuple[sa.Column, ...]) -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
    for column in columns:
        if column.name not in existing:
            op.add_column(table, column)


def upgrade():
    _add_missing(
        "ddi_rule",
        (
            sa.Column("clinical_detail_available", sa.Boolean(), nullable=True),
            sa.Column("medscape_action", sa.Text(), nullable=True),
            sa.Column("recommendation_source", sa.String(250), nullable=True),
            sa.Column("medscape_summary", sa.Text(), nullable=True),
        ),
    )
    _add_missing(
        "screening_pair",
        (
            sa.Column("severity_label", sa.String(100), nullable=True),
            sa.Column("mechanism", sa.Text(), nullable=True),
            sa.Column("clinical_detail_available", sa.Boolean(), nullable=True),
            sa.Column("medscape_action", sa.Text(), nullable=True),
            sa.Column("recommendation_source", sa.String(250), nullable=True),
            sa.Column("medscape_summary", sa.Text(), nullable=True),
            sa.Column("source_name", sa.String(250), nullable=True),
        ),
    )


def downgrade():
    # Clinical snapshots are retained for auditability; no destructive downgrade.
    pass
