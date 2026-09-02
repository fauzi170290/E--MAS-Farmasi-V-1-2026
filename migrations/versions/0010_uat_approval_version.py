"""Bind UAT approvals to the running application version."""

from alembic import op
import sqlalchemy as sa


revision = "0010_uat_version"
down_revision = "0009_sprint10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "uat_session",
        sa.Column(
            "pharmacist_approved_version",
            sa.String(length=30),
            nullable=True,
        ),
    )
    op.add_column(
        "uat_session",
        sa.Column(
            "it_approved_version",
            sa.String(length=30),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("uat_session", "it_approved_version")
    op.drop_column("uat_session", "pharmacist_approved_version")
