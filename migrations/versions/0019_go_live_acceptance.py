"""Add immutable go-live acceptance and decision evidence."""

from alembic import op
import sqlalchemy as sa


revision = "0019_go_live_acceptance"
down_revision = "0018_evidence_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "go_live_acceptance_session",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("application_version", sa.String(30), nullable=False),
        sa.Column("schema_revision", sa.String(64), nullable=False),
        sa.Column("release_report_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("installer_filename", sa.String(260), nullable=False),
        sa.Column("installer_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("environment_label", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), server_default="IN_PROGRESS", nullable=False),
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
        sa.ForeignKeyConstraint(["clinical_attested_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["technical_attested_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decided_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_go_live_acceptance_status",
        "go_live_acceptance_session",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_go_live_acceptance_release",
        "go_live_acceptance_session",
        ["application_version", "release_report_checksum_sha256"],
    )

    op.create_table(
        "go_live_acceptance_item",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("item_code", sa.String(40), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), server_default="NOT_TESTED", nullable=False),
        sa.Column("evidence_filename", sa.String(260), nullable=True),
        sa.Column("evidence_checksum_sha256", sa.String(64), nullable=True),
        sa.Column("notes", sa.String(300), nullable=True),
        sa.Column("tested_by", sa.String(36), nullable=True),
        sa.Column("tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["go_live_acceptance_session.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tested_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "item_code", name="uq_go_live_acceptance_item_code"),
    )
    op.create_index(
        "ix_go_live_acceptance_item_status",
        "go_live_acceptance_item",
        ["session_id", "status"],
    )

    op.create_table(
        "go_live_decision_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("entry_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["go_live_acceptance_session.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_go_live_decision_event"),
        sa.UniqueConstraint("entry_hash", name="uq_go_live_decision_hash"),
        sa.UniqueConstraint("previous_hash", name="uq_go_live_decision_previous"),
    )
    op.create_index(
        "ix_go_live_decision_session",
        "go_live_decision_ledger",
        ["session_id", "id"],
    )

    op.execute(
        "CREATE TRIGGER trg_go_live_session_binding_immutable "
        "BEFORE UPDATE ON go_live_acceptance_session WHEN "
        "NEW.application_version IS NOT OLD.application_version OR "
        "NEW.schema_revision IS NOT OLD.schema_revision OR "
        "NEW.release_report_checksum_sha256 IS NOT OLD.release_report_checksum_sha256 OR "
        "NEW.installer_filename IS NOT OLD.installer_filename OR "
        "NEW.installer_checksum_sha256 IS NOT OLD.installer_checksum_sha256 OR "
        "NEW.environment_label IS NOT OLD.environment_label OR "
        "NEW.expires_at IS NOT OLD.expires_at OR NEW.created_by IS NOT OLD.created_by OR "
        "NEW.created_at IS NOT OLD.created_at "
        "BEGIN SELECT RAISE(ABORT, 'go-live session binding is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_go_live_session_final_immutable "
        "BEFORE UPDATE ON go_live_acceptance_session "
        "WHEN OLD.status IN ('GO', 'NO_GO') "
        "BEGIN SELECT RAISE(ABORT, 'go-live decision is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_go_live_session_no_delete "
        "BEFORE DELETE ON go_live_acceptance_session "
        "BEGIN SELECT RAISE(ABORT, 'go-live session is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_go_live_item_identity_immutable "
        "BEFORE UPDATE ON go_live_acceptance_item WHEN "
        "NEW.session_id IS NOT OLD.session_id OR NEW.item_code IS NOT OLD.item_code OR "
        "NEW.category IS NOT OLD.category OR NEW.description IS NOT OLD.description OR "
        "NEW.owner_type IS NOT OLD.owner_type "
        "BEGIN SELECT RAISE(ABORT, 'go-live item identity is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_go_live_item_final_immutable "
        "BEFORE UPDATE ON go_live_acceptance_item WHEN EXISTS ("
        "SELECT 1 FROM go_live_acceptance_session s "
        "WHERE s.id = OLD.session_id AND s.status IN ('GO', 'NO_GO')) "
        "BEGIN SELECT RAISE(ABORT, 'final go-live evidence is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_go_live_item_no_delete "
        "BEFORE DELETE ON go_live_acceptance_item "
        "BEGIN SELECT RAISE(ABORT, 'go-live evidence is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_go_live_ledger_no_update "
        "BEFORE UPDATE ON go_live_decision_ledger "
        "BEGIN SELECT RAISE(ABORT, 'go-live ledger is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_go_live_ledger_no_delete "
        "BEFORE DELETE ON go_live_decision_ledger "
        "BEGIN SELECT RAISE(ABORT, 'go-live ledger is immutable'); END"
    )


def downgrade() -> None:
    for trigger in (
        "trg_go_live_ledger_no_delete",
        "trg_go_live_ledger_no_update",
        "trg_go_live_item_no_delete",
        "trg_go_live_item_final_immutable",
        "trg_go_live_item_identity_immutable",
        "trg_go_live_session_no_delete",
        "trg_go_live_session_final_immutable",
        "trg_go_live_session_binding_immutable",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    op.drop_index("ix_go_live_decision_session", table_name="go_live_decision_ledger")
    op.drop_table("go_live_decision_ledger")
    op.drop_index("ix_go_live_acceptance_item_status", table_name="go_live_acceptance_item")
    op.drop_table("go_live_acceptance_item")
    op.drop_index("ix_go_live_acceptance_release", table_name="go_live_acceptance_session")
    op.drop_index("ix_go_live_acceptance_status", table_name="go_live_acceptance_session")
    op.drop_table("go_live_acceptance_session")
