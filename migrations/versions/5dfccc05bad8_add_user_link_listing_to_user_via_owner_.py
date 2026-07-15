"""add user; link listing to user via owner_id

Revision ID: 5dfccc05bad8
Revises: d65ddfbbd8e7
Create Date: 2026-07-15 23:16:33.650563

M1 introduces the User model and replaces the M2 denormalised owner columns
(owner_name / owner_rating / is_verified) on ``listings`` with an ``owner_id`` FK.

To keep any pre-existing M2 listings working, ``owner_id`` is added as nullable,
each distinct legacy owner is materialised into a real ``users`` row (preserving
their rating and mapping the verified flag to ``verification_status``), the
listings are pointed at those users, and only then is ``owner_id`` made NOT NULL.
Legacy owners get a usable password (``circlo123``) matching the seed convention.
"""
import re

from alembic import op
import sqlalchemy as sa
from werkzeug.security import generate_password_hash


# revision identifiers, used by Alembic.
revision = '5dfccc05bad8'
down_revision = 'd65ddfbbd8e7'
branch_labels = None
depends_on = None

_SEED_EMAIL_DOMAIN = "demo.circlo.pk"
_SEED_PASSWORD = "circlo123"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:60]


def _backfill_owner_users(bind) -> None:
    """Create a user for each distinct legacy owner and link their listings."""
    rows = bind.execute(
        sa.text(
            "SELECT DISTINCT owner_name, owner_rating, is_verified FROM listings"
        )
    ).fetchall()
    if not rows:
        return

    pw_hash = generate_password_hash(_SEED_PASSWORD)
    for name, rating, verified in rows:
        email = f"{_slug(name).replace('-', '.')}@{_SEED_EMAIL_DOMAIN}"
        status = "approved" if verified else "pending"
        user_id = bind.execute(
            sa.text(
                """
                INSERT INTO users
                    (name, email, password_hash, role, verification_status,
                     rating, created_at)
                VALUES
                    (:name, :email, :pw, 'user', :status, :rating, NOW())
                ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """
            ),
            {"name": name, "email": email, "pw": pw_hash,
             "status": status, "rating": rating},
        ).scalar()
        bind.execute(
            sa.text(
                "UPDATE listings SET owner_id = :uid WHERE owner_name = :name"
            ),
            {"uid": user_id, "name": name},
        )


def upgrade():
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('verification_status', sa.String(length=20), nullable=False),
    sa.Column('rating', sa.Numeric(precision=2, scale=1), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)

    # Add owner_id nullable, backfill from legacy owner columns, then enforce NOT NULL.
    with op.batch_alter_table('listings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('owner_id', sa.Integer(), nullable=True))

    _backfill_owner_users(op.get_bind())

    with op.batch_alter_table('listings', schema=None) as batch_op:
        batch_op.alter_column('owner_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_index(batch_op.f('ix_listings_owner_id'), ['owner_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_listings_owner_id_users', 'users', ['owner_id'], ['id']
        )
        batch_op.drop_column('owner_name')
        batch_op.drop_column('owner_rating')
        batch_op.drop_column('is_verified')


def downgrade():
    # Re-add the denormalised columns (nullable to tolerate existing rows), copy
    # owner attributes back from the linked user, then drop the FK.
    with op.batch_alter_table('listings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_verified', sa.BOOLEAN(), nullable=True))
        batch_op.add_column(sa.Column('owner_rating', sa.NUMERIC(precision=2, scale=1), nullable=True))
        batch_op.add_column(sa.Column('owner_name', sa.VARCHAR(length=120), nullable=True))

    op.execute(
        """
        UPDATE listings l SET
            owner_name = u.name,
            owner_rating = COALESCE(u.rating, 0),
            is_verified = (u.verification_status = 'approved')
        FROM users u WHERE l.owner_id = u.id
        """
    )

    with op.batch_alter_table('listings', schema=None) as batch_op:
        batch_op.drop_constraint('fk_listings_owner_id_users', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_listings_owner_id'))
        batch_op.drop_column('owner_id')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_email'))

    op.drop_table('users')
