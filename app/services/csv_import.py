import csv
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .geocoding import normalize_country_name


DATE_FORMATS = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"]
TIME_FORMATS = ["%H:%M", "%H:%M:%S"]

CITE_RE = re.compile(r"\s*\[cite:[^\]]+\]")

AIRPORT_OVERRIDES = {
    "TXL": {"city": "Berlin", "country": "Germany"},
    "SXF": {"city": "Berlin", "country": "Germany"},
}


def strip_citations(value):
    if not isinstance(value, str):
        return value
    return CITE_RE.sub("", value).strip()


def normalize_header(header):
    return re.sub(r"[^a-z0-9]+", " ", header.strip().lower()).strip()


HEADER_MAP = {
    "tripname": "trip_name",
    "trip name": "trip_name",
    "tripid": "trip_id",
    "trip id": "trip_id",
    "type": "trip_type",
    "activityid": "activity_id",
    "activity id": "activity_id",
    "activitycost": "activity_cost",
    "activity cost": "activity_cost",
    "url": "url",
    "bookingsite": "booking_site",
    "booking site": "booking_site",
    "supplierconfirmation": "supplier_confirmation",
    "supplier confirmation": "supplier_confirmation",
    "bookingdate": "booking_date",
    "booking date": "booking_date",
    "bookingsitephone": "booking_site_phone",
    "booking site phone": "booking_site_phone",
    "traveller": "traveller",
    "ticketnumber": "ticket_number",
    "ticket number": "ticket_number",
    "airlinecode": "airline_code",
    "airline code": "airline_code",
    "aircraft": "aircraft",
    "serviceclass": "service_class",
    "service class": "service_class",
    "flightnumber": "flight_number",
    "flight number": "flight_number",
    "startcountry": "start_country",
    "start country": "start_country",
    "startcityname": "start_city_name",
    "start city name": "start_city_name",
    "startairport": "start_airport",
    "start airport": "start_airport",
    "startterminal": "start_terminal",
    "start terminal": "start_terminal",
    "startlat": "start_lat",
    "start lat": "start_lat",
    "startlong": "start_long",
    "start long": "start_long",
    "startdate": "start_date",
    "start date": "start_date",
    "starttime": "start_time",
    "start time": "start_time",
    "endcountry": "end_country",
    "end country": "end_country",
    "endcityname": "end_city_name",
    "end city name": "end_city_name",
    "endairport": "end_airport",
    "end airport": "end_airport",
    "endterminal": "end_terminal",
    "end terminal": "end_terminal",
    "endlat": "end_lat",
    "end lat": "end_lat",
    "endlong": "end_long",
    "end long": "end_long",
    "enddate": "end_date",
    "end date": "end_date",
    "endtime": "end_time",
    "end time": "end_time",
    "stops": "stops",
    "distance": "distance",
}


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


def parse_time(value):
    if not value:
        return None
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).time()
        except ValueError:
            continue
    return None


def parse_decimal(value):
    if value is None or value == "":
        return None
    raw = str(value).replace(",", "").strip()
    raw = re.sub(r"[^\d.]+", "", raw)
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def parse_int(value):
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def parse_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def apply_airport_overrides(parsed_entry):
    for prefix in ("start", "end"):
        airport_code = parsed_entry.get(f"{prefix}_airport")
        if not airport_code:
            continue
        override = AIRPORT_OVERRIDES.get(str(airport_code).strip().upper())
        if not override:
            continue
        city_field = f"{prefix}_city_name"
        country_field = f"{prefix}_country"
        if not parsed_entry.get(city_field):
            parsed_entry[city_field] = override.get("city")
        if not parsed_entry.get(country_field):
            parsed_entry[country_field] = override.get("country")


def parse_csv(file_storage, date_formats=None, source_file=None):
    if hasattr(file_storage, "stream"):
        raw = file_storage.stream.read()
    else:
        raw = file_storage.read()

    if isinstance(raw, bytes):
        decoded = raw.decode("utf-8", errors="ignore")
    else:
        decoded = str(raw)
    cleaned_text = CITE_RE.sub("", decoded)
    reader = csv.DictReader(cleaned_text.splitlines())
    normalized_headers = {}
    for header in reader.fieldnames or []:
        normalized_headers[header] = HEADER_MAP.get(normalize_header(header))

    rows = []
    errors = []
    for index, row in enumerate(reader, start=2):
        parsed = {}
        for header, value in row.items():
            target = normalized_headers.get(header)
            if not target:
                continue
            cleaned = strip_citations(value)
            parsed[target] = cleaned

        parsed_start_date = parse_date(parsed.get("start_date"), date_formats=date_formats)
        if not parsed_start_date:
            errors.append(
                f"Row {index}: invalid start date '{parsed.get('start_date')}'"
            )
            continue
        start_time = parse_time(parsed.get("start_time"))
        end_time = parse_time(parsed.get("end_time"))

        parsed_entry = {
            "trip_name": parsed.get("trip_name"),
            "trip_id": parsed.get("trip_id"),
            "trip_type": parsed.get("trip_type"),
            "activity_id": parsed.get("activity_id"),
            "activity_cost": parse_decimal(parsed.get("activity_cost")),
            "url": parsed.get("url"),
            "booking_site": parsed.get("booking_site"),
            "supplier_confirmation": parsed.get("supplier_confirmation"),
            "booking_date": parse_date(parsed.get("booking_date"), date_formats=date_formats),
            "booking_site_phone": parsed.get("booking_site_phone"),
            "traveller": parsed.get("traveller"),
            "ticket_number": parsed.get("ticket_number"),
            "airline_code": parsed.get("airline_code"),
            "service_class": parsed.get("service_class"),
            "aircraft": parsed.get("aircraft"),
            "flight_number": parsed.get("flight_number"),
            "start_country": normalize_country_name(parsed.get("start_country")),
            "start_city_name": parsed.get("start_city_name"),
            "start_airport": parsed.get("start_airport"),
            "start_terminal": parsed.get("start_terminal"),
            "start_lat": parse_float(parsed.get("start_lat")),
            "start_long": parse_float(parsed.get("start_long")),
            "start_date": parsed_start_date,
            "start_time": start_time,
            "end_country": normalize_country_name(parsed.get("end_country")),
            "end_city_name": parsed.get("end_city_name"),
            "end_airport": parsed.get("end_airport"),
            "end_terminal": parsed.get("end_terminal"),
            "end_lat": parse_float(parsed.get("end_lat")),
            "end_long": parse_float(parsed.get("end_long")),
            "end_date": parse_date(parsed.get("end_date"), date_formats=date_formats),
            "end_time": end_time,
            "stops": parse_int(parsed.get("stops")),
            "distance": parse_float(parsed.get("distance")),
            "source_file": source_file,
        }

        apply_airport_overrides(parsed_entry)

        if not (parsed_entry["start_city_name"] or parsed_entry["start_airport"]):
            errors.append(f"Row {index}: missing start city or airport")
            continue
        if not (parsed_entry["end_city_name"] or parsed_entry["end_airport"]):
            errors.append(f"Row {index}: missing end city or airport")
            continue

        rows.append(parsed_entry)

    return rows, errors
