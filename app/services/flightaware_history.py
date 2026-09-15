"""FlightAware AeroAPI v4 client.

This is the app's only flight-tracking provider. It uses the
``GET /flights/{ident}`` endpoint, which on the Personal tier only returns
flights scheduled between 10 days ago and 2 days ahead. Older flights would
need the paid ``/history`` endpoints, which this module does not call.

API reference: https://www.flightaware.com/aeroapi/portal/documentation
"""
import json
from datetime import datetime, time, timedelta, timezone
from urllib import parse, request
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import current_app

from ..extensions import db
from ..models import FlightHistoryAirNavRadar
from .aircraft_types import apply_aircraft_to_flight
from .airlines import lookup_airline_name

SOURCE = "flightaware"
DEFAULT_BASE_URL = "https://aeroapi.flightaware.com/aeroapi"
LOOKBACK_DAYS = 10
LOOKAHEAD_DAYS = 2
REQUEST_TIMEOUT = 20
# Keeps the clamped query window inside AeroAPI's limits despite request
# latency and clock skew between this host and FlightAware.
_WINDOW_MARGIN = timedelta(hours=1)


class FlightAwareHistoryError(Exception):
    """The AeroAPI request failed or the integration is not configured.

    ``status_code`` carries the HTTP status when the failure came from AeroAPI.
    """

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class FlightAwareWindowError(FlightAwareHistoryError):
    """The departure date is outside the window AeroAPI will search."""


def is_configured():
    """Whether an AeroAPI key is available in the app config."""
    return bool(current_app.config.get("FLIGHTAWARE_API_KEY"))


def _normalize_code(value):
    if not value:
        return ""
    return str(value).strip().replace(" ", "").upper()


def normalize_flight_iata(airline_code, flight_number):
    """Combine an airline code and flight number into an ident such as ``BA117``."""
    airline = _normalize_code(airline_code)
    number = _normalize_code(flight_number)
    if not airline or not number:
        return ""
    if number.startswith(airline):
        return number
    return f"{airline}{number}"


def _parse_datetime(value):
    """Parse an AeroAPI ISO-8601 timestamp into a naive UTC datetime."""
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.replace(tzinfo=None)


def _iso_z(value):
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _airport_field(entry, side, key):
    airport = entry.get(side)
    if isinstance(airport, dict):
        return airport.get(key)
    return None


def _departure_dates(entry):
    """Return (local date, UTC date) of the scheduled departure.

    AeroAPI timestamps are UTC; the local date uses the origin airport's
    timezone so that a late-evening departure is matched to the date the
    traveller wrote down. Falls back to the UTC date when no timezone is known.
    """
    scheduled = _parse_datetime(entry.get("scheduled_out") or entry.get("scheduled_off"))
    if scheduled is None:
        return None, None
    utc_date = scheduled.date()
    tz_name = _airport_field(entry, "origin", "timezone")
    if tz_name:
        try:
            local = scheduled.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz_name))
            return local.date(), utc_date
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return utc_date, utc_date


def _departs_on(entry, dep_date):
    return dep_date in _departure_dates(entry)


def _score_entry(entry, flight_iata, dep_iata, dep_date):
    score = 0
    wanted = _normalize_code(flight_iata)
    idents = {
        _normalize_code(entry.get(key))
        for key in ("ident_iata", "ident_icao", "ident")
    }
    idents.discard("")
    if wanted and wanted in idents:
        score += 6
    elif wanted and any(wanted in ident for ident in idents):
        score += 3

    wanted_dep = _normalize_code(dep_iata)
    if wanted_dep:
        origin_codes = {
            _normalize_code(_airport_field(entry, "origin", key))
            for key in ("code_iata", "code_icao", "code")
        }
        if wanted_dep in origin_codes:
            score += 3

    local_date, utc_date = _departure_dates(entry)
    if dep_date and local_date == dep_date:
        score += 3
    elif dep_date and utc_date == dep_date:
        score += 1

    if entry.get("cancelled"):
        score -= 2
    if entry.get("position_only"):
        score -= 1
    return score


def _pick_best_entry(entries, flight_iata, dep_iata, dep_date):
    candidates = [
        entry
        for entry in entries
        if isinstance(entry, dict) and _departs_on(entry, dep_date)
    ]
    if not candidates:
        return None
    scored = sorted(
        (
            (entry, _score_entry(entry, flight_iata, dep_iata, dep_date))
            for entry in candidates
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    best, best_score = scored[0]
    return best if best_score > 0 else None


def is_within_window(dep_date, today=None):
    """Whether AeroAPI's ``/flights`` endpoint can still return ``dep_date``."""
    if dep_date is None:
        return False
    today = today or datetime.now(timezone.utc).date()
    earliest = today - timedelta(days=LOOKBACK_DAYS)
    latest = today + timedelta(days=LOOKAHEAD_DAYS)
    return earliest <= dep_date <= latest


def window_error(dep_date):
    return FlightAwareWindowError(
        f"FlightAware only returns flights from {LOOKBACK_DAYS} days ago to "
        f"{LOOKAHEAD_DAYS} days ahead; {dep_date.isoformat()} is outside that window."
    )


def query_window(dep_date, now=None):
    """UTC (start, end) datetimes to search for flights on ``dep_date``.

    The span covers the day before through the day after the local departure
    date so late-evening and early-morning departures are not cut off at the
    UTC boundary, clamped to the range AeroAPI accepts.
    """
    now = now or datetime.now(timezone.utc)
    if not is_within_window(dep_date, today=now.date()):
        raise window_error(dep_date)
    earliest = now - timedelta(days=LOOKBACK_DAYS) + _WINDOW_MARGIN
    latest = now + timedelta(days=LOOKAHEAD_DAYS) - _WINDOW_MARGIN
    start = datetime.combine(dep_date - timedelta(days=1), time.min, tzinfo=timezone.utc)
    end = datetime.combine(dep_date + timedelta(days=1), time(23, 59, 59), tzinfo=timezone.utc)
    start = max(start, earliest)
    end = min(end, latest)
    if start >= end:
        raise window_error(dep_date)
    return start.replace(microsecond=0), end.replace(microsecond=0)


def _error_detail(body):
    """Pull the human-readable reason out of an AeroAPI error body."""
    if not body:
        return ""
    try:
        data = json.loads(body)
    except ValueError:
        return body.strip()
    if isinstance(data, dict):
        return str(data.get("detail") or data.get("reason") or data.get("title") or body).strip()
    return body.strip()


def search_flightaware_history(
    flight_iata, dep_date, dep_iata=None, include_payload=False
):
    """Find the AeroAPI flight for ``flight_iata`` departing on ``dep_date``.

    Returns the best-matching flight dict, or ``None`` when nothing matched.
    With ``include_payload=True`` returns ``(entry, payload)`` where payload
    holds the request parameters and raw response for auditing.
    """
    config = current_app.config
    base_url = (config.get("FLIGHTAWARE_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    api_key = config.get("FLIGHTAWARE_API_KEY")
    if not api_key:
        raise FlightAwareHistoryError("Missing FLIGHTAWARE_API_KEY configuration.")
    if not flight_iata or not dep_date:
        raise FlightAwareHistoryError("Flight number and date are required.")

    start, end = query_window(dep_date)
    params = {
        "ident_type": "designator",
        "start": _iso_z(start),
        "end": _iso_z(end),
        "max_pages": 1,
    }
    url = f"{base_url}/flights/{parse.quote(flight_iata)}?{parse.urlencode(params)}"
    current_app.logger.info(
        "FlightAware search: flight=%s depDate=%s depIata=%s",
        flight_iata,
        dep_date.isoformat(),
        dep_iata,
    )
    req = request.Request(
        url,
        headers={"Accept": "application/json", "x-apikey": api_key},
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            data = json.load(response)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        detail = _error_detail(body)
        current_app.logger.warning(
            "FlightAware HTTPError: status=%s body=%s", exc.code, body
        )
        if exc.code == 401:
            message = "FlightAware rejected the API key (401)."
        elif exc.code == 429:
            message = "FlightAware rate limit reached (429); try again in a minute."
        else:
            message = f"FlightAware request failed ({exc.code})."
        if detail:
            message = f"{message} {detail}"
        raise FlightAwareHistoryError(message, status_code=exc.code) from exc
    except URLError as exc:
        current_app.logger.warning("FlightAware URLError: %s", exc)
        raise FlightAwareHistoryError("FlightAware request failed.") from exc

    payload = {"request": {"url": url, "params": params}, "response": data}
    flights = data.get("flights") if isinstance(data, dict) else None
    if not isinstance(flights, list):
        flights = []
    current_app.logger.info(
        "FlightAware response: flight=%s results=%d", flight_iata, len(flights)
    )
    current_app.logger.debug("FlightAware raw response: %s", data)
    entry = _pick_best_entry(flights, flight_iata, dep_iata, dep_date)
    if include_payload:
        return entry, payload
    return entry


def _delay_status(seconds):
    if seconds is None:
        return None
    if seconds > 0:
        return "delayed"
    if seconds < 0:
        return "early"
    return "on time"


def _delay_detail(seconds):
    if seconds is None:
        return None
    minutes = int(round(seconds / 60))
    if minutes == 0:
        return "on time"
    return f"{minutes:+d} min"


def _seconds_between(start, end):
    if start is None or end is None:
        return None
    return int((end - start).total_seconds())


def normalize_flightaware_history_entry(entry):
    """Map an AeroAPI flight object onto FlightHistoryAirNavRadar columns.

    Times are stored as naive UTC. ``distance`` is AeroAPI's route distance in
    statute miles; ``duration`` and ``planned_duration`` are seconds.
    """
    airline_iata = entry.get("operator_iata")
    airline_icao = entry.get("operator_icao")
    actual_off = _parse_datetime(entry.get("actual_off"))
    actual_on = _parse_datetime(entry.get("actual_on"))
    fa_flight_id = entry.get("fa_flight_id")
    return {
        "callsign": entry.get("atc_ident") or entry.get("ident_icao") or entry.get("ident"),
        "flight_number_iata": entry.get("ident_iata"),
        "flight_number_icao": entry.get("ident_icao"),
        "aircraft_registration": entry.get("registration"),
        "aircraft_type": entry.get("aircraft_type"),
        "airline_iata": airline_iata,
        "airline_icao": airline_icao,
        "airline_name": lookup_airline_name(airline_iata) or lookup_airline_name(airline_icao),
        "dep_airport_icao": _airport_field(entry, "origin", "code_icao"),
        "dep_airport_iata": _airport_field(entry, "origin", "code_iata"),
        "dep_airport_name": _airport_field(entry, "origin", "name"),
        "dep_airport_city": _airport_field(entry, "origin", "city"),
        "dep_airport_tz": _airport_field(entry, "origin", "timezone"),
        "scheduled_departure": _parse_datetime(entry.get("scheduled_out")),
        "estimated_departure": _parse_datetime(entry.get("estimated_out")),
        "actual_departure": _parse_datetime(entry.get("actual_out")),
        "actual_takeoff": actual_off,
        "calculated_takeoff": _parse_datetime(
            entry.get("estimated_off") or entry.get("scheduled_off")
        ),
        "arr_airport_icao": _airport_field(entry, "destination", "code_icao"),
        "arr_airport_iata": _airport_field(entry, "destination", "code_iata"),
        "arr_airport_name": _airport_field(entry, "destination", "name"),
        "arr_airport_city": _airport_field(entry, "destination", "city"),
        "arr_airport_tz": _airport_field(entry, "destination", "timezone"),
        "scheduled_arrival": _parse_datetime(entry.get("scheduled_in")),
        "estimated_arrival": _parse_datetime(entry.get("estimated_in")),
        "actual_arrival": _parse_datetime(entry.get("actual_in")),
        "actual_landing": actual_on,
        "calculated_landing": _parse_datetime(
            entry.get("estimated_on") or entry.get("scheduled_on")
        ),
        "departure_status": _delay_status(entry.get("departure_delay")),
        "departure_delay_detail": _delay_detail(entry.get("departure_delay")),
        "departure_gate": entry.get("gate_origin"),
        "departure_terminal": entry.get("terminal_origin"),
        "arrival_status": _delay_status(entry.get("arrival_delay")),
        "arrival_delay_detail": _delay_detail(entry.get("arrival_delay")),
        "distance": entry.get("route_distance"),
        "duration": _seconds_between(actual_off, actual_on),
        "planned_duration": entry.get("filed_ete"),
        "source": SOURCE,
        "flight_url": (
            f"https://www.flightaware.com/live/flight/id/{parse.quote(fa_flight_id)}"
            if fa_flight_id
            else None
        ),
        "icao_route": entry.get("route"),
        "status": entry.get("status"),
    }


def record_flightaware_history(flight, entry, overwrite_aircraft=True):
    """Store ``entry`` as a history row for ``flight`` and copy the aircraft onto it.

    The flight's ``aircraft`` gets a display name for the ICAO type FlightAware
    reported (e.g. "Boeing 777-200", from the curated alias map, else the
    aircraft table / ADSBDB) and ``aircraft_type_normalized`` the designator
    itself (e.g. "B772"). With
    ``overwrite_aircraft`` those fields are replaced; otherwise only empty ones
    are filled. The row is added to the session but not committed; the caller
    commits.
    """
    fields = normalize_flightaware_history_entry(entry)
    name, code = apply_aircraft_to_flight(
        flight,
        registration=fields.get("aircraft_registration"),
        icao_type=fields.get("aircraft_type"),
        overwrite=overwrite_aircraft,
    )
    if name and name != code:
        fields["aircraft_type_description"] = name[:128]
    history = FlightHistoryAirNavRadar(
        flight_id=flight.id,
        dep_date=flight.start_date,
        raw_payload=entry,
        **fields,
    )
    db.session.add(history)
    return history
