import argparse

from app import create_app
from app.models import Flight
from app.services.analytics import group_flights_by_match_score, resolve_duplicate_rules


def summarize_flight(flight):
    date = flight.start_date.isoformat() if flight.start_date else "-"
    origin = flight.origin_name or "-"
    destination = flight.destination_name or "-"
    flight_number = flight.flight_number or "-"
    return f"{flight.id} · {date} · {origin} → {destination} · {flight_number}"


def main():
    parser = argparse.ArgumentParser(
        description="Preview duplicate grouping suggestions."
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--show-reasons", action="store_true")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        rules = resolve_duplicate_rules(app.config.get("DUPLICATE_MATCH_RULES"))
        if args.show_reasons:
            rules["show_reasons"] = True
        flights = (
            Flight.query.order_by(Flight.start_date.desc(), Flight.id.desc()).all()
        )
        groups = group_flights_by_match_score(flights, rules)
        duplicates = [group for group in groups if group["count"] > 1]

    print(f"Found {len(duplicates)} duplicate groups.")
    for group in duplicates[: args.limit]:
        primary = group["primary"]
        score = group.get("match_score")
        score_label = score if score is not None else "-"
        print(
            f"\nGroup {primary.id} · score {score_label} · {group['count']} flights"
        )
        if args.show_reasons and group.get("match_reasons"):
            print(f"  Reasons: {', '.join(group['match_reasons'])}")
        for flight in group["flights"]:
            print(f"  - {summarize_flight(flight)}")


if __name__ == "__main__":
    main()
