"""add aircraft registration to flight

Revision ID: d1e2f3a4b5c6
Revises: b7c8d9e0f1a2
Create Date: 2026-01-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d1e2f3a4b5c6"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "flight",
        sa.Column("aircraft_registration", sa.String(length=32)),
    )


def downgrade():
    op.drop_column("flight", "aircraft_registration")
