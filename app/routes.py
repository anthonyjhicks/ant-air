import json
import calendar
from collections import Counter, defaultdict
from urllib.parse import quote
from datetime import datetime, date
from uuid import uuid4
from decimal import Decimal, InvalidOperation

import pycountry

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import and_, func, or_

from .extensions import db
from .models import (
    Aircraft,
    AuditDuplicateIgnore,
    Flight,
    FlightHistory,
    FlightHistoryAirNavRadar,
    FlightPosition,
    Trip,
    TripLeg,
)
from .sync import stamp_revision
from .services.flight_groups import (
    approved_group_members,
    fill_blank_fields_from_group,
    group_primary,
    group_sort_key,
    is_group_primary,
    matches_flight_or_group_member,
)
from .services.analytics import (
    build_missing_leg_audit,
    group_flights_by_dedupe_key,
    group_flights_by_day_month_route,
    group_flights_by_match_score,
    group_flights_by_route_date,
    merged_flights_for_reporting,
    normalize_key,
    resolve_duplicate_rules,
    resolve_airline_code,
    summarize_flights,
)
from .services.airlines import (
    AIRLINE_LOOKUP,
    LOGO_URL_TEMPLATE,
    build_airline_logo_url,
    lookup_airline_name,
)
from .services.adsbdb import get_aircraft_details
from .services.flight_lookup import FlightLookupError, lookup_and_record
from .services.gemini_codeshare import (
    GeminiCodeshareError,
    lookup_codeshare_details,
)
from .services.gemini_registration_scan import (
    GeminiRegistrationScanError,
    scan_registration_from_image,
)
from .services.csv_import import parse_csv
from .services.geocoding import lookup_location
from .services.personalisation import (
    default_traveller,
    home_airports,
    home_city,
    home_country,
)
from .services.importer import compute_distance, import_rows
from .services.script_runner import (
    ScriptRunnerError,
    get_script_history,
    get_script_catalog,
    get_script_run_status,
    start_script_run,
    stop_script_run,
)

main_bp = Blueprint("main", __name__)


@main_bp.route("/health")
def health():
    return (
        jsonify(
            {
                "status": "ok",
                "version": current_app.config.get("APP_VERSION", "unknown"),
            }
        ),
        200,
    )


@main_bp.route("/api/search")
def api_search():
    q = (request.args.get("q") or "").strip()
    if not q or len(q) < 2:
        return jsonify({"flights": [], "aircraft": []})

    term = f"%{q}%"

    def text_match(entity):
        return or_(
            entity.flight_number.ilike(term),
            entity.airline_code.ilike(term),
            entity.operating_airline_code.ilike(term),
            entity.start_airport.ilike(term),
            entity.end_airport.ilike(term),
            entity.start_city_name.ilike(term),
            entity.end_city_name.ilike(term),
            entity.start_country.ilike(term),
            entity.end_country.ilike(term),
            entity.aircraft.ilike(term),
            entity.aircraft_type_normalized.ilike(term),
            entity.aircraft_registration.ilike(term),
            entity.traveller.ilike(term),
            entity.booking_site.ilike(term),
            entity.supplier_confirmation.ilike(term),
            entity.trip_name.ilike(term),
            entity.ticket_number.ilike(term),
        )

    # One result per flight: the group's primary, found through any member's values.
    flights_query = (
        approved_flights_query()
        .filter(matches_flight_or_group_member(text_match))
        .order_by(Flight.start_date.desc())
        .limit(50)
        .all()
    )

    aircraft_query = (
        Aircraft.query.filter(
            or_(
                Aircraft.registration.ilike(term),
                Aircraft.type.ilike(term),
                Aircraft.icao_type.ilike(term),
                Aircraft.manufacturer.ilike(term),
                Aircraft.registered_owner.ilike(term),
                Aircraft.registered_owner_country_name.ilike(term),
            )
        )
        .order_by(Aircraft.registration)
        .limit(50)
        .all()
    )

    flight_results = []
    for f in flights_query:
        flight_results.append({
            "id": f.id,
            "start_date": f.start_date.isoformat() if f.start_date else None,
            "origin_name": f.origin_name,
            "destination_name": f.destination_name,
            "flight_number": f.flight_number,
            "airline_code": f.airline_code,
            "aircraft": f.aircraft,
            "aircraft_registration": f.aircraft_registration,
            "distance": f.distance,
            "traveller": f.traveller,
        })

    aircraft_results = []
    for a in aircraft_query:
        aircraft_results.append({
            "registration": a.registration,
            "type": a.type,
            "icao_type": a.icao_type,
            "manufacturer": a.manufacturer,
            "owner": a.registered_owner,
        })

    return jsonify({"flights": flight_results, "aircraft": aircraft_results})


@main_bp.route("/api/aircraft/<registration>")
def api_aircraft_lookup(registration):
    reg = (registration or "").strip().upper()
    if not reg:
        return jsonify({"error": "Registration required"}), 400

    details = get_aircraft_details(reg) or {}

    flights = (
        approved_flights_query()
        .filter(func.upper(Flight.aircraft_registration) == reg)
        .order_by(Flight.start_date.desc())
        .all()
    )
    flight_list = []
    for f in flights:
        flight_list.append({
            "id": f.id,
            "start_date": f.start_date.isoformat() if f.start_date else None,
            "origin_name": f.origin_name,
            "destination_name": f.destination_name,
            "flight_number": f.flight_number,
            "airline_code": f.airline_code,
            "aircraft": f.aircraft,
            "distance": f.distance,
            "traveller": f.traveller,
        })

    airnav_histories = (
        FlightHistoryAirNavRadar.query.join(
            Flight, FlightHistoryAirNavRadar.flight_id == Flight.id
        )
        .filter(
            func.upper(FlightHistoryAirNavRadar.aircraft_registration) == reg,
            Flight.deleted_at.is_(None),
        )
        .order_by(
            FlightHistoryAirNavRadar.dep_date.desc(),
            FlightHistoryAirNavRadar.created_at.desc(),
        )
        .limit(150)
        .all()
    )
    airnav_list = []
    seen_history_keys = set()
    for h in airnav_histories:
        # Members of a duplicate group each hold a copy of the same history.
        history_key = (
            h.dep_date,
            h.flight_number_iata or h.flight_number_icao,
            h.dep_airport_iata or h.dep_airport_icao,
            h.arr_airport_iata or h.arr_airport_icao,
        )
        if history_key in seen_history_keys:
            continue
        seen_history_keys.add(history_key)
        if len(airnav_list) >= 50:
            break
        airnav_list.append({
            "id": h.id,
            "flight_id": h.flight_id,
            "dep_date": h.dep_date.isoformat() if h.dep_date else None,
            "flight_number": h.flight_number_iata or h.flight_number_icao,
            "airline_name": h.airline_name,
            "dep_airport": h.dep_airport_iata or h.dep_airport_icao,
            "dep_city": h.dep_airport_city,
            "arr_airport": h.arr_airport_iata or h.arr_airport_icao,
            "arr_city": h.arr_airport_city,
            "aircraft_type": h.aircraft_type_description or h.aircraft_type,
            "source": h.source,
            "status": h.status,
        })

    return jsonify({
        "registration": reg,
        "details": details,
        "flights": flight_list,
        "airnav_history": airnav_list,
    })


SCAN_ALLOWED_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/heic", "image/heif",
}
SCAN_MAX_SIZE = 10 * 1024 * 1024  # 10 MB


@main_bp.route("/api/scan-registration", methods=["POST"])
def api_scan_registration():
    if "image" not in request.files:
        return jsonify({"error": "No image provided"}), 400
    file = request.files["image"]
    if not file.filename:
        return jsonify({"error": "No image provided"}), 400

    mime_type = file.content_type or "image/jpeg"
    if mime_type not in SCAN_ALLOWED_TYPES:
        return jsonify({"error": f"Unsupported image type: {mime_type}"}), 400

    image_bytes = file.read()
    if len(image_bytes) > SCAN_MAX_SIZE:
        return jsonify({"error": "Image too large (max 10 MB)"}), 400
    if not image_bytes:
        return jsonify({"error": "Empty image"}), 400

    try:
        parsed, debug = scan_registration_from_image(image_bytes, mime_type)
    except GeminiRegistrationScanError as exc:
        return jsonify({"error": str(exc)}), 500

    if not parsed:
        return jsonify({"error": "Could not read registration from image"})

    registration = parsed.get("registration")
    confidence = parsed.get("confidence")
    result = {
        "registration": registration,
        "confidence": confidence,
        "location_on_aircraft": parsed.get("location_on_aircraft"),
        "aircraft_type_guess": parsed.get("aircraft_type_guess"),
    }
    if confidence is not None and confidence < 0.5:
        result["low_confidence"] = True
    return jsonify(result)


MERGE_FIELDS = (
    "trip_name",
    "trip_id",
    "trip_type",
    "activity_id",
    "activity_cost",
    "url",
    "booking_site",
    "supplier_confirmation",
    "booking_date",
    "booking_site_phone",
    "traveller",
    "ticket_number",
    "airline_code",
    "aircraft",
    "service_class",
    "flight_number",
    "start_country",
    "start_city_name",
    "start_airport",
    "start_terminal",
    "start_lat",
    "start_long",
    "start_date",
    "start_time",
    "end_country",
    "end_city_name",
    "end_airport",
    "end_terminal",
    "end_lat",
    "end_long",
    "end_date",
    "end_time",
    "stops",
    "route_direction",
    "distance",
)

APPROVED_STATUS = "approved"
DRAFT_STATUS = "draft"


def resolve_redirect_target(value, default_endpoint):
    if isinstance(value, str) and value.startswith("/") and not value.startswith("//"):
        return value
    return url_for(default_endpoint)


def wants_json_response():
    return (
        request.headers.get("X-Requested-With") == "fetch"
        or "application/json" in request.headers.get("Accept", "")
    )


def build_duplicate_ignore_signature(flight_ids):
    normalized = sorted({int(item) for item in flight_ids})
    return ",".join(str(item) for item in normalized)


def approved_flights_query(include_group_members=False):
    """Approved, active flights.

    Duplicate groups (rows sharing a grouping_id) are collapsed to their
    primary, newest member. Pass ``include_group_members=True`` only when the
    caller handles groups itself: the flight list, the audit pages and anything
    feeding ``merged_flights_for_reporting``.
    """
    query = Flight.query.filter(
        Flight.status == APPROVED_STATUS, Flight.deleted_at.is_(None)
    )
    if not include_group_members:
        query = query.filter(is_group_primary())
    return query


def parse_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def resolve_leg_sequence(payload, fallback):
    sequence = parse_int(payload.get("sequence"))
    if sequence is None or sequence < 1:
        return fallback
    return sequence


DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y"]
DATE_PRECISIONS = ("day", "month", "year")
LEG_MODES = [
    ("flight", "Flight"),
    ("train", "Train"),
    ("car", "Car"),
    ("bus", "Bus"),
    ("boat", "Boat"),
    ("other", "Other"),
]


def parse_date(value):
    if not value:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def normalize_date_precision(value, year=None, month=None, day=None):
    precision = (value or "").strip().lower()
    if precision in DATE_PRECISIONS:
        return precision
    if day:
        return "day"
    if month:
        return "month"
    if year:
        return "year"
    return None


def build_canonical_date(year, month, day, precision):
    if not year:
        return None
    if precision == "year":
        month = 1
        day = 1
    elif precision == "month":
        month = month or 1
        day = 1
    else:
        if not month or not day:
            return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def format_partial_date(value, precision, year, month, day):
    if precision == "year" and year:
        return f"{year}"
    if precision == "month" and year and month:
        return f"{year}-{month:02d}"
    if value:
        return value.isoformat()
    return "-"


def trip_display_date(trip):
    return format_partial_date(
        trip.start_date,
        trip.start_date_precision,
        trip.start_date_year,
        trip.start_date_month,
        trip.start_date_day,
    )


def trip_leg_display_date(leg):
    return format_partial_date(
        leg.start_date,
        leg.start_date_precision,
        leg.start_date_year,
        leg.start_date_month,
        leg.start_date_day,
    )


def parse_time(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None


def parse_decimal(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def require_n8n_auth():
    expected_token = current_app.config.get("N8N_WEBHOOK_TOKEN")
    if not expected_token:
        return jsonify({"ok": False, "error": "Webhook token not configured."}), 500
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"ok": False, "error": "Unauthorized."}), 401
    provided = auth_header.split(" ", 1)[1].strip()
    if not provided or provided != expected_token:
        return jsonify({"ok": False, "error": "Unauthorized."}), 401
    return None


def traveller_key(value):
    if not value:
        return "unknown"
    trimmed = " ".join(value.strip().split())
    if not trimmed:
        return "unknown"
    return quote(trimmed)


def booking_site_key(value):
    if not value:
        return "unknown"
    trimmed = " ".join(value.strip().split())
    if not trimmed:
        return "unknown"
    return quote(trimmed)


def normalize_flight_id(value):
    if not value:
        return ""
    return str(value).strip().replace(" ", "").upper()


def extract_trip_leg_payloads(form):
    legs = {}
    for key in form.keys():
        if not key.startswith("legs-"):
            continue
        parts = key.split("-", 2)
        if len(parts) != 3:
            continue
        index = parts[1]
        field = parts[2]
        legs.setdefault(index, {})[field] = form.get(key)
    payloads = []
    for index, fields in legs.items():
        payloads.append((parse_int(index) or 0, fields))
    return [fields for _, fields in sorted(payloads, key=lambda item: item[0])]


def build_trip_leg_from_payload(payload, trip_id=None):
    leg_id = parse_int(payload.get("id"))
    sequence = parse_int(payload.get("sequence"))
    mode = (payload.get("mode") or "flight").strip().lower() or "flight"
    start_year = parse_int(payload.get("start_year"))
    start_month = parse_int(payload.get("start_month"))
    start_day = parse_int(payload.get("start_day"))
    start_precision = normalize_date_precision(
        payload.get("start_precision"), start_year, start_month, start_day
    )
    start_date = build_canonical_date(
        start_year, start_month, start_day, start_precision
    )
    end_year = parse_int(payload.get("end_year"))
    end_month = parse_int(payload.get("end_month"))
    end_day = parse_int(payload.get("end_day"))
    end_precision = normalize_date_precision(
        payload.get("end_precision"), end_year, end_month, end_day
    )
    end_date = build_canonical_date(end_year, end_month, end_day, end_precision)

    leg = TripLeg()
    if trip_id is not None:
        leg.trip_id = trip_id
    leg.id = leg_id
    leg.sequence = sequence if sequence is not None else 0
    leg.mode = mode
    leg.carrier_name = payload.get("carrier_name") or None
    leg.carrier_code = payload.get("carrier_code") or None
    leg.service_class = payload.get("service_class") or None
    leg.flight_number = payload.get("flight_number") or None
    leg.aircraft_type = payload.get("aircraft_type") or None
    leg.aircraft_registration = payload.get("aircraft_registration") or None
    leg.start_country = payload.get("start_country") or None
    leg.start_city_name = payload.get("start_city_name") or None
    leg.start_airport = payload.get("start_airport") or None
    leg.end_country = payload.get("end_country") or None
    leg.end_city_name = payload.get("end_city_name") or None
    leg.end_airport = payload.get("end_airport") or None
    leg.start_date = start_date
    leg.start_date_precision = start_precision
    leg.start_date_year = start_year
    leg.start_date_month = start_month
    leg.start_date_day = start_day
    leg.end_date = end_date
    leg.end_date_precision = end_precision
    leg.end_date_year = end_year
    leg.end_date_month = end_month
    leg.end_date_day = end_day
    leg.notes = payload.get("notes") or None
    return leg


def apply_trip_leg_payload(leg, payload, sequence_override=None):
    updated = build_trip_leg_from_payload(payload, trip_id=leg.trip_id)
    leg.sequence = (
        sequence_override
        if sequence_override is not None
        else updated.sequence
    )
    leg.mode = updated.mode
    leg.carrier_name = updated.carrier_name
    leg.carrier_code = updated.carrier_code
    leg.service_class = updated.service_class
    leg.flight_number = updated.flight_number
    leg.aircraft_type = updated.aircraft_type
    leg.aircraft_registration = updated.aircraft_registration
    leg.start_country = updated.start_country
    leg.start_city_name = updated.start_city_name
    leg.start_airport = updated.start_airport
    leg.end_country = updated.end_country
    leg.end_city_name = updated.end_city_name
    leg.end_airport = updated.end_airport
    leg.start_date = updated.start_date
    leg.start_date_precision = updated.start_date_precision
    leg.start_date_year = updated.start_date_year
    leg.start_date_month = updated.start_date_month
    leg.start_date_day = updated.start_date_day
    leg.end_date = updated.end_date
    leg.end_date_precision = updated.end_date_precision
    leg.end_date_year = updated.end_date_year
    leg.end_date_month = updated.end_date_month
    leg.end_date_day = updated.end_date_day
    leg.notes = updated.notes
    return leg


def is_trip_leg_blank(payload):
    checks = [
        payload.get("carrier_name"),
        payload.get("carrier_code"),
        payload.get("service_class"),
        payload.get("flight_number"),
        payload.get("aircraft_type"),
        payload.get("aircraft_registration"),
        payload.get("start_country"),
        payload.get("start_city_name"),
        payload.get("start_airport"),
        payload.get("end_country"),
        payload.get("end_city_name"),
        payload.get("end_airport"),
        payload.get("start_year"),
        payload.get("start_month"),
        payload.get("start_day"),
        payload.get("end_year"),
        payload.get("end_month"),
        payload.get("end_day"),
        payload.get("notes"),
    ]
    return not any(value for value in checks)


def validate_trip_leg_payload(payload, index_label="leg"):
    mode = (payload.get("mode") or "flight").strip().lower() or "flight"
    if mode != "flight":
        return None
    start_year = parse_int(payload.get("start_year"))
    start_month = parse_int(payload.get("start_month"))
    start_day = parse_int(payload.get("start_day"))
    start_precision = normalize_date_precision(
        payload.get("start_precision"), start_year, start_month, start_day
    )
    start_date = build_canonical_date(
        start_year, start_month, start_day, start_precision
    )
    if not start_date:
        return f"Flight {index_label} needs at least a year (and month/day if selected)."
    if not (payload.get("start_city_name") or payload.get("start_airport")):
        return f"Flight {index_label} needs a start city or airport."
    if not (payload.get("end_city_name") or payload.get("end_airport")):
        return f"Flight {index_label} needs an end city or airport."
    return None


def sync_trip_leg_flight(leg, trip):
    if leg.mode != "flight":
        if leg.flight:
            db.session.delete(leg.flight)
        return None
    if not leg.start_date:
        return "Flight legs require a date."
    if not (leg.start_city_name or leg.start_airport):
        return "Flight legs require a start city or airport."
    if not (leg.end_city_name or leg.end_airport):
        return "Flight legs require an end city or airport."

    flight = leg.flight or Flight(status=APPROVED_STATUS)
    flight.trip_leg_id = leg.id
    flight.trip_name = trip.name or None
    flight.trip_id = trip.trip_code or f"trip-{trip.id}"
    flight.trip_type = trip.trip_type or None
    flight.airline_code = leg.carrier_code or None
    flight.flight_number = leg.flight_number or None
    flight.service_class = leg.service_class or None
    flight.aircraft = leg.aircraft_type or None
    flight.aircraft_registration = leg.aircraft_registration or None
    flight.start_country = leg.start_country or None
    flight.start_city_name = leg.start_city_name or None
    flight.start_airport = leg.start_airport or None
    flight.start_date = leg.start_date
    flight.end_country = leg.end_country or None
    flight.end_city_name = leg.end_city_name or None
    flight.end_airport = leg.end_airport or None
    flight.end_date = leg.end_date
    if flight.distance is None:
        flight.distance = compute_distance(
            flight.start_lat, flight.start_long, flight.end_lat, flight.end_long
        )
    if flight.id is None:
        db.session.add(flight)
    return None


COUNTRY_FLAG_OVERRIDES = {
    "uk": "gb",
    "u.k.": "gb",
    "united kingdom": "gb",
    "united states": "us",
    "united states of america": "us",
    "usa": "us",
}


def resolve_country_code(value):
    if not value:
        return None
    text = str(value).strip()
    if not text or text == "Unknown":
        return None
    if len(text) == 2 and text.isalpha():
        return text.lower()
    normalized = text.lower()
    override = COUNTRY_FLAG_OVERRIDES.get(normalized)
    if override:
        return override
    try:
        match = pycountry.countries.search_fuzzy(text)[0]
    except LookupError:
        return None
    return match.alpha_2.lower() if match.alpha_2 else None


def build_country_flag_url(country):
    code = resolve_country_code(country)
    if code:
        return f"https://flagcdn.com/w40/{code}.png"
    if country and country != "Unknown":
        return f"https://countryflagsapi.com/png/{quote(country)}"
    return None


def build_aircraft_thumbnail(registration):
    if not registration:
        return None
    details = get_aircraft_details(registration)
    if not details:
        return None
    return {
        "registration": registration,
        "thumbnail_url": details.get("url_photo_thumbnail"),
        "photo_url": details.get("url_photo"),
        "type": details.get("type"),
    }


def build_timeline_data(group_by_trips=True):
    """Build timeline data structure for chronological flight view."""
    from datetime import date

    flights = (
        approved_flights_query(include_group_members=True)
        .order_by(Flight.start_date.asc())
        .all()
    )
    # Collapse duplicate groups and drop excluded flights.
    merged_flights = merged_flights_for_reporting(flights)

    # Create lookup dict for merged flights by ID and by grouping_id
    flight_lookup = {}
    for flight in merged_flights:
        flight_lookup[flight.id] = flight
        if flight.grouping_id:
            # Map all flights in this group to the merged primary flight
            for orig_flight in flights:
                if orig_flight.grouping_id == flight.grouping_id:
                    flight_lookup[orig_flight.id] = flight

    if group_by_trips:
        trips = Trip.query.order_by(Trip.start_date.asc()).all()
        timeline_items = []
        seen_flight_ids = set()

        for trip in trips:
            trip_legs = TripLeg.query.filter(TripLeg.trip_id == trip.id).order_by(TripLeg.sequence).all()
            trip_flights = []

            for leg in trip_legs:
                if leg.flight and leg.flight.id in flight_lookup:
                    merged_flight = flight_lookup[leg.flight.id]
                    # Only add if we haven't already added this merged flight to this trip
                    if merged_flight.id not in seen_flight_ids:
                        trip_flights.append(merged_flight)
                        seen_flight_ids.add(merged_flight.id)

            if trip_flights:
                timeline_items.append({
                    'type': 'trip',
                    'trip': trip,
                    'flights': trip_flights,
                    'start_date': trip.start_date,
                })

        # Add ungrouped flights (no trip association)
        ungrouped = [f for f in merged_flights if not f.trip_leg_id]
        for flight in ungrouped:
            if flight.id not in seen_flight_ids:
                timeline_items.append({
                    'type': 'flight',
                    'flight': flight,
                    'start_date': flight.start_date,
                })
                seen_flight_ids.add(flight.id)

        timeline_items.sort(key=lambda x: x['start_date'] or date.min)
        return timeline_items
    else:
        # Individual flights view - sort in ascending order (oldest first) by default
        timeline_items = [{'type': 'flight', 'flight': f, 'start_date': f.start_date} for f in merged_flights]
        timeline_items.sort(key=lambda x: x['start_date'] or date.min)
        return timeline_items


@main_bp.route("/")
def dashboard():
    flights = (
        approved_flights_query(include_group_members=True)
        .order_by(Flight.start_date.desc())
        .all()
    )
    reporting_flights = merged_flights_for_reporting(flights)
    stats = summarize_flights(reporting_flights)

    traveller_counts = Counter()
    for flight in reporting_flights:
        label = (flight.traveller or "").strip() or "Unknown"
        traveller_counts[label] += 1
    if "Unknown" not in traveller_counts:
        traveller_counts["Unknown"] = 0

    booking_site_counts = Counter()
    for flight in reporting_flights:
        label = (flight.booking_site or "").strip() or "Unknown"
        booking_site_counts[label] += 1
    if "Unknown" not in booking_site_counts:
        booking_site_counts["Unknown"] = 0

    map_routes = []
    for flight in reporting_flights:
        origin_coords = None
        destination_coords = None
        if flight.start_lat is not None and flight.start_long is not None:
            origin_coords = [flight.start_lat, flight.start_long]
        if flight.end_lat is not None and flight.end_long is not None:
            destination_coords = [flight.end_lat, flight.end_long]
        map_routes.append(
            {
                "origin_coords": origin_coords,
                "destination_coords": destination_coords,
                "origin_name": flight.origin_name,
                "destination_name": flight.destination_name,
                "route_direction": flight.route_direction,
                "airline_code": flight.airline_code,
                "aircraft": flight.aircraft_type_normalized,
                "start_date": flight.start_date.isoformat() if flight.start_date else None,
                "flight_number": flight.flight_number,
                "aircraft_registration": flight.aircraft_registration,
                "distance": flight.distance,
            }
        )

    cities_top = stats["top_cities"][:10]
    countries_top = stats["top_countries"][:8]
    airlines_top = stats["top_airlines"][:10]
    aircrafts_top = stats.get("top_aircrafts", [])[:10]
    routes_top = stats["top_routes"][:10]
    tailnumbers_top = stats.get("top_tailnumbers", [])[:10]
    aircraft_miles_top = stats.get("top_aircraft_miles", [])[:10]

    def airline_display_label(code):
        if not code or code == "Unknown":
            return "Unknown"
        name = lookup_airline_name(code)
        if not name:
            return code
        return f"{name} ({code})"

    chart_payload = {
        "monthlyLabels": [item[0] for item in stats["monthly"]],
        "monthlyCounts": [item[1] for item in stats["monthly"]],
        "monthlyMiles": [item[1] for item in stats["monthly_miles"]],
        "topCitiesLabels": [item[0] for item in cities_top],
        "topCitiesCounts": [item[1] for item in cities_top],
        "topCountriesLabels": [item[0] for item in countries_top],
        "topCountriesCounts": [item[1] for item in countries_top],
        "topAirlinesLabels": [airline_display_label(item[0]) for item in airlines_top],
        "topAirlinesCounts": [item[1] for item in airlines_top],
        "topAircraftLabels": [item[0] for item in aircrafts_top],
        "topAircraftCounts": [item[1] for item in aircrafts_top],
        "topAircraftMilesLabels": [item[0] for item in aircraft_miles_top],
        "topAircraftMilesCounts": [item[1] for item in aircraft_miles_top],
        "topTailnumbersLabels": [item[0] for item in tailnumbers_top],
        "topTailnumbersCounts": [item[1] for item in tailnumbers_top],
        "topRoutesLabels": [item[0] for item in routes_top],
        "topRoutesCounts": [item[1] for item in routes_top],
        "yearlyLabels": [str(item[0]) for item in stats["yearly"]],
        "yearlyCounts": [item[1] for item in stats["yearly"]],
        "yearlyMilesLabels": [str(item[0]) for item in stats["yearly_miles"]],
        "yearlyMilesCounts": [item[1] for item in stats["yearly_miles"]],
        "yearlyCo2Labels": [str(item[0]) for item in stats["yearly_co2"]],
        "yearlyCo2Counts": [item[1] for item in stats["yearly_co2"]],
    }

    for flight in reporting_flights:
        flight.traveller_key = traveller_key(flight.traveller)
        flight.booking_site_key = booking_site_key(flight.booking_site)

    travellers_sorted = sorted(
        traveller_counts.items(),
        key=lambda item: (-item[1], normalize_key(item[0]) or ""),
    )
    booking_sites_sorted = sorted(
        booking_site_counts.items(),
        key=lambda item: (-item[1], normalize_key(item[0]) or ""),
    )
    dashboard_flights = [
        {
            "id": flight.id,
            "traveller_key": flight.traveller_key,
            "traveller_label": (flight.traveller or "").strip() or "Unknown",
            "booking_site_key": flight.booking_site_key,
            "booking_site_label": (flight.booking_site or "").strip() or "Unknown",
            "start_date": flight.start_date.isoformat() if flight.start_date else None,
            "origin_name": flight.origin_name,
            "destination_name": flight.destination_name,
            "distance": flight.distance,
            "start_country": flight.start_country,
            "end_country": flight.end_country,
            "start_lat": flight.start_lat,
            "start_long": flight.start_long,
            "end_lat": flight.end_lat,
            "end_long": flight.end_long,
            "flight_number": flight.flight_number,
            "airline_code": flight.airline_code,
            "aircraft": flight.aircraft_type_normalized,
            "aircraft_type_normalized": flight.aircraft_type_normalized,
            "aircraft_registration": flight.aircraft_registration,
        }
        for flight in reporting_flights
    ]

    top_airline_code, top_airline_count = stats.get("top_airline", ("-", 0))
    resolved_airline_code = (
        resolve_airline_code(top_airline_code, None)
        if top_airline_code not in ("-", "Unknown", None)
        else None
    )
    airline_card = {
        "code": resolved_airline_code,
        "name": lookup_airline_name(resolved_airline_code),
        "logo_url": build_airline_logo_url(resolved_airline_code),
        "count": top_airline_count,
    }
    next_airlines = []
    for code, _ in stats.get("top_airlines", [])[1:]:
        resolved = resolve_airline_code(code, None)
        if not resolved or resolved == "Unknown":
            continue
        next_airlines.append(
            {
                "code": resolved,
                "name": lookup_airline_name(resolved),
                "logo_url": build_airline_logo_url(resolved),
            }
        )
        if len(next_airlines) >= 8:
            break

    top_aircraft_label = stats.get("top_aircraft", ("-", 0))[0]
    top_aircraft_registration = None
    if top_aircraft_label and top_aircraft_label not in ("-", "Unknown"):
        target_key = normalize_key(top_aircraft_label) or ""
        for flight in reporting_flights:
            aircraft_label = (flight.aircraft_type_normalized or "").strip()
            if normalize_key(aircraft_label) == target_key:
                registration = (flight.aircraft_registration or "").strip().upper()
                if registration:
                    top_aircraft_registration = registration
                    break

    top_aircraft_thumb = (
        build_aircraft_thumbnail(top_aircraft_registration)
        if top_aircraft_registration
        else None
    )

    top_tailnumber_label = stats.get("top_tailnumber", ("-", 0))[0]
    top_tailnumber_registration = (
        top_tailnumber_label.strip().upper()
        if top_tailnumber_label and top_tailnumber_label not in ("-", "Unknown")
        else None
    )
    top_tailnumber_thumb = (
        build_aircraft_thumbnail(top_tailnumber_registration)
        if top_tailnumber_registration
        else None
    )

    first_flight = None
    last_flight = None
    last_flight_with_reg = None
    for flight in reporting_flights:
        if not flight.start_date:
            continue
        if not first_flight or flight.start_date < first_flight.start_date:
            first_flight = flight
        if not last_flight or flight.start_date > last_flight.start_date:
            last_flight = flight
        registration = (flight.aircraft_registration or "").strip().upper()
        if registration and (
            not last_flight_with_reg
            or flight.start_date > last_flight_with_reg.start_date
        ):
            last_flight_with_reg = flight

    def build_flight_summary(flight):
        if not flight:
            return {"date": None, "registration": "-"}
        registration = (flight.aircraft_registration or "").strip().upper()
        return {
            "date": flight.start_date.isoformat() if flight.start_date else None,
            "registration": registration or "-",
        }

    first_flight_summary = build_flight_summary(first_flight)
    first_flight_thumb = None
    if first_flight and (first_flight.aircraft_registration or "").strip():
        first_flight_thumb = build_aircraft_thumbnail(
            first_flight.aircraft_registration.strip().upper()
        )
    last_flight_summary = build_flight_summary(last_flight_with_reg or last_flight)
    last_flight_thumb = None
    if last_flight_with_reg:
        last_flight_thumb = build_aircraft_thumbnail(
            (last_flight_with_reg.aircraft_registration or "").strip().upper()
        )

    top_country_flags = []
    base_country_key = normalize_key(home_country() or "")
    for country, _ in stats.get("top_countries", []):
        if base_country_key and normalize_key(country) == base_country_key:
            continue
        flag_url = build_country_flag_url(country)
        top_country_flags.append(
            {
                "country": country,
                "flag_url": flag_url,
            }
        )
        if len(top_country_flags) >= 8:
            break

    now = datetime.now()
    today = now.date()
    current_time = now.time()

    # Fetch candidate flights: today or future, ordered by date then time then id.
    next_flight_candidates = (
        approved_flights_query()
        .filter(Flight.start_date >= today)
        .order_by(
            Flight.start_date.asc(),
            Flight.start_time.asc().nulls_last(),
            Flight.id.asc(),
        )
        .all()
    )

    next_flight = None
    for candidate in next_flight_candidates:
        if candidate.start_date > today:
            # Future flight — always the next one.
            next_flight = candidate
            break

        # Flight is today — determine if departure time has already passed.
        dep_time = candidate.start_time
        if dep_time is None:
            # Fall back to stored flight history for a scheduled/actual departure time.
            airnav = (
                FlightHistoryAirNavRadar.query.filter_by(flight_id=candidate.id)
                .order_by(FlightHistoryAirNavRadar.created_at.desc())
                .first()
            )
            if airnav:
                dep_dt = airnav.scheduled_departure or airnav.actual_departure
                if dep_dt:
                    dep_time = dep_dt.time()

        if dep_time is None:
            # No time info at all — show this flight (can't tell if it's done).
            next_flight = candidate
            break

        if current_time < dep_time:
            # Flight hasn't departed yet.
            next_flight = candidate
            break
        # Departure time has passed — skip to the next candidate.
    next_flight_card = None
    if next_flight:
        nf_reg = (next_flight.aircraft_registration or "").strip().upper()
        nf_airline = next_flight.operating_airline_code or next_flight.airline_code
        nf_thumb = build_aircraft_thumbnail(nf_reg) if nf_reg else None
        nf_airline_name = lookup_airline_name(resolve_airline_code(nf_airline, None)) if nf_airline else None
        nf_logo_url = build_airline_logo_url(resolve_airline_code(nf_airline, None)) if nf_airline else None
        next_flight_card = {
            "id": next_flight.id,
            "date": next_flight.start_date.isoformat() if next_flight.start_date else None,
            "time": next_flight.start_time.strftime("%H:%M") if next_flight.start_time else None,
            "airline_code": nf_airline,
            "airline_name": nf_airline_name,
            "airline_logo_url": nf_logo_url,
            "flight_number": next_flight.flight_number,
            "origin": next_flight.origin_name,
            "origin_code": next_flight.start_airport,
            "destination": next_flight.destination_name,
            "destination_code": next_flight.end_airport,
            "aircraft": next_flight.aircraft,
            "aircraft_registration": nf_reg or None,
            "thumbnail_url": nf_thumb.get("thumbnail_url") if nf_thumb else None,
            "photo_url": nf_thumb.get("photo_url") if nf_thumb else None,
        }

    return render_template(
        "dashboard.html",
        flights=reporting_flights[:10],
        stats=stats,
        map_routes=map_routes,
        chart_payload=json.dumps(chart_payload),
        travellers=[
            {"label": label, "key": traveller_key(label), "count": count}
            for label, count in travellers_sorted
        ],
        booking_sites=[
            {"label": label, "key": booking_site_key(label), "count": count}
            for label, count in booking_sites_sorted
        ],
        dashboard_flights=dashboard_flights,
        airline_card=airline_card,
        next_airlines=next_airlines,
        top_country_flags=top_country_flags,
        top_aircraft_thumb=top_aircraft_thumb,
        top_tailnumber_thumb=top_tailnumber_thumb,
        first_flight_summary=first_flight_summary,
        first_flight_thumb=first_flight_thumb,
        last_flight_summary=last_flight_summary,
        last_flight_thumb=last_flight_thumb,
        next_flight_card=next_flight_card,
        airline_lookup=AIRLINE_LOOKUP,
        airline_logo_template=LOGO_URL_TEMPLATE,
        today_iso=date.today().isoformat(),
    )


@main_bp.route("/timeline")
def timeline():
    """Display chronological timeline view of flights and trips."""
    group_by_trips = request.args.get('group', 'trips') == 'trips'
    sort_order = request.args.get('sort', 'asc')

    timeline_items = build_timeline_data(group_by_trips)

    if sort_order == 'desc':
        timeline_items.reverse()

    # Calculate max duration for relative bar sizing
    max_duration = 0
    for item in timeline_items:
        if item['type'] == 'trip':
            for flight in item['flights']:
                if flight.start_date and flight.end_date:
                    duration = (flight.end_date - flight.start_date).days
                    max_duration = max(max_duration, duration)
        else:
            flight = item['flight']
            if flight.start_date and flight.end_date:
                duration = (flight.end_date - flight.start_date).days
                max_duration = max(max_duration, duration)

    # Enrich with aircraft thumbnails
    for item in timeline_items:
        flights_to_process = item['flights'] if item['type'] == 'trip' else [item['flight']]
        for flight in flights_to_process:
            flight.aircraft_thumb = build_aircraft_thumbnail(flight.aircraft_registration)

    return render_template(
        'timeline.html',
        timeline_items=timeline_items,
        group_by_trips=group_by_trips,
        sort_order=sort_order,
        max_duration=max_duration or 1,
    )


@main_bp.route("/achievements")
def achievements():
    """Display earned and locked achievements."""
    from app.services.analytics import get_all_achievements

    flights = (
        approved_flights_query(include_group_members=True)
        .order_by(Flight.start_date.asc())
        .all()
    )
    reporting_flights = merged_flights_for_reporting(flights)
    stats = summarize_flights(reporting_flights)

    achievements_list = get_all_achievements(reporting_flights, stats)

    # Separate earned vs locked
    earned = [a for a in achievements_list if a['progress']['earned']]
    locked = [a for a in achievements_list if not a['progress']['earned']]

    return render_template(
        'achievements.html',
        achievements=achievements_list,
        earned=earned,
        locked=locked,
        stats=stats,
    )


@main_bp.route("/insights")
def insights():
    """Display AI-generated flight history insights."""
    from app.services.gemini_insights import get_cached_insights

    flights = (
        approved_flights_query(include_group_members=True)
        .order_by(Flight.start_date.asc())
        .all()
    )
    reporting_flights = merged_flights_for_reporting(flights)
    stats = summarize_flights(reporting_flights)

    cached = get_cached_insights(stats["total_flights"], stats["total_miles"])
    insights_data = cached.get("insights") if cached else None
    is_stale = cached.get("is_stale", False) if cached else False
    generated_at = cached.get("generated_at") if cached else None

    return render_template(
        "insights.html",
        stats=stats,
        insights=insights_data,
        insights_json=json.dumps(insights_data) if insights_data else "null",
        is_stale=is_stale,
        generated_at=generated_at,
    )


@main_bp.route("/api/insights/generate", methods=["POST"])
def api_generate_insights():
    """Generate fresh AI insights via Gemini."""
    from app.services.gemini_insights import (
        GeminiInsightsError,
        generate_insights,
        save_cached_insights,
    )

    flights = (
        approved_flights_query(include_group_members=True)
        .order_by(Flight.start_date.asc())
        .all()
    )
    reporting_flights = merged_flights_for_reporting(flights)
    stats = summarize_flights(reporting_flights)

    try:
        result = generate_insights(reporting_flights, stats)
        save_cached_insights(result, stats["total_flights"], stats["total_miles"])
        return jsonify({"ok": True, "insights": result})
    except GeminiInsightsError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


@main_bp.route("/aircraft")
def aircraft_list():
    flights = approved_flights_query().order_by(Flight.start_date.desc()).all()
    registrations = {}
    for flight in flights:
        registration = (flight.aircraft_registration or "").strip().upper()
        if not registration:
            continue
        registrations.setdefault(registration, []).append(flight)

    aircrafts = []
    for registration, matches in sorted(registrations.items()):
        details = get_aircraft_details(registration) or {}
        last_flight = None
        for flight in matches:
            if not flight.start_date:
                continue
            if not last_flight or flight.start_date > last_flight:
                last_flight = flight.start_date
        aircrafts.append(
            {
                "registration": registration,
                "type": details.get("type"),
                "icao_type": details.get("icao_type"),
                "manufacturer": details.get("manufacturer"),
                "mode_s": details.get("mode_s"),
                "owner_country_iso": details.get("registered_owner_country_iso_name"),
                "owner_country": details.get("registered_owner_country_name"),
                "owner_operator": details.get("registered_owner_operator_flag_code"),
                "owner": details.get("registered_owner"),
                "photo_url": details.get("url_photo"),
                "thumbnail_url": details.get("url_photo_thumbnail"),
                "flight_count": len(matches),
                "last_flight_date": last_flight.isoformat() if last_flight else None,
                "source_url": f"https://api.adsbdb.com/v0/aircraft/{registration}",
            }
        )

    return render_template("aircraft.html", aircrafts=aircrafts)


@main_bp.route("/admin/badges")
def admin_badges_list():
    """List all achievement badges for admin management."""
    from app.models import AchievementBadge

    badges = AchievementBadge.query.order_by(
        AchievementBadge.display_order,
        AchievementBadge.id
    ).all()
    return render_template('admin_badges.html', badges=badges)


@main_bp.route("/admin/badges/new", methods=["GET", "POST"])
def admin_badges_new():
    """Create new achievement badge."""
    from app.models import AchievementBadge

    if request.method == "POST":
        badge = AchievementBadge(
            name=request.form.get("name"),
            description=request.form.get("description"),
            category=request.form.get("category") or None,
            badge_type=request.form.get("badge_type"),
            threshold_value=parse_int(request.form.get("threshold_value")),
            icon_emoji=request.form.get("icon_emoji") or None,
            icon_url=request.form.get("icon_url") or None,
            display_order=parse_int(request.form.get("display_order")) or 0,
            is_active=request.form.get("is_active") == "on",
        )
        db.session.add(badge)
        db.session.commit()
        flash(f"Badge '{badge.name}' created.", "success")
        return redirect(url_for("main.admin_badges_list"))

    return render_template("admin_badge_form.html", badge=None)


@main_bp.route("/admin/badges/<int:badge_id>/edit", methods=["GET", "POST"])
def admin_badges_edit(badge_id):
    """Edit existing achievement badge."""
    from app.models import AchievementBadge

    badge = AchievementBadge.query.get_or_404(badge_id)

    if request.method == "POST":
        badge.name = request.form.get("name")
        badge.description = request.form.get("description")
        badge.category = request.form.get("category") or None
        badge.badge_type = request.form.get("badge_type")
        badge.threshold_value = parse_int(request.form.get("threshold_value"))
        badge.icon_emoji = request.form.get("icon_emoji") or None
        badge.icon_url = request.form.get("icon_url") or None
        badge.display_order = parse_int(request.form.get("display_order")) or 0
        badge.is_active = request.form.get("is_active") == "on"

        db.session.commit()
        flash(f"Badge '{badge.name}' updated.", "success")
        return redirect(url_for("main.admin_badges_list"))

    return render_template("admin_badge_form.html", badge=badge)


@main_bp.route("/admin/badges/<int:badge_id>/delete", methods=["POST"])
def admin_badges_delete(badge_id):
    """Delete achievement badge."""
    from app.models import AchievementBadge

    badge = AchievementBadge.query.get_or_404(badge_id)
    name = badge.name
    db.session.delete(badge)
    db.session.commit()
    flash(f"Badge '{name}' deleted.", "success")
    return redirect(url_for("main.admin_badges_list"))


@main_bp.route("/webhooks/n8n", methods=["POST"])
def n8n_webhook():
    auth_error = require_n8n_auth()
    if auth_error:
        return auth_error

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Invalid JSON payload."}), 400

    def is_blank(value):
        return value is None or (isinstance(value, str) and value.strip() == "")

    def normalize_flight_number(value):
        if not value:
            return None
        trimmed = str(value).strip().replace(" ", "")
        if not trimmed:
            return None
        if trimmed.isdigit():
            return trimmed.lstrip("0") or "0"
        prefix = "".join(char for char in trimmed if char.isalpha())
        suffix = "".join(char for char in trimmed if char.isdigit())
        if not suffix:
            return trimmed.upper()
        return f"{prefix.upper()}{suffix.lstrip('0') or '0'}"

    def resolve_airport_coords(airport_code, country_hint=None):
        if not airport_code:
            return None
        code = airport_code.strip().upper()
        queries = [f"{code} airport", code]
        if country_hint:
            country = country_hint.strip()
            queries.insert(0, f"{code} airport {country}")
            queries.insert(1, f"{code}, {country}")
        for query in queries:
            details = lookup_location(query)
            if details and details.get("latitude") is not None and details.get("longitude") is not None:
                return details
        return None

    def build_flight(data, missing_prefix=""):
        trip_name = (data.get("trip_name") or "").strip()
        start_city_name = (data.get("start_city_name") or "").strip()
        start_country = (data.get("start_country") or "").strip()
        end_city_name = (data.get("end_city_name") or "").strip()
        end_country = (data.get("end_country") or "").strip()
        airline_code = (data.get("airline_code") or "").strip()
        flight_number = normalize_flight_number(data.get("flight_number"))
        start_date = parse_date(data.get("start_date"))
        end_date = parse_date(data.get("end_date"))

        missing = []
        if is_blank(start_city_name):
            missing.append(f"{missing_prefix}start_city_name")
        if is_blank(end_city_name):
            missing.append(f"{missing_prefix}end_city_name")
        if is_blank(airline_code):
            missing.append(f"{missing_prefix}airline_code")
        if is_blank(flight_number):
            missing.append(f"{missing_prefix}flight_number")
        if not start_date:
            missing.append(f"{missing_prefix}start_date")
        if not end_date:
            missing.append(f"{missing_prefix}end_date")

        base_city = (home_city() or "").strip().lower()
        base_country = home_country()
        if base_city and base_country:
            if start_city_name.lower() == base_city and not start_country:
                start_country = base_country
            if end_city_name.lower() == base_city and not end_country:
                end_country = base_country

        flight = Flight(
            status=DRAFT_STATUS,
            trip_name=trip_name or None,
            trip_id=data.get("trip_id") or None,
            trip_type=data.get("trip_type") or None,
            activity_id=data.get("activity_id") or None,
            activity_cost=parse_decimal(data.get("activity_cost")),
            url=data.get("url") or None,
            booking_site="n8n",
            supplier_confirmation=data.get("supplier_confirmation") or None,
            booking_date=parse_date(data.get("booking_date")),
            booking_site_phone=data.get("booking_site_phone") or None,
            traveller=(data.get("traveller") or default_traveller()),
            ticket_number=data.get("ticket_number") or None,
            airline_code=airline_code or None,
            aircraft=data.get("aircraft") or None,
            service_class=data.get("service_class") or None,
            flight_number=flight_number or None,
            start_country=start_country or None,
            start_city_name=start_city_name or None,
            start_airport=data.get("start_airport") or None,
            start_terminal=data.get("start_terminal") or None,
            start_lat=parse_float(data.get("start_lat")),
            start_long=parse_float(data.get("start_long")),
            start_date=start_date,
            start_time=parse_time(data.get("start_time")),
            end_country=end_country or None,
            end_city_name=end_city_name or None,
            end_airport=data.get("end_airport") or None,
            end_terminal=data.get("end_terminal") or None,
            end_lat=parse_float(data.get("end_lat")),
            end_long=parse_float(data.get("end_long")),
            end_date=end_date,
            end_time=parse_time(data.get("end_time")),
            stops=parse_int(data.get("stops")),
            distance=parse_float(data.get("distance")),
        )
        if (
            flight.distance is None
            and flight.start_airport
            and flight.end_airport
            and (flight.start_lat is None or flight.start_long is None or flight.end_lat is None or flight.end_long is None)
        ):
            start_details = resolve_airport_coords(
                flight.start_airport, flight.start_country
            )
            end_details = resolve_airport_coords(flight.end_airport, flight.end_country)
            if start_details:
                flight.start_lat = flight.start_lat or start_details.get("latitude")
                flight.start_long = flight.start_long or start_details.get("longitude")
            if end_details:
                flight.end_lat = flight.end_lat or end_details.get("latitude")
                flight.end_long = flight.end_long or end_details.get("longitude")
        if flight.distance is None:
            flight.distance = compute_distance(
                flight.start_lat, flight.start_long, flight.end_lat, flight.end_long
            )
        return flight, missing

    if "flights" in payload:
        flights_payload = payload.get("flights")
        if not isinstance(flights_payload, list) or not flights_payload:
            return (
                jsonify({"ok": False, "error": "Invalid flights payload."}),
                400,
            )
        flights = []
        missing = []
        for idx, flight_payload in enumerate(flights_payload):
            if not isinstance(flight_payload, dict):
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": "Invalid flights payload.",
                        }
                    ),
                    400,
                )
            flight, flight_missing = build_flight(
                flight_payload, missing_prefix=f"flights[{idx}]."
            )
            flights.append(flight)
            missing.extend(flight_missing)

        if missing:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "Missing or invalid required fields.",
                        "missing": missing,
                    }
                ),
                400,
            )

        for flight in flights:
            db.session.add(flight)
        db.session.commit()
        return jsonify({"ok": True, "ids": [flight.id for flight in flights]}), 201

    primary_flight, missing = build_flight(payload)
    return_payload = payload.get("return_flight")
    return_flight = None
    if return_payload is not None:
        if not isinstance(return_payload, dict):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "Invalid return_flight payload.",
                    }
                ),
                400,
            )
        return_flight, return_missing = build_flight(
            return_payload, missing_prefix="return_flight."
        )
        missing.extend(return_missing)

    if missing:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Missing or invalid required fields.",
                    "missing": missing,
                }
            ),
            400,
        )

    db.session.add(primary_flight)
    if return_flight:
        db.session.add(return_flight)
    db.session.commit()

    response_payload = {"ok": True, "id": primary_flight.id}
    if return_flight:
        response_payload["return_id"] = return_flight.id
    return jsonify(response_payload), 201


@main_bp.route("/trips")
def trip_list():
    trips = Trip.query.filter(Trip.deleted_at.is_(None)).order_by(Trip.start_date.desc(), Trip.id.desc()).all()
    return render_template(
        "trips.html",
        trips=trips,
        trip_display_date=trip_display_date,
    )


@main_bp.route("/trips/new", methods=["GET", "POST"])
def trip_new():
    if request.method == "POST":
        next_url = request.form.get("next")
        payloads = extract_trip_leg_payloads(request.form)
        errors = []

        trip_code = request.form.get("trip_code") or None
        if trip_code:
            existing = Trip.query.filter(Trip.trip_code == trip_code).first()
            if existing:
                errors.append("Trip ID already exists.")

        for idx, payload in enumerate(payloads):
            if payload.get("delete") == "1":
                continue
            if is_trip_leg_blank(payload) and not payload.get("id"):
                continue
            error = validate_trip_leg_payload(payload, index_label=str(idx + 1))
            if error:
                errors.append(error)

        if errors:
            for message in errors:
                flash(message, "error")
            trip = Trip(
                name=request.form.get("name") or None,
                trip_code=trip_code,
                trip_type=request.form.get("trip_type") or None,
                notes=request.form.get("notes") or None,
            )
            trip.start_date_year = parse_int(request.form.get("start_year"))
            trip.start_date_month = parse_int(request.form.get("start_month"))
            trip.start_date_day = parse_int(request.form.get("start_day"))
            trip.start_date_precision = normalize_date_precision(
                request.form.get("start_precision"),
                trip.start_date_year,
                trip.start_date_month,
                trip.start_date_day,
            )
            trip.start_date = build_canonical_date(
                trip.start_date_year,
                trip.start_date_month,
                trip.start_date_day,
                trip.start_date_precision,
            )
            trip.end_date_year = parse_int(request.form.get("end_year"))
            trip.end_date_month = parse_int(request.form.get("end_month"))
            trip.end_date_day = parse_int(request.form.get("end_day"))
            trip.end_date_precision = normalize_date_precision(
                request.form.get("end_precision"),
                trip.end_date_year,
                trip.end_date_month,
                trip.end_date_day,
            )
            trip.end_date = build_canonical_date(
                trip.end_date_year,
                trip.end_date_month,
                trip.end_date_day,
                trip.end_date_precision,
            )
            legs = []
            for idx, payload in enumerate(payloads):
                if payload.get("delete") == "1":
                    continue
                if is_trip_leg_blank(payload) and not payload.get("id"):
                    continue
                leg = build_trip_leg_from_payload(payload)
                leg.sequence = resolve_leg_sequence(payload, idx + 1)
                legs.append(leg)
            legs = sorted(legs, key=lambda leg: (leg.sequence, leg.id or 0))
            if not legs:
                legs = [TripLeg(sequence=1, mode="flight")]
            return render_template(
                "trip_form.html",
                trip=trip,
                legs=legs,
                next_url=next_url,
                date_precisions=DATE_PRECISIONS,
                leg_modes=LEG_MODES,
                trip_display_date=trip_display_date,
                trip_leg_display_date=trip_leg_display_date,
            )

        trip = Trip(
            name=request.form.get("name") or None,
            trip_code=trip_code,
            trip_type=request.form.get("trip_type") or None,
            notes=request.form.get("notes") or None,
        )
        trip.start_date_year = parse_int(request.form.get("start_year"))
        trip.start_date_month = parse_int(request.form.get("start_month"))
        trip.start_date_day = parse_int(request.form.get("start_day"))
        trip.start_date_precision = normalize_date_precision(
            request.form.get("start_precision"),
            trip.start_date_year,
            trip.start_date_month,
            trip.start_date_day,
        )
        trip.start_date = build_canonical_date(
            trip.start_date_year,
            trip.start_date_month,
            trip.start_date_day,
            trip.start_date_precision,
        )
        trip.end_date_year = parse_int(request.form.get("end_year"))
        trip.end_date_month = parse_int(request.form.get("end_month"))
        trip.end_date_day = parse_int(request.form.get("end_day"))
        trip.end_date_precision = normalize_date_precision(
            request.form.get("end_precision"),
            trip.end_date_year,
            trip.end_date_month,
            trip.end_date_day,
        )
        trip.end_date = build_canonical_date(
            trip.end_date_year,
            trip.end_date_month,
            trip.end_date_day,
            trip.end_date_precision,
        )

        db.session.add(trip)
        db.session.flush()

        legs = []
        for idx, payload in enumerate(payloads):
            if payload.get("delete") == "1":
                continue
            if is_trip_leg_blank(payload) and not payload.get("id"):
                continue
            leg = TripLeg(trip_id=trip.id)
            apply_trip_leg_payload(
                leg, payload, sequence_override=resolve_leg_sequence(payload, idx + 1)
            )
            db.session.add(leg)
            legs.append(leg)

        db.session.flush()
        for leg in legs:
            error = sync_trip_leg_flight(leg, trip)
            if error:
                flash(error, "error")
                return render_template(
                    "trip_form.html",
                    trip=trip,
                    legs=sorted(
                        legs, key=lambda leg: (leg.sequence, leg.id or 0)
                    ),
                    next_url=next_url,
                    date_precisions=DATE_PRECISIONS,
                    leg_modes=LEG_MODES,
                    trip_display_date=trip_display_date,
                    trip_leg_display_date=trip_leg_display_date,
                )

        db.session.commit()
        flash("Trip saved.", "success")
        return redirect(resolve_redirect_target(next_url, "main.trip_list"))

    next_url = request.args.get("next")
    return render_template(
        "trip_form.html",
        trip=None,
        legs=[TripLeg(sequence=1, mode="flight")],
        next_url=next_url,
        date_precisions=DATE_PRECISIONS,
        leg_modes=LEG_MODES,
        trip_display_date=trip_display_date,
        trip_leg_display_date=trip_leg_display_date,
    )


@main_bp.route("/trips/<int:trip_id>")
def trip_detail(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    legs = sorted(trip.legs, key=lambda leg: (leg.sequence, leg.id or 0))
    return render_template(
        "trip_detail.html",
        trip=trip,
        legs=legs,
        trip_display_date=trip_display_date,
        trip_leg_display_date=trip_leg_display_date,
    )


@main_bp.route("/trips/<int:trip_id>/edit", methods=["GET", "POST"])
def trip_edit(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    if request.method == "POST":
        next_url = request.form.get("next")
        payloads = extract_trip_leg_payloads(request.form)
        errors = []

        trip_code = request.form.get("trip_code") or None
        if trip_code:
            existing = Trip.query.filter(Trip.trip_code == trip_code).first()
            if existing and existing.id != trip.id:
                errors.append("Trip ID already exists.")

        for idx, payload in enumerate(payloads):
            if payload.get("delete") == "1":
                continue
            if is_trip_leg_blank(payload) and not payload.get("id"):
                continue
            error = validate_trip_leg_payload(payload, index_label=str(idx + 1))
            if error:
                errors.append(error)

        if errors:
            for message in errors:
                flash(message, "error")
            trip.name = request.form.get("name") or None
            trip.trip_code = trip_code
            trip.trip_type = request.form.get("trip_type") or None
            trip.notes = request.form.get("notes") or None
            trip.start_date_year = parse_int(request.form.get("start_year"))
            trip.start_date_month = parse_int(request.form.get("start_month"))
            trip.start_date_day = parse_int(request.form.get("start_day"))
            trip.start_date_precision = normalize_date_precision(
                request.form.get("start_precision"),
                trip.start_date_year,
                trip.start_date_month,
                trip.start_date_day,
            )
            trip.start_date = build_canonical_date(
                trip.start_date_year,
                trip.start_date_month,
                trip.start_date_day,
                trip.start_date_precision,
            )
            trip.end_date_year = parse_int(request.form.get("end_year"))
            trip.end_date_month = parse_int(request.form.get("end_month"))
            trip.end_date_day = parse_int(request.form.get("end_day"))
            trip.end_date_precision = normalize_date_precision(
                request.form.get("end_precision"),
                trip.end_date_year,
                trip.end_date_month,
                trip.end_date_day,
            )
            trip.end_date = build_canonical_date(
                trip.end_date_year,
                trip.end_date_month,
                trip.end_date_day,
                trip.end_date_precision,
            )
            legs = []
            for idx, payload in enumerate(payloads):
                if payload.get("delete") == "1":
                    continue
                if is_trip_leg_blank(payload) and not payload.get("id"):
                    continue
                leg = build_trip_leg_from_payload(payload)
                leg.sequence = resolve_leg_sequence(payload, idx + 1)
                legs.append(leg)
            legs = sorted(legs, key=lambda leg: (leg.sequence, leg.id or 0))
            if not legs:
                legs = [TripLeg(sequence=1, mode="flight")]
            return render_template(
                "trip_form.html",
                trip=trip,
                legs=legs,
                next_url=next_url,
                date_precisions=DATE_PRECISIONS,
                leg_modes=LEG_MODES,
                trip_display_date=trip_display_date,
                trip_leg_display_date=trip_leg_display_date,
            )

        trip.name = request.form.get("name") or None
        trip.trip_code = trip_code
        trip.trip_type = request.form.get("trip_type") or None
        trip.notes = request.form.get("notes") or None
        trip.start_date_year = parse_int(request.form.get("start_year"))
        trip.start_date_month = parse_int(request.form.get("start_month"))
        trip.start_date_day = parse_int(request.form.get("start_day"))
        trip.start_date_precision = normalize_date_precision(
            request.form.get("start_precision"),
            trip.start_date_year,
            trip.start_date_month,
            trip.start_date_day,
        )
        trip.start_date = build_canonical_date(
            trip.start_date_year,
            trip.start_date_month,
            trip.start_date_day,
            trip.start_date_precision,
        )
        trip.end_date_year = parse_int(request.form.get("end_year"))
        trip.end_date_month = parse_int(request.form.get("end_month"))
        trip.end_date_day = parse_int(request.form.get("end_day"))
        trip.end_date_precision = normalize_date_precision(
            request.form.get("end_precision"),
            trip.end_date_year,
            trip.end_date_month,
            trip.end_date_day,
        )
        trip.end_date = build_canonical_date(
            trip.end_date_year,
            trip.end_date_month,
            trip.end_date_day,
            trip.end_date_precision,
        )

        existing_legs = {leg.id: leg for leg in trip.legs}
        updated_legs = []
        for idx, payload in enumerate(payloads):
            if payload.get("delete") == "1":
                leg_id = parse_int(payload.get("id"))
                if leg_id and leg_id in existing_legs:
                    leg = existing_legs[leg_id]
                    if leg.flight:
                        db.session.delete(leg.flight)
                    db.session.delete(leg)
                continue
            if is_trip_leg_blank(payload) and not payload.get("id"):
                continue
            leg_id = parse_int(payload.get("id"))
            if leg_id and leg_id in existing_legs:
                leg = existing_legs[leg_id]
            else:
                leg = TripLeg(trip_id=trip.id)
                db.session.add(leg)
            apply_trip_leg_payload(
                leg, payload, sequence_override=resolve_leg_sequence(payload, idx + 1)
            )
            updated_legs.append(leg)

        db.session.flush()
        for leg in updated_legs:
            error = sync_trip_leg_flight(leg, trip)
            if error:
                flash(error, "error")
                return render_template(
                    "trip_form.html",
                    trip=trip,
                    legs=sorted(
                        updated_legs, key=lambda leg: (leg.sequence, leg.id or 0)
                    ),
                    next_url=next_url,
                    date_precisions=DATE_PRECISIONS,
                    leg_modes=LEG_MODES,
                    trip_display_date=trip_display_date,
                    trip_leg_display_date=trip_leg_display_date,
                )

        db.session.commit()
        flash("Trip updated.", "success")
        return redirect(resolve_redirect_target(next_url, "main.trip_list"))

    next_url = request.args.get("next")
    legs = sorted(trip.legs, key=lambda leg: (leg.sequence, leg.id or 0))
    if not legs:
        legs = [TripLeg(sequence=1, mode="flight")]
    return render_template(
        "trip_form.html",
        trip=trip,
        legs=legs,
        next_url=next_url,
        date_precisions=DATE_PRECISIONS,
        leg_modes=LEG_MODES,
        trip_display_date=trip_display_date,
        trip_leg_display_date=trip_leg_display_date,
    )


@main_bp.route("/flights")
def flight_list():
    flights = (
        approved_flights_query(include_group_members=True)
        .order_by(Flight.start_date.asc())
        .all()
    )
    groups = group_flights_by_route_date(flights)
    duplicate_ids = {
        flight.id
        for group in groups
        if group["count"] > 1
        for flight in group["flights"]
    }
    window_days = current_app.config.get("MISSING_LEG_WINDOW_DAYS", 30)
    missing_entries, _ = build_missing_leg_audit(
        flights,
        window_days=window_days,
        include_ungrouped=False,
    )
    missing_leg_ids = {entry["flight"].id for entry in missing_entries}
    traveller_counts = Counter()
    for flight in flights:
        label = (flight.traveller or "").strip() or "Unknown"
        traveller_counts[label] += 1

    booking_site_counts = Counter()
    for flight in flights:
        label = (flight.booking_site or "").strip() or "Unknown"
        booking_site_counts[label] += 1

    for flight in flights:
        flight.traveller_key = traveller_key(flight.traveller)
        flight.booking_site_key = booking_site_key(flight.booking_site)

    grouped = defaultdict(list)
    for flight in flights:
        group_key = flight.grouping_id or f"single-{flight.id}"
        grouped[group_key].append(flight)
    grouped_list = []
    for key, items in grouped.items():
        # Rows stay in date order; the primary is the newest member, the
        # record the dashboard, MCP server and API report for the group.
        items_sorted = sorted(items, key=group_sort_key)
        primary = group_primary(items) if items else None
        for flight in items_sorted:
            flight.group_key = key
            flight.is_group_primary = bool(primary and flight.id == primary.id)
        grouped_list.append(
            {
                "key": key,
                "flights": items_sorted,
                "primary": primary,
            }
        )
    grouped_list.sort(
        key=lambda group: (
            group["primary"].start_date or date.min,
            group["primary"].id or 0,
        )
    )
    for index, group in enumerate(grouped_list, start=1):
        group["row_number"] = index
        for flight in group["flights"]:
            flight.group_row_number = index
    flights = [flight for group in grouped_list for flight in group["flights"]]

    gemini_by_flight = {}
    if flights:
        flight_ids = [flight.id for flight in flights]
        gemini_histories = (
            FlightHistoryAirNavRadar.query.filter(
                FlightHistoryAirNavRadar.flight_id.in_(flight_ids),
                FlightHistoryAirNavRadar.source.in_(["gemini", "gemini_guess"]),
            )
            .order_by(
                FlightHistoryAirNavRadar.created_at.desc(),
                FlightHistoryAirNavRadar.id.desc(),
            )
            .all()
        )
        for history in gemini_histories:
            if history.flight_id in gemini_by_flight:
                continue
            raw_payload = history.raw_payload or {}
            reasoning = None
            if isinstance(raw_payload, dict):
                reasoning = raw_payload.get("reasoning")
                if not reasoning:
                    response = raw_payload.get("response")
                    if isinstance(response, dict):
                        reasoning = response.get("text")
            gemini_by_flight[history.flight_id] = {
                "id": history.id,
                "aircraft_type": history.aircraft_type,
                "aircraft_registration": history.aircraft_registration,
                "reasoning": reasoning,
            }

    history_by_flight = {}
    if flights:
        flight_ids = [flight.id for flight in flights]
        tracked_histories = (
            FlightHistoryAirNavRadar.query.filter(
                FlightHistoryAirNavRadar.flight_id.in_(flight_ids),
                or_(
                    FlightHistoryAirNavRadar.source.is_(None),
                    FlightHistoryAirNavRadar.source.notin_(["gemini", "gemini_guess"]),
                ),
                FlightHistoryAirNavRadar.aircraft_registration.isnot(None),
            )
            .order_by(
                FlightHistoryAirNavRadar.created_at.desc(),
                FlightHistoryAirNavRadar.id.desc(),
            )
            .all()
        )
        for history in tracked_histories:
            if history.flight_id in history_by_flight:
                continue
            history_by_flight[history.flight_id] = {
                "id": history.id,
                "aircraft_type": history.aircraft_type,
                "aircraft_registration": history.aircraft_registration,
            }

    def display_value(value):
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    def blend_value(items, attr):
        # Newest member first, matching merged_flights_for_reporting.
        for item in sorted(items, key=group_sort_key, reverse=True):
            blended = display_value(getattr(item, attr, None))
            if blended:
                return blended
        return None

    grouping_labels = {}
    group_index = 1
    for group in grouped_list:
        grouping_id = group["primary"].grouping_id
        if grouping_id and grouping_id not in grouping_labels:
            grouping_labels[grouping_id] = f"Group {group_index}"
            group_index += 1

    blended_map = {}
    for group in grouped_list:
        primary = group["primary"]
        if not primary:
            continue
        blended_map[primary.id] = {
            "start_date": blend_value(group["flights"], "start_date"),
            "origin_name": blend_value(group["flights"], "origin_name"),
            "destination_name": blend_value(group["flights"], "destination_name"),
            "flight_number": blend_value(group["flights"], "flight_number"),
            "airline_code": blend_value(group["flights"], "airline_code"),
            "booking_site": blend_value(group["flights"], "booking_site"),
            "distance": blend_value(group["flights"], "distance"),
        }

    travellers_sorted = sorted(
        traveller_counts.items(),
        key=lambda item: (-item[1], normalize_key(item[0]) or ""),
    )
    booking_sites_sorted = sorted(
        booking_site_counts.items(),
        key=lambda item: (-item[1], normalize_key(item[0]) or ""),
    )
    top_traveller = travellers_sorted[0] if travellers_sorted else ("-", 0)
    top_booking_site = booking_sites_sorted[0] if booking_sites_sorted else ("-", 0)

    def serialize_flight(flight):
        return {
            "id": flight.id,
            "trip_name": flight.trip_name,
            "trip_id": flight.trip_id,
            "trip_type": flight.trip_type,
            "activity_id": flight.activity_id,
            "activity_cost": str(flight.activity_cost)
            if flight.activity_cost is not None
            else None,
            "url": flight.url,
            "booking_site": flight.booking_site,
            "supplier_confirmation": flight.supplier_confirmation,
            "booking_date": flight.booking_date.isoformat()
            if flight.booking_date
            else None,
            "booking_site_phone": flight.booking_site_phone,
            "traveller": flight.traveller,
            "ticket_number": flight.ticket_number,
            "airline_code": flight.airline_code,
            "aircraft": flight.aircraft,
            "service_class": flight.service_class,
            "flight_number": flight.flight_number,
            "start_country": flight.start_country,
            "start_city_name": flight.start_city_name,
            "start_airport": flight.start_airport,
            "start_terminal": flight.start_terminal,
            "start_lat": flight.start_lat,
            "start_long": flight.start_long,
            "start_date": flight.start_date.isoformat()
            if flight.start_date
            else None,
            "start_time": flight.start_time.strftime("%H:%M")
            if flight.start_time
            else None,
            "end_country": flight.end_country,
            "end_city_name": flight.end_city_name,
            "end_airport": flight.end_airport,
            "end_terminal": flight.end_terminal,
            "end_lat": flight.end_lat,
            "end_long": flight.end_long,
            "end_date": flight.end_date.isoformat() if flight.end_date else None,
            "end_time": flight.end_time.strftime("%H:%M") if flight.end_time else None,
            "stops": flight.stops,
            "distance": flight.distance,
            "route_direction": flight.route_direction,
            "origin_name": flight.origin_name,
            "destination_name": flight.destination_name,
            "grouping_id": flight.grouping_id,
        }

    flights_payload = [serialize_flight(flight) for flight in flights]
    return render_template(
        "flights.html",
        flights=flights,
        duplicate_ids=duplicate_ids,
        missing_leg_ids=missing_leg_ids,
        grouping_labels=grouping_labels,
        blended_map=blended_map,
        travellers=[
            {"label": label, "key": traveller_key(label), "count": count}
            for label, count in travellers_sorted
        ],
        booking_sites=[
            {"label": label, "key": booking_site_key(label), "count": count}
            for label, count in booking_sites_sorted
        ],
        traveller_summary={
            "total": len(travellers_sorted),
            "top_label": top_traveller[0],
            "top_count": top_traveller[1],
        },
        booking_site_summary={
            "total": len(booking_sites_sorted),
            "top_label": top_booking_site[0],
            "top_count": top_booking_site[1],
        },
        gemini_by_flight=gemini_by_flight,
        history_by_flight=history_by_flight,
        flights_json=json.dumps(flights_payload),
    )


@main_bp.route("/flights/merge", methods=["POST"])
def flight_merge():
    selected_raw = request.form.get("selected_ids", "")
    primary_raw = request.form.get("primary_id", "")
    next_url = request.form.get("next", "")

    redirect_target = resolve_redirect_target(next_url, "main.flight_list")
    selected_ids = [
        int(item)
        for item in selected_raw.split(",")
        if item.strip().isdigit()
    ]
    if primary_raw and primary_raw.isdigit():
        primary_id = int(primary_raw)
    else:
        primary_id = selected_ids[0] if selected_ids else None

    if not selected_ids or len(selected_ids) < 2 or primary_id not in selected_ids:
        flash("Select at least two flights to merge.", "error")
        return redirect(redirect_target)

    flights = Flight.query.filter(Flight.id.in_(selected_ids)).all()
    flights_by_id = {flight.id: flight for flight in flights}
    primary = flights_by_id.get(primary_id)
    if not primary:
        flash("Unable to locate the selected flights to merge.", "error")
        return redirect(redirect_target)

    def is_empty(value):
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ""
        return False

    def merge_booking_sites(*values):
        sites = []
        seen = set()
        for value in values:
            if value is None:
                continue
            for part in str(value).split("+"):
                trimmed = part.strip()
                if not trimmed:
                    continue
                key = trimmed.lower()
                if key in seen:
                    continue
                seen.add(key)
                sites.append(trimmed)
        return "+".join(sites) if sites else None

    float_fields = {"start_lat", "start_long", "end_lat", "end_long", "distance"}
    int_fields = {"stops"}
    date_fields = {"booking_date", "start_date", "end_date"}
    time_fields = {"start_time", "end_time"}
    decimal_fields = {"activity_cost"}

    merged_at = datetime.utcnow()
    others = [flight for flight in flights if flight.id != primary_id]
    for source in others:
        for attr in MERGE_FIELDS:
            if attr == "booking_site":
                merged_booking_site = merge_booking_sites(
                    primary.booking_site,
                    source.booking_site,
                )
                if merged_booking_site != primary.booking_site:
                    primary.booking_site = merged_booking_site
                continue
            if is_empty(getattr(primary, attr)) and not is_empty(
                getattr(source, attr)
            ):
                setattr(primary, attr, getattr(source, attr))
        # Soft-delete like /flights/<id>/delete so sync clients drop the row too.
        source.deleted_at = merged_at
        source.updated_at = merged_at
        stamp_revision(source)

    for attr in MERGE_FIELDS:
        if attr not in request.form:
            continue
        raw_value = request.form.get(attr)
        if attr in decimal_fields:
            value = parse_decimal(raw_value)
        elif attr in float_fields:
            value = parse_float(raw_value)
        elif attr in int_fields:
            value = parse_int(raw_value)
        elif attr in date_fields:
            value = parse_date(raw_value)
        elif attr in time_fields:
            value = parse_time(raw_value)
        else:
            value = raw_value.strip() if raw_value else None
        setattr(primary, attr, value)

    if primary.grouping_id:
        remaining_members = Flight.query.filter(
            Flight.grouping_id == primary.grouping_id,
            Flight.deleted_at.is_(None),
            Flight.id != primary.id,
        ).count()
        if remaining_members == 0:
            primary.grouping_id = None
    primary.updated_at = merged_at
    stamp_revision(primary)
    db.session.commit()
    flash(
        f"Merged {len(selected_ids)} flights into flight {primary.id}.",
        "success",
    )
    return redirect(redirect_target)


@main_bp.route("/audit/duplicates")
def audit_duplicates():
    flights = (
        Flight.query.filter(
            Flight.status.in_([APPROVED_STATUS, DRAFT_STATUS]),
            Flight.deleted_at.is_(None),
        )
        .order_by(Flight.start_date.desc(), Flight.id.desc())
        .all()
    )
    rules = resolve_duplicate_rules(current_app.config.get("DUPLICATE_MATCH_RULES"))
    groups = group_flights_by_match_score(flights, rules)
    partial_groups = group_flights_by_day_month_route(flights, rules)
    existing_signatures = {
        build_duplicate_ignore_signature([flight.id for flight in group["flights"]])
        for group in groups
    }
    filtered_partial_groups = []
    for group in partial_groups:
        signature = build_duplicate_ignore_signature(
            [flight.id for flight in group["flights"]]
        )
        if signature in existing_signatures:
            continue
        key = group.get("key") or ()
        if key and key[0] == "by-day-month":
            month = key[1]
            day = key[2]
            airline = key[3] or "-"
            number = key[4] or "-"
            month_label = calendar.month_abbr[int(month)] if month else "-"
            group["summary_label"] = f"{day:02d} {month_label} · {airline} {number}"
        filtered_partial_groups.append(group)
    groups.extend(filtered_partial_groups)
    ignored_signatures = {
        ignore.signature for ignore in AuditDuplicateIgnore.query.all()
    }
    duplicate_groups = []
    for group in groups:
        if group["count"] <= 1:
            continue
        signature = build_duplicate_ignore_signature(
            [flight.id for flight in group["flights"]]
        )
        group["ignore_signature"] = signature
        grouped_id = group["primary"].grouping_id
        is_suggested = not grouped_id and group.get("match_score")
        if is_suggested and signature in ignored_signatures:
            continue
        duplicate_groups.append(group)
    trips_by_date = defaultdict(list)
    for flight in flights:
        if not flight.start_date:
            continue
        trip_name = (flight.trip_name or "").strip()
        trip_id = (flight.trip_id or "").strip()
        route_label = f"{flight.origin_name} → {flight.destination_name}"
        if trip_name and trip_id:
            label = f"{trip_name} ({trip_id})"
        elif trip_name or trip_id:
            label = trip_name or trip_id
        else:
            if flight.origin_name == "-" and flight.destination_name == "-":
                label = "Unknown"
            else:
                label = route_label
        if label not in trips_by_date[flight.start_date]:
            trips_by_date[flight.start_date].append(label)
    trips_by_date = {
        date_key: sorted(
            labels,
            key=lambda value: normalize_key(value) or "",
        )
        for date_key, labels in trips_by_date.items()
    }

    def serialize_flight(flight):
        return {
            "id": flight.id,
            "trip_name": flight.trip_name,
            "trip_id": flight.trip_id,
            "trip_type": flight.trip_type,
            "activity_id": flight.activity_id,
            "activity_cost": str(flight.activity_cost)
            if flight.activity_cost is not None
            else None,
            "url": flight.url,
            "booking_site": flight.booking_site,
            "supplier_confirmation": flight.supplier_confirmation,
            "booking_date": flight.booking_date.isoformat()
            if flight.booking_date
            else None,
            "booking_site_phone": flight.booking_site_phone,
            "traveller": flight.traveller,
            "ticket_number": flight.ticket_number,
            "airline_code": flight.airline_code,
            "aircraft": flight.aircraft,
            "service_class": flight.service_class,
            "start_date": flight.start_date.isoformat() if flight.start_date else None,
            "start_time": flight.start_time.strftime("%H:%M")
            if flight.start_time
            else None,
            "start_country": flight.start_country,
            "start_city_name": flight.start_city_name,
            "start_airport": flight.start_airport,
            "start_terminal": flight.start_terminal,
            "start_lat": flight.start_lat,
            "start_long": flight.start_long,
            "origin_name": flight.origin_name,
            "destination_name": flight.destination_name,
            "flight_number": flight.flight_number,
            "end_country": flight.end_country,
            "end_city_name": flight.end_city_name,
            "end_airport": flight.end_airport,
            "end_terminal": flight.end_terminal,
            "end_lat": flight.end_lat,
            "end_long": flight.end_long,
            "end_date": flight.end_date.isoformat() if flight.end_date else None,
            "end_time": flight.end_time.strftime("%H:%M") if flight.end_time else None,
            "stops": flight.stops,
            "distance": flight.distance,
            "route_direction": flight.route_direction,
        }

    flights_payload = [serialize_flight(flight) for flight in flights]
    return render_template(
        "audit_duplicates.html",
        groups=duplicate_groups,
        total_flights=len(flights),
        total_groups=len(groups),
        duplicate_groups=len(duplicate_groups),
        trips_by_date=trips_by_date,
        match_threshold=rules.get("threshold", 0),
        show_match_reasons=rules.get("show_reasons", False),
        flights_json=json.dumps(flights_payload),
        audit_title="Duplicate Audit",
        audit_description=(
            "Groups are suggested using weighted signals (date, flight number, route, city, and trip details). "
            "Boarding-pass drafts also add day/month + route + flight number matches."
        ),
        audit_toggle_label="Hide grouped duplicates (default)",
    )


@main_bp.route("/audit/duplicates/exact")
def audit_duplicates_exact():
    flights = approved_flights_query(include_group_members=True).order_by(
        Flight.start_date.desc(), Flight.id.desc()
    ).all()
    excluded_fields = {"id", "created_at", "updated_at"}
    exact_fields = [
        column.name
        for column in Flight.__table__.columns
        if column.name not in excluded_fields
    ]
    groups = defaultdict(list)
    for flight in flights:
        key = tuple(getattr(flight, field) for field in exact_fields)
        groups[key].append(flight)
    duplicate_groups = []
    for items in groups.values():
        if len(items) <= 1:
            continue
        items_sorted = sorted(
            items,
            key=lambda f: (
                f.start_date or date.min,
                f.id or 0,
            ),
            reverse=True,
        )
        duplicate_groups.append(
            {
                "key": ("exact",),
                "flights": items_sorted,
                "primary": items_sorted[0],
                "count": len(items_sorted),
                "match_score": None,
                "match_reasons": [],
            }
        )
    duplicate_groups.sort(
        key=lambda group: (
            group["primary"].start_date or date.min,
            group["count"],
            group["primary"].id or 0,
        ),
        reverse=True,
    )

    trips_by_date = defaultdict(list)
    for flight in flights:
        if not flight.start_date:
            continue
        trip_name = (flight.trip_name or "").strip()
        trip_id = (flight.trip_id or "").strip()
        route_label = f"{flight.origin_name} → {flight.destination_name}"
        if trip_name and trip_id:
            label = f"{trip_name} ({trip_id})"
        elif trip_name or trip_id:
            label = trip_name or trip_id
        else:
            if flight.origin_name == "-" and flight.destination_name == "-":
                label = "Unknown"
            else:
                label = route_label
        if label not in trips_by_date[flight.start_date]:
            trips_by_date[flight.start_date].append(label)
    trips_by_date = {
        date_key: sorted(
            labels,
            key=lambda value: normalize_key(value) or "",
        )
        for date_key, labels in trips_by_date.items()
    }

    def serialize_flight(flight):
        return {
            "id": flight.id,
            "trip_name": flight.trip_name,
            "trip_id": flight.trip_id,
            "trip_type": flight.trip_type,
            "activity_id": flight.activity_id,
            "activity_cost": str(flight.activity_cost)
            if flight.activity_cost is not None
            else None,
            "url": flight.url,
            "booking_site": flight.booking_site,
            "supplier_confirmation": flight.supplier_confirmation,
            "booking_date": flight.booking_date.isoformat()
            if flight.booking_date
            else None,
            "booking_site_phone": flight.booking_site_phone,
            "traveller": flight.traveller,
            "ticket_number": flight.ticket_number,
            "airline_code": flight.airline_code,
            "aircraft": flight.aircraft,
            "service_class": flight.service_class,
            "start_date": flight.start_date.isoformat() if flight.start_date else None,
            "start_time": flight.start_time.strftime("%H:%M")
            if flight.start_time
            else None,
            "start_country": flight.start_country,
            "start_city_name": flight.start_city_name,
            "start_airport": flight.start_airport,
            "start_terminal": flight.start_terminal,
            "start_lat": flight.start_lat,
            "start_long": flight.start_long,
            "origin_name": flight.origin_name,
            "destination_name": flight.destination_name,
            "flight_number": flight.flight_number,
            "end_country": flight.end_country,
            "end_city_name": flight.end_city_name,
            "end_airport": flight.end_airport,
            "end_terminal": flight.end_terminal,
            "end_lat": flight.end_lat,
            "end_long": flight.end_long,
            "end_date": flight.end_date.isoformat() if flight.end_date else None,
            "end_time": flight.end_time.strftime("%H:%M") if flight.end_time else None,
            "stops": flight.stops,
            "distance": flight.distance,
            "route_direction": flight.route_direction,
        }

    flights_payload = [serialize_flight(flight) for flight in flights]
    return render_template(
        "audit_duplicates.html",
        groups=duplicate_groups,
        total_flights=len(flights),
        total_groups=len(groups),
        duplicate_groups=len(duplicate_groups),
        trips_by_date=trips_by_date,
        match_threshold=0,
        show_match_reasons=False,
        flights_json=json.dumps(flights_payload),
        audit_title="Exact Duplicate Audit",
        audit_description="Groups share identical values across every flight record field (excluding ids and timestamps).",
        audit_toggle_label=None,
    )


@main_bp.route("/audit/missing")
def audit_missing():
    def is_blank(column):
        return or_(column.is_(None), column == "")

    def is_empty(value):
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ""
        return False

    def normalize_filter_key(value):
        if not value:
            return None
        return value.strip().lower()

    def has_value(value):
        return not is_empty(value)

    missing_filter = or_(
        is_blank(Flight.airline_code),
        is_blank(Flight.aircraft),
        is_blank(Flight.start_country),
        is_blank(Flight.end_country),
    )
    all_missing_flights = (
        approved_flights_query(include_group_members=True)
        .filter(missing_filter)
        .order_by(Flight.start_date.desc(), Flight.id.desc())
        .all()
    )
    def normalize_group_id(value):
        if not value:
            return None
        return str(value).strip() or None

    grouped_ids = {
        normalize_group_id(flight.grouping_id)
        for flight in all_missing_flights
        if normalize_group_id(flight.grouping_id)
    }
    grouped_flights = (
        Flight.query.filter(Flight.grouping_id.in_(grouped_ids)).all()
        if grouped_ids
        else []
    )
    grouped_values = {}
    for flight in grouped_flights:
        group_id = normalize_group_id(flight.grouping_id)
        if not group_id:
            continue
        grouped_values.setdefault(
            group_id,
            {
                "airline_code": False,
                "aircraft": False,
                "start_country": False,
                "end_country": False,
            },
        )
        group_state = grouped_values[group_id]
        if has_value(flight.airline_code):
            group_state["airline_code"] = True
        if has_value(flight.aircraft):
            group_state["aircraft"] = True
        if has_value(flight.start_country):
            group_state["start_country"] = True
        if has_value(flight.end_country):
            group_state["end_country"] = True

    filter_map = {
        "airline": "airline_code",
        "aircraft": "aircraft",
        "start_country": "start_country",
        "end_country": "end_country",
    }
    filter_labels = {
        "airline": "Missing airline",
        "aircraft": "Missing aircraft",
        "start_country": "Missing start country",
        "end_country": "Missing end country",
    }
    raw_missing_filters = request.args.get("missing", "")
    active_filters = []
    for item in raw_missing_filters.split(","):
        key = normalize_filter_key(item)
        if key in filter_map:
            active_filters.append(key)
    active_filter_labels = [filter_labels[key] for key in active_filters]
    exclude_grouped = request.args.get("exclude_grouped") in ("1", "true", "yes")

    def has_grouped_resolution(flight):
        group_id = normalize_group_id(flight.grouping_id)
        if not group_id:
            return False
        group_state = grouped_values.get(group_id)
        if not group_state:
            return False
        keys_to_check = active_filters or list(filter_map.keys())
        missing_keys = [
            key
            for key in keys_to_check
            if is_empty(getattr(flight, filter_map[key]))
        ]
        if not missing_keys:
            return False
        return all(group_state[filter_map[key]] for key in missing_keys)

    def is_missing_for_key(flight, key):
        field = filter_map[key]
        if not is_empty(getattr(flight, field)):
            return False
        group_id = normalize_group_id(flight.grouping_id)
        if not exclude_grouped or not group_id:
            return True
        group_state = grouped_values.get(group_id)
        if not group_state:
            return True
        return not group_state[field]

    def matches_filter(flight):
        keys_to_check = active_filters or list(filter_map.keys())
        return any(is_missing_for_key(flight, key) for key in keys_to_check)

    flights = [
        flight
        for flight in all_missing_flights
        if matches_filter(flight)
        and (not exclude_grouped or not has_grouped_resolution(flight))
    ]
    for flight in flights:
        labels = []
        if is_missing_for_key(flight, "airline"):
            labels.append("Airline")
        if is_missing_for_key(flight, "aircraft"):
            labels.append("Aircraft")
        if is_missing_for_key(flight, "start_country"):
            labels.append("Start country")
        if is_missing_for_key(flight, "end_country"):
            labels.append("End country")
        flight.missing_labels = labels

    summary = {
        "total": len(all_missing_flights),
        "missing_airline": sum(
            1 for flight in all_missing_flights if is_empty(flight.airline_code)
        ),
        "missing_aircraft": sum(
            1 for flight in all_missing_flights if is_empty(flight.aircraft)
        ),
        "missing_start_country": sum(
            1 for flight in all_missing_flights if is_empty(flight.start_country)
        ),
        "missing_end_country": sum(
            1 for flight in all_missing_flights if is_empty(flight.end_country)
        ),
    }

    return render_template(
        "audit_missing.html",
        flights=flights,
        summary=summary,
        active_filters=active_filters,
        active_filter_labels=active_filter_labels,
        filter_labels=filter_labels,
        exclude_grouped=exclude_grouped,
    )


@main_bp.route("/audit/missing/airline")
def audit_missing_airline():
    def is_empty(value):
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ""
        return False

    flights = (
        approved_flights_query(include_group_members=True)
        .order_by(Flight.start_date.desc(), Flight.id.desc())
        .all()
    )
    missing = [
        flight
        for flight in merged_flights_for_reporting(flights)
        if is_empty(flight.airline_code)
    ]

    return render_template(
        "audit_missing_airline.html",
        flights=missing,
        total=len(missing),
    )


@main_bp.route("/audit/missing/aircraft")
def audit_missing_aircraft():
    def is_empty(value):
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ""
        return False

    flights = (
        approved_flights_query(include_group_members=True)
        .order_by(Flight.start_date.desc(), Flight.id.desc())
        .all()
    )
    flights = [flight for flight in flights if not flight.exclude_from_stats]

    def group_key_for(flight):
        if flight.grouping_id:
            return f"group:{flight.grouping_id}"
        return f"single:{flight.id}"

    history_by_group = {}
    for flight in flights:
        key = group_key_for(flight)
        has_history_aircraft = any(
            (history.aircraft_type or history.aircraft_registration)
            for history in (flight.airnav_histories or [])
        )
        if has_history_aircraft:
            history_by_group[key] = True
        else:
            history_by_group.setdefault(key, False)

    grouped_flights = merged_flights_for_reporting(flights)
    missing = []
    for flight in grouped_flights:
        if not is_empty(flight.aircraft):
            continue
        if history_by_group.get(group_key_for(flight), False):
            continue
        missing.append(flight)

    return render_template(
        "audit_missing_aircraft.html",
        flights=missing,
        total=len(missing),
    )


@main_bp.route("/audit/missing/registration")
def audit_missing_registration():
    def is_empty(value):
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ""
        return False

    flights = (
        approved_flights_query(include_group_members=True)
        .order_by(Flight.start_date.desc(), Flight.id.desc())
        .all()
    )
    flights = [f for f in flights if not f.exclude_from_stats]
    flights = [f for f in flights if (f.airline_code or "").strip().upper() != "9F"]
    missing_raw = [f for f in flights if is_empty(f.aircraft_registration)]

    grouped_flights = merged_flights_for_reporting(missing_raw)
    missing = grouped_flights

    counts_by_year = defaultdict(int)
    for f in missing:
        year = (f.start_date.year if f.start_date else 0) or 0
        counts_by_year[year] += 1
    year_counts = sorted(counts_by_year.items(), key=lambda x: -x[0])

    return render_template(
        "audit_missing_registration.html",
        flights=missing,
        total_raw=len(missing_raw),
        total_grouped=len(missing),
        counts_by_year=year_counts,
    )


@main_bp.route("/audit/missing/routes")
def audit_missing_routes():
    def is_empty(value):
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ""
        return False

    flights = (
        approved_flights_query(include_group_members=True)
        .order_by(Flight.start_date.desc(), Flight.id.desc())
        .all()
    )
    missing = []
    for flight in merged_flights_for_reporting(flights):
        labels = []
        if is_empty(flight.start_airport):
            labels.append("Start airport")
        if is_empty(flight.end_airport):
            labels.append("End airport")
        if labels:
            flight.missing_route_labels = labels
            missing.append(flight)

    return render_template(
        "audit_missing_routes.html",
        flights=missing,
        total=len(missing),
    )


@main_bp.route("/audit/routes/pair")
def audit_routes_pair():
    """Audit every flight between two cities (defaults: home base and blank).

    Query string: ``a``/``b`` are city names, ``a_airports``/``b_airports``
    are optional comma-separated IATA codes that also count as that city.
    """

    def parse_codes(value):
        return {
            code.strip().upper()
            for code in (value or "").split(",")
            if code.strip()
        }

    base_city = home_city() or ""
    city_a = (request.args.get("a") or base_city).strip()
    city_b = (request.args.get("b") or "").strip()
    airports_a = parse_codes(request.args.get("a_airports"))
    if not airports_a and city_a and city_a.lower() == base_city.lower():
        airports_a = set(home_airports())
    airports_b = parse_codes(request.args.get("b_airports"))

    flights = []
    a_to_b = 0
    b_to_a = 0
    if city_a and city_b:

        def city_match(column, name):
            return column.ilike(f"%{name}%")

        def side_filter(city_column, airport_column, name, airports):
            clause = city_match(city_column, name)
            if airports:
                clause = or_(clause, func.upper(airport_column).in_(airports))
            return clause

        start_a = side_filter(Flight.start_city_name, Flight.start_airport, city_a, airports_a)
        end_a = side_filter(Flight.end_city_name, Flight.end_airport, city_a, airports_a)
        start_b = side_filter(Flight.start_city_name, Flight.start_airport, city_b, airports_b)
        end_b = side_filter(Flight.end_city_name, Flight.end_airport, city_b, airports_b)

        flights = (
            approved_flights_query()
            .filter(or_(and_(start_a, end_b), and_(start_b, end_a)))
            .order_by(Flight.start_date.desc(), Flight.id.desc())
            .all()
        )

        key_a = city_a.lower()
        key_b = city_b.lower()
        for flight in flights:
            start_city = (flight.start_city_name or "").strip().lower()
            end_city = (flight.end_city_name or "").strip().lower()
            start_airport = (flight.start_airport or "").strip().upper()
            end_airport = (flight.end_airport or "").strip().upper()

            is_start_a = key_a in start_city or start_airport in airports_a
            is_end_a = key_a in end_city or end_airport in airports_a
            is_start_b = key_b in start_city or start_airport in airports_b
            is_end_b = key_b in end_city or end_airport in airports_b

            if is_start_a and is_end_b:
                flight.route_label = f"{city_a} to {city_b}"
                a_to_b += 1
            elif is_start_b and is_end_a:
                flight.route_label = f"{city_b} to {city_a}"
                b_to_a += 1
            else:
                flight.route_label = f"{city_a}/{city_b}"

    return render_template(
        "audit_routes_pair.html",
        flights=flights,
        total=len(flights),
        city_a=city_a,
        city_b=city_b,
        airports_a=sorted(airports_a),
        airports_b=sorted(airports_b),
        a_to_b=a_to_b,
        b_to_a=b_to_a,
        ready=bool(city_a and city_b),
    )


@main_bp.route("/audit/missing-legs")
def audit_missing_legs():
    flights = (
        approved_flights_query(include_group_members=True)
        .order_by(Flight.start_date.desc(), Flight.id.desc())
        .all()
    )
    include_ungrouped = request.args.get("include_ungrouped") in (
        "1",
        "true",
        "yes",
    )
    window_days = current_app.config.get("MISSING_LEG_WINDOW_DAYS", 30)
    missing_entries, summary = build_missing_leg_audit(
        flights,
        window_days=window_days,
        include_ungrouped=include_ungrouped,
    )
    return render_template(
        "audit_missing_legs.html",
        entries=missing_entries,
        summary=summary,
        include_ungrouped=include_ungrouped,
        window_days=window_days,
    )


@main_bp.route("/audit/gemini/guesses")
def audit_gemini_guesses():
    histories = (
        FlightHistoryAirNavRadar.query.filter(
            FlightHistoryAirNavRadar.source == "gemini_guess"
        )
        .order_by(
            FlightHistoryAirNavRadar.dep_date.desc(),
            FlightHistoryAirNavRadar.id.desc(),
        )
        .all()
    )
    entries = []
    for history in histories:
        raw_payload = history.raw_payload or {}
        details = raw_payload.get("details") if isinstance(raw_payload, dict) else {}
        applied_fields = (
            raw_payload.get("applied_fields") if isinstance(raw_payload, dict) else []
        )
        if not isinstance(applied_fields, list):
            applied_fields = []
        reasoning = raw_payload.get("reasoning") if isinstance(raw_payload, dict) else None
        flight = history.flight
        route_label = "-"
        if flight:
            route_label = f"{flight.origin_name} → {flight.destination_name}"
        else:
            dep_iata = history.dep_airport_iata or "-"
            arr_iata = history.arr_airport_iata or "-"
            route_label = f"{dep_iata} → {arr_iata}"
        entries.append(
            {
                "history": history,
                "flight": flight,
                "route_label": route_label,
                "flight_date": flight.start_date if flight else history.dep_date,
                "applied_fields": applied_fields,
                "scope": details.get("scope"),
                "reasoning": reasoning,
            }
        )

    return render_template(
        "audit_gemini_guesses.html",
        entries=entries,
        total=len(histories),
    )


@main_bp.route("/audit/gemini/codeshares")
def audit_gemini_codeshares():
    histories = (
        FlightHistoryAirNavRadar.query.filter(FlightHistoryAirNavRadar.source == "gemini")
        .order_by(
            FlightHistoryAirNavRadar.dep_date.desc(),
            FlightHistoryAirNavRadar.id.desc(),
        )
        .all()
    )
    entries = []
    for history in histories:
        raw_payload = history.raw_payload or {}
        details = raw_payload.get("details") if isinstance(raw_payload, dict) else {}
        applied_fields = (
            raw_payload.get("applied_fields") if isinstance(raw_payload, dict) else []
        )
        if not isinstance(applied_fields, list):
            applied_fields = []
        flight = history.flight
        route_label = "-"
        if flight:
            route_label = f"{flight.origin_name} → {flight.destination_name}"
        else:
            dep_iata = history.dep_airport_iata or "-"
            arr_iata = history.arr_airport_iata or "-"
            route_label = f"{dep_iata} → {arr_iata}"
        entries.append(
            {
                "history": history,
                "flight": flight,
                "route_label": route_label,
                "flight_date": flight.start_date if flight else history.dep_date,
                "applied_fields": applied_fields,
                "operating_airline_code": details.get("operating_airline_code"),
                "operating_flight_number": details.get("operating_flight_number"),
                "aircraft_type": details.get("aircraft_type"),
            }
        )

    return render_template(
        "audit_gemini_codeshares.html",
        entries=entries,
        total=len(histories),
    )


@main_bp.route("/audit/missing-legs/<int:flight_id>/ignore", methods=["POST"])
def audit_missing_legs_ignore(flight_id):
    flight = Flight.query.get_or_404(flight_id)
    flight.audit_missing_leg_ignored = True
    db.session.commit()
    flash(f"Ignored missing leg audit for flight {flight.id}.", "success")
    redirect_target = resolve_redirect_target(
        request.form.get("next"), "main.audit_missing_legs"
    )
    return redirect(redirect_target)


@main_bp.route("/audit/ignore-grouping", methods=["POST"])
def audit_ignore_grouping():
    selected_raw = request.form.get("selected_ids", "")
    next_url = request.form.get("next", "")

    redirect_target = resolve_redirect_target(next_url, "main.audit_duplicates")
    selected_ids = [
        int(item) for item in selected_raw.split(",") if item.strip().isdigit()
    ]
    if len(selected_ids) < 2:
        flash("Select at least two flights to ignore a grouping.", "error")
        return redirect(redirect_target)

    signature = build_duplicate_ignore_signature(selected_ids)
    existing = AuditDuplicateIgnore.query.filter_by(signature=signature).first()
    if not existing:
        db.session.add(AuditDuplicateIgnore(signature=signature))
        db.session.commit()

    if wants_json_response():
        return jsonify({"ok": True, "ignored": True, "signature": signature})
    flash("Ignored duplicate grouping suggestion.", "success")
    return redirect(redirect_target)


@main_bp.route("/audit/confirm-grouping", methods=["POST"])
def audit_confirm_grouping():
    selected_raw = request.form.get("selected_ids", "")
    next_url = request.form.get("next", "")

    redirect_target = resolve_redirect_target(next_url, "main.audit_duplicates")
    selected_ids = [
        int(item) for item in selected_raw.split(",") if item.strip().isdigit()
    ]
    if len(selected_ids) < 2:
        flash("Select at least two flights to confirm a grouping.", "error")
        return redirect(redirect_target)

    flights = Flight.query.filter(Flight.id.in_(selected_ids)).all()
    if len(flights) < 2:
        flash("Unable to locate the selected flights to group.", "error")
        return redirect(redirect_target)

    grouping_id = next(
        (flight.grouping_id for flight in flights if flight.grouping_id), None
    )
    if not grouping_id:
        grouping_id = str(uuid4())

    grouped_at = datetime.utcnow()
    for flight in flights:
        flight.grouping_id = grouping_id
        flight.updated_at = grouped_at
        stamp_revision(flight)

    # The newest member now represents the group everywhere; give it any
    # detail only the older records carry so nothing drops out of reports.
    members = approved_group_members(grouping_id) or sorted(
        flights, key=group_sort_key, reverse=True
    )
    primary = members[0]
    filled_fields = fill_blank_fields_from_group(primary, members[1:])
    if filled_fields:
        primary.updated_at = grouped_at
        stamp_revision(primary)

    db.session.commit()
    if "application/json" in request.headers.get("Accept", ""):
        return jsonify(
            {
                "ok": True,
                "grouping_id": grouping_id,
                "count": len(flights),
                "primary_id": primary.id,
                "filled_fields": filled_fields,
            }
        )
    flash(
        f"Confirmed grouping for {len(flights)} flights.",
        "success",
    )
    return redirect(redirect_target)


@main_bp.route("/audit/ungroup", methods=["POST"])
def audit_ungroup():
    selected_raw = request.form.get("selected_ids", "")
    next_url = request.form.get("next", "")

    redirect_target = resolve_redirect_target(next_url, "main.audit_duplicates")
    selected_ids = [
        int(item) for item in selected_raw.split(",") if item.strip().isdigit()
    ]
    if len(selected_ids) < 2:
        flash("Select at least two flights to ungroup.", "error")
        return redirect(redirect_target)

    flights = Flight.query.filter(Flight.id.in_(selected_ids)).all()
    if len(flights) < 2:
        flash("Unable to locate the selected flights to ungroup.", "error")
        return redirect(redirect_target)

    ungrouped_at = datetime.utcnow()
    for flight in flights:
        flight.grouping_id = None
        flight.updated_at = ungrouped_at
        stamp_revision(flight)

    db.session.commit()
    if "application/json" in request.headers.get("Accept", ""):
        return jsonify(
            {
                "ok": True,
                "grouping_id": None,
                "count": len(flights),
            }
        )
    flash(
        f"Ungrouped {len(flights)} flights.",
        "success",
    )
    return redirect(redirect_target)


@main_bp.route("/inbox")
def inbox():
    flights = (
        Flight.query.filter(Flight.status == DRAFT_STATUS, Flight.deleted_at.is_(None))
        .order_by(Flight.created_at.desc(), Flight.id.desc())
        .all()
    )
    return render_template("inbox.html", flights=flights)


@main_bp.route("/inbox/<int:flight_id>/approve", methods=["POST"])
def inbox_approve(flight_id):
    flight = Flight.query.get_or_404(flight_id)
    approved = False
    if flight.status != APPROVED_STATUS:
        flight.status = APPROVED_STATUS
        db.session.commit()
        approved = True
    message = "Flight approved and published." if approved else "Flight already approved."
    if wants_json_response():
        remaining = Flight.query.filter(Flight.status == DRAFT_STATUS, Flight.deleted_at.is_(None)).count()
        return jsonify(
            {
                "ok": True,
                "approved": approved,
                "flight_id": flight.id,
                "remaining": remaining,
                "message": message,
            }
        )
    flash(message, "success" if approved else "warning")
    redirect_target = resolve_redirect_target(
        request.form.get("next"), "main.inbox"
    )
    return redirect(redirect_target)


@main_bp.route("/flights/new", methods=["GET", "POST"])
def flight_new():
    if request.method == "POST":
        next_url = request.form.get("next")
        start_date = parse_date(request.form.get("start_date"))
        start_city_name = request.form.get("start_city_name", "").strip() or None
        start_airport = request.form.get("start_airport", "").strip() or None
        end_city_name = request.form.get("end_city_name", "").strip() or None
        end_airport = request.form.get("end_airport", "").strip() or None
        if not start_date or not (start_city_name or start_airport) or not (
            end_city_name or end_airport
        ):
            flash("Start date, start, and end locations are required.", "error")
            return render_template(
                "flight_form.html",
                flight=None,
                prefill=None,
                next_url=next_url,
                flight_histories=[],
                history_counts={},
                airnav_histories=[],
            )

        flight = Flight(
            status=APPROVED_STATUS,
            trip_name=request.form.get("trip_name") or None,
            trip_id=request.form.get("trip_id") or None,
            trip_type=request.form.get("trip_type") or None,
            activity_id=request.form.get("activity_id") or None,
            activity_cost=parse_decimal(request.form.get("activity_cost")),
            url=request.form.get("url") or None,
            booking_site=request.form.get("booking_site") or None,
            supplier_confirmation=request.form.get("supplier_confirmation") or None,
            booking_date=parse_date(request.form.get("booking_date")),
            booking_site_phone=request.form.get("booking_site_phone") or None,
            traveller=request.form.get("traveller") or None,
            ticket_number=request.form.get("ticket_number") or None,
            airline_code=request.form.get("airline_code") or None,
            operating_airline_code=request.form.get("operating_airline_code") or None,
            aircraft=request.form.get("aircraft") or None,
            aircraft_registration=request.form.get("aircraft_registration") or None,
            service_class=request.form.get("service_class") or None,
            flight_number=request.form.get("flight_number") or None,
            operating_flight_number=request.form.get("operating_flight_number") or None,
            start_country=request.form.get("start_country") or None,
            start_city_name=start_city_name,
            start_airport=start_airport,
            start_terminal=request.form.get("start_terminal") or None,
            start_lat=parse_float(request.form.get("start_lat")),
            start_long=parse_float(request.form.get("start_long")),
            start_date=start_date,
            start_time=parse_time(request.form.get("start_time")),
            end_country=request.form.get("end_country") or None,
            end_city_name=end_city_name,
            end_airport=end_airport,
            end_terminal=request.form.get("end_terminal") or None,
            end_lat=parse_float(request.form.get("end_lat")),
            end_long=parse_float(request.form.get("end_long")),
            end_date=parse_date(request.form.get("end_date")),
            end_time=parse_time(request.form.get("end_time")),
            stops=parse_int(request.form.get("stops")),
            distance=parse_float(request.form.get("distance")),
        )
        if flight.distance is None:
            flight.distance = compute_distance(
                flight.start_lat, flight.start_long, flight.end_lat, flight.end_long
            )
        db.session.add(flight)
        db.session.commit()
        flash("Flight saved.", "success")
        return redirect(resolve_redirect_target(next_url, "main.flight_list"))

    next_url = request.args.get("next")
    return render_template(
        "flight_form.html",
        flight=None,
        prefill=None,
        next_url=next_url,
        flight_histories=[],
        history_counts={},
        airnav_histories=[],
    )


@main_bp.route("/flights/<int:flight_id>/duplicate")
def flight_duplicate(flight_id):
    flight = Flight.query.get_or_404(flight_id)
    next_url = request.args.get("next")
    return render_template(
        "flight_form.html",
        flight=None,
        prefill=flight,
        next_url=next_url,
        flight_histories=[],
        history_counts={},
        airnav_histories=[],
    )


@main_bp.route("/flights/<int:flight_id>/edit", methods=["GET", "POST"])
def flight_edit(flight_id):
    flight = Flight.query.get_or_404(flight_id)

    def load_history_context():
        histories = (
            FlightHistory.query.filter_by(flight_id=flight.id)
            .order_by(FlightHistory.created_at.desc())
            .all()
        )
        airnav_histories = (
            FlightHistoryAirNavRadar.query.filter_by(flight_id=flight.id)
            .order_by(FlightHistoryAirNavRadar.created_at.desc())
            .all()
        )
        counts = {}
        if histories:
            history_ids = [history.id for history in histories]
            counts = {
                history_id: count
                for history_id, count in db.session.query(
                    FlightPosition.history_id, func.count(FlightPosition.id)
                )
                .filter(FlightPosition.history_id.in_(history_ids))
                .group_by(FlightPosition.history_id)
                .all()
            }
        return histories, counts, airnav_histories

    if request.method == "POST":
        next_url = request.form.get("next")
        start_date = parse_date(request.form.get("start_date"))
        start_city_name = request.form.get("start_city_name", "").strip() or None
        start_airport = request.form.get("start_airport", "").strip() or None
        end_city_name = request.form.get("end_city_name", "").strip() or None
        end_airport = request.form.get("end_airport", "").strip() or None
        if not start_date or not (start_city_name or start_airport) or not (
            end_city_name or end_airport
        ):
            flash("Start date, start, and end locations are required.", "error")
            histories, history_counts, airnav_histories = load_history_context()
            return render_template(
                "flight_form.html",
                flight=flight,
                prefill=None,
                next_url=next_url,
                flight_histories=histories,
                history_counts=history_counts,
                airnav_histories=airnav_histories,
            )

        flight.trip_name = request.form.get("trip_name") or None
        flight.trip_id = request.form.get("trip_id") or None
        flight.trip_type = request.form.get("trip_type") or None
        flight.activity_id = request.form.get("activity_id") or None
        flight.activity_cost = parse_decimal(request.form.get("activity_cost"))
        flight.url = request.form.get("url") or None
        flight.booking_site = request.form.get("booking_site") or None
        flight.supplier_confirmation = request.form.get("supplier_confirmation") or None
        flight.booking_date = parse_date(request.form.get("booking_date"))
        flight.booking_site_phone = request.form.get("booking_site_phone") or None
        flight.traveller = request.form.get("traveller") or None
        flight.ticket_number = request.form.get("ticket_number") or None
        flight.airline_code = request.form.get("airline_code") or None
        flight.operating_airline_code = (
            request.form.get("operating_airline_code") or None
        )
        flight.aircraft = request.form.get("aircraft") or None
        flight.aircraft_registration = request.form.get("aircraft_registration") or None
        flight.service_class = request.form.get("service_class") or None
        flight.flight_number = request.form.get("flight_number") or None
        flight.operating_flight_number = (
            request.form.get("operating_flight_number") or None
        )
        flight.start_country = request.form.get("start_country") or None
        flight.start_city_name = start_city_name
        flight.start_airport = start_airport
        flight.start_terminal = request.form.get("start_terminal") or None
        flight.start_lat = parse_float(request.form.get("start_lat"))
        flight.start_long = parse_float(request.form.get("start_long"))
        flight.start_date = start_date
        flight.start_time = parse_time(request.form.get("start_time"))
        flight.end_country = request.form.get("end_country") or None
        flight.end_city_name = end_city_name
        flight.end_airport = end_airport
        flight.end_terminal = request.form.get("end_terminal") or None
        flight.end_lat = parse_float(request.form.get("end_lat"))
        flight.end_long = parse_float(request.form.get("end_long"))
        flight.end_date = parse_date(request.form.get("end_date"))
        flight.end_time = parse_time(request.form.get("end_time"))
        flight.stops = parse_int(request.form.get("stops"))
        flight.distance = parse_float(request.form.get("distance"))
        if flight.distance is None:
            flight.distance = compute_distance(
                flight.start_lat, flight.start_long, flight.end_lat, flight.end_long
            )

        db.session.commit()
        flash("Flight updated.", "success")
        return redirect(resolve_redirect_target(next_url, "main.flight_list"))

    next_url = request.args.get("next")
    histories, history_counts, airnav_histories = load_history_context()
    group_members = approved_group_members(flight.grouping_id)
    return render_template(
        "flight_form.html",
        flight=flight,
        prefill=None,
        next_url=next_url,
        flight_histories=histories,
        history_counts=history_counts,
        airnav_histories=airnav_histories,
        group_members=group_members,
        group_primary_id=group_members[0].id if group_members else flight.id,
    )


def _quick_payload():
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload
    return request.form.to_dict()


def _quick_str(payload, key):
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _apply_aircraft_lookup(flight):
    if not flight.aircraft_registration:
        return
    record = Aircraft.query.filter(
        func.upper(Aircraft.registration) == flight.aircraft_registration.upper()
    ).first()
    if not record:
        return
    if not flight.aircraft and record.type:
        flight.aircraft = record.type
    if not flight.aircraft_type_normalized and record.icao_type:
        flight.aircraft_type_normalized = record.icao_type


def _flight_quick_summary(flight):
    return {
        "id": flight.id,
        "aircraft_registration": flight.aircraft_registration,
        "aircraft": flight.aircraft,
        "start_airport": flight.start_airport,
        "start_city_name": flight.start_city_name,
        "start_country": flight.start_country,
        "end_airport": flight.end_airport,
        "end_city_name": flight.end_city_name,
        "end_country": flight.end_country,
        "start_date": flight.start_date.isoformat() if flight.start_date else None,
        "end_date": flight.end_date.isoformat() if flight.end_date else None,
        "flight_number": flight.flight_number,
        "airline_code": flight.airline_code,
        "distance": flight.distance,
        "origin_name": flight.origin_name,
        "destination_name": flight.destination_name,
    }


@main_bp.route("/flights/quick-add", methods=["POST"])
def flight_quick_add():
    payload = _quick_payload()
    start_date = parse_date(_quick_str(payload, "start_date"))
    if not start_date:
        return jsonify({"ok": False, "error": "Start date is required."}), 400

    end_date = parse_date(_quick_str(payload, "end_date")) or start_date
    start_airport = _quick_str(payload, "start_airport")
    end_airport = _quick_str(payload, "end_airport")
    if not start_airport or not end_airport:
        return (
            jsonify({"ok": False, "error": "Start and end airport codes are required."}),
            400,
        )

    flight = Flight(
        status=APPROVED_STATUS,
        aircraft_registration=(_quick_str(payload, "aircraft_registration") or "").upper() or None,
        aircraft=_quick_str(payload, "aircraft"),
        start_airport=start_airport.upper(),
        start_city_name=_quick_str(payload, "start_city_name"),
        start_country=_quick_str(payload, "start_country"),
        start_lat=parse_float(payload.get("start_lat")),
        start_long=parse_float(payload.get("start_long")),
        start_date=start_date,
        end_airport=end_airport.upper(),
        end_city_name=_quick_str(payload, "end_city_name"),
        end_country=_quick_str(payload, "end_country"),
        end_lat=parse_float(payload.get("end_lat")),
        end_long=parse_float(payload.get("end_long")),
        end_date=end_date,
        flight_number=_quick_str(payload, "flight_number"),
        airline_code=(_quick_str(payload, "airline_code") or "").upper() or None,
    )
    flight.distance = compute_distance(
        flight.start_lat, flight.start_long, flight.end_lat, flight.end_long
    )
    _apply_aircraft_lookup(flight)
    db.session.add(flight)
    db.session.flush()
    stamp_revision(flight)
    db.session.commit()
    return jsonify({"ok": True, "flight": _flight_quick_summary(flight)})


@main_bp.route("/flights/<int:flight_id>/quick-edit", methods=["GET", "POST"])
def flight_quick_edit(flight_id):
    flight = Flight.query.get_or_404(flight_id)
    if request.method == "GET":
        return jsonify({"ok": True, "flight": _flight_quick_summary(flight)})

    payload = _quick_payload()
    start_date = parse_date(_quick_str(payload, "start_date"))
    if not start_date:
        return jsonify({"ok": False, "error": "Start date is required."}), 400

    end_date = parse_date(_quick_str(payload, "end_date")) or start_date
    start_airport = _quick_str(payload, "start_airport")
    end_airport = _quick_str(payload, "end_airport")
    if not start_airport or not end_airport:
        return (
            jsonify({"ok": False, "error": "Start and end airport codes are required."}),
            400,
        )

    flight.aircraft_registration = (
        (_quick_str(payload, "aircraft_registration") or "").upper() or None
    )
    if "aircraft" in payload:
        flight.aircraft = _quick_str(payload, "aircraft")
    new_start_airport = start_airport.upper()
    new_end_airport = end_airport.upper()
    start_airport_changed = new_start_airport != (flight.start_airport or "").upper()
    end_airport_changed = new_end_airport != (flight.end_airport or "").upper()

    flight.start_airport = new_start_airport
    flight.start_city_name = _quick_str(payload, "start_city_name")
    flight.start_country = _quick_str(payload, "start_country")
    new_start_lat = parse_float(payload.get("start_lat"))
    new_start_long = parse_float(payload.get("start_long"))
    if new_start_lat is not None:
        flight.start_lat = new_start_lat
    elif start_airport_changed:
        flight.start_lat = None
    if new_start_long is not None:
        flight.start_long = new_start_long
    elif start_airport_changed:
        flight.start_long = None
    flight.start_date = start_date

    flight.end_airport = new_end_airport
    flight.end_city_name = _quick_str(payload, "end_city_name")
    flight.end_country = _quick_str(payload, "end_country")
    new_end_lat = parse_float(payload.get("end_lat"))
    new_end_long = parse_float(payload.get("end_long"))
    if new_end_lat is not None:
        flight.end_lat = new_end_lat
    elif end_airport_changed:
        flight.end_lat = None
    if new_end_long is not None:
        flight.end_long = new_end_long
    elif end_airport_changed:
        flight.end_long = None
    flight.end_date = end_date
    if "flight_number" in payload:
        flight.flight_number = _quick_str(payload, "flight_number")
    if "airline_code" in payload:
        flight.airline_code = (_quick_str(payload, "airline_code") or "").upper() or None

    recomputed = compute_distance(
        flight.start_lat, flight.start_long, flight.end_lat, flight.end_long
    )
    if recomputed is not None:
        flight.distance = recomputed
    elif start_airport_changed or end_airport_changed:
        flight.distance = None
    _apply_aircraft_lookup(flight)
    stamp_revision(flight)
    db.session.commit()
    return jsonify({"ok": True, "flight": _flight_quick_summary(flight)})


@main_bp.route("/flights/<int:flight_id>/gemini-codeshare", methods=["POST"])
def gemini_codeshare_lookup(flight_id):
    flight = Flight.query.get_or_404(flight_id)
    if not flight.airline_code or not flight.flight_number:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Airline code and flight number are required.",
                }
            ),
            400,
        )

    try:
        details, debug = lookup_codeshare_details(
            flight.airline_code,
            flight.flight_number,
            dep_date=flight.start_date,
            dep_iata=flight.start_airport,
            arr_iata=flight.end_airport,
        )
    except GeminiCodeshareError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502

    if not details:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "No details returned.",
                    "request": debug.get("request") if debug else None,
                    "response": debug.get("response") if debug else None,
                }
            ),
            404,
        )

    return jsonify(
        {
            "ok": True,
            "details": details,
            "request": debug.get("request") if debug else None,
            "response": debug.get("response") if debug else None,
            "current": {
                "flight_number": flight.flight_number,
                "airline_code": flight.airline_code,
                "aircraft": flight.aircraft,
                "operating_airline_code": flight.operating_airline_code,
                "operating_flight_number": flight.operating_flight_number,
            },
        }
    )


@main_bp.route("/flights/<int:flight_id>/gemini-codeshare/record", methods=["POST"])
def gemini_codeshare_record(flight_id):
    flight = Flight.query.get_or_404(flight_id)
    if not flight.start_date:
        return (
            jsonify({"ok": False, "error": "Departure date is required for history."}),
            400,
        )
    payload = request.get_json(silent=True) or {}
    details = payload.get("details") or {}
    request_info = payload.get("request")
    response_info = payload.get("response")
    applied_fields = payload.get("applied_fields") or []
    reasoning = None
    if isinstance(details, dict):
        reasoning = details.get("reasoning")
    if not reasoning and isinstance(response_info, dict):
        reasoning = response_info.get("text")

    history = FlightHistoryAirNavRadar(
        flight_id=flight.id,
        dep_date=flight.start_date,
        source="gemini",
        aircraft_type=details.get("aircraft_type"),
        aircraft_registration=details.get("aircraft_registration"),
        airline_iata=details.get("operating_airline_code") or flight.airline_code,
        flight_number_iata=details.get("operating_flight_number"),
        raw_payload={
            "details": details,
            "request": request_info,
            "response": response_info,
            "reasoning": reasoning,
            "applied_fields": applied_fields,
        },
    )
    db.session.add(history)
    db.session.commit()
    return jsonify(
        {
            "ok": True,
            "history_id": history.id,
            "aircraft_type": history.aircraft_type,
            "aircraft_registration": history.aircraft_registration,
        }
    )


def _refresh_flight_history(flight):
    """Look the flight up with the configured provider, store a history row, and commit.

    Raises FlightLookupError with a suitable HTTP status when nothing was stored.
    """
    result = lookup_and_record(flight)
    if any(result.applied.values()):
        stamp_revision(flight)
    db.session.commit()
    return result.history


def _history_response(history):
    return jsonify(
        {
            "ok": True,
            "history_id": history.id,
            "source": history.source,
            "aircraft_type": history.aircraft_type,
            "aircraft_registration": history.aircraft_registration,
        }
    )


@main_bp.route("/flights/<int:flight_id>/flightaware/history", methods=["POST"])
def flightaware_history(flight_id):
    flight = Flight.query.get_or_404(flight_id)
    try:
        history = _refresh_flight_history(flight)
    except FlightLookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), exc.status
    return _history_response(history)


@main_bp.route("/flights/<int:flight_id>/history/refresh", methods=["POST"])
def flight_history_refresh(flight_id):
    flight = Flight.query.get_or_404(flight_id)
    if flight.exclude_from_stats:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Flight is excluded from stats; history refresh skipped.",
                }
            ),
            400,
        )
    try:
        history = _refresh_flight_history(flight)
    except FlightLookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), exc.status
    return _history_response(history)


@main_bp.route("/api/refresh-today-history", methods=["POST"])
def api_refresh_today_history():
    today = date.today()
    flights = (
        approved_flights_query()
        .filter(Flight.start_date == today)
        .filter(Flight.exclude_from_stats.isnot(True))
        .order_by(Flight.id)
        .all()
    )

    results = []
    for flight in flights:
        try:
            history = _refresh_flight_history(flight)
        except FlightLookupError as exc:
            if exc.status == 404:
                results.append({"flight_id": flight.id, "status": "not_found"})
            elif exc.status == 400:
                results.append(
                    {"flight_id": flight.id, "status": "skipped", "reason": str(exc)}
                )
            else:
                results.append(
                    {"flight_id": flight.id, "status": "error", "reason": str(exc)}
                )
            continue
        results.append(
            {"flight_id": flight.id, "status": "saved", "history_id": history.id}
        )

    saved_count = sum(1 for r in results if r["status"] == "saved")
    return jsonify({
        "ok": True,
        "total": len(flights),
        "saved": saved_count,
        "results": results,
    })


@main_bp.route("/flights/history/<int:history_id>")
def flight_history_record_view(history_id):
    history = FlightHistoryAirNavRadar.query.get_or_404(history_id)
    payload = json.dumps(history.raw_payload, indent=2, sort_keys=True)
    return render_template(
        "flight_history_record.html",
        history=history,
        payload=payload,
    )


@main_bp.route("/flights/history/<int:history_id>/delete", methods=["POST"])
def flight_history_record_delete(history_id):
    history = FlightHistoryAirNavRadar.query.get_or_404(history_id)
    flight_id = history.flight_id
    db.session.delete(history)
    db.session.commit()
    if wants_json_response():
        return jsonify({"ok": True, "history_id": history_id, "flight_id": flight_id})
    flash("Flight history entry deleted.", "success")
    next_url = request.form.get("next")
    if isinstance(next_url, str) and next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect(url_for("main.flight_edit", flight_id=flight_id))


@main_bp.route("/flights/<int:flight_id>/delete", methods=["POST"])
def flight_delete(flight_id):
    flight = Flight.query.get_or_404(flight_id)
    grouping_id = flight.grouping_id
    flight.deleted_at = datetime.utcnow()
    flight.updated_at = datetime.utcnow()
    stamp_revision(flight)
    db.session.flush()
    if grouping_id:
        remaining = (
            db.session.query(Flight.id)
            .filter(
                Flight.grouping_id == grouping_id,
                Flight.deleted_at.is_(None),
            )
            .count()
        )
        if remaining == 1:
            survivor = (
                Flight.query.filter(
                    Flight.grouping_id == grouping_id,
                    Flight.deleted_at.is_(None),
                ).first()
            )
            if survivor:
                survivor.grouping_id = None
    db.session.commit()
    if wants_json_response():
        return jsonify({"ok": True, "flight_id": flight_id})
    flash("Flight deleted.", "success")
    redirect_target = resolve_redirect_target(
        request.form.get("next"), "main.flight_list"
    )
    return redirect(redirect_target)


@main_bp.route("/flights/<int:flight_id>/follow-up", methods=["POST"])
def flight_follow_up(flight_id):
    flight = Flight.query.get_or_404(flight_id)
    flag_value = (request.form.get("flag") or "").strip().lower()
    should_flag = flag_value in ("1", "true", "yes", "on")
    flight.follow_up = should_flag
    db.session.commit()
    if wants_json_response():
        return jsonify(
            {"ok": True, "flight_id": flight_id, "follow_up": should_flag}
        )
    flash(
        "Flagged for follow up." if should_flag else "Follow up cleared.",
        "success",
    )
    redirect_target = resolve_redirect_target(
        request.form.get("next"), "main.flight_list"
    )
    return redirect(redirect_target)


@main_bp.route("/flights/<int:flight_id>/exclude", methods=["POST"])
def flight_exclude(flight_id):
    flight = Flight.query.get_or_404(flight_id)
    flag_value = (request.form.get("exclude") or "").strip().lower()
    should_exclude = flag_value in ("1", "true", "yes", "on")
    flight.exclude_from_stats = should_exclude
    flight.updated_at = datetime.utcnow()
    stamp_revision(flight)
    db.session.commit()
    if wants_json_response():
        return jsonify(
            {
                "ok": True,
                "flight_id": flight_id,
                "exclude_from_stats": should_exclude,
            }
        )
    flash(
        "Excluded from stats." if should_exclude else "Included in stats.",
        "success",
    )
    redirect_target = resolve_redirect_target(
        request.form.get("next"), "main.flight_list"
    )
    return redirect(redirect_target)


@main_bp.route("/flights/<int:flight_id>/registration/clear", methods=["POST"])
def flight_clear_registration(flight_id):
    flight = Flight.query.get_or_404(flight_id)
    flight.aircraft_registration = None
    db.session.commit()
    if wants_json_response():
        return jsonify(
            {"ok": True, "flight_id": flight_id, "aircraft_registration": None}
        )
    flash("Aircraft registration cleared.", "success")
    redirect_target = resolve_redirect_target(
        request.form.get("next"), "main.flight_list"
    )
    return redirect(redirect_target)


@main_bp.route("/flights/<int:flight_id>/aircraft/overwrite-gemini", methods=["POST"])
def flight_overwrite_aircraft_from_gemini(flight_id):
    flight = Flight.query.get_or_404(flight_id)
    history = (
        FlightHistoryAirNavRadar.query.filter(
            FlightHistoryAirNavRadar.flight_id == flight_id,
            FlightHistoryAirNavRadar.source.in_(["gemini", "gemini_guess"]),
        )
        .order_by(
            FlightHistoryAirNavRadar.created_at.desc(),
            FlightHistoryAirNavRadar.id.desc(),
        )
        .first()
    )
    if not history or not history.aircraft_type:
        flash("No Gemini aircraft type available to apply.", "warning")
        redirect_target = resolve_redirect_target(
            request.form.get("next"), "main.flight_list"
        )
        return redirect(redirect_target)

    updated_flight_ids = []
    group_key = f"single-{flight.id}"
    if flight.grouping_id:
        group_key = str(flight.grouping_id)
        group_flights = Flight.query.filter(
            Flight.grouping_id == flight.grouping_id
        ).all()
        for group_flight in group_flights:
            group_flight.aircraft = history.aircraft_type
            updated_flight_ids.append(group_flight.id)
    else:
        flight.aircraft = history.aircraft_type
        updated_flight_ids.append(flight.id)
    db.session.commit()
    if wants_json_response():
        return jsonify(
            {
                "ok": True,
                "flight_id": flight_id,
                "aircraft": flight.aircraft,
                "aircraft_type": history.aircraft_type,
                "group_key": group_key,
                "updated_flight_ids": updated_flight_ids,
                "source": history.source,
            }
        )
    flash("Aircraft type updated from Gemini.", "success")
    redirect_target = resolve_redirect_target(
        request.form.get("next"), "main.flight_list"
    )
    return redirect(redirect_target)


@main_bp.route("/flights/<int:flight_id>/aircraft/apply-group", methods=["POST"])
def flight_apply_aircraft_to_group(flight_id):
    flight = Flight.query.get_or_404(flight_id)
    if not flight.aircraft:
        flash("No aircraft type set for this flight.", "warning")
        redirect_target = resolve_redirect_target(
            request.form.get("next"), "main.flight_list"
        )
        return redirect(redirect_target)

    updated_flight_ids = []
    group_key = f"single-{flight.id}"
    if flight.grouping_id:
        group_key = str(flight.grouping_id)
        group_flights = Flight.query.filter(
            Flight.grouping_id == flight.grouping_id
        ).all()
        for group_flight in group_flights:
            group_flight.aircraft = flight.aircraft
            updated_flight_ids.append(group_flight.id)
    else:
        updated_flight_ids.append(flight.id)

    db.session.commit()
    if wants_json_response():
        return jsonify(
            {
                "ok": True,
                "flight_id": flight_id,
                "aircraft": flight.aircraft,
                "aircraft_type": flight.aircraft,
                "group_key": group_key,
                "updated_flight_ids": updated_flight_ids,
            }
        )
    flash("Aircraft type applied to group.", "success")
    redirect_target = resolve_redirect_target(
        request.form.get("next"), "main.flight_list"
    )
    return redirect(redirect_target)


@main_bp.route("/import", methods=["GET", "POST"])
def import_csv():
    if request.method == "POST":
        file = request.files.get("csv_file")
        if not file:
            flash("Please choose a CSV file.", "error")
            return render_template("import.html")

        rows, errors = parse_csv(file)
        imported = import_rows(rows)
        flash(f"Imported {imported} flights.", "success")
        if errors:
            flash(f"{len(errors)} rows skipped. See details below.", "warning")
        return render_template("import.html", errors=errors, imported=imported)

    return render_template("import.html")


@main_bp.route("/utilities/scripts")
def utilities_scripts():
    catalog = get_script_catalog()
    scripts = [
        {key: value for key, value in script.items() if key != "path"}
        for script in catalog["items"]
    ]
    return render_template("utility_scripts.html", scripts=scripts)


@main_bp.route("/utilities/scripts/run", methods=["POST"])
def utilities_scripts_run():
    payload = request.get_json(silent=True) or {}
    try:
        run = start_script_run(
            payload.get("script_key"),
            payload.get("options"),
            payload.get("arguments"),
        )
    except ScriptRunnerError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(
        {
            "ok": True,
            "run_id": run.run_id,
            "status": run.status,
            "command": run.command,
            "created_at": run.created_at.isoformat() + "Z",
        }
    )


@main_bp.route("/utilities/scripts/status/<run_id>")
def utilities_scripts_status(run_id):
    cursor = parse_int(request.args.get("cursor")) or 0
    status = get_script_run_status(run_id, cursor=cursor)
    if not status:
        return jsonify({"ok": False, "error": "Run not found."}), 404
    status["ok"] = True
    return jsonify(status)


@main_bp.route("/utilities/scripts/stop", methods=["POST"])
def utilities_scripts_stop():
    payload = request.get_json(silent=True) or {}
    run_id = payload.get("run_id")
    if not run_id:
        return jsonify({"ok": False, "error": "Run id required."}), 400
    try:
        run = stop_script_run(run_id)
    except ScriptRunnerError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify(
        {
            "ok": True,
            "run_id": run.run_id,
            "status": run.status,
        }
    )


@main_bp.route("/utilities/scripts/history")
def utilities_scripts_history():
    return jsonify({"ok": True, "history": get_script_history()})
