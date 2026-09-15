import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from app.services.importer import import_rows
from app.services.tripit_har_import import parse_tripit_har


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("har_path", help="Path to TripIt HAR file")
    parser.add_argument(
        "--source-file",
        help="Override source_file value saved on flights",
    )
    args = parser.parse_args()

    har_path = args.har_path
    source_file = args.source_file or os.path.basename(har_path)

    app = create_app()
    with app.app_context():
        rows, errors = parse_tripit_har(har_path, source_file=source_file)
        imported = import_rows(rows, status="draft")

    print(f"Imported {imported} TripIt HAR flights into inbox.")
    if errors:
        print(f"Skipped {len(errors)} segments:")
        for error in errors:
            print(f"- {error}")


if __name__ == "__main__":
    main()
