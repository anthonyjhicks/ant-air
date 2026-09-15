"""Stamp existing records with sync_revision=1 so they appear in incremental sync.

The initial sync migration set sync_revision=0 as the server_default, but
the pull API filters sync_revision > since. Records with revision 0 are
invisible to any client that already completed an initial sync (since > 0).

This migration bumps all revision-0 records to 1 and ensures sync_state
starts at 1 so future incremental pulls include these records.

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-02-26
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "h2i3j4k5l6m7"
down_revision = "g1h2i3j4k5l6"
branch_labels = None
depends_on = None


def upgrade():
    # Stamp every existing record that still has revision 0
    for table in ("flight", "trip", "trip_leg", "aircraft", "achievement_badge"):
        op.execute(f"UPDATE {table} SET sync_revision = 1 WHERE sync_revision = 0")

    # Ensure the global counter is at least 1 so future bumps start from 2+
    op.execute("UPDATE sync_state SET current_revision = GREATEST(current_revision, 1)")


def downgrade():
    # Revert stamped records back to 0
    for table in ("flight", "trip", "trip_leg", "aircraft", "achievement_badge"):
        op.execute(f"UPDATE {table} SET sync_revision = 0 WHERE sync_revision = 1")
