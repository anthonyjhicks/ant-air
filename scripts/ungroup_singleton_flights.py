from pathlib import Path
import sys

from sqlalchemy import func, select

repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))

from app import create_app
from app.extensions import db
from app.models import Flight


def main():
    app = create_app()
    with app.app_context():
        singleton_group_ids = (
            db.session.query(Flight.grouping_id)
            .filter(Flight.grouping_id.isnot(None), Flight.grouping_id != "")
            .group_by(Flight.grouping_id)
            .having(func.count(Flight.id) == 1)
            .subquery()
        )
        group_count = (
            db.session.query(func.count())
            .select_from(singleton_group_ids)
            .scalar()
            or 0
        )
        updated = (
            db.session.query(Flight)
            .filter(Flight.grouping_id.in_(select(singleton_group_ids.c.grouping_id)))
            .update({Flight.grouping_id: None}, synchronize_session=False)
        )
        db.session.commit()

    print(
        f"Cleared grouping_id for {updated} flights "
        f"across {group_count} singleton groups."
    )


if __name__ == "__main__":
    main()
