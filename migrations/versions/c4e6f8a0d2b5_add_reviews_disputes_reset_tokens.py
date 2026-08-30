"""add password_reset_tokens, reviews, disputes

Revision ID: c4e6f8a0d2b5
Revises: b1c3d5e7f9a2
Create Date: 2026-08-31 15:00:00.000000

M5 (Trust & Polish, blueprint §5, §6). Adds:
  * ``password_reset_tokens`` — single-use, 1-hour reset tokens (hash only).
  * ``reviews``               — mutual 1-5 ratings after a booking completes.
  * ``disputes``              — a reported problem, resolved by an admin, with a
    tracked ``amount_from_fund`` (Trust & Safety Fund bookkeeping).

Trust-fund starting balance is stored in the existing ``app_settings`` table, no
schema change for that.

Hand-written in the style of the existing migrations — run ``flask db upgrade``
and sanity-check the DDL on Docker/Postgres.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4e6f8a0d2b5'
down_revision = 'b1c3d5e7f9a2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'password_reset_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('password_reset_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_password_reset_tokens_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_password_reset_tokens_token_hash'), ['token_hash'], unique=True)

    op.create_table(
        'reviews',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('booking_id', sa.Integer(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=False),
        sa.Column('subject_id', sa.Integer(), nullable=False),
        sa.Column('direction', sa.String(length=20), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['subject_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('booking_id', 'author_id', name='uq_review_booking_author'),
    )
    with op.batch_alter_table('reviews', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_reviews_booking_id'), ['booking_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_reviews_author_id'), ['author_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_reviews_subject_id'), ['subject_id'], unique=False)

    op.create_table(
        'disputes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('booking_id', sa.Integer(), nullable=False),
        sa.Column('opened_by', sa.Integer(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('resolution', sa.Text(), nullable=True),
        sa.Column('deposit_decision', sa.String(length=20), nullable=False),
        sa.Column('amount_from_fund', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ),
        sa.ForeignKeyConstraint(['opened_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('disputes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_disputes_booking_id'), ['booking_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_disputes_opened_by'), ['opened_by'], unique=False)
        batch_op.create_index(batch_op.f('ix_disputes_status'), ['status'], unique=False)


def downgrade():
    with op.batch_alter_table('disputes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_disputes_status'))
        batch_op.drop_index(batch_op.f('ix_disputes_opened_by'))
        batch_op.drop_index(batch_op.f('ix_disputes_booking_id'))
    op.drop_table('disputes')

    with op.batch_alter_table('reviews', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_reviews_subject_id'))
        batch_op.drop_index(batch_op.f('ix_reviews_author_id'))
        batch_op.drop_index(batch_op.f('ix_reviews_booking_id'))
    op.drop_table('reviews')

    with op.batch_alter_table('password_reset_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_password_reset_tokens_token_hash'))
        batch_op.drop_index(batch_op.f('ix_password_reset_tokens_user_id'))
    op.drop_table('password_reset_tokens')
