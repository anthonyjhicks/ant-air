"""Seed initial achievement badges."""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from app.extensions import db
from app.models import AchievementBadge

app = create_app()

INITIAL_BADGES = [
    # Flight Milestones
    {"name": "First Flight", "category": "milestones", "badge_type": "flight_count", "threshold_value": 1, "icon_emoji": "✈️", "description": "Complete your first flight", "display_order": 1},
    {"name": "Frequent Flyer", "category": "milestones", "badge_type": "flight_count", "threshold_value": 25, "icon_emoji": "🛫", "description": "Fly 25 flights", "display_order": 2},
    {"name": "Sky Warrior", "category": "milestones", "badge_type": "flight_count", "threshold_value": 50, "icon_emoji": "🎖️", "description": "Reach 50 flights", "display_order": 3},
    {"name": "Century Club", "category": "milestones", "badge_type": "flight_count", "threshold_value": 100, "icon_emoji": "💯", "description": "Complete 100 flights", "display_order": 4},
    {"name": "Elite Traveler", "category": "milestones", "badge_type": "flight_count", "threshold_value": 250, "icon_emoji": "👑", "description": "Fly 250 flights", "display_order": 5},

    # Distance Milestones
    {"name": "50K Miles", "category": "milestones", "badge_type": "total_miles", "threshold_value": 50000, "icon_emoji": "🌟", "description": "Fly 50,000 miles", "display_order": 10},
    {"name": "100K Miles", "category": "milestones", "badge_type": "total_miles", "threshold_value": 100000, "icon_emoji": "⭐", "description": "Fly 100,000 miles", "display_order": 11},
    {"name": "Half Million", "category": "milestones", "badge_type": "total_miles", "threshold_value": 500000, "icon_emoji": "💫", "description": "Fly 500,000 miles", "display_order": 12},
    {"name": "Million Miler", "category": "milestones", "badge_type": "total_miles", "threshold_value": 1000000, "icon_emoji": "🏆", "description": "Reach 1 million miles flown", "display_order": 13},

    # Geographic
    {"name": "Globe Trotter", "category": "geographic", "badge_type": "countries_visited", "threshold_value": 10, "icon_emoji": "🌍", "description": "Visit 10 different countries", "display_order": 20},
    {"name": "World Explorer", "category": "geographic", "badge_type": "countries_visited", "threshold_value": 25, "icon_emoji": "🗺️", "description": "Visit 25 different countries", "display_order": 21},
    {"name": "Continental", "category": "geographic", "badge_type": "continents_visited", "threshold_value": 3, "icon_emoji": "🌎", "description": "Visit 3 continents", "display_order": 22},
    {"name": "All Continents", "category": "geographic", "badge_type": "continents_visited", "threshold_value": 6, "icon_emoji": "🌏", "description": "Visit all 6 inhabited continents", "display_order": 23},

    # Equipment Diversity
    {"name": "Aircraft Enthusiast", "category": "equipment", "badge_type": "aircraft_types", "threshold_value": 5, "icon_emoji": "🛩️", "description": "Fly 5 different aircraft types", "display_order": 30},
    {"name": "Fleet Master", "category": "equipment", "badge_type": "aircraft_types", "threshold_value": 10, "icon_emoji": "🚁", "description": "Fly 10 different aircraft types", "display_order": 31},
    {"name": "Aviation Expert", "category": "equipment", "badge_type": "aircraft_types", "threshold_value": 25, "icon_emoji": "✈️", "description": "Fly 25 different aircraft types", "display_order": 32},
    {"name": "Tail Collector", "category": "equipment", "badge_type": "unique_registrations", "threshold_value": 50, "icon_emoji": "🔢", "description": "Fly 50 unique aircraft registrations", "display_order": 33},

    # Temporal
    {"name": "Night Owl", "category": "temporal", "badge_type": "red_eye_count", "threshold_value": 10, "icon_emoji": "🌙", "description": "Complete 10 red-eye (overnight) flights", "display_order": 40},
    {"name": "Century Year", "category": "temporal", "badge_type": "single_year_flights", "threshold_value": 100, "icon_emoji": "📅", "description": "Fly 100 flights in a single calendar year", "display_order": 41},

    # Special
    {"name": "Rare Bird Spotter", "category": "equipment", "badge_type": "rare_aircraft", "threshold_value": 5, "icon_emoji": "💎", "description": "Fly 5 rare aircraft (with <5 total appearances)", "display_order": 50},
    {"name": "Airline Loyalist", "category": "loyalty", "badge_type": "airline_count", "threshold_value": 50, "icon_emoji": "🎫", "description": "Fly with 50 different airlines", "display_order": 51},
]

with app.app_context():
    for badge_data in INITIAL_BADGES:
        existing = AchievementBadge.query.filter_by(name=badge_data["name"]).first()
        if not existing:
            badge = AchievementBadge(**badge_data, is_active=True)
            db.session.add(badge)
            print(f"✓ Added badge: {badge_data['name']}")
        else:
            print(f"- Badge already exists: {badge_data['name']}")

    db.session.commit()
    print(f"\n✓ Seeded {len(INITIAL_BADGES)} achievement badges")
