import csv
import re
from datetime import datetime

from .csv_import import strip_citations
from .geocoding import normalize_country_name
from .personalisation import default_traveller

DATE_FORMATS = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"]
FLIGHT_NUMBER_RE = re.compile(r"^\s*([A-Za-z]{2,3})\s*0*([0-9]+)\s*$")


def parse_date(value, date_formats=None):
    if not value:
        return None
    formats = date_formats or DATE_FORMATS
    for fmt in formats:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_flight_number(value):
    if not value:
        return None, None
    match = FLIGHT_NUMBER_RE.match(value)
    if not match:
        trimmed = value.strip().upper()
        return None, trimmed or None
    airline_code = match.group(1).upper()
    number = match.group(2).lstrip("0") or "0"
    return airline_code, number


def parse_flightpath_csv(file_storage, geocode=True, date_formats=None, source_file=None):
    if hasattr(file_storage, "stream"):
        raw = file_storage.stream.read()
    else:
        raw = file_storage.read()

    if isinstance(raw, bytes):
        decoded = raw.decode("utf-8", errors="ignore")
    else:
        decoded = str(raw)

    reader = csv.DictReader(decoded.splitlines())
    rows = []
    errors = []

    geocode_cache = {} if geocode else None

    for index, row in enumerate(reader, start=2):
        date_value = strip_citations(row.get("Date (dd/mm/yyyy)") or row.get("Date"))
        origin = strip_citations(row.get("Origin"))
        origin_country = strip_citations(row.get("OriginCountry") or row.get("Origin Country"))
        destination = strip_citations(row.get("Destination"))
        destination_country = strip_citations(
            row.get("DestinationCountry") or row.get("Destination Country")
        )
        airline_code_raw = strip_citations(
            row.get("AirlineCode") or row.get("Airline Code")
        )
        flight_number_raw = strip_citations(
            row.get("Flight Number") or row.get("FlightNumber")
        )
        traveller = strip_citations(row.get("Traveller")) or default_traveller()

        start_date = parse_date(date_value, date_formats=date_formats)
        if not start_date:
            errors.append(f"Row {index}: invalid date '{date_value}'")
            continue

        if not origin or not destination:
            errors.append(f"Row {index}: missing origin or destination")
            continue

        parsed_code, flight_number = parse_flight_number(flight_number_raw)
        airline_code = (airline_code_raw or parsed_code or "").strip().upper() or None
        if not airline_code:
            airline_code = "BA"
        origin_details = None
        destination_details = None
        if geocode:
            origin_key = origin.lower()
            destination_key = destination.lower()
            origin_details = geocode_cache.get(origin_key)
            if origin_details is None:
                origin_details = {}
                geocode_cache[origin_key] = origin_details
            destination_details = geocode_cache.get(destination_key)
            if destination_details is None:
                destination_details = {}
                geocode_cache[destination_key] = destination_details

        rows.append(
            {
                "trip_name": None,
                "trip_id": None,
                "trip_type": "Air",
                "activity_id": None,
                "activity_cost": None,
                "url": None,
                "booking_site": "baflightpath",
                "supplier_confirmation": None,
                "booking_date": None,
                "booking_site_phone": None,
                "traveller": traveller,
                "ticket_number": None,
                "airline_code": airline_code,
                "aircraft": None,
                "service_class": None,
                "flight_number": flight_number,
                "start_country": normalize_country_name(
                    origin_country
                    or (origin_details.get("country") if origin_details else None)
                ),
                "start_city_name": origin,
                "start_airport": None,
                "start_terminal": None,
                "start_lat": (
                    origin_details.get("latitude") if origin_details else None
                ),
                "start_long": (
                    origin_details.get("longitude") if origin_details else None
                ),
                "start_date": start_date,
                "start_time": None,
                "end_country": normalize_country_name(
                    destination_country
                    or (destination_details.get("country") if destination_details else None)
                ),
                "end_city_name": destination,
                "end_airport": None,
                "end_terminal": None,
                "end_lat": (
                    destination_details.get("latitude") if destination_details else None
                ),
                "end_long": (
                    destination_details.get("longitude") if destination_details else None
                ),
                "end_date": None,
                "end_time": None,
                "stops": None,
                "distance": None,
                "source_file": source_file,
            }
        )

    return rows, errors
