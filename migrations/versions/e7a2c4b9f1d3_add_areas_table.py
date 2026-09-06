"""add areas reference table + standardize listing.area

Revision ID: e7a2c4b9f1d3
Revises: d4f1a7c9e2b6
Create Date: 2026-09-07 15:00:00.000000

Location filtering was broken because ``listings.area`` was free text an owner
typed at listing time ("F-7" vs "F7" vs "F-7 Islamabad" never matched). This:

  * creates the ``areas`` reference table and populates it from the canonical
    Islamabad / Rawalpindi list (``app.services.areas.CANONICAL_AREAS``),
  * remaps every existing listing's free-text ``area`` onto the closest
    canonical name (``areas.closest_area``) and re-derives ``listings.city``
    from that area, so nothing is left with a non-standard value.

Hand-written in the style of the existing migrations — run ``flask db upgrade``
and sanity-check on Docker/Postgres.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column


# revision identifiers, used by Alembic.
revision = 'e7a2c4b9f1d3'
down_revision = 'd4f1a7c9e2b6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'areas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('slug', sa.String(length=80), nullable=False),
        sa.Column('city', sa.String(length=80), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_areas_name'),
    )
    with op.batch_alter_table('areas', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_areas_slug'), ['slug'], unique=True)
        batch_op.create_index(batch_op.f('ix_areas_city'), ['city'], unique=False)

    # --- Populate the canonical areas -----------------------------------------
    from app.services.areas import CANONICAL_AREAS, closest_area, city_for_area

    areas_tbl = table(
        'areas',
        column('name', sa.String), column('slug', sa.String),
        column('city', sa.String), column('sort_order', sa.Integer),
    )
    op.bulk_insert(areas_tbl, [dict(a) for a in CANONICAL_AREAS])

    # --- Remap existing listings onto standardized areas ---------------------
    bind = op.get_bind()
    listings = bind.execute(sa.text(
        "SELECT id, area, city FROM listings"
    )).fetchall()
    for row in listings:
        canonical = closest_area(row.area, city=row.city)
        new_city = city_for_area(canonical) or row.city
        if canonical != row.area or new_city != row.city:
            bind.execute(
                sa.text("UPDATE listings SET area = :a, city = :c WHERE id = :id"),
                {"a": canonical, "c": new_city, "id": row.id},
            )


def downgrade():
    with op.batch_alter_table('areas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_areas_city'))
        batch_op.drop_index(batch_op.f('ix_areas_slug'))
    op.drop_table('areas')
