"""Sprint 7: intervensi apoteker dan dokumentasi klinis."""

from alembic import op
import sqlalchemy as sa

revision = "0007_sprint7"
down_revision = "0006_sprint6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pharmacist_intervention",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("queue_item_id", sa.String(36), nullable=False),
        sa.Column("screening_id", sa.String(36), nullable=True),
        sa.Column("pharmacist_user_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(30), server_default="OPEN", nullable=False),
        sa.Column("intervention_type", sa.String(60), nullable=False),
        sa.Column("decision", sa.String(60), nullable=False),
        sa.Column("communication_method", sa.String(40), nullable=True),
        sa.Column("communication_result", sa.String(60), nullable=True),
        sa.Column("contacted_party", sa.String(120), nullable=True),
        sa.Column("reason_if_continued", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["pharmacist_user_id"], ["app_user.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["queue_item_id"], ["processing_queue.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["screening_id"], ["screening.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pharmacist_intervention"),
        sa.UniqueConstraint(
            "queue_item_id", name="uq_intervention_queue_item"
        ),
    )
    op.create_index(
        "ix_intervention_status_created",
        "pharmacist_intervention",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_intervention_pharmacist",
        "pharmacist_intervention",
        ["pharmacist_user_id", "created_at"],
    )
    op.create_table(
        "intervention_detail",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("intervention_id", sa.String(36), nullable=False),
        sa.Column("finding_type", sa.String(40), nullable=False),
        sa.Column("reference", sa.String(300), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("outcome", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["intervention_id"],
            ["pharmacist_intervention.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_intervention_detail"),
    )
    op.create_index(
        "ix_intervention_detail_parent",
        "intervention_detail",
        ["intervention_id", "finding_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_intervention_detail_parent", table_name="intervention_detail"
    )
    op.drop_table("intervention_detail")
    op.drop_index(
        "ix_intervention_pharmacist", table_name="pharmacist_intervention"
    )
    op.drop_index(
        "ix_intervention_status_created", table_name="pharmacist_intervention"
    )
    op.drop_table("pharmacist_intervention")
