"""create aircraft table

Revision ID: e4b1c2d3f4a5
Revises: d1e2f3a4b5c6
Create Date: 2026-01-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e4b1c2d3f4a5"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "aircraft",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("registration", sa.String(length=32), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=True),
        sa.Column("icao_type", sa.String(length=16), nullable=True),
        sa.Column("manufacturer", sa.String(length=64), nullable=True),
        sa.Column("mode_s", sa.String(length=16), nullable=True),
        sa.Column("registered_owner_country_iso_name", sa.String(length=8), nullable=True),
        sa.Column("registered_owner_country_name", sa.String(length=128), nullable=True),
        sa.Column(
            "registered_owner_operator_flag_code",
            sa.String(length=16),
            nullable=True,
        ),
        sa.Column("registered_owner", sa.String(length=255), nullable=True),
        sa.Column("url_photo", sa.Text(), nullable=True),
        sa.Column("url_photo_thumbnail", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("registration"),
    )


def downgrade():
    op.drop_table("aircraft")
