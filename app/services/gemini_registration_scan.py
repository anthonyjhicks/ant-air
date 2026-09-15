"""Gemini vision service for scanning aircraft registrations from photos."""

import base64
import json
from urllib import request
from urllib.error import HTTPError, URLError

from flask import current_app

from .gemini_utils import extract_json, extract_text


class GeminiRegistrationScanError(Exception):
    pass


PROMPT = (
    "You are reading an aircraft registration number from a photo. "
    "The registration is an alphanumeric code typically painted on the tail, "
    "rear fuselage, or wing of the aircraft (e.g. G-EUUB, VH-OQA, N12345, "
    "9V-SWN, ZK-OKA, A6-EEA, JA812A, D-AISP). "
    "Return ONLY JSON with keys: registration, confidence, "
    "location_on_aircraft, aircraft_type_guess. "
    "registration must be uppercase with the correct dash/hyphen placement. "
    "confidence should be 0.0 to 1.0. "
    "location_on_aircraft should describe where you see it (tail, fuselage, etc). "
    "aircraft_type_guess should be the IATA type code if you can identify "
    "the aircraft model (e.g. A320, B738, B77W), or null if unsure. "
    "If no registration is visible, return registration as null."
)


def scan_registration_from_image(image_bytes, mime_type="image/jpeg"):
    """Send an aircraft photo to Gemini vision and extract the registration.

    Returns (parsed_dict, debug_info) tuple.
    parsed_dict has keys: registration, confidence, location_on_aircraft,
    aircraft_type_guess. Returns (None, debug_info) on failure.
    """
    api_key = current_app.config.get("GEMINI_API_KEY")
    base_url = current_app.config.get(
        "GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
    )
    model = current_app.config.get("GEMINI_MODEL", "gemini-3-flash-preview")
    fallback_model = current_app.config.get("GEMINI_FALLBACK_MODEL")

    if not api_key:
        raise GeminiRegistrationScanError("Missing GEMINI_API_KEY configuration.")
    if not image_bytes:
        raise GeminiRegistrationScanError("No image data provided.")

    def run_request(model_name, max_output_tokens):
        endpoint = f"{base_url.rstrip('/')}/models/{model_name}:generateContent"
        url = f"{endpoint}?key={api_key}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": PROMPT},
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": base64.b64encode(image_bytes).decode("utf-8"),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
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
            with request.urlopen(req, timeout=30) as response:
                data = json.load(response)
        except HTTPError as exc:
            message = exc.read().decode("utf-8") if exc.fp else ""
            payload_error = None
            try:
                payload_error = json.loads(message) if message else None
            except json.JSONDecodeError:
                payload_error = None
            debug = {
                "request": {"endpoint": endpoint, "prompt": PROMPT, "payload": payload},
                "response": {"payload": payload_error or message, "status": exc.code},
            }
            if exc.code == 429:
                return None, debug, "RATE_LIMIT"
            raise GeminiRegistrationScanError(
                f"Gemini request failed ({exc.code}). {message}".strip()
            ) from exc
        except URLError as exc:
            raise GeminiRegistrationScanError("Gemini request failed.") from exc
        except TimeoutError as exc:
            raise GeminiRegistrationScanError("Gemini request timed out.") from exc

        text = extract_text(data)
        parsed = extract_json(text)
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
                "prompt": PROMPT,
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
        parsed, debug, finish_reason = run_request(model_name, 512)
        if finish_reason == "RATE_LIMIT":
            continue
        if not isinstance(parsed, dict) and finish_reason == "MAX_TOKENS":
            parsed, debug, finish_reason = run_request(model_name, 1024)
        break

    if finish_reason == "RATE_LIMIT":
        raise GeminiRegistrationScanError("Gemini rate limit hit.")
    if not isinstance(parsed, dict):
        return None, debug

    return parsed, debug
