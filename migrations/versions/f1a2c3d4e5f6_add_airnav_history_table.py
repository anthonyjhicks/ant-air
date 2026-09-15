"""add airnav radar history table

Revision ID: f1a2c3d4e5f6
Revises: c3e5f7a9b1d2
Create Date: 2026-01-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f1a2c3d4e5f6"
down_revision = "c3e5f7a9b1d2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "flight_history_air_nav_radar",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("flight_id", sa.Integer(), nullable=False),
        sa.Column("dep_date", sa.Date(), nullable=False),
        sa.Column("callsign", sa.String(length=32)),
        sa.Column("flight_number_iata", sa.String(length=16)),
        sa.Column("flight_number_icao", sa.String(length=16)),
        sa.Column("aircraft_registration", sa.String(length=32)),
        sa.Column("aircraft_mode_s", sa.String(length=16)),
        sa.Column("aircraft_serial_number", sa.String(length=32)),
        sa.Column("aircraft_type", sa.String(length=16)),
        sa.Column("aircraft_classes", sa.JSON()),
        sa.Column("aircraft_type_description", sa.String(length=128)),
        sa.Column("airline_iata", sa.String(length=16)),
        sa.Column("airline_icao", sa.String(length=16)),
        sa.Column("airline_name", sa.String(length=128)),
        sa.Column("dep_airport_icao", sa.String(length=16)),
        sa.Column("dep_airport_iata", sa.String(length=16)),
        sa.Column("dep_airport_name", sa.String(length=255)),
        sa.Column("dep_airport_city", sa.String(length=128)),
        sa.Column("dep_airport_state", sa.String(length=128)),
        sa.Column("dep_airport_country", sa.String(length=128)),
        sa.Column("dep_airport_country_iso2", sa.String(length=8)),
        sa.Column("dep_airport_country_iso3", sa.String(length=8)),
        sa.Column("dep_airport_latitude", sa.Float()),
        sa.Column("dep_airport_longitude", sa.Float()),
        sa.Column("dep_airport_tz", sa.String(length=16)),
        sa.Column("dep_airport_tz_diff_utc", sa.Float()),
        sa.Column("scheduled_departure", sa.DateTime()),
        sa.Column("estimated_departure", sa.DateTime()),
        sa.Column("actual_departure", sa.DateTime()),
        sa.Column("actual_takeoff", sa.DateTime()),
        sa.Column("calculated_takeoff", sa.DateTime()),
        sa.Column("arr_airport_icao", sa.String(length=16)),
        sa.Column("arr_airport_iata", sa.String(length=16)),
        sa.Column("arr_airport_name", sa.String(length=255)),
        sa.Column("arr_airport_city", sa.String(length=128)),
        sa.Column("arr_airport_state", sa.String(length=128)),
        sa.Column("arr_airport_country", sa.String(length=128)),
        sa.Column("arr_airport_country_iso2", sa.String(length=8)),
        sa.Column("arr_airport_country_iso3", sa.String(length=8)),
        sa.Column("arr_airport_latitude", sa.Float()),
        sa.Column("arr_airport_longitude", sa.Float()),
        sa.Column("arr_airport_tz", sa.String(length=16)),
        sa.Column("arr_airport_tz_diff_utc", sa.Float()),
        sa.Column("scheduled_arrival", sa.DateTime()),
        sa.Column("estimated_arrival", sa.DateTime()),
        sa.Column("actual_arrival", sa.DateTime()),
        sa.Column("actual_landing", sa.DateTime()),
        sa.Column("calculated_landing", sa.DateTime()),
        sa.Column("departure_status", sa.String(length=16)),
        sa.Column("departure_delay_reason", sa.String(length=32)),
        sa.Column("departure_delay_detail", sa.String(length=32)),
        sa.Column("departure_gate", sa.String(length=16)),
        sa.Column("departure_terminal", sa.String(length=16)),
        sa.Column("arrival_status", sa.String(length=16)),
        sa.Column("arrival_delay_reason", sa.String(length=32)),
        sa.Column("arrival_delay_detail", sa.String(length=32)),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("squawk_code", sa.Integer()),
        sa.Column("distance", sa.Integer()),
        sa.Column("duration", sa.Integer()),
        sa.Column("planned_duration", sa.Integer()),
        sa.Column("source", sa.String(length=32)),
        sa.Column("created", sa.DateTime()),
        sa.Column("updated", sa.DateTime()),
        sa.Column("flight_url", sa.Text()),
        sa.Column("flight_kml", sa.Text()),
        sa.Column("flight_csv", sa.Text()),
        sa.Column("flight_geojson", sa.Text()),
        sa.Column("icao_route", sa.Text()),
        sa.Column("waypoints", sa.Text()),
        sa.Column("status", sa.String(length=32)),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["flight_id"], ["flight.id"]),
    )
    op.create_index(
        "ix_flight_history_air_nav_radar_flight_id",
        "flight_history_air_nav_radar",
        ["flight_id"],
    )
    op.create_index(
        "ix_flight_history_air_nav_radar_dep_date",
        "flight_history_air_nav_radar",
        ["dep_date"],
    )


def downgrade():
    op.drop_index(
        "ix_flight_history_air_nav_radar_dep_date",
        table_name="flight_history_air_nav_radar",
    )
    op.drop_index(
        "ix_flight_history_air_nav_radar_flight_id",
        table_name="flight_history_air_nav_radar",
    )
    op.drop_table("flight_history_air_nav_radar")
