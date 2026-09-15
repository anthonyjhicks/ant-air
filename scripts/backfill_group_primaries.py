"""Fill blank fields on each duplicate group's primary from its older records.

Flights sharing a grouping_id are one flight recorded more than once, and the
newest record (the primary) represents the group in every report. A value that
only an older duplicate carries would never show, so copy it onto the primary
when the primary's own field is blank. Dry run by default; pass --apply to write.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Flight  # noqa: E402
from app.services.flight_groups import (  # noqa: E402
    APPROVED_FLIGHT_FILTERS,
    fill_blank_fields_from_group,
)
from app.sync import stamp_revision  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="write the changes (default: dry run)"
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        rows = (
            Flight.query.filter(
                *APPROVED_FLIGHT_FILTERS,
                Flight.grouping_id.isnot(None),
                Flight.grouping_id != "",
            )
            .order_by(Flight.grouping_id, Flight.start_date.desc(), Flight.id.desc())
            .all()
        )
        groups = {}
        for flight in rows:
            groups.setdefault(flight.grouping_id, []).append(flight)

        touched = 0
        now = datetime.utcnow()
        for members in groups.values():
            if len(members) < 2:
                continue
            primary = members[0]
            filled = fill_blank_fields_from_group(primary, members[1:])
            if not filled:
                continue
            touched += 1
            label = f"{primary.airline_code or ''}{primary.flight_number or ''}".strip()
            print(f"flight {primary.id} ({primary.start_date} {label}): {', '.join(filled)}")
            if args.apply:
                primary.updated_at = now
                stamp_revision(primary)

        if args.apply:
            db.session.commit()
            print(f"Updated {touched} primaries.")
        else:
            db.session.rollback()
            print(f"Dry run: {touched} primaries would change. Re-run with --apply to write.")


if __name__ == "__main__":
    main()
