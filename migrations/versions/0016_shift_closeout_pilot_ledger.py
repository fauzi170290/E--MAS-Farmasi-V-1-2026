"""Add shift closeout, dual attestation, and immutable pilot ledger."""

from alembic import op
import sqlalchemy as sa


revision = "0016_shift_closeout_ledger"
down_revision = "0015_two_person_advisory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("advisory_pilot_activation") as batch:
        batch.add_column(
            sa.Column("shift_started_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(
            sa.Column("shift_expires_at", sa.DateTime(timezone=True), nullable=True)
        )
    op.execute(
        "UPDATE advisory_pilot_activation "
        "SET shift_started_at = activated_at, shift_expires_at = expires_at "
        "WHERE shift_started_at IS NULL"
    )

    with op.batch_alter_table(
        "advisory_pilot_authorization_request"
    ) as batch:
        batch.add_column(sa.Column("handover_summary_json", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("handover_summary_sha256", sa.String(64), nullable=True)
        )
        batch.add_column(sa.Column("unresolved_alerts", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("unresolved_critical_alerts", sa.Integer(), nullable=True)
        )
        batch.add_column(
            sa.Column("unresolved_interventions", sa.Integer(), nullable=True)
        )
        batch.add_column(
            sa.Column("outgoing_attested_by", sa.String(36), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "outgoing_attested_at", sa.DateTime(timezone=True), nullable=True
            )
        )
        batch.create_foreign_key(
            "fk_advisory_authorization_outgoing_attested_by",
            "app_user",
            ["outgoing_attested_by"],
            ["id"],
            ondelete="RESTRICT",
        )

    op.create_table(
        "advisory_pilot_shift_closeout",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("activation_id", sa.String(36), nullable=False),
        sa.Column("closeout_type", sa.String(40), nullable=False),
        sa.Column("closed_by", sa.String(36), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("summary_sha256", sa.String(64), nullable=False),
        sa.Column(
            "unresolved_alerts", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "unresolved_critical_alerts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "unresolved_interventions",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("outgoing_attested_by", sa.String(36), nullable=True),
        sa.Column(
            "outgoing_attested_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("incoming_attested_by", sa.String(36), nullable=True),
        sa.Column(
            "incoming_attested_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("handover_request_id", sa.String(36), nullable=True),
        sa.Column("notes", sa.String(300), nullable=True),
        sa.ForeignKeyConstraint(
            ["activation_id"],
            ["advisory_pilot_activation.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["closed_by"], ["app_user.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["outgoing_attested_by"], ["app_user.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["incoming_attested_by"], ["app_user.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["handover_request_id"],
            ["advisory_pilot_authorization_request.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "activation_id", name="uq_advisory_shift_closeout_activation"
        ),
    )
    op.create_index(
        "ix_advisory_shift_closeout_closed",
        "advisory_pilot_shift_closeout",
        ["closed_at", "closeout_type"],
    )

    op.create_table(
        "advisory_pilot_session_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("activation_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("entry_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["activation_id"],
            ["advisory_pilot_activation.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["app_user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_pilot_session_ledger_event"),
        sa.UniqueConstraint("entry_hash", name="uq_pilot_session_ledger_hash"),
        sa.UniqueConstraint(
            "previous_hash", name="uq_pilot_session_ledger_previous"
        ),
    )
    op.create_index(
        "ix_pilot_session_ledger_activation",
        "advisory_pilot_session_ledger",
        ["activation_id", "id"],
    )
    op.execute(
        "CREATE TRIGGER trg_pilot_session_ledger_no_update "
        "BEFORE UPDATE ON advisory_pilot_session_ledger "
        "BEGIN SELECT RAISE(ABORT, 'pilot session ledger is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_pilot_session_ledger_no_delete "
        "BEFORE DELETE ON advisory_pilot_session_ledger "
        "BEGIN SELECT RAISE(ABORT, 'pilot session ledger is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_pilot_shift_closeout_no_update "
        "BEFORE UPDATE ON advisory_pilot_shift_closeout "
        "BEGIN SELECT RAISE(ABORT, 'pilot shift closeout is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_pilot_shift_closeout_no_delete "
        "BEFORE DELETE ON advisory_pilot_shift_closeout "
        "BEGIN SELECT RAISE(ABORT, 'pilot shift closeout is immutable'); END"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_pilot_shift_closeout_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_pilot_shift_closeout_no_update")
    op.execute("DROP TRIGGER IF EXISTS trg_pilot_session_ledger_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_pilot_session_ledger_no_update")
    op.drop_index(
        "ix_pilot_session_ledger_activation",
        table_name="advisory_pilot_session_ledger",
    )
    op.drop_table("advisory_pilot_session_ledger")
    op.drop_index(
        "ix_advisory_shift_closeout_closed",
        table_name="advisory_pilot_shift_closeout",
    )
    op.drop_table("advisory_pilot_shift_closeout")

    with op.batch_alter_table(
        "advisory_pilot_authorization_request"
    ) as batch:
        batch.drop_constraint(
            "fk_advisory_authorization_outgoing_attested_by",
            type_="foreignkey",
        )
        batch.drop_column("outgoing_attested_at")
        batch.drop_column("outgoing_attested_by")
        batch.drop_column("unresolved_interventions")
        batch.drop_column("unresolved_critical_alerts")
        batch.drop_column("unresolved_alerts")
        batch.drop_column("handover_summary_sha256")
        batch.drop_column("handover_summary_json")

    with op.batch_alter_table("advisory_pilot_activation") as batch:
        batch.drop_column("shift_expires_at")
        batch.drop_column("shift_started_at")
