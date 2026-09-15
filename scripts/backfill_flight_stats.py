import csv
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from app.extensions import db
from app.models import Flight
from app.services.geocoding import lookup_location
from app.services.importer import compute_distance

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


def _parse_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_text(value):
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _normalize_city_name(city_name):
    if not city_name:
        return None
    key = city_name.strip().lower()
    return CITY_RENAMES.get(key, city_name)


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
        queries.append(f"{airport_code} airport")
        queries.append(airport_code)
        if country:
            queries.append(f"{airport_code} airport {country}")
            queries.append(f"{airport_code}, {country}")

    if city:
        if country:
            queries.append(f"{city}, {country}")
        queries.append(city)

    for query in queries:
        _log(f"lookup: {prefix} '{query}'")
        details = lookup_location(query)
        if details and details.get("latitude") is not None and details.get("longitude") is not None:
            _log(f"lookup success: {prefix} '{query}'")
            return details
    _log(f"lookup failed: {prefix}")
    return None


def backfill():
    flights = Flight.query.order_by(Flight.start_date.asc()).all()
    updated = 0
    total = len(flights)
    for idx, flight in enumerate(flights, start=1):
        _log(
            f"flight {idx}/{total}: {flight.start_city_name} -> {flight.end_city_name}"
        )
        if flight.distance is None:
            if (
                flight.start_lat is not None
                and flight.start_long is not None
                and flight.end_lat is not None
                and flight.end_long is not None
            ):
                _log("distance: using stored lat/long")
                flight.distance = compute_distance(
                    flight.start_lat, flight.start_long, flight.end_lat, flight.end_long
                )
            else:
                _log("distance: missing lat/long, using lookups")
                start_details = _resolve_location(flight, "start")
                end_details = _resolve_location(flight, "end")
                if start_details and end_details:
                    flight.distance = compute_distance(
                        start_details.get("latitude"),
                        start_details.get("longitude"),
                        end_details.get("latitude"),
                        end_details.get("longitude"),
                    )
                else:
                    _log("distance unresolved: missing lookup coords")
            if flight.distance is not None:
                _log(f"distance computed: {flight.distance} miles")
            else:
                _log("distance unresolved")
        else:
            _log("distance already present")

        if db.session.is_modified(flight, include_collections=False):
            updated += 1

    db.session.commit()
    return updated


def main():
    app = create_app()
    with app.app_context():
        updated = backfill()
    print(f"Backfilled {updated} flights.")


if __name__ == "__main__":
    main()
