"""add users.avatar_key, users.bio

Revision ID: f1c8b3e9a274
Revises: e7a2c4b9f1d3
Create Date: 2026-09-07 18:00:00.000000

Profile enhancements: an optional profile photo (object key in the public
storage bucket, same pattern as listing images) and an optional short bio.
Both nullable — existing accounts keep the initials-circle avatar and show no
bio section.

Hand-written in the style of the existing migrations — run ``flask db upgrade``
and sanity-check the DDL on Docker/Postgres.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1c8b3e9a274'
down_revision = 'e7a2c4b9f1d3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('avatar_key', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('bio', sa.String(length=500), nullable=True))


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('bio')
        batch_op.drop_column('avatar_key')
