"""merge heads ab12cd34ef56 and e4b1c2d3f4a5

Revision ID: f0f0f0f0f0f0
Revises: ab12cd34ef56, e4b1c2d3f4a5
Create Date: 2026-02-04
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f0f0f0f0f0f0'
down_revision = ('ab12cd34ef56', 'e4b1c2d3f4a5')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
