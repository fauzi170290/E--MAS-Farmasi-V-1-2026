"""Add immutable pilot evidence verification chain-of-custody records."""

from alembic import op
import sqlalchemy as sa


revision = "0018_evidence_verification"
down_revision = "0017_pilot_ledger_quarantine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pilot_evidence_verification",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("package_filename", sa.String(260), nullable=False),
        sa.Column("package_checksum_sha256", sa.String(64), nullable=True),
        sa.Column("manifest_format", sa.String(50), nullable=True),
        sa.Column("application_version", sa.String(30), nullable=True),
        sa.Column("schema_revision", sa.String(64), nullable=True),
        sa.Column("ledger_head_hash", sa.String(64), nullable=True),
        sa.Column("ledger_entries", sa.Integer(), nullable=True),
        sa.Column("closeouts", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(10), nullable=False),
        sa.Column("errors_json", sa.Text(), server_default="[]", nullable=False),
        sa.Column("verified_by", sa.String(36), nullable=True),
        sa.Column(
            "verified_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["verified_by"], ["app_user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pilot_evidence_verification_time",
        "pilot_evidence_verification",
        ["verified_at", "outcome"],
    )
    op.create_index(
        "ix_pilot_evidence_verification_checksum",
        "pilot_evidence_verification",
        ["package_checksum_sha256"],
    )
    op.execute(
        "CREATE TRIGGER trg_pilot_evidence_verification_no_update "
        "BEFORE UPDATE ON pilot_evidence_verification "
        "BEGIN SELECT RAISE(ABORT, "
        "'pilot evidence verification is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_pilot_evidence_verification_no_delete "
        "BEFORE DELETE ON pilot_evidence_verification "
        "BEGIN SELECT RAISE(ABORT, "
        "'pilot evidence verification is immutable'); END"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_pilot_evidence_verification_no_delete"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_pilot_evidence_verification_no_update"
    )
    op.drop_index(
        "ix_pilot_evidence_verification_checksum",
        table_name="pilot_evidence_verification",
    )
    op.drop_index(
        "ix_pilot_evidence_verification_time",
        table_name="pilot_evidence_verification",
    )
    op.drop_table("pilot_evidence_verification")
