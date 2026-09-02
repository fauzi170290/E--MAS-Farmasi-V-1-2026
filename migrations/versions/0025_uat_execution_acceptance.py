"""UAT execution evidence and independent acceptance"""

from alembic import op
import sqlalchemy as sa

revision = "0025_uat_execution_acceptance"
down_revision = "0024_uat_release_candidate_dossier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "uat_execution_session",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("candidate_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), server_default="OPEN", nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("results_snapshot_sha256", sa.String(64), nullable=True),
        sa.Column("clinical_signed_by", sa.String(36), nullable=True),
        sa.Column("clinical_signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("technical_signed_by", sa.String(36), nullable=True),
        sa.Column("technical_signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(36), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason_hash_sha256", sa.String(64), nullable=True),
        sa.Column("revoked_by", sa.String(36), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason_hash_sha256", sa.String(64), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["uat_release_candidate.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["clinical_signed_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["technical_signed_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decided_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["revoked_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", name="uq_uat_execution_candidate"),
    )
    op.create_index("ix_uat_execution_status", "uat_execution_session", ["status", "created_at"])
    op.create_table(
        "uat_execution_result",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("result_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("scenario_code", sa.String(60), nullable=False),
        sa.Column("owner_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("evidence_filename", sa.String(260), nullable=False),
        sa.Column("evidence_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("result_summary_hash_sha256", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tested_by", sa.String(36), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["uat_execution_session.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tested_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("result_id"),
    )
    op.create_index("ix_uat_result_scenario", "uat_execution_result", ["session_id", "scenario_code", "id"])
    op.create_index("ix_uat_result_status", "uat_execution_result", ["session_id", "status"])
    op.create_table(
        "uat_execution_issue",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("issue_number", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(12), nullable=False),
        sa.Column("status", sa.String(12), server_default="OPEN", nullable=False),
        sa.Column("summary_hash_sha256", sa.String(64), nullable=False),
        sa.Column("raised_by", sa.String(36), nullable=False),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolution_hash_sha256", sa.String(64), nullable=True),
        sa.Column("resolved_by", sa.String(36), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["uat_execution_session.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["raised_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resolved_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "issue_number", name="uq_uat_issue_number"),
    )
    op.create_index("ix_uat_issue_status", "uat_execution_issue", ["session_id", "status", "severity"])
    op.create_table(
        "uat_execution_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("entry_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["uat_execution_session.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_uat_execution_event"),
        sa.UniqueConstraint("entry_hash", name="uq_uat_execution_hash"),
        sa.UniqueConstraint("previous_hash", name="uq_uat_execution_previous"),
    )
    op.create_index("ix_uat_execution_ledger", "uat_execution_ledger", ["session_id", "id"])
    for table in ("uat_execution_result", "uat_execution_ledger"):
        op.execute(f"CREATE TRIGGER trg_{table}_no_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, '{table} is immutable'); END")
        op.execute(f"CREATE TRIGGER trg_{table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, '{table} is immutable'); END")
    op.execute("CREATE TRIGGER trg_uat_issue_binding_immutable BEFORE UPDATE ON uat_execution_issue WHEN OLD.session_id != NEW.session_id OR OLD.issue_number != NEW.issue_number OR OLD.severity != NEW.severity OR OLD.summary_hash_sha256 != NEW.summary_hash_sha256 OR OLD.raised_by != NEW.raised_by OR OLD.raised_at != NEW.raised_at BEGIN SELECT RAISE(ABORT, 'UAT issue binding is immutable'); END")
    op.execute("CREATE TRIGGER trg_uat_issue_terminal_immutable BEFORE UPDATE ON uat_execution_issue WHEN OLD.status = 'RESOLVED' BEGIN SELECT RAISE(ABORT, 'UAT issue resolution is immutable'); END")
    op.execute("CREATE TRIGGER trg_uat_issue_no_delete BEFORE DELETE ON uat_execution_issue BEGIN SELECT RAISE(ABORT, 'UAT issue is immutable'); END")
    op.execute("CREATE TRIGGER trg_uat_execution_binding_immutable BEFORE UPDATE ON uat_execution_session WHEN OLD.candidate_id != NEW.candidate_id OR OLD.window_start != NEW.window_start OR OLD.window_end != NEW.window_end OR OLD.created_by != NEW.created_by OR OLD.created_at != NEW.created_at BEGIN SELECT RAISE(ABORT, 'UAT execution binding is immutable'); END")
    op.execute("CREATE TRIGGER trg_uat_execution_terminal_immutable BEFORE UPDATE ON uat_execution_session WHEN OLD.status IN ('REJECTED','REVOKED') OR (OLD.status = 'ACCEPTED' AND NEW.status != 'REVOKED') BEGIN SELECT RAISE(ABORT, 'UAT execution terminal state is immutable'); END")
    op.execute("CREATE TRIGGER trg_uat_execution_no_delete BEFORE DELETE ON uat_execution_session BEGIN SELECT RAISE(ABORT, 'UAT execution is immutable'); END")


def downgrade() -> None:
    for trigger in (
        "trg_uat_execution_no_delete", "trg_uat_execution_terminal_immutable",
        "trg_uat_execution_binding_immutable", "trg_uat_issue_no_delete",
        "trg_uat_issue_terminal_immutable", "trg_uat_issue_binding_immutable",
        "trg_uat_execution_ledger_no_delete", "trg_uat_execution_ledger_no_update",
        "trg_uat_execution_result_no_delete", "trg_uat_execution_result_no_update",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    op.drop_index("ix_uat_execution_ledger", table_name="uat_execution_ledger")
    op.drop_table("uat_execution_ledger")
    op.drop_index("ix_uat_issue_status", table_name="uat_execution_issue")
    op.drop_table("uat_execution_issue")
    op.drop_index("ix_uat_result_status", table_name="uat_execution_result")
    op.drop_index("ix_uat_result_scenario", table_name="uat_execution_result")
    op.drop_table("uat_execution_result")
    op.drop_index("ix_uat_execution_status", table_name="uat_execution_session")
    op.drop_table("uat_execution_session")
