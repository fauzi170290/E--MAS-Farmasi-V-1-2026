"""UAT release-candidate dossier and readiness evidence"""

from alembic import op
import sqlalchemy as sa

revision = "0024_uat_release_candidate_dossier"
down_revision = "0023_verified_evidence_ceremony"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "uat_release_candidate",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("application_version", sa.String(30), nullable=False),
        sa.Column("schema_revision", sa.String(64), nullable=False),
        sa.Column("qualification_filename", sa.String(260), nullable=False),
        sa.Column("qualification_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("installer_filename", sa.String(260), nullable=False),
        sa.Column("installer_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("environment_label", sa.String(120), nullable=False),
        sa.Column("status", sa.String(16), server_default="DRAFT", nullable=False),
        sa.Column("evidence_snapshot_sha256", sa.String(64), nullable=True),
        sa.Column("clinical_attested_by", sa.String(36), nullable=True),
        sa.Column("clinical_attested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("technical_attested_by", sa.String(36), nullable=True),
        sa.Column("technical_attested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_by", sa.String(36), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason_hash_sha256", sa.String(64), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["clinical_attested_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["technical_attested_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["revoked_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_uat_candidate_status", "uat_release_candidate", ["status", "created_at"])
    op.create_table(
        "uat_readiness_evidence",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("candidate_id", sa.String(36), nullable=False),
        sa.Column("evidence_type", sa.String(40), nullable=False),
        sa.Column("evidence_filename", sa.String(260), nullable=False),
        sa.Column("evidence_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_by", sa.String(36), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["uat_release_candidate.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "evidence_type", name="uq_uat_readiness_evidence_type"),
    )
    op.create_index("ix_uat_readiness_candidate", "uat_readiness_evidence", ["candidate_id", "evidence_type"])
    op.create_table(
        "uat_candidate_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("candidate_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("entry_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["uat_release_candidate.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_uat_candidate_event"),
        sa.UniqueConstraint("entry_hash", name="uq_uat_candidate_hash"),
        sa.UniqueConstraint("previous_hash", name="uq_uat_candidate_previous"),
    )
    op.create_index("ix_uat_candidate_ledger", "uat_candidate_ledger", ["candidate_id", "id"])
    op.execute("CREATE TRIGGER trg_uat_readiness_evidence_no_update BEFORE UPDATE ON uat_readiness_evidence BEGIN SELECT RAISE(ABORT, 'UAT readiness evidence is immutable'); END")
    op.execute("CREATE TRIGGER trg_uat_readiness_evidence_no_delete BEFORE DELETE ON uat_readiness_evidence BEGIN SELECT RAISE(ABORT, 'UAT readiness evidence is immutable'); END")
    op.execute("CREATE TRIGGER trg_uat_candidate_ledger_no_update BEFORE UPDATE ON uat_candidate_ledger BEGIN SELECT RAISE(ABORT, 'UAT candidate ledger is immutable'); END")
    op.execute("CREATE TRIGGER trg_uat_candidate_ledger_no_delete BEFORE DELETE ON uat_candidate_ledger BEGIN SELECT RAISE(ABORT, 'UAT candidate ledger is immutable'); END")
    op.execute("CREATE TRIGGER trg_uat_candidate_binding_immutable BEFORE UPDATE ON uat_release_candidate WHEN OLD.application_version != NEW.application_version OR OLD.schema_revision != NEW.schema_revision OR OLD.qualification_checksum_sha256 != NEW.qualification_checksum_sha256 OR OLD.installer_checksum_sha256 != NEW.installer_checksum_sha256 OR OLD.environment_label != NEW.environment_label OR OLD.expires_at != NEW.expires_at OR OLD.created_by != NEW.created_by OR OLD.created_at != NEW.created_at BEGIN SELECT RAISE(ABORT, 'UAT candidate binding is immutable'); END")
    op.execute("CREATE TRIGGER trg_uat_candidate_terminal_immutable BEFORE UPDATE ON uat_release_candidate WHEN OLD.status = 'REVOKED' OR (OLD.status = 'SEALED' AND NEW.status != 'REVOKED') BEGIN SELECT RAISE(ABORT, 'UAT candidate terminal state is immutable'); END")
    op.execute("CREATE TRIGGER trg_uat_candidate_no_delete BEFORE DELETE ON uat_release_candidate BEGIN SELECT RAISE(ABORT, 'UAT candidate is immutable'); END")


def downgrade() -> None:
    for trigger in (
        "trg_uat_candidate_no_delete", "trg_uat_candidate_terminal_immutable",
        "trg_uat_candidate_binding_immutable", "trg_uat_candidate_ledger_no_delete",
        "trg_uat_candidate_ledger_no_update", "trg_uat_readiness_evidence_no_delete",
        "trg_uat_readiness_evidence_no_update",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    op.drop_index("ix_uat_candidate_ledger", table_name="uat_candidate_ledger")
    op.drop_table("uat_candidate_ledger")
    op.drop_index("ix_uat_readiness_candidate", table_name="uat_readiness_evidence")
    op.drop_table("uat_readiness_evidence")
    op.drop_index("ix_uat_candidate_status", table_name="uat_release_candidate")
    op.drop_table("uat_release_candidate")
