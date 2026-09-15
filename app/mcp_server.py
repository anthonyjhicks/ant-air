"""MCP server exposing flight history read/write tools.

Run locally over stdio (the default):
    .venv/bin/python -m app.mcp_server

Or serve over streamable HTTP, e.g. inside the Kubernetes cluster:
    MCP_TRANSPORT=streamable-http MCP_PORT=8001 python -m app.mcp_server

HTTP settings (all optional): MCP_HOST (0.0.0.0), MCP_PORT (8001), MCP_PATH
(/mcp), MCP_STATELESS (true), MCP_JSON_RESPONSE (false), MCP_LOG_LEVEL (info)
and MCP_AUTH_TOKEN. When MCP_AUTH_TOKEN is set every request except /healthz
must carry ``Authorization: Bearer <token>``; leave it unset to rely on
network isolation alone.

Reuses the Flask app's SQLAlchemy models and helpers so behavior matches the
REST API. A Flask app context is pushed once at startup; each tool call wraps
its DB work in a session scope and commits/rolls back per call.
"""

from __future__ import annotations

import hmac
import inspect
import os
from datetime import datetime, timezone
from typing import Annotated, Any, Optional

from flask import current_app
from pydantic import Field
from sqlalchemy import func, or_, text
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import create_app
from .api_v1 import (
    apply_leg_fields,
    apply_trip_fields,
    parse_date,
    parse_datetime,
)
from .extensions import db
from .services.flight_groups import (
    ACTIVE_FLIGHT_FILTERS,
    REPORTABLE_FLIGHT_FILTERS,
    group_info,
    group_info_by_flight,
    is_group_primary,
    matches_flight_or_group_member,
    reporting_flights_query,
)
from .flight_fields import (
    APPROVED_STATUS,
    DEFAULT_SOURCE,
    ENUMERABLE_FIELDS,
    FIELD_GROUPS,
    FLIGHT_FIELDS,
    UNCLEARABLE_FIELDS,
    coerce_flight_fields,
    duplicate_key,
    enrich_flight,
    field_catalog,
    find_possible_duplicates,
    lookup_aircraft,
    validate_required_for_create,
)
from .services.flight_lookup import (
    FlightLookupError,
    active_provider,
    lookup_and_record,
    provider_label,
)
from .models import (
    AchievementBadge,
    Aircraft,
    Flight,
    FlightHistory,
    FlightHistoryAirNavRadar,
    FlightPosition,
    SyncState,
    Trip,
    TripLeg,
)
from .sync import (
    aircraft_to_dict,
    badge_to_dict,
    flight_to_dict,
    serialize_date,
    serialize_value,
    stamp_revision,
    trip_leg_to_dict,
    trip_to_dict,
)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "The 'mcp' package is required. Install it with:\n"
        "  .venv/bin/pip install 'mcp>=1.2.0'\n"
    ) from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "stdio").strip().lower() or "stdio"
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0").strip() or "0.0.0.0"
MCP_PORT = int(os.environ.get("MCP_PORT", "8001") or 8001)
MCP_PATH = os.environ.get("MCP_PATH", "/mcp").strip() or "/mcp"
MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "").strip()

mcp = FastMCP(
    "ant-air",
    instructions=(
        "Ant Air personal flight history: flights, trips, aircraft, "
        "badges and flight history in one database. Before creating or editing "
        "flights, call describe_flight_fields for the field catalog and "
        "flight_field_values to reuse the traveller, service class and airline "
        "labels already in use. create_flight and bulk_create_flights also ask "
        "the configured flight-data provider (currently FlightAware) which "
        "aircraft operated each new flight and fill aircraft_registration; use "
        "lookup_flight_registration to retry that for an existing flight. "
        "Flights that share a grouping_id are one flight recorded more than "
        "once; every list and statistic reports such a group once, through its "
        "primary (newest) record, unless list_flights is called with "
        "include_group_members=true."
    ),
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path=MCP_PATH,
    stateless_http=_env_bool("MCP_STATELESS", True),
    json_response=_env_bool("MCP_JSON_RESPONSE", False),
)


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def _active_flights():
    return Flight.query.filter(Flight.deleted_at.is_(None))


def _approved_active_flights():
    return _active_flights().filter(Flight.status == "approved")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _commit_or_rollback():
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


# ---------------------------------------------------------------------------
# Flights — read
# ---------------------------------------------------------------------------

@mcp.tool()
def list_flights(
    year: Optional[int] = None,
    airline_code: Optional[str] = None,
    traveller: Optional[str] = None,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    q: Optional[str] = None,
    status: Optional[str] = "approved",
    include_deleted: bool = False,
    include_group_members: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List flights with optional filters.

    `origin` / `destination` match against airport codes or city names (ilike).
    `q` is a free-text search across flight number, airline, airport, city,
    aircraft, registration and trip name; it also matches values held only by
    an older duplicate of a flight. `status` is 'approved' (default), 'draft'
    (inbox), or 'any'.

    Flights sharing a `grouping_id` are one flight recorded more than once.
    Only the group's primary (newest) record is returned and counted in
    `total` unless `include_group_members` is true. Every flight carries a
    `group` entry (grouping_id, primary_id, is_primary, member_ids), or null
    when it is not grouped.
    """
    identity_filters = [] if include_deleted else list(ACTIVE_FLIGHT_FILTERS)
    if status and status.strip().lower() != "any":
        identity_filters.append(Flight.status == status.strip().lower())
    query = Flight.query.filter(*identity_filters)
    if not include_group_members:
        query = query.filter(is_group_primary(identity_filters))

    if year is not None:
        query = query.filter(func.extract("year", Flight.start_date) == year)
    if airline_code:
        query = query.filter(Flight.airline_code.ilike(airline_code))
    if traveller:
        query = query.filter(Flight.traveller.ilike(traveller))
    if origin:
        term = f"%{origin}%"
        query = query.filter(
            or_(Flight.start_airport.ilike(term), Flight.start_city_name.ilike(term))
        )
    if destination:
        term = f"%{destination}%"
        query = query.filter(
            or_(Flight.end_airport.ilike(term), Flight.end_city_name.ilike(term))
        )
    if q:
        term = f"%{q}%"

        def text_match(entity):
            return or_(
                entity.flight_number.ilike(term),
                entity.airline_code.ilike(term),
                entity.start_airport.ilike(term),
                entity.end_airport.ilike(term),
                entity.start_city_name.ilike(term),
                entity.end_city_name.ilike(term),
                entity.aircraft.ilike(term),
                entity.aircraft_registration.ilike(term),
                entity.trip_name.ilike(term),
            )

        query = query.filter(matches_flight_or_group_member(text_match))

    total = query.count()
    rows = (
        query.order_by(Flight.start_date.desc(), Flight.start_time.desc())
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 500))
        .all()
    )
    groups = group_info_by_flight(rows)

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "flights": [dict(flight_to_dict(f), group=groups[f.id]) for f in rows],
    }


@mcp.tool()
def get_flight(flight_id: int) -> dict[str, Any]:
    """Fetch a single flight by id, including AirNav history if present.

    `group` says whether the record is one of several for the same flight and
    which of them (the newest, `primary_id`) statistics and lists report.
    """
    flight = _active_flights().filter_by(id=flight_id).first()
    if flight is None:
        return {"error": "Flight not found", "id": flight_id}
    payload = flight_to_dict(flight)
    payload["group"] = group_info(flight)
    payload["airnav_histories"] = [
        {
            "id": h.id,
            "dep_date": h.dep_date.isoformat() if h.dep_date else None,
            "callsign": h.callsign,
            "aircraft_registration": h.aircraft_registration,
            "aircraft_type": h.aircraft_type,
            "airline_name": h.airline_name,
            "dep_airport_iata": h.dep_airport_iata,
            "arr_airport_iata": h.arr_airport_iata,
            "scheduled_departure": h.scheduled_departure.isoformat() if h.scheduled_departure else None,
            "actual_departure": h.actual_departure.isoformat() if h.actual_departure else None,
            "scheduled_arrival": h.scheduled_arrival.isoformat() if h.scheduled_arrival else None,
            "actual_arrival": h.actual_arrival.isoformat() if h.actual_arrival else None,
            "duration": h.duration,
            "distance": h.distance,
            "status": h.status,
        }
        for h in flight.airnav_histories
    ]
    return payload


@mcp.tool()
def search_flights(q: str, limit: int = 20) -> dict[str, Any]:
    """Free-text search across flights — shorthand for list_flights(q=...)."""
    return list_flights(q=q, limit=limit)


# ---------------------------------------------------------------------------
# Flights — write
# ---------------------------------------------------------------------------

_AUTO_FILL_DESC = (
    "Fill missing origin/destination city, country and coordinates from earlier "
    "flights that use the same airport codes, and the aircraft type from the "
    "registration. Distance and route direction are always computed when "
    "coordinates are known."
)


_LOOKUP_REGISTRATION_DESC = (
    "After the flight is stored, ask the configured flight-data provider "
    "(FLIGHT_DATA_PROVIDER, currently FlightAware) which aircraft operated it "
    "and fill aircraft_registration, plus aircraft (display name) and "
    "aircraft_type_normalized (ICAO code) when empty. Skipped when a "
    "registration was supplied or the provider cannot see the flight; the "
    "response's registration_lookup says what happened."
)


def _lookup_registration(flight: Flight, *, overwrite: bool = False) -> dict[str, Any]:
    """Fill the aircraft registration from the configured provider and commit.

    Never raises: the flight is already stored, so a failed lookup is reported
    in the returned dict (status applied / found_no_registration / not_found /
    skipped / error) rather than undoing the create.
    """
    provider = active_provider()
    if not overwrite and flight.aircraft_registration:
        return {
            "provider": provider,
            "status": "skipped",
            "reason": "flight already has a registration; pass overwrite=true to replace it",
        }
    try:
        result = lookup_and_record(flight, overwrite_aircraft=overwrite)
    except FlightLookupError as exc:
        status = "not_found" if exc.kind == "not_found" else (
            "error" if exc.kind in ("rate_limited", "provider_error") else "skipped"
        )
        return {"provider": provider, "status": status, "kind": exc.kind, "reason": str(exc)}
    if any(result.applied.values()):
        stamp_revision(flight)
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return {
            "provider": provider,
            "status": "error",
            "kind": "commit_failed",
            "reason": f"lookup succeeded but could not be saved: {exc}",
        }
    out = {
        "provider": provider,
        "status": "applied" if result.aircraft_registration else "found_no_registration",
        "aircraft_registration": result.aircraft_registration,
        "aircraft": result.aircraft,
        "aircraft_type_normalized": result.aircraft_type,
        "history_id": result.history.id,
        "applied": [name for name, changed in result.applied.items() if changed],
    }
    if not result.aircraft_registration:
        out["reason"] = (
            f"{provider_label()} knows this flight but no aircraft is assigned yet "
            "(registrations usually appear within a day of departure); call "
            "lookup_flight_registration(flight_id) closer to the date."
        )
    return out


def _desc(name: str) -> str:
    return FLIGHT_FIELDS[name].description


def _validation_error(errors: dict[str, str], **extra: Any) -> dict[str, Any]:
    return {
        "error": "validation_failed",
        "message": "No changes were made. Fix the listed fields and retry.",
        "field_errors": errors,
        **extra,
    }


def _prepare_new_flight(
    raw: dict[str, Any],
    *,
    auto_fill: bool,
    allow_duplicate: bool,
    seen_keys: Optional[set] = None,
) -> tuple[Optional[Flight], dict[str, Any]]:
    """Validate and build (but do not add) a Flight. Returns (flight, info).

    On success ``info`` carries ``warnings``, ``auto_filled`` and
    ``possible_duplicates``; on failure ``flight`` is None and ``info`` is the
    error payload.
    """
    cleaned, errors, warnings = coerce_flight_fields(raw)
    if not errors:
        errors.update(validate_required_for_create(cleaned))
    if errors:
        return None, _validation_error(errors)

    if cleaned.get("status") is None:
        cleaned["status"] = APPROVED_STATUS
    if cleaned.get("end_date") is None:
        cleaned["end_date"] = cleaned["start_date"]
    if cleaned.get("source_file") is None:
        cleaned["source_file"] = DEFAULT_SOURCE

    duplicates = find_possible_duplicates(cleaned)
    key = duplicate_key(cleaned)
    in_batch = seen_keys is not None and key is not None and key in seen_keys
    if seen_keys is not None and key is not None:
        seen_keys.add(key)
    exact = [d for d in duplicates if d["match"] == "exact"]
    if (exact or in_batch) and not allow_duplicate:
        return None, {
            "error": "possible_duplicate",
            "message": (
                "A flight with the same date, route, flight number and traveller "
                "already exists. Nothing was created. Pass allow_duplicate=true to "
                "create it anyway, or update the existing flight instead."
            ),
            "possible_duplicates": duplicates,
            "duplicate_within_batch": in_batch,
        }

    flight = Flight()
    for name, value in cleaned.items():
        setattr(flight, name, value)
    filled, enrich_warnings = enrich_flight(flight, auto_fill=auto_fill)
    return flight, {
        "warnings": warnings + enrich_warnings,
        "auto_filled": filled,
        "possible_duplicates": duplicates,
    }


def _apply_flight_update(
    flight: Flight,
    raw: dict[str, Any],
    clear_fields: Optional[list[str]],
    *,
    auto_fill: bool,
) -> dict[str, Any]:
    """Validate and apply an update to a loaded Flight without committing.

    On validation failure the flight is left untouched and the returned payload
    has an ``error`` key. Otherwise it reports ``changed`` (old -> new per
    field), ``reset`` (derived fields blanked because their inputs changed),
    ``auto_filled`` and ``warnings``.
    """
    cleaned, errors, warnings = coerce_flight_fields(raw)
    for name in clear_fields or []:
        if name not in FLIGHT_FIELDS:
            errors[name] = "unknown field (see describe_flight_fields)"
        elif name in UNCLEARABLE_FIELDS:
            errors[name] = "cannot be cleared"
        elif name in raw:
            errors[name] = "listed in clear_fields and also given a value"
        else:
            cleaned[name] = None
    if "start_date" in cleaned and cleaned["start_date"] is None:
        errors["start_date"] = "required (YYYY-MM-DD)"
    if "status" in cleaned and cleaned["status"] is None:
        errors["status"] = "must be one of: " + ", ".join(FLIGHT_FIELDS["status"].choices)
    if errors:
        return _validation_error(errors, id=flight.id)

    changed: dict[str, dict[str, Any]] = {}
    for name, value in cleaned.items():
        old = getattr(flight, name)
        if old != value:
            changed[name] = {"from": serialize_value(old), "to": serialize_value(value)}
            setattr(flight, name, value)

    # An airport code change invalidates the location details that came with
    # the old code unless new ones were supplied in the same call.
    reset: list[str] = []
    for side in ("start", "end"):
        if f"{side}_airport" not in changed:
            continue
        for key in ("city_name", "country", "lat", "long"):
            name = f"{side}_{key}"
            if name not in cleaned and getattr(flight, name) is not None:
                setattr(flight, name, None)
                reset.append(name)
    coords_changed = bool(reset) or any(
        name in changed for name in ("start_lat", "start_long", "end_lat", "end_long")
    )
    if coords_changed:
        if "distance" not in cleaned and flight.distance is not None:
            flight.distance = None
            reset.append("distance")
        if "route_direction" not in cleaned and flight.route_direction is not None:
            flight.route_direction = None
            reset.append("route_direction")

    if "aircraft_registration" in changed and "aircraft" not in cleaned and flight.aircraft:
        record = lookup_aircraft(flight.aircraft_registration or "")
        if record is not None and record.type and record.type != flight.aircraft:
            warnings.append(
                f"The aircraft table lists {record.type} for "
                f"{flight.aircraft_registration} but aircraft is still "
                f"'{flight.aircraft}'. Pass aircraft to change it."
            )

    filled, enrich_warnings = enrich_flight(
        flight, auto_fill=auto_fill, exclude_id=flight.id
    )
    return {
        "changed": changed,
        "reset": reset,
        "auto_filled": filled,
        "warnings": warnings + enrich_warnings,
    }


def _flight_fields_from_args(args: dict[str, Any]) -> dict[str, Any]:
    """Pick the Flight field parameters out of a tool's locals(), dropping unset ones."""
    return {k: v for k, v in args.items() if k in FLIGHT_FIELDS and v is not None}


@mcp.tool()
def create_flight(
    start_date: Annotated[str, Field(description=_desc("start_date"))],
    status: Annotated[Optional[str], Field(description=_desc("status"))] = None,
    start_time: Annotated[Optional[str], Field(description=_desc("start_time"))] = None,
    end_date: Annotated[Optional[str], Field(description=_desc("end_date"))] = None,
    end_time: Annotated[Optional[str], Field(description=_desc("end_time"))] = None,
    start_airport: Annotated[Optional[str], Field(description=_desc("start_airport"))] = None,
    start_city_name: Annotated[Optional[str], Field(description=_desc("start_city_name"))] = None,
    start_country: Annotated[Optional[str], Field(description=_desc("start_country"))] = None,
    start_terminal: Annotated[Optional[str], Field(description=_desc("start_terminal"))] = None,
    start_lat: Annotated[Optional[float], Field(description=_desc("start_lat"))] = None,
    start_long: Annotated[Optional[float], Field(description=_desc("start_long"))] = None,
    end_airport: Annotated[Optional[str], Field(description=_desc("end_airport"))] = None,
    end_city_name: Annotated[Optional[str], Field(description=_desc("end_city_name"))] = None,
    end_country: Annotated[Optional[str], Field(description=_desc("end_country"))] = None,
    end_terminal: Annotated[Optional[str], Field(description=_desc("end_terminal"))] = None,
    end_lat: Annotated[Optional[float], Field(description=_desc("end_lat"))] = None,
    end_long: Annotated[Optional[float], Field(description=_desc("end_long"))] = None,
    stops: Annotated[Optional[int], Field(description=_desc("stops"))] = None,
    distance: Annotated[Optional[float], Field(description=_desc("distance"))] = None,
    route_direction: Annotated[Optional[str], Field(description=_desc("route_direction"))] = None,
    airline_code: Annotated[Optional[str], Field(description=_desc("airline_code"))] = None,
    flight_number: Annotated[Optional[str], Field(description=_desc("flight_number"))] = None,
    operating_airline_code: Annotated[Optional[str], Field(description=_desc("operating_airline_code"))] = None,
    operating_flight_number: Annotated[Optional[str], Field(description=_desc("operating_flight_number"))] = None,
    aircraft: Annotated[Optional[str], Field(description=_desc("aircraft"))] = None,
    aircraft_type_normalized: Annotated[Optional[str], Field(description=_desc("aircraft_type_normalized"))] = None,
    aircraft_registration: Annotated[Optional[str], Field(description=_desc("aircraft_registration"))] = None,
    service_class: Annotated[Optional[str], Field(description=_desc("service_class"))] = None,
    ticket_number: Annotated[Optional[str], Field(description=_desc("ticket_number"))] = None,
    traveller: Annotated[Optional[str], Field(description=_desc("traveller"))] = None,
    booking_site: Annotated[Optional[str], Field(description=_desc("booking_site"))] = None,
    supplier_confirmation: Annotated[Optional[str], Field(description=_desc("supplier_confirmation"))] = None,
    booking_date: Annotated[Optional[str], Field(description=_desc("booking_date"))] = None,
    booking_site_phone: Annotated[Optional[str], Field(description=_desc("booking_site_phone"))] = None,
    url: Annotated[Optional[str], Field(description=_desc("url"))] = None,
    activity_id: Annotated[Optional[str], Field(description=_desc("activity_id"))] = None,
    activity_cost: Annotated[Optional[float], Field(description=_desc("activity_cost"))] = None,
    trip_name: Annotated[Optional[str], Field(description=_desc("trip_name"))] = None,
    trip_id: Annotated[Optional[str], Field(description=_desc("trip_id"))] = None,
    trip_type: Annotated[Optional[str], Field(description=_desc("trip_type"))] = None,
    trip_leg_id: Annotated[Optional[int], Field(description=_desc("trip_leg_id"))] = None,
    follow_up: Annotated[Optional[bool], Field(description=_desc("follow_up"))] = None,
    exclude_from_stats: Annotated[Optional[bool], Field(description=_desc("exclude_from_stats"))] = None,
    audit_missing_leg_ignored: Annotated[Optional[bool], Field(description=_desc("audit_missing_leg_ignored"))] = None,
    grouping_id: Annotated[Optional[str], Field(description=_desc("grouping_id"))] = None,
    source_file: Annotated[Optional[str], Field(description=_desc("source_file"))] = None,
    auto_fill: Annotated[bool, Field(description=_AUTO_FILL_DESC)] = True,
    allow_duplicate: Annotated[bool, Field(description=(
        "Create even when a flight with the same date, route, flight number "
        "and traveller already exists."
    ))] = False,
    lookup_registration: Annotated[bool, Field(description=_LOOKUP_REGISTRATION_DESC)] = True,
) -> dict[str, Any]:
    """Create a flight. Every writable Flight column is available as a parameter.

    Required: start_date plus an origin (start_airport or start_city_name) and
    a destination (end_airport or end_city_name). Defaults: end_date =
    start_date, status = 'approved', source_file = 'mcp'. Airport, airline and
    registration codes are uppercased and 'BA123' is split into airline_code
    'BA' + flight_number '123'. All values are validated first; if anything is
    wrong nothing is written and field_errors names each problem. When an
    exact duplicate exists the call refuses with error=possible_duplicate
    unless allow_duplicate=true. Once stored, the configured flight-data
    provider (currently FlightAware) is asked which aircraft operated the
    flight unless lookup_registration=false or a registration was supplied;
    the outcome is reported under registration_lookup. The response echoes
    the stored flight plus auto_filled, warnings and possible_duplicates. Call
    describe_flight_fields for the field catalog and flight_field_values to
    reuse existing labels.
    """
    args = locals()
    flight, info = _prepare_new_flight(
        _flight_fields_from_args(args),
        auto_fill=auto_fill,
        allow_duplicate=allow_duplicate,
    )
    if flight is None:
        return info
    stamp_revision(flight)
    db.session.add(flight)
    _commit_or_rollback()
    lookup = _lookup_registration(flight) if lookup_registration else None
    payload = flight_to_dict(flight)
    payload.update(info)
    if lookup is not None:
        payload["registration_lookup"] = lookup
    return payload


@mcp.tool()
def update_flight(
    flight_id: Annotated[int, Field(description="Id of the flight to update.")],
    status: Annotated[Optional[str], Field(description=_desc("status"))] = None,
    start_date: Annotated[Optional[str], Field(description=_desc("start_date"))] = None,
    start_time: Annotated[Optional[str], Field(description=_desc("start_time"))] = None,
    end_date: Annotated[Optional[str], Field(description=_desc("end_date"))] = None,
    end_time: Annotated[Optional[str], Field(description=_desc("end_time"))] = None,
    start_airport: Annotated[Optional[str], Field(description=_desc("start_airport"))] = None,
    start_city_name: Annotated[Optional[str], Field(description=_desc("start_city_name"))] = None,
    start_country: Annotated[Optional[str], Field(description=_desc("start_country"))] = None,
    start_terminal: Annotated[Optional[str], Field(description=_desc("start_terminal"))] = None,
    start_lat: Annotated[Optional[float], Field(description=_desc("start_lat"))] = None,
    start_long: Annotated[Optional[float], Field(description=_desc("start_long"))] = None,
    end_airport: Annotated[Optional[str], Field(description=_desc("end_airport"))] = None,
    end_city_name: Annotated[Optional[str], Field(description=_desc("end_city_name"))] = None,
    end_country: Annotated[Optional[str], Field(description=_desc("end_country"))] = None,
    end_terminal: Annotated[Optional[str], Field(description=_desc("end_terminal"))] = None,
    end_lat: Annotated[Optional[float], Field(description=_desc("end_lat"))] = None,
    end_long: Annotated[Optional[float], Field(description=_desc("end_long"))] = None,
    stops: Annotated[Optional[int], Field(description=_desc("stops"))] = None,
    distance: Annotated[Optional[float], Field(description=_desc("distance"))] = None,
    route_direction: Annotated[Optional[str], Field(description=_desc("route_direction"))] = None,
    airline_code: Annotated[Optional[str], Field(description=_desc("airline_code"))] = None,
    flight_number: Annotated[Optional[str], Field(description=_desc("flight_number"))] = None,
    operating_airline_code: Annotated[Optional[str], Field(description=_desc("operating_airline_code"))] = None,
    operating_flight_number: Annotated[Optional[str], Field(description=_desc("operating_flight_number"))] = None,
    aircraft: Annotated[Optional[str], Field(description=_desc("aircraft"))] = None,
    aircraft_type_normalized: Annotated[Optional[str], Field(description=_desc("aircraft_type_normalized"))] = None,
    aircraft_registration: Annotated[Optional[str], Field(description=_desc("aircraft_registration"))] = None,
    service_class: Annotated[Optional[str], Field(description=_desc("service_class"))] = None,
    ticket_number: Annotated[Optional[str], Field(description=_desc("ticket_number"))] = None,
    traveller: Annotated[Optional[str], Field(description=_desc("traveller"))] = None,
    booking_site: Annotated[Optional[str], Field(description=_desc("booking_site"))] = None,
    supplier_confirmation: Annotated[Optional[str], Field(description=_desc("supplier_confirmation"))] = None,
    booking_date: Annotated[Optional[str], Field(description=_desc("booking_date"))] = None,
    booking_site_phone: Annotated[Optional[str], Field(description=_desc("booking_site_phone"))] = None,
    url: Annotated[Optional[str], Field(description=_desc("url"))] = None,
    activity_id: Annotated[Optional[str], Field(description=_desc("activity_id"))] = None,
    activity_cost: Annotated[Optional[float], Field(description=_desc("activity_cost"))] = None,
    trip_name: Annotated[Optional[str], Field(description=_desc("trip_name"))] = None,
    trip_id: Annotated[Optional[str], Field(description=_desc("trip_id"))] = None,
    trip_type: Annotated[Optional[str], Field(description=_desc("trip_type"))] = None,
    trip_leg_id: Annotated[Optional[int], Field(description=_desc("trip_leg_id"))] = None,
    follow_up: Annotated[Optional[bool], Field(description=_desc("follow_up"))] = None,
    exclude_from_stats: Annotated[Optional[bool], Field(description=_desc("exclude_from_stats"))] = None,
    audit_missing_leg_ignored: Annotated[Optional[bool], Field(description=_desc("audit_missing_leg_ignored"))] = None,
    grouping_id: Annotated[Optional[str], Field(description=_desc("grouping_id"))] = None,
    source_file: Annotated[Optional[str], Field(description=_desc("source_file"))] = None,
    clear_fields: Annotated[Optional[list[str]], Field(description=(
        "Names of fields to blank (set to null). Needed because omitted "
        "parameters are left unchanged. start_date and status cannot be cleared."
    ))] = None,
    auto_fill: Annotated[bool, Field(description=_AUTO_FILL_DESC)] = True,
) -> dict[str, Any]:
    """Update a flight. Only the parameters you pass are changed.

    Omitted parameters keep their current value; use clear_fields to blank a
    field. Values are validated and normalised exactly as in create_flight and
    nothing is written if any field is invalid. Changing an airport code
    blanks that side's city/country/coordinates (unless supplied in the same
    call) and re-derives them, along with distance and route_direction, via
    auto_fill. The response echoes the stored flight plus changed (old -> new),
    reset, auto_filled and warnings; no_changes=true means nothing differed.
    """
    args = locals()
    flight = _active_flights().filter_by(id=flight_id).first()
    if flight is None:
        return {"error": "Flight not found", "id": flight_id}

    result = _apply_flight_update(
        flight, _flight_fields_from_args(args), clear_fields, auto_fill=auto_fill
    )
    if "error" in result:
        return result
    if not (result["changed"] or result["reset"] or result["auto_filled"]):
        payload = flight_to_dict(flight)
        payload.update(result)
        payload["no_changes"] = True
        return payload

    flight.updated_at = _now()
    stamp_revision(flight)
    _commit_or_rollback()
    payload = flight_to_dict(flight)
    payload.update(result)
    return payload


def _assert_exposes_all_fields(fn) -> None:
    """Fail at import time if a tool signature stops covering the catalog."""
    missing = set(FLIGHT_FIELDS) - set(inspect.signature(fn).parameters)
    if missing:  # pragma: no cover - guards against schema drift
        raise RuntimeError(
            f"{fn.__name__} is missing Flight field parameters: {sorted(missing)}"
        )


_assert_exposes_all_fields(create_flight)
_assert_exposes_all_fields(update_flight)


@mcp.tool()
def describe_flight_fields(
    group: Annotated[Optional[str], Field(description=(
        "Restrict to one group: " + ", ".join(FIELD_GROUPS) + "."
    ))] = None,
) -> dict[str, Any]:
    """Catalog of every writable Flight field.

    Returns each field's type, group, description, allowed values and limits,
    plus the create-time requirements, defaults and normalisation rules that
    create_flight / update_flight / bulk_* apply.
    """
    fields = field_catalog()
    if group:
        if group not in FIELD_GROUPS:
            return {"error": "unknown group", "groups": list(FIELD_GROUPS)}
        fields = [f for f in fields if f["group"] == group]
    return {
        "groups": list(FIELD_GROUPS),
        "required_on_create": [
            "start_date",
            "start_airport or start_city_name",
            "end_airport or end_city_name",
        ],
        "defaults_on_create": {
            "status": APPROVED_STATUS,
            "end_date": "same as start_date",
            "source_file": DEFAULT_SOURCE,
        },
        "normalisation": [
            "airport, airline and registration codes are uppercased",
            "flight_number / operating_flight_number keep digits only; a "
            "prefix such as 'BA123' moves into the matching airline code",
            "dates are YYYY-MM-DD, times are HH:MM (24-hour)",
            "activity_cost is kept to two decimal places",
            "empty strings are stored as null",
        ],
        "auto_filled_when_missing": [
            "start/end city, country and coordinates (from earlier flights "
            "with the same airport code)",
            "aircraft and aircraft_type_normalized (from the aircraft table, "
            "via aircraft_registration)",
            "distance and route_direction (from coordinates)",
            "aircraft_registration, plus aircraft (display name from the "
            "built-in ICAO type map, else the aircraft table/ADSBDB) and "
            "aircraft_type_normalized (ICAO designator) when empty, from the "
            "configured flight-data provider (currently FlightAware) for "
            "flights it can still see: 10 days back to 2 days ahead; reported "
            "under registration_lookup, disable with lookup_registration=false",
        ],
        "fields": fields,
    }


@mcp.tool()
def flight_field_values(
    field: Annotated[str, Field(description="One of: " + ", ".join(ENUMERABLE_FIELDS) + ".")],
    q: Annotated[Optional[str], Field(description="Optional case-insensitive substring filter.")] = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Distinct values already stored for an enum-like Flight field.

    Returns each value with its usage count and most recent flight date, most
    used first. Use it before creating or updating flights so traveller names,
    service classes, trip types, airline codes and similar stay consistent.
    """
    if field not in ENUMERABLE_FIELDS:
        return {
            "error": "field must be one of: " + ", ".join(ENUMERABLE_FIELDS),
            "field": field,
        }
    column = getattr(Flight, field)
    query = (
        db.session.query(column, func.count(Flight.id), func.max(Flight.start_date))
        .filter(*ACTIVE_FLIGHT_FILTERS, column.isnot(None), column != "")
        .filter(is_group_primary(ACTIVE_FLIGHT_FILTERS))
    )
    if q:
        query = query.filter(column.ilike(f"%{q}%"))
    rows = (
        query.group_by(column)
        .order_by(func.count(Flight.id).desc(), column.asc())
        .limit(min(max(limit, 1), 500))
        .all()
    )
    return {
        "field": field,
        "values": [
            {"value": value, "count": int(count), "last_flown": serialize_date(last)}
            for value, count, last in rows
        ],
    }


@mcp.tool()
def delete_flight(flight_id: int) -> dict[str, Any]:
    """Soft-delete a flight (sets deleted_at; reversible via restore_flight)."""
    flight = _active_flights().filter_by(id=flight_id).first()
    if flight is None:
        return {"error": "Flight not found", "id": flight_id}

    flight.deleted_at = _now()
    flight.updated_at = _now()
    stamp_revision(flight)
    _commit_or_rollback()
    return {"status": "deleted", "id": flight_id}


@mcp.tool()
def restore_flight(flight_id: int) -> dict[str, Any]:
    """Undo a soft-delete by clearing deleted_at."""
    flight = Flight.query.filter_by(id=flight_id).first()
    if flight is None:
        return {"error": "Flight not found", "id": flight_id}
    if flight.deleted_at is None:
        return {"status": "already_active", "id": flight_id}

    flight.deleted_at = None
    flight.updated_at = _now()
    stamp_revision(flight)
    _commit_or_rollback()
    return {"status": "restored", "id": flight_id}


@mcp.tool()
def lookup_flight_registration(
    flight_id: Annotated[int, Field(description="Id of the flight to look up.")],
    overwrite: Annotated[bool, Field(description=(
        "Replace an existing aircraft and registration with the provider's "
        "answer instead of only filling empty fields."
    ))] = False,
) -> dict[str, Any]:
    """Ask the configured flight-data provider (currently FlightAware) which aircraft operated a flight.

    Fills aircraft_registration and, when empty, aircraft (display name such
    as "Boeing 777-200") and aircraft_type_normalized (ICAO designator),
    and stores the provider's record as flight history. FlightAware only covers flights from 10 days ago to 2 days ahead,
    and registrations for future flights usually appear within a day of
    departure, so re-run this closer to the date when status is
    found_no_registration. Nothing else on the flight changes.
    """
    flight = _active_flights().filter_by(id=flight_id).first()
    if flight is None:
        return {"error": "Flight not found", "id": flight_id}
    result = _lookup_registration(flight, overwrite=overwrite)
    return {
        "id": flight.id,
        **result,
        "flight_aircraft": flight.aircraft,
        "flight_aircraft_registration": flight.aircraft_registration,
    }


@mcp.tool()
def set_follow_up(flight_id: int, value: bool) -> dict[str, Any]:
    """Set the follow_up flag explicitly (true/false)."""
    flight = _active_flights().filter_by(id=flight_id).first()
    if flight is None:
        return {"error": "Flight not found", "id": flight_id}

    flight.follow_up = bool(value)
    flight.updated_at = _now()
    stamp_revision(flight)
    _commit_or_rollback()
    return {"id": flight_id, "follow_up": flight.follow_up}


@mcp.tool()
def set_exclude_from_stats(flight_id: int, value: bool) -> dict[str, Any]:
    """Set the exclude_from_stats flag explicitly (true/false)."""
    flight = _active_flights().filter_by(id=flight_id).first()
    if flight is None:
        return {"error": "Flight not found", "id": flight_id}

    flight.exclude_from_stats = bool(value)
    flight.updated_at = _now()
    stamp_revision(flight)
    _commit_or_rollback()
    return {"id": flight_id, "exclude_from_stats": flight.exclude_from_stats}


# ---------------------------------------------------------------------------
# Aircraft
# ---------------------------------------------------------------------------

@mcp.tool()
def list_aircraft(
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List aircraft, optionally filtered by registration/type/manufacturer."""
    query = Aircraft.query
    if q:
        term = f"%{q}%"
        query = query.filter(
            or_(
                Aircraft.registration.ilike(term),
                Aircraft.type.ilike(term),
                Aircraft.icao_type.ilike(term),
                Aircraft.manufacturer.ilike(term),
                Aircraft.registered_owner.ilike(term),
            )
        )
    total = query.count()
    rows = (
        query.order_by(Aircraft.registration.asc())
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 500))
        .all()
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "aircraft": [aircraft_to_dict(a) for a in rows],
    }


@mcp.tool()
def get_aircraft(registration: str) -> dict[str, Any]:
    """Look up an aircraft by registration, with the user's flights on it."""
    reg = (registration or "").strip().upper()
    if not reg:
        return {"error": "registration is required"}

    ac = Aircraft.query.filter(func.upper(Aircraft.registration) == reg).first()
    flights = (
        _approved_active_flights()
        .filter(func.upper(Flight.aircraft_registration) == reg)
        .order_by(Flight.start_date.desc())
        .all()
    )
    return {
        "aircraft": aircraft_to_dict(ac) if ac else None,
        "flight_count": len(flights),
        "flights": [flight_to_dict(f) for f in flights],
    }


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def _stats_base(year: Optional[int]):
    """Flights that count: approved, active, not excluded, one per duplicate group."""
    base = reporting_flights_query()
    if year is not None:
        base = base.filter(func.extract("year", Flight.start_date) == year)
    return base


@mcp.tool()
def stats_summary(year: Optional[int] = None) -> dict[str, Any]:
    """Aggregate counts and miles.

    Deleted and excluded flights are left out, and a duplicate group (flights
    sharing a grouping_id) counts once.
    """
    base = _stats_base(year)
    total_flights = base.count()
    total_miles = base.with_entities(
        func.coalesce(func.sum(Flight.distance), 0)
    ).scalar() or 0
    countries = base.with_entities(
        func.count(func.distinct(Flight.start_country))
    ).filter(Flight.start_country.isnot(None)).scalar() or 0
    cities = base.with_entities(
        func.count(func.distinct(Flight.start_city_name))
    ).filter(Flight.start_city_name.isnot(None)).scalar() or 0
    airlines = base.with_entities(
        func.count(func.distinct(Flight.airline_code))
    ).filter(Flight.airline_code.isnot(None)).scalar() or 0
    aircraft_types = base.with_entities(
        func.count(func.distinct(Flight.aircraft))
    ).filter(Flight.aircraft.isnot(None)).scalar() or 0
    return {
        "year": year,
        "total_flights": total_flights,
        "total_miles": float(total_miles),
        "countries": countries,
        "cities": cities,
        "airlines": airlines,
        "aircraft_types": aircraft_types,
    }


@mcp.tool()
def flights_by_year() -> dict[str, Any]:
    """Count of flights grouped by year (descending)."""
    rows = (
        db.session.query(
            func.extract("year", Flight.start_date).label("year"),
            func.count(Flight.id).label("count"),
            func.coalesce(func.sum(Flight.distance), 0).label("miles"),
        )
        .filter(*REPORTABLE_FLIGHT_FILTERS, is_group_primary())
        .group_by("year")
        .order_by(func.extract("year", Flight.start_date).desc())
        .all()
    )
    return {
        "years": [
            {"year": int(r.year), "count": int(r.count), "miles": float(r.miles)}
            for r in rows
            if r.year is not None
        ]
    }


@mcp.tool()
def top_routes(limit: int = 10, year: Optional[int] = None) -> dict[str, Any]:
    """Top origin -> destination routes by flight count."""
    base = _stats_base(year).filter(
        Flight.start_airport.isnot(None), Flight.end_airport.isnot(None)
    )
    rows = (
        base.with_entities(
            Flight.start_airport,
            Flight.end_airport,
            func.count(Flight.id).label("count"),
        )
        .group_by(Flight.start_airport, Flight.end_airport)
        .order_by(func.count(Flight.id).desc())
        .limit(min(max(limit, 1), 100))
        .all()
    )
    return {
        "routes": [
            {"origin": r[0], "destination": r[1], "count": int(r[2])} for r in rows
        ]
    }


@mcp.tool()
def top_airlines(limit: int = 10, year: Optional[int] = None) -> dict[str, Any]:
    """Top airlines by flight count."""
    base = _stats_base(year).filter(Flight.airline_code.isnot(None))
    rows = (
        base.with_entities(
            Flight.airline_code,
            func.count(Flight.id).label("count"),
            func.coalesce(func.sum(Flight.distance), 0).label("miles"),
        )
        .group_by(Flight.airline_code)
        .order_by(func.count(Flight.id).desc())
        .limit(min(max(limit, 1), 100))
        .all()
    )
    return {
        "airlines": [
            {"airline_code": r[0], "count": int(r[1]), "miles": float(r[2])}
            for r in rows
        ]
    }


# ---------------------------------------------------------------------------
# Trips & TripLegs
# ---------------------------------------------------------------------------

def _active_trips():
    return Trip.query.filter(Trip.deleted_at.is_(None))


def _trip_payload(trip: Trip) -> dict[str, Any]:
    payload = trip_to_dict(trip)
    payload["legs"] = [
        trip_leg_to_dict(leg) for leg in trip.legs if leg.deleted_at is None
    ]
    return payload


@mcp.tool()
def list_trips(
    q: Optional[str] = None,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List trips ordered by start_date desc. `q` matches name/code/notes (ilike)."""
    query = Trip.query if include_deleted else _active_trips()
    if q:
        term = f"%{q}%"
        query = query.filter(
            or_(Trip.name.ilike(term), Trip.trip_code.ilike(term), Trip.notes.ilike(term))
        )
    total = query.count()
    rows = (
        query.order_by(Trip.start_date.desc().nullslast(), Trip.id.desc())
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 500))
        .all()
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "trips": [_trip_payload(t) for t in rows],
    }


@mcp.tool()
def get_trip(trip_id: int) -> dict[str, Any]:
    """Fetch a single trip with its active legs."""
    trip = Trip.query.filter_by(id=trip_id).first()
    if trip is None:
        return {"error": "Trip not found", "id": trip_id}
    return _trip_payload(trip)


@mcp.tool()
def create_trip(fields: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Create a trip. Accepts any Trip writable fields (name, trip_code, start_date, ...)."""
    trip = Trip()
    apply_trip_fields(trip, fields or {})
    stamp_revision(trip)
    db.session.add(trip)
    _commit_or_rollback()
    return _trip_payload(trip)


@mcp.tool()
def update_trip(trip_id: int, fields: dict[str, Any]) -> dict[str, Any]:
    """Update a trip. Unknown keys are ignored."""
    trip = _active_trips().filter_by(id=trip_id).first()
    if trip is None:
        return {"error": "Trip not found", "id": trip_id}
    apply_trip_fields(trip, fields or {})
    trip.updated_at = _now()
    stamp_revision(trip)
    _commit_or_rollback()
    return _trip_payload(trip)


@mcp.tool()
def delete_trip(trip_id: int) -> dict[str, Any]:
    """Soft-delete a trip and cascade soft-delete to its legs."""
    trip = _active_trips().filter_by(id=trip_id).first()
    if trip is None:
        return {"error": "Trip not found", "id": trip_id}
    now = _now()
    trip.deleted_at = now
    trip.updated_at = now
    stamp_revision(trip)
    for leg in trip.legs:
        if leg.deleted_at is None:
            leg.deleted_at = now
            leg.updated_at = now
            stamp_revision(leg)
    _commit_or_rollback()
    return {"status": "deleted", "id": trip_id}


@mcp.tool()
def restore_trip(trip_id: int) -> dict[str, Any]:
    """Restore a soft-deleted trip. Does not auto-restore its legs."""
    trip = Trip.query.filter_by(id=trip_id).first()
    if trip is None:
        return {"error": "Trip not found", "id": trip_id}
    if trip.deleted_at is None:
        return {"status": "already_active", "id": trip_id}
    trip.deleted_at = None
    trip.updated_at = _now()
    stamp_revision(trip)
    _commit_or_rollback()
    return {"status": "restored", "id": trip_id}


@mcp.tool()
def create_trip_leg(trip_id: int, fields: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Add a leg to a trip. Accepts any TripLeg writable fields."""
    trip = _active_trips().filter_by(id=trip_id).first()
    if trip is None:
        return {"error": "Trip not found", "id": trip_id}
    leg = TripLeg(trip_id=trip_id)
    apply_leg_fields(leg, fields or {})
    stamp_revision(leg)
    db.session.add(leg)
    trip.updated_at = _now()
    stamp_revision(trip)
    _commit_or_rollback()
    return trip_leg_to_dict(leg)


@mcp.tool()
def update_trip_leg(leg_id: int, fields: dict[str, Any]) -> dict[str, Any]:
    """Update a single trip leg by id."""
    leg = TripLeg.query.filter_by(id=leg_id).first()
    if leg is None or leg.deleted_at is not None:
        return {"error": "Leg not found", "id": leg_id}
    apply_leg_fields(leg, fields or {})
    leg.updated_at = _now()
    stamp_revision(leg)
    _commit_or_rollback()
    return trip_leg_to_dict(leg)


@mcp.tool()
def delete_trip_leg(leg_id: int) -> dict[str, Any]:
    """Soft-delete a trip leg."""
    leg = TripLeg.query.filter_by(id=leg_id).first()
    if leg is None or leg.deleted_at is not None:
        return {"error": "Leg not found", "id": leg_id}
    leg.deleted_at = _now()
    leg.updated_at = _now()
    stamp_revision(leg)
    _commit_or_rollback()
    return {"status": "deleted", "id": leg_id}


# ---------------------------------------------------------------------------
# Aircraft writes
# ---------------------------------------------------------------------------

_AIRCRAFT_WRITABLE = {
    "type", "icao_type", "manufacturer", "mode_s",
    "registered_owner_country_iso_name", "registered_owner_country_name",
    "registered_owner_operator_flag_code", "registered_owner",
    "url_photo", "url_photo_thumbnail", "source_url",
}


def _apply_aircraft_fields(ac: Aircraft, data: dict[str, Any]) -> None:
    for key, val in (data or {}).items():
        if key in _AIRCRAFT_WRITABLE:
            setattr(ac, key, val)


@mcp.tool()
def upsert_aircraft(
    registration: str,
    fields: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Create or update an Aircraft by registration (case-insensitive)."""
    reg = (registration or "").strip().upper()
    if not reg:
        return {"error": "registration is required"}
    ac = Aircraft.query.filter(func.upper(Aircraft.registration) == reg).first()
    created = False
    if ac is None:
        ac = Aircraft(registration=reg)
        db.session.add(ac)
        created = True
    _apply_aircraft_fields(ac, fields or {})
    stamp_revision(ac)
    _commit_or_rollback()
    payload = aircraft_to_dict(ac)
    payload["_created"] = created
    return payload


@mcp.tool()
def delete_aircraft(registration: str) -> dict[str, Any]:
    """Hard-delete an Aircraft row. Flights referencing this registration are untouched."""
    reg = (registration or "").strip().upper()
    if not reg:
        return {"error": "registration is required"}
    ac = Aircraft.query.filter(func.upper(Aircraft.registration) == reg).first()
    if ac is None:
        return {"error": "Aircraft not found", "registration": reg}
    db.session.delete(ac)
    _commit_or_rollback()
    return {"status": "deleted", "registration": reg}


# ---------------------------------------------------------------------------
# Achievement badges
# ---------------------------------------------------------------------------

_BADGE_WRITABLE = {
    "name", "description", "category", "badge_type", "threshold_value",
    "icon_emoji", "icon_url", "display_order", "is_active",
}


def _apply_badge_fields(badge: AchievementBadge, data: dict[str, Any]) -> None:
    for key, val in (data or {}).items():
        if key not in _BADGE_WRITABLE:
            continue
        if key in {"threshold_value", "display_order"}:
            setattr(badge, key, int(val) if val is not None and val != "" else None)
        elif key == "is_active":
            setattr(badge, key, bool(val) if val is not None else True)
        else:
            setattr(badge, key, val)


@mcp.tool()
def list_badges(
    active_only: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    """List achievement badges, ordered by display_order then id."""
    query = AchievementBadge.query
    if active_only:
        query = query.filter(AchievementBadge.is_active.is_(True))
    total = query.count()
    rows = (
        query.order_by(AchievementBadge.display_order.asc(), AchievementBadge.id.asc())
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 500))
        .all()
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "badges": [badge_to_dict(b) for b in rows],
    }


@mcp.tool()
def get_badge(badge_id: int) -> dict[str, Any]:
    """Fetch a single badge by id."""
    badge = AchievementBadge.query.filter_by(id=badge_id).first()
    if badge is None:
        return {"error": "Badge not found", "id": badge_id}
    return badge_to_dict(badge)


@mcp.tool()
def create_badge(
    name: str,
    badge_type: str,
    threshold_value: int,
    description: Optional[str] = None,
    category: Optional[str] = None,
    icon_emoji: Optional[str] = None,
    icon_url: Optional[str] = None,
    display_order: int = 0,
    is_active: bool = True,
) -> dict[str, Any]:
    """Create a new achievement badge. `name` must be unique."""
    if not name or not badge_type or threshold_value is None:
        return {"error": "name, badge_type, and threshold_value are required"}
    if AchievementBadge.query.filter_by(name=name).first() is not None:
        return {"error": "Badge name already exists", "name": name}
    badge = AchievementBadge(
        name=name, badge_type=badge_type, threshold_value=int(threshold_value)
    )
    _apply_badge_fields(badge, {
        "description": description, "category": category,
        "icon_emoji": icon_emoji, "icon_url": icon_url,
        "display_order": display_order, "is_active": is_active,
    })
    stamp_revision(badge)
    db.session.add(badge)
    _commit_or_rollback()
    return badge_to_dict(badge)


@mcp.tool()
def update_badge(badge_id: int, fields: dict[str, Any]) -> dict[str, Any]:
    """Update an achievement badge. Pass is_active=false to deactivate."""
    badge = AchievementBadge.query.filter_by(id=badge_id).first()
    if badge is None:
        return {"error": "Badge not found", "id": badge_id}
    _apply_badge_fields(badge, fields or {})
    badge.updated_at = _now()
    stamp_revision(badge)
    _commit_or_rollback()
    return badge_to_dict(badge)


@mcp.tool()
def delete_badge(badge_id: int) -> dict[str, Any]:
    """Hard-delete a badge. Prefer update_badge(is_active=false) for safety."""
    badge = AchievementBadge.query.filter_by(id=badge_id).first()
    if badge is None:
        return {"error": "Badge not found", "id": badge_id}
    db.session.delete(badge)
    _commit_or_rollback()
    return {"status": "deleted", "id": badge_id}


# ---------------------------------------------------------------------------
# AirNav history (FlightHistoryAirNavRadar) — CRUD
# ---------------------------------------------------------------------------

_AIRNAV_DATE_FIELDS = {"dep_date"}
_AIRNAV_DATETIME_FIELDS = {
    "scheduled_departure", "estimated_departure", "actual_departure",
    "actual_takeoff", "calculated_takeoff",
    "scheduled_arrival", "estimated_arrival", "actual_arrival",
    "actual_landing", "calculated_landing",
    "created", "updated",
}
_AIRNAV_FLOAT_FIELDS = {
    "dep_airport_latitude", "dep_airport_longitude", "dep_airport_tz_diff_utc",
    "arr_airport_latitude", "arr_airport_longitude", "arr_airport_tz_diff_utc",
    "latitude", "longitude",
}
_AIRNAV_INT_FIELDS = {"flight_id", "squawk_code", "distance", "duration", "planned_duration"}
_AIRNAV_WRITABLE = {
    "flight_id", "dep_date", "callsign", "flight_number_iata", "flight_number_icao",
    "aircraft_registration", "aircraft_mode_s", "aircraft_serial_number",
    "aircraft_type", "aircraft_classes", "aircraft_type_description",
    "airline_iata", "airline_icao", "airline_name",
    "dep_airport_icao", "dep_airport_iata", "dep_airport_name", "dep_airport_city",
    "dep_airport_state", "dep_airport_country", "dep_airport_country_iso2",
    "dep_airport_country_iso3", "dep_airport_latitude", "dep_airport_longitude",
    "dep_airport_tz", "dep_airport_tz_diff_utc",
    "arr_airport_icao", "arr_airport_iata", "arr_airport_name", "arr_airport_city",
    "arr_airport_state", "arr_airport_country", "arr_airport_country_iso2",
    "arr_airport_country_iso3", "arr_airport_latitude", "arr_airport_longitude",
    "arr_airport_tz", "arr_airport_tz_diff_utc",
    "scheduled_departure", "estimated_departure", "actual_departure",
    "actual_takeoff", "calculated_takeoff",
    "scheduled_arrival", "estimated_arrival", "actual_arrival",
    "actual_landing", "calculated_landing",
    "departure_status", "departure_delay_reason", "departure_delay_detail",
    "departure_gate", "departure_terminal",
    "arrival_status", "arrival_delay_reason", "arrival_delay_detail",
    "latitude", "longitude", "squawk_code", "distance", "duration", "planned_duration",
    "source", "created", "updated",
    "flight_url", "flight_kml", "flight_csv", "flight_geojson",
    "icao_route", "waypoints", "status", "raw_payload",
}


def _apply_airnav_fields(h: FlightHistoryAirNavRadar, data: dict[str, Any]) -> None:
    for key, val in (data or {}).items():
        if key not in _AIRNAV_WRITABLE:
            continue
        if key in _AIRNAV_DATE_FIELDS:
            setattr(h, key, parse_date(val))
        elif key in _AIRNAV_DATETIME_FIELDS:
            setattr(h, key, parse_datetime(val))
        elif key in _AIRNAV_FLOAT_FIELDS:
            setattr(h, key, float(val) if val is not None and val != "" else None)
        elif key in _AIRNAV_INT_FIELDS:
            setattr(h, key, int(val) if val is not None and val != "" else None)
        else:
            setattr(h, key, val)


def _airnav_to_dict(h: FlightHistoryAirNavRadar) -> dict[str, Any]:
    return {
        "id": h.id,
        "flight_id": h.flight_id,
        "dep_date": serialize_date(h.dep_date),
        "callsign": h.callsign,
        "flight_number_iata": h.flight_number_iata,
        "flight_number_icao": h.flight_number_icao,
        "aircraft_registration": h.aircraft_registration,
        "aircraft_type": h.aircraft_type,
        "aircraft_type_description": h.aircraft_type_description,
        "airline_iata": h.airline_iata,
        "airline_icao": h.airline_icao,
        "airline_name": h.airline_name,
        "dep_airport_icao": h.dep_airport_icao,
        "dep_airport_iata": h.dep_airport_iata,
        "dep_airport_name": h.dep_airport_name,
        "dep_airport_city": h.dep_airport_city,
        "dep_airport_country": h.dep_airport_country,
        "dep_airport_latitude": h.dep_airport_latitude,
        "dep_airport_longitude": h.dep_airport_longitude,
        "arr_airport_icao": h.arr_airport_icao,
        "arr_airport_iata": h.arr_airport_iata,
        "arr_airport_name": h.arr_airport_name,
        "arr_airport_city": h.arr_airport_city,
        "arr_airport_country": h.arr_airport_country,
        "arr_airport_latitude": h.arr_airport_latitude,
        "arr_airport_longitude": h.arr_airport_longitude,
        "scheduled_departure": serialize_date(h.scheduled_departure),
        "estimated_departure": serialize_date(h.estimated_departure),
        "actual_departure": serialize_date(h.actual_departure),
        "actual_takeoff": serialize_date(h.actual_takeoff),
        "scheduled_arrival": serialize_date(h.scheduled_arrival),
        "estimated_arrival": serialize_date(h.estimated_arrival),
        "actual_arrival": serialize_date(h.actual_arrival),
        "actual_landing": serialize_date(h.actual_landing),
        "departure_status": h.departure_status,
        "departure_gate": h.departure_gate,
        "departure_terminal": h.departure_terminal,
        "arrival_status": h.arrival_status,
        "distance": h.distance,
        "duration": h.duration,
        "planned_duration": h.planned_duration,
        "source": h.source,
        "status": h.status,
        "flight_url": h.flight_url,
        "icao_route": h.icao_route,
        "created_at": serialize_date(h.created_at),
        "updated_at": serialize_date(h.updated_at),
    }


@mcp.tool()
def list_airnav_history(
    flight_id: Optional[int] = None,
    aircraft_registration: Optional[str] = None,
    dep_date_from: Optional[str] = None,
    dep_date_to: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List AirNav history rows. Filter by flight, registration, or dep_date range."""
    query = FlightHistoryAirNavRadar.query
    if flight_id is not None:
        query = query.filter(FlightHistoryAirNavRadar.flight_id == flight_id)
    if aircraft_registration:
        query = query.filter(
            func.upper(FlightHistoryAirNavRadar.aircraft_registration)
            == aircraft_registration.strip().upper()
        )
    d_from = parse_date(dep_date_from) if dep_date_from else None
    d_to = parse_date(dep_date_to) if dep_date_to else None
    if d_from:
        query = query.filter(FlightHistoryAirNavRadar.dep_date >= d_from)
    if d_to:
        query = query.filter(FlightHistoryAirNavRadar.dep_date <= d_to)
    total = query.count()
    rows = (
        query.order_by(
            FlightHistoryAirNavRadar.dep_date.desc(),
            FlightHistoryAirNavRadar.id.desc(),
        )
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 500))
        .all()
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "histories": [_airnav_to_dict(h) for h in rows],
    }


@mcp.tool()
def get_airnav_history(history_id: int) -> dict[str, Any]:
    """Fetch a single AirNav history record by id."""
    h = FlightHistoryAirNavRadar.query.filter_by(id=history_id).first()
    if h is None:
        return {"error": "AirNav history not found", "id": history_id}
    return _airnav_to_dict(h)


@mcp.tool()
def create_airnav_history(
    flight_id: int,
    dep_date: str,
    fields: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Create a new AirNav history row attached to a flight.

    `flight_id` must point to an existing (non-deleted) flight.
    `dep_date` is required (YYYY-MM-DD).
    """
    flight = _active_flights().filter_by(id=flight_id).first()
    if flight is None:
        return {"error": "Flight not found", "flight_id": flight_id}
    d = parse_date(dep_date)
    if d is None:
        return {"error": "dep_date must be YYYY-MM-DD"}
    payload = dict(fields or {})
    raw = payload.get("raw_payload")
    if raw is None:
        raw = {}
    h = FlightHistoryAirNavRadar(flight_id=flight_id, dep_date=d, raw_payload=raw)
    payload.pop("flight_id", None)
    payload.pop("dep_date", None)
    payload.pop("raw_payload", None)
    _apply_airnav_fields(h, payload)
    db.session.add(h)
    _commit_or_rollback()
    return _airnav_to_dict(h)


@mcp.tool()
def update_airnav_history(history_id: int, fields: dict[str, Any]) -> dict[str, Any]:
    """Update an AirNav history record."""
    h = FlightHistoryAirNavRadar.query.filter_by(id=history_id).first()
    if h is None:
        return {"error": "AirNav history not found", "id": history_id}
    _apply_airnav_fields(h, fields or {})
    h.updated_at = _now()
    _commit_or_rollback()
    return _airnav_to_dict(h)


@mcp.tool()
def delete_airnav_history(history_id: int) -> dict[str, Any]:
    """Hard-delete an AirNav history row (no soft-delete column)."""
    h = FlightHistoryAirNavRadar.query.filter_by(id=history_id).first()
    if h is None:
        return {"error": "AirNav history not found", "id": history_id}
    db.session.delete(h)
    _commit_or_rollback()
    return {"status": "deleted", "id": history_id}


# ---------------------------------------------------------------------------
# Raw FlightHistory + positions (read-only — machine-generated)
# ---------------------------------------------------------------------------

def _flight_position_to_dict(p: FlightPosition) -> dict[str, Any]:
    return {
        "id": p.id,
        "history_id": p.history_id,
        "altitude": p.altitude,
        "direction": p.direction,
        "horizontal_speed": p.horizontal_speed,
        "vertical_speed": p.vertical_speed,
        "is_ground": p.is_ground,
        "latitude": p.latitude,
        "longitude": p.longitude,
        "position_updated": serialize_date(p.position_updated),
    }


def _flight_history_to_dict(
    h: FlightHistory, include_positions: bool = False
) -> dict[str, Any]:
    payload = {
        "id": h.id,
        "flight_id": h.flight_id,
        "dep_iata": h.dep_iata,
        "dep_icao": h.dep_icao,
        "arr_iata": h.arr_iata,
        "arr_icao": h.arr_icao,
        "dep_date": serialize_date(h.dep_date),
        "dep_scheduled_time": serialize_date(h.dep_scheduled_time),
        "arr_scheduled_time": serialize_date(h.arr_scheduled_time),
        "airline_iata": h.airline_iata,
        "airline_icao": h.airline_icao,
        "flight_iata": h.flight_iata,
        "flight_icao": h.flight_icao,
        "aircraft_icao": h.aircraft_icao,
        "aircraft_icao24": h.aircraft_icao24,
        "aircraft_reg_number": h.aircraft_reg_number,
        "status": h.status,
        "created_at": serialize_date(h.created_at),
        "updated_at": serialize_date(h.updated_at),
    }
    if include_positions:
        payload["positions"] = [_flight_position_to_dict(p) for p in h.positions]
    return payload


@mcp.tool()
def list_flight_history(
    flight_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List aviation-edge FlightHistory records (read-only)."""
    query = FlightHistory.query
    if flight_id is not None:
        query = query.filter(FlightHistory.flight_id == flight_id)
    total = query.count()
    rows = (
        query.order_by(FlightHistory.dep_date.desc(), FlightHistory.id.desc())
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 500))
        .all()
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "histories": [_flight_history_to_dict(h) for h in rows],
    }


@mcp.tool()
def get_flight_history(
    history_id: int, include_positions: bool = True
) -> dict[str, Any]:
    """Fetch a FlightHistory row, optionally with all of its FlightPositions."""
    h = FlightHistory.query.filter_by(id=history_id).first()
    if h is None:
        return {"error": "Flight history not found", "id": history_id}
    return _flight_history_to_dict(h, include_positions=include_positions)


# ---------------------------------------------------------------------------
# Sync & bulk ops
# ---------------------------------------------------------------------------

@mcp.tool()
def get_sync_revision() -> dict[str, Any]:
    """Return the current global sync revision counter."""
    return {"current_revision": SyncState.current()}


@mcp.tool()
def changes_since(since_revision: int, limit: int = 200) -> dict[str, Any]:
    """Return entities with sync_revision > since_revision.

    Spans flights, trips, trip legs, aircraft, and badges. Soft-deleted rows are
    included with their deleted_at populated so callers can mirror deletions.
    """
    limit = min(max(limit, 1), 1000)
    flights = (
        Flight.query.filter(Flight.sync_revision > since_revision)
        .order_by(Flight.sync_revision.asc())
        .limit(limit)
        .all()
    )
    trips = (
        Trip.query.filter(Trip.sync_revision > since_revision)
        .order_by(Trip.sync_revision.asc())
        .limit(limit)
        .all()
    )
    legs = (
        TripLeg.query.filter(TripLeg.sync_revision > since_revision)
        .order_by(TripLeg.sync_revision.asc())
        .limit(limit)
        .all()
    )
    aircraft = (
        Aircraft.query.filter(Aircraft.sync_revision > since_revision)
        .order_by(Aircraft.sync_revision.asc())
        .limit(limit)
        .all()
    )
    badges = (
        AchievementBadge.query.filter(AchievementBadge.sync_revision > since_revision)
        .order_by(AchievementBadge.sync_revision.asc())
        .limit(limit)
        .all()
    )
    return {
        "since_revision": since_revision,
        "current_revision": SyncState.current(),
        "flights": [flight_to_dict(f) for f in flights],
        "trips": [trip_to_dict(t) for t in trips],
        "trip_legs": [trip_leg_to_dict(leg) for leg in legs],
        "aircraft": [aircraft_to_dict(a) for a in aircraft],
        "badges": [badge_to_dict(b) for b in badges],
    }


@mcp.tool()
def bulk_create_flights(
    flights: Annotated[list[dict[str, Any]], Field(description=(
        "List of flight objects. Each accepts the same keys as create_flight's "
        "parameters (see describe_flight_fields)."
    ))],
    auto_fill: Annotated[bool, Field(description=_AUTO_FILL_DESC)] = True,
    allow_duplicate: Annotated[bool, Field(description=(
        "Create rows even when an exact duplicate exists in the database or "
        "earlier in the same batch."
    ))] = False,
    lookup_registration: Annotated[bool, Field(description=_LOOKUP_REGISTRATION_DESC)] = True,
) -> dict[str, Any]:
    """Create many flights in one all-or-nothing transaction.

    Every row is validated, normalised and checked for duplicates first with
    the same rules and defaults as create_flight. If any row fails, nothing is
    created and results lists the problem per row (by index). After the commit
    each row without a registration is looked up with the configured
    flight-data provider (see registration_lookup per row); if the provider
    rate-limits mid-batch the remaining rows are marked skipped so they can be
    retried with lookup_flight_registration.
    """
    if not isinstance(flights, list) or not flights:
        return {"error": "flights must be a non-empty list of objects"}
    prepared: list[tuple[int, Flight, dict[str, Any]]] = []
    results: list[dict[str, Any]] = []
    seen_keys: set = set()
    failed = False
    for idx, item in enumerate(flights):
        if not isinstance(item, dict):
            results.append({"index": idx, "error": "validation_failed",
                            "message": "each item must be an object"})
            failed = True
            continue
        flight, info = _prepare_new_flight(
            item, auto_fill=auto_fill, allow_duplicate=allow_duplicate,
            seen_keys=seen_keys,
        )
        if flight is None:
            failed = True
            results.append({"index": idx, **info})
        else:
            prepared.append((idx, flight, info))
            results.append({"index": idx, "status": "ok"})
    if failed:
        db.session.rollback()
        return {
            "error": "validation_failed",
            "message": "No flights were created. Fix the rows listed in results and retry.",
            "created": 0,
            "results": results,
        }
    for _, flight, _ in prepared:
        stamp_revision(flight)
        db.session.add(flight)
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return {"error": "commit_failed", "detail": str(exc), "created": 0}
    rate_limited = False
    for idx, flight, info in prepared:
        results[idx].update({"id": flight.id, **info})
        if not lookup_registration:
            continue
        if rate_limited:
            results[idx]["registration_lookup"] = {
                "provider": active_provider(),
                "status": "skipped",
                "kind": "rate_limited",
                "reason": (
                    "provider rate limit reached earlier in this batch; retry with "
                    "lookup_flight_registration"
                ),
            }
            continue
        lookup = _lookup_registration(flight)
        results[idx]["registration_lookup"] = lookup
        if lookup.get("kind") == "rate_limited":
            rate_limited = True
    return {"created": len(prepared), "results": results}


@mcp.tool()
def bulk_update_flights(
    updates: Annotated[list[dict[str, Any]], Field(description=(
        "List of {id, fields, clear_fields?} objects. `fields` takes the same "
        "keys as update_flight's parameters (a null value blanks the field); "
        "`clear_fields` optionally lists field names to blank."
    ))],
    auto_fill: Annotated[bool, Field(description=_AUTO_FILL_DESC)] = True,
) -> dict[str, Any]:
    """Update many flights in one all-or-nothing transaction.

    Each row is validated and applied with the same rules as update_flight. If
    any row is invalid or its flight is missing, nothing is written and results
    lists the problem per row (by index).
    """
    if not isinstance(updates, list) or not updates:
        return {"error": "updates must be a non-empty list of {id, fields} objects"}
    results: list[dict[str, Any]] = []
    touched: list[int] = []
    failed = False
    for idx, item in enumerate(updates):
        if not isinstance(item, dict) or item.get("id") is None:
            results.append({"index": idx, "error": "validation_failed",
                            "message": "each item must be an object with an id"})
            failed = True
            continue
        try:
            fid = int(item["id"])
        except (TypeError, ValueError):
            results.append({"index": idx, "error": "validation_failed", "message": "id must be an integer"})
            failed = True
            continue
        fields = item.get("fields") or {}
        clear_fields = item.get("clear_fields") or []
        if not isinstance(fields, dict) or not isinstance(clear_fields, list):
            results.append({"index": idx, "id": fid, "error": "validation_failed",
                            "message": "fields must be an object and clear_fields a list"})
            failed = True
            continue
        flight = _active_flights().filter_by(id=fid).first()
        if flight is None:
            results.append({"index": idx, "id": fid, "error": "not_found"})
            failed = True
            continue
        result = _apply_flight_update(flight, fields, clear_fields, auto_fill=auto_fill)
        if "error" in result:
            failed = True
            results.append({"index": idx, **result})
            continue
        if result["changed"] or result["reset"] or result["auto_filled"]:
            flight.updated_at = _now()
            stamp_revision(flight)
            touched.append(fid)
            results.append({"index": idx, "id": fid, "status": "updated", **result})
        else:
            results.append({"index": idx, "id": fid, "status": "unchanged", **result})
    if failed:
        db.session.rollback()
        return {
            "error": "validation_failed",
            "message": "No flights were updated. Fix the rows listed in results and retry.",
            "updated": 0,
            "results": results,
        }
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return {"error": "commit_failed", "detail": str(exc), "updated": 0, "results": results}
    return {"updated": len(touched), "results": results}


# ---------------------------------------------------------------------------
# Extra stats
# ---------------------------------------------------------------------------

@mcp.tool()
def top_aircraft(limit: int = 10, year: Optional[int] = None) -> dict[str, Any]:
    """Top aircraft tail registrations by flight count + miles."""
    base = _stats_base(year).filter(Flight.aircraft_registration.isnot(None))
    rows = (
        base.with_entities(
            Flight.aircraft_registration,
            func.count(Flight.id).label("count"),
            func.coalesce(func.sum(Flight.distance), 0).label("miles"),
        )
        .group_by(Flight.aircraft_registration)
        .order_by(func.count(Flight.id).desc())
        .limit(min(max(limit, 1), 100))
        .all()
    )
    return {
        "aircraft": [
            {"registration": r[0], "count": int(r[1]), "miles": float(r[2])}
            for r in rows
        ]
    }


@mcp.tool()
def top_destinations(limit: int = 10, year: Optional[int] = None) -> dict[str, Any]:
    """Top destination airports by flight count."""
    base = _stats_base(year).filter(Flight.end_airport.isnot(None))
    rows = (
        base.with_entities(
            Flight.end_airport,
            Flight.end_city_name,
            func.count(Flight.id).label("count"),
        )
        .group_by(Flight.end_airport, Flight.end_city_name)
        .order_by(func.count(Flight.id).desc())
        .limit(min(max(limit, 1), 100))
        .all()
    )
    return {
        "destinations": [
            {"airport": r[0], "city": r[1], "count": int(r[2])} for r in rows
        ]
    }


@mcp.tool()
def top_origins(limit: int = 10, year: Optional[int] = None) -> dict[str, Any]:
    """Top origin airports by flight count."""
    base = _stats_base(year).filter(Flight.start_airport.isnot(None))
    rows = (
        base.with_entities(
            Flight.start_airport,
            Flight.start_city_name,
            func.count(Flight.id).label("count"),
        )
        .group_by(Flight.start_airport, Flight.start_city_name)
        .order_by(func.count(Flight.id).desc())
        .limit(min(max(limit, 1), 100))
        .all()
    )
    return {
        "origins": [
            {"airport": r[0], "city": r[1], "count": int(r[2])} for r in rows
        ]
    }


@mcp.tool()
def flights_by_month(year: int) -> dict[str, Any]:
    """Monthly flight count + miles for the given year."""
    base = _stats_base(year)
    rows = (
        base.with_entities(
            func.extract("month", Flight.start_date).label("month"),
            func.count(Flight.id).label("count"),
            func.coalesce(func.sum(Flight.distance), 0).label("miles"),
        )
        .group_by("month")
        .order_by("month")
        .all()
    )
    return {
        "year": year,
        "months": [
            {"month": int(r.month), "count": int(r.count), "miles": float(r.miles)}
            for r in rows
            if r.month is not None
        ],
    }


@mcp.tool()
def distance_summary(year: Optional[int] = None) -> dict[str, Any]:
    """Min / avg / max / total distance across approved flights with a distance set."""
    base = _stats_base(year).filter(Flight.distance.isnot(None))
    row = base.with_entities(
        func.min(Flight.distance),
        func.avg(Flight.distance),
        func.max(Flight.distance),
        func.coalesce(func.sum(Flight.distance), 0),
        func.count(Flight.id),
    ).first()
    if row is None:
        return {"year": year, "count": 0}
    mn, avg, mx, total, count = row
    return {
        "year": year,
        "count": int(count or 0),
        "min_miles": float(mn) if mn is not None else None,
        "avg_miles": float(avg) if avg is not None else None,
        "max_miles": float(mx) if mx is not None else None,
        "total_miles": float(total or 0),
    }


# ---------------------------------------------------------------------------
# HTTP transport support: health probe + optional bearer token
# ---------------------------------------------------------------------------

@mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
async def healthz(request: Request) -> JSONResponse:
    """Kubernetes probe: verifies the database answers a trivial query."""
    try:
        db.session.execute(text("SELECT 1"))
        db.session.rollback()
    except Exception as exc:  # pragma: no cover - only hit when the DB is down
        db.session.rollback()
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=503)
    return JSONResponse({
        "status": "ok",
        "version": current_app.config.get("APP_VERSION", "unknown"),
        "transport": MCP_TRANSPORT,
    })


class _BearerTokenMiddleware:
    """Reject HTTP requests that lack the configured bearer token.

    Pure ASGI middleware so it wraps FastMCP's Starlette app without touching
    its lifespan. /healthz stays open so Kubernetes probes keep working.
    """

    def __init__(self, app, token: str, exempt_paths: tuple[str, ...] = ("/healthz",)):
        self.app = app
        self.expected = f"Bearer {token}"
        self.exempt_paths = exempt_paths

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") in self.exempt_paths:
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        supplied = headers.get(b"authorization", b"").decode("latin-1")
        if not hmac.compare_digest(supplied, self.expected):
            response = JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def build_http_app():
    """The ASGI app served in streamable-http mode (also handy for tests)."""
    asgi_app = mcp.streamable_http_app()
    if MCP_AUTH_TOKEN:
        asgi_app = _BearerTokenMiddleware(asgi_app, MCP_AUTH_TOKEN)
    return asgi_app


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    app = create_app()
    app.app_context().push()

    if MCP_TRANSPORT == "stdio":
        mcp.run()
        return
    if MCP_TRANSPORT not in {"streamable-http", "http"}:
        raise SystemExit(
            f"Unsupported MCP_TRANSPORT={MCP_TRANSPORT!r}; use 'stdio' or 'streamable-http'."
        )

    import uvicorn

    uvicorn.run(
        build_http_app(),
        host=MCP_HOST,
        port=MCP_PORT,
        log_level=(os.environ.get("MCP_LOG_LEVEL") or "info").lower(),
    )


if __name__ == "__main__":
    main()
