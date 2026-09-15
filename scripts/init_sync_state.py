#!/usr/bin/env python3
"""Initialise the sync_state table and stamp all existing records.

Usage:
    python scripts/init_sync_state.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.extensions import db
from app.models import Aircraft, AchievementBadge, Flight, SyncState, Trip, TripLeg

app = create_app()
with app.app_context():
    state = SyncState.query.first()
    if state is None:
        state = SyncState(id=1, current_revision=0)
        db.session.add(state)

    count = 0
    for model in [Flight, Trip, TripLeg, Aircraft, AchievementBadge]:
        for row in model.query.filter_by(sync_revision=0).all():
            state.current_revision += 1
            row.sync_revision = state.current_revision
            count += 1

    db.session.commit()
    print(f"Sync state initialised. Stamped {count} records at revision {state.current_revision}.")
