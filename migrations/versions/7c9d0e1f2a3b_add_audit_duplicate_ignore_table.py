"""add audit duplicate ignore table

Revision ID: 7c9d0e1f2a3b
Revises: f6a7b8c9d0e1
Create Date: 2026-01-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7c9d0e1f2a3b"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "audit_duplicate_ignore",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("signature", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("audit_duplicate_ignore")
