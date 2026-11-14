"""Add preview metadata and support file attachments.

Revision ID: a35d16b8e027
Revises: e3b9d7a2c541
"""
from alembic import op
import sqlalchemy as sa

revision = 'a35d16b8e027'
down_revision = 'e3b9d7a2c541'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('notes_attachments', sa.Column('preview_storage_key', sa.String(256), nullable=True))
    op.add_column('notes_attachments', sa.Column('preview_size_bytes', sa.BigInteger(), nullable=True))
    op.add_column('notes_attachments', sa.Column('attachment_type', sa.String(16), nullable=False,
                                                 server_default='image'))
    op.create_check_constraint('ck_notes_attachments_type', 'notes_attachments', "attachment_type IN ('image', 'file')")
    for column in ('width', 'height'):
        op.alter_column('notes_attachments', column, nullable=True)


def downgrade() -> None:
    # fail rather than discard file attachments during a downgrade
    for column in ('width', 'height'):
        op.alter_column('notes_attachments', column, nullable=False)
    op.drop_constraint('ck_notes_attachments_type', 'notes_attachments', type_='check')
    op.drop_column('notes_attachments', 'attachment_type')
    op.drop_column('notes_attachments', 'preview_size_bytes')
    op.drop_column('notes_attachments', 'preview_storage_key')
