"""add source file to flight

Revision ID: 8f3b9a6d9f3c
Revises: 2e9cb0cadf86
Create Date: 2026-01-20 10:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8f3b9a6d9f3c"
down_revision = "2e9cb0cadf86"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("flight", sa.Column("source_file", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("flight", "source_file")
