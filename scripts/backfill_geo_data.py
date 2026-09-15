import argparse
import csv
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from app.extensions import db
from app.models import Flight
from app.services.geocoding import lookup_location
from app.services.importer import compute_distance, compute_route_direction

LOCATION_CACHE = {}
CITY_RENAMES = {
    "txl": "Berlin",
    "sxf": "Berlin",
}
AIRPORTS_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "app", "static", "airports.dat"
)
_AIRPORT_DATA = None


def _log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")


def _cache_key(name):
    return name.strip().lower()


def _normalize_city_name(city_name):
    if not city_name:
        return None
    key = _cache_key(city_name)
    return CITY_RENAMES.get(key, city_name)


def _clean_text(value):
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _parse_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_airport_data():
    global _AIRPORT_DATA
    if _AIRPORT_DATA is not None:
        return _AIRPORT_DATA
    data = {}
    if not os.path.exists(AIRPORTS_DATA_PATH):
        _log(f"airports.dat missing: {AIRPORTS_DATA_PATH}")
        _AIRPORT_DATA = data
        return _AIRPORT_DATA
    with open(AIRPORTS_DATA_PATH, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if len(row) < 8:
                continue
            iata = _clean_text(row[4])
            if not iata or iata == "\\N":
                continue
            lat = _parse_float(row[6])
            lon = _parse_float(row[7])
            if lat is None or lon is None:
                continue
            data[iata.upper()] = {
                "latitude": lat,
                "longitude": lon,
                "city": _clean_text(row[2]),
                "country": _clean_text(row[3]),
            }
    _AIRPORT_DATA = data
    _log(f"airports.dat loaded: {len(_AIRPORT_DATA)} airports")
    return _AIRPORT_DATA


def _lookup_airport_coords(airport_code):
    if not airport_code:
        return None
    data = _load_airport_data()
    return data.get(airport_code.strip().upper())


def _lookup_location(query, label):
    key = _cache_key(query)
    if key in LOCATION_CACHE:
        _log(f"cache hit: {label} '{query}'")
        return LOCATION_CACHE[key]
    _log(f"lookup: {label} '{query}'")
    LOCATION_CACHE[key] = lookup_location(query)
    if LOCATION_CACHE[key] is None:
        _log(f"miss: {label} '{query}'")
    return LOCATION_CACHE[key]


def _resolve_location(flight, prefix):
    airport_code = _clean_text(getattr(flight, f"{prefix}_airport"))
    city = _clean_text(getattr(flight, f"{prefix}_city_name"))
    country = _clean_text(getattr(flight, f"{prefix}_country"))
    if city:
        city = _normalize_city_name(city)

    if airport_code:
        airport_details = _lookup_airport_coords(airport_code)
        if airport_details:
            _log(f"airport data hit: {prefix} '{airport_code}'")
            return airport_details
        _log(f"airport data miss: {prefix} '{airport_code}'")

    queries = []
    if airport_code:
        queries.append((f"{airport_code} airport", f"{prefix} airport"))
        queries.append((airport_code, f"{prefix} airport"))
        if country:
            queries.append((f"{airport_code} airport {country}", f"{prefix} airport"))
            queries.append((f"{airport_code}, {country}", f"{prefix} airport"))

    if city:
        if country:
            queries.append((f"{city}, {country}", f"{prefix} city"))
        queries.append((city, f"{prefix} city"))

    for query, label in queries:
        details = _lookup_location(query, label)
        if details and details.get("latitude") is not None and details.get("longitude") is not None:
            return details
    return None


def _maybe_update_coord(flight, field_name, new_value, label):
    if new_value is None:
        return
    current = getattr(flight, field_name)
    if current != new_value:
        setattr(flight, field_name, new_value)
        _log(f"{label} {field_name} updated: {current} -> {new_value}")


def _maybe_update_direction(flight, new_value):
    if new_value is None:
        return
    current = flight.route_direction
    if current != new_value:
        flight.route_direction = new_value
        _log(f"route direction updated: {current} -> {new_value}")


def _has_missing_data(flight):
    return (
        flight.distance is None
        or flight.start_lat is None
        or flight.start_long is None
        or flight.end_lat is None
        or flight.end_long is None
        or flight.route_direction is None
    )


def backfill(missing_only=False, recompute_distance=False, refresh_geo=False, dry_run=False):
    flights = Flight.query.order_by(Flight.start_date.asc()).all()
    updated = 0

    total = len(flights)
    for idx, flight in enumerate(flights, start=1):
        if (
            missing_only
            and not recompute_distance
            and not refresh_geo
            and not _has_missing_data(flight)
        ):
            continue
        _log(f"flight {idx}/{total}: {flight.start_city_name} -> {flight.end_city_name}")

        coords_missing = (
            flight.start_lat is None
            or flight.start_long is None
            or flight.end_lat is None
            or flight.end_long is None
        )
        start_details = None
        end_details = None

        if coords_missing or refresh_geo:
            start_details = _resolve_location(flight, "start")
            end_details = _resolve_location(flight, "end")
            if not start_details and not end_details:
                _log("coords unresolved: missing location lookup")
            if start_details:
                if refresh_geo or flight.start_lat is None:
                    _maybe_update_coord(
                        flight, "start_lat", start_details.get("latitude"), "start"
                    )
                if refresh_geo or flight.start_long is None:
                    _maybe_update_coord(
                        flight, "start_long", start_details.get("longitude"), "start"
                    )
            if end_details:
                if refresh_geo or flight.end_lat is None:
                    _maybe_update_coord(flight, "end_lat", end_details.get("latitude"), "end")
                if refresh_geo or flight.end_long is None:
                    _maybe_update_coord(
                        flight, "end_long", end_details.get("longitude"), "end"
                    )

        if flight.distance is None or recompute_distance or refresh_geo:
            if flight.start_lat is None or flight.start_long is None:
                if start_details is None:
                    start_details = _resolve_location(flight, "start")
                if start_details:
                    _maybe_update_coord(
                        flight,
                        "start_lat",
                        flight.start_lat or start_details.get("latitude"),
                        "start",
                    )
                    _maybe_update_coord(
                        flight,
                        "start_long",
                        flight.start_long or start_details.get("longitude"),
                        "start",
                    )
            if flight.end_lat is None or flight.end_long is None:
                if end_details is None:
                    end_details = _resolve_location(flight, "end")
                if end_details:
                    _maybe_update_coord(
                        flight,
                        "end_lat",
                        flight.end_lat or end_details.get("latitude"),
                        "end",
                    )
                    _maybe_update_coord(
                        flight,
                        "end_long",
                        flight.end_long or end_details.get("longitude"),
                        "end",
                    )

            if (
                flight.start_lat is None
                or flight.start_long is None
                or flight.end_lat is None
                or flight.end_long is None
            ):
                _log("distance unresolved: missing coords")
            else:
                flight.distance = compute_distance(
                    flight.start_lat,
                    flight.start_long,
                    flight.end_lat,
                    flight.end_long,
                )
                action = "refreshed" if refresh_geo else "recomputed" if recompute_distance else "computed"
                _log(f"distance {action}: {flight.distance} miles")

        if refresh_geo or flight.route_direction is None:
            direction = compute_route_direction(
                flight.start_lat,
                flight.start_long,
                flight.end_lat,
                flight.end_long,
            )
            _maybe_update_direction(flight, direction)

        if db.session.is_modified(flight, include_collections=False):
            updated += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return updated


def main():
    parser = argparse.ArgumentParser(description="Backfill flight distance data.")
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Only update flights that have missing distance.",
    )
    parser.add_argument(
        "--recompute-distance",
        action="store_true",
        help="Recompute distance for all flights, even if already set.",
    )
    parser.add_argument(
        "--refresh-geo",
        action="store_true",
        help="Refresh lat/long lookups and recompute distance for all flights.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log updates without committing to the database.",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        updated = backfill(
            missing_only=args.missing_only,
            recompute_distance=args.recompute_distance,
            refresh_geo=args.refresh_geo,
            dry_run=args.dry_run,
        )
    label = "Would backfill" if args.dry_run else "Backfilled"
    print(f"{label} {updated} flights.")


if __name__ == "__main__":
    main()
