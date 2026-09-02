"""early-life surveillance and release promotion evidence"""

from alembic import op
import sqlalchemy as sa

revision = "0021_early_life_surveillance"
down_revision = "0020_limited_rollout"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "early_life_surveillance_session",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("rollout_session_id", sa.String(36), nullable=False),
        sa.Column("application_version", sa.String(30), nullable=False),
        sa.Column("schema_revision", sa.String(64), nullable=False),
        sa.Column("environment_label", sa.String(120), nullable=False),
        sa.Column("minimum_snapshots", sa.Integer(), nullable=False),
        sa.Column("minimum_observation_hours", sa.Integer(), nullable=False),
        sa.Column("maximum_snapshot_age_hours", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), server_default="OBSERVING", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("clinical_attested_by", sa.String(36), nullable=True),
        sa.Column("clinical_attested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("technical_attested_by", sa.String(36), nullable=True),
        sa.Column("technical_attested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(36), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.String(300), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["rollout_session_id"], ["limited_rollout_session.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["clinical_attested_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["technical_attested_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decided_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rollout_session_id", name="uq_surveillance_rollout"),
    )
    op.create_index("ix_surveillance_status", "early_life_surveillance_session", ["status", "created_at"])
    op.create_table(
        "surveillance_snapshot",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("surveillance_session_id", sa.String(36), nullable=False),
        sa.Column("prescriptions_total", sa.Integer(), nullable=False),
        sa.Column("critical_total", sa.Integer(), nullable=False),
        sa.Column("unacknowledged_critical_alerts", sa.Integer(), nullable=False),
        sa.Column("open_interventions", sa.Integer(), nullable=False),
        sa.Column("polling_failures", sa.Integer(), nullable=False),
        sa.Column("health_state", sa.String(20), nullable=False),
        sa.Column("audit_chain_valid", sa.Boolean(), nullable=False),
        sa.Column("captured_by", sa.String(36), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["surveillance_session_id"], ["early_life_surveillance_session.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["captured_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_surveillance_snapshot_session", "surveillance_snapshot", ["surveillance_session_id", "captured_at"])
    op.create_table(
        "surveillance_issue",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("surveillance_session_id", sa.String(36), nullable=False),
        sa.Column("issue_number", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("summary_hash_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), server_default="OPEN", nullable=False),
        sa.Column("resolution_hash_sha256", sa.String(64), nullable=True),
        sa.Column("recorded_by", sa.String(36), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_by", sa.String(36), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["surveillance_session_id"], ["early_life_surveillance_session.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["closed_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("surveillance_session_id", "issue_number", name="uq_surveillance_issue_number"),
    )
    op.create_index("ix_surveillance_issue_status", "surveillance_issue", ["surveillance_session_id", "status", "severity"])
    op.create_table(
        "surveillance_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("surveillance_session_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("entry_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["surveillance_session_id"], ["early_life_surveillance_session.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_surveillance_event"),
        sa.UniqueConstraint("entry_hash", name="uq_surveillance_hash"),
        sa.UniqueConstraint("previous_hash", name="uq_surveillance_previous"),
    )
    op.create_index("ix_surveillance_ledger_session", "surveillance_ledger", ["surveillance_session_id", "id"])
    op.execute("CREATE TRIGGER trg_surveillance_session_binding_immutable BEFORE UPDATE ON early_life_surveillance_session WHEN OLD.rollout_session_id != NEW.rollout_session_id OR OLD.application_version != NEW.application_version OR OLD.schema_revision != NEW.schema_revision OR OLD.environment_label != NEW.environment_label OR OLD.minimum_snapshots != NEW.minimum_snapshots OR OLD.minimum_observation_hours != NEW.minimum_observation_hours OR OLD.maximum_snapshot_age_hours != NEW.maximum_snapshot_age_hours OR OLD.expires_at != NEW.expires_at BEGIN SELECT RAISE(ABORT, 'surveillance binding is immutable'); END")
    op.execute("CREATE TRIGGER trg_surveillance_session_final_immutable BEFORE UPDATE ON early_life_surveillance_session WHEN OLD.status IN ('PROMOTED','ROLLED_BACK') BEGIN SELECT RAISE(ABORT, 'surveillance decision is immutable'); END")
    op.execute("CREATE TRIGGER trg_surveillance_session_no_delete BEFORE DELETE ON early_life_surveillance_session BEGIN SELECT RAISE(ABORT, 'surveillance session is immutable'); END")
    op.execute("CREATE TRIGGER trg_surveillance_snapshot_no_update BEFORE UPDATE ON surveillance_snapshot BEGIN SELECT RAISE(ABORT, 'surveillance snapshot is immutable'); END")
    op.execute("CREATE TRIGGER trg_surveillance_snapshot_no_delete BEFORE DELETE ON surveillance_snapshot BEGIN SELECT RAISE(ABORT, 'surveillance snapshot is immutable'); END")
    op.execute("CREATE TRIGGER trg_surveillance_issue_identity_immutable BEFORE UPDATE ON surveillance_issue WHEN OLD.surveillance_session_id != NEW.surveillance_session_id OR OLD.issue_number != NEW.issue_number OR OLD.severity != NEW.severity OR OLD.summary_hash_sha256 != NEW.summary_hash_sha256 OR OLD.recorded_by != NEW.recorded_by OR OLD.recorded_at != NEW.recorded_at BEGIN SELECT RAISE(ABORT, 'surveillance issue identity is immutable'); END")
    op.execute("CREATE TRIGGER trg_surveillance_issue_closed_immutable BEFORE UPDATE ON surveillance_issue WHEN OLD.status = 'CLOSED' BEGIN SELECT RAISE(ABORT, 'closed surveillance issue is immutable'); END")
    op.execute("CREATE TRIGGER trg_surveillance_issue_no_delete BEFORE DELETE ON surveillance_issue BEGIN SELECT RAISE(ABORT, 'surveillance issue is immutable'); END")
    op.execute("CREATE TRIGGER trg_surveillance_ledger_no_update BEFORE UPDATE ON surveillance_ledger BEGIN SELECT RAISE(ABORT, 'surveillance ledger is append-only'); END")
    op.execute("CREATE TRIGGER trg_surveillance_ledger_no_delete BEFORE DELETE ON surveillance_ledger BEGIN SELECT RAISE(ABORT, 'surveillance ledger is append-only'); END")


def downgrade() -> None:
    for trigger in (
        "trg_surveillance_ledger_no_delete", "trg_surveillance_ledger_no_update",
        "trg_surveillance_issue_no_delete", "trg_surveillance_issue_closed_immutable",
        "trg_surveillance_issue_identity_immutable", "trg_surveillance_snapshot_no_delete",
        "trg_surveillance_snapshot_no_update", "trg_surveillance_session_no_delete",
        "trg_surveillance_session_final_immutable", "trg_surveillance_session_binding_immutable",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    op.drop_index("ix_surveillance_ledger_session", table_name="surveillance_ledger")
    op.drop_table("surveillance_ledger")
    op.drop_index("ix_surveillance_issue_status", table_name="surveillance_issue")
    op.drop_table("surveillance_issue")
    op.drop_index("ix_surveillance_snapshot_session", table_name="surveillance_snapshot")
    op.drop_table("surveillance_snapshot")
    op.drop_index("ix_surveillance_status", table_name="early_life_surveillance_session")
    op.drop_table("early_life_surveillance_session")
