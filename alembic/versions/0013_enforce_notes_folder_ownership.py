"""Enforce owner consistency for note and folder links."""

from alembic import op

revision = '0013_notes_folder_ownership'
down_revision = 'a35d16b8e027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint('uq_notes_folders_id_user_id', 'notes_folders', ['id', 'user_id'])
    op.create_foreign_key(
        'fk_notes_folder_owner', 'notes', 'notes_folders', ['folder_id', 'user_id'], ['id', 'user_id'],
    )
    op.create_foreign_key(
        'fk_notes_folders_parent_owner', 'notes_folders', 'notes_folders',
        ['parent_id', 'user_id'], ['id', 'user_id'],
    )
    op.create_check_constraint('ck_notes_folders_not_own_parent', 'notes_folders', 'parent_id <> id')


def downgrade() -> None:
    op.drop_constraint('ck_notes_folders_not_own_parent', 'notes_folders', type_='check')
    op.drop_constraint('fk_notes_folders_parent_owner', 'notes_folders', type_='foreignkey')
    op.drop_constraint('fk_notes_folder_owner', 'notes', type_='foreignkey')
    op.drop_constraint('uq_notes_folders_id_user_id', 'notes_folders', type_='unique')
