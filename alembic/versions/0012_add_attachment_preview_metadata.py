"""Add attachment preview metadata.

Revision ID: b7d014ca608e
Revises: e3b9d7a2c541
"""
from alembic import op
import sqlalchemy as sa

revision = 'b7d014ca608e'
down_revision = 'e3b9d7a2c541'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('notes_attachments', sa.Column('preview_storage_key', sa.String(256), nullable=True))
    op.add_column('notes_attachments', sa.Column('preview_size_bytes', sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column('notes_attachments', 'preview_size_bytes')
    op.drop_column('notes_attachments', 'preview_storage_key')
