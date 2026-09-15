"""add trip tables

Revision ID: a1b2c3d4e5f7
Revises: 9d1e6c0b7a2f
Create Date: 2026-01-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f7"
down_revision = "9d1e6c0b7a2f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "trip",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255)),
        sa.Column("trip_code", sa.String(length=64), unique=True),
        sa.Column("trip_type", sa.String(length=64)),
        sa.Column("notes", sa.Text()),
        sa.Column("start_date", sa.Date()),
        sa.Column("start_date_precision", sa.String(length=8)),
        sa.Column("start_date_year", sa.Integer()),
        sa.Column("start_date_month", sa.Integer()),
        sa.Column("start_date_day", sa.Integer()),
        sa.Column("end_date", sa.Date()),
        sa.Column("end_date_precision", sa.String(length=8)),
        sa.Column("end_date_year", sa.Integer()),
        sa.Column("end_date_month", sa.Integer()),
        sa.Column("end_date_day", sa.Integer()),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_table(
        "trip_leg",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trip_id", sa.Integer(), sa.ForeignKey("trip.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="flight"),
        sa.Column("carrier_name", sa.String(length=128)),
        sa.Column("carrier_code", sa.String(length=16)),
        sa.Column("service_class", sa.String(length=64)),
        sa.Column("flight_number", sa.String(length=32)),
        sa.Column("start_country", sa.String(length=128)),
        sa.Column("start_city_name", sa.String(length=128)),
        sa.Column("start_airport", sa.String(length=64)),
        sa.Column("end_country", sa.String(length=128)),
        sa.Column("end_city_name", sa.String(length=128)),
        sa.Column("end_airport", sa.String(length=64)),
        sa.Column("start_date", sa.Date()),
        sa.Column("start_date_precision", sa.String(length=8)),
        sa.Column("start_date_year", sa.Integer()),
        sa.Column("start_date_month", sa.Integer()),
        sa.Column("start_date_day", sa.Integer()),
        sa.Column("end_date", sa.Date()),
        sa.Column("end_date_precision", sa.String(length=8)),
        sa.Column("end_date_year", sa.Integer()),
        sa.Column("end_date_month", sa.Integer()),
        sa.Column("end_date_day", sa.Integer()),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.add_column("flight", sa.Column("trip_leg_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_flight_trip_leg_id",
        "flight",
        "trip_leg",
        ["trip_leg_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint("fk_flight_trip_leg_id", "flight", type_="foreignkey")
    op.drop_column("flight", "trip_leg_id")
    op.drop_table("trip_leg")
    op.drop_table("trip")
