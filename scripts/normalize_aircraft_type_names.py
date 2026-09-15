import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import or_

from app import create_app
from app.extensions import db
from app.models import Flight
from app.services.aircraft_types import AIRCRAFT_TYPE_ALIASES as AIRCRAFT_TYPE_MAP


def update_field(model, field_name, description_field_name=None):
    total = 0
    skipped = 0
    field = getattr(model, field_name)
    max_length = model.__table__.columns[field_name].type.length
    with db.session.no_autoflush:
        for old_value, new_value in AIRCRAFT_TYPE_MAP.items():
            records = model.query.filter(field == old_value).all()
            updated = 0
            skipped_here = 0
            for record in records:
                if max_length and len(new_value) > max_length:
                    skipped_here += 1
                    if description_field_name:
                        current = getattr(record, description_field_name)
                        if not current:
                            setattr(record, description_field_name, new_value)
                    continue
                setattr(record, field_name, new_value)
                print(
                    f"{model.__name__} #{record.id} {field_name}: "
                    f"{old_value} -> {new_value}"
                )
                updated += 1
            if records:
                message = (
                    f"{model.__name__}.{field_name}: "
                    f"{old_value} -> {new_value} ({updated})"
                )
                if skipped_here:
                    message += f" skipped {skipped_here}"
                print(message)
            total += updated
            skipped += skipped_here
    return total, skipped


def strip_passenger(model, field_name):
    total = 0
    field = getattr(model, field_name)
    records = model.query.filter(field.contains("Passenger")).all()
    for record in records:
        current = getattr(record, field_name)
        if not current or "Passenger" not in current:
            continue
        cleaned = current.replace("Passenger", "").strip()
        if cleaned != current:
            setattr(record, field_name, cleaned)
            total += 1
    if records:
        print(f"{model.__name__}.{field_name}: stripped Passenger ({total})")
    return total


def backfill_normalized_from_aircraft():
    total = 0
    skipped = 0
    max_length = Flight.__table__.columns["aircraft_type_normalized"].type.length
    records = Flight.query.filter(
        Flight.aircraft.isnot(None),
        or_(
            Flight.aircraft_type_normalized.is_(None),
            Flight.aircraft_type_normalized == "",
        ),
    ).all()
    for record in records:
        source = record.aircraft
        if not source:
            continue
        cleaned_source = source.strip()
        if not cleaned_source:
            continue
        lookup_key = cleaned_source.upper()
        normalized = AIRCRAFT_TYPE_MAP.get(lookup_key, cleaned_source)
        if max_length and len(normalized) > max_length:
            skipped += 1
            continue
        record.aircraft_type_normalized = normalized
        print(
            f"{Flight.__name__} #{record.id} aircraft_type_normalized: "
            f"{source} -> {normalized}"
        )
        total += 1
    if records:
        message = (
            f"{Flight.__name__}.aircraft_type_normalized: "
            f"backfilled from aircraft ({total})"
        )
        if skipped:
            message += f" skipped {skipped}"
        print(message)
    return total, skipped


def normalize_existing_normalized():
    total = 0
    skipped = 0
    max_length = Flight.__table__.columns["aircraft_type_normalized"].type.length
    records = Flight.query.filter(
        Flight.aircraft_type_normalized.isnot(None),
        Flight.aircraft_type_normalized != "",
    ).all()
    for record in records:
        current = record.aircraft_type_normalized
        if not current:
            continue
        cleaned = current.strip()
        if not cleaned:
            continue
        lookup_key = cleaned.upper()
        normalized = AIRCRAFT_TYPE_MAP.get(lookup_key, cleaned)
        if max_length and len(normalized) > max_length:
            skipped += 1
            continue
        if normalized == current:
            continue
        record.aircraft_type_normalized = normalized
        print(
            f"{Flight.__name__} #{record.id} aircraft_type_normalized: "
            f"{current} -> {normalized}"
        )
        total += 1
    if records:
        message = (
            f"{Flight.__name__}.aircraft_type_normalized: "
            f"normalized existing values ({total})"
        )
        if skipped:
            message += f" skipped {skipped}"
        print(message)
    return total, skipped


def main():
    app = create_app()
    with app.app_context():
        total = 0
        skipped = 0
        updated, skipped_here = normalize_existing_normalized()
        total += updated
        skipped += skipped_here
        updated, skipped_here = backfill_normalized_from_aircraft()
        total += updated
        skipped += skipped_here
        total += strip_passenger(Flight, "aircraft_type_normalized")

        if total or skipped:
            db.session.commit()
            print(f"Updated {total} records.")
            if skipped:
                print(f"Skipped {skipped} records due to field length.")
        else:
            print("No matching aircraft_type values found.")


if __name__ == "__main__":
    main()
