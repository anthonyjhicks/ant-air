#!/usr/bin/env python3
"""Seed an empty database with a fictional demo flight history.

Creates a few years of flights for an invented traveller ("Sam Rivers"), the
trips that group them, and the standard achievement badges, so a fresh
install has something to look at. Aircraft registrations are real, public
airframes so the aircraft page and photo lookups work.

Usage:
    python scripts/seed_demo_data.py            # refuses to run if flights exist
    python scripts/seed_demo_data.py --reset    # deletes existing flights/trips first
"""
import argparse
import os
import subprocess
import sys
from datetime import date, time, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Flight, Trip, TripLeg  # noqa: E402
from app.services.importer import compute_distance, compute_route_direction  # noqa: E402

TRAVELLER = "Sam Rivers"

# Display name -> ICAO type designator (stored in aircraft_type_normalized)
ICAO_TYPES = {
    "Airbus A320": "A320",
    "Airbus A320neo": "A20N",
    "Airbus A321neo": "A21N",
    "Airbus A220-100": "BCS1",
    "Airbus A330-200": "A332",
    "Airbus A350-900": "A359",
    "Airbus A350-1000": "A35K",
    "Airbus A380-800": "A388",
    "Boeing 737-800": "B738",
    "Boeing 757-200": "B752",
    "Boeing 787-9": "B789",
}

# IATA -> (city, country, lat, lon)
AIRPORTS = {
    "LHR": ("London", "United Kingdom", 51.4706, -0.4619),
    "LGW": ("London", "United Kingdom", 51.1481, -0.1903),
    "LCY": ("London", "United Kingdom", 51.5053, 0.0553),
    "LIS": ("Lisbon", "Portugal", 38.7742, -9.1342),
    "HND": ("Tokyo", "Japan", 35.5494, 139.7798),
    "JFK": ("New York", "United States", 40.6413, -73.7781),
    "CPH": ("Copenhagen", "Denmark", 55.6180, 12.6508),
    "BCN": ("Barcelona", "Spain", 41.2974, 2.0833),
    "DUB": ("Dublin", "Ireland", 53.4213, -6.2701),
    "SIN": ("Singapore", "Singapore", 1.3644, 103.9915),
    "SYD": ("Sydney", "Australia", -33.9399, 151.1753),
    "ATH": ("Athens", "Greece", 37.9364, 23.9445),
    "KEF": ("Reykjavik", "Iceland", 63.9850, -22.6056),
    "AMS": ("Amsterdam", "Netherlands", 52.3105, 4.7683),
    "FCO": ("Rome", "Italy", 41.8003, 12.2389),
    "DXB": ("Dubai", "United Arab Emirates", 25.2532, 55.3657),
    "CPT": ("Cape Town", "South Africa", -33.9715, 18.6021),
    "SFO": ("San Francisco", "United States", 37.6213, -122.3790),
    "YVR": ("Vancouver", "Canada", 49.1947, -123.1792),
    "ZRH": ("Zurich", "Switzerland", 47.4582, 8.5555),
    "EDI": ("Edinburgh", "United Kingdom", 55.9508, -3.3615),
    "IST": ("Istanbul", "Türkiye", 41.2753, 28.7519),
    "RAK": ("Marrakech", "Morocco", 31.6069, -8.0363),
    "MAD": ("Madrid", "Spain", 40.4983, -3.5676),
    "LAX": ("Los Angeles", "United States", 33.9416, -118.4085),
}

# (trip name, [(date, airline, flight no, from, to, aircraft type, registration, class, dep time, arr time), ...])
TRIPS = [
    ("Barcelona long weekend", [
        ("2019-05-10", "BA", "478", "LHR", "BCN", "Airbus A320", "G-EUUA", "Euro Traveller", "07:35", "10:45"),
        ("2019-05-13", "BA", "479", "BCN", "LHR", "Airbus A320", "G-EUUA", "Euro Traveller", "18:05", "19:30"),
    ]),
    ("Dublin day trip", [
        ("2019-09-20", "EI", "155", "LHR", "DUB", "Airbus A320", "EI-DEO", "Economy", "07:10", "08:30"),
        ("2019-09-20", "EI", "178", "DUB", "LHR", "Airbus A320", "EI-DEO", "Economy", "19:45", "21:10"),
    ]),
    ("New York in the fall", [
        ("2019-10-18", "VS", "3", "LHR", "JFK", "Airbus A350-1000", "G-VLUX", "Upper Class", "10:30", "13:35"),
        ("2019-10-25", "VS", "4", "JFK", "LHR", "Airbus A350-1000", "G-VPOP", "Upper Class", "18:30", "06:40"),
    ]),
    ("Amsterdam meetings", [
        ("2020-02-03", "KL", "1000", "LHR", "AMS", "Boeing 737-800", "PH-BXA", "Economy", "06:55", "09:15"),
        ("2020-02-05", "KL", "1017", "AMS", "LHR", "Boeing 737-800", "PH-BXA", "Economy", "17:30", "17:50"),
    ]),
    ("Reykjavik northern lights", [
        ("2021-10-08", "FI", "451", "LHR", "KEF", "Boeing 757-200", "TF-FIR", "Economy", "13:00", "15:55"),
        ("2021-10-12", "FI", "450", "KEF", "LHR", "Boeing 757-200", "TF-FIR", "Economy", "07:40", "11:35"),
    ]),
    ("Lisbon in spring", [
        ("2022-03-25", "TP", "1359", "LHR", "LIS", "Airbus A320neo", "CS-TVA", "Economy", "07:20", "10:05"),
        ("2022-03-29", "TP", "1352", "LIS", "LHR", "Airbus A320neo", "CS-TVA", "Economy", "18:30", "21:10"),
    ]),
    ("Rome anniversary", [
        ("2022-06-10", "BA", "548", "LHR", "FCO", "Airbus A320neo", "G-TTNA", "Club Europe", "08:15", "11:50"),
        ("2022-06-14", "BA", "551", "FCO", "LHR", "Airbus A320neo", "G-TTNA", "Club Europe", "12:40", "14:30"),
    ]),
    ("Tokyo spring trip", [
        ("2023-04-02", "JL", "44", "LHR", "HND", "Boeing 787-9", "JA861J", "Premium Economy", "19:00", "15:20"),
        ("2023-04-14", "JL", "43", "HND", "LHR", "Boeing 787-9", "JA861J", "Premium Economy", "11:40", "16:15"),
    ]),
    ("Copenhagen weekend", [
        ("2023-06-09", "SK", "502", "LHR", "CPH", "Airbus A320neo", "SE-ROA", "Economy", "08:15", "11:10"),
        ("2023-06-11", "SK", "505", "CPH", "LHR", "Airbus A320neo", "SE-ROA", "Economy", "17:45", "18:50"),
    ]),
    ("Athens island hopping", [
        ("2023-09-01", "BA", "632", "LHR", "ATH", "Airbus A321neo", "G-NEOP", "Euro Traveller", "08:40", "14:15"),
        ("2023-09-10", "BA", "633", "ATH", "LHR", "Airbus A321neo", "G-NEOP", "Euro Traveller", "15:05", "17:05"),
    ]),
    ("Dubai stopover", [
        ("2023-11-17", "EK", "2", "LHR", "DXB", "Airbus A380-800", "A6-EDB", "Economy", "14:30", "01:15"),
        ("2023-11-24", "EK", "1", "DXB", "LHR", "Airbus A380-800", "A6-EDB", "Economy", "07:45", "11:25"),
    ]),
    ("Edinburgh festival", [
        ("2024-08-16", "BA", "1440", "LHR", "EDI", "Airbus A320", "G-EUYB", "Euro Traveller", "08:00", "09:25"),
        ("2024-08-19", "BA", "1445", "EDI", "LHR", "Airbus A320", "G-EUYB", "Euro Traveller", "12:10", "13:40"),
    ]),
    ("San Francisco conference", [
        ("2024-10-06", "BA", "285", "LHR", "SFO", "Airbus A380-800", "G-XLEA", "World Traveller Plus", "11:25", "14:20"),
        ("2024-10-12", "BA", "284", "SFO", "LHR", "Airbus A380-800", "G-XLEB", "World Traveller Plus", "16:35", "10:50"),
    ]),
    ("Istanbul city break", [
        ("2025-03-07", "TK", "1980", "LHR", "IST", "Airbus A330-200", "TC-JNA", "Economy", "11:35", "17:40"),
        ("2025-03-11", "TK", "1971", "IST", "LHR", "Airbus A330-200", "TC-JNA", "Economy", "08:05", "10:40"),
    ]),
    ("Singapore and Sydney", [
        ("2025-05-02", "SQ", "317", "LHR", "SIN", "Airbus A380-800", "9V-SKA", "Economy", "11:00", "07:05"),
        ("2025-05-05", "QF", "2", "SIN", "SYD", "Airbus A380-800", "VH-OQA", "Economy", "20:10", "06:25"),
        ("2025-05-18", "QF", "1", "SYD", "SIN", "Airbus A380-800", "VH-OQA", "Economy", "16:10", "22:10"),
        ("2025-05-18", "SQ", "318", "SIN", "LHR", "Airbus A350-900", "9V-SMA", "Economy", "23:55", "06:20"),
    ]),
    ("Marrakech escape", [
        ("2025-11-14", "AT", "801", "LGW", "RAK", "Boeing 737-800", "CN-RGJ", "Economy", "10:15", "14:25"),
        ("2025-11-19", "AT", "800", "RAK", "LGW", "Boeing 737-800", "CN-RGJ", "Economy", "15:20", "19:10"),
    ]),
    ("Cape Town summer", [
        ("2026-01-16", "BA", "59", "LHR", "CPT", "Airbus A380-800", "G-XLEC", "World Traveller", "21:00", "09:55"),
        ("2026-01-30", "BA", "58", "CPT", "LHR", "Airbus A380-800", "G-XLEC", "World Traveller", "19:30", "05:45"),
    ]),
    ("Zurich ski weekend", [
        ("2026-02-20", "LX", "317", "LCY", "ZRH", "Airbus A220-100", "HB-JBA", "Economy", "09:50", "12:30"),
        ("2026-02-23", "LX", "318", "ZRH", "LCY", "Airbus A220-100", "HB-JBA", "Economy", "13:15", "14:05"),
    ]),
    ("Vancouver and the Rockies", [
        ("2026-06-05", "AC", "855", "LHR", "YVR", "Boeing 787-9", "C-FGDZ", "Economy", "13:20", "15:05"),
        ("2026-06-19", "AC", "854", "YVR", "LHR", "Boeing 787-9", "C-FGDZ", "Economy", "19:50", "13:15"),
    ]),
]

# A future trip so the "next flight" card has something to show.
NEXT_TRIP = ("Lisbon long weekend", [
    (18, "TP", "1359", "LHR", "LIS", "Airbus A320neo", "CS-TVA", "Economy", "07:20", "10:05"),
    (21, "TP", "1352", "LIS", "LHR", "Airbus A320neo", "CS-TVA", "Economy", "18:30", "21:10"),
])


def parse_time(value):
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def build_flight(row, trip_name, trip_code, source):
    dep_date, airline, number, origin, dest, aircraft, reg, cabin, dep_time, arr_time = row
    if isinstance(dep_date, int):
        start_date = date.today() + timedelta(days=dep_date)
    else:
        start_date = date.fromisoformat(dep_date)
    o_city, o_country, o_lat, o_lon = AIRPORTS[origin]
    d_city, d_country, d_lat, d_lon = AIRPORTS[dest]
    end_date = start_date
    if parse_time(arr_time) < parse_time(dep_time):
        end_date = start_date + timedelta(days=1)
    return Flight(
        status="approved",
        trip_name=trip_name,
        trip_id=trip_code,
        trip_type="Air",
        booking_site=source,
        traveller=TRAVELLER,
        airline_code=airline,
        flight_number=number,
        aircraft=aircraft,
        aircraft_type_normalized=ICAO_TYPES.get(aircraft),
        aircraft_registration=reg,
        service_class=cabin,
        start_country=o_country,
        start_city_name=o_city,
        start_airport=origin,
        start_lat=o_lat,
        start_long=o_lon,
        start_date=start_date,
        start_time=parse_time(dep_time),
        end_country=d_country,
        end_city_name=d_city,
        end_airport=dest,
        end_lat=d_lat,
        end_long=d_lon,
        end_date=end_date,
        end_time=parse_time(arr_time),
        stops=0,
        distance=compute_distance(o_lat, o_lon, d_lat, d_lon),
        route_direction=compute_route_direction(o_lat, o_lon, d_lat, d_lon),
        source_file="demo",
    )


def seed(reset=False):
    existing = Flight.query.count()
    if existing and not reset:
        print(f"Database already has {existing} flights. Re-run with --reset to replace them.")
        return 1
    if reset:
        for model in (Flight, TripLeg, Trip):
            deleted = model.query.delete()
            print(f"Deleted {deleted} {model.__tablename__} rows")
        db.session.commit()

    created = 0
    all_trips = TRIPS + [NEXT_TRIP]
    for index, (trip_name, rows) in enumerate(all_trips, start=1):
        trip_code = f"DEMO-{index:03d}"
        flights = [build_flight(row, trip_name, trip_code, "demo") for row in rows]
        trip = Trip(
            name=trip_name,
            trip_code=trip_code,
            trip_type="Air",
            start_date=flights[0].start_date,
            start_date_precision="day",
            start_date_year=flights[0].start_date.year,
            start_date_month=flights[0].start_date.month,
            start_date_day=flights[0].start_date.day,
            end_date=flights[-1].end_date,
            end_date_precision="day",
            end_date_year=flights[-1].end_date.year,
            end_date_month=flights[-1].end_date.month,
            end_date_day=flights[-1].end_date.day,
        )
        db.session.add(trip)
        db.session.flush()
        for sequence, flight in enumerate(flights, start=1):
            leg = TripLeg(
                trip_id=trip.id,
                sequence=sequence,
                mode="flight",
                carrier_code=flight.airline_code,
                flight_number=flight.flight_number,
                aircraft_type=flight.aircraft,
                aircraft_registration=flight.aircraft_registration,
                service_class=flight.service_class,
                start_country=flight.start_country,
                start_city_name=flight.start_city_name,
                start_airport=flight.start_airport,
                end_country=flight.end_country,
                end_city_name=flight.end_city_name,
                end_airport=flight.end_airport,
                start_date=flight.start_date,
                start_date_precision="day",
                start_date_year=flight.start_date.year,
                start_date_month=flight.start_date.month,
                start_date_day=flight.start_date.day,
                end_date=flight.end_date,
                end_date_precision="day",
                end_date_year=flight.end_date.year,
                end_date_month=flight.end_date.month,
                end_date_day=flight.end_date.day,
            )
            db.session.add(leg)
            db.session.flush()
            flight.trip_leg_id = leg.id
            db.session.add(flight)
            created += 1
    db.session.commit()
    print(f"Created {created} demo flights across {len(all_trips)} trips for {TRAVELLER}.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete existing flights, legs and trips first")
    parser.add_argument("--skip-badges", action="store_true", help="do not seed achievement badges")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        status = seed(reset=args.reset)
    if status:
        return status

    if not args.skip_badges:
        here = os.path.dirname(os.path.abspath(__file__))
        for script in ("seed_badges.py", "seed_rare_aircraft_badges.py"):
            path = os.path.join(here, script)
            if os.path.exists(path):
                print(f"\nRunning {script} ...")
                subprocess.run([sys.executable, path], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
