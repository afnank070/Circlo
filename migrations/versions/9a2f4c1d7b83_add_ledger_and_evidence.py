"""add ledger_entries + evidence_media, bookings.rental_amount

Revision ID: 9a2f4c1d7b83
Revises: 7c3f9a1b2e4d
Create Date: 2026-08-30 12:00:00.000000

M4 (money + evidence, blueprint §5, §7). Adds:
  * ``ledger_entries``  — every rupee that moves for a booking (semi-manual;
    an admin flips ``pending`` -> ``confirmed``).
  * ``evidence_media``  — before/after handover photos (private bucket keys).
  * ``bookings.rental_amount`` — snapshot of the total rental fee at request
    time (nullable; the booking service backfills it on read for old rows).

Hand-written in the style of the existing migrations — no Docker/Postgres was
available to autogenerate against; run ``flask db upgrade`` and sanity-check the
DDL once back on Docker.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9a2f4c1d7b83'
down_revision = '7c3f9a1b2e4d'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ledger_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('booking_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('confirmed_by', sa.Integer(), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ),
        sa.ForeignKeyConstraint(['confirmed_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('ledger_entries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ledger_entries_booking_id'), ['booking_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ledger_entries_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_ledger_entries_type'), ['type'], unique=False)

    op.create_table(
        'evidence_media',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('booking_id', sa.Integer(), nullable=False),
        sa.Column('phase', sa.String(length=10), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), nullable=False),
        sa.Column('object_key', sa.String(length=255), nullable=False),
        sa.Column('media_type', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('evidence_media', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_evidence_media_booking_id'), ['booking_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_evidence_media_phase'), ['phase'], unique=False)
        batch_op.create_index(batch_op.f('ix_evidence_media_uploaded_by'), ['uploaded_by'], unique=False)

    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('rental_amount', sa.Numeric(precision=10, scale=2), nullable=True))


def downgrade():
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_column('rental_amount')

    with op.batch_alter_table('evidence_media', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_evidence_media_uploaded_by'))
        batch_op.drop_index(batch_op.f('ix_evidence_media_phase'))
        batch_op.drop_index(batch_op.f('ix_evidence_media_booking_id'))
    op.drop_table('evidence_media')

    with op.batch_alter_table('ledger_entries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ledger_entries_type'))
        batch_op.drop_index(batch_op.f('ix_ledger_entries_status'))
        batch_op.drop_index(batch_op.f('ix_ledger_entries_booking_id'))
    op.drop_table('ledger_entries')
