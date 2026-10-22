"""add is_pinned to notes

Revision ID: 64c9f0ad271e
Revises: c3f42a9d7e10
Create Date: 2026-10-22 18:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '64c9f0ad271e'
down_revision: str | None = 'c3f42a9d7e10'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'notes',
        sa.Column('is_pinned', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('notes', 'is_pinned')
