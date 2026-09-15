import re

from app import create_app
from app.extensions import db
from app.models import Flight


FLIGHT_NUMBER_PATTERN = re.compile(r"^\s*([A-Za-z]{2,3})\s*([0-9]{1,5})\s*$")


def normalize_flight_numbers():
    flights = Flight.query.order_by(Flight.id.asc()).all()
    updated = 0
    skipped_conflicts = 0

    for flight in flights:
        if not flight.flight_number:
            continue

        match = FLIGHT_NUMBER_PATTERN.match(flight.flight_number)
        if not match:
            continue

        extracted_code = match.group(1).upper()
        extracted_number = match.group(2)

        existing_code = (
            flight.airline_code.strip().upper()
            if flight.airline_code and flight.airline_code.strip()
            else None
        )

        if existing_code and existing_code != extracted_code:
            skipped_conflicts += 1
            continue

        flight.airline_code = extracted_code
        flight.flight_number = extracted_number

        if db.session.is_modified(flight, include_collections=False):
            updated += 1

    db.session.commit()
    return updated, skipped_conflicts


def main():
    app = create_app()
    with app.app_context():
        updated, skipped_conflicts = normalize_flight_numbers()

    print(f"Normalized {updated} flights.")
    if skipped_conflicts:
        print(f"Skipped {skipped_conflicts} conflicting records.")


if __name__ == "__main__":
    main()
