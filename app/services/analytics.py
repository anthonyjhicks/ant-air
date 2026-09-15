import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from copy import deepcopy

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm.attributes import set_committed_value

from .flight_groups import GROUP_FILL_FIELDS, group_sort_key


def normalize_key(value):
    if value is None:
        return None
    if isinstance(value, str):
        normalized = " ".join(value.strip().lower().split())
        return normalized or None
    return value


AIRLINE_CODE_PATTERN = re.compile(r"^[A-Z0-9]{2,3}$")
FLIGHT_NUMBER_PATTERN = re.compile(r"^([A-Z]{2,3})?0*([0-9]{1,5})$")


def normalize_airline_code(value):
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().upper()
        return normalized or None
    return value


def extract_flight_number_parts(value):
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, value

    compact = "".join(value.strip().upper().split())
    if not compact:
        return None, None

    match = FLIGHT_NUMBER_PATTERN.match(compact)
    if match:
        return match.group(1), match.group(2)

    if compact.isdigit():
        return None, compact.lstrip("0") or "0"

    return None, compact


def resolve_airline_code(airline_code, flight_number):
    normalized = normalize_airline_code(airline_code)
    if normalized:
        return normalized
    extracted_code, _ = extract_flight_number_parts(flight_number)
    return normalize_airline_code(extracted_code)


DEFAULT_DUPLICATE_MATCH_RULES = {
    "threshold": 8,
    "primary_match_threshold": 8,
    "primary_match_signals": [
        "route",
        "flight_number",
        "supplier_confirmation",
        "ticket_number",
    ],
    "date_window_days": 0,
    "time_window_minutes": 120,
    "show_reasons": False,
    "blocking_keys": [
        "flight_number",
        "route",
        "city",
        "trip_id",
        "supplier_confirmation",
        "ticket_number",
    ],
    "signals": {
        "flight_number": 10,
        "route": 6,
        "city": 4,
        "trip_id": 4,
        "trip_name": 3,
        "supplier_confirmation": 5,
        "ticket_number": 4,
        "booking_site": 1,
        "traveller": 1,
        "service_class": 1,
        "start_time_window": 1,
    },
}


def _merge_rules(base, overrides):
    if not overrides:
        return base
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _merge_rules(base.get(key, {}), value)
        else:
            base[key] = value
    return base


def resolve_duplicate_rules(overrides=None):
    merged = deepcopy(DEFAULT_DUPLICATE_MATCH_RULES)
    if overrides:
        merged = _merge_rules(merged, overrides)
    return merged


def flight_dedupe_key(flight):
    airline_code = normalize_airline_code(flight.airline_code)

    extracted_code, extracted_number = extract_flight_number_parts(
        flight.flight_number
    )
    effective_code = airline_code or extracted_code
    effective_number = extracted_number or normalize_key(flight.flight_number)

    if flight.start_date and effective_code and effective_number:
        return (
            "by-number",
            flight.start_date,
            normalize_key(effective_code),
            normalize_key(effective_number),
        )

    return ("no-dedupe", flight.id)


def flight_route_date_key(flight):
    if not flight.start_date:
        return ("no-route-date", flight.id)

    origin = normalize_key(flight.origin_name)
    destination = normalize_key(flight.destination_name)
    if origin and destination:
        return (
            "by-route-date",
            flight.start_date,
            origin,
            destination,
        )

    return ("no-route-date", flight.id)


def flight_city_date_key(flight):
    if not flight.start_date:
        return ("no-city-date", flight.id)

    city = normalize_key(flight.start_city_name) or normalize_key(
        flight.end_city_name
    )
    if city:
        return (
            "by-city-date",
            flight.start_date,
            city,
        )

    return ("no-city-date", flight.id)


def _normalized_token(value):
    if not value:
        return None
    if isinstance(value, str):
        normalized = normalize_key(value)
        return normalized or None
    return value


def is_boarding_pass_source(source_file):
    if not source_file:
        return False
    normalized = normalize_key(str(source_file)) or ""
    return "boarding-pass" in normalized or "boarding pass" in normalized or "boarding_pass" in normalized


def _normalize_airport_code(value):
    if not value:
        return None
    cleaned = str(value).strip().upper()
    return cleaned or None


def _normalize_location_key(airport_code, city_name, country_name):
    airport = _normalize_airport_code(airport_code)
    if airport:
        return ("airport", airport)
    city = _normalized_token(city_name)
    if city:
        return ("city", city)
    country = _normalized_token(country_name)
    if country:
        return ("country", country)
    return None


def group_flights_by_day_month_route(flights, rules=None, require_boarding_pass=True):
    rules = resolve_duplicate_rules(rules)
    threshold = rules.get("threshold", 0) or 1
    groups = defaultdict(list)
    for flight in flights:
        if not flight.start_date:
            continue
        airline_code = resolve_airline_code(flight.airline_code, flight.flight_number)
        _extracted_code, extracted_number = extract_flight_number_parts(
            flight.flight_number
        )
        if not airline_code or not extracted_number:
            continue
        origin_key = _normalize_location_key(
            flight.start_airport, flight.start_city_name, flight.start_country
        )
        destination_key = _normalize_location_key(
            flight.end_airport, flight.end_city_name, flight.end_country
        )
        if not origin_key or not destination_key:
            continue
        key = (
            "by-day-month",
            flight.start_date.month,
            flight.start_date.day,
            normalize_airline_code(airline_code),
            extracted_number,
            origin_key,
            destination_key,
        )
        groups[key].append(flight)

    grouped = []
    for key, items in groups.items():
        if len(items) <= 1:
            continue
        if require_boarding_pass and not any(
            is_boarding_pass_source(item.source_file) for item in items
        ):
            continue
        items_sorted = sorted(
            items,
            key=lambda f: (
                f.start_date or date.min,
                f.id or 0,
            ),
            reverse=True,
        )
        grouped.append(
            {
                "key": key,
                "flights": items_sorted,
                "primary": items_sorted[0],
                "count": len(items_sorted),
                "match_score": threshold,
                "match_reasons": [
                    "Same day/month",
                    "Same flight number",
                    "Same route",
                ],
            }
        )

    grouped.sort(
        key=lambda group: (
            group["primary"].start_date or date.min,
            group["count"],
            group["primary"].id or 0,
        ),
        reverse=True,
    )
    return grouped


def _flight_number_signature(flight):
    extracted_code, extracted_number = extract_flight_number_parts(
        flight.flight_number
    )
    effective_code = normalize_airline_code(flight.airline_code) or normalize_airline_code(
        extracted_code
    )
    effective_number = extracted_number or _normalized_token(flight.flight_number)
    return effective_code, effective_number


def _dates_within_window(left, right, window_days):
    if not left or not right:
        return False
    if window_days <= 0:
        return left == right
    delta_days = abs((left - right).days)
    return delta_days <= window_days


def _times_within_window(left, right, window_minutes):
    if not left or not right or window_minutes <= 0:
        return False
    left_minutes = left.hour * 60 + left.minute
    right_minutes = right.hour * 60 + right.minute
    return abs(left_minutes - right_minutes) <= window_minutes


def _is_same_day_round_trip(left, right):
    if not left.start_date or not right.start_date:
        return False
    if left.start_date != right.start_date:
        return False
    left_origin = _normalized_token(left.origin_name)
    left_dest = _normalized_token(left.destination_name)
    right_origin = _normalized_token(right.origin_name)
    right_dest = _normalized_token(right.destination_name)
    if not (left_origin and left_dest and right_origin and right_dest):
        return False
    return left_origin == right_dest and left_dest == right_origin


def score_duplicate_match(left, right, rules):
    signals = rules.get("signals", {})
    score = 0
    reasons = []
    matched_signals = []

    if not _dates_within_window(
        left.start_date, right.start_date, rules.get("date_window_days", 0)
    ):
        return score, reasons, matched_signals
    if left.end_date and right.end_date and not _dates_within_window(
        left.end_date, right.end_date, rules.get("date_window_days", 0)
    ):
        return score, reasons, matched_signals
    if _is_same_day_round_trip(left, right):
        return score, reasons, matched_signals

    left_code, left_number = _flight_number_signature(left)
    right_code, right_number = _flight_number_signature(right)
    if left_number and right_number and left_number == right_number:
        if not left_code or not right_code or left_code == right_code:
            weight = signals.get("flight_number", 0)
            if weight:
                score += weight
                reasons.append("Same flight number")
                matched_signals.append("flight_number")

    left_origin = _normalized_token(left.origin_name)
    left_dest = _normalized_token(left.destination_name)
    right_origin = _normalized_token(right.origin_name)
    right_dest = _normalized_token(right.destination_name)
    if left_origin and left_dest and left_origin == right_origin and left_dest == right_dest:
        weight = signals.get("route", 0)
        if weight:
            score += weight
            reasons.append("Same route")
            matched_signals.append("route")

    left_start_city = _normalized_token(left.start_city_name)
    left_end_city = _normalized_token(left.end_city_name)
    right_start_city = _normalized_token(right.start_city_name)
    right_end_city = _normalized_token(right.end_city_name)
    same_start_city = left_start_city and right_start_city and left_start_city == right_start_city
    same_end_city = left_end_city and right_end_city and left_end_city == right_end_city
    if same_start_city or same_end_city:
        weight = signals.get("city", 0)
        if weight:
            score += weight
            reasons.append("Same city")
            matched_signals.append("city")

    if _normalized_token(left.trip_id) and _normalized_token(left.trip_id) == _normalized_token(
        right.trip_id
    ):
        weight = signals.get("trip_id", 0)
        if weight:
            score += weight
            reasons.append("Same trip id")
            matched_signals.append("trip_id")

    if _normalized_token(left.trip_name) and _normalized_token(left.trip_name) == _normalized_token(
        right.trip_name
    ):
        weight = signals.get("trip_name", 0)
        if weight:
            score += weight
            reasons.append("Same trip name")
            matched_signals.append("trip_name")

    if _normalized_token(left.supplier_confirmation) and _normalized_token(
        left.supplier_confirmation
    ) == _normalized_token(right.supplier_confirmation):
        weight = signals.get("supplier_confirmation", 0)
        if weight:
            score += weight
            reasons.append("Same supplier confirmation")
            matched_signals.append("supplier_confirmation")

    if _normalized_token(left.ticket_number) and _normalized_token(left.ticket_number) == _normalized_token(
        right.ticket_number
    ):
        weight = signals.get("ticket_number", 0)
        if weight:
            score += weight
            reasons.append("Same ticket number")
            matched_signals.append("ticket_number")

    if _normalized_token(left.booking_site) and _normalized_token(left.booking_site) == _normalized_token(
        right.booking_site
    ):
        weight = signals.get("booking_site", 0)
        if weight:
            score += weight
            reasons.append("Same booking site")
            matched_signals.append("booking_site")

    if _normalized_token(left.traveller) and _normalized_token(left.traveller) == _normalized_token(
        right.traveller
    ):
        weight = signals.get("traveller", 0)
        if weight:
            score += weight
            reasons.append("Same traveller")
            matched_signals.append("traveller")

    if _normalized_token(left.service_class) and _normalized_token(left.service_class) == _normalized_token(
        right.service_class
    ):
        weight = signals.get("service_class", 0)
        if weight:
            score += weight
            reasons.append("Same service class")
            matched_signals.append("service_class")

    if _times_within_window(
        left.start_time,
        right.start_time,
        rules.get("time_window_minutes", 0),
    ):
        weight = signals.get("start_time_window", 0)
        if weight:
            score += weight
            reasons.append("Start time within window")
            matched_signals.append("start_time_window")

    return score, reasons, matched_signals


def _blocking_keys_for_flight(flight, rules):
    configured = set(rules.get("blocking_keys", []))
    keys = []

    if flight.start_date and ("flight_number" in configured or not configured):
        code, number = _flight_number_signature(flight)
        if number:
            keys.append(("flight_number", flight.start_date, code, number))

    if flight.start_date and ("route" in configured or not configured):
        origin = _normalized_token(flight.origin_name)
        destination = _normalized_token(flight.destination_name)
        if origin and destination:
            keys.append(("route", flight.start_date, origin, destination))

    if flight.start_date and ("city" in configured or not configured):
        start_city = _normalized_token(flight.start_city_name)
        end_city = _normalized_token(flight.end_city_name)
        if start_city:
            keys.append(("city_start", flight.start_date, start_city))
        if end_city:
            keys.append(("city_end", flight.start_date, end_city))

    if "trip_id" in configured or not configured:
        trip_id = _normalized_token(flight.trip_id)
        if trip_id:
            keys.append(("trip_id", trip_id))

    if "supplier_confirmation" in configured or not configured:
        supplier_confirmation = _normalized_token(flight.supplier_confirmation)
        if supplier_confirmation:
            keys.append(("supplier_confirmation", supplier_confirmation))

    if "ticket_number" in configured or not configured:
        ticket_number = _normalized_token(flight.ticket_number)
        if ticket_number:
            keys.append(("ticket_number", ticket_number))

    if not keys and flight.start_date:
        keys.append(("date", flight.start_date))

    return keys


def _candidate_pairs(flights, rules):
    buckets = defaultdict(list)
    for idx, flight in enumerate(flights):
        for key in _blocking_keys_for_flight(flight, rules):
            buckets[key].append(idx)

    pairs = set()
    for indexes in buckets.values():
        if len(indexes) < 2:
            continue
        for i, left in enumerate(indexes[:-1]):
            for right in indexes[i + 1 :]:
                pairs.add((left, right) if left < right else (right, left))
    return pairs


def _set_display_value(target, attr, value):
    """Set a value on a loaded row for display only, without marking it dirty.

    Reporting shows a group's primary with blanks filled from an older member.
    Writing that through ``setattr`` would make the ORM persist member data the
    next time anything in the request commits (the insights cache does), so
    rows loaded from the database get the value via ``set_committed_value``.
    """
    state = sa_inspect(target, raiseerr=False)
    if state is not None and state.persistent:
        set_committed_value(target, attr, value)
    else:
        setattr(target, attr, value)


def merge_flight_report_data(target, source):
    for attr in (
        "distance",
        "start_country",
        "end_country",
    ):
        if getattr(target, attr) is None and getattr(source, attr) is not None:
            _set_display_value(target, attr, getattr(source, attr))
    return target


REPORTING_MERGE_FIELDS = GROUP_FILL_FIELDS


def merge_flight_reporting_data(target, source):
    def is_empty(value):
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ""
        return False

    for attr in REPORTING_MERGE_FIELDS:
        if is_empty(getattr(target, attr)) and not is_empty(getattr(source, attr)):
            _set_display_value(target, attr, getattr(source, attr))
    return target


def dedupe_flights(flights):
    merged = {}
    for flight in flights:
        key = flight_dedupe_key(flight)
        if key in merged:
            merge_flight_report_data(merged[key], flight)
            continue
        merged[key] = flight
    return list(merged.values())


def merged_flights_for_reporting(flights):
    """Collapse duplicate groups to one flight each: newest wins.

    Flights sharing a ``grouping_id`` are one flight recorded more than once.
    The group's primary is its newest member (latest start_date, highest id),
    the same rule ``flight_groups.is_group_primary`` applies in SQL. A group
    whose primary is excluded from stats is left out, as is an excluded single.

    Blank fields on the primary are shown with a member's value for display
    only; the ORM rows are not modified (see ``_set_display_value``).
    """
    groups = defaultdict(list)
    for flight in flights:
        if flight.grouping_id:
            key = ("group", flight.grouping_id)
        else:
            key = ("single", flight.id)
        groups[key].append(flight)

    merged = []
    for items in groups.values():
        items_sorted = sorted(items, key=group_sort_key, reverse=True)
        primary = items_sorted[0]
        if getattr(primary, "exclude_from_stats", False):
            continue
        for source in items_sorted[1:]:
            merge_flight_reporting_data(primary, source)
        merged.append(primary)

    merged.sort(key=group_sort_key, reverse=True)
    return merged


def group_flights_by_dedupe_key(flights):
    groups = defaultdict(list)
    for flight in flights:
        groups[flight_dedupe_key(flight)].append(flight)

    grouped = []
    for key, items in groups.items():
        items_sorted = sorted(
            items,
            key=lambda f: (
                f.start_date or date.min,
                f.id or 0,
            ),
            reverse=True,
        )
        grouped.append(
            {
                "key": key,
                "flights": items_sorted,
                "primary": items_sorted[0],
                "count": len(items_sorted),
            }
        )

    grouped.sort(
        key=lambda group: (
            group["primary"].start_date or date.min,
            group["count"],
            group["primary"].id or 0,
        ),
        reverse=True,
    )
    return grouped


def group_flights_by_route_date(flights):
    groups = defaultdict(list)
    for flight in flights:
        groups[flight_route_date_key(flight)].append(flight)

    grouped = []
    for key, items in groups.items():
        items_sorted = sorted(
            items,
            key=lambda f: (
                f.start_date or date.min,
                f.id or 0,
            ),
            reverse=True,
        )
        grouped.append(
            {
                "key": key,
                "flights": items_sorted,
                "primary": items_sorted[0],
                "count": len(items_sorted),
            }
        )

    grouped.sort(
        key=lambda group: (
            group["primary"].start_date or date.min,
            group["count"],
            group["primary"].id or 0,
        ),
        reverse=True,
    )
    return grouped


def build_missing_leg_audit(
    flights,
    window_days=30,
    include_ungrouped=False,
    home_city=None,
    home_airports=None,
):
    """Find outbound flights from the home base without a return leg.

    The home base comes from ``HOME_CITY`` / ``HOME_AIRPORTS`` unless passed
    explicitly. With no home base configured nothing can be flagged.
    """
    from .personalisation import home_airports as _home_airports
    from .personalisation import home_city as _home_city

    if home_city is None:
        home_city = _home_city()
    if home_airports is None:
        home_airports = _home_airports()
    home_key = normalize_key(home_city or "")
    home_codes = {str(code).strip().upper() for code in (home_airports or []) if code}
    home_name = home_city or (sorted(home_codes)[0] if home_codes else "home")

    def is_empty(value):
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ""
        return False

    def group_label(flight):
        traveller_key = normalize_key(flight.traveller) or "unknown"
        trip_leg = getattr(flight, "trip_leg", None)
        if trip_leg and getattr(trip_leg, "trip", None):
            trip = trip_leg.trip
            if getattr(trip, "trip_code", None):
                return (f"Trip ID: {trip.trip_code}", True)
            if getattr(trip, "name", None):
                return (f"Trip: {trip.name}", True)
            if getattr(trip, "id", None):
                return (f"Trip #{trip.id}", True)
        if not is_empty(flight.trip_id):
            raw = str(flight.trip_id).strip()
            return (
                f"Trip ID: {raw}",
                True,
            )
        if not is_empty(flight.supplier_confirmation):
            raw = str(flight.supplier_confirmation).strip()
            return (
                f"Supplier confirmation: {raw}",
                True,
            )
        if not is_empty(flight.ticket_number):
            raw = str(flight.ticket_number).strip()
            return (
                f"Ticket: {raw}",
                True,
            )
        if not is_empty(flight.trip_name):
            raw = str(flight.trip_name).strip()
            return (
                f"Trip: {raw}",
                True,
            )
        return ("Unassigned trip", False)

    def sort_key(flight):
        return (flight.start_date or date.min, flight.id or 0)

    def is_base(name, airport_code=None):
        code = (airport_code or "").strip().upper()
        if code and code in home_codes:
            return True
        normalized = normalize_key(name or "")
        return bool(home_key and normalized and home_key in normalized)

    def is_outbound(flight):
        return is_base(flight.origin_name, flight.start_airport) and not is_base(
            flight.destination_name, flight.end_airport
        )

    def is_inbound(flight):
        return is_base(flight.destination_name, flight.end_airport) and not is_base(
            flight.origin_name, flight.start_airport
        )

    def normalize_country(value):
        return normalize_key(value)

    def same_country(outbound_flight, inbound_flight):
        outbound_country = normalize_country(outbound_flight.end_country)
        inbound_country = normalize_country(inbound_flight.start_country)
        if outbound_country and inbound_country:
            return outbound_country == inbound_country
        return False

    grouped = defaultdict(list)
    label_lookup = {}
    traveller_lookup = {}
    for flight in flights:
        if getattr(flight, "audit_missing_leg_ignored", False):
            continue
        label, has_group = group_label(flight)
        if not has_group and not include_ungrouped:
            continue
        traveller_key = normalize_key(flight.traveller) or "unknown"
        grouped[traveller_key].append(flight)
        label_lookup[flight.id] = label
        traveller_lookup[traveller_key] = flight.traveller or "Unknown"

    missing_entries = []
    for traveller_key, traveller_flights in grouped.items():
        sorted_flights = sorted(traveller_flights, key=sort_key)
        total_flights = len(sorted_flights)
        for idx, flight in enumerate(sorted_flights):
            if not is_outbound(flight) or not flight.start_date:
                continue
            cutoff_date = flight.start_date + timedelta(days=window_days)
            return_flight = None
            for check_idx in range(idx + 1, total_flights):
                candidate = sorted_flights[check_idx]
                if not candidate.start_date:
                    continue
                if candidate.start_date < flight.start_date:
                    continue
                if candidate.start_date > cutoff_date:
                    break
                if is_inbound(candidate) and same_country(flight, candidate):
                    return_flight = candidate
                    break

            if return_flight:
                continue

            thread_flights = []
            for check_idx in range(idx + 1, total_flights):
                candidate = sorted_flights[check_idx]
                if candidate.start_date and candidate.start_date > cutoff_date:
                    break
                thread_flights.append(candidate)

            destination = flight.destination_name or "Unknown"
            missing_entries.append(
                {
                    "flight": flight,
                    "group_key": traveller_key,
                    "group_label": label_lookup.get(flight.id, "Unknown"),
                    "reverse_route": f"{destination} → {home_name}",
                    "thread_flights": thread_flights,
                    "traveller_label": traveller_lookup.get(traveller_key, "Unknown"),
                }
            )

    missing_entries.sort(key=lambda item: sort_key(item["flight"]), reverse=True)
    summary = {
        "total_missing": len(missing_entries),
        "total_groups": len({entry["group_key"] for entry in missing_entries}),
        "total_flights": len(flights),
    }
    return missing_entries, summary


def group_flights_by_audit_key(flights):
    rules = resolve_duplicate_rules()
    return group_flights_by_match_score(flights, rules)


def _has_primary_match_requirements(rules):
    return rules.get("primary_match_threshold") is not None or bool(
        rules.get("primary_match_signals")
    )


def _passes_primary_match_gate(primary, candidate, rules):
    if primary.id == candidate.id:
        return True
    score, _reasons, matched = score_duplicate_match(primary, candidate, rules)
    threshold = rules.get("primary_match_threshold")
    required_signals = rules.get("primary_match_signals", [])
    if threshold is not None and score < threshold:
        return False
    if required_signals:
        matched_set = set(matched)
        if not any(signal in matched_set for signal in required_signals):
            return False
    return True


def _build_group_summary(items_sorted, rules):
    primary = items_sorted[0]
    scores = []
    reasons = Counter()
    for flight in items_sorted[1:]:
        score, flight_reasons, _matched = score_duplicate_match(primary, flight, rules)
        if score:
            scores.append(score)
        for reason in flight_reasons:
            reasons[reason] += 1
    return {
        "key": flight_dedupe_key(primary),
        "flights": items_sorted,
        "primary": primary,
        "count": len(items_sorted),
        "match_score": max(scores) if scores else None,
        "match_reasons": [reason for reason, _ in reasons.most_common()]
        if reasons
        else [],
    }


def _split_group_by_primary_gate(items_sorted, rules):
    subgroups = []
    for flight in items_sorted:
        placed = False
        for subgroup in subgroups:
            if _passes_primary_match_gate(subgroup["primary"], flight, rules):
                subgroup["flights"].append(flight)
                placed = True
                break
        if not placed:
            subgroups.append(
                {
                    "primary": flight,
                    "flights": [flight],
                }
            )
    return subgroups


def group_flights_by_match_score(flights, rules):
    rules = resolve_duplicate_rules(rules)
    threshold = rules.get("threshold", 0)
    parents = list(range(len(flights)))
    pair_matches = []

    def find(idx):
        while parents[idx] != idx:
            parents[idx] = parents[parents[idx]]
            idx = parents[idx]
        return idx

    def union(left, right):
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parents[root_right] = root_left

    for left, right in _candidate_pairs(flights, rules):
        score, reasons, _matched = score_duplicate_match(
            flights[left], flights[right], rules
        )
        if score >= threshold:
            union(left, right)
            pair_matches.append((left, right, score, reasons))

    groups = defaultdict(list)
    for idx, flight in enumerate(flights):
        groups[find(idx)].append(flight)

    group_meta = defaultdict(lambda: {"scores": [], "reasons": Counter()})
    for left, right, score, reasons in pair_matches:
        root = find(left)
        group_meta[root]["scores"].append(score)
        for reason in reasons:
            group_meta[root]["reasons"][reason] += 1

    grouped = []
    for root, items in groups.items():
        items_sorted = sorted(
            items,
            key=lambda f: (
                f.start_date or date.min,
                f.id or 0,
            ),
            reverse=True,
        )
        meta = group_meta.get(root, {})
        scores = meta.get("scores", [])
        reasons = meta.get("reasons", {})
        grouped.append(
            {
                "key": flight_dedupe_key(items_sorted[0]),
                "flights": items_sorted,
                "primary": items_sorted[0],
                "count": len(items_sorted),
                "match_score": max(scores) if scores else None,
                "match_reasons": [
                    reason for reason, _ in reasons.most_common()
                ]
                if reasons
                else [],
            }
        )

    if _has_primary_match_requirements(rules):
        gated_groups = []
        for group in grouped:
            subgroups = _split_group_by_primary_gate(group["flights"], rules)
            for subgroup in subgroups:
                subgroup_sorted = sorted(
                    subgroup["flights"],
                    key=lambda f: (
                        f.start_date or date.min,
                        f.id or 0,
                    ),
                    reverse=True,
                )
                gated_groups.append(_build_group_summary(subgroup_sorted, rules))
        grouped = gated_groups

    grouped.sort(
        key=lambda group: (
            group["primary"].start_date or date.min,
            group["count"],
            group["primary"].id or 0,
        ),
        reverse=True,
    )
    return grouped


def extract_country(location_name):
    if not location_name:
        return None
    if "(" in location_name and ")" in location_name:
        country = location_name.split("(", 1)[1].split(")", 1)[0].strip()
        return country or None
    if "," in location_name:
        country = location_name.split(",")[-1].strip()
        return country or None
    return None


COUNTRY_NAME_OVERRIDES = {
    "usa": "United States",
    "u.s.a.": "United States",
    "u.s.a": "United States",
    "u.s.": "United States",
    "us": "United States",
    "united states of america": "United States",
}


def normalize_country_label(value):
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = normalize_key(text) or ""
    if normalized in COUNTRY_NAME_OVERRIDES:
        return COUNTRY_NAME_OVERRIDES[normalized]
    return text


def summarize_flights(flights, home_city=None, home_country=None):
    """Aggregate statistics for the dashboard, API and MCP server.

    ``home_city`` / ``home_country`` (default: ``HOME_CITY`` / ``HOME_COUNTRY``)
    are skipped when picking the top destination so the home base does not
    dominate the cards.
    """
    from .personalisation import home_city as _home_city
    from .personalisation import home_country as _home_country

    if home_city is None:
        home_city = _home_city()
    if home_country is None:
        home_country = _home_country()
    total_flights = len(flights)
    total_miles = round(
        sum(f.distance or 0 for f in flights),
        2,
    )

    top_cities = Counter()
    top_routes = Counter()
    city_labels = defaultdict(Counter)
    route_labels = defaultdict(Counter)
    top_countries = Counter()
    top_airlines = Counter()
    top_aircrafts = Counter()
    aircraft_labels = defaultdict(Counter)
    top_tailnumbers = Counter()
    tailnumber_labels = defaultdict(Counter)
    aircraft_miles = defaultdict(float)
    monthly = defaultdict(int)
    monthly_miles = defaultdict(float)
    yearly = defaultdict(int)
    yearly_miles = defaultdict(float)
    yearly_co2 = defaultdict(float)

    for flight in flights:
        origin_name = flight.origin_name
        destination_name = flight.destination_name
        origin_key = normalize_key(origin_name) or "unknown"
        destination_key = normalize_key(destination_name) or "unknown"
        route_key = (origin_key, destination_key)

        destination_label = destination_name or "Unknown"
        route_label = f"{origin_name} → {destination_name}"

        top_cities[destination_key] += 1
        city_labels[destination_key][destination_label] += 1
        top_routes[route_key] += 1
        route_labels[route_key][route_label] += 1

        destination_country = normalize_country_label(
            flight.end_country or extract_country(destination_name)
        ) or "Unknown"
        top_countries[destination_country] += 1

        airline_code = resolve_airline_code(flight.airline_code, flight.flight_number)
        top_airlines[airline_code or "Unknown"] += 1

        aircraft_label = (flight.aircraft_type_normalized or "").strip() or "Unknown"
        aircraft_key = normalize_key(aircraft_label) or "unknown"
        top_aircrafts[aircraft_key] += 1
        aircraft_labels[aircraft_key][aircraft_label] += 1
        aircraft_miles[aircraft_key] += flight.distance or 0

        tailnumber_label = (flight.aircraft_registration or "").strip().upper()
        tailnumber_label = tailnumber_label or "Unknown"
        tailnumber_key = normalize_key(tailnumber_label) or "unknown"
        top_tailnumbers[tailnumber_key] += 1
        tailnumber_labels[tailnumber_key][tailnumber_label] += 1

        month_key = flight.start_date.strftime("%Y-%m")
        monthly[month_key] += 1
        monthly_miles[month_key] += flight.distance or 0

        year_key = flight.start_date.year
        yearly[year_key] += 1
        yearly_miles[year_key] += flight.distance or 0

        co2_kg = (flight.distance or 0) * 1.60934 * 0.255
        yearly_co2[year_key] += co2_kg

    top_cities_data = [
        (
            (city_labels[key].most_common(1)[0][0] if city_labels[key] else "Unknown"),
            count,
        )
        for key, count in top_cities.most_common()
    ]
    top_routes_data = [
        (
            (
                route_labels[key].most_common(1)[0][0]
                if route_labels[key]
                else f"{key[0]} → {key[1]}"
            ),
            count,
        )
        for key, count in top_routes.most_common()
    ]
    top_countries_data = top_countries.most_common()
    top_airlines_data = top_airlines.most_common()
    def aircraft_display_label(key):
        return (
            aircraft_labels[key].most_common(1)[0][0] if aircraft_labels[key] else "Unknown"
        )

    top_aircrafts_data = [
        (aircraft_display_label(key), count)
        for key, count in top_aircrafts.most_common()
    ]
    top_aircraft_miles_data = [
        (aircraft_display_label(key), round(miles, 2))
        for key, miles in sorted(
            aircraft_miles.items(),
            key=lambda item: (-item[1], aircraft_display_label(item[0])),
        )
    ]
    top_tailnumbers_data = [
        (
            (
                tailnumber_labels[key].most_common(1)[0][0]
                if tailnumber_labels[key]
                else "Unknown"
            ),
            count,
        )
        for key, count in top_tailnumbers.most_common()
    ]
    monthly_sorted = sorted(monthly.items())
    yearly_sorted = sorted(yearly.items())
    yearly_miles_sorted = [
        (year, round(yearly_miles.get(year, 0), 2)) for year, _ in yearly_sorted
    ]
    yearly_co2_sorted = [
        (year, round(yearly_co2.get(year, 0), 1)) for year, _ in yearly_sorted
    ]
    total_co2 = round(sum(yearly_co2.values()), 1)

    def is_unknown_label(label):
        normalized = normalize_key(label or "")
        return normalized in {"unknown", "-", "n/a", "na", ""}

    def select_top_entry(entries, excluded_labels=None):
        excluded_labels = excluded_labels or set()
        excluded_normalized = {normalize_key(value) for value in excluded_labels if value}
        for label, count in entries:
            normalized = normalize_key(label or "")
            if not normalized or normalized in excluded_normalized:
                continue
            if is_unknown_label(label):
                continue
            return (label, count)
        return ("-", 0)

    top_city = select_top_entry(top_cities_data, {home_city} if home_city else set())
    top_country = select_top_entry(
        top_countries_data, {home_country} if home_country else set()
    )
    top_year = max(yearly.items(), key=lambda item: item[1]) if yearly else ("-", 0)
    top_airline = top_airlines_data[0] if top_airlines_data else ("-", 0)
    top_aircraft = select_top_entry(top_aircrafts_data)
    top_tailnumber = select_top_entry(top_tailnumbers_data)

    monthly_miles_sorted = [
        (month, round(monthly_miles.get(month, 0), 2)) for month, _ in monthly_sorted
    ]

    return {
        "total_flights": total_flights,
        "total_miles": total_miles,
        "total_hours": None,
        "top_cities": top_cities_data,
        "top_routes": top_routes_data,
        "top_countries": top_countries_data,
        "top_airlines": top_airlines_data,
        "top_aircrafts": top_aircrafts_data,
        "top_aircraft_miles": top_aircraft_miles_data,
        "top_tailnumbers": top_tailnumbers_data,
        "monthly": monthly_sorted,
        "monthly_miles": monthly_miles_sorted,
        "yearly": yearly_sorted,
        "yearly_miles": yearly_miles_sorted,
        "yearly_co2": yearly_co2_sorted,
        "total_co2": total_co2,
        "top_city": top_city,
        "top_country": top_country,
        "top_year": top_year,
        "top_airline": top_airline,
        "top_aircraft": top_aircraft,
        "top_tailnumber": top_tailnumber,
    }


def calculate_badge_progress(badge, stats, flights):
    """
    Calculate if a badge is earned and current progress.

    Args:
        badge: AchievementBadge model instance
        stats: Dict from summarize_flights()
        flights: List of Flight objects

    Returns:
        {
            'earned': bool,
            'current': int,
            'target': int,
            'progress_percent': int,
            'date_earned': Date or None
        }
    """
    from datetime import date

    badge_type = badge.badge_type
    threshold = badge.threshold_value
    current = 0
    date_earned = None

    if badge_type == 'flight_count':
        current = stats['total_flights']
        if current >= threshold:
            # Find the date of the Nth flight
            sorted_flights = sorted(flights, key=lambda f: f.start_date or date.min)
            if len(sorted_flights) >= threshold:
                date_earned = sorted_flights[threshold - 1].start_date

    elif badge_type == 'total_miles':
        current = int(stats['total_miles'])

    elif badge_type == 'countries_visited':
        current = len(stats.get('top_countries', []))

    elif badge_type == 'continents_visited':
        # Map countries to continents
        countries = [c[0] for c in stats.get('top_countries', [])]
        continents = set()
        for country in countries:
            continent = map_country_to_continent(country)
            if continent:
                continents.add(continent)
        current = len(continents)

    elif badge_type == 'aircraft_types':
        current = len(stats.get('top_aircrafts', []))

    elif badge_type == 'unique_registrations':
        current = len(stats.get('top_tailnumbers', []))

    elif badge_type == 'airline_count':
        current = len(stats.get('top_airlines', []))

    elif badge_type == 'red_eye_count':
        # Count overnight flights (depart after 18:00, arrive next day before 10:00)
        red_eyes = 0
        for flight in flights:
            if flight.start_time and flight.start_date and flight.end_date:
                # Check if overnight flight
                depart_hour = flight.start_time.hour
                is_overnight = (flight.end_date - flight.start_date).days >= 1
                if depart_hour >= 18 and is_overnight:
                    red_eyes += 1
        current = red_eyes

    elif badge_type == 'rare_aircraft':
        # Count flights on aircraft with <5 total appearances
        rare_count = 0
        reg_counts = {reg: count for reg, count in stats.get('top_tailnumbers', [])}
        for flight in flights:
            if flight.aircraft_registration:
                count = reg_counts.get(normalize_key(flight.aircraft_registration), 0)
                if count > 0 and count <= 5:
                    rare_count += 1
        current = rare_count

    elif badge_type == 'single_year_flights':
        # Max flights in a single calendar year
        year_counts = {}
        for flight in flights:
            if flight.start_date:
                year = flight.start_date.year
                year_counts[year] = year_counts.get(year, 0) + 1
        current = max(year_counts.values()) if year_counts else 0

    elif badge_type.startswith('rare_aircraft_'):
        # Specific rare aircraft type badge (e.g., rare_aircraft_b748)
        icao_type = badge_type.replace('rare_aircraft_', '').upper()

        # Map ICAO codes to possible string patterns in aircraft_type_normalized
        # This handles variations like "Boeing 747-8" for B748, "747-8i" etc.
        # Use specific patterns to avoid false matches (e.g., 747-8 not matching 747-400)
        icao_to_patterns = {
            'B748': ['747-8', '747-8i', '747-800'],  # Specific to avoid 747-400/747-300 matches
            'A388': ['a380', 'a-380'],
            'A346': ['a340-600', 'a346', '340-600', '340-6'],  # Specific 600 variant
            'A343': ['a340-300', 'a343', '340-300', '340-3'],  # Specific 300 variant
            'IL96': ['il-96', 'il96', 'ilyushin 96'],
            'B744': ['747-400', '747-4', 'b744', '747-436', '747-438', '747-422'],  # 747-400 variants
            'A338': ['a330-800', 'a330-8', 'a338', '330-800neo'],
            'B77L': ['777-200lr', '777-2lr', 'b77l'],
            'A359': ['a350-900ulr', 'a350-9ulr', 'a359ulr'],
            'B712': ['717', 'b717'],
            'MD82': ['md-82', 'md82', 'mcdonnell douglas 82'],
            'MD83': ['md-83', 'md83', 'mcdonnell douglas 83'],
            'MD88': ['md-88', 'md88', 'mcdonnell douglas 88'],
            'F70': ['fokker 70', 'f70'],
            'F100': ['fokker 100', 'f100'],
            'B732': ['737-200', '737-2', 'b732', '737-21', '737-22', '737-23'],  # 737-200 variants
            'B733': ['737-300', '737-3', 'b733', '737-31', '737-32', '737-33'],  # 737-300 variants
            'B734': ['737-400', '737-4', 'b734', '737-41', '737-42', '737-43'],  # 737-400 variants
            'B735': ['737-500', '737-5', 'b735', '737-51', '737-52', '737-53'],  # 737-500 variants
            'AJ27': ['arj21', 'arj-21', 'c909', 'comac'],
            'SU95': ['superjet', 'ssj100', 'ssj-100', 'su95', 'sukhoi'],
            'T204': ['tu-204', 'tu204', 'tu-214', 'tupolev 204'],
            'AN24': ['an-24', 'an24', 'antonov 24'],
            'L410': ['l-410', 'l410', 'let 410', 'turbolet'],
            'DHC6': ['dhc-6', 'dhc6', 'twin otter', 'de havilland 6'],
            'DHC7': ['dhc-7', 'dhc7', 'dash 7', 'dash-7'],
            'D328': ['dornier 328', 'd328', 'do328'],
            'D228': ['dornier 228', 'd228', 'do228'],
            'SB20': ['saab 2000', 'sb20'],
            'B463': ['bae 146', 'bae146', 'avro rj', 'rj85', 'rj100', 'b463'],
        }

        patterns = icao_to_patterns.get(icao_type, [icao_type.lower()])

        # Count flights on this specific aircraft type
        current = 0
        for flight in flights:
            matched = False

            # Check normalized aircraft type
            if flight.aircraft_type_normalized:
                normalized_type = normalize_key(flight.aircraft_type_normalized) or ''
                for pattern in patterns:
                    if pattern in normalized_type:
                        matched = True
                        break

            # Also check ICAO code from flight history if available
            if not matched and hasattr(flight, 'flight_histories') and flight.flight_histories:
                for history in flight.flight_histories:
                    if history.aircraft_icao:
                        history_icao = normalize_key(history.aircraft_icao) or ''
                        if history_icao == normalize_key(icao_type):
                            matched = True
                            break

            # Also check AirNavRadar history
            if not matched and hasattr(flight, 'airnav_histories') and flight.airnav_histories:
                for history in flight.airnav_histories:
                    if history.aircraft_type:
                        anr_type = normalize_key(history.aircraft_type) or ''
                        for pattern in patterns:
                            if pattern in anr_type:
                                matched = True
                                break
                    if matched:
                        break

            if matched:
                current = 1
                if current >= threshold:
                    date_earned = flight.start_date
                    break

    else:
        # Unknown badge type
        current = 0

    earned = current >= threshold
    progress_percent = min(int((current / threshold) * 100), 100) if threshold > 0 else 0

    return {
        'earned': earned,
        'current': current,
        'target': threshold,
        'progress_percent': progress_percent,
        'date_earned': date_earned if earned else None,
    }


def map_country_to_continent(country_name):
    """Map country name to continent."""
    continent_mapping = {
        # North America
        'United States': 'North America',
        'Canada': 'North America',
        'Mexico': 'North America',

        # Europe
        'United Kingdom': 'Europe',
        'France': 'Europe',
        'Germany': 'Europe',
        'Italy': 'Europe',
        'Spain': 'Europe',
        'Netherlands': 'Europe',
        'Switzerland': 'Europe',
        'Austria': 'Europe',
        'Belgium': 'Europe',
        'Greece': 'Europe',
        'Portugal': 'Europe',
        'Ireland': 'Europe',
        'Poland': 'Europe',
        'Czech Republic': 'Europe',
        'Hungary': 'Europe',
        'Denmark': 'Europe',
        'Sweden': 'Europe',
        'Norway': 'Europe',
        'Finland': 'Europe',

        # Asia
        'China': 'Asia',
        'Japan': 'Asia',
        'India': 'Asia',
        'South Korea': 'Asia',
        'Thailand': 'Asia',
        'Singapore': 'Asia',
        'Malaysia': 'Asia',
        'Indonesia': 'Asia',
        'Vietnam': 'Asia',
        'Philippines': 'Asia',
        'United Arab Emirates': 'Asia',
        'Israel': 'Asia',
        'Turkey': 'Asia',
        'Qatar': 'Asia',

        # South America
        'Brazil': 'South America',
        'Argentina': 'South America',
        'Chile': 'South America',
        'Peru': 'South America',
        'Colombia': 'South America',

        # Africa
        'South Africa': 'Africa',
        'Egypt': 'Africa',
        'Morocco': 'Africa',
        'Kenya': 'Africa',

        # Oceania
        'Australia': 'Oceania',
        'New Zealand': 'Oceania',
    }
    return continent_mapping.get(country_name)


def get_all_achievements(flights, stats):
    """
    Get all achievements with progress for the current user.

    Args:
        flights: List of Flight objects
        stats: Dict from summarize_flights()

    Returns:
        List of dicts with badge info + progress
    """
    from app.models import AchievementBadge

    badges = AchievementBadge.query.filter_by(is_active=True).order_by(
        AchievementBadge.display_order, AchievementBadge.id
    ).all()

    achievements = []
    for badge in badges:
        progress = calculate_badge_progress(badge, stats, flights)
        achievements.append({
            'badge': badge,
            'progress': progress,
        })

    return achievements
