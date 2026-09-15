import os


def _csv_env(name):
    raw = os.environ.get(name, "")
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")
    # Branding shown in the navbar, page titles and the MCP server description.
    APP_NAME = os.environ.get("APP_NAME", "Ant Air").strip() or "Ant Air"
    # Personalisation. All optional: leave blank and the app stays generic.
    DEFAULT_TRAVELLER = os.environ.get("DEFAULT_TRAVELLER", "").strip() or None
    HOME_CITY = os.environ.get("HOME_CITY", "").strip() or None
    HOME_COUNTRY = os.environ.get("HOME_COUNTRY", "").strip() or None
    HOME_AIRPORTS = _csv_env("HOME_AIRPORTS")
    _raw_db_url = os.environ.get("DATABASE_URL")
    if _raw_db_url and _raw_db_url.startswith("postgresql://"):
        _raw_db_url = _raw_db_url.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
    SQLALCHEMY_DATABASE_URI = _raw_db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    GEOCODE_ON_IMPORT = os.environ.get("GEOCODE_ON_IMPORT", "false").lower() == "true"
    FLIGHTAWARE_API_BASE_URL = os.environ.get(
        "FLIGHTAWARE_API_BASE_URL", "https://aeroapi.flightaware.com/aeroapi"
    )
    FLIGHTAWARE_API_KEY = os.environ.get("FLIGHTAWARE_API_KEY")
    # Which flight-data provider backs history and registration lookups.
    # Only "flightaware" is implemented; see app/services/flight_lookup.py.
    FLIGHT_DATA_PROVIDER = os.environ.get("FLIGHT_DATA_PROVIDER", "flightaware")
    GEMINI_API_BASE_URL = os.environ.get(
        "GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
    )
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
    GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL")
    N8N_WEBHOOK_TOKEN = os.environ.get("N8N_WEBHOOK_TOKEN")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES", str(30 * 24 * 3600)))  # 30 days
    JWT_REFRESH_TOKEN_EXPIRES = int(os.environ.get("JWT_REFRESH_TOKEN_EXPIRES", str(90 * 24 * 3600)))  # 90 days
    MISSING_LEG_WINDOW_DAYS = int(os.environ.get("MISSING_LEG_WINDOW_DAYS", "30"))
    DUPLICATE_MATCH_RULES = {
        "threshold": 8,
        "primary_match_threshold": 8,
        "primary_match_signals": [
            "route",
            "flight_number",
            "supplier_confirmation",
            "ticket_number",
        ],
        "date_window_days": 0,
        "time_window_minutes": 120,
        "show_reasons": False,
        "blocking_keys": [
            "flight_number",
            "route",
            "city",
            "trip_id",
            "supplier_confirmation",
            "ticket_number",
        ],
        "signals": {
            "flight_number": 10,
            "route": 6,
            "city": 4,
            "trip_id": 4,
            "trip_name": 3,
            "supplier_confirmation": 5,
            "ticket_number": 4,
            "booking_site": 1,
            "traveller": 1,
            "service_class": 1,
            "start_time_window": 1,
        },
    }
