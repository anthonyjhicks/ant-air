import json
import time
from datetime import datetime
from urllib.parse import quote
from urllib.request import Request, urlopen

from ..extensions import db
from ..models import Aircraft

ADSBDB_URL = "https://api.adsbdb.com/v0/aircraft/"
USER_AGENT = "ant-air/1.0 (adsbdb)"
MIN_SECONDS_BETWEEN_LOOKUPS = 0.35

_CACHE = {}
_last_lookup_time = 0.0


def _throttle():
    global _last_lookup_time
    now = time.monotonic()
    wait_for = MIN_SECONDS_BETWEEN_LOOKUPS - (now - _last_lookup_time)
    if wait_for > 0:
        time.sleep(wait_for)
    _last_lookup_time = time.monotonic()


def fetch_aircraft_details(registration, timeout=6):
    if not registration:
        return None
    key = str(registration).strip().upper()
    if not key:
        return None
    if key in _CACHE:
        return _CACHE[key]

    url = f"{ADSBDB_URL}{quote(key)}"
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        _throttle()
        with urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
        data = json.loads(payload)
    except Exception:
        _CACHE[key] = None
        return None

    aircraft = data.get("response", {}).get("aircraft")
    if not isinstance(aircraft, dict):
        _CACHE[key] = None
        return None

    _CACHE[key] = aircraft
    return aircraft


def _serialize_aircraft(record):
    if not record:
        return None
    return {
        "registration": record.registration,
        "type": record.type,
        "icao_type": record.icao_type,
        "manufacturer": record.manufacturer,
        "mode_s": record.mode_s,
        "registered_owner_country_iso_name": record.registered_owner_country_iso_name,
        "registered_owner_country_name": record.registered_owner_country_name,
        "registered_owner_operator_flag_code": record.registered_owner_operator_flag_code,
        "registered_owner": record.registered_owner,
        "url_photo": record.url_photo,
        "url_photo_thumbnail": record.url_photo_thumbnail,
        "source_url": record.source_url,
        "fetched_at": record.fetched_at.isoformat() if record.fetched_at else None,
    }


def get_aircraft_details(registration):
    if not registration:
        return None
    key = str(registration).strip().upper()
    if not key:
        return None

    record = Aircraft.query.filter_by(registration=key).first()
    if record:
        return _serialize_aircraft(record)

    details = fetch_aircraft_details(key)
    if not details:
        return None

    record = Aircraft(registration=key)
    record.type = details.get("type")
    record.icao_type = details.get("icao_type")
    record.manufacturer = details.get("manufacturer")
    record.mode_s = details.get("mode_s")
    record.registered_owner_country_iso_name = details.get(
        "registered_owner_country_iso_name"
    )
    record.registered_owner_country_name = details.get(
        "registered_owner_country_name"
    )
    record.registered_owner_operator_flag_code = details.get(
        "registered_owner_operator_flag_code"
    )
    record.registered_owner = details.get("registered_owner")
    record.url_photo = details.get("url_photo")
    record.url_photo_thumbnail = details.get("url_photo_thumbnail")
    record.source_url = f"{ADSBDB_URL}{quote(key)}"
    record.raw_payload = details
    record.fetched_at = datetime.utcnow()

    db.session.add(record)
    db.session.commit()
    return _serialize_aircraft(record)
