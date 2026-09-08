"""switch the rental unit from days to hours

Revision ID: b8e2d1a4c6f0
Revises: f1c8b3e9a274
Create Date: 2026-09-09 10:00:00.000000

The rental unit is now hours, not days (real architectural change, not a
relabel):

* ``listings.price_per_day`` -> ``listings.price_per_hour`` (hourly rate).
* ``bookings.rental_date_start`` / ``rental_date_end`` (date-only) are replaced
  by ``bookings.start_datetime`` (hour precision) + ``bookings.duration_hours``.

This is pre-launch: there is no production data to convert, so the columns are
swapped outright and the seed script now emits hourly rates. ``server_default``s
are only there so the DDL applies cleanly to a dev DB that already has demo
rows — the app always sets these values explicitly.

Hand-written in the style of the existing migrations — run ``flask db upgrade``
and sanity-check the DDL on Docker/Postgres.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8e2d1a4c6f0'
down_revision = 'f1c8b3e9a274'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('listings', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'price_per_hour', sa.Numeric(precision=10, scale=2),
            nullable=False, server_default='0',
        ))
        batch_op.drop_column('price_per_day')

    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'start_datetime', sa.DateTime(),
            nullable=False, server_default=sa.func.now(),
        ))
        batch_op.add_column(sa.Column(
            'duration_hours', sa.Integer(), nullable=False, server_default='1',
        ))
        batch_op.drop_column('rental_date_start')
        batch_op.drop_column('rental_date_end')


def downgrade():
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'rental_date_end', sa.Date(), nullable=False,
            server_default=sa.func.now(),
        ))
        batch_op.add_column(sa.Column(
            'rental_date_start', sa.Date(), nullable=False,
            server_default=sa.func.now(),
        ))
        batch_op.drop_column('duration_hours')
        batch_op.drop_column('start_datetime')

    with op.batch_alter_table('listings', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'price_per_day', sa.Numeric(precision=10, scale=2),
            nullable=False, server_default='0',
        ))
        batch_op.drop_column('price_per_hour')
