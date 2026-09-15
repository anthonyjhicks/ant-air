import argparse
import json
import os
import sys
import time
from datetime import date

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
from app.services.gemini_codeshare import (
    GeminiCodeshareError,
    lookup_codeshare_details,
    lookup_route_aircraft_type,
)

REGISTRATION_CONFIDENCE_MIN = 0.7


def _already_has_history(flight_id):
    return (
        db.session.query(FlightHistoryAirNavRadar.id)
        .filter(FlightHistoryAirNavRadar.flight_id == flight_id)
        .first()
        is not None
    )


def _base_should_process(flight):
    if flight.exclude_from_stats:
        return False
    if flight.aircraft:
        return False
    if _already_has_history(flight.id):
        return False
    if not flight.start_date or flight.start_date > date.today():
        return False
    return True


def _base_should_process_registration(flight):
    if flight.exclude_from_stats:
        return False
    if flight.aircraft_registration:
        return False
    if not flight.start_date or flight.start_date > date.today():
        return False
    return True


def _should_process_codeshare(flight):
    if not _base_should_process(flight):
        return False
    if not flight.airline_code or not flight.flight_number:
        return False
    return True


def _should_process_route_guess(flight):
    if not _base_should_process(flight):
        return False
    if not flight.airline_code or flight.flight_number:
        return False
    if not flight.start_airport or not flight.end_airport:
        return False
    return True


def _should_process_registration(flight):
    if not _base_should_process_registration(flight):
        return False
    if not flight.airline_code:
        return False
    if not flight.flight_number and (not flight.start_airport or not flight.end_airport):
        return False
    return True


def _get_registration_confidence(details):
    if not details:
        return None
    try:
        return float(details.get("registration_confidence"))
    except (TypeError, ValueError):
        return None


def _should_accept_registration(flight, details):
    if not details:
        return False
    if not (flight.flight_number and flight.start_date):
        return False
    if not (flight.start_airport and flight.end_airport):
        return False
    confidence = _get_registration_confidence(details)
    return confidence is not None and confidence >= REGISTRATION_CONFIDENCE_MIN


def _skip_reason(flight):
    if flight.exclude_from_stats:
        return "skipped_excluded"
    if flight.aircraft:
        return "skipped_has_aircraft"
    if _already_has_history(flight.id):
        return "skipped_has_history"
    if not flight.start_date:
        return "skipped_missing_date"
    if flight.start_date > date.today():
        return "skipped_future_date"
    if not flight.airline_code:
        return "skipped_missing_airline"
    if flight.flight_number:
        return "skipped_unhandled_state"
    if not flight.start_airport or not flight.end_airport:
        return "skipped_missing_route"
    return "skipped_unhandled_state"


def _skip_reason_registration(flight):
    if flight.exclude_from_stats:
        return "skipped_excluded"
    if flight.aircraft_registration:
        return "skipped_has_registration"
    if not flight.start_date:
        return "skipped_missing_date"
    if flight.start_date > date.today():
        return "skipped_future_date"
    if not flight.airline_code:
        return "skipped_missing_airline"
    if not flight.flight_number and (
        not flight.start_airport or not flight.end_airport
    ):
        return "skipped_missing_route"
    return "skipped_unhandled_state"


def _save_gemini_history(
    flight,
    details,
    debug,
    applied_fields,
    source="gemini",
    accepted_registration=None,
    registration_confidence=None,
):
    reasoning = None
    if details and isinstance(details, dict):
        reasoning = details.get("reasoning")
    if not reasoning and debug and isinstance(debug, dict):
        response = debug.get("response")
        if isinstance(response, dict):
            reasoning = response.get("text")
    history = FlightHistoryAirNavRadar(
        flight_id=flight.id,
        dep_date=flight.start_date,
        source=source,
        aircraft_type=details.get("aircraft_type"),
        aircraft_registration=accepted_registration,
        airline_iata=details.get("operating_airline_code") or flight.airline_code,
        flight_number_iata=details.get("operating_flight_number"),
        raw_payload={
            "details": details,
            "request": debug.get("request") if debug else None,
            "response": debug.get("response") if debug else None,
            "reasoning": reasoning,
            "accepted_registration": accepted_registration,
            "registration_confidence": registration_confidence,
            "applied_fields": applied_fields,
        },
    )
    db.session.add(history)


def _refresh_flightaware_history(flight):
    lookup_airline = flight.operating_airline_code or flight.airline_code
    lookup_number = flight.operating_flight_number or flight.flight_number
    flight_iata = normalize_flight_iata(lookup_airline, lookup_number)
    if not flight_iata:
        return "skipped_invalid_flight_iata"
    if not flight.start_date:
        return "skipped_missing_date"
    if not is_within_window(flight.start_date):
        return "skipped_outside_flightaware_window"
    try:
        entry = search_flightaware_history(
            flight_iata, flight.start_date, dep_iata=flight.start_airport
        )
    except FlightAwareHistoryError as exc:
        return f"error_flightaware:{exc}"
    if not entry:
        return "not_found"

    record_flightaware_history(flight, entry)
    return "saved"


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Backfill aircraft and codeshare via Gemini."
    )
    parser.add_argument(
        "limit",
        nargs="?",
        type=int,
        help="Optional limit on number of flights to process.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=3.0,
        help="Seconds to sleep between Gemini requests.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Retries per flight when rate limited.",
    )
    parser.add_argument(
        "--retry-sleep",
        type=float,
        default=20.0,
        help="Seconds to sleep before retrying a rate-limited flight.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show updates without saving.",
    )
    parser.add_argument(
        "--only-missing-aircraft",
        action="store_true",
        help="Only consider flights missing aircraft.",
    )
    parser.add_argument(
        "--only-missing-aircraft-with-airline",
        action="store_true",
        help="Only missing aircraft flights that have an airline code.",
    )
    parser.add_argument(
        "--only-missing-registration",
        action="store_true",
        help="Only consider flights missing aircraft registration.",
    )
    parser.add_argument(
        "--only-missing-registration-with-route",
        action="store_true",
        help="Missing registration flights with airline and route.",
    )
    parser.add_argument(
        "--refresh-gemini-guess-reasoning",
        action="store_true",
        help="Refresh Gemini guess history entries with reasoning.",
    )
    parser.add_argument(
        "--refresh-gemini-codeshare-history",
        action="store_true",
        help="Re-run Gemini codeshare lookups and refresh history entries.",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    app = create_app()
    with app.app_context():
        if args.refresh_gemini_guess_reasoning:
            results = {}
            histories = (
                FlightHistoryAirNavRadar.query.filter(
                    FlightHistoryAirNavRadar.source == "gemini_guess"
                )
                .order_by(
                    FlightHistoryAirNavRadar.dep_date.desc(),
                    FlightHistoryAirNavRadar.id.desc(),
                )
            )
            if args.limit:
                histories = histories.limit(args.limit)
            histories = histories.all()
            for index, history in enumerate(histories, start=1):
                flight = history.flight
                if not flight:
                    results["skipped_missing_flight"] = (
                        results.get("skipped_missing_flight", 0) + 1
                    )
                    continue
                if (
                    not flight.airline_code
                    or not flight.start_airport
                    or not flight.end_airport
                    or not history.dep_date
                ):
                    results["skipped_missing_context"] = (
                        results.get("skipped_missing_context", 0) + 1
                    )
                    continue

                try:
                    details = debug = None
                    for attempt in range(args.retries + 1):
                        try:
                            details, debug = lookup_route_aircraft_type(
                                flight.airline_code,
                                flight.start_airport,
                                flight.end_airport,
                                history.dep_date,
                            )
                            break
                        except GeminiCodeshareError as exc:
                            message = str(exc).lower()
                            if (
                                "rate limit" in message
                                or "quota" in message
                                or "429" in message
                            ) and attempt < args.retries:
                                time.sleep(args.retry_sleep)
                                continue
                            raise
                except GeminiCodeshareError as exc:
                    outcome = f"error_gemini_guess:{exc}"
                    results[outcome] = results.get(outcome, 0) + 1
                    print(
                        f"[{index}/{len(histories)}] "
                        f"History {history.id} -> {outcome}"
                    )
                    time.sleep(args.sleep)
                    continue

                aircraft_type = details.get("aircraft_type") if details else None
                aircraft_registration = (
                    details.get("aircraft_registration") if details else None
                )
                registration_confidence = _get_registration_confidence(details)
                accept_registration = _should_accept_registration(flight, details)
                registration_confidence = _get_registration_confidence(details)
                accept_registration = _should_accept_registration(flight, details)
                if not aircraft_type and not aircraft_registration:
                    results["guess_not_found"] = results.get("guess_not_found", 0) + 1
                    print(
                        f"[{index}/{len(histories)}] "
                        f"History {history.id} -> guess_not_found"
                    )
                    time.sleep(args.sleep)
                    continue

                raw_payload = history.raw_payload or {}
                raw_payload.update(
                    {
                        "details": details,
                        "request": debug.get("request") if debug else None,
                        "response": debug.get("response") if debug else None,
                        "reasoning": (
                            debug.get("response", {}).get("text")
                            if isinstance(debug, dict)
                            else None
                        ),
                        "accepted_registration": (
                            aircraft_registration if accept_registration else None
                        ),
                        "registration_confidence": registration_confidence,
                        "refreshed_at": time.strftime(
                            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                        ),
                    }
                )
                history.raw_payload = raw_payload
                if aircraft_type:
                    history.aircraft_type = aircraft_type
                if accept_registration and aircraft_registration:
                    history.aircraft_registration = aircraft_registration

                if args.dry_run:
                    db.session.rollback()
                else:
                    db.session.commit()

                results["refreshed"] = results.get("refreshed", 0) + 1
                print(
                    f"[{index}/{len(histories)}] "
                    f"History {history.id} -> refreshed"
                )
                time.sleep(args.sleep)

            print("Summary:")
            for key, value in sorted(results.items()):
                print(f"- {key}: {value}")
            return

        if args.refresh_gemini_codeshare_history:
            results = {}
            histories = (
                FlightHistoryAirNavRadar.query.filter(
                    FlightHistoryAirNavRadar.source == "gemini"
                )
                .order_by(
                    FlightHistoryAirNavRadar.dep_date.desc(),
                    FlightHistoryAirNavRadar.id.desc(),
                )
            )
            if args.limit:
                histories = histories.limit(args.limit)
            histories = histories.all()
            for index, history in enumerate(histories, start=1):
                flight = history.flight
                if not flight:
                    results["skipped_missing_flight"] = (
                        results.get("skipped_missing_flight", 0) + 1
                    )
                    continue
                if not flight.airline_code or not flight.flight_number:
                    results["skipped_missing_context"] = (
                        results.get("skipped_missing_context", 0) + 1
                    )
                    continue

                try:
                    details = debug = None
                    for attempt in range(args.retries + 1):
                        try:
                            details, debug = lookup_codeshare_details(
                                flight.airline_code,
                                flight.flight_number,
                                dep_date=flight.start_date,
                                dep_iata=flight.start_airport,
                                arr_iata=flight.end_airport,
                            )
                            break
                        except GeminiCodeshareError as exc:
                            message = str(exc).lower()
                            if (
                                "rate limit" in message
                                or "quota" in message
                                or "429" in message
                            ) and attempt < args.retries:
                                time.sleep(args.retry_sleep)
                                continue
                            raise
                except GeminiCodeshareError as exc:
                    outcome = f"error_gemini:{exc}"
                    results[outcome] = results.get(outcome, 0) + 1
                    print(
                        f"[{index}/{len(histories)}] "
                        f"History {history.id} -> {outcome}"
                    )
                    time.sleep(args.sleep)
                    continue

                if not details:
                    results["not_found"] = results.get("not_found", 0) + 1
                    print(
                        f"[{index}/{len(histories)}] "
                        f"History {history.id} -> not_found"
                    )
                    time.sleep(args.sleep)
                    continue

                applied_fields = []
                aircraft_type = details.get("aircraft_type")
                if aircraft_type and flight.aircraft != aircraft_type:
                    flight.aircraft = aircraft_type
                    applied_fields.append("aircraft")

                operating_airline_code = details.get("operating_airline_code")
                operating_flight_number = details.get("operating_flight_number")
                if operating_airline_code and operating_flight_number:
                    if (
                        flight.operating_airline_code != operating_airline_code
                        or flight.operating_flight_number != operating_flight_number
                    ):
                        flight.operating_airline_code = operating_airline_code
                        flight.operating_flight_number = operating_flight_number
                        applied_fields.extend(
                            ["operating_airline_code", "operating_flight_number"]
                        )

                reasoning = None
                if isinstance(details, dict):
                    reasoning = details.get("reasoning")
                if not reasoning and isinstance(debug, dict):
                    reasoning = debug.get("response", {}).get("text")

                raw_payload = history.raw_payload or {}
                raw_payload.update(
                    {
                        "details": details,
                        "request": debug.get("request") if debug else None,
                        "response": debug.get("response") if debug else None,
                        "reasoning": reasoning,
                        "applied_fields": applied_fields,
                        "refreshed_at": time.strftime(
                            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                        ),
                    }
                )
                history.raw_payload = raw_payload
                history.aircraft_type = aircraft_type
                history.airline_iata = (
                    operating_airline_code or flight.airline_code
                )
                history.flight_number_iata = operating_flight_number

                if args.dry_run:
                    db.session.rollback()
                else:
                    db.session.commit()

                results["refreshed"] = results.get("refreshed", 0) + 1
                print(
                    f"[{index}/{len(histories)}] "
                    f"History {history.id} -> refreshed"
                )
                time.sleep(args.sleep)

            print("Summary:")
            for key, value in sorted(results.items()):
                print(f"- {key}: {value}")
            return

        query = (
            Flight.query.filter(Flight.start_date <= date.today())
            .order_by(Flight.start_date.desc(), Flight.id.desc())
        )
        if args.only_missing_aircraft:
            query = query.filter(Flight.aircraft.is_(None))
        if args.only_missing_aircraft_with_airline:
            query = query.filter(
                Flight.aircraft.is_(None), Flight.airline_code.isnot(None)
            )
        if args.only_missing_registration:
            query = query.filter(Flight.aircraft_registration.is_(None))
        if args.only_missing_registration_with_route:
            query = query.filter(
                Flight.aircraft_registration.is_(None),
                Flight.airline_code.isnot(None),
                Flight.start_airport.isnot(None),
                Flight.end_airport.isnot(None),
            )
        if args.limit:
            query = query.limit(args.limit)
        flights = query.all()

        results = {}
        guess_summaries = []
        for index, flight in enumerate(flights, start=1):
            if args.only_missing_registration or args.only_missing_registration_with_route:
                if not _should_process_registration(flight):
                    results["skipped"] = results.get("skipped", 0) + 1
                    reason = _skip_reason_registration(flight)
                    results[reason] = results.get(reason, 0) + 1
                    print(
                        f"[{index}/{len(flights)}] Flight {flight.id} -> {reason}"
                    )
                    continue

                details = debug = None
                try:
                    for attempt in range(args.retries + 1):
                        try:
                            if flight.flight_number:
                                details, debug = lookup_codeshare_details(
                                    flight.airline_code,
                                    flight.flight_number,
                                    dep_date=flight.start_date,
                                    dep_iata=flight.start_airport,
                                    arr_iata=flight.end_airport,
                                )
                            else:
                                details, debug = lookup_route_aircraft_type(
                                    flight.airline_code,
                                    flight.start_airport,
                                    flight.end_airport,
                                    flight.start_date,
                                )
                            break
                        except GeminiCodeshareError as exc:
                            message = str(exc).lower()
                            if (
                                "rate limit" in message
                                or "quota" in message
                                or "429" in message
                            ) and attempt < args.retries:
                                time.sleep(args.retry_sleep)
                                continue
                            raise
                except GeminiCodeshareError as exc:
                    outcome = f"error_gemini_registration:{exc}"
                    results[outcome] = results.get(outcome, 0) + 1
                    print(
                        f"[{index}/{len(flights)}] Flight {flight.id} -> {outcome}"
                    )
                    time.sleep(args.sleep)
                    continue

                if not details:
                    results["registration_not_found"] = (
                        results.get("registration_not_found", 0) + 1
                    )
                    print(
                        f"[{index}/{len(flights)}] Flight {flight.id} -> registration_not_found"
                    )
                    time.sleep(args.sleep)
                    continue

                applied_fields = []
                aircraft_type = details.get("aircraft_type")
                aircraft_registration = details.get("aircraft_registration")
                registration_confidence = _get_registration_confidence(details)
                accept_registration = _should_accept_registration(flight, details)
                if aircraft_type and not flight.aircraft:
                    flight.aircraft = aircraft_type
                    applied_fields.append("aircraft")
                if (
                    accept_registration
                    and aircraft_registration
                    and not flight.aircraft_registration
                ):
                    flight.aircraft_registration = aircraft_registration
                    applied_fields.append("aircraft_registration")

                operating_airline_code = details.get("operating_airline_code")
                operating_flight_number = details.get("operating_flight_number")
                if operating_airline_code and operating_flight_number:
                    if (
                        flight.operating_airline_code != operating_airline_code
                        or flight.operating_flight_number != operating_flight_number
                    ):
                        flight.operating_airline_code = operating_airline_code
                        flight.operating_flight_number = operating_flight_number
                        applied_fields.extend(
                            ["operating_airline_code", "operating_flight_number"]
                        )

                if not applied_fields:
                    results["registration_no_updates"] = results.get(
                        "registration_no_updates", 0
                    ) + 1
                    print(
                        f"[{index}/{len(flights)}] Flight {flight.id} -> registration_no_updates"
                    )
                    time.sleep(args.sleep)
                    continue

                if not args.dry_run:
                    _save_gemini_history(
                        flight,
                        details,
                        debug,
                        applied_fields,
                        source=details.get("source") or "gemini",
                        accepted_registration=(
                            aircraft_registration if accept_registration else None
                        ),
                        registration_confidence=registration_confidence,
                    )

                if args.dry_run:
                    db.session.rollback()
                else:
                    db.session.commit()

                results["registration_updated"] = results.get(
                    "registration_updated", 0
                ) + 1
                print(
                    f"[{index}/{len(flights)}] Flight {flight.id} -> registration_updated"
                )
                time.sleep(args.sleep)
                continue

            if _should_process_codeshare(flight):
                try:
                    details = debug = None
                    for attempt in range(args.retries + 1):
                        try:
                            details, debug = lookup_codeshare_details(
                                flight.airline_code,
                                flight.flight_number,
                                dep_date=flight.start_date,
                                dep_iata=flight.start_airport,
                                arr_iata=flight.end_airport,
                            )
                            break
                        except GeminiCodeshareError as exc:
                            message = str(exc).lower()
                            if (
                                "rate limit" in message
                                or "quota" in message
                                or "429" in message
                            ) and attempt < args.retries:
                                time.sleep(args.retry_sleep)
                                continue
                            raise
                except GeminiCodeshareError as exc:
                    outcome = f"error_gemini:{exc}"
                    results[outcome] = results.get(outcome, 0) + 1
                    print(
                        f"[{index}/{len(flights)}] Flight {flight.id} -> {outcome}"
                    )
                    time.sleep(args.sleep)
                    continue

                if not details:
                    results["not_found"] = results.get("not_found", 0) + 1
                    print(
                        f"[{index}/{len(flights)}] Flight {flight.id} -> not_found"
                    )
                    time.sleep(args.sleep)
                    continue

                applied_fields = []
                added_operator = False

                aircraft_type = details.get("aircraft_type")
                aircraft_registration = details.get("aircraft_registration")
                registration_confidence = _get_registration_confidence(details)
                accept_registration = _should_accept_registration(flight, details)
                if aircraft_type and not flight.aircraft:
                    flight.aircraft = aircraft_type
                    applied_fields.append("aircraft")
                if (
                    accept_registration
                    and aircraft_registration
                    and not flight.aircraft_registration
                ):
                    flight.aircraft_registration = aircraft_registration
                    applied_fields.append("aircraft_registration")

                operating_airline_code = details.get("operating_airline_code")
                operating_flight_number = details.get("operating_flight_number")
                if operating_airline_code and operating_flight_number:
                    if (
                        flight.operating_airline_code != operating_airline_code
                        or flight.operating_flight_number != operating_flight_number
                    ):
                        flight.operating_airline_code = operating_airline_code
                        flight.operating_flight_number = operating_flight_number
                        applied_fields.extend(
                            ["operating_airline_code", "operating_flight_number"]
                        )
                        added_operator = True

                if not applied_fields:
                    results["no_updates"] = results.get("no_updates", 0) + 1
                    print(
                        f"[{index}/{len(flights)}] Flight {flight.id} -> no_updates"
                    )
                    time.sleep(args.sleep)
                    continue

                if not args.dry_run:
                    _save_gemini_history(
                        flight,
                        details,
                        debug,
                        applied_fields,
                        accepted_registration=(
                            aircraft_registration if accept_registration else None
                        ),
                        registration_confidence=registration_confidence,
                    )

                refresh_outcome = None
                if added_operator:
                    refresh_outcome = _refresh_flightaware_history(flight)

                if args.dry_run:
                    db.session.rollback()
                else:
                    db.session.commit()

                outcome = "updated"
                results[outcome] = results.get(outcome, 0) + 1
                refresh_label = (
                    f" refresh={refresh_outcome}" if refresh_outcome else ""
                )
                print(
                    f"[{index}/{len(flights)}] Flight {flight.id} -> {outcome}"
                    f"{refresh_label}"
                )
                time.sleep(args.sleep)
                continue

            if _should_process_route_guess(flight):
                try:
                    details = debug = None
                    for attempt in range(args.retries + 1):
                        try:
                            details, debug = lookup_route_aircraft_type(
                                flight.airline_code,
                                flight.start_airport,
                                flight.end_airport,
                                flight.start_date,
                            )
                            break
                        except GeminiCodeshareError as exc:
                            message = str(exc).lower()
                            if (
                                "rate limit" in message
                                or "quota" in message
                                or "429" in message
                            ) and attempt < args.retries:
                                time.sleep(args.retry_sleep)
                                continue
                            raise
                except GeminiCodeshareError as exc:
                    outcome = f"error_gemini_guess:{exc}"
                    results[outcome] = results.get(outcome, 0) + 1
                    print(
                        f"[{index}/{len(flights)}] Flight {flight.id} -> {outcome}"
                    )
                    time.sleep(args.sleep)
                    continue

                aircraft_type = details.get("aircraft_type") if details else None
                aircraft_registration = (
                    details.get("aircraft_registration") if details else None
                )
                if not aircraft_type and not aircraft_registration:
                    results["guess_not_found"] = results.get("guess_not_found", 0) + 1
                    print(
                        f"[{index}/{len(flights)}] Flight {flight.id} -> guess_not_found"
                    )
                    time.sleep(args.sleep)
                    continue

                applied_fields = []
                if not flight.aircraft:
                    if aircraft_type:
                        flight.aircraft = aircraft_type
                        applied_fields.append("aircraft")
                if (
                    accept_registration
                    and aircraft_registration
                    and not flight.aircraft_registration
                ):
                    flight.aircraft_registration = aircraft_registration
                    applied_fields.append("aircraft_registration")

                if not applied_fields:
                    results["guess_no_updates"] = results.get(
                        "guess_no_updates", 0
                    ) + 1
                    print(
                        f"[{index}/{len(flights)}] Flight {flight.id} -> guess_no_updates"
                    )
                    time.sleep(args.sleep)
                    continue

                if not args.dry_run:
                    _save_gemini_history(
                        flight,
                        details,
                        debug,
                        applied_fields,
                        source="gemini_guess",
                        accepted_registration=(
                            aircraft_registration if accept_registration else None
                        ),
                        registration_confidence=registration_confidence,
                    )

                if args.dry_run:
                    db.session.rollback()
                else:
                    db.session.commit()

                outcome = "guess_updated"
                results[outcome] = results.get(outcome, 0) + 1
                guess_summaries.append(
                    {
                        "flight_id": flight.id,
                        "aircraft_type": aircraft_type,
                        "aircraft_registration": aircraft_registration,
                        "airline_code": flight.airline_code,
                        "start_airport": flight.start_airport,
                        "end_airport": flight.end_airport,
                        "start_date": flight.start_date.isoformat()
                        if flight.start_date
                        else None,
                        "scope": details.get("scope") if details else None,
                    }
                )
                print(
                    f"[{index}/{len(flights)}] Flight {flight.id} -> {outcome}"
                )
                time.sleep(args.sleep)
                continue

            results["skipped"] = results.get("skipped", 0) + 1
            reason = _skip_reason(flight)
            results[reason] = results.get(reason, 0) + 1
            print(f"[{index}/{len(flights)}] Flight {flight.id} -> {reason}")

    print("Summary:")
    for key, value in sorted(results.items()):
        print(f"- {key}: {value}")
    if guess_summaries:
        print("Gemini guess suggestions:")
        for entry in guess_summaries:
            route = f"{entry['start_airport']}-{entry['end_airport']}"
            airline = entry["airline_code"] or "-"
            scope = entry["scope"] or "-"
            registration = entry.get("aircraft_registration") or "-"
            print(
                "- "
                f"flight={entry['flight_id']} "
                f"aircraft={entry['aircraft_type']} "
                f"registration={registration} "
                f"airline={airline} "
                f"route={route} "
                f"date={entry['start_date']} "
                f"scope={scope}"
            )


if __name__ == "__main__":
    main()
