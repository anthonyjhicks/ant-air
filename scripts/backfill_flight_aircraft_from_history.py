#!/usr/bin/env python

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app
from app.extensions import db
from app.models import Flight, FlightHistoryAirNavRadar


def _is_empty(value):
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _parse_args():
    import argparse

    parser = argparse.ArgumentParser(
        description="Backfill flight aircraft fields from history."
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing aircraft fields on flights.",
    )
    return parser.parse_args()


def main():
    app = create_app()
    args = _parse_args()
    with app.app_context():
        flights = (
            Flight.query.order_by(Flight.start_date.desc(), Flight.id.desc()).all()
        )
        updated = 0
        for flight in flights:
            needs_aircraft = args.overwrite or _is_empty(flight.aircraft)
            needs_registration = args.overwrite or _is_empty(
                flight.aircraft_registration
            )
            if not needs_aircraft and not needs_registration:
                continue

            history = (
                FlightHistoryAirNavRadar.query.filter_by(flight_id=flight.id)
                .filter(
                    db.or_(
                        FlightHistoryAirNavRadar.aircraft_type.isnot(None),
                        FlightHistoryAirNavRadar.aircraft_registration.isnot(None),
                    )
                )
                .order_by(FlightHistoryAirNavRadar.created_at.desc())
                .first()
            )
            if not history:
                continue

            changed = False
            if needs_aircraft and not _is_empty(history.aircraft_type):
                flight.aircraft = history.aircraft_type
                changed = True
            if needs_registration and not _is_empty(history.aircraft_registration):
                flight.aircraft_registration = history.aircraft_registration
                changed = True

            if changed:
                updated += 1

        db.session.commit()
        print(f"Updated flights: {updated}")


if __name__ == "__main__":
    main()
