"""Sync helpers: revision stamping and change serialisation."""

from datetime import date, time, datetime
from decimal import Decimal

from .extensions import db
from .models import SyncState


def stamp_revision(instance):
    """Bump the global revision and stamp it on a model instance."""
    rev = SyncState.bump()
    instance.sync_revision = rev
    return rev


def serialize_date(val):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, time):
        return val.isoformat()
    return str(val)


def serialize_value(val):
    if val is None:
        return None
    if isinstance(val, (datetime, date, time)):
        return serialize_date(val)
    if isinstance(val, Decimal):
        return float(val)
    return val


def flight_to_dict(flight):
    return {
        "id": flight.id,
        "status": flight.status,
        "trip_name": flight.trip_name,
        "trip_id": flight.trip_id,
        "trip_type": flight.trip_type,
        "trip_leg_id": flight.trip_leg_id,
        "activity_id": flight.activity_id,
        "activity_cost": serialize_value(flight.activity_cost),
        "url": flight.url,
        "booking_site": flight.booking_site,
        "supplier_confirmation": flight.supplier_confirmation,
        "booking_date": serialize_date(flight.booking_date),
        "booking_site_phone": flight.booking_site_phone,
        "traveller": flight.traveller,
        "ticket_number": flight.ticket_number,
        "airline_code": flight.airline_code,
        "operating_airline_code": flight.operating_airline_code,
        "aircraft": flight.aircraft,
        "aircraft_type_normalized": flight.aircraft_type_normalized,
        "aircraft_registration": flight.aircraft_registration,
        "service_class": flight.service_class,
        "flight_number": flight.flight_number,
        "operating_flight_number": flight.operating_flight_number,
        "start_country": flight.start_country,
        "start_city_name": flight.start_city_name,
        "start_airport": flight.start_airport,
        "start_terminal": flight.start_terminal,
        "start_lat": flight.start_lat,
        "start_long": flight.start_long,
        "start_date": serialize_date(flight.start_date),
        "start_time": serialize_date(flight.start_time),
        "end_country": flight.end_country,
        "end_city_name": flight.end_city_name,
        "end_airport": flight.end_airport,
        "end_terminal": flight.end_terminal,
        "end_lat": flight.end_lat,
        "end_long": flight.end_long,
        "end_date": serialize_date(flight.end_date),
        "end_time": serialize_date(flight.end_time),
        "stops": flight.stops,
        "distance": flight.distance,
        "route_direction": flight.route_direction,
        "source_file": flight.source_file,
        "grouping_id": flight.grouping_id,
        "audit_missing_leg_ignored": flight.audit_missing_leg_ignored,
        "follow_up": flight.follow_up,
        "exclude_from_stats": flight.exclude_from_stats,
        "sync_revision": flight.sync_revision,
        "deleted_at": serialize_date(flight.deleted_at),
        "created_at": serialize_date(flight.created_at),
        "updated_at": serialize_date(flight.updated_at),
    }


def trip_to_dict(trip):
    return {
        "id": trip.id,
        "name": trip.name,
        "trip_code": trip.trip_code,
        "trip_type": trip.trip_type,
        "notes": trip.notes,
        "start_date": serialize_date(trip.start_date),
        "start_date_precision": trip.start_date_precision,
        "start_date_year": trip.start_date_year,
        "start_date_month": trip.start_date_month,
        "start_date_day": trip.start_date_day,
        "end_date": serialize_date(trip.end_date),
        "end_date_precision": trip.end_date_precision,
        "end_date_year": trip.end_date_year,
        "end_date_month": trip.end_date_month,
        "end_date_day": trip.end_date_day,
        "sync_revision": trip.sync_revision,
        "deleted_at": serialize_date(trip.deleted_at),
        "created_at": serialize_date(trip.created_at),
        "updated_at": serialize_date(trip.updated_at),
    }


def trip_leg_to_dict(leg):
    return {
        "id": leg.id,
        "trip_id": leg.trip_id,
        "sequence": leg.sequence,
        "mode": leg.mode,
        "carrier_name": leg.carrier_name,
        "carrier_code": leg.carrier_code,
        "service_class": leg.service_class,
        "flight_number": leg.flight_number,
        "aircraft_type": leg.aircraft_type,
        "aircraft_registration": leg.aircraft_registration,
        "start_country": leg.start_country,
        "start_city_name": leg.start_city_name,
        "start_airport": leg.start_airport,
        "end_country": leg.end_country,
        "end_city_name": leg.end_city_name,
        "end_airport": leg.end_airport,
        "start_date": serialize_date(leg.start_date),
        "start_date_precision": leg.start_date_precision,
        "start_date_year": leg.start_date_year,
        "start_date_month": leg.start_date_month,
        "start_date_day": leg.start_date_day,
        "end_date": serialize_date(leg.end_date),
        "end_date_precision": leg.end_date_precision,
        "end_date_year": leg.end_date_year,
        "end_date_month": leg.end_date_month,
        "end_date_day": leg.end_date_day,
        "notes": leg.notes,
        "sync_revision": leg.sync_revision,
        "deleted_at": serialize_date(leg.deleted_at),
        "created_at": serialize_date(leg.created_at),
        "updated_at": serialize_date(leg.updated_at),
    }


def aircraft_to_dict(ac):
    return {
        "id": ac.id,
        "registration": ac.registration,
        "type": ac.type,
        "icao_type": ac.icao_type,
        "manufacturer": ac.manufacturer,
        "mode_s": ac.mode_s,
        "registered_owner_country_iso_name": ac.registered_owner_country_iso_name,
        "registered_owner_country_name": ac.registered_owner_country_name,
        "registered_owner_operator_flag_code": ac.registered_owner_operator_flag_code,
        "registered_owner": ac.registered_owner,
        "url_photo": ac.url_photo,
        "url_photo_thumbnail": ac.url_photo_thumbnail,
        "source_url": ac.source_url,
        "sync_revision": ac.sync_revision,
        "created_at": serialize_date(ac.created_at),
        "updated_at": serialize_date(ac.updated_at),
    }


def badge_to_dict(badge):
    return {
        "id": badge.id,
        "name": badge.name,
        "description": badge.description,
        "category": badge.category,
        "badge_type": badge.badge_type,
        "threshold_value": badge.threshold_value,
        "icon_emoji": badge.icon_emoji,
        "icon_url": badge.icon_url,
        "display_order": badge.display_order,
        "is_active": badge.is_active,
        "sync_revision": badge.sync_revision,
        "created_at": serialize_date(badge.created_at),
        "updated_at": serialize_date(badge.updated_at),
    }
