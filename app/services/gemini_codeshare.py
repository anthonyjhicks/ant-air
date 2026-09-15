import json
import re
from urllib import request
from urllib.error import HTTPError, URLError

from flask import current_app

from .gemini_utils import extract_json as _extract_json
from .gemini_utils import extract_text as _extract_text


class GeminiCodeshareError(Exception):
    pass


def _normalize_code(value):
    if not value:
        return ""
    return str(value).strip().replace(" ", "").upper()


def _normalize_flight_number(value):
    if not value:
        return ""
    return str(value).strip().replace(" ", "").upper()


def _coerce_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _split_flight_iata(value):
    cleaned = _normalize_flight_number(value)
    if not cleaned:
        return None, None
    match = re.match(r"^([A-Z0-9]{2,3})(.+)$", cleaned)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def lookup_codeshare_details(
    airline_code,
    flight_number,
    dep_date=None,
    dep_iata=None,
    arr_iata=None,
):
    api_key = current_app.config.get("GEMINI_API_KEY")
    base_url = current_app.config.get(
        "GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
    )
    model = current_app.config.get("GEMINI_MODEL", "gemini-3-flash-preview")
    fallback_model = current_app.config.get("GEMINI_FALLBACK_MODEL")
    if not api_key:
        raise GeminiCodeshareError("Missing GEMINI_API_KEY configuration.")
    if not airline_code or not flight_number:
        raise GeminiCodeshareError("Airline code and flight number are required.")

    airline_code = _normalize_code(airline_code)
    flight_number = _normalize_flight_number(flight_number)

    dep_iata = _normalize_code(dep_iata)
    arr_iata = _normalize_code(arr_iata)
    dep_year = dep_date.year if dep_date else None
    dep_date_label = dep_date.strftime("%Y-%m-%d") if dep_date else "unknown"
    route_label = (
        f"{dep_iata}-{arr_iata}" if dep_iata and arr_iata else "unknown"
    )

    prompt = (
        "You are a flight data assistant. Given a marketing airline code and flight number, "
        "determine the aircraft type, aircraft registration, and the operating flight if this is a codeshare. "
        "Consider the airline's fleet and route-specific equipment for the given year and route. "
        "If a specific aircraft type was not in service for that airline/route/year, choose a more "
        "likely type from that period. "
        "Return ONLY JSON with keys: aircraft_type, aircraft_registration, operating_airline_code, "
        "operating_flight_number, confidence, reasoning. "
        "Use IATA airline codes. Use the numeric portion for operating_flight_number. "
        "If the flight is not a codeshare or the operating flight is unknown, set operating_* to null. "
        "If the aircraft type or registration is unknown, set those to null. "
        "Confidence should be a number from 0 to 1 for the registration accuracy.\n"
        "Reasoning should be a short sentence referencing the year/route constraint.\n"
        f"airline_code={airline_code}\n"
        f"flight_number={flight_number}\n"
        f"route={route_label}\n"
        f"departure_date={dep_date_label}\n"
        f"departure_year={dep_year or 'unknown'}\n"
        "Example output:\n"
        '{"aircraft_type": "A320", "aircraft_registration": "G-EUUB", "operating_airline_code": "IB", "operating_flight_number": "1234", "confidence": 0.82}'
    )

    def run_request(model_name, max_output_tokens):
        endpoint = f"{base_url.rstrip('/')}/models/{model_name}:generateContent"
        url = f"{endpoint}?key={api_key}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": max_output_tokens,
            },
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=20) as response:
                data = json.load(response)
        except HTTPError as exc:
            message = exc.read().decode("utf-8") if exc.fp else ""
            payload_error = None
            try:
                payload_error = json.loads(message) if message else None
            except json.JSONDecodeError:
                payload_error = None
            debug = {
                "request": {"endpoint": endpoint, "prompt": prompt, "payload": payload},
                "response": {"payload": payload_error or message, "status": exc.code},
            }
            if exc.code == 429:
                return None, debug, "RATE_LIMIT"
            raise GeminiCodeshareError(
                f"Gemini request failed ({exc.code}). {message}".strip()
            ) from exc
        except URLError as exc:
            raise GeminiCodeshareError("Gemini request failed.") from exc
        except TimeoutError as exc:
            raise GeminiCodeshareError("Gemini request timed out.") from exc
        text = _extract_text(data)
        parsed = _extract_json(text)
        candidates = data.get("candidates") if isinstance(data, dict) else None
        finish_reason = None
        if isinstance(candidates, list) and candidates:
            first = candidates[0]
            if isinstance(first, dict):
                finish_reason = first.get("finishReason")
        debug = {
            "request": {
                "endpoint": endpoint,
                "model": model_name,
                "prompt": prompt,
                "payload": payload,
            },
            "response": {
                "payload": data,
                "text": text,
                "parsed": parsed,
                "finishReason": finish_reason,
            },
        }
        return parsed, debug, finish_reason

    models_to_try = [model]
    if fallback_model and fallback_model != model:
        models_to_try.append(fallback_model)

    parsed = debug = finish_reason = None
    for model_name in models_to_try:
        parsed, debug, finish_reason = run_request(model_name, 1024)
        if finish_reason == "RATE_LIMIT":
            continue
        if not isinstance(parsed, dict) and finish_reason == "MAX_TOKENS":
            parsed, debug, finish_reason = run_request(model_name, 2048)
        break

    if finish_reason == "RATE_LIMIT":
        raise GeminiCodeshareError("Gemini rate limit hit.")
    if not isinstance(parsed, dict):
        return None, debug

    aircraft_type = parsed.get("aircraft_type")
    aircraft_registration = parsed.get("aircraft_registration")
    registration_confidence = _coerce_float(parsed.get("confidence"))
    operating_airline_code = _normalize_code(parsed.get("operating_airline_code"))
    operating_flight_number = _normalize_flight_number(
        parsed.get("operating_flight_number")
    )
    if not operating_airline_code and operating_flight_number:
        inferred_code, inferred_number = _split_flight_iata(operating_flight_number)
        if inferred_code and inferred_number:
            operating_airline_code = _normalize_code(inferred_code)
            operating_flight_number = _normalize_flight_number(inferred_number)
    if not operating_airline_code or not operating_flight_number:
        inferred_code, inferred_number = _split_flight_iata(
            parsed.get("operating_flight_iata")
        )
        if not operating_airline_code:
            operating_airline_code = _normalize_code(inferred_code)
        if not operating_flight_number:
            operating_flight_number = _normalize_flight_number(inferred_number)

    if (
        operating_airline_code
        and operating_flight_number
        and operating_airline_code == airline_code
        and operating_flight_number == flight_number
    ):
        operating_airline_code = ""
        operating_flight_number = ""

    return (
        {
            "aircraft_type": aircraft_type or None,
            "aircraft_registration": aircraft_registration or None,
            "operating_airline_code": operating_airline_code or None,
            "operating_flight_number": operating_flight_number or None,
            "registration_confidence": registration_confidence,
            "source": "gemini",
        },
        debug,
    )


def lookup_route_aircraft_type(airline_code, dep_iata, arr_iata, dep_date):
    api_key = current_app.config.get("GEMINI_API_KEY")
    base_url = current_app.config.get(
        "GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
    )
    model = current_app.config.get("GEMINI_MODEL", "gemini-3-flash-preview")
    fallback_model = current_app.config.get("GEMINI_FALLBACK_MODEL")
    if not api_key:
        raise GeminiCodeshareError("Missing GEMINI_API_KEY configuration.")
    if not airline_code or not dep_iata or not arr_iata or not dep_date:
        raise GeminiCodeshareError(
            "Airline code, route, and departure date are required."
        )

    airline_code = _normalize_code(airline_code)
    dep_iata = _normalize_code(dep_iata)
    arr_iata = _normalize_code(arr_iata)

    def build_prompt(scope, date_value):
        return (
            "You are a flight data assistant. Given an airline, route, and date, "
            "provide the most likely aircraft type and aircraft registration used on that route around that time. "
            "Return ONLY JSON with keys: aircraft_type, aircraft_registration, confidence, scope. "
            "Use IATA aircraft type codes like A320, B738, B77W. "
            "If the aircraft type or registration is unknown, set them to null. "
            "Confidence should be a number from 0 to 1 for the registration accuracy.\n"
            "Do not include citations or sources; this is a best-guess answer.\n"
            f"airline_code={airline_code}\n"
            f"dep_iata={dep_iata}\n"
            f"arr_iata={arr_iata}\n"
            f"{scope}={date_value}\n"
            "Example output:\n"
            '{"aircraft_type": "A320", "aircraft_registration": "G-EUUB", "confidence": 0.62, "scope": "month"}'
        )

    def run_request(model_name, max_output_tokens, prompt):
        endpoint = f"{base_url.rstrip('/')}/models/{model_name}:generateContent"
        url = f"{endpoint}?key={api_key}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": max_output_tokens,
            },
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=20) as response:
                data = json.load(response)
        except HTTPError as exc:
            message = exc.read().decode("utf-8") if exc.fp else ""
            payload_error = None
            try:
                payload_error = json.loads(message) if message else None
            except json.JSONDecodeError:
                payload_error = None
            debug = {
                "request": {"endpoint": endpoint, "prompt": prompt, "payload": payload},
                "response": {"payload": payload_error or message, "status": exc.code},
            }
            if exc.code == 429:
                return None, debug, "RATE_LIMIT"
            raise GeminiCodeshareError(
                f"Gemini request failed ({exc.code}). {message}".strip()
            ) from exc
        except URLError as exc:
            raise GeminiCodeshareError("Gemini request failed.") from exc
        except TimeoutError as exc:
            raise GeminiCodeshareError("Gemini request timed out.") from exc
        text = _extract_text(data)
        parsed = _extract_json(text)
        candidates = data.get("candidates") if isinstance(data, dict) else None
        finish_reason = None
        if isinstance(candidates, list) and candidates:
            first = candidates[0]
            if isinstance(first, dict):
                finish_reason = first.get("finishReason")
        debug = {
            "request": {
                "endpoint": endpoint,
                "model": model_name,
                "prompt": prompt,
                "payload": payload,
            },
            "response": {
                "payload": data,
                "text": text,
                "parsed": parsed,
                "finishReason": finish_reason,
            },
        }
        return parsed, debug, finish_reason

    models_to_try = [model]
    if fallback_model and fallback_model != model:
        models_to_try.append(fallback_model)

    scopes = [
        ("date", dep_date.strftime("%Y-%m-%d")),
        ("month", dep_date.strftime("%Y-%m")),
        ("year", dep_date.strftime("%Y")),
    ]

    last_debug = None
    for scope, value in scopes:
        prompt = build_prompt(scope, value)
        parsed = debug = finish_reason = None
        for model_name in models_to_try:
            parsed, debug, finish_reason = run_request(model_name, 512, prompt)
            if finish_reason == "RATE_LIMIT":
                continue
            if not isinstance(parsed, dict) and finish_reason == "MAX_TOKENS":
                parsed, debug, finish_reason = run_request(model_name, 1024, prompt)
            break
        if finish_reason == "RATE_LIMIT":
            last_debug = debug
            continue
        if not isinstance(parsed, dict):
            last_debug = debug
            continue
        aircraft_type = parsed.get("aircraft_type")
        aircraft_registration = parsed.get("aircraft_registration")
        registration_confidence = _coerce_float(parsed.get("confidence"))
        if not aircraft_type and not aircraft_registration:
            last_debug = debug
            continue
        return (
            {
                "aircraft_type": aircraft_type,
                "aircraft_registration": aircraft_registration or None,
                "registration_confidence": registration_confidence,
                "scope": scope,
                "source": "gemini_guess",
            },
            debug,
        )

    if finish_reason == "RATE_LIMIT":
        raise GeminiCodeshareError("Gemini rate limit hit.")
    return None, last_debug
