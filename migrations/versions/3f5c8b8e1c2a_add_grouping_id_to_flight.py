"""add grouping id to flight

Revision ID: 3f5c8b8e1c2a
Revises: 8f3b9a6d9f3c
Create Date: 2026-01-20 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3f5c8b8e1c2a"
down_revision = "8f3b9a6d9f3c"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "flight", sa.Column("grouping_id", sa.String(length=36), nullable=True)
    )


def downgrade():
    op.drop_column("flight", "grouping_id")
