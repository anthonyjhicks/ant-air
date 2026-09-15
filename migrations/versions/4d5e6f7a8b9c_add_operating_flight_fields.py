"""add operating flight fields

Revision ID: 4d5e6f7a8b9c
Revises: 1c2d3e4f5a6b
Create Date: 2026-01-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4d5e6f7a8b9c"
down_revision = "1c2d3e4f5a6b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "flight",
        sa.Column("operating_airline_code", sa.String(length=16)),
    )
    op.add_column(
        "flight",
        sa.Column("operating_flight_number", sa.String(length=32)),
    )


def downgrade():
    op.drop_column("flight", "operating_flight_number")
    op.drop_column("flight", "operating_airline_code")
