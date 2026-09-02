"""Durable ingestion checkpoints and observed source events.

Downgrade intentionally retains these additive tables and their audit evidence.
Older releases ignore them; re-upgrade reuses them. No clinical data is removed.
"""
from alembic import op
import sqlalchemy as sa

revision = '0027_durable_monitor'
down_revision = '0026_bundled_ddi_master'
branch_labels = None
depends_on = None


def upgrade():
    # Explicit schema definitions, independent of future ORM revisions.
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if 'monitor_checkpoint' not in existing:
        op.create_table('monitor_checkpoint',
            sa.Column('adapter_code', sa.String(30), primary_key=True),
            sa.Column('lane', sa.String(30), primary_key=True),
            sa.Column('cursor_key', sa.String(80), nullable=False),
            sa.Column('cursor_time', sa.DateTime(timezone=True)),
            sa.Column('cycles', sa.Integer(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))
    if 'monitor_inbox' not in existing:
        op.create_table('monitor_inbox',
            sa.Column('adapter_code', sa.String(30), primary_key=True),
            sa.Column('no_resep', sa.String(80), primary_key=True),
            sa.Column('lane', sa.String(30), nullable=False),
            sa.Column('priority', sa.Integer(), nullable=False),
            sa.Column('state', sa.String(30), nullable=False),
            sa.Column('fingerprint', sa.String(64), nullable=False),
            sa.Column('source_status', sa.String(40), nullable=False),
            sa.Column('sequence', sa.Integer(), nullable=False),
            sa.Column('event_id', sa.String(36)),
            sa.Column('stable_since', sa.DateTime(timezone=True)),
            sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('attempts', sa.Integer(), nullable=False),
            sa.Column('error_code', sa.String(80), nullable=False),
            sa.Column('last_seen_at', sa.DateTime(timezone=True)),
            sa.Column('screening_id', sa.String(36)))
        op.create_index('ix_monitor_inbox_due', 'monitor_inbox', ['adapter_code', 'next_attempt_at', 'priority'])
    if 'monitor_event' not in existing:
        op.create_table('monitor_event',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('adapter_code', sa.String(30), nullable=False),
            sa.Column('no_resep', sa.String(80), nullable=False),
            sa.Column('sequence', sa.Integer(), nullable=False),
            sa.Column('event_type', sa.String(40), nullable=False),
            sa.Column('fingerprint', sa.String(64), nullable=False),
            sa.Column('source_status', sa.String(40), nullable=False),
            sa.Column('snapshot_json', sa.Text(), nullable=False),
            sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('state', sa.String(30), nullable=False),
            sa.Column('screening_id', sa.String(36)),
            sa.Column('completed_at', sa.DateTime(timezone=True)))
        op.create_index('ix_monitor_event_source', 'monitor_event', ['adapter_code', 'no_resep', 'sequence'], unique=True)
    op.execute("CREATE TRIGGER IF NOT EXISTS trg_monitor_event_source_immutable "
        "BEFORE UPDATE OF adapter_code, no_resep, sequence, event_type, fingerprint, source_status, snapshot_json, observed_at "
        "ON monitor_event BEGIN SELECT RAISE(ABORT, 'source observation is immutable'); END")
    op.execute("CREATE TRIGGER IF NOT EXISTS trg_monitor_event_no_delete BEFORE DELETE ON monitor_event "
        "BEGIN SELECT RAISE(ABORT, 'source observation is immutable'); END")


def downgrade():
    pass  # Preserve checkpoints, retries, source observations and ledger links.
