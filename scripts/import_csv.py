import sys

from app import create_app
from app.extensions import db
from app.models import Flight
from app.services.csv_import import parse_csv
from app.services.importer import import_rows


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_csv.py <path-to-csv>")
        raise SystemExit(1)

    csv_path = sys.argv[1]
    app = create_app()

    with app.app_context():
        with open(csv_path, "rb") as handle:
            rows, errors = parse_csv(handle)
        booking_sites = sorted(
            {row.get("booking_site") for row in rows if row.get("booking_site")}
        )
        deleted = 0
        if booking_sites:
            deleted = (
                Flight.query.filter(Flight.booking_site.in_(booking_sites)).delete()
            )
            db.session.commit()
        imported = import_rows(rows)

    if booking_sites:
        print(f"Deleted {deleted} flights for booking_site in {booking_sites}.")
    print(f"Imported {imported} flights.")
    if errors:
        print(f"Skipped {len(errors)} rows:")
        for error in errors:
            print(f"- {error}")


if __name__ == "__main__":
    main()
