import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('datasets',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('created_at', sa.String(length=32), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('sources',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('latitude', sa.Float(), nullable=False),
    sa.Column('longitude', sa.Float(), nullable=False),
    sa.Column('baseline_speed', sa.Float(), nullable=False),
    sa.Column('created_at', sa.String(length=32), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('events',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('source_id', sa.String(length=36), nullable=False),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('severity', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('origin', sa.String(length=20), nullable=False),
    sa.Column('image_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.String(length=32), nullable=False),
    sa.Column('updated_at', sa.String(length=32), nullable=False),
    sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_events_created_at'), 'events', ['created_at'], unique=False)
    op.create_index('ix_events_source_kind_time', 'events', ['source_id', 'kind', 'created_at'], unique=False)
    op.create_index(op.f('ix_events_status'), 'events', ['status'], unique=False)
    op.create_table('images',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('dataset_id', sa.String(length=36), nullable=True),
    sa.Column('filename', sa.String(length=200), nullable=False),
    sa.Column('width', sa.Integer(), nullable=False),
    sa.Column('height', sa.Integer(), nullable=False),
    sa.Column('split', sa.String(length=10), nullable=False),
    sa.Column('annotations', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.String(length=32), nullable=False),
    sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('metrics',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('source_id', sa.String(length=36), nullable=False),
    sa.Column('observed_at', sa.String(length=32), nullable=False),
    sa.Column('speed', sa.Float(), nullable=False),
    sa.Column('congestion', sa.Float(), nullable=False),
    sa.Column('volume', sa.Integer(), nullable=False),
    sa.Column('anomaly', sa.Boolean(), nullable=False),
    sa.Column('score', sa.Float(), nullable=False),
    sa.Column('baseline', sa.Float(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_id', 'observed_at')
    )
    op.create_index('ix_metrics_source_time', 'metrics', ['source_id', 'observed_at'], unique=False)
    op.create_table('event_actions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('event_id', sa.String(length=36), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('created_at', sa.String(length=32), nullable=False),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_event_actions_event_id'), 'event_actions', ['event_id'], unique=False)
    op.create_table('jobs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('source_id', sa.String(length=36), nullable=False),
    sa.Column('image_id', sa.String(length=36), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('result', sa.JSON(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('lease_token', sa.String(length=36), nullable=True),
    sa.Column('lease_until', sa.String(length=32), nullable=True),
    sa.Column('created_at', sa.String(length=32), nullable=False),
    sa.Column('updated_at', sa.String(length=32), nullable=False),
    sa.ForeignKeyConstraint(['image_id'], ['images.id'], ),
    sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_jobs_status'), 'jobs', ['status'], unique=False)

def downgrade():
    op.drop_index(op.f('ix_jobs_status'), table_name='jobs')
    op.drop_table('jobs')
    op.drop_index(op.f('ix_event_actions_event_id'), table_name='event_actions')
    op.drop_table('event_actions')
    op.drop_index('ix_metrics_source_time', table_name='metrics')
    op.drop_table('metrics')
    op.drop_table('images')
    op.drop_index(op.f('ix_events_status'), table_name='events')
    op.drop_index('ix_events_source_kind_time', table_name='events')
    op.drop_index(op.f('ix_events_created_at'), table_name='events')
    op.drop_table('events')
    op.drop_table('sources')
    op.drop_table('datasets')
