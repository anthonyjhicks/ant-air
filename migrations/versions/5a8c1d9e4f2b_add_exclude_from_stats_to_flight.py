"""add exclude from stats to flight

Revision ID: 5a8c1d9e4f2b
Revises: 2f3a4b5c6d7e
Create Date: 2026-01-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5a8c1d9e4f2b"
down_revision = "2f3a4b5c6d7e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "flight",
        sa.Column(
            "exclude_from_stats",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("flight", "exclude_from_stats")
