"""add app_settings table

Revision ID: b1c3d5e7f9a2
Revises: 9a2f4c1d7b83
Create Date: 2026-08-31 12:00:00.000000

Admin-configurable operational settings (key/value). First use: CIRCLO's
payment-collection details (EasyPaisa / bank account) shown to renters on the
payment step, editable from /admin/settings without a redeploy.

Hand-written in the style of the existing migrations — run ``flask db upgrade``
and sanity-check on Docker/Postgres.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1c3d5e7f9a2'
down_revision = '9a2f4c1d7b83'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('key'),
    )


def downgrade():
    op.drop_table('app_settings')
