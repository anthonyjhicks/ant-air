"""One rule for duplicate flight groups.

Flights that share a ``grouping_id`` are the same flight recorded more than
once (TripIt export, BA Flightpath export, boarding-pass scan, manual entry).
Grouping is a soft merge: every row stays, but the group must be reported as
one flight everywhere: dashboards, statistics, lists, search, the MCP server,
the REST API and the iOS app.

The member that represents a group is its *primary*: the newest member, that
is the latest ``start_date`` with the highest ``id`` as tie-breaker. The other
members must not be counted, summed or listed unless a caller explicitly asks
for group members (the flight list and the audit pages do).

``is_group_primary`` expresses the rule in SQL for queries and aggregates;
``group_primary`` and ``group_sort_key`` apply the same rule to loaded rows
(see ``merged_flights_for_reporting`` in analytics, and ``FlightReporting``
in the iOS app).
"""

from collections import defaultdict
from datetime import date

from sqlalchemy import String, and_, cast, exists, func, or_, select
from sqlalchemy.orm import aliased

from ..models import Flight

ACTIVE_FLIGHT_FILTERS = (Flight.deleted_at.is_(None),)
APPROVED_FLIGHT_FILTERS = ACTIVE_FLIGHT_FILTERS + (Flight.status == "approved",)
REPORTABLE_FLIGHT_FILTERS = APPROVED_FLIGHT_FILTERS + (
    Flight.exclude_from_stats.is_(False),
)

# Fields a group's primary may take from an older member when its own value is
# blank. Shared by the reporting blend and the grouping backfill.
GROUP_FILL_FIELDS = (
    "trip_name",
    "trip_id",
    "trip_type",
    "activity_id",
    "activity_cost",
    "url",
    "booking_site",
    "supplier_confirmation",
    "booking_date",
    "booking_site_phone",
    "traveller",
    "ticket_number",
    "airline_code",
    "aircraft",
    "aircraft_type_normalized",
    "service_class",
    "flight_number",
    "start_country",
    "start_city_name",
    "start_airport",
    "start_terminal",
    "start_lat",
    "start_long",
    "start_date",
    "start_time",
    "end_country",
    "end_city_name",
    "end_airport",
    "end_terminal",
    "end_lat",
    "end_long",
    "end_date",
    "end_time",
    "stops",
    "route_direction",
    "distance",
    "aircraft_registration",
)


def is_blank_value(value):
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def group_sort_key(flight):
    """Sort key that orders group members oldest to newest."""
    return (flight.start_date or date.min, flight.id or 0)


def group_primary(flights):
    """The member that represents a group of loaded rows: newest wins."""
    return max(flights, key=group_sort_key)


def has_grouping_id(entity=Flight):
    return and_(entity.grouping_id.isnot(None), entity.grouping_id != "")


def primary_flight_ids(filters=APPROVED_FLIGHT_FILTERS):
    """SELECT of the ids that are the primary of their group.

    ``filters`` decide which rows compete for primary; by default active,
    approved flights. Rows without a grouping_id form a group of one.
    """
    group_key = func.coalesce(
        func.nullif(Flight.grouping_id, ""), cast(Flight.id, String)
    )
    ranked = (
        select(
            Flight.id.label("flight_id"),
            func.row_number()
            .over(
                partition_by=group_key,
                order_by=(Flight.start_date.desc(), Flight.id.desc()),
            )
            .label("group_rank"),
        )
        .where(*filters)
        .subquery("ranked_flights")
    )
    return select(ranked.c.flight_id).where(ranked.c.group_rank == 1)


def is_group_primary(filters=APPROVED_FLIGHT_FILTERS):
    """Criterion: the row is the primary of its group (see primary_flight_ids)."""
    return Flight.id.in_(primary_flight_ids(filters))


def reporting_flights_query():
    """Flights that count in statistics: approved, active, not excluded, one per group."""
    return Flight.query.filter(*REPORTABLE_FLIGHT_FILTERS).filter(is_group_primary())


def matches_flight_or_group_member(criterion_for):
    """Criterion that holds when the flight, or any active member of its group, matches.

    ``criterion_for(entity)`` builds the criterion for a Flight entity or alias,
    so a search for a ticket number stored only on an older duplicate still
    finds the group's primary.
    """
    member = aliased(Flight, name="group_member")
    member_matches = exists().where(
        member.grouping_id == Flight.grouping_id,
        member.id != Flight.id,
        member.deleted_at.is_(None),
        criterion_for(member),
    )
    return or_(criterion_for(Flight), and_(has_grouping_id(), member_matches))


def approved_group_members(grouping_id):
    """All approved, active rows of a group, newest first (the primary comes first)."""
    if not grouping_id:
        return []
    return (
        Flight.query.filter(Flight.grouping_id == grouping_id, *APPROVED_FLIGHT_FILTERS)
        .order_by(Flight.start_date.desc(), Flight.id.desc())
        .all()
    )


def group_info(flight, members=None):
    """Describe a flight's group for API payloads; None when the flight is not grouped."""
    if not flight.grouping_id:
        return None
    if members is None:
        members = approved_group_members(flight.grouping_id)
    member_ids = [member.id for member in members]
    primary_id = member_ids[0] if member_ids else flight.id
    return {
        "grouping_id": flight.grouping_id,
        "primary_id": primary_id,
        "is_primary": flight.id == primary_id,
        "member_ids": member_ids,
    }


def group_info_by_flight(flights):
    """``group_info`` for many rows with one query for all their groups."""
    grouping_ids = {flight.grouping_id for flight in flights if flight.grouping_id}
    members_by_group = defaultdict(list)
    if grouping_ids:
        members = (
            Flight.query.filter(
                Flight.grouping_id.in_(grouping_ids), *APPROVED_FLIGHT_FILTERS
            )
            .order_by(Flight.start_date.desc(), Flight.id.desc())
            .all()
        )
        for member in members:
            members_by_group[member.grouping_id].append(member)
    return {
        flight.id: group_info(flight, members_by_group.get(flight.grouping_id, []))
        for flight in flights
    }


def fill_blank_fields_from_group(primary, members):
    """Persistently copy values for blank fields on a primary from its other members.

    Members are consulted newest first. Returns the names of the fields filled.
    Used when a grouping is confirmed, so the record that now represents the
    group carries every detail the older records had.
    """
    ordered = sorted(
        (member for member in members if member.id != primary.id),
        key=group_sort_key,
        reverse=True,
    )
    filled = []
    for attr in GROUP_FILL_FIELDS:
        if not is_blank_value(getattr(primary, attr)):
            continue
        for member in ordered:
            value = getattr(member, attr)
            if not is_blank_value(value):
                setattr(primary, attr, value)
                filled.append(attr)
                break
    return filled
