"""REST API v1 blueprint for iOS app and external clients."""

from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from sqlalchemy import func, or_

from .api_auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    require_api_auth,
)
from .extensions import db
from .models import (
    AchievementBadge,
    Aircraft,
    ApiUser,
    Flight,
    SyncState,
    Trip,
    TripLeg,
)
from .sync import (
    aircraft_to_dict,
    badge_to_dict,
    flight_to_dict,
    stamp_revision,
    trip_leg_to_dict,
    trip_to_dict,
)
from .services.flight_groups import (
    group_info_by_flight,
    is_group_primary,
    matches_flight_or_group_member,
    reporting_flights_query,
)

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_date(val):
    """Parse an ISO date string to a date object."""
    if val is None or val == "":
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    try:
        return date.fromisoformat(val)
    except (ValueError, TypeError):
        return None


def parse_time(val):
    """Parse an ISO time string to a time object."""
    if val is None or val == "":
        return None
    if isinstance(val, time):
        return val
    try:
        return time.fromisoformat(val)
    except (ValueError, TypeError):
        return None


def parse_datetime(val):
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(val)
    except (ValueError, TypeError):
        return None


def parse_decimal(val):
    if val is None or val == "":
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return None


FLIGHT_WRITABLE_FIELDS = {
    "status", "trip_name", "trip_id", "trip_type", "trip_leg_id",
    "activity_id", "activity_cost", "url", "booking_site",
    "supplier_confirmation", "booking_date", "booking_site_phone",
    "traveller", "ticket_number", "airline_code", "operating_airline_code",
    "aircraft", "aircraft_type_normalized", "aircraft_registration",
    "service_class", "flight_number", "operating_flight_number",
    "start_country", "start_city_name", "start_airport", "start_terminal",
    "start_lat", "start_long", "start_date", "start_time",
    "end_country", "end_city_name", "end_airport", "end_terminal",
    "end_lat", "end_long", "end_date", "end_time",
    "stops", "distance", "route_direction", "source_file", "grouping_id",
    "audit_missing_leg_ignored", "follow_up", "exclude_from_stats",
}

DATE_FIELDS = {"start_date", "end_date", "booking_date"}
TIME_FIELDS = {"start_time", "end_time"}
DECIMAL_FIELDS = {"activity_cost"}
FLOAT_FIELDS = {"start_lat", "start_long", "end_lat", "end_long", "distance"}
INT_FIELDS = {"stops", "trip_leg_id"}
BOOL_FIELDS = {"audit_missing_leg_ignored", "follow_up", "exclude_from_stats"}


def apply_flight_fields(flight, data):
    """Apply a dict of field values to a Flight instance with type coercion."""
    for key, val in data.items():
        if key not in FLIGHT_WRITABLE_FIELDS:
            continue
        if key in DATE_FIELDS:
            setattr(flight, key, parse_date(val))
        elif key in TIME_FIELDS:
            setattr(flight, key, parse_time(val))
        elif key in DECIMAL_FIELDS:
            setattr(flight, key, parse_decimal(val))
        elif key in FLOAT_FIELDS:
            setattr(flight, key, float(val) if val is not None and val != "" else None)
        elif key in INT_FIELDS:
            setattr(flight, key, int(val) if val is not None and val != "" else None)
        elif key in BOOL_FIELDS:
            setattr(flight, key, bool(val) if val is not None else False)
        else:
            setattr(flight, key, val)


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@api_v1_bp.route("/auth/token", methods=["POST"])
def auth_token():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    client_id = data.get("client_id")

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    user = ApiUser.query.filter_by(username=username).first()
    if user is None or not user.check_password(password):
        return jsonify({"error": "Invalid credentials"}), 401

    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({
        "access_token": create_access_token(user, client_id),
        "refresh_token": create_refresh_token(user, client_id),
        "user": {"id": user.id, "username": user.username},
    })


@api_v1_bp.route("/auth/refresh", methods=["POST"])
def auth_refresh():
    data = request.get_json(silent=True) or {}
    token = data.get("refresh_token") or ""

    payload = decode_token(token)
    if payload is None or payload.get("type") != "refresh":
        return jsonify({"error": "Invalid or expired refresh token"}), 401

    user = ApiUser.query.filter_by(username=payload["sub"]).first()
    if user is None:
        return jsonify({"error": "User not found"}), 401

    client_id = payload.get("client_id")
    return jsonify({
        "access_token": create_access_token(user, client_id),
        "refresh_token": create_refresh_token(user, client_id),
    })


# ---------------------------------------------------------------------------
# Flights CRUD
# ---------------------------------------------------------------------------

def active_flights_query():
    return Flight.query.filter(Flight.deleted_at.is_(None))


@api_v1_bp.route("/flights", methods=["GET"])
@require_api_auth
def list_flights():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 100, type=int), 500)
    status = request.args.get("status") or "approved"
    traveller = request.args.get("traveller")
    q = request.args.get("q", "").strip()
    # Flights sharing a grouping_id are one flight recorded more than once;
    # only the group's primary (newest) record is listed unless asked for.
    include_group_members = request.args.get(
        "include_group_members", ""
    ).strip().lower() in ("1", "true", "yes")

    identity_filters = (Flight.deleted_at.is_(None), Flight.status == status)
    query = Flight.query.filter(*identity_filters)
    if not include_group_members:
        query = query.filter(is_group_primary(identity_filters))
    if traveller:
        query = query.filter(Flight.traveller == traveller)
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
            )

        query = query.filter(matches_flight_or_group_member(text_match))

    query = query.order_by(Flight.start_date.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    groups = group_info_by_flight(pagination.items)

    return jsonify({
        "flights": [
            dict(flight_to_dict(f), group=groups[f.id]) for f in pagination.items
        ],
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages,
        "has_next": pagination.has_next,
    })


@api_v1_bp.route("/flights/<int:flight_id>", methods=["GET"])
@require_api_auth
def get_flight(flight_id):
    flight = active_flights_query().filter_by(id=flight_id).first()
    if flight is None:
        return jsonify({"error": "Flight not found"}), 404
    return jsonify(flight_to_dict(flight))


@api_v1_bp.route("/flights", methods=["POST"])
@require_api_auth
def create_flight():
    data = request.get_json(silent=True) or {}
    if not data.get("start_date"):
        return jsonify({"error": "start_date is required"}), 400

    flight = Flight(start_date=parse_date(data["start_date"]))
    apply_flight_fields(flight, data)
    stamp_revision(flight)
    db.session.add(flight)
    db.session.commit()

    return jsonify(flight_to_dict(flight)), 201


@api_v1_bp.route("/flights/<int:flight_id>", methods=["PUT"])
@require_api_auth
def update_flight(flight_id):
    flight = active_flights_query().filter_by(id=flight_id).first()
    if flight is None:
        return jsonify({"error": "Flight not found"}), 404

    data = request.get_json(silent=True) or {}
    apply_flight_fields(flight, data)
    flight.updated_at = datetime.now(timezone.utc)
    stamp_revision(flight)
    db.session.commit()

    return jsonify(flight_to_dict(flight))


@api_v1_bp.route("/flights/<int:flight_id>", methods=["DELETE"])
@require_api_auth
def delete_flight(flight_id):
    flight = active_flights_query().filter_by(id=flight_id).first()
    if flight is None:
        return jsonify({"error": "Flight not found"}), 404

    flight.deleted_at = datetime.now(timezone.utc)
    flight.updated_at = datetime.now(timezone.utc)
    stamp_revision(flight)
    db.session.commit()

    return jsonify({"status": "deleted", "id": flight_id})


@api_v1_bp.route("/flights/<int:flight_id>/follow-up", methods=["PATCH"])
@require_api_auth
def toggle_follow_up(flight_id):
    flight = active_flights_query().filter_by(id=flight_id).first()
    if flight is None:
        return jsonify({"error": "Flight not found"}), 404

    flight.follow_up = not flight.follow_up
    flight.updated_at = datetime.now(timezone.utc)
    stamp_revision(flight)
    db.session.commit()

    return jsonify({"id": flight_id, "follow_up": flight.follow_up})


@api_v1_bp.route("/flights/<int:flight_id>/exclude", methods=["PATCH"])
@require_api_auth
def toggle_exclude(flight_id):
    flight = active_flights_query().filter_by(id=flight_id).first()
    if flight is None:
        return jsonify({"error": "Flight not found"}), 404

    flight.exclude_from_stats = not flight.exclude_from_stats
    flight.updated_at = datetime.now(timezone.utc)
    stamp_revision(flight)
    db.session.commit()

    return jsonify({"id": flight_id, "exclude_from_stats": flight.exclude_from_stats})


# ---------------------------------------------------------------------------
# Trips CRUD
# ---------------------------------------------------------------------------

def active_trips_query():
    return Trip.query.filter(Trip.deleted_at.is_(None))


TRIP_WRITABLE_FIELDS = {
    "name", "trip_code", "trip_type", "notes",
    "start_date", "end_date",
    "start_date_precision", "start_date_year", "start_date_month", "start_date_day",
    "end_date_precision", "end_date_year", "end_date_month", "end_date_day",
}

TRIP_DATE_FIELDS = {"start_date", "end_date"}
TRIP_INT_FIELDS = {
    "start_date_year", "start_date_month", "start_date_day",
    "end_date_year", "end_date_month", "end_date_day",
}


def apply_trip_fields(trip, data):
    for key, val in data.items():
        if key not in TRIP_WRITABLE_FIELDS:
            continue
        if key in TRIP_DATE_FIELDS:
            setattr(trip, key, parse_date(val))
        elif key in TRIP_INT_FIELDS:
            setattr(trip, key, int(val) if val is not None and val != "" else None)
        else:
            setattr(trip, key, val)


@api_v1_bp.route("/trips", methods=["GET"])
@require_api_auth
def list_trips():
    trips = active_trips_query().order_by(Trip.start_date.desc()).all()
    result = []
    for t in trips:
        td = trip_to_dict(t)
        td["legs"] = [trip_leg_to_dict(leg) for leg in t.legs if leg.deleted_at is None]
        result.append(td)
    return jsonify({"trips": result})


@api_v1_bp.route("/trips/<int:trip_id>", methods=["GET"])
@require_api_auth
def get_trip(trip_id):
    trip = active_trips_query().filter_by(id=trip_id).first()
    if trip is None:
        return jsonify({"error": "Trip not found"}), 404
    td = trip_to_dict(trip)
    td["legs"] = [trip_leg_to_dict(leg) for leg in trip.legs if leg.deleted_at is None]
    return jsonify(td)


@api_v1_bp.route("/trips", methods=["POST"])
@require_api_auth
def create_trip():
    data = request.get_json(silent=True) or {}
    trip = Trip()
    apply_trip_fields(trip, data)
    stamp_revision(trip)
    db.session.add(trip)
    db.session.commit()
    td = trip_to_dict(trip)
    td["legs"] = []
    return jsonify(td), 201


@api_v1_bp.route("/trips/<int:trip_id>", methods=["PUT"])
@require_api_auth
def update_trip(trip_id):
    trip = active_trips_query().filter_by(id=trip_id).first()
    if trip is None:
        return jsonify({"error": "Trip not found"}), 404
    data = request.get_json(silent=True) or {}
    apply_trip_fields(trip, data)
    trip.updated_at = datetime.now(timezone.utc)
    stamp_revision(trip)
    db.session.commit()
    td = trip_to_dict(trip)
    td["legs"] = [trip_leg_to_dict(leg) for leg in trip.legs if leg.deleted_at is None]
    return jsonify(td)


@api_v1_bp.route("/trips/<int:trip_id>", methods=["DELETE"])
@require_api_auth
def delete_trip(trip_id):
    trip = active_trips_query().filter_by(id=trip_id).first()
    if trip is None:
        return jsonify({"error": "Trip not found"}), 404
    trip.deleted_at = datetime.now(timezone.utc)
    trip.updated_at = datetime.now(timezone.utc)
    stamp_revision(trip)
    for leg in trip.legs:
        if leg.deleted_at is None:
            leg.deleted_at = datetime.now(timezone.utc)
            leg.updated_at = datetime.now(timezone.utc)
            stamp_revision(leg)
    db.session.commit()
    return jsonify({"status": "deleted", "id": trip_id})


# ---------------------------------------------------------------------------
# Trip legs
# ---------------------------------------------------------------------------

LEG_WRITABLE_FIELDS = {
    "sequence", "mode", "carrier_name", "carrier_code", "service_class",
    "flight_number", "aircraft_type", "aircraft_registration",
    "start_country", "start_city_name", "start_airport",
    "end_country", "end_city_name", "end_airport",
    "start_date", "end_date",
    "start_date_precision", "start_date_year", "start_date_month", "start_date_day",
    "end_date_precision", "end_date_year", "end_date_month", "end_date_day",
    "notes",
}


def apply_leg_fields(leg, data):
    for key, val in data.items():
        if key not in LEG_WRITABLE_FIELDS:
            continue
        if key in {"start_date", "end_date"}:
            setattr(leg, key, parse_date(val))
        elif key in {"sequence", "start_date_year", "start_date_month", "start_date_day",
                      "end_date_year", "end_date_month", "end_date_day"}:
            setattr(leg, key, int(val) if val is not None and val != "" else None)
        else:
            setattr(leg, key, val)


@api_v1_bp.route("/trips/<int:trip_id>/legs", methods=["POST"])
@require_api_auth
def create_leg(trip_id):
    trip = active_trips_query().filter_by(id=trip_id).first()
    if trip is None:
        return jsonify({"error": "Trip not found"}), 404
    data = request.get_json(silent=True) or {}
    leg = TripLeg(trip_id=trip_id)
    apply_leg_fields(leg, data)
    stamp_revision(leg)
    db.session.add(leg)
    # also bump the parent trip revision
    trip.updated_at = datetime.now(timezone.utc)
    stamp_revision(trip)
    db.session.commit()
    return jsonify(trip_leg_to_dict(leg)), 201


@api_v1_bp.route("/trips/<int:trip_id>/legs/<int:leg_id>", methods=["PUT"])
@require_api_auth
def update_leg(trip_id, leg_id):
    leg = TripLeg.query.filter_by(id=leg_id, trip_id=trip_id).first()
    if leg is None or leg.deleted_at is not None:
        return jsonify({"error": "Leg not found"}), 404
    data = request.get_json(silent=True) or {}
    apply_leg_fields(leg, data)
    leg.updated_at = datetime.now(timezone.utc)
    stamp_revision(leg)
    db.session.commit()
    return jsonify(trip_leg_to_dict(leg))


@api_v1_bp.route("/trips/<int:trip_id>/legs/<int:leg_id>", methods=["DELETE"])
@require_api_auth
def delete_leg(trip_id, leg_id):
    leg = TripLeg.query.filter_by(id=leg_id, trip_id=trip_id).first()
    if leg is None or leg.deleted_at is not None:
        return jsonify({"error": "Leg not found"}), 404
    leg.deleted_at = datetime.now(timezone.utc)
    leg.updated_at = datetime.now(timezone.utc)
    stamp_revision(leg)
    db.session.commit()
    return jsonify({"status": "deleted", "id": leg_id})


# ---------------------------------------------------------------------------
# Aircraft (read-only from API)
# ---------------------------------------------------------------------------

@api_v1_bp.route("/aircraft", methods=["GET"])
@require_api_auth
def list_aircraft():
    aircraft = Aircraft.query.order_by(Aircraft.registration).all()
    return jsonify({"aircraft": [aircraft_to_dict(a) for a in aircraft]})


@api_v1_bp.route("/aircraft/<registration>", methods=["GET"])
@require_api_auth
def get_aircraft(registration):
    reg = (registration or "").strip().upper()
    ac = Aircraft.query.filter(func.upper(Aircraft.registration) == reg).first()
    if ac is None:
        return jsonify({"error": "Aircraft not found"}), 404
    return jsonify(aircraft_to_dict(ac))


# ---------------------------------------------------------------------------
# Achievements
# ---------------------------------------------------------------------------

@api_v1_bp.route("/achievements", methods=["GET"])
@require_api_auth
def list_achievements():
    badges = AchievementBadge.query.filter_by(is_active=True).order_by(
        AchievementBadge.display_order
    ).all()

    # Compute current stats for badge evaluation: one flight per duplicate group.
    base = reporting_flights_query()
    flight_count = base.count()
    total_miles = float(
        base.with_entities(func.coalesce(func.sum(Flight.distance), 0)).scalar() or 0
    )
    country_count = (
        base.filter(Flight.start_country.isnot(None))
        .with_entities(func.count(func.distinct(Flight.start_country)))
        .scalar()
        or 0
    )

    result = []
    for badge in badges:
        bd = badge_to_dict(badge)
        if badge.badge_type == "flight_count":
            bd["earned"] = flight_count >= badge.threshold_value
            bd["progress"] = min(flight_count, badge.threshold_value)
        elif badge.badge_type == "total_miles":
            bd["earned"] = total_miles >= badge.threshold_value
            bd["progress"] = min(total_miles, badge.threshold_value)
        elif badge.badge_type == "countries_visited":
            bd["earned"] = country_count >= badge.threshold_value
            bd["progress"] = min(country_count, badge.threshold_value)
        else:
            bd["earned"] = False
            bd["progress"] = 0
        result.append(bd)

    return jsonify({"badges": result})


# ---------------------------------------------------------------------------
# Stats / Summary
# ---------------------------------------------------------------------------

@api_v1_bp.route("/stats/summary", methods=["GET"])
@require_api_auth
def stats_summary():
    # Approved, active, not excluded, and one flight per duplicate group.
    base = reporting_flights_query()

    def distinct_count(column):
        return (
            base.filter(column.isnot(None))
            .with_entities(func.count(func.distinct(column)))
            .scalar()
            or 0
        )

    total_flights = base.count()
    total_miles = (
        base.with_entities(func.coalesce(func.sum(Flight.distance), 0)).scalar() or 0
    )

    return jsonify({
        "total_flights": total_flights,
        "total_miles": float(total_miles),
        "countries": distinct_count(Flight.start_country),
        "cities": distinct_count(Flight.start_city_name),
        "airlines": distinct_count(Flight.airline_code),
        "aircraft_types": distinct_count(Flight.aircraft),
    })


# ---------------------------------------------------------------------------
# Sync endpoints
# ---------------------------------------------------------------------------

@api_v1_bp.route("/sync/status", methods=["GET"])
@require_api_auth
def sync_status():
    return jsonify({
        "current_revision": SyncState.current(),
    })


@api_v1_bp.route("/sync/changes", methods=["GET"])
@require_api_auth
def sync_pull():
    """Pull all changes since a given revision.

    Query params:
        since: revision number (default 0 = full sync)
        limit: max records per entity type (default 500)
        cursor: offset for pagination
    """
    since = request.args.get("since", 0, type=int)
    limit = min(request.args.get("limit", 500, type=int), 500)
    cursor = request.args.get("cursor", 0, type=int)

    def _query(model):
        q = model.query
        if since > 0:
            q = q.filter(model.sync_revision > since)
        return (
            q.order_by(model.sync_revision)
            .offset(cursor)
            .limit(limit + 1)
            .all()
        )

    flights = _query(Flight)
    trips = _query(Trip)
    trip_legs = _query(TripLeg)
    aircraft = _query(Aircraft)
    badges = _query(AchievementBadge)

    # Check if any entity type has more records
    has_more = (
        len(flights) > limit
        or len(trips) > limit
        or len(trip_legs) > limit
        or len(aircraft) > limit
        or len(badges) > limit
    )

    return jsonify({
        "current_revision": SyncState.current(),
        "flights": [flight_to_dict(f) for f in flights[:limit]],
        "trips": [trip_to_dict(t) for t in trips[:limit]],
        "trip_legs": [trip_leg_to_dict(l) for l in trip_legs[:limit]],
        "aircraft": [aircraft_to_dict(a) for a in aircraft[:limit]],
        "badges": [badge_to_dict(b) for b in badges[:limit]],
        "has_more": has_more,
        "next_cursor": cursor + limit if has_more else None,
    })


@api_v1_bp.route("/sync/push", methods=["POST"])
@require_api_auth
def sync_push():
    """Process a batch of client changes.

    Request body:
    {
        "client_id": "device-uuid",
        "changes": [
            {
                "entity_type": "flight",
                "entity_id": 42,          // null for creates
                "temp_id": "uuid",         // for creates
                "change_type": "create" | "update" | "delete",
                "base_revision": 15,       // for updates
                "fields": { ... }
            }
        ]
    }
    """
    data = request.get_json(silent=True) or {}
    changes = data.get("changes", [])
    results = []

    for change in changes:
        entity_type = change.get("entity_type")
        entity_id = change.get("entity_id")
        temp_id = change.get("temp_id")
        change_type = change.get("change_type")
        base_revision = change.get("base_revision", 0)
        fields = change.get("fields", {})

        try:
            if entity_type == "flight":
                result = _process_flight_change(
                    entity_id, temp_id, change_type, base_revision, fields
                )
            elif entity_type == "trip":
                result = _process_trip_change(
                    entity_id, temp_id, change_type, base_revision, fields
                )
            elif entity_type == "trip_leg":
                result = _process_trip_leg_change(
                    entity_id, temp_id, change_type, base_revision, fields
                )
            else:
                result = {"status": "error", "message": f"Unknown entity type: {entity_type}"}
            results.append(result)
        except Exception as exc:
            db.session.rollback()
            results.append({
                "status": "error",
                "entity_type": entity_type,
                "entity_id": entity_id,
                "temp_id": temp_id,
                "message": str(exc),
            })

    db.session.commit()

    return jsonify({
        "results": results,
        "current_revision": SyncState.current(),
    })


def _process_flight_change(entity_id, temp_id, change_type, base_revision, fields):
    if change_type == "create":
        if not fields.get("start_date"):
            return {"status": "error", "temp_id": temp_id, "message": "start_date required"}
        flight = Flight(start_date=parse_date(fields["start_date"]))
        apply_flight_fields(flight, fields)
        rev = stamp_revision(flight)
        db.session.add(flight)
        db.session.flush()
        return {
            "status": "created",
            "temp_id": temp_id,
            "entity_id": flight.id,
            "revision": rev,
        }

    elif change_type == "update":
        flight = Flight.query.get(entity_id)
        if flight is None:
            return {"status": "error", "entity_id": entity_id, "message": "Not found"}
        if flight.deleted_at is not None:
            return {"status": "error", "entity_id": entity_id, "message": "Already deleted"}

        # Conflict detection
        if flight.sync_revision > base_revision:
            # Check for field-level conflict
            server_changed = _get_changed_fields_since(flight, base_revision)
            client_fields = set(fields.keys()) & FLIGHT_WRITABLE_FIELDS
            overlap = server_changed & client_fields

            if overlap:
                # Conflicting fields — last write wins (client wins since they're pushing)
                apply_flight_fields(flight, fields)
                flight.updated_at = datetime.now(timezone.utc)
                rev = stamp_revision(flight)
                return {
                    "status": "conflict_resolved",
                    "entity_id": entity_id,
                    "revision": rev,
                    "conflicting_fields": list(overlap),
                    "resolution": "client_wins",
                    "server_fields": {k: str(getattr(flight, k)) for k in overlap},
                }

        apply_flight_fields(flight, fields)
        flight.updated_at = datetime.now(timezone.utc)
        rev = stamp_revision(flight)
        return {"status": "ok", "entity_id": entity_id, "revision": rev}

    elif change_type == "delete":
        flight = Flight.query.get(entity_id)
        if flight is None:
            return {"status": "error", "entity_id": entity_id, "message": "Not found"}
        flight.deleted_at = datetime.now(timezone.utc)
        flight.updated_at = datetime.now(timezone.utc)
        rev = stamp_revision(flight)
        return {"status": "deleted", "entity_id": entity_id, "revision": rev}

    return {"status": "error", "message": f"Unknown change_type: {change_type}"}


def _process_trip_change(entity_id, temp_id, change_type, base_revision, fields):
    if change_type == "create":
        trip = Trip()
        apply_trip_fields(trip, fields)
        rev = stamp_revision(trip)
        db.session.add(trip)
        db.session.flush()
        return {
            "status": "created",
            "temp_id": temp_id,
            "entity_id": trip.id,
            "revision": rev,
        }

    elif change_type == "update":
        trip = Trip.query.get(entity_id)
        if trip is None or trip.deleted_at is not None:
            return {"status": "error", "entity_id": entity_id, "message": "Not found"}
        apply_trip_fields(trip, fields)
        trip.updated_at = datetime.now(timezone.utc)
        rev = stamp_revision(trip)
        return {"status": "ok", "entity_id": entity_id, "revision": rev}

    elif change_type == "delete":
        trip = Trip.query.get(entity_id)
        if trip is None:
            return {"status": "error", "entity_id": entity_id, "message": "Not found"}
        trip.deleted_at = datetime.now(timezone.utc)
        trip.updated_at = datetime.now(timezone.utc)
        rev = stamp_revision(trip)
        for leg in trip.legs:
            if leg.deleted_at is None:
                leg.deleted_at = datetime.now(timezone.utc)
                leg.updated_at = datetime.now(timezone.utc)
                stamp_revision(leg)
        return {"status": "deleted", "entity_id": entity_id, "revision": rev}

    return {"status": "error", "message": f"Unknown change_type: {change_type}"}


def _process_trip_leg_change(entity_id, temp_id, change_type, base_revision, fields):
    if change_type == "create":
        trip_id = fields.get("trip_id")
        if not trip_id:
            return {"status": "error", "temp_id": temp_id, "message": "trip_id required"}
        leg = TripLeg(trip_id=int(trip_id))
        apply_leg_fields(leg, fields)
        rev = stamp_revision(leg)
        db.session.add(leg)
        db.session.flush()
        return {
            "status": "created",
            "temp_id": temp_id,
            "entity_id": leg.id,
            "revision": rev,
        }

    elif change_type == "update":
        leg = TripLeg.query.get(entity_id)
        if leg is None or leg.deleted_at is not None:
            return {"status": "error", "entity_id": entity_id, "message": "Not found"}
        apply_leg_fields(leg, fields)
        leg.updated_at = datetime.now(timezone.utc)
        rev = stamp_revision(leg)
        return {"status": "ok", "entity_id": entity_id, "revision": rev}

    elif change_type == "delete":
        leg = TripLeg.query.get(entity_id)
        if leg is None:
            return {"status": "error", "entity_id": entity_id, "message": "Not found"}
        leg.deleted_at = datetime.now(timezone.utc)
        leg.updated_at = datetime.now(timezone.utc)
        rev = stamp_revision(leg)
        return {"status": "deleted", "entity_id": entity_id, "revision": rev}

    return {"status": "error", "message": f"Unknown change_type: {change_type}"}


def _get_changed_fields_since(flight, base_revision):
    """Placeholder: in production this would compare against a change log.

    For now, we return an empty set — meaning no server-side field tracking,
    so updates always apply cleanly. Full field-level tracking can be added
    by storing per-field revision stamps or a change audit log.
    """
    return set()
