"""Add optimistic locking and persisted height/glucose measurements.

Revision ID: b4e20261015
Revises: 3a9f9c9fc63d
"""
from alembic import op
import sqlalchemy as sa
revision = 'b4e20261015'
down_revision = '3a9f9c9fc63d'
branch_labels = None
depends_on = None

def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    # The original migration predates Account, although create_all installations have it.
    if 'accounts' not in inspector.get_table_names():
        op.create_table('accounts',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('phone_number', sa.String(32), nullable=False, unique=True),
            sa.Column('clinic_name', sa.String(128), nullable=False),
            sa.Column('doctor_name', sa.String(128), nullable=False),
            sa.Column('password_hash', sa.String(255), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False))
        op.create_index('ix_accounts_phone_number','accounts',['phone_number'])
    for table in ['encounters','vouchers','appointments']:
        if 'version' not in {c['name'] for c in inspector.get_columns(table)}:
            op.add_column(table, sa.Column('version', sa.Integer(), nullable=False, server_default='1'))
    for field in ['height','rbs']:
        if field not in {c['name'] for c in inspector.get_columns('encounter_vitals')}:
            op.add_column('encounter_vitals', sa.Column(field, sa.Float(), nullable=True))

def downgrade():
    # Explicitly abort because removing versioning/measurements can discard clinical data.
    raise RuntimeError('Restore a reviewed backup to reverse this clinical schema migration.')
