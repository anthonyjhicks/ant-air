import argparse
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from app.extensions import db
from app.models import Flight, Trip, TripLeg


def _log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")


def _canonical_trip_key(flight):
    if flight.trip_id:
        return ("trip_id", str(flight.trip_id).strip())
    if flight.trip_name:
        return ("trip_name", str(flight.trip_name).strip())
    return None


def _maybe_update_trip_window(trip, start_date, end_date):
    if start_date:
        if not trip.start_date or start_date < trip.start_date:
            trip.start_date = start_date
            trip.start_date_precision = "day"
            trip.start_date_year = start_date.year
            trip.start_date_month = start_date.month
            trip.start_date_day = start_date.day
    if end_date:
        if not trip.end_date or end_date > trip.end_date:
            trip.end_date = end_date
            trip.end_date_precision = "day"
            trip.end_date_year = end_date.year
            trip.end_date_month = end_date.month
            trip.end_date_day = end_date.day


def _attach_leg(flight, trip, sequence):
    leg = TripLeg(
        trip_id=trip.id,
        sequence=sequence,
        mode="flight",
        carrier_code=flight.airline_code,
        service_class=flight.service_class,
        flight_number=flight.flight_number,
        start_country=flight.start_country,
        start_city_name=flight.start_city_name,
        start_airport=flight.start_airport,
        end_country=flight.end_country,
        end_city_name=flight.end_city_name,
        end_airport=flight.end_airport,
        start_date=flight.start_date,
        start_date_precision="day" if flight.start_date else None,
        start_date_year=flight.start_date.year if flight.start_date else None,
        start_date_month=flight.start_date.month if flight.start_date else None,
        start_date_day=flight.start_date.day if flight.start_date else None,
        end_date=flight.end_date,
        end_date_precision="day" if flight.end_date else None,
        end_date_year=flight.end_date.year if flight.end_date else None,
        end_date_month=flight.end_date.month if flight.end_date else None,
        end_date_day=flight.end_date.day if flight.end_date else None,
    )
    leg.flight = flight
    db.session.add(leg)
    return leg


def backfill(dry_run=False):
    flights = (
        Flight.query.filter(Flight.trip_leg_id.is_(None))
        .order_by(Flight.start_date.asc(), Flight.id.asc())
        .all()
    )
    trips_by_key = {}
    created_trips = 0
    created_legs = 0
    trip_leg_counts = {}

    for flight in flights:
        key = _canonical_trip_key(flight)
        if not key:
            continue
        if key not in trips_by_key:
            existing = None
            if key[0] == "trip_id":
                existing = Trip.query.filter(Trip.trip_code == key[1]).first()
            else:
                existing = Trip.query.filter(Trip.trip_code.is_(None)).filter(
                    Trip.name == key[1]
                ).first()
            if existing:
                trips_by_key[key] = existing
            else:
                trip = Trip(
                    name=flight.trip_name or None,
                    trip_code=flight.trip_id or None,
                    trip_type=flight.trip_type or None,
                )
                db.session.add(trip)
                db.session.flush()
                trips_by_key[key] = trip
                created_trips += 1

        trip = trips_by_key[key]
        if not trip.trip_type and flight.trip_type:
            trip.trip_type = flight.trip_type
        _maybe_update_trip_window(trip, flight.start_date, flight.end_date)
        trip_leg_counts[trip.id] = trip_leg_counts.get(trip.id, 0) + 1
        _attach_leg(flight, trip, sequence=trip_leg_counts[trip.id])
        created_legs += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()

    return created_trips, created_legs


def main():
    parser = argparse.ArgumentParser(description="Backfill Trip and TripLeg records.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build trip records but rollback instead of committing.",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        created_trips, created_legs = backfill(dry_run=args.dry_run)
    mode = "Dry run" if args.dry_run else "Backfill"
    print(f"{mode} created {created_trips} trips and {created_legs} legs.")


if __name__ == "__main__":
    main()
