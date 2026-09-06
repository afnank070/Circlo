"""add cancellation_requests

Revision ID: d4f1a7c9e2b6
Revises: a3d8e1f4c6b7
Create Date: 2026-09-07 12:00:00.000000

Cancellation flow (blueprint §5, §7). A booking in AWAITING_PAYMENT or PAID
can't just be cancelled — money has moved, so either party raises a
``CancellationRequest`` and an admin confirms the refund by hand (same manual
pattern as the M4 payout step) before the booking goes to CANCELLED.
Pre-payment (REQUESTED / ACCEPTED) cancellations stay instant and need no row
here; once the item is handed over cancellation is gone (dispute flow instead).

Hand-written in the style of the existing migrations — run ``flask db upgrade``
and sanity-check the DDL on Docker/Postgres.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4f1a7c9e2b6'
down_revision = 'a3d8e1f4c6b7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cancellation_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('booking_id', sa.Integer(), nullable=False),
        sa.Column('requested_by', sa.Integer(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ),
        sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('cancellation_requests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_cancellation_requests_booking_id'), ['booking_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_cancellation_requests_requested_by'), ['requested_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_cancellation_requests_status'), ['status'], unique=False)


def downgrade():
    with op.batch_alter_table('cancellation_requests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_cancellation_requests_status'))
        batch_op.drop_index(batch_op.f('ix_cancellation_requests_requested_by'))
        batch_op.drop_index(batch_op.f('ix_cancellation_requests_booking_id'))
    op.drop_table('cancellation_requests')
