"""Per-installation personalisation (home base, default traveller).

Values come from the Flask config when an app context is active and fall
back to environment variables otherwise, so the same helpers work from web
routes, the MCP server and the standalone scripts.
"""
import os


def _config_value(key, default=None):
    try:
        from flask import current_app

        return current_app.config.get(key, default)
    except RuntimeError:  # outside an app context
        return default


def _env_list(name):
    raw = os.environ.get(name, "")
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def default_traveller():
    """Traveller name to use when an import or webhook does not supply one."""
    value = _config_value("DEFAULT_TRAVELLER")
    if value is None:
        value = os.environ.get("DEFAULT_TRAVELLER", "").strip() or None
    return value or None


def home_city():
    value = _config_value("HOME_CITY")
    if value is None:
        value = os.environ.get("HOME_CITY", "").strip() or None
    return value or None


def home_country():
    value = _config_value("HOME_COUNTRY")
    if value is None:
        value = os.environ.get("HOME_COUNTRY", "").strip() or None
    return value or None


def home_airports():
    value = _config_value("HOME_AIRPORTS")
    if value is None:
        value = _env_list("HOME_AIRPORTS")
    return [str(item).strip().upper() for item in (value or []) if str(item).strip()]


def home_label():
    """Human-readable name for the home base, or None when unset."""
    return home_city() or (home_airports()[0] if home_airports() else None)
