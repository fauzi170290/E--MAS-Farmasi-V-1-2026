"""verified production evidence package and manual deployment ceremony"""

from alembic import op
import sqlalchemy as sa

revision = "0023_verified_evidence_ceremony"
down_revision = "0022_production_release_authorization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "production_evidence_package_verification",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("verification_id", sa.String(36), nullable=False),
        sa.Column("release_record_id", sa.String(36), nullable=False),
        sa.Column("package_filename", sa.String(260), nullable=False),
        sa.Column("package_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("manifest_checksum_sha256", sa.String(64), nullable=True),
        sa.Column("evidence_snapshot_sha256", sa.String(64), nullable=True),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("entry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("verified_by", sa.String(36), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["release_record_id"], ["production_release_record.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verified_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("verification_id", name="uq_production_package_verification_id"),
    )
    op.create_index("ix_production_package_release", "production_evidence_package_verification", ["release_record_id", "id"])
    op.create_index("ix_production_package_status", "production_evidence_package_verification", ["status", "verified_at"])
    op.create_table(
        "production_deployment_ceremony",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("release_record_id", sa.String(36), nullable=False),
        sa.Column("verification_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), server_default="OPEN", nullable=False),
        sa.Column("deployment_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deployment_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("technical_attested_by", sa.String(36), nullable=True),
        sa.Column("technical_attested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinical_attested_by", sa.String(36), nullable=True),
        sa.Column("clinical_attested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("aborted_by", sa.String(36), nullable=True),
        sa.Column("aborted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("abort_reason_hash_sha256", sa.String(64), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["release_record_id"], ["production_release_record.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verification_id"], ["production_evidence_package_verification.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["technical_attested_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["clinical_attested_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["aborted_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("release_record_id", name="uq_production_ceremony_release"),
    )
    op.create_index("ix_production_ceremony_status", "production_deployment_ceremony", ["status", "created_at"])
    op.execute("CREATE TRIGGER trg_production_package_no_update BEFORE UPDATE ON production_evidence_package_verification BEGIN SELECT RAISE(ABORT, 'production evidence verification is immutable'); END")
    op.execute("CREATE TRIGGER trg_production_package_no_delete BEFORE DELETE ON production_evidence_package_verification BEGIN SELECT RAISE(ABORT, 'production evidence verification is immutable'); END")
    op.execute("CREATE TRIGGER trg_production_ceremony_binding_immutable BEFORE UPDATE ON production_deployment_ceremony WHEN OLD.release_record_id != NEW.release_record_id OR OLD.verification_id != NEW.verification_id OR OLD.deployment_window_start != NEW.deployment_window_start OR OLD.deployment_window_end != NEW.deployment_window_end OR OLD.created_by != NEW.created_by OR OLD.created_at != NEW.created_at BEGIN SELECT RAISE(ABORT, 'production ceremony binding is immutable'); END")
    op.execute("CREATE TRIGGER trg_production_ceremony_terminal_immutable BEFORE UPDATE ON production_deployment_ceremony WHEN OLD.status IN ('ATTESTED','ABORTED') BEGIN SELECT RAISE(ABORT, 'production ceremony terminal state is immutable'); END")
    op.execute("CREATE TRIGGER trg_production_ceremony_no_delete BEFORE DELETE ON production_deployment_ceremony BEGIN SELECT RAISE(ABORT, 'production ceremony is immutable'); END")


def downgrade() -> None:
    for trigger in (
        "trg_production_ceremony_no_delete", "trg_production_ceremony_terminal_immutable",
        "trg_production_ceremony_binding_immutable", "trg_production_package_no_delete",
        "trg_production_package_no_update",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    op.drop_index("ix_production_ceremony_status", table_name="production_deployment_ceremony")
    op.drop_table("production_deployment_ceremony")
    op.drop_index("ix_production_package_status", table_name="production_evidence_package_verification")
    op.drop_index("ix_production_package_release", table_name="production_evidence_package_verification")
    op.drop_table("production_evidence_package_verification")
