"""Persist the commissioned prescription source with the workstation profile."""

from alembic import op
import sqlalchemy as sa


revision = "0031_commissioning_source"
down_revision = "0030_unmapped_drug_registry"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("pharmacy_installation")}
    if "prescription_source" not in columns:
        op.add_column(
            "pharmacy_installation",
            sa.Column("prescription_source", sa.String(10), nullable=True),
        )
    if "commissioning_complete" not in columns:
        op.add_column(
            "pharmacy_installation",
            sa.Column(
                "commissioning_complete",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    if "commissioned_by" not in columns:
        op.add_column(
            "pharmacy_installation",
            sa.Column("commissioned_by", sa.String(36), nullable=True),
        )
    if "commissioned_at" not in columns:
        op.add_column(
            "pharmacy_installation",
            sa.Column("commissioned_at", sa.DateTime(), nullable=True),
        )
    op.execute("DROP TRIGGER IF EXISTS pharmacy_scope_no_update")
    op.execute(
        "CREATE TRIGGER pharmacy_scope_no_update BEFORE UPDATE ON pharmacy_installation "
        "WHEN OLD.care_setting <> NEW.care_setting "
        "OR OLD.commissioning_complete = 1 "
        "OR OLD.prescription_source IS NOT NULL "
        "BEGIN SELECT RAISE(ABORT, 'installation commissioning is fixed'); END"
    )


def downgrade():
    # Installation identity is persistent safety configuration.
    pass
