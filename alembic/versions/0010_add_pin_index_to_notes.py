"""add pin index to notes

Revision ID: d2a8c6f1b430
Revises: 7a4f3c2d1e90
Create Date: 2026-11-05 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'd2a8c6f1b430'
down_revision: str | None = '7a4f3c2d1e90'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('notes', sa.Column('pin_index', sa.Integer(), nullable=True))
    op.execute(
        """
        WITH ordered_pins AS (
            SELECT id, row_number() OVER (
                PARTITION BY user_id ORDER BY updated_dt DESC, id DESC
            ) - 1 AS pin_index
            FROM notes
            WHERE is_pinned = true AND is_deleted = false
        )
        UPDATE notes
        SET pin_index = ordered_pins.pin_index
        FROM ordered_pins
        WHERE notes.id = ordered_pins.id
        """
    )


def downgrade() -> None:
    op.drop_column('notes', 'pin_index')
