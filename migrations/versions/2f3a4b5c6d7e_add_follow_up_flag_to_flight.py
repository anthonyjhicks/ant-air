"""add follow up flag to flight

Revision ID: 2f3a4b5c6d7e
Revises: 7c9d0e1f2a3b
Create Date: 2026-01-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2f3a4b5c6d7e"
down_revision = "7c9d0e1f2a3b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "flight",
        sa.Column(
            "follow_up",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("flight", "follow_up")
