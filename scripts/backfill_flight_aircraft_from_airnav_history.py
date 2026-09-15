#!/usr/bin/env python

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import or_

from app import create_app
from app.extensions import db
from app.models import Flight, FlightHistoryAirNavRadar


def _clean(value):
    if not value:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return value


def _fits(value, max_length):
    if value is None or max_length is None:
        return True
    return len(value) <= max_length


def _is_gemini_history(history):
    source = _clean(history.source)
    if source in ("gemini", "gemini_guess"):
        return True
    payload = history.raw_payload
    if isinstance(payload, dict):
        details = payload.get("details")
        if isinstance(details, dict):
            detail_source = _clean(details.get("source"))
            if detail_source in ("gemini", "gemini_guess"):
                return True
    return False


def _parse_args():
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Backfill flight aircraft fields from AirNav history records."
        )
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing aircraft fields on flights.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report changes without persisting updates.",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    app = create_app()
    with app.app_context():
        results = {
            "histories_considered": 0,
            "flights_updated": 0,
            "skipped_existing": 0,
            "skipped_gemini_source": 0,
            "skipped_length": 0,
            "skipped_no_values": 0,
        }

        aircraft_max = Flight.__table__.columns["aircraft"].type.length
        normalized_max = Flight.__table__.columns["aircraft_type_normalized"].type.length
        registration_max = Flight.__table__.columns["aircraft_registration"].type.length

        histories = (
            FlightHistoryAirNavRadar.query.filter(
                or_(
                    FlightHistoryAirNavRadar.aircraft_type_description.isnot(None),
                    FlightHistoryAirNavRadar.aircraft_type.isnot(None),
                    FlightHistoryAirNavRadar.aircraft_registration.isnot(None),
                )
            )
            .order_by(
                FlightHistoryAirNavRadar.created_at.desc(),
                FlightHistoryAirNavRadar.id.desc(),
            )
            .all()
        )

        seen_flights = set()
        for history in histories:
            if history.flight_id in seen_flights:
                continue
            seen_flights.add(history.flight_id)
            results["histories_considered"] += 1

            if _is_gemini_history(history):
                results["skipped_gemini_source"] += 1
                continue

            flight = history.flight
            if not flight:
                continue

            aircraft_desc = _clean(history.aircraft_type_description)
            aircraft_type = _clean(history.aircraft_type)
            aircraft_registration = _clean(history.aircraft_registration)

            if not aircraft_desc and not aircraft_type and not aircraft_registration:
                results["skipped_no_values"] += 1
                continue

            desired_aircraft = aircraft_desc or aircraft_type
            if desired_aircraft and not _fits(desired_aircraft, aircraft_max):
                if aircraft_desc and aircraft_type and _fits(
                    aircraft_type, aircraft_max
                ):
                    desired_aircraft = aircraft_type
                else:
                    desired_aircraft = None
                    results["skipped_length"] += 1

            changed = False

            if desired_aircraft:
                if args.overwrite or not _clean(flight.aircraft):
                    if flight.aircraft != desired_aircraft:
                        flight.aircraft = desired_aircraft
                        changed = True
                else:
                    results["skipped_existing"] += 1

            if aircraft_desc and _fits(aircraft_desc, normalized_max):
                if args.overwrite or not _clean(flight.aircraft_type_normalized):
                    if flight.aircraft_type_normalized != aircraft_desc:
                        flight.aircraft_type_normalized = aircraft_desc
                        changed = True
                else:
                    results["skipped_existing"] += 1
            elif aircraft_desc:
                results["skipped_length"] += 1

            if aircraft_registration and _fits(
                aircraft_registration, registration_max
            ):
                if args.overwrite or not _clean(flight.aircraft_registration):
                    if flight.aircraft_registration != aircraft_registration:
                        flight.aircraft_registration = aircraft_registration
                        changed = True
                else:
                    results["skipped_existing"] += 1
            elif aircraft_registration:
                results["skipped_length"] += 1

            if changed:
                results["flights_updated"] += 1

        if args.dry_run or not results["flights_updated"]:
            db.session.rollback()
        else:
            db.session.commit()

        print("Backfill flight aircraft fields from AirNav history:")
        if args.dry_run:
            print("- dry_run: true")
        for key, value in results.items():
            print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
