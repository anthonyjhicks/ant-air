import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app
from app.extensions import db
from app.models import FlightHistoryAirNavRadar


def _extract_aircraft_type(raw_payload):
    if not isinstance(raw_payload, dict):
        return None
    details = raw_payload.get("details")
    if isinstance(details, dict):
        value = details.get("aircraft_type")
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = raw_payload.get("aircraft_type")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Sync FlightHistoryAirNavRadar.aircraft_type from raw payload values."
        )
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
            "total": 0,
            "skipped_no_payload": 0,
            "skipped_no_payload_type": 0,
            "skipped_same_value": 0,
            "updated": 0,
        }
        updates = []

        histories = FlightHistoryAirNavRadar.query.order_by(
            FlightHistoryAirNavRadar.id.asc()
        ).all()

        for history in histories:
            results["total"] += 1
            raw_payload = history.raw_payload
            if not raw_payload:
                results["skipped_no_payload"] += 1
                continue

            payload_type = _extract_aircraft_type(raw_payload)
            if not payload_type:
                results["skipped_no_payload_type"] += 1
                continue

            if history.aircraft_type == payload_type:
                results["skipped_same_value"] += 1
                continue

            updates.append(
                {
                    "history_id": history.id,
                    "flight_id": history.flight_id,
                    "from_type": history.aircraft_type,
                    "to_type": payload_type,
                }
            )
            history.aircraft_type = payload_type
            results["updated"] += 1

        if args.dry_run or not results["updated"]:
            db.session.rollback()
        else:
            db.session.commit()

        print("Sync AirNavRadar history aircraft_type:")
        if args.dry_run:
            print("- dry_run: true")
        for key, value in results.items():
            print(f"- {key}: {value}")
        if args.dry_run and updates:
            print("Dry run updates:")
            for entry in updates:
                from_type = entry["from_type"] or "-"
                to_type = entry["to_type"] or "-"
                print(
                    "- "
                    f"history={entry['history_id']} "
                    f"flight={entry['flight_id']} "
                    f"aircraft_type={from_type} -> {to_type}"
                )


if __name__ == "__main__":
    main()
