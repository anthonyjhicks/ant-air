import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import pycountry
except ImportError:  # pragma: no cover - optional dependency
    pycountry = None

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "ant-air/1.0 (geocoding)"
ACCEPT_LANGUAGE = "en"
MIN_SECONDS_BETWEEN_LOOKUPS = 1.1

_CACHE = {}
_AIRPORT_CITY_CACHE = {}

COUNTRY_CODE_OVERRIDES = {
    "UK": "United Kingdom",
    "GB": "United Kingdom",
    "US": "United States",
}

_last_lookup_time = 0.0


def _parse_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _throttle():
    global _last_lookup_time
    now = time.monotonic()
    wait_for = MIN_SECONDS_BETWEEN_LOOKUPS - (now - _last_lookup_time)
    if wait_for > 0:
        time.sleep(wait_for)
    _last_lookup_time = time.monotonic()


def _extract_city(address):
    if not isinstance(address, dict):
        return None
    for key in (
        "city",
        "town",
        "village",
        "hamlet",
        "municipality",
        "county",
        "state_district",
    ):
        value = address.get(key)
        if value:
            if value.strip().lower() == "greater london":
                return "London"
            return value
    return None


def normalize_country_name(value):
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 2 and text.isalpha():
        code = text.upper()
        override = COUNTRY_CODE_OVERRIDES.get(code)
        if override:
            return override
        if pycountry:
            country = pycountry.countries.get(alpha_2=code)
            if country:
                return country.name
        return text
    return text


def lookup_location(name, timeout=6):
    if not name:
        return None
    key = name.strip().lower()
    if key in _CACHE:
        return _CACHE[key]

    params = urlencode(
        {
            "q": name,
            "format": "json",
            "addressdetails": 1,
            "accept-language": ACCEPT_LANGUAGE,
            "limit": 1,
        }
    )
    url = f"{NOMINATIM_URL}?{params}"
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": ACCEPT_LANGUAGE},
    )
    try:
        _throttle()
        with urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
        results = json.loads(payload)
    except Exception:
        _CACHE[key] = None
        return None

    if not results:
        _CACHE[key] = None
        return None

    result = results[0]
    address = result.get("address", {})
    latitude = _parse_float(result.get("lat"))
    longitude = _parse_float(result.get("lon"))
    country = normalize_country_name(address.get("country"))
    city = _extract_city(address)

    if latitude is None or longitude is None:
        _CACHE[key] = None
        return None

    resolved = {
        "latitude": latitude,
        "longitude": longitude,
        "country": country,
        "city": city,
    }
    _CACHE[key] = resolved
    return resolved


def lookup_airport_city(city_name, country_hint=None, timeout=6):
    if not city_name:
        return None
    cache_parts = [city_name.strip().lower()]
    if country_hint:
        cache_parts.append(country_hint.strip().lower())
    cache_key = "::".join(cache_parts)
    if cache_key in _AIRPORT_CITY_CACHE:
        return _AIRPORT_CITY_CACHE[cache_key]

    if country_hint:
        query = f"{city_name}, {country_hint} airport"
    else:
        query = f"{city_name} airport"
    details = lookup_location(query, timeout=timeout)
    if not details:
        if country_hint:
            query = f"{city_name}, {country_hint} international airport"
        else:
            query = f"{city_name} international airport"
        details = lookup_location(query, timeout=timeout)

    _AIRPORT_CITY_CACHE[cache_key] = details
    return details
