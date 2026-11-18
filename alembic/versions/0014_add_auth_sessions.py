"""Add revocable API sessions and invalidate them on account changes."""

import sqlalchemy as sa
from alembic import op

revision = '0014_auth_sessions'
down_revision = '0013_notes_folder_ownership'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('auth_epoch', sa.BigInteger(), server_default='0', nullable=False))
    op.create_table(
        'auth_sessions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('auth_epoch', sa.BigInteger(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_auth_sessions_user_id', 'auth_sessions', ['user_id'])
    op.create_index('ix_auth_sessions_expires_at', 'auth_sessions', ['expires_at'])
    op.execute("""
        CREATE FUNCTION advance_user_auth_epoch() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.hashed_password IS DISTINCT FROM OLD.hashed_password
                OR NEW.is_active IS DISTINCT FROM OLD.is_active
                OR NEW.is_deleted IS DISTINCT FROM OLD.is_deleted THEN
                NEW.auth_epoch := OLD.auth_epoch + 1;
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER user_auth_epoch_changed
        BEFORE UPDATE OF hashed_password, is_active, is_deleted ON users
        FOR EACH ROW EXECUTE FUNCTION advance_user_auth_epoch()
    """)


def downgrade() -> None:
    op.execute('DROP TRIGGER user_auth_epoch_changed ON users')
    op.execute('DROP FUNCTION advance_user_auth_epoch()')
    op.drop_table('auth_sessions')
    op.drop_column('users', 'auth_epoch')
