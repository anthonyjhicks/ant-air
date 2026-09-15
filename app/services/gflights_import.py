import csv
from datetime import datetime

from .csv_import import strip_citations
from .geocoding import normalize_country_name

DATE_FORMATS = ["%Y-%m-%d"]


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


def parse_gflights_csv(file_storage, date_formats=None, source_file=None):
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

    for index, row in enumerate(reader, start=2):
        trip_name = strip_citations(row.get("Trip Name"))
        trip_type = strip_citations(row.get("Flight Type"))
        date_value = strip_citations(
            row.get("Flight Date (dd/mm/yyyy)") or row.get("Flight Date")
        )
        origin = strip_citations(row.get("Origin"))
        destination = strip_citations(row.get("Destination"))
        origin_city = strip_citations(row.get("Origin City"))
        origin_country = normalize_country_name(
            strip_citations(row.get("Origin Country"))
        )
        destination_city = strip_citations(row.get("City"))
        destination_country = normalize_country_name(strip_citations(row.get("Country")))
        booking_site = "gflights"
        traveller = strip_citations(row.get("Traveller"))

        start_date = parse_date(date_value, date_formats=date_formats)
        if not start_date:
            errors.append(f"Row {index}: invalid flight date '{date_value}'")
            continue

        if not origin or not destination:
            errors.append(f"Row {index}: missing origin or destination")
            continue

        rows.append(
            {
                "trip_name": trip_name,
                "trip_id": None,
                "trip_type": trip_type,
                "activity_id": None,
                "activity_cost": None,
                "url": None,
                "booking_site": booking_site,
                "supplier_confirmation": None,
                "booking_date": None,
                "booking_site_phone": None,
                "traveller": traveller,
                "ticket_number": None,
                "airline_code": None,
                "aircraft": None,
                "service_class": None,
                "flight_number": None,
                "start_country": origin_country,
                "start_city_name": origin_city,
                "start_airport": origin,
                "start_terminal": None,
                "start_lat": None,
                "start_long": None,
                "start_date": start_date,
                "start_time": None,
                "end_country": destination_country,
                "end_city_name": destination_city,
                "end_airport": destination,
                "end_terminal": None,
                "end_lat": None,
                "end_long": None,
                "end_date": None,
                "end_time": None,
                "stops": None,
                "distance": None,
                "source_file": source_file,
            }
        )

    return rows, errors
