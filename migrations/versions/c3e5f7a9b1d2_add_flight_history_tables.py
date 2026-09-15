"""add flight history tables

Revision ID: c3e5f7a9b1d2
Revises: 9d1e6c0b7a2f
Create Date: 2026-01-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c3e5f7a9b1d2"
down_revision = "9d1e6c0b7a2f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "flight_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("flight_id", sa.Integer(), nullable=False),
        sa.Column("dep_iata", sa.String(length=8)),
        sa.Column("dep_icao", sa.String(length=8)),
        sa.Column("arr_iata", sa.String(length=8)),
        sa.Column("arr_icao", sa.String(length=8)),
        sa.Column("dep_date", sa.Date(), nullable=False),
        sa.Column("dep_scheduled_time", sa.DateTime()),
        sa.Column("arr_scheduled_time", sa.DateTime()),
        sa.Column("airline_iata", sa.String(length=8)),
        sa.Column("airline_icao", sa.String(length=8)),
        sa.Column("flight_iata", sa.String(length=16)),
        sa.Column("flight_icao", sa.String(length=16)),
        sa.Column("aircraft_icao", sa.String(length=8)),
        sa.Column("aircraft_icao24", sa.String(length=16)),
        sa.Column("aircraft_reg_number", sa.String(length=32)),
        sa.Column("status", sa.String(length=32)),
        sa.Column("system_squawk", sa.String(length=16)),
        sa.Column("system_updated", sa.DateTime()),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["flight_id"], ["flight.id"]),
    )
    op.create_index("ix_flight_history_dep_date", "flight_history", ["dep_date"])
    op.create_index("ix_flight_history_flight_id", "flight_history", ["flight_id"])

    op.create_table(
        "flight_position",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("history_id", sa.Integer(), nullable=False),
        sa.Column("altitude", sa.Float()),
        sa.Column("direction", sa.Float()),
        sa.Column("horizontal_speed", sa.Float()),
        sa.Column("vertical_speed", sa.Float()),
        sa.Column("is_ground", sa.Boolean()),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("position_updated", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["history_id"], ["flight_history.id"]),
    )
    op.create_index(
        "ix_flight_position_history_id", "flight_position", ["history_id"]
    )
    op.create_index(
        "ix_flight_position_position_updated",
        "flight_position",
        ["position_updated"],
    )


def downgrade():
    op.drop_index("ix_flight_position_position_updated", table_name="flight_position")
    op.drop_index("ix_flight_position_history_id", table_name="flight_position")
    op.drop_table("flight_position")
    op.drop_index("ix_flight_history_flight_id", table_name="flight_history")
    op.drop_index("ix_flight_history_dep_date", table_name="flight_history")
    op.drop_table("flight_history")
