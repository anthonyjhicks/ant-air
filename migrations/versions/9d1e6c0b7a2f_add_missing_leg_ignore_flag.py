"""add missing leg ignore flag

Revision ID: 9d1e6c0b7a2f
Revises: 4c7b1e6f9d2a
Create Date: 2026-01-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9d1e6c0b7a2f"
down_revision = "4c7b1e6f9d2a"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "flight",
        sa.Column(
            "audit_missing_leg_ignored",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("flight", "audit_missing_leg_ignored")
