import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app
from app.extensions import db
from app.models import Flight, FlightHistoryAirNavRadar

def _parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Clear Gemini-based registrations from flight records."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without persisting updates.",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    app = create_app()
    with app.app_context():
        results = {
            "total_histories": 0,
            "skipped_no_flight": 0,
            "skipped_registration_mismatch": 0,
            "cleared_registration": 0,
        }
        cleared_entries = []

        histories = (
            FlightHistoryAirNavRadar.query.filter(
                FlightHistoryAirNavRadar.source.in_(["gemini", "gemini_guess"]),
                FlightHistoryAirNavRadar.aircraft_registration.isnot(None),
            )
            .order_by(FlightHistoryAirNavRadar.dep_date.desc())
            .all()
        )

        for history in histories:
            results["total_histories"] += 1
            flight = history.flight
            if not flight:
                results["skipped_no_flight"] += 1
                continue

            if flight.aircraft_registration != history.aircraft_registration:
                results["skipped_registration_mismatch"] += 1
                continue

            flight.aircraft_registration = None
            results["cleared_registration"] += 1
            cleared_entries.append(
                {
                    "flight_id": flight.id,
                    "registration": history.aircraft_registration,
                    "dep_date": history.dep_date,
                    "source": history.source,
                }
            )

        if args.dry_run or not results["cleared_registration"]:
            db.session.rollback()
        else:
            db.session.commit()

        print("Gemini guess registration cleanup:")
        if args.dry_run:
            print("- dry_run: true")
        for key, value in results.items():
            print(f"- {key}: {value}")
        if args.dry_run and cleared_entries:
            print("Dry run would clear registrations for:")
            for entry in cleared_entries:
                dep_date = entry["dep_date"].isoformat() if entry["dep_date"] else "-"
                print(
                    "- "
                    f"flight={entry['flight_id']} "
                    f"registration={entry['registration']} "
                    f"source={entry['source']} "
                    f"date={dep_date}"
                )


if __name__ == "__main__":
    main()
