"""expand airnav history timezones

Revision ID: 1c2d3e4f5a6b
Revises: 9b8c7d6e5f4a
Create Date: 2026-01-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "1c2d3e4f5a6b"
down_revision = "9b8c7d6e5f4a"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "flight_history_air_nav_radar",
        "dep_airport_tz",
        existing_type=sa.String(length=16),
        type_=sa.String(length=64),
    )
    op.alter_column(
        "flight_history_air_nav_radar",
        "arr_airport_tz",
        existing_type=sa.String(length=16),
        type_=sa.String(length=64),
    )


def downgrade():
    op.alter_column(
        "flight_history_air_nav_radar",
        "arr_airport_tz",
        existing_type=sa.String(length=64),
        type_=sa.String(length=16),
    )
    op.alter_column(
        "flight_history_air_nav_radar",
        "dep_airport_tz",
        existing_type=sa.String(length=64),
        type_=sa.String(length=16),
    )
