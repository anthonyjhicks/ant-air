"""Backfill flight history from FlightAware AeroAPI.

AeroAPI's ``/flights`` endpoint only covers flights from 10 days ago to 2 days
ahead, so anything older is reported as skipped rather than looked up.
"""
import argparse
import json
import os
import sys
import time
from datetime import date

from sqlalchemy import or_

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app
from app.extensions import db
from app.models import Flight, FlightHistoryAirNavRadar
from app.services.flightaware_history import (
    FlightAwareHistoryError,
    is_within_window,
    normalize_flight_iata,
    record_flightaware_history,
    search_flightaware_history,
)

# AeroAPI's Personal tier allows 10 result sets per minute.
API_CALL_DELAY_SECONDS = 6


def should_process(flight):
    if not flight.airline_code or not flight.flight_number:
        return False
    if not flight.start_date:
        return False
    if flight.start_date > date.today():
        return False
    return True


def already_has_history(flight_id):
    return (
        db.session.query(FlightHistoryAirNavRadar.id)
        .filter(FlightHistoryAirNavRadar.flight_id == flight_id)
        .first()
        is not None
    )


def _flight_idents(flight):
    primary_iata = normalize_flight_iata(flight.airline_code, flight.flight_number)
    operating_iata = normalize_flight_iata(
        flight.operating_airline_code, flight.operating_flight_number
    )
    return primary_iata, operating_iata


def get_processing_decision(flight):
    """
    Determine whether a flight would be looked up or skipped (no API/DB writes).
    Returns (action, reason) where action is 'lookup' or 'skip'.
    """
    if flight.exclude_from_stats:
        return "skip", "excluded_from_stats"
    if not should_process(flight):
        return "skip", "missing_fields_or_future"
    if already_has_history(flight.id):
        return "skip", "existing_history"
    if not is_within_window(flight.start_date):
        return "skip", "outside_flightaware_window"
    primary_iata, operating_iata = _flight_idents(flight)
    if not primary_iata and not operating_iata:
        return "skip", "invalid_flight_iata"
    return "lookup", "would_lookup"


def _fetch_history(flight_iata, dep_date, dep_iata):
    """Return (entry, outcome, payload); outcome is saved, not_found, or error:..."""
    try:
        entry, payload = search_flightaware_history(
            flight_iata, dep_date, dep_iata=dep_iata, include_payload=True
        )
    except FlightAwareHistoryError as exc:
        return None, f"error:flightaware:{exc}", None
    if not entry:
        return None, "not_found", payload
    return entry, "saved", payload


def process_flight(flight, query_cache):
    if flight.exclude_from_stats:
        return "skipped_excluded", False, False
    if not should_process(flight):
        return "skipped_missing_fields", False, False
    if already_has_history(flight.id):
        return "skipped_existing_history", False, False
    if not is_within_window(flight.start_date):
        return "skipped_outside_flightaware_window", False, False

    def _lookup(flight_iata):
        query_key = (flight_iata, flight.start_date)
        cached = query_cache.get(query_key)
        if cached:
            return cached["outcome"], False, True, cached.get("entry")

        entry, outcome, payload = _fetch_history(
            flight_iata, flight.start_date, dep_iata=flight.start_airport
        )
        if outcome == "not_found" and payload:
            print("[not_found] FlightAware payload:")
            print(json.dumps(payload, sort_keys=True))
        query_cache[query_key] = {"outcome": outcome, "entry": entry}
        return outcome, True, False, entry

    primary_iata, operating_iata = _flight_idents(flight)
    if not primary_iata and not operating_iata:
        return "skipped_invalid_flight_iata", False, False

    entry = None
    used_api = False
    cache_hit = False
    outcome = "not_found"
    idents = [ident for ident in (primary_iata, operating_iata) if ident]
    for ident in dict.fromkeys(idents):
        outcome, ident_used_api, ident_cache_hit, entry = _lookup(ident)
        used_api = used_api or ident_used_api
        cache_hit = cache_hit or ident_cache_hit
        if outcome == "saved":
            break

    if outcome != "saved":
        return outcome, used_api, cache_hit

    record_flightaware_history(flight, entry)
    db.session.commit()
    return "saved", used_api, cache_hit


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Backfill flight history from FlightAware AeroAPI (last 10 days only)."
    )
    parser.add_argument(
        "limit",
        nargs="?",
        type=int,
        help="Optional limit on number of flights to process.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report which flights would be looked up vs skipped; no API calls or DB writes.",
    )
    parser.add_argument(
        "--missing-registration-only",
        action="store_true",
        help="Only consider flights that have no aircraft_registration (look up only those).",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=1,
        metavar="N",
        help="1-based index to start at (e.g. 50 to skip the first 49 flights). Default 1.",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    limit = args.limit
    dry_run = args.dry_run
    missing_registration_only = args.missing_registration_only
    start_index = max(1, args.start)

    app = create_app()
    with app.app_context():
        query = (
            Flight.query.filter(Flight.start_date <= date.today())
            .order_by(Flight.start_date.desc(), Flight.id.desc())
        )
        if missing_registration_only:
            query = query.filter(
                or_(
                    Flight.aircraft_registration.is_(None),
                    Flight.aircraft_registration == "",
                )
            )
        if start_index > 1:
            query = query.offset(start_index - 1)
        if limit:
            query = query.limit(limit)
        flights = query.all()

        if start_index > 1 and flights:
            print(f"Starting from position {start_index} (skipped first {start_index - 1} flights).\n")

        if dry_run:
            print(
                "DRY RUN: no API calls or DB writes. "
                + ("(missing-registration-only)\n" if missing_registration_only else "\n")
            )
            results = {}
            for index, flight in enumerate(flights, start=1):
                action, reason = get_processing_decision(flight)
                key = f"{action}:{reason}"
                results[key] = results.get(key, 0) + 1
                reg = (flight.aircraft_registration or "").strip() or "—"
                print(
                    f"[{index}/{len(flights)}] Flight {flight.id} "
                    f"{flight.airline_code or ''}{flight.flight_number or ''} "
                    f"{flight.start_date} reg={reg} -> {action}: {reason}"
                )
            print("Summary:")
            for key in sorted(results.keys()):
                print(f"- {key}: {results[key]}")
            lookup_total = sum(v for k, v in results.items() if k.startswith("lookup:"))
            skip_total = sum(v for k, v in results.items() if k.startswith("skip:"))
            print(f"- total would_lookup: {lookup_total}")
            print(f"- total would_skip: {skip_total}")
            return

        results = {}
        cache_hits = 0
        query_cache = {}
        for index, flight in enumerate(flights, start=1):
            outcome, used_api, cache_hit = process_flight(flight, query_cache)
            results[outcome] = results.get(outcome, 0) + 1
            if cache_hit:
                cache_hits += 1
            print(
                f"[{index}/{len(flights)}] Flight {flight.id} "
                f"{flight.airline_code or ''}{flight.flight_number or ''} "
                f"{flight.start_date} -> {outcome}"
            )
            if used_api:
                time.sleep(API_CALL_DELAY_SECONDS)

    print("Summary:")
    for key, value in sorted(results.items()):
        print(f"- {key}: {value}")
    print(f"- cache_hits: {cache_hits}")


if __name__ == "__main__":
    main()
