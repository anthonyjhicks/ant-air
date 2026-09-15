"""add route direction to flight

Revision ID: 9b8c7d6e5f4a
Revises: 5a8c1d9e4f2b
Create Date: 2026-01-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9b8c7d6e5f4a"
down_revision = "5a8c1d9e4f2b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "flight",
        sa.Column("route_direction", sa.String(length=8)),
    )


def downgrade():
    op.drop_column("flight", "route_direction")
