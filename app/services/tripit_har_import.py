import json
import re
from datetime import datetime

from .csv_import import parse_decimal, parse_float, parse_time
from .geocoding import normalize_country_name

TRIPIT_TRIP_URL_RE = re.compile(r"/api/v2/get/trip/uuid/([a-f0-9\\-]+)")


def _decode_har_payload(content):
    body = content.get("text")
    if not body:
        return None
    if content.get("encoding") == "base64":
        import base64

        return base64.b64decode(body).decode("utf-8", errors="replace")
    return body


def _normalize_air_objects(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _normalize_segments(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_distance(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\\d+(?:\\.\\d+)?", str(value))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _parse_stops(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower()
    if "nonstop" in text or "non-stop" in text:
        return 0
    match = re.search(r"\\d+", text)
    if match:
        return int(match.group(0))
    return None


def _format_traveller(value):
    if isinstance(value, list) and value:
        value = value[0]
    if not isinstance(value, dict):
        return None
    first = (value.get("first_name") or "").strip()
    last = (value.get("last_name") or "").strip()
    full = " ".join(part for part in (first, last) if part)
    return full or None


def _trip_type(value):
    if isinstance(value, dict):
        return value.get("purpose_type_code")
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            return first.get("purpose_type_code")
    return None


def _trip_uuid_from_url(url):
    match = TRIPIT_TRIP_URL_RE.search(url or "")
    if match:
        return match.group(1)
    return None


def parse_tripit_har(file_storage, source_file=None):
    if hasattr(file_storage, "read"):
        raw = file_storage.read()
    else:
        with open(file_storage, "rb") as handle:
            raw = handle.read()

    if isinstance(raw, bytes):
        decoded = raw.decode("utf-8", errors="ignore")
    else:
        decoded = str(raw)

    payload = json.loads(decoded)
    entries = payload.get("log", {}).get("entries", [])
    rows = []
    errors = []
    seen = set()

    for entry in entries:
        request_url = entry.get("request", {}).get("url", "")
        if "/api/v2/get/trip/uuid/" not in request_url:
            continue
        if "include_objects/true" not in request_url:
            continue

        content = entry.get("response", {}).get("content", {})
        body = _decode_har_payload(content)
        if not body:
            errors.append(f"Missing response body for {request_url}")
            continue
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            errors.append(f"Invalid JSON in response for {request_url}")
            continue

        trip = data.get("Trip") or {}
        trip_uuid = trip.get("uuid") or _trip_uuid_from_url(request_url)
        air_objects = _normalize_air_objects(data.get("AirObject"))
        if not air_objects:
            errors.append(f"No AirObject entries for {request_url}")
            continue

        for air in air_objects:
            segments = _normalize_segments(air.get("Segment"))
            for segment in segments:
                segment_uuid = segment.get("uuid")
                if not segment_uuid:
                    errors.append(f"Missing segment uuid for {request_url}")
                    continue
                dedupe_key = (trip_uuid, segment_uuid)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                start_dt = segment.get("StartDateTime") or {}
                end_dt = segment.get("EndDateTime") or {}
                start_date = _parse_date(start_dt.get("date"))
                end_date = _parse_date(end_dt.get("date"))

                row = {
                    "trip_name": trip.get("display_name"),
                    "trip_id": trip_uuid,
                    "trip_type": _trip_type(trip.get("TripPurposes")),
                    "activity_id": segment_uuid,
                    "activity_cost": parse_decimal(air.get("total_cost")),
                    "url": (
                        f"https://www.tripit.com/app/trips/{trip_uuid}/flights/{segment_uuid}"
                        if trip_uuid
                        else None
                    ),
                    "booking_site": air.get("booking_site_name"),
                    "supplier_confirmation": air.get("supplier_conf_num"),
                    "booking_date": None,
                    "booking_site_phone": air.get("booking_site_phone"),
                    "traveller": _format_traveller(air.get("Traveler")),
                    "ticket_number": None,
                    "airline_code": segment.get("marketing_airline_code"),
                    "aircraft": segment.get("aircraft_display_name")
                    or segment.get("aircraft"),
                    "service_class": segment.get("service_class"),
                    "flight_number": segment.get("marketing_flight_number"),
                    "start_country": normalize_country_name(
                        segment.get("start_country_code")
                    ),
                    "start_city_name": segment.get("start_city_name"),
                    "start_airport": segment.get("start_airport_code"),
                    "start_terminal": segment.get("start_terminal"),
                    "start_lat": parse_float(segment.get("start_airport_latitude")),
                    "start_long": parse_float(segment.get("start_airport_longitude")),
                    "start_date": start_date,
                    "start_time": parse_time(start_dt.get("time")),
                    "end_country": normalize_country_name(segment.get("end_country_code")),
                    "end_city_name": segment.get("end_city_name"),
                    "end_airport": segment.get("end_airport_code"),
                    "end_terminal": segment.get("end_terminal"),
                    "end_lat": parse_float(segment.get("end_airport_latitude")),
                    "end_long": parse_float(segment.get("end_airport_longitude")),
                    "end_date": end_date,
                    "end_time": parse_time(end_dt.get("time")),
                    "stops": _parse_stops(segment.get("stops")),
                    "distance": _parse_distance(segment.get("distance")),
                    "source_file": source_file,
                }

                if not row["start_date"]:
                    errors.append(
                        f"Segment {segment_uuid}: invalid start date '{start_dt.get('date')}'"
                    )
                    continue
                rows.append(row)

    return rows, errors
