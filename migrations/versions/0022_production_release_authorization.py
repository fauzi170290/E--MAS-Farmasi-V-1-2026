"""production release record and deployment authorization"""

from alembic import op
import sqlalchemy as sa

revision = "0022_production_release_authorization"
down_revision = "0021_early_life_surveillance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "production_release_record",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("surveillance_session_id", sa.String(36), nullable=False),
        sa.Column("application_version", sa.String(30), nullable=False),
        sa.Column("schema_revision", sa.String(64), nullable=False),
        sa.Column("environment_label", sa.String(120), nullable=False),
        sa.Column("installer_filename", sa.String(260), nullable=False),
        sa.Column("installer_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), server_default="DRAFT", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("authorized_by", sa.String(36), nullable=True),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason_hash_sha256", sa.String(64), nullable=True),
        sa.Column("revoked_by", sa.String(36), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason_hash_sha256", sa.String(64), nullable=True),
        sa.Column("rollback_ordered_by", sa.String(36), nullable=True),
        sa.Column("rollback_ordered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rollback_reason_hash_sha256", sa.String(64), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["surveillance_session_id"], ["early_life_surveillance_session.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["authorized_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["revoked_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["rollback_ordered_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("surveillance_session_id", name="uq_production_release_surveillance"),
    )
    op.create_index("ix_production_release_status", "production_release_record", ["status", "created_at"])
    op.create_table(
        "production_release_evidence",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("release_record_id", sa.String(36), nullable=False),
        sa.Column("evidence_type", sa.String(40), nullable=False),
        sa.Column("evidence_filename", sa.String(260), nullable=False),
        sa.Column("evidence_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_by", sa.String(36), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["release_record_id"], ["production_release_record.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("release_record_id", "evidence_type", name="uq_production_evidence_type"),
    )
    op.create_index("ix_production_evidence_record", "production_release_evidence", ["release_record_id", "evidence_type"])
    op.create_table(
        "production_change_approval",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("release_record_id", sa.String(36), nullable=False),
        sa.Column("evidence_filename", sa.String(260), nullable=False),
        sa.Column("evidence_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("approval_reference_hash_sha256", sa.String(64), nullable=False),
        sa.Column("external_approver_hash_sha256", sa.String(64), nullable=False),
        sa.Column("deployment_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deployment_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by", sa.String(36), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["release_record_id"], ["production_release_record.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("release_record_id", name="uq_production_change_release"),
    )
    op.create_table(
        "production_release_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("release_record_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("entry_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["release_record_id"], ["production_release_record.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_production_release_event"),
        sa.UniqueConstraint("entry_hash", name="uq_production_release_hash"),
        sa.UniqueConstraint("previous_hash", name="uq_production_release_previous"),
    )
    op.create_index("ix_production_release_ledger_record", "production_release_ledger", ["release_record_id", "id"])
    op.execute("CREATE TRIGGER trg_production_release_binding_immutable BEFORE UPDATE ON production_release_record WHEN OLD.surveillance_session_id != NEW.surveillance_session_id OR OLD.application_version != NEW.application_version OR OLD.schema_revision != NEW.schema_revision OR OLD.environment_label != NEW.environment_label OR OLD.installer_filename != NEW.installer_filename OR OLD.installer_checksum_sha256 != NEW.installer_checksum_sha256 OR OLD.expires_at != NEW.expires_at OR OLD.created_by != NEW.created_by OR OLD.created_at != NEW.created_at BEGIN SELECT RAISE(ABORT, 'production release binding is immutable'); END")
    op.execute("CREATE TRIGGER trg_production_release_terminal_immutable BEFORE UPDATE ON production_release_record WHEN OLD.status IN ('REJECTED','REVOKED','ROLLBACK_ORDERED') BEGIN SELECT RAISE(ABORT, 'production release terminal state is immutable'); END")
    op.execute("CREATE TRIGGER trg_production_release_no_delete BEFORE DELETE ON production_release_record BEGIN SELECT RAISE(ABORT, 'production release record is immutable'); END")
    op.execute("CREATE TRIGGER trg_production_evidence_no_update BEFORE UPDATE ON production_release_evidence BEGIN SELECT RAISE(ABORT, 'production evidence is immutable'); END")
    op.execute("CREATE TRIGGER trg_production_evidence_no_delete BEFORE DELETE ON production_release_evidence BEGIN SELECT RAISE(ABORT, 'production evidence is immutable'); END")
    op.execute("CREATE TRIGGER trg_production_change_no_update BEFORE UPDATE ON production_change_approval BEGIN SELECT RAISE(ABORT, 'production change approval is immutable'); END")
    op.execute("CREATE TRIGGER trg_production_change_no_delete BEFORE DELETE ON production_change_approval BEGIN SELECT RAISE(ABORT, 'production change approval is immutable'); END")
    op.execute("CREATE TRIGGER trg_production_ledger_no_update BEFORE UPDATE ON production_release_ledger BEGIN SELECT RAISE(ABORT, 'production release ledger is append-only'); END")
    op.execute("CREATE TRIGGER trg_production_ledger_no_delete BEFORE DELETE ON production_release_ledger BEGIN SELECT RAISE(ABORT, 'production release ledger is append-only'); END")


def downgrade() -> None:
    for trigger in (
        "trg_production_ledger_no_delete", "trg_production_ledger_no_update",
        "trg_production_change_no_delete", "trg_production_change_no_update",
        "trg_production_evidence_no_delete", "trg_production_evidence_no_update",
        "trg_production_release_no_delete", "trg_production_release_terminal_immutable",
        "trg_production_release_binding_immutable",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    op.drop_index("ix_production_release_ledger_record", table_name="production_release_ledger")
    op.drop_table("production_release_ledger")
    op.drop_table("production_change_approval")
    op.drop_index("ix_production_evidence_record", table_name="production_release_evidence")
    op.drop_table("production_release_evidence")
    op.drop_index("ix_production_release_status", table_name="production_release_record")
    op.drop_table("production_release_record")
