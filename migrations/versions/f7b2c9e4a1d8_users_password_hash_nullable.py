"""make users.password_hash nullable (Google OAuth accounts)

Revision ID: f7b2c9e4a1d8
Revises: c4e6f8a0d2b5
Create Date: 2026-09-03 12:00:00.000000

"Sign in with Google": accounts created through the OAuth flow have no password
— they authenticate via the provider — so ``users.password_hash`` becomes
nullable. Email/password accounts still always have a hash (enforced in the
service/model layer, not the DB).

Hand-written in the style of the existing migrations — run ``flask db upgrade``
and sanity-check the DDL on Docker/Postgres.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f7b2c9e4a1d8'
down_revision = 'c4e6f8a0d2b5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column(
            'password_hash',
            existing_type=sa.String(length=255),
            nullable=True,
        )


def downgrade():
    # Backfill any passwordless (OAuth-only) rows so the NOT NULL can be restored.
    op.execute("UPDATE users SET password_hash = '' WHERE password_hash IS NULL")
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column(
            'password_hash',
            existing_type=sa.String(length=255),
            nullable=False,
        )
