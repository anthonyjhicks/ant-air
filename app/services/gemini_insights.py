"""AI-powered flight history insights using the Gemini API."""

import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from urllib import request
from urllib.error import HTTPError, URLError

from flask import current_app

from .analytics import map_country_to_continent
from .gemini_utils import extract_json as _extract_json
from .gemini_utils import extract_text as _extract_text


class GeminiInsightsError(Exception):
    pass


WIDEBODY_TYPES = {
    "A330", "A340", "A350", "A380",
    "B747", "B767", "B777", "B787",
    "747", "767", "777", "787",
    "A330-200", "A330-300", "A330-900", "A330neo",
    "A340-300", "A340-600",
    "A350-900", "A350-1000",
    "A380-800",
    "747-400", "747-8",
    "767-300", "767-400",
    "777-200", "777-300", "777-9",
    "787-8", "787-9", "787-10",
    "Dreamliner",
    "MD-11", "DC-10", "L-1011",
    "IL-96", "IL-86",
}

MANUFACTURER_PREFIXES = {
    "A3": "Airbus", "A2": "Airbus", "A1": "Airbus",
    "B7": "Boeing", "B6": "Boeing", "B5": "Boeing", "B4": "Boeing", "B3": "Boeing",
    "73": "Boeing", "74": "Boeing", "75": "Boeing", "76": "Boeing", "77": "Boeing", "78": "Boeing",
    "E1": "Embraer", "E2": "Embraer", "ER": "Embraer",
    "CR": "Bombardier", "CL": "Bombardier", "DH": "De Havilland",
    "AT": "ATR",
    "MD": "McDonnell Douglas", "DC": "McDonnell Douglas",
    "BA": "BAe",
    "F1": "Fokker", "F5": "Fokker", "F7": "Fokker",
    "IL": "Ilyushin", "TU": "Tupolev", "AN": "Antonov",
    "L-": "Lockheed", "CO": "Concorde",
    "SA": "Saab",
}


def _classify_manufacturer(aircraft_type):
    if not aircraft_type:
        return "Unknown"
    t = aircraft_type.strip().upper()
    for prefix, mfr in MANUFACTURER_PREFIXES.items():
        if t.startswith(prefix):
            return mfr
    lower = aircraft_type.lower()
    if "airbus" in lower:
        return "Airbus"
    if "boeing" in lower or "dreamliner" in lower:
        return "Boeing"
    if "embraer" in lower:
        return "Embraer"
    if "bombardier" in lower or "canadair" in lower:
        return "Bombardier"
    if "dash" in lower or "dhc" in lower:
        return "De Havilland"
    if "atr" in lower:
        return "ATR"
    if "concorde" in lower:
        return "Concorde"
    if "fokker" in lower:
        return "Fokker"
    return "Other"


def _is_widebody(aircraft_type):
    if not aircraft_type:
        return False
    t = aircraft_type.strip()
    for wb in WIDEBODY_TYPES:
        if wb.lower() in t.lower():
            return True
    return False


def _time_bucket(t):
    if not t:
        return None
    hour = t.hour
    if hour < 6:
        return "Night (00-06)"
    elif hour < 12:
        return "Morning (06-12)"
    elif hour < 18:
        return "Afternoon (12-18)"
    else:
        return "Evening (18-24)"


def _is_red_eye(t):
    if not t:
        return False
    return t.hour >= 21 or t.hour < 5


def build_data_summary(flights, stats):
    """Build a comprehensive text summary of flight data for the Gemini prompt."""
    if not flights:
        return "No flight data available."

    lines = []

    # --- Overview ---
    dates = sorted(f.start_date for f in flights if f.start_date)
    first_flight = dates[0] if dates else None
    last_flight = dates[-1] if dates else None
    span_years = (last_flight.year - first_flight.year + 1) if first_flight and last_flight else 0

    lines.append("=== FLIGHT HISTORY OVERVIEW ===")
    lines.append(f"Total flights: {stats['total_flights']}")
    lines.append(f"Total distance: {stats['total_miles']:,.0f} miles")
    lines.append(f"Date range: {first_flight} to {last_flight} ({span_years} years)")
    lines.append(f"Average flights per year: {stats['total_flights'] / max(span_years, 1):.1f}")

    # --- Distance stats ---
    distances = [f.distance for f in flights if f.distance and f.distance > 0]
    if distances:
        lines.append("")
        lines.append("=== DISTANCE STATISTICS ===")
        lines.append(f"Average distance per flight: {statistics.mean(distances):,.0f} miles")
        lines.append(f"Median distance: {statistics.median(distances):,.0f} miles")
        lines.append(f"Shortest flight: {min(distances):,.0f} miles")
        lines.append(f"Longest flight: {max(distances):,.0f} miles")
        if len(distances) > 1:
            lines.append(f"Distance std dev: {statistics.stdev(distances):,.0f} miles")

    # --- Top destinations ---
    lines.append("")
    lines.append("=== TOP DESTINATIONS (city, count) ===")
    for city, count in stats["top_cities"][:15]:
        lines.append(f"  {city}: {count}")

    # --- Top routes ---
    lines.append("")
    lines.append("=== TOP ROUTES (route, count) ===")
    for route, count in stats["top_routes"][:15]:
        lines.append(f"  {route}: {count}")

    # --- Top countries ---
    lines.append("")
    lines.append("=== TOP COUNTRIES (country, count) ===")
    for country, count in stats["top_countries"][:20]:
        lines.append(f"  {country}: {count}")

    # --- Unique counts ---
    unique_airports = set()
    unique_cities = set()
    unique_countries = set()
    unique_airlines = set()
    unique_aircraft_types = set()
    unique_registrations = set()

    for f in flights:
        if f.start_airport:
            unique_airports.add(f.start_airport.strip().upper())
        if f.end_airport:
            unique_airports.add(f.end_airport.strip().upper())
        if f.start_city_name:
            unique_cities.add(f.start_city_name.strip())
        if f.end_city_name:
            unique_cities.add(f.end_city_name.strip())
        if f.end_country:
            unique_countries.add(f.end_country.strip())
        if f.start_country:
            unique_countries.add(f.start_country.strip())
        if f.airline_code:
            unique_airlines.add(f.airline_code.strip().upper())
        if f.aircraft_type_normalized:
            unique_aircraft_types.add(f.aircraft_type_normalized.strip())
        if f.aircraft_registration:
            unique_registrations.add(f.aircraft_registration.strip().upper())

    lines.append("")
    lines.append("=== UNIQUE COUNTS ===")
    lines.append(f"Unique airports: {len(unique_airports)}")
    lines.append(f"Unique cities: {len(unique_cities)}")
    lines.append(f"Unique countries: {len(unique_countries)}")
    lines.append(f"Unique airlines: {len(unique_airlines)}")
    lines.append(f"Unique aircraft types: {len(unique_aircraft_types)}")
    lines.append(f"Unique registrations (tail numbers): {len(unique_registrations)}")

    # --- Continent breakdown ---
    continent_counter = Counter()
    for country in unique_countries:
        continent = map_country_to_continent(country)
        continent_counter[continent or "Unknown"] += 1

    lines.append("")
    lines.append("=== CONTINENTS VISITED ===")
    for continent, count in continent_counter.most_common():
        lines.append(f"  {continent}: {count} countries")

    # --- Airlines ---
    lines.append("")
    lines.append("=== TOP AIRLINES (code, count) ===")
    for airline, count in stats["top_airlines"][:15]:
        lines.append(f"  {airline}: {count}")

    # --- Aircraft types ---
    lines.append("")
    lines.append("=== TOP AIRCRAFT TYPES (type, count) ===")
    for aircraft, count in stats["top_aircrafts"][:15]:
        lines.append(f"  {aircraft}: {count}")

    # --- Top registrations ---
    lines.append("")
    lines.append("=== TOP REGISTRATIONS (registration, count) ===")
    for reg, count in stats["top_tailnumbers"][:15]:
        lines.append(f"  {reg}: {count}")

    # --- Aircraft miles ---
    lines.append("")
    lines.append("=== TOP AIRCRAFT BY MILES ===")
    for aircraft, miles in stats["top_aircraft_miles"][:10]:
        lines.append(f"  {aircraft}: {miles:,.0f} miles")

    # --- Service class breakdown ---
    class_counter = Counter()
    for f in flights:
        cls = (f.service_class or "").strip() or "Unknown"
        class_counter[cls] += 1
    lines.append("")
    lines.append("=== SERVICE CLASS BREAKDOWN ===")
    for cls, count in class_counter.most_common():
        lines.append(f"  {cls}: {count}")

    # --- Manufacturer breakdown ---
    mfr_counter = Counter()
    for f in flights:
        mfr = _classify_manufacturer(f.aircraft_type_normalized)
        mfr_counter[mfr] += 1
    lines.append("")
    lines.append("=== MANUFACTURER BREAKDOWN ===")
    for mfr, count in mfr_counter.most_common():
        lines.append(f"  {mfr}: {count}")

    # --- Widebody vs narrowbody ---
    wb_count = sum(1 for f in flights if _is_widebody(f.aircraft_type_normalized))
    nb_count = len(flights) - wb_count
    lines.append("")
    lines.append("=== WIDEBODY VS NARROWBODY ===")
    lines.append(f"Widebody flights: {wb_count} ({wb_count / max(len(flights), 1) * 100:.1f}%)")
    lines.append(f"Narrowbody/regional flights: {nb_count} ({nb_count / max(len(flights), 1) * 100:.1f}%)")

    # --- Yearly breakdown ---
    lines.append("")
    lines.append("=== YEARLY FLIGHT COUNTS ===")
    for year, count in sorted(stats.get("yearly", {}) if isinstance(stats.get("yearly"), dict) else stats.get("yearly", [])):
        lines.append(f"  {year}: {count}")

    # --- Monthly trend (last 24 months) ---
    monthly_items = stats.get("monthly", [])
    if isinstance(monthly_items, dict):
        monthly_items = sorted(monthly_items.items())
    lines.append("")
    lines.append("=== MONTHLY FLIGHT COUNTS (recent 24 months) ===")
    for month, count in monthly_items[-24:]:
        lines.append(f"  {month}: {count}")

    # --- Day of week distribution ---
    dow_counter = Counter()
    dow_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for f in flights:
        if f.start_date:
            dow_counter[dow_names[f.start_date.weekday()]] += 1
    lines.append("")
    lines.append("=== DAY OF WEEK DISTRIBUTION ===")
    for day in dow_names:
        lines.append(f"  {day}: {dow_counter.get(day, 0)}")

    # --- Time of day distribution ---
    tod_counter = Counter()
    for f in flights:
        bucket = _time_bucket(f.start_time)
        if bucket:
            tod_counter[bucket] += 1
    if tod_counter:
        lines.append("")
        lines.append("=== TIME OF DAY DISTRIBUTION ===")
        for bucket in ["Night (00-06)", "Morning (06-12)", "Afternoon (12-18)", "Evening (18-24)"]:
            lines.append(f"  {bucket}: {tod_counter.get(bucket, 0)}")

    # --- Red-eye flights ---
    red_eye_count = sum(1 for f in flights if _is_red_eye(f.start_time))
    lines.append(f"\nRed-eye flights (departing 21:00-05:00): {red_eye_count}")

    # --- Hemisphere analysis ---
    north = south = east = west = 0
    for f in flights:
        if f.end_lat is not None:
            if f.end_lat >= 0:
                north += 1
            else:
                south += 1
        if f.end_long is not None:
            if f.end_long >= 0:
                east += 1
            else:
                west += 1
    if north + south > 0:
        lines.append("")
        lines.append("=== HEMISPHERE ANALYSIS ===")
        lines.append(f"Northern hemisphere destinations: {north}")
        lines.append(f"Southern hemisphere destinations: {south}")
        lines.append(f"Eastern hemisphere destinations: {east}")
        lines.append(f"Western hemisphere destinations: {west}")

    # --- Route direction ---
    dir_counter = Counter()
    for f in flights:
        d = (f.route_direction or "").strip().upper()
        if d:
            dir_counter[d] += 1
    if dir_counter:
        lines.append("")
        lines.append("=== ROUTE DIRECTION DISTRIBUTION ===")
        for d, count in dir_counter.most_common():
            lines.append(f"  {d}: {count}")

    # --- Booking sites ---
    bs_counter = Counter()
    for f in flights:
        bs = (f.booking_site or "").strip() or "Unknown"
        bs_counter[bs] += 1
    lines.append("")
    lines.append("=== BOOKING SITES ===")
    for bs, count in bs_counter.most_common(10):
        lines.append(f"  {bs}: {count}")

    # --- Traveller breakdown ---
    trav_counter = Counter()
    for f in flights:
        t = (f.traveller or "").strip() or "Unknown"
        trav_counter[t] += 1
    if len(trav_counter) > 1:
        lines.append("")
        lines.append("=== TRAVELLERS ===")
        for t, count in trav_counter.most_common():
            lines.append(f"  {t}: {count}")

    # --- Busiest periods ---
    day_counter = Counter()
    month_counter = Counter()
    for f in flights:
        if f.start_date:
            day_counter[f.start_date.isoformat()] += 1
            month_counter[f.start_date.strftime("%Y-%m")] += 1

    if day_counter:
        busiest_day, busiest_day_count = day_counter.most_common(1)[0]
        lines.append(f"\nBusiest single day: {busiest_day} ({busiest_day_count} flights)")
    if month_counter:
        busiest_month, busiest_month_count = month_counter.most_common(1)[0]
        lines.append(f"Busiest month: {busiest_month} ({busiest_month_count} flights)")

    # --- Consecutive flight day streaks ---
    if dates:
        sorted_dates = sorted(set(dates))
        max_streak = current_streak = 1
        for i in range(1, len(sorted_dates)):
            diff = (sorted_dates[i] - sorted_dates[i - 1]).days
            if diff == 1:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            elif diff > 1:
                current_streak = 1
        lines.append(f"Longest consecutive days with flights: {max_streak}")

    # --- Longest and shortest flights with details ---
    flights_with_distance = [(f, f.distance) for f in flights if f.distance and f.distance > 0]
    if flights_with_distance:
        longest = max(flights_with_distance, key=lambda x: x[1])
        shortest = min(flights_with_distance, key=lambda x: x[1])
        lines.append("")
        lines.append("=== NOTABLE FLIGHTS ===")
        lf = longest[0]
        lines.append(f"Longest: {lf.start_city_name or lf.start_airport} -> {lf.end_city_name or lf.end_airport} ({longest[1]:,.0f} mi, {lf.airline_code} {lf.flight_number}, {lf.start_date})")
        sf = shortest[0]
        lines.append(f"Shortest: {sf.start_city_name or sf.start_airport} -> {sf.end_city_name or sf.end_airport} ({shortest[1]:,.0f} mi, {sf.airline_code} {sf.flight_number}, {sf.start_date})")

    return "\n".join(lines)


INSIGHTS_SYSTEM_PROMPT = """You are an expert aviation analyst and travel data storyteller. Analyse the flight history data below and produce deep, creative, personalised insights.

Return ONLY valid JSON (no markdown, no code fences) with this exact structure:

{
  "travel_personality": {
    "title": "A creative archetype name (e.g. 'The Transcontinental Explorer', 'The Atlantic Commuter')",
    "subtitle": "A witty one-line tagline",
    "description": "2-3 sentences describing their travel personality based on the data patterns",
    "traits": [
      {"name": "Trait name", "description": "Brief explanation based on data"}
    ]
  },
  "geographic": {
    "highlights": [
      {"title": "Short label", "value": "Key number or fact", "detail": "1-2 sentence insight", "icon": "emoji"}
    ],
    "map_completion": {
      "visited_countries": <number>,
      "percentage": <number 0-100>,
      "detail": "Contextual comment about global coverage"
    },
    "hemisphere_balance": {
      "north_south": "Description of N/S balance",
      "east_west": "Description of E/W balance"
    },
    "missing_destinations": ["Suggest 3-5 destinations they haven't visited but might like based on their patterns"]
  },
  "aircraft_aviation": {
    "highlights": [
      {"title": "Short label", "value": "Key number or fact", "detail": "1-2 sentence insight", "icon": "emoji"}
    ],
    "diversity_score": <number 1-100>,
    "diversity_detail": "Explanation of score",
    "plane_spotter_score": <number 1-100>,
    "spotter_detail": "Explanation based on unique registrations",
    "manufacturer_loyalty": "Which manufacturer dominates and by how much",
    "widebody_ratio": "Statement about widebody vs narrowbody preference"
  },
  "airline": {
    "highlights": [
      {"title": "Short label", "value": "Key number or fact", "detail": "1-2 sentence insight", "icon": "emoji"}
    ],
    "loyalty_index": <number 1-100>,
    "loyalty_detail": "How concentrated their airline choices are",
    "alliance_analysis": "Which alliance(s) they gravitate toward",
    "fsc_lcc_ratio": "Full-service vs low-cost carrier analysis"
  },
  "temporal": {
    "highlights": [
      {"title": "Short label", "value": "Key number or fact", "detail": "1-2 sentence insight", "icon": "emoji"}
    ],
    "peak_season": "When they fly most and why it might be",
    "rhythm_description": "Description of their travel rhythm/cadence",
    "busiest_period": "Their most intense flying period",
    "year_over_year": "Growth or decline trend analysis"
  },
  "superlatives": [
    {"title": "Record name", "value": "The record value", "detail": "Context and fun commentary", "icon": "emoji", "category": "distance|frequency|time|geographic|equipment"}
  ],
  "fun_comparisons": [
    {"comparison": "A vivid comparison (e.g. 'Your total distance equals 2.3 trips to the Moon')", "value": "The key number", "icon": "emoji"}
  ],
  "predictions": {
    "next_destination": {"destination": "Predicted place", "reasoning": "Why based on patterns"},
    "travel_twin": {"archetype": "Famous traveller or type they resemble", "reasoning": "Why"},
    "growth_trend": "Prediction about their future flying patterns"
  }
}

GUIDELINES:
- Be specific and reference actual data points (cities, airlines, aircraft types, dates)
- Make insights genuinely interesting, not generic. Find surprising patterns.
- Include at least 3-4 highlights per category
- Generate at least 8 superlatives spanning different categories
- Generate at least 6 fun comparisons (use real math: Moon=238,900mi, Earth circumference=24,901mi, ISS orbit=254mi altitude, speed of sound=767mph, NYC-London=3,459mi)
- For the personality profile, be creative and specific to THEIR data - avoid generic archetypes
- The plane spotter score should reflect unique registrations relative to total flights
- The diversity score should reflect variety of aircraft types
- The loyalty index should reflect concentration (high=loyal to few airlines, low=spread across many)
- For predictions, base them on actual patterns you can see in the data
- For missing destinations, consider their geographic preferences and suggest places in regions they seem to like but haven't visited
- Keep all text concise and punchy - this is for display cards, not essays
"""


def generate_insights(flights, stats):
    """Generate AI insights by sending flight data summary to Gemini."""
    api_key = current_app.config.get("GEMINI_API_KEY")
    base_url = current_app.config.get(
        "GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
    )
    model = current_app.config.get("GEMINI_MODEL", "gemini-3-flash-preview")
    fallback_model = current_app.config.get("GEMINI_FALLBACK_MODEL")

    if not api_key:
        raise GeminiInsightsError("Missing GEMINI_API_KEY configuration.")

    data_summary = build_data_summary(flights, stats)

    user_prompt = f"Here is the complete flight history data to analyse:\n\n{data_summary}"

    def run_request(model_name, max_output_tokens):
        endpoint = f"{base_url.rstrip('/')}/models/{model_name}:generateContent"
        url = f"{endpoint}?key={api_key}"
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": INSIGHTS_SYSTEM_PROMPT + "\n\n" + user_prompt}]},
            ],
            "generationConfig": {
                "temperature": 0.8,
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
            with request.urlopen(req, timeout=60) as response:
                data = json.load(response)
        except HTTPError as exc:
            message = exc.read().decode("utf-8") if exc.fp else ""
            if exc.code == 429:
                return None, "RATE_LIMIT"
            raise GeminiInsightsError(
                f"Gemini request failed ({exc.code}). {message}".strip()
            ) from exc
        except URLError as exc:
            raise GeminiInsightsError("Gemini request failed.") from exc
        except TimeoutError as exc:
            raise GeminiInsightsError("Gemini request timed out.") from exc

        text = _extract_text(data)
        parsed = _extract_json(text)
        candidates = data.get("candidates") if isinstance(data, dict) else None
        finish_reason = None
        if isinstance(candidates, list) and candidates:
            first = candidates[0]
            if isinstance(first, dict):
                finish_reason = first.get("finishReason")
        return parsed, finish_reason

    models_to_try = [model]
    if fallback_model and fallback_model != model:
        models_to_try.append(fallback_model)

    parsed = finish_reason = None
    for model_name in models_to_try:
        parsed, finish_reason = run_request(model_name, 8192)
        if finish_reason == "RATE_LIMIT":
            continue
        if not isinstance(parsed, dict) and finish_reason == "MAX_TOKENS":
            parsed, finish_reason = run_request(model_name, 16384)
        break

    if finish_reason == "RATE_LIMIT":
        raise GeminiInsightsError("Gemini rate limit hit. Please try again later.")
    if not isinstance(parsed, dict):
        raise GeminiInsightsError("Failed to parse Gemini response into structured insights.")

    return parsed


def get_cached_insights(flight_count, total_miles):
    """Return last generated insights. Includes staleness flag if data has changed."""
    from app.models import InsightCache

    cached = InsightCache.query.filter_by(cache_key="main").first()
    if not cached or not cached.insights_json:
        return None
    try:
        insights = json.loads(cached.insights_json)
    except (json.JSONDecodeError, TypeError):
        return None
    is_stale = (
        cached.flight_count != flight_count
        or cached.total_miles != round(total_miles, 2)
    )
    generated_at = cached.generated_at.strftime("%d %b %Y, %H:%M") if cached.generated_at else None
    return {
        "insights": insights,
        "is_stale": is_stale,
        "generated_at": generated_at,
    }


def save_cached_insights(insights, flight_count, total_miles):
    """Save insights to the database cache."""
    from app.models import InsightCache
    from app.extensions import db

    cached = InsightCache.query.filter_by(cache_key="main").first()
    if not cached:
        cached = InsightCache(cache_key="main")
        db.session.add(cached)
    cached.flight_count = flight_count
    cached.total_miles = round(total_miles, 2)
    cached.insights_json = json.dumps(insights)
    cached.generated_at = datetime.utcnow()
    db.session.commit()
