"""add_planner_partial_indexes

Revision ID: c3f42a9d7e10
Revises: 8bace0897ce7
Create Date: 2026-09-12 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3f42a9d7e10'
down_revision: Union[str, None] = '8bace0897ce7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DAY_ITEMS_INDEX = 'idx_planner_day_items_active_user_day_index'
AGENDA_ITEMS_INDEX = 'idx_planner_agenda_items_active_agenda_index'


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            f'CREATE INDEX CONCURRENTLY {DAY_ITEMS_INDEX} '
            'ON planner_day_items (user_id, day, "index") '
            'WHERE is_deleted IS FALSE'
        )
        op.execute(
            f'CREATE INDEX CONCURRENTLY {AGENDA_ITEMS_INDEX} '
            'ON planner_agenda_items (agenda_id, "index") '
            'WHERE is_deleted IS FALSE'
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {AGENDA_ITEMS_INDEX}')
        op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {DAY_ITEMS_INDEX}')
