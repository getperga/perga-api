"""improve English notes search

Revision ID: 7a4f3c2d1e90
Revises: 64c9f0ad271e
Create Date: 2026-11-01 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '7a4f3c2d1e90'
down_revision: str | None = '64c9f0ad271e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SEARCH_VECTOR_EXPRESSION = (
    "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(body_plain_text, '')), 'B')"
)


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')

    op.drop_index('idx_notes_search_vector', table_name='notes', postgresql_using='gin')
    op.drop_column('notes', 'search_vector')
    op.add_column(
        'notes',
        sa.Column(
            'search_vector',
            postgresql.TSVECTOR(),
            sa.Computed(SEARCH_VECTOR_EXPRESSION, persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        'idx_notes_search_vector',
        'notes',
        ['search_vector'],
        postgresql_using='gin',
    )
    op.execute(
        'CREATE INDEX idx_notes_title_trgm '
        'ON notes USING gin (lower(title) gin_trgm_ops)'
    )


def downgrade() -> None:
    op.drop_index('idx_notes_title_trgm', table_name='notes', postgresql_using='gin')
    op.drop_index('idx_notes_search_vector', table_name='notes', postgresql_using='gin')
    op.drop_column('notes', 'search_vector')
    op.add_column(
        'notes',
        sa.Column(
            'search_vector',
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple', coalesce(title, '') || ' ' || "
                "coalesce(body_plain_text, ''))",
                persisted=True,
            ),
            nullable=True,
        ),
    )
    op.create_index(
        'idx_notes_search_vector',
        'notes',
        ['search_vector'],
        postgresql_using='gin',
    )
