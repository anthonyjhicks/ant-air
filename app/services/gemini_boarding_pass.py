import base64
import json
from urllib import request
from urllib.error import HTTPError, URLError

from flask import current_app

from .gemini_utils import extract_json as _extract_json
from .gemini_utils import extract_text as _extract_text


class GeminiBoardingPassError(Exception):
    pass


def extract_boarding_pass_details(pdf_bytes):
    api_key = current_app.config.get("GEMINI_API_KEY")
    base_url = current_app.config.get(
        "GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
    )
    model = current_app.config.get("GEMINI_MODEL", "gemini-3-flash-preview")
    fallback_model = current_app.config.get("GEMINI_FALLBACK_MODEL")
    if not api_key:
        raise GeminiBoardingPassError("Missing GEMINI_API_KEY configuration.")
    if not pdf_bytes:
        raise GeminiBoardingPassError("No PDF data provided.")

    prompt = (
        "You are extracting flight details from a boarding pass scan. "
        "Return ONLY JSON with the keys:\n"
        "airline_code, flight_number, origin, origin_iata, destination, destination_iata, "
        "departure_day, departure_month, departure_year, departure_time, "
        "arrival_day, arrival_month, arrival_year, arrival_time, "
        "service_class, ticket_number, confirmation_code, passenger_name.\n"
        "Use IATA airline codes and IATA airport codes when present. "
        "If the year is not shown, set departure_year/arrival_year to null. "
        "Use month numbers (1-12). Use 24h time in HH:MM. "
        "If a value is missing, set it to null. Do not include citations."
    )

    def run_request(model_name, max_output_tokens):
        endpoint = f"{base_url.rstrip('/')}/models/{model_name}:generateContent"
        url = f"{endpoint}?key={api_key}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": "application/pdf",
                                "data": base64.b64encode(pdf_bytes).decode("utf-8"),
                            }
                        },
                    ],
                }
            ],
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
                "request": {"endpoint": endpoint, "prompt": prompt, "payload": payload},
                "response": {"payload": payload_error or message, "status": exc.code},
            }
            if exc.code == 429:
                return None, debug, "RATE_LIMIT"
            raise GeminiBoardingPassError(
                f"Gemini request failed ({exc.code}). {message}".strip()
            ) from exc
        except URLError as exc:
            raise GeminiBoardingPassError("Gemini request failed.") from exc
        except TimeoutError as exc:
            raise GeminiBoardingPassError("Gemini request timed out.") from exc
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
        parsed, debug, finish_reason = run_request(model_name, 2048)
        if finish_reason == "RATE_LIMIT":
            continue
        if not isinstance(parsed, dict) and finish_reason == "MAX_TOKENS":
            parsed, debug, finish_reason = run_request(model_name, 4096)
        break

    if finish_reason == "RATE_LIMIT":
        raise GeminiBoardingPassError("Gemini rate limit hit.")
    if not isinstance(parsed, dict):
        return None, debug

    parsed["source"] = "gemini_boarding_pass"
    return parsed, debug
