import math

from .distance import haversine_miles
from ..extensions import db
from ..models import Flight


def compute_distance(start_lat, start_long, end_lat, end_long):
    return haversine_miles(start_lat, start_long, end_lat, end_long)


def compute_route_direction(start_lat, start_long, end_lat, end_long):
    def parse_number(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    start_lon = parse_number(start_long)
    end_lon = parse_number(end_long)
    if start_lon is None or end_lon is None:
        return None
    if not math.isfinite(start_lon) or not math.isfinite(end_lon):
        return None

    east_degrees = (end_lon - start_lon) % 360
    west_degrees = (start_lon - end_lon) % 360
    if east_degrees == 0 or west_degrees == 0:
        return None

    start_lat_val = parse_number(start_lat)
    end_lat_val = parse_number(end_lat)
    if start_lat_val is None or end_lat_val is None:
        if east_degrees == west_degrees:
            return None
        return "east" if east_degrees < west_degrees else "west"

    if not math.isfinite(start_lat_val) or not math.isfinite(end_lat_val):
        if east_degrees == west_degrees:
            return None
        return "east" if east_degrees < west_degrees else "west"

    radius_miles = 3958.7613
    lat1_rad = math.radians(start_lat_val)
    lat2_rad = math.radians(end_lat_val)
    dlat = lat2_rad - lat1_rad

    def rhumb_distance(delta_degrees):
        dlon = math.radians(delta_degrees)
        try:
            dpsi = math.log(
                math.tan(math.pi / 4 + lat2_rad / 2)
                / math.tan(math.pi / 4 + lat1_rad / 2)
            )
        except (ValueError, ZeroDivisionError):
            return None
        if not math.isfinite(dpsi):
            return None
        if abs(dpsi) > 1e-12:
            q = dlat / dpsi
        else:
            q = math.cos(lat1_rad)
        return radius_miles * math.sqrt(dlat**2 + (q * dlon) ** 2)

    east_distance = rhumb_distance(east_degrees)
    west_distance = rhumb_distance(west_degrees)
    if east_distance is None or west_distance is None:
        if east_degrees == west_degrees:
            return None
        return "east" if east_degrees < west_degrees else "west"

    if math.isclose(east_distance, west_distance, rel_tol=1e-6, abs_tol=1e-6):
        return None
    return "east" if east_distance < west_distance else "west"


def create_flight_from_row(row):
    flight = Flight(
        trip_name=row.get("trip_name"),
        trip_id=row.get("trip_id"),
        trip_type=row.get("trip_type"),
        activity_id=row.get("activity_id"),
        activity_cost=row.get("activity_cost"),
        url=row.get("url"),
        booking_site=row.get("booking_site"),
        supplier_confirmation=row.get("supplier_confirmation"),
        booking_date=row.get("booking_date"),
        booking_site_phone=row.get("booking_site_phone"),
        traveller=row.get("traveller"),
        ticket_number=row.get("ticket_number"),
        airline_code=row.get("airline_code"),
        aircraft=row.get("aircraft"),
        service_class=row.get("service_class"),
        flight_number=row.get("flight_number"),
        start_country=row.get("start_country"),
        start_city_name=row.get("start_city_name"),
        start_airport=row.get("start_airport"),
        start_terminal=row.get("start_terminal"),
        start_lat=row.get("start_lat"),
        start_long=row.get("start_long"),
        start_date=row.get("start_date"),
        start_time=row.get("start_time"),
        end_country=row.get("end_country"),
        end_city_name=row.get("end_city_name"),
        end_airport=row.get("end_airport"),
        end_terminal=row.get("end_terminal"),
        end_lat=row.get("end_lat"),
        end_long=row.get("end_long"),
        end_date=row.get("end_date"),
        end_time=row.get("end_time"),
        stops=row.get("stops"),
        distance=row.get("distance"),
        route_direction=compute_route_direction(
            row.get("start_lat"),
            row.get("start_long"),
            row.get("end_lat"),
            row.get("end_long"),
        ),
        source_file=row.get("source_file"),
    )
    if flight.distance is None:
        flight.distance = compute_distance(
            flight.start_lat, flight.start_long, flight.end_lat, flight.end_long
        )
    return flight


def import_rows(rows, status=None):
    imported = 0
    for row in rows:
        flight = create_flight_from_row(row)
        if status:
            flight.status = status
        db.session.add(flight)
        imported += 1
    db.session.commit()
    return imported
