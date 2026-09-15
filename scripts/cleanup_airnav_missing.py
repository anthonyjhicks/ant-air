import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app
from app.extensions import db
from app.models import Flight, FlightHistoryAirNavRadar


def _clear_airnav_missing(model, field_name):
    field = getattr(model, field_name)
    return (
        db.session.query(model)
        .filter(field == "AirNavMissing")
        .update({field: None}, synchronize_session=False)
    )


def main():
    app = create_app()
    with app.app_context():
        deleted = (
            FlightHistoryAirNavRadar.query.filter(
                FlightHistoryAirNavRadar.aircraft_type == "AirNavMissing",
                FlightHistoryAirNavRadar.aircraft_registration == "AirNavMissing",
            ).delete(synchronize_session=False)
        )
        history_aircraft_type = _clear_airnav_missing(
            FlightHistoryAirNavRadar, "aircraft_type"
        )
        history_aircraft_reg = _clear_airnav_missing(
            FlightHistoryAirNavRadar, "aircraft_registration"
        )
        flight_aircraft = _clear_airnav_missing(Flight, "aircraft")
        flight_aircraft_reg = _clear_airnav_missing(Flight, "aircraft_registration")

        db.session.commit()
        print("Cleared AirNavMissing values:")
        print(f"- FlightHistoryAirNavRadar deleted: {deleted}")
        print(f"- FlightHistoryAirNavRadar.aircraft_type: {history_aircraft_type}")
        print(
            f"- FlightHistoryAirNavRadar.aircraft_registration: {history_aircraft_reg}"
        )
        print(f"- Flight.aircraft: {flight_aircraft}")
        print(f"- Flight.aircraft_registration: {flight_aircraft_reg}")


if __name__ == "__main__":
    main()
