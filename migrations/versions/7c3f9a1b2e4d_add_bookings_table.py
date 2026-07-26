"""add bookings table

Revision ID: 7c3f9a1b2e4d
Revises: 48271134b900
Create Date: 2026-07-26 10:00:00.000000

M3: the rental request/accept/reject/cancel flow (blueprint §5). Only the front
half of the lifecycle exists yet — PAID/HANDED_OVER/ACTIVE/RETURNED/COMPLETED/
DISPUTED land with M4 (money + evidence) and M5 (disputes).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7c3f9a1b2e4d'
down_revision = '48271134b900'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('bookings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('listing_id', sa.Integer(), nullable=False),
    sa.Column('renter_id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('rental_date_start', sa.Date(), nullable=False),
    sa.Column('rental_date_end', sa.Date(), nullable=False),
    sa.Column('deposit_amount', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('message_from_renter', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], ),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['renter_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_bookings_listing_id'), ['listing_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bookings_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bookings_renter_id'), ['renter_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bookings_status'), ['status'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_bookings_status'))
        batch_op.drop_index(batch_op.f('ix_bookings_renter_id'))
        batch_op.drop_index(batch_op.f('ix_bookings_owner_id'))
        batch_op.drop_index(batch_op.f('ix_bookings_listing_id'))

    op.drop_table('bookings')
    # ### end Alembic commands ###
