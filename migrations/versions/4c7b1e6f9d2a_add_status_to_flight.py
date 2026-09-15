"""add status to flight

Revision ID: 4c7b1e6f9d2a
Revises: 3f5c8b8e1c2a
Create Date: 2026-01-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4c7b1e6f9d2a"
down_revision = "3f5c8b8e1c2a"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "flight",
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="approved",
        ),
    )


def downgrade():
    op.drop_column("flight", "status")
