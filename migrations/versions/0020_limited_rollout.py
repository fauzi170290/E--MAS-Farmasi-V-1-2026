"""limited production rollout and immutable operational guardrail ledger"""

from alembic import op
import sqlalchemy as sa


revision = "0020_limited_rollout"
down_revision = "0019_go_live_acceptance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "limited_rollout_session",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("acceptance_session_id", sa.String(36), nullable=False),
        sa.Column("application_version", sa.String(30), nullable=False),
        sa.Column("schema_revision", sa.String(64), nullable=False),
        sa.Column("scope_label", sa.String(120), nullable=False),
        sa.Column("max_workstations", sa.Integer(), nullable=False),
        sa.Column("incident_halt_threshold", sa.Integer(), nullable=False),
        sa.Column("critical_halt_threshold", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), server_default="PLANNED", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("clinical_attested_by", sa.String(36), nullable=True),
        sa.Column("clinical_attested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("technical_attested_by", sa.String(36), nullable=True),
        sa.Column("technical_attested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(36), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.String(300), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("started_by", sa.String(36), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["acceptance_session_id"], ["go_live_acceptance_session.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["clinical_attested_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["technical_attested_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decided_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["started_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_limited_rollout_status", "limited_rollout_session", ["status", "created_at"])
    op.create_index("ix_limited_rollout_acceptance", "limited_rollout_session", ["acceptance_session_id"])
    op.create_table(
        "limited_rollout_wave",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("rollout_session_id", sa.String(36), nullable=False),
        sa.Column("wave_number", sa.Integer(), nullable=False),
        sa.Column("cohort_label", sa.String(120), nullable=False),
        sa.Column("planned_workstations", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), server_default="PENDING", nullable=False),
        sa.Column("activated_by", sa.String(36), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.String(36), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["rollout_session_id"], ["limited_rollout_session.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["activated_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["closed_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rollout_session_id", "wave_number", name="uq_rollout_wave_number"),
    )
    op.create_index("ix_limited_rollout_wave_status", "limited_rollout_wave", ["rollout_session_id", "status"])
    op.create_table(
        "limited_rollout_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("rollout_session_id", sa.String(36), nullable=False),
        sa.Column("wave_id", sa.String(36), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("entry_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["rollout_session_id"], ["limited_rollout_session.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["wave_id"], ["limited_rollout_wave.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_limited_rollout_event"),
        sa.UniqueConstraint("entry_hash", name="uq_limited_rollout_hash"),
        sa.UniqueConstraint("previous_hash", name="uq_limited_rollout_previous"),
    )
    op.create_index("ix_limited_rollout_ledger_session", "limited_rollout_ledger", ["rollout_session_id", "id"])

    op.execute(
        "CREATE TRIGGER trg_rollout_session_binding_immutable BEFORE UPDATE ON limited_rollout_session WHEN "
        "OLD.acceptance_session_id != NEW.acceptance_session_id OR OLD.application_version != NEW.application_version OR "
        "OLD.schema_revision != NEW.schema_revision OR OLD.scope_label != NEW.scope_label OR "
        "OLD.max_workstations != NEW.max_workstations OR OLD.incident_halt_threshold != NEW.incident_halt_threshold OR "
        "OLD.critical_halt_threshold != NEW.critical_halt_threshold OR OLD.expires_at != NEW.expires_at "
        "BEGIN SELECT RAISE(ABORT, 'rollout binding is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_rollout_session_final_immutable BEFORE UPDATE ON limited_rollout_session "
        "WHEN OLD.status IN ('COMPLETED','ROLLED_BACK') BEGIN SELECT RAISE(ABORT, 'rollout decision is immutable'); END"
    )
    op.execute("CREATE TRIGGER trg_rollout_session_no_delete BEFORE DELETE ON limited_rollout_session BEGIN SELECT RAISE(ABORT, 'rollout session is immutable'); END")
    op.execute(
        "CREATE TRIGGER trg_rollout_wave_identity_immutable BEFORE UPDATE ON limited_rollout_wave WHEN "
        "OLD.rollout_session_id != NEW.rollout_session_id OR OLD.wave_number != NEW.wave_number OR "
        "OLD.cohort_label != NEW.cohort_label OR OLD.planned_workstations != NEW.planned_workstations "
        "BEGIN SELECT RAISE(ABORT, 'rollout wave identity is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_rollout_wave_final_immutable BEFORE UPDATE ON limited_rollout_wave "
        "WHEN OLD.status IN ('COMPLETED','ROLLED_BACK') BEGIN SELECT RAISE(ABORT, 'rollout wave is final'); END"
    )
    op.execute("CREATE TRIGGER trg_rollout_wave_no_delete BEFORE DELETE ON limited_rollout_wave BEGIN SELECT RAISE(ABORT, 'rollout wave is immutable'); END")
    op.execute("CREATE TRIGGER trg_rollout_ledger_no_update BEFORE UPDATE ON limited_rollout_ledger BEGIN SELECT RAISE(ABORT, 'rollout ledger is append-only'); END")
    op.execute("CREATE TRIGGER trg_rollout_ledger_no_delete BEFORE DELETE ON limited_rollout_ledger BEGIN SELECT RAISE(ABORT, 'rollout ledger is append-only'); END")


def downgrade() -> None:
    for trigger in (
        "trg_rollout_ledger_no_delete", "trg_rollout_ledger_no_update",
        "trg_rollout_wave_no_delete", "trg_rollout_wave_final_immutable",
        "trg_rollout_wave_identity_immutable", "trg_rollout_session_no_delete",
        "trg_rollout_session_final_immutable", "trg_rollout_session_binding_immutable",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    op.drop_index("ix_limited_rollout_ledger_session", table_name="limited_rollout_ledger")
    op.drop_table("limited_rollout_ledger")
    op.drop_index("ix_limited_rollout_wave_status", table_name="limited_rollout_wave")
    op.drop_table("limited_rollout_wave")
    op.drop_index("ix_limited_rollout_acceptance", table_name="limited_rollout_session")
    op.drop_index("ix_limited_rollout_status", table_name="limited_rollout_session")
    op.drop_table("limited_rollout_session")
