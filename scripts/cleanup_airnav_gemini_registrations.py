#!/usr/bin/env python

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app
from app.extensions import db
from app.models import FlightHistoryAirNavRadar


def _parse_args():
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Clear flight registrations sourced from gemini AirNav history."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report changes without persisting updates.",
    )
    return parser.parse_args()


def _clean(value):
    if not value:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return value


def _extract_details(payload):
    if not isinstance(payload, dict):
        return None
    details = payload.get("details")
    if isinstance(details, dict):
        return details
    return None


def _extract_applied_fields(payload):
    if not isinstance(payload, dict):
        return None
    applied_fields = payload.get("applied_fields")
    if isinstance(applied_fields, list):
        return applied_fields
    return None


def main():
    args = _parse_args()
    app = create_app()
    with app.app_context():
        results = {
            "total_histories": 0,
            "skipped_no_flight": 0,
            "skipped_no_details": 0,
            "skipped_no_suggested": 0,
            "skipped_not_applied": 0,
            "skipped_trusted_airnav": 0,
            "skipped_registration_mismatch": 0,
            "cleared_registration": 0,
        }
        entries = []

        trusted_flight_ids = {
            row.flight_id
            for row in FlightHistoryAirNavRadar.query.filter(
                FlightHistoryAirNavRadar.aircraft_registration.isnot(None),
                FlightHistoryAirNavRadar.source.isnot(None),
                FlightHistoryAirNavRadar.source.notin_(["gemini", "gemini_guess"]),
            )
            .with_entities(FlightHistoryAirNavRadar.flight_id)
            .distinct()
            .all()
        }

        histories = (
            FlightHistoryAirNavRadar.query.order_by(
                FlightHistoryAirNavRadar.created_at.desc(),
                FlightHistoryAirNavRadar.id.desc(),
            ).all()
        )

        seen_flights = set()
        for history in histories:
            if history.flight_id in seen_flights:
                continue
            seen_flights.add(history.flight_id)
            results["total_histories"] += 1

            flight = history.flight
            if not flight:
                results["skipped_no_flight"] += 1
                continue

            details = _extract_details(history.raw_payload)
            if not details:
                results["skipped_no_details"] += 1
                continue

            source = _clean(details.get("source")) or _clean(history.source)
            if source not in ("gemini", "gemini_guess"):
                continue

            suggested = _clean(details.get("aircraft_registration"))
            if not suggested:
                results["skipped_no_suggested"] += 1
                continue

            applied_fields = _extract_applied_fields(history.raw_payload)
            if applied_fields is not None and "aircraft_registration" not in applied_fields:
                results["skipped_not_applied"] += 1
                continue

            if history.flight_id in trusted_flight_ids:
                results["skipped_trusted_airnav"] += 1
                continue

            current = _clean(flight.aircraft_registration)
            would_clear = current == suggested
            if not would_clear:
                results["skipped_registration_mismatch"] += 1

            entries.append(
                {
                    "flight_id": flight.id,
                    "source": source,
                    "suggested": suggested,
                    "current": current,
                    "would_clear": would_clear,
                }
            )

            if would_clear:
                flight.aircraft_registration = None
                results["cleared_registration"] += 1

        if args.dry_run or not results["cleared_registration"]:
            db.session.rollback()
        else:
            db.session.commit()

        print("AirNav gemini registration cleanup:")
        if args.dry_run:
            print("- dry_run: true")
        for key, value in results.items():
            print(f"- {key}: {value}")
        if args.dry_run and entries:
            print("Dry run entries:")
            for index, entry in enumerate(entries, start=1):
                status = "clear" if entry["would_clear"] else "skip"
                print(
                    "- "
                    f"count={index} "
                    f"flight={entry['flight_id']} "
                    f"source={entry['source']} "
                    f"suggested={entry['suggested']} "
                    f"current={entry['current'] or '-'} "
                    f"action={status}"
                )


if __name__ == "__main__":
    main()
