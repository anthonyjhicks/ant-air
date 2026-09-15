"""Provider-neutral flight lookup shared by the web routes and the MCP server.

``FLIGHT_DATA_PROVIDER`` selects the provider. Only FlightAware AeroAPI is
implemented today; this module exists so callers never need to know which
provider answers, and so a second provider can be added in one place.
"""
from dataclasses import dataclass, field
from typing import Any, Optional

from flask import current_app

from ..models import Flight
from . import flightaware_history as flightaware

DEFAULT_PROVIDER = "flightaware"

_PROVIDERS = {
    "flightaware": {
        "label": "FlightAware",
        "is_configured": flightaware.is_configured,
        "is_within_window": flightaware.is_within_window,
        "window_error": flightaware.window_error,
        "search": flightaware.search_flightaware_history,
        "record": flightaware.record_flightaware_history,
        "error_type": flightaware.FlightAwareHistoryError,
        "window_error_type": flightaware.FlightAwareWindowError,
    },
}


class FlightLookupError(Exception):
    """A lookup could not be completed.

    ``kind`` is one of ``invalid_flight``, ``outside_window``,
    ``not_configured``, ``not_found``, ``rate_limited`` or ``provider_error``.
    ``status`` is the matching HTTP status for the web routes.
    """

    def __init__(self, message, kind, status):
        super().__init__(message)
        self.kind = kind
        self.status = status


@dataclass
class FlightLookupResult:
    provider: str
    history: Any
    aircraft: Optional[str]  # display name, e.g. "Boeing 777-200"
    aircraft_type: Optional[str]  # ICAO designator, e.g. "B772"
    aircraft_registration: Optional[str]
    # Which flight fields this lookup actually changed.
    applied: dict[str, bool] = field(default_factory=dict)


def active_provider() -> str:
    name = current_app.config.get("FLIGHT_DATA_PROVIDER") or DEFAULT_PROVIDER
    return str(name).strip().lower()


def provider_label() -> str:
    spec = _PROVIDERS.get(active_provider())
    return spec["label"] if spec else active_provider()


def _provider():
    name = active_provider()
    spec = _PROVIDERS.get(name)
    if spec is None:
        raise FlightLookupError(
            f"Unknown FLIGHT_DATA_PROVIDER '{name}'; known providers: "
            + ", ".join(sorted(_PROVIDERS)),
            "not_configured",
            503,
        )
    return name, spec


def lookup_ident(flight: Flight) -> str:
    """The flight designator to search for, preferring the operating carrier."""
    lookup_airline = flight.operating_airline_code or flight.airline_code
    lookup_number = flight.operating_flight_number or flight.flight_number
    if not lookup_airline or not lookup_number:
        raise FlightLookupError(
            "Airline code and flight number are required.", "invalid_flight", 400
        )
    if not flight.start_date:
        raise FlightLookupError(
            "Departure date is required for lookup.", "invalid_flight", 400
        )
    ident = flightaware.normalize_flight_iata(lookup_airline, lookup_number)
    if not ident:
        raise FlightLookupError(
            "Unable to determine flight IATA code.", "invalid_flight", 400
        )
    return ident


def check_lookup_possible(flight: Flight) -> str:
    """Raise FlightLookupError if the provider cannot be asked about ``flight``.

    Returns the ident that would be searched. Makes no network calls, so it is
    cheap enough to use for skip decisions before a batch of lookups.
    """
    name, spec = _provider()
    ident = lookup_ident(flight)
    if not spec["is_configured"]():
        raise FlightLookupError(
            f"{spec['label']} is not configured (missing API key).",
            "not_configured",
            503,
        )
    if not spec["is_within_window"](flight.start_date):
        raise FlightLookupError(
            str(spec["window_error"](flight.start_date)), "outside_window", 400
        )
    return ident


def lookup_and_record(flight: Flight, *, overwrite_aircraft: bool = True) -> FlightLookupResult:
    """Ask the provider about ``flight`` and store what it returns.

    Stores a history row and copies the aircraft type and registration onto the
    flight (only into empty fields unless ``overwrite_aircraft``). Adds to the
    session without committing; the caller commits. Raises FlightLookupError
    when nothing was stored.
    """
    name, spec = _provider()
    ident = check_lookup_possible(flight)
    try:
        entry = spec["search"](ident, flight.start_date, dep_iata=flight.start_airport)
    except spec["window_error_type"] as exc:
        raise FlightLookupError(str(exc), "outside_window", 400) from exc
    except spec["error_type"] as exc:
        code = getattr(exc, "status_code", None)
        if code == 429:
            raise FlightLookupError(str(exc), "rate_limited", 429) from exc
        raise FlightLookupError(str(exc), "provider_error", 502) from exc
    if not entry:
        raise FlightLookupError(
            f"No matching flight found on {spec['label']}.", "not_found", 404
        )

    tracked = ("aircraft", "aircraft_type_normalized", "aircraft_registration")
    before = {name_: getattr(flight, name_) for name_ in tracked}
    history = spec["record"](flight, entry, overwrite_aircraft=overwrite_aircraft)
    applied = {name_: getattr(flight, name_) != before[name_] for name_ in tracked}
    return FlightLookupResult(
        provider=name,
        history=history,
        aircraft=history.aircraft_type_description or history.aircraft_type,
        aircraft_type=history.aircraft_type,
        aircraft_registration=history.aircraft_registration,
        applied=applied,
    )
