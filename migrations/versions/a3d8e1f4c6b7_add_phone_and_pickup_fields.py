"""add users.phone, listings.pickup_location, listings.map_link

Revision ID: a3d8e1f4c6b7
Revises: f7b2c9e4a1d8
Create Date: 2026-09-06 09:00:00.000000

Contact reveal + pickup location feature: once a booking is accepted, the
renter and owner see each other's phone number and the listing's pickup
location / optional Google Maps link — plain data reveal, no messaging.
``users.phone`` is nullable so existing accounts (and OAuth signups, which
skip the phone step) don't violate a NOT NULL constraint; it's required at
the signup form level for new email/password accounts going forward.

Hand-written in the style of the existing migrations — run ``flask db upgrade``
and sanity-check the DDL on Docker/Postgres.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3d8e1f4c6b7'
down_revision = 'f7b2c9e4a1d8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('phone', sa.String(length=20), nullable=True))

    with op.batch_alter_table('listings') as batch_op:
        batch_op.add_column(sa.Column('pickup_location', sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column('map_link', sa.String(length=500), nullable=True))


def downgrade():
    with op.batch_alter_table('listings') as batch_op:
        batch_op.drop_column('map_link')
        batch_op.drop_column('pickup_location')

    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('phone')
