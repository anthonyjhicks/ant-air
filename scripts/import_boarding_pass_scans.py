import argparse
import glob
import os
import sys
from datetime import date, datetime, time

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from app.services.gemini_boarding_pass import (
    GeminiBoardingPassError,
    extract_boarding_pass_details,
)
from app.services.importer import import_rows


def _clean_text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_code(value):
    text = _clean_text(value)
    if not text:
        return None
    return "".join(text.split()).upper()


def _is_iata_code(value):
    if not value:
        return False
    cleaned = "".join(str(value).split()).upper()
    return len(cleaned) == 3 and cleaned.isalnum()


def _parse_time(value):
    if not value:
        return None
    text = _clean_text(value)
    if not text:
        return None
    for fmt in ("%H:%M", "%H%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _build_date(day, month, year):
    if not day or not month or not year:
        return None
    try:
        return date(int(year), int(month), int(day))
    except (ValueError, TypeError):
        return None


def _build_row(details, source_file, assume_year):
    airline_code = _normalize_code(details.get("airline_code"))
    flight_number = _normalize_code(details.get("flight_number"))

    origin_iata = _normalize_code(details.get("origin_iata"))
    destination_iata = _normalize_code(details.get("destination_iata"))
    origin_label = _clean_text(details.get("origin"))
    destination_label = _clean_text(details.get("destination"))

    if not origin_iata and _is_iata_code(origin_label):
        origin_iata = _normalize_code(origin_label)
        origin_label = None
    if not destination_iata and _is_iata_code(destination_label):
        destination_iata = _normalize_code(destination_label)
        destination_label = None

    dep_day = details.get("departure_day")
    dep_month = details.get("departure_month")
    dep_year = details.get("departure_year") or assume_year
    arr_day = details.get("arrival_day")
    arr_month = details.get("arrival_month")
    arr_year = details.get("arrival_year") or dep_year

    start_date = _build_date(dep_day, dep_month, dep_year)
    end_date = _build_date(arr_day, arr_month, arr_year)

    return {
        "booking_site": "boarding-pass",
        "airline_code": airline_code,
        "flight_number": flight_number,
        "start_city_name": origin_label,
        "start_airport": origin_iata,
        "end_city_name": destination_label,
        "end_airport": destination_iata,
        "start_date": start_date,
        "start_time": _parse_time(details.get("departure_time")),
        "end_date": end_date,
        "end_time": _parse_time(details.get("arrival_time")),
        "service_class": _clean_text(details.get("service_class")),
        "ticket_number": _clean_text(details.get("ticket_number")),
        "supplier_confirmation": _clean_text(details.get("confirmation_code")),
        "traveller": _clean_text(details.get("passenger_name")),
        "source_file": source_file,
    }


def _is_row_valid(row):
    if not row.get("start_date"):
        return False
    if not (row.get("start_airport") or row.get("start_city_name")):
        return False
    if not (row.get("end_airport") or row.get("end_city_name")):
        return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("scan_dir", help="Directory containing boarding pass PDFs")
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Scan subdirectories for PDF files",
    )
    parser.add_argument(
        "--assume-year",
        type=int,
        default=datetime.utcnow().year,
        help="Year to use when a boarding pass omits the year",
    )
    parser.add_argument(
        "--source-prefix",
        default="boarding-pass",
        help="Prefix stored in source_file for these imports",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of PDFs processed",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse files but do not import drafts",
    )
    args = parser.parse_args()

    scan_dir = args.scan_dir
    if not os.path.isdir(scan_dir):
        raise SystemExit(f"Directory not found: {scan_dir}")

    pattern = "**/*.pdf" if args.recursive else "*.pdf"
    pdf_paths = sorted(glob.glob(os.path.join(scan_dir, pattern)))
    if args.limit:
        pdf_paths = pdf_paths[: args.limit]

    if not pdf_paths:
        raise SystemExit("No PDF files found.")

    app = create_app()
    rows = []
    errors = []

    with app.app_context():
        for path in pdf_paths:
            file_label = os.path.basename(path)
            source_file = f"{args.source_prefix}/{file_label}"
            try:
                with open(path, "rb") as handle:
                    payload = handle.read()
                details, _debug = extract_boarding_pass_details(payload)
            except GeminiBoardingPassError as exc:
                errors.append(f"{file_label}: {exc}")
                continue

            if not details:
                errors.append(f"{file_label}: no details returned")
                continue

            row = _build_row(details, source_file, args.assume_year)
            if not _is_row_valid(row):
                errors.append(f"{file_label}: missing required details")
                continue
            rows.append(row)

        imported = 0
        if rows and not args.dry_run:
            imported = import_rows(rows, status="draft")

    print(f"Processed {len(pdf_paths)} PDFs.")
    if rows:
        status_label = "Prepared" if args.dry_run else "Imported"
        print(f"{status_label} {len(rows)} draft flights into inbox.")
    if imported:
        print(f"Imported {imported} draft flights.")
    if errors:
        print(f"Skipped {len(errors)} files:")
        for error in errors:
            print(f"- {error}")


if __name__ == "__main__":
    main()
