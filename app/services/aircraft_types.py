"""Aircraft type helpers shared by the lookups and the normalisation script.

``AIRCRAFT_TYPE_ALIASES`` maps ICAO/IATA type designators and common spellings
to the display names used in the ``aircraft`` field. ``resolve_aircraft`` turns
a provider's answer (registration plus ICAO type) into a display name and an
ICAO designator: the alias map supplies the display name, and the aircraft
table (fed by ADSBDB) fills in when the map does not know the code.
"""
from flask import current_app

from .adsbdb import get_aircraft_details

AIRCRAFT_TYPE_ALIASES = {
    "Airbus A318": "Airbus A318/A319/A320",
    "Airbus A319": "Airbus A318/A319/A320",
    "Airbus A320": "Airbus A318/A319/A320",
    "A318": "Airbus A318/A319/A320",
    "A319": "Airbus A318/A319/A320",
    "A320": "Airbus A318/A319/A320",
    "A20N": "Airbus A320neo",
    "A21N": "Airbus A321neo",
    "A330": "Airbus A330",
    "A330-300": "Airbus A330-300",
    "A350-900": "Airbus A350-900",
    "A351": "Airbus A350-1000",
    "A346": "Airbus A340-600",
    "A340-600": "Airbus A340-600",
    "A35K": "Airbus A350-1000",
    "A380": "Airbus A380-800",
    "A388": "Airbus A380-800",
    "A380-800": "Airbus A380-800",
    "738": "Boeing 737-800",
    "B738": "Boeing 737-800",
    "B733": "Boeing 737-300",
    "B734": "Boeing 737-400",
    "B737-400": "Boeing 737-400",
    "B739": "Boeing 737-900",
    "B744": "Boeing 747-400",
    "B747-400": "Boeing 747-400",
    "744": "Boeing 747-400",
    "B789": "Boeing 787-9",
    "B787": "Boeing 787",
    "B787-8": "Boeing 787-8",
    "B788": "Boeing 787-8",
    "B787-9": "Boeing 787-9",
    "B38M": "Boeing 737 MAX 8",
    "777": "Boeing 777",
    "B777": "Boeing 777",
    "B772": "Boeing 777-200",
    "B777-200": "Boeing 777-200",
    "B777-200ER": "Boeing 777-200ER",
    "B77W": "Boeing 777-300ER",
    "B777-300ER": "Boeing 777-300ER",
    "77W": "Boeing 777-300ER",
    "B752": "Boeing 757-200",
    "B757-200": "Boeing 757-200",
    "B763": "Boeing 767-300",
    "D328": "Dornier 328",
    "DH4": "De Havilland Dash 8-400",
    "DH8D": "De Havilland Dash 8-400",
    "ERJ-145": "Embraer ERJ-145",
    "Fokker 50": "Fokker 50",
    "RJ85": "Avro RJ85",
    "E75L": "Embraer 175",
    "E175": "Embraer 175",
    "E190": "Embraer 190",
    # Additional ICAO designators FlightAware commonly reports.
    "A321": "Airbus A321",
    "A332": "Airbus A330-200",
    "A333": "Airbus A330-300",
    "A339": "Airbus A330-900neo",
    "A343": "Airbus A340-300",
    "A359": "Airbus A350-900",
    "B735": "Boeing 737-500",
    "B736": "Boeing 737-600",
    "B737": "Boeing 737-700",
    "B37M": "Boeing 737 MAX 7",
    "B39M": "Boeing 737 MAX 9",
    "B748": "Boeing 747-8",
    "B753": "Boeing 757-300",
    "B762": "Boeing 767-200",
    "B764": "Boeing 767-400",
    "B77L": "Boeing 777-200LR",
    "B78X": "Boeing 787-10",
    "BCS1": "Airbus A220-100",
    "BCS3": "Airbus A220-300",
    "E170": "Embraer 170",
    "E195": "Embraer 195",
    "E290": "Embraer E190-E2",
    "E295": "Embraer E195-E2",
    "CRJ2": "Bombardier CRJ200",
    "CRJ7": "Bombardier CRJ700",
    "CRJ9": "Bombardier CRJ900",
    "AT45": "ATR 42-500",
    "AT72": "ATR 72",
    "AT75": "ATR 72-500",
    "AT76": "ATR 72-600",
    "DH8A": "De Havilland Dash 8-100",
    "DH8B": "De Havilland Dash 8-200",
    "DH8C": "De Havilland Dash 8-300",
}


def display_name_for_type(code):
    """Display name for an ICAO/IATA type designator, or None if unknown."""
    key = (code or "").strip().upper()
    if not key:
        return None
    return AIRCRAFT_TYPE_ALIASES.get(key)


def _adsbdb_display_name(details):
    """Manufacturer plus model from an aircraft-table row, e.g. "Boeing 777 236ER"."""
    model = (details.get("type") or "").strip()
    manufacturer = (details.get("manufacturer") or "").strip()
    if not model:
        return None
    if manufacturer and not model.lower().startswith(manufacturer.lower()):
        return f"{manufacturer} {model}"
    return model


def resolve_aircraft(registration, icao_type):
    """Return ``(display_name, icao_type)`` for the aircraft that flew.

    The provider's ``icao_type`` wins because it describes this specific
    flight; when it is missing, the registration's aircraft-table row (fetched
    from ADSBDB, free and keyless, on a miss) supplies it. The display name is
    the curated alias-map label for that code, so flights get the same labels
    the normalisation script produces; for codes the map does not know it
    falls back to ADSBDB's manufacturer and model, then the bare code.
    """
    reg = (registration or "").strip().upper()
    details = None
    if reg:
        try:
            details = get_aircraft_details(reg)
        except Exception as exc:  # network or database hiccup: fall back to the map
            current_app.logger.warning("Aircraft lookup failed for %s: %s", reg, exc)
            details = None
    details = details or {}
    code = (icao_type or "").strip().upper() or (details.get("icao_type") or "").strip().upper() or None
    name = display_name_for_type(code) or _adsbdb_display_name(details) or code
    return name, code


def apply_aircraft_to_flight(flight, *, registration=None, icao_type=None, overwrite=True):
    """Set the flight's registration, display type and ICAO type.

    With ``overwrite`` existing values are replaced; otherwise only empty fields
    are filled. Returns the resolved ``(display_name, icao_type)``.
    """
    name, code = resolve_aircraft(registration, icao_type)
    reg = (registration or "").strip().upper() or None
    if reg and (overwrite or not flight.aircraft_registration):
        flight.aircraft_registration = reg
    if name and (overwrite or not flight.aircraft):
        flight.aircraft = name[:64]
    if code and (overwrite or not flight.aircraft_type_normalized):
        flight.aircraft_type_normalized = code
    return name, code
