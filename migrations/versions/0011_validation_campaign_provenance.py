"""Bind clinical validation campaigns to runtime provenance."""

from alembic import op
import sqlalchemy as sa


revision = "0011_validation_provenance"
down_revision = "0010_uat_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("validation_campaign") as batch:
        batch.add_column(
            sa.Column("application_version", sa.String(length=30), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "screening_engine_version",
                sa.String(length=40),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "knowledge_base_version_id",
                sa.String(length=36),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "safety_configuration_fingerprint",
                sa.String(length=64),
                nullable=True,
            )
        )
        batch.create_foreign_key(
            "fk_validation_campaign_knowledge_base_version_id",
            "knowledge_base_version",
            ["knowledge_base_version_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("validation_campaign") as batch:
        batch.drop_constraint(
            "fk_validation_campaign_knowledge_base_version_id",
            type_="foreignkey",
        )
        batch.drop_column("safety_configuration_fingerprint")
        batch.drop_column("knowledge_base_version_id")
        batch.drop_column("screening_engine_version")
        batch.drop_column("application_version")
