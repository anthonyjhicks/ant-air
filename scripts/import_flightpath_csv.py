import argparse

from app import create_app
from app.extensions import db
from app.models import Flight
from app.services.flightpath_import import parse_flightpath_csv
from app.services.importer import import_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", help="Path to flights.csv")
    parser.add_argument(
        "--no-geocode",
        action="store_true",
        help="Skip geocoding cities to countries/coordinates",
    )
    args = parser.parse_args()

    csv_path = args.csv_path
    app = create_app()

    with app.app_context():
        deleted = Flight.query.filter_by(booking_site="baflightpath").delete()
        db.session.commit()
        with open(csv_path, "rb") as handle:
            rows, errors = parse_flightpath_csv(handle, geocode=not args.no_geocode)
        imported = import_rows(rows)

    print(f"Deleted {deleted} baflightpath flights.")
    print(f"Imported {imported} flights.")
    if errors:
        print(f"Skipped {len(errors)} rows:")
        for error in errors:
            print(f"- {error}")


if __name__ == "__main__":
    main()
