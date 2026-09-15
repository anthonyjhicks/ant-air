import argparse
import io
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from app.extensions import db
from app.models import Flight
from app.services.csv_import import parse_csv
from app.services.flightpath_import import parse_flightpath_csv
from app.services.gflights_import import parse_gflights_csv
from app.services.importer import import_rows


def load_csv(path):
    with open(path, "rb") as handle:
        return io.BytesIO(handle.read())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--import-dir",
        default=os.path.join(os.path.dirname(os.path.dirname(__file__)), "import"),
        help="Directory containing tripit.csv, gflights_v2.csv, baflightpath_v2.csv",
    )
    parser.add_argument(
        "--no-geocode",
        action="store_true",
        help="Skip geocoding cities to countries/coordinates for baflightpath",
    )
    args = parser.parse_args()

    import_dir = args.import_dir
    tripit_path = os.path.join(import_dir, "tripit.csv")
    gflights_path = os.path.join(import_dir, "gflights_v2.csv")
    baflightpath_path = os.path.join(import_dir, "baflightpath_v2.csv")

    for path in (tripit_path, gflights_path, baflightpath_path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing import file: {path}")

    app = create_app()
    with app.app_context():
        deleted = Flight.query.delete()
        db.session.commit()
        print(f"Deleted {deleted} flights.")

        tripit_rows, tripit_errors = parse_csv(
            load_csv(tripit_path),
            date_formats=["%m/%d/%Y"],
            source_file="tripit.csv",
        )
        tripit_imported = import_rows(tripit_rows)

        gflights_rows, gflights_errors = parse_gflights_csv(
            load_csv(gflights_path),
            date_formats=["%d/%m/%Y"],
            source_file="gflights",
        )
        gflights_imported = import_rows(gflights_rows)

        baflight_rows, baflight_errors = parse_flightpath_csv(
            load_csv(baflightpath_path),
            geocode=False,
            date_formats=["%d/%m/%Y"],
            source_file="baflightpath.csv",
        )
        baflight_imported = import_rows(baflight_rows)

    print(f"Imported {tripit_imported} TripIt flights.")
    if tripit_errors:
        print(f"Skipped {len(tripit_errors)} TripIt rows:")
        for error in tripit_errors:
            print(f"- {error}")

    print(f"Imported {gflights_imported} GFlights flights.")
    if gflights_errors:
        print(f"Skipped {len(gflights_errors)} GFlights rows:")
        for error in gflights_errors:
            print(f"- {error}")

    print(f"Imported {baflight_imported} BA Flightpath flights.")
    if baflight_errors:
        print(f"Skipped {len(baflight_errors)} BA Flightpath rows:")
        for error in baflight_errors:
            print(f"- {error}")


if __name__ == "__main__":
    main()
