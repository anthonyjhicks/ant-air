"""add aircraft type normalized to flight

Revision ID: ab12cd34ef56
Revises: 4d5e6f7a8b9c
Create Date: 2026-02-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ab12cd34ef56"
down_revision = "4d5e6f7a8b9c"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "flight",
        sa.Column("aircraft_type_normalized", sa.String(length=64)),
    )


def downgrade():
    op.drop_column("flight", "aircraft_type_normalized")
