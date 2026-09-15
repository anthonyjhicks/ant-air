"""add aircraft fields to trip legs

Revision ID: f6a7b8c9d0e1
Revises: a1b2c3d4e5f7
Create Date: 2026-01-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f6a7b8c9d0e1"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "trip_leg",
        sa.Column("aircraft_type", sa.String(length=64)),
    )
    op.add_column(
        "trip_leg",
        sa.Column("aircraft_registration", sa.String(length=32)),
    )


def downgrade():
    op.drop_column("trip_leg", "aircraft_registration")
    op.drop_column("trip_leg", "aircraft_type")
