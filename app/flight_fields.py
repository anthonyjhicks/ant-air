"""Flight field catalog plus coercion, normalisation and enrichment helpers.

This module is the single description of "what a Flight looks like to a
writer". The MCP server uses it to:

* expose every writable ``Flight`` column with a type and a description,
* validate incoming values *before* touching the database and report each
  problem by field name instead of silently storing ``None``,
* apply the conveniences the web UI applies: uppercase airport / airline /
  registration codes, split ``BA123`` into ``airline_code`` + ``flight_number``,
  look up the aircraft type from the registration, and compute distance and
  route direction from coordinates.

The catalog is checked against ``api_v1.FLIGHT_WRITABLE_FIELDS`` at import time
so the REST API and the MCP server cannot drift apart silently.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import func

from .api_v1 import FLIGHT_WRITABLE_FIELDS
from .models import Aircraft, Flight
from .services.distance import haversine_miles
from .services.importer import compute_route_direction

APPROVED_STATUS = "approved"
DRAFT_STATUS = "draft"
FLIGHT_STATUSES = (APPROVED_STATUS, DRAFT_STATUS)
ROUTE_DIRECTIONS = ("east", "west")
DEFAULT_SOURCE = "mcp"

# Fields that must never be blanked via clear_fields.
UNCLEARABLE_FIELDS = frozenset({"start_date", "status"})


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: str  # str | date | time | decimal | float | int | bool
    group: str
    description: str
    upper: bool = False
    max_length: Optional[int] = None
    choices: Optional[tuple[str, ...]] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None

    @property
    def json_type(self) -> str:
        return {
            "str": "string",
            "date": "string (YYYY-MM-DD)",
            "time": "string (HH:MM)",
            "decimal": "number",
            "float": "number",
            "int": "integer",
            "bool": "boolean",
        }[self.kind]

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "type": self.json_type,
            "group": self.group,
            "description": self.description,
        }
        if self.upper:
            payload["uppercased"] = True
        if self.max_length:
            payload["max_length"] = self.max_length
        if self.choices:
            payload["choices"] = list(self.choices)
        if self.minimum is not None:
            payload["minimum"] = self.minimum
        if self.maximum is not None:
            payload["maximum"] = self.maximum
        return payload


def _lat(name: str, side: str) -> FieldSpec:
    return FieldSpec(
        name, "float", "route",
        f"{side} latitude in decimal degrees (-90 to 90). Auto-filled from "
        f"earlier flights that use the same airport code when omitted.",
        minimum=-90, maximum=90,
    )


def _long(name: str, side: str) -> FieldSpec:
    return FieldSpec(
        name, "float", "route",
        f"{side} longitude in decimal degrees (-180 to 180). Auto-filled from "
        f"earlier flights that use the same airport code when omitted.",
        minimum=-180, maximum=180,
    )


_SPECS: tuple[FieldSpec, ...] = (
    # --- core -------------------------------------------------------------
    FieldSpec(
        "status", "str", "core",
        "Workflow status: 'approved' (counts in stats and shows in the flight "
        "list) or 'draft' (sits in the inbox awaiting approval). Defaults to "
        "'approved'.",
        choices=FLIGHT_STATUSES, max_length=16,
    ),
    FieldSpec("start_date", "date", "core",
              "Departure date as YYYY-MM-DD. Required when creating."),
    FieldSpec("start_time", "time", "core",
              "Scheduled departure time as HH:MM (24-hour, local time at the origin)."),
    FieldSpec("end_date", "date", "core",
              "Arrival date as YYYY-MM-DD. Defaults to start_date when creating."),
    FieldSpec("end_time", "time", "core",
              "Scheduled arrival time as HH:MM (24-hour, local time at the destination)."),
    # --- route ------------------------------------------------------------
    FieldSpec(
        "start_airport", "str", "route",
        "Origin airport IATA code, e.g. LHR. Stored uppercase. When creating, "
        "either this or start_city_name is required.",
        upper=True, max_length=64,
    ),
    FieldSpec("start_city_name", "str", "route", "Origin city, e.g. London.", max_length=128),
    FieldSpec("start_country", "str", "route", "Origin country name, e.g. United Kingdom.", max_length=128),
    FieldSpec("start_terminal", "str", "route", "Departure terminal, e.g. 5.", max_length=32),
    _lat("start_lat", "Origin"),
    _long("start_long", "Origin"),
    FieldSpec(
        "end_airport", "str", "route",
        "Destination airport IATA code, e.g. JFK. Stored uppercase. When "
        "creating, either this or end_city_name is required.",
        upper=True, max_length=64,
    ),
    FieldSpec("end_city_name", "str", "route", "Destination city, e.g. New York.", max_length=128),
    FieldSpec("end_country", "str", "route", "Destination country name, e.g. United States.", max_length=128),
    FieldSpec("end_terminal", "str", "route", "Arrival terminal, e.g. 8.", max_length=32),
    _lat("end_lat", "Destination"),
    _long("end_long", "Destination"),
    FieldSpec("stops", "int", "route",
              "Number of intermediate stops; 0 for a non-stop flight.", minimum=0),
    FieldSpec(
        "distance", "float", "route",
        "Great-circle distance in statute miles. Auto-computed from the "
        "coordinates when omitted.",
        minimum=0,
    ),
    FieldSpec(
        "route_direction", "str", "route",
        "Overall heading, 'east' or 'west'. Auto-computed from the coordinates "
        "when omitted.",
        choices=ROUTE_DIRECTIONS, max_length=8,
    ),
    # --- airline & aircraft ----------------------------------------------
    FieldSpec(
        "airline_code", "str", "airline",
        "Marketing airline IATA code, e.g. BA. Stored uppercase. Derived from "
        "flight_number when that includes a prefix such as 'BA123'.",
        upper=True, max_length=16,
    ),
    FieldSpec(
        "flight_number", "str", "airline",
        "Marketing flight number. Stored as digits only (e.g. '123'); a "
        "prefixed value such as 'BA123' or 'BA 123' is split into airline_code "
        "and flight_number automatically.",
        max_length=32,
    ),
    FieldSpec(
        "operating_airline_code", "str", "airline",
        "Operating carrier IATA code when the flight is a codeshare, e.g. AA. "
        "Stored uppercase.",
        upper=True, max_length=16,
    ),
    FieldSpec(
        "operating_flight_number", "str", "airline",
        "Operating carrier flight number for codeshares, digits only. A prefix "
        "is split off into operating_airline_code like flight_number.",
        max_length=32,
    ),
    FieldSpec(
        "aircraft", "str", "airline",
        "Aircraft type as displayed, e.g. 'Boeing 777-300ER'. Auto-filled from "
        "the aircraft table when aircraft_registration is known.",
        max_length=64,
    ),
    FieldSpec(
        "aircraft_type_normalized", "str", "airline",
        "ICAO aircraft type designator, e.g. B77W. Auto-filled from the "
        "aircraft table when aircraft_registration is known.",
        max_length=64,
    ),
    FieldSpec(
        "aircraft_registration", "str", "airline",
        "Tail number / registration, e.g. G-STBA. Stored uppercase.",
        upper=True, max_length=32,
    ),
    FieldSpec(
        "service_class", "str", "airline",
        "Cabin flown, e.g. Economy, Premium Economy, Business, First. Use "
        "flight_field_values('service_class') to see the labels already in use.",
        max_length=64,
    ),
    FieldSpec("ticket_number", "str", "airline", "E-ticket number.", max_length=64),
    # --- booking ----------------------------------------------------------
    FieldSpec(
        "traveller", "str", "booking",
        "Name of the person who flew. Use flight_field_values('traveller') to "
        "see the names already in use and keep them consistent.",
        max_length=128,
    ),
    FieldSpec("booking_site", "str", "booking",
              "Where it was booked, e.g. British Airways, Expedia.", max_length=255),
    FieldSpec("supplier_confirmation", "str", "booking",
              "Airline booking reference / PNR, e.g. ABC123.", max_length=128),
    FieldSpec("booking_date", "date", "booking", "Date the booking was made, YYYY-MM-DD."),
    FieldSpec("booking_site_phone", "str", "booking",
              "Contact phone number for the booking site.", max_length=64),
    FieldSpec("url", "str", "booking", "Link to the booking or itinerary."),
    FieldSpec("activity_id", "str", "booking",
              "External itinerary segment identifier (e.g. the TripIt segment id).",
              max_length=64),
    FieldSpec("activity_cost", "decimal", "booking",
              "Cost of this segment as a decimal number, e.g. 249.99 (two decimal places kept)."),
    # --- trip -------------------------------------------------------------
    FieldSpec("trip_name", "str", "trip",
              "Name of the trip this flight belongs to, e.g. 'Japan 2025'.", max_length=255),
    FieldSpec("trip_id", "str", "trip",
              "External trip identifier (e.g. the TripIt trip id). Free text, not a "
              "foreign key.", max_length=64),
    FieldSpec("trip_type", "str", "trip", "Trip category, e.g. Business, Personal.", max_length=64),
    FieldSpec("trip_leg_id", "int", "trip",
              "Id of the TripLeg row this flight fulfils (see list_trips / get_trip).",
              minimum=1),
    # --- flags & provenance ----------------------------------------------
    FieldSpec("follow_up", "bool", "flags",
              "Mark the flight for follow-up (details still to chase)."),
    FieldSpec("exclude_from_stats", "bool", "flags",
              "Exclude from dashboards and statistics without deleting it."),
    FieldSpec("audit_missing_leg_ignored", "bool", "flags",
              "Suppress this flight from the missing-leg audit."),
    FieldSpec(
        "grouping_id", "str", "flags",
        "UUID shared by flights that were merged as duplicates of one another. "
        "Normally managed by the merge tool; leave unset.",
        max_length=36,
    ),
    FieldSpec(
        "source_file", "str", "flags",
        "Provenance of the record, e.g. an import file name. Defaults to 'mcp' "
        "when created through the MCP server.",
        max_length=255,
    ),
)

FLIGHT_FIELDS: dict[str, FieldSpec] = {spec.name: spec for spec in _SPECS}
FIELD_GROUPS: tuple[str, ...] = ("core", "route", "airline", "booking", "trip", "flags")

# Fields whose distinct values are meaningful to list (enum-like text columns).
ENUMERABLE_FIELDS: tuple[str, ...] = (
    "traveller", "service_class", "trip_type", "trip_name", "status",
    "airline_code", "operating_airline_code", "booking_site",
    "aircraft", "aircraft_type_normalized", "aircraft_registration",
    "start_airport", "end_airport", "start_city_name", "end_city_name",
    "start_country", "end_country", "route_direction", "source_file",
)

_missing = set(FLIGHT_WRITABLE_FIELDS) - set(FLIGHT_FIELDS)
_extra = set(FLIGHT_FIELDS) - set(FLIGHT_WRITABLE_FIELDS)
if _missing or _extra:  # pragma: no cover - guards against schema drift
    raise RuntimeError(
        "flight_fields catalog is out of sync with api_v1.FLIGHT_WRITABLE_FIELDS: "
        f"missing={sorted(_missing)} extra={sorted(_extra)}"
    )


def field_catalog() -> list[dict[str, Any]]:
    """Field specs as plain dicts, in display order."""
    return [spec.to_dict() for spec in _SPECS]


# ---------------------------------------------------------------------------
# Coercion
# ---------------------------------------------------------------------------

_TRUE = {"true", "yes", "y", "1", "on"}
_FALSE = {"false", "no", "n", "0", "off"}
_TIME_FORMATS = ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p", "%H%M")
# Carrier prefix: 2-3 letters (IATA/ICAO) or a 2-char code with one digit
# (e.g. U2, 9W). The prefix must not end in a digit that belongs to the number.
_FLIGHT_NUMBER_RE = re.compile(
    r"^(?P<code>[A-Za-z]{2,3}|[A-Za-z]\d|\d[A-Za-z])[\s-]*(?P<number>\d{1,5})$"
)


def _parse_date(raw: Any) -> date:
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    text = str(raw).strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        raise ValueError("expected a date as YYYY-MM-DD") from None


def _parse_time(raw: Any) -> time:
    if isinstance(raw, datetime):
        return raw.time().replace(tzinfo=None)
    if isinstance(raw, time):
        return raw.replace(tzinfo=None)
    text = str(raw).strip().upper()
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    raise ValueError("expected a time as HH:MM (24-hour)")


def _parse_decimal(raw: Any) -> Decimal:
    if isinstance(raw, bool):
        raise ValueError("expected a number")
    if isinstance(raw, (int, float)):
        if isinstance(raw, float) and not math.isfinite(raw):
            raise ValueError("expected a finite number")
        value = Decimal(str(raw))
    else:
        text = str(raw).strip().replace(",", "").lstrip("$£€")
        try:
            value = Decimal(text)
        except InvalidOperation:
            raise ValueError("expected a number such as 249.99") from None
    if not value.is_finite():
        raise ValueError("expected a finite number")
    if abs(value) >= Decimal("100000000"):
        raise ValueError("must be less than 100,000,000")
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _parse_float(raw: Any, spec: FieldSpec) -> float:
    if isinstance(raw, bool):
        raise ValueError("expected a number")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValueError("expected a number") from None
    if not math.isfinite(value):
        raise ValueError("expected a finite number")
    _check_range(value, spec)
    return value


def _parse_int(raw: Any, spec: FieldSpec) -> int:
    if isinstance(raw, bool):
        raise ValueError("expected a whole number")
    if isinstance(raw, float):
        if not raw.is_integer():
            raise ValueError("expected a whole number")
        value = int(raw)
    else:
        try:
            value = int(str(raw).strip())
        except ValueError:
            raise ValueError("expected a whole number") from None
    _check_range(value, spec)
    return value


def _parse_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)) and raw in (0, 1):
        return bool(raw)
    text = str(raw).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ValueError("expected true or false")


def _parse_str(raw: Any, spec: FieldSpec) -> str:
    if isinstance(raw, bool):
        raise ValueError("expected text")
    text = " ".join(str(raw).split())
    if spec.upper:
        text = text.upper()
    if spec.choices:
        lowered = text.lower()
        if lowered not in spec.choices:
            raise ValueError("must be one of: " + ", ".join(spec.choices))
        text = lowered
    if spec.max_length and len(text) > spec.max_length:
        raise ValueError(f"must be at most {spec.max_length} characters")
    return text


def _check_range(value: float, spec: FieldSpec) -> None:
    if spec.minimum is not None and value < spec.minimum:
        raise ValueError(f"must be at least {spec.minimum:g}")
    if spec.maximum is not None and value > spec.maximum:
        raise ValueError(f"must be at most {spec.maximum:g}")


def coerce_value(spec: FieldSpec, raw: Any) -> Any:
    """Coerce one raw value to the column's Python type. Raises ValueError."""
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    if spec.kind == "str":
        return _parse_str(raw, spec)
    if spec.kind == "date":
        return _parse_date(raw)
    if spec.kind == "time":
        return _parse_time(raw)
    if spec.kind == "decimal":
        return _parse_decimal(raw)
    if spec.kind == "float":
        return _parse_float(raw, spec)
    if spec.kind == "int":
        return _parse_int(raw, spec)
    if spec.kind == "bool":
        return _parse_bool(raw)
    raise ValueError(f"unsupported field kind {spec.kind}")  # pragma: no cover


def _split_flight_number(
    cleaned: dict[str, Any], number_key: str, code_key: str, warnings: list[str]
) -> None:
    """Normalise 'BA123' -> airline_code='BA', flight_number='123'."""
    value = cleaned.get(number_key)
    if not value:
        return
    if value.isdigit():
        cleaned[number_key] = value.lstrip("0") or "0"
        return
    match = _FLIGHT_NUMBER_RE.match(value)
    if not match:
        cleaned[number_key] = value.upper()
        return
    prefix, digits = match.group(1).upper(), match.group(2).lstrip("0") or "0"
    existing = cleaned.get(code_key)
    if existing and existing != prefix:
        warnings.append(
            f"{number_key} '{value}' carries prefix {prefix} but {code_key} was "
            f"given as {existing}; kept {code_key}={existing} and "
            f"{number_key}={digits}."
        )
    elif not existing:
        cleaned[code_key] = prefix
    cleaned[number_key] = digits


def coerce_flight_fields(
    data: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    """Validate and normalise a dict of raw field values.

    Returns ``(cleaned, errors, warnings)``. ``cleaned`` only contains keys that
    were present in ``data`` (a value of ``None`` means "blank this field").
    Unknown keys and unparseable values are reported in ``errors`` by field
    name; nothing is applied to any model here.
    """
    cleaned: dict[str, Any] = {}
    errors: dict[str, str] = {}
    warnings: list[str] = []
    for key, raw in (data or {}).items():
        spec = FLIGHT_FIELDS.get(key)
        if spec is None:
            errors[key] = "unknown field (see describe_flight_fields)"
            continue
        try:
            cleaned[key] = coerce_value(spec, raw)
        except ValueError as exc:
            errors[key] = str(exc)
    if not errors:
        _split_flight_number(cleaned, "flight_number", "airline_code", warnings)
        _split_flight_number(
            cleaned, "operating_flight_number", "operating_airline_code", warnings
        )
    return cleaned, errors, warnings


def validate_required_for_create(cleaned: dict[str, Any]) -> dict[str, str]:
    """Checks that apply only when creating a flight."""
    errors: dict[str, str] = {}
    if cleaned.get("start_date") is None:
        errors["start_date"] = "required (YYYY-MM-DD)"
    if not (cleaned.get("start_airport") or cleaned.get("start_city_name")):
        errors["start_airport"] = "start_airport or start_city_name is required"
    if not (cleaned.get("end_airport") or cleaned.get("end_city_name")):
        errors["end_airport"] = "end_airport or end_city_name is required"
    return errors


# ---------------------------------------------------------------------------
# Enrichment (mirrors the web UI's quick-add behaviour)
# ---------------------------------------------------------------------------

_AIRPORT_DETAIL_KEYS = ("city_name", "country", "lat", "long")


def lookup_airport_from_flights(
    code: str, exclude_id: Optional[int] = None
) -> dict[str, Any]:
    """Best-known city/country/lat/long for an airport code, from existing flights.

    Rows that carry coordinates are preferred, most recently updated first.
    """
    result: dict[str, Any] = {key: None for key in _AIRPORT_DETAIL_KEYS}
    code = (code or "").strip().upper()
    if not code:
        return result

    candidates = []
    for side in ("start", "end"):
        airport_col = getattr(Flight, f"{side}_airport")
        cols = [getattr(Flight, f"{side}_{key}") for key in _AIRPORT_DETAIL_KEYS]
        base = Flight.query.filter(
            func.upper(airport_col) == code, Flight.deleted_at.is_(None)
        )
        if exclude_id is not None:
            base = base.filter(Flight.id != exclude_id)
        with_coords = base.filter(cols[2].isnot(None), cols[3].isnot(None))
        candidates.append((with_coords, cols))
        candidates.append((base, cols))

    # Coordinates first (both sides), then anything.
    ordered = candidates[0::2] + candidates[1::2]
    for query, cols in ordered:
        row = query.order_by(Flight.updated_at.desc()).with_entities(*cols).first()
        if row is None:
            continue
        for key, value in zip(_AIRPORT_DETAIL_KEYS, row):
            if result[key] is None and value not in (None, ""):
                result[key] = value
        if all(result[key] is not None for key in _AIRPORT_DETAIL_KEYS):
            break
    return result


def lookup_aircraft(registration: str) -> Optional[Aircraft]:
    reg = (registration or "").strip().upper()
    if not reg:
        return None
    return Aircraft.query.filter(func.upper(Aircraft.registration) == reg).first()


def enrich_flight(
    flight: Flight, *, auto_fill: bool = True, exclude_id: Optional[int] = None
) -> tuple[list[str], list[str]]:
    """Fill derived fields that are still empty. Returns ``(filled, warnings)``.

    With ``auto_fill`` the origin/destination city, country and coordinates are
    copied from earlier flights using the same airport code and the aircraft
    type is looked up from the aircraft table. Distance and route direction are
    always computed from coordinates when missing.
    """
    filled: list[str] = []
    warnings: list[str] = []

    if auto_fill:
        for side in ("start", "end"):
            code = getattr(flight, f"{side}_airport")
            if not code:
                continue
            missing = [
                key for key in _AIRPORT_DETAIL_KEYS
                if getattr(flight, f"{side}_{key}") is None
            ]
            if not missing:
                continue
            known = lookup_airport_from_flights(code, exclude_id=exclude_id)
            for key in missing:
                if known.get(key) is not None:
                    setattr(flight, f"{side}_{key}", known[key])
                    filled.append(f"{side}_{key}")

        if flight.aircraft_registration and (
            flight.aircraft is None or flight.aircraft_type_normalized is None
        ):
            record = lookup_aircraft(flight.aircraft_registration)
            if record is not None:
                if flight.aircraft is None and record.type:
                    flight.aircraft = record.type
                    filled.append("aircraft")
                if flight.aircraft_type_normalized is None and record.icao_type:
                    flight.aircraft_type_normalized = record.icao_type
                    filled.append("aircraft_type_normalized")

    coords = (flight.start_lat, flight.start_long, flight.end_lat, flight.end_long)
    have_coords = None not in coords
    if flight.distance is None:
        if have_coords:
            flight.distance = haversine_miles(*coords)
            filled.append("distance")
        else:
            unknown = [
                side for side in ("start", "end")
                if getattr(flight, f"{side}_lat") is None
                or getattr(flight, f"{side}_long") is None
            ]
            warnings.append(
                "distance not computed: coordinates unknown for "
                + ", ".join(
                    f"{side} ({getattr(flight, f'{side}_airport') or getattr(flight, f'{side}_city_name') or '?'})"
                    for side in unknown
                )
                + ". Pass start_lat/start_long/end_lat/end_long or distance."
            )
    if flight.route_direction is None and have_coords:
        direction = compute_route_direction(*coords)
        if direction:
            flight.route_direction = direction
            filled.append("route_direction")
    return filled, warnings


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def duplicate_key(values: dict[str, Any]) -> Optional[tuple]:
    """Key used to spot duplicates inside one batch (same route/date/number/traveller)."""
    if values.get("start_date") is None:
        return None
    origin = values.get("start_airport") or values.get("start_city_name")
    dest = values.get("end_airport") or values.get("end_city_name")
    if not (origin and dest):
        return None
    return (
        values["start_date"],
        origin.upper(),
        dest.upper(),
        (values.get("flight_number") or "").upper(),
        (values.get("traveller") or "").lower(),
    )


def find_possible_duplicates(
    values: dict[str, Any], exclude_id: Optional[int] = None
) -> list[dict[str, Any]]:
    """Existing flights on the same date and route.

    ``match`` is ``"exact"`` when the flight number matches as well (and the
    traveller matches or is unknown on either side), otherwise ``"route"``.
    """
    start_date = values.get("start_date")
    if start_date is None:
        return []
    query = Flight.query.filter(
        Flight.deleted_at.is_(None), Flight.start_date == start_date
    )
    start_airport, end_airport = values.get("start_airport"), values.get("end_airport")
    if start_airport and end_airport:
        query = query.filter(
            func.upper(Flight.start_airport) == start_airport.upper(),
            func.upper(Flight.end_airport) == end_airport.upper(),
        )
    else:
        start_city, end_city = values.get("start_city_name"), values.get("end_city_name")
        if not (start_city and end_city):
            return []
        query = query.filter(
            func.lower(Flight.start_city_name) == start_city.lower(),
            func.lower(Flight.end_city_name) == end_city.lower(),
        )
    if exclude_id is not None:
        query = query.filter(Flight.id != exclude_id)

    number = (values.get("flight_number") or "").upper() or None
    traveller = (values.get("traveller") or "").lower() or None
    matches = []
    for other in query.order_by(Flight.id.asc()).limit(20).all():
        other_number = (other.flight_number or "").upper() or None
        other_traveller = (other.traveller or "").lower() or None
        same_number = number == other_number
        same_traveller = (
            traveller is None or other_traveller is None or traveller == other_traveller
        )
        matches.append({
            "id": other.id,
            "match": "exact" if same_number and same_traveller else "route",
            "status": other.status,
            "airline_code": other.airline_code,
            "flight_number": other.flight_number,
            "traveller": other.traveller,
            "start_airport": other.start_airport,
            "end_airport": other.end_airport,
            "start_time": other.start_time.isoformat() if other.start_time else None,
        })
    return matches
