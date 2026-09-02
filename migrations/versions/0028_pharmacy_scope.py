"""Persistent installation service and additive queue routing; preserve on downgrade."""
from alembic import op
import sqlalchemy as sa

revision = '0028_pharmacy_scope'
down_revision = '0027_durable_monitor'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if 'pharmacy_installation' not in inspector.get_table_names():
        op.create_table('pharmacy_installation',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('care_setting', sa.String(10), nullable=False),
            sa.Column('selected_at', sa.DateTime(), nullable=False),
            sa.CheckConstraint("id=1 AND care_setting IN ('RALAN','RANAP')", name='ck_pharmacy_scope'))
    if 'care_setting' not in {x['name'] for x in inspector.get_columns('processing_queue')}:
        op.add_column('processing_queue', sa.Column('care_setting', sa.String(10), nullable=False, server_default='UNKNOWN'))
        op.create_index('ix_queue_care_setting', 'processing_queue', ['care_setting'])
    # Choosing once without a password cannot silently replace a previous choice.
    op.execute("CREATE TRIGGER IF NOT EXISTS pharmacy_scope_no_update BEFORE UPDATE ON pharmacy_installation BEGIN SELECT RAISE(ABORT, 'installation scope is fixed'); END")
    op.execute("CREATE TRIGGER IF NOT EXISTS pharmacy_scope_no_delete BEFORE DELETE ON pharmacy_installation BEGIN SELECT RAISE(ABORT, 'installation scope is fixed'); END")


def downgrade():
    pass
