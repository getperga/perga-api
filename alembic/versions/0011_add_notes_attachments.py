"""Add notes attachments.

Revision ID: e3b9d7a2c541
Revises: d2a8c6f1b430
"""
from alembic import op
import sqlalchemy as sa

revision = 'e3b9d7a2c541'
down_revision = 'd2a8c6f1b430'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'notes_attachments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('note_id', sa.Integer(), sa.ForeignKey('notes.id'), nullable=False),
        sa.Column('storage_key', sa.String(256), nullable=False, unique=True),
        sa.Column('original_filename', sa.String(256), nullable=False),
        sa.Column('content_type', sa.String(64), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('width', sa.Integer(), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('created_dt', sa.DateTime(timezone=True)),
        sa.Column('updated_dt', sa.DateTime(timezone=True)),
        sa.Column('is_deleted', sa.Boolean()),
        sa.Column('deleted_dt', sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('uploading', 'ready')", name='ck_note_attachments_status'),
    )
    op.create_index('ix_notes_attachments_id', 'notes_attachments', ['id'])
    op.create_index('ix_notes_attachments_note_id', 'notes_attachments', ['note_id'])
    op.create_index('ix_notes_attachments_cleanup', 'notes_attachments', ['is_deleted', 'deleted_dt'])


def downgrade() -> None:
    op.drop_table('notes_attachments')
