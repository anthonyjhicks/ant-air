"""Seed rare aircraft achievement badges with images."""
import os
import sys
import json
import time
from urllib.parse import quote
from urllib.request import Request, urlopen

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from app.extensions import db
from app.models import AchievementBadge

app = create_app()

# Representative registrations for each rare aircraft type
# These are real registrations to fetch actual aircraft images
# Multiple options to try for each type
REPRESENTATIVE_REGISTRATIONS = {
    "B748": ["D-ABYA", "N6067E", "HL7644"],  # Lufthansa, Korean Air
    "A388": ["A6-EUA", "F-HPJB", "9V-SKA"],  # Emirates, Air France, Singapore
    "A346": ["D-AIHL", "CS-TRI", "PH-AOA"],  # Lufthansa, TAP, KLM (retired)
    "A343": ["HB-JMG", "D-AIFE", "CS-TOA"],  # Swiss, Lufthansa, TAP
    "IL96": ["RA-96022", "RA-96016"],  # Rossiya
    "B744": ["VH-OEJ", "N744ST", "9V-SMU"],  # Qantas, Atlas, Singapore
    "A338": ["9M-MNA", "F-HHAV", "2-DEER"],  # Malaysia, Hi Fly, Kuwait
    "B77L": ["VT-ALH", "N6066Z", "A6-EWH"],  # Air India, Delta, Emirates
    "A359": ["9V-SMW", "9V-SGA"],  # Singapore ULR
    "B712": ["N916NN", "N928NN", "VH-YQT"],  # Delta, Hawaiian, QantasLink
    "MD82": ["EC-LYF", "N965AS", "I-SMEL"],  # Swiftair, Alaska (retired), Alitalia
    "MD83": ["YR-HBB", "N963AS", "EC-KXD"],  # Blue Air, Alaska
    "MD88": ["N956DL", "N987DL"],  # Delta (retired)
    "F70": ["PH-WXD", "PH-KZA", "OE-LFO"],  # KLM Cityhopper, Austrian
    "F100": ["VH-FQA", "N146US", "PH-OFO"],  # Alliance, US Air
    "B732": ["C-GNLK", "N221US", "N73711"],  # Nolinor,
    "B733": ["N314SW", "N300SW", "G-THOP"],  # Southwest (retired)
    "B734": ["N417AS", "VH-TJG", "9M-MMD"],  # Alaska, Qantas, Malaysia
    "B735": ["N521SW", "N531SW"],  # Southwest (retired)
    "AJ27": ["B-3321", "B-3386", "B-602A"],  # Chengdu Airlines
    "SU95": ["RA-89098", "RA-89011", "RA-89012"],  # Aeroflot
    "T204": ["RA-64057", "RA-64043"],  # Red Wings
    "AN24": ["ER-AXO", "UN-47302"],  # Air Moldova
    "L410": ["OK-TDR", "S5-CDG"],
    "DHC6": ["N882MA", "C-FTGI", "N391PX"],  # Cape Air
    "DHC7": ["C-FLOG", "C-GNDK"],
    "D328": ["D-BADA", "HB-AES"],
    "D228": ["VT-KAE", "D-IFAW"],
    "SB20": ["SE-LNY", "N291SF"],
    "B463": ["VH-NJE", "G-JEBB", "ZS-SYB"],  # BAe 146
}

RARE_AIRCRAFT_DATA = [
    {
        "icaoType": "B748",
        "tier": "S",
        "name": "Boeing 747-8 Intercontinental",
        "whyRareScheduled": "Very small number of scheduled passenger operators; limited routes."
    },
    {
        "icaoType": "A388",
        "tier": "S",
        "name": "Airbus A380",
        "whyRareScheduled": "Operated by a limited set of airlines; usually only on specific trunk routes."
    },
    {
        "icaoType": "A346",
        "tier": "S",
        "name": "Airbus A340-600",
        "whyRareScheduled": "Four-engine widebody now limited to a small number of scheduled operators."
    },
    {
        "icaoType": "A343",
        "tier": "S",
        "name": "Airbus A340-300",
        "whyRareScheduled": "Scheduled use persists in small pockets; generally disappearing."
    },
    {
        "icaoType": "IL96",
        "tier": "S",
        "name": "Ilyushin Il-96",
        "whyRareScheduled": "Extremely limited scheduled passenger operations and route availability."
    },
    {
        "icaoType": "B744",
        "tier": "S",
        "name": "Boeing 747-400 (Passenger)",
        "whyRareScheduled": "Mostly retired from scheduled passenger service; remaining ops are scarce."
    },
    {
        "icaoType": "A338",
        "tier": "A",
        "name": "Airbus A330-800neo",
        "whyRareScheduled": "Low global fleet and few scheduled operators; hard to encounter organically."
    },
    {
        "icaoType": "B77L",
        "tier": "A",
        "name": "Boeing 777-200LR",
        "whyRareScheduled": "Small production run; operated by relatively few airlines on specific long routes."
    },
    {
        "icaoType": "A359",
        "tier": "A",
        "name": "Airbus A350-900ULR (variant within A359)",
        "whyRareScheduled": "Specialized ultra-long-haul sub-variant used on a small set of routes."
    },
    {
        "icaoType": "B712",
        "tier": "A",
        "name": "Boeing 717",
        "whyRareScheduled": "Concentrated with very few airlines; location-dependent availability."
    },
    {
        "icaoType": "MD82",
        "tier": "A",
        "name": "McDonnell Douglas MD-82",
        "whyRareScheduled": "MD-80 family now limited to a small number of scheduled operators."
    },
    {
        "icaoType": "MD83",
        "tier": "A",
        "name": "McDonnell Douglas MD-83",
        "whyRareScheduled": "Same rarity pattern as other MD-80 variants in scheduled service."
    },
    {
        "icaoType": "MD88",
        "tier": "A",
        "name": "McDonnell Douglas MD-88",
        "whyRareScheduled": "Scheduled operations are uncommon globally; mostly phased out."
    },
    {
        "icaoType": "F70",
        "tier": "A",
        "name": "Fokker 70",
        "whyRareScheduled": "Scheduled fleets exist only in limited regional pockets."
    },
    {
        "icaoType": "F100",
        "tier": "A",
        "name": "Fokker 100",
        "whyRareScheduled": "Still scheduled in a few regions but rare elsewhere; slowly shrinking."
    },
    {
        "icaoType": "B732",
        "tier": "A",
        "name": "Boeing 737-200",
        "whyRareScheduled": "Very rare in scheduled passenger service; mostly niche/remote operations."
    },
    {
        "icaoType": "B733",
        "tier": "B",
        "name": "Boeing 737-300",
        "whyRareScheduled": "Classic variant increasingly uncommon on scheduled routes outside certain markets."
    },
    {
        "icaoType": "B734",
        "tier": "B",
        "name": "Boeing 737-400",
        "whyRareScheduled": "Classic variant; scheduled service exists but is regionally constrained."
    },
    {
        "icaoType": "B735",
        "tier": "B",
        "name": "Boeing 737-500",
        "whyRareScheduled": "Classic variant; rare in many regions and shrinking in scheduled use."
    },
    {
        "icaoType": "AJ27",
        "tier": "B",
        "name": "COMAC C909 (ARJ21)",
        "whyRareScheduled": "Mostly concentrated in one region; limited exposure on global networks."
    },
    {
        "icaoType": "SU95",
        "tier": "B",
        "name": "Sukhoi Superjet 100 / SJ-100",
        "whyRareScheduled": "Primarily region-locked; uncommon to encounter on wider international itineraries."
    },
    {
        "icaoType": "T204",
        "tier": "B",
        "name": "Tupolev Tu-204/214",
        "whyRareScheduled": "Very limited scheduled passenger usage; niche and location-dependent."
    },
    {
        "icaoType": "AN24",
        "tier": "B",
        "name": "Antonov An-24",
        "whyRareScheduled": "Scheduled service persists in small pockets; very uncommon globally."
    },
    {
        "icaoType": "L410",
        "tier": "B",
        "name": "Let L-410 Turbolet",
        "whyRareScheduled": "Niche scheduled networks; rare outside very specific regional routes."
    },
    {
        "icaoType": "DHC6",
        "tier": "B",
        "name": "De Havilland Canada DHC-6 Twin Otter",
        "whyRareScheduled": "Scheduled island/remote-strip flying; rarely appears in mainstream schedules."
    },
    {
        "icaoType": "DHC7",
        "tier": "B",
        "name": "De Havilland Canada Dash 7",
        "whyRareScheduled": "Extremely niche scheduled operations; uncommon to find on timetables."
    },
    {
        "icaoType": "D328",
        "tier": "B",
        "name": "Dornier 328",
        "whyRareScheduled": "Small fleets and niche routes; scheduled passenger appearances are uncommon."
    },
    {
        "icaoType": "D228",
        "tier": "B",
        "name": "Dornier 228",
        "whyRareScheduled": "Specialist regional operations; limited scheduled passenger footprint."
    },
    {
        "icaoType": "SB20",
        "tier": "B",
        "name": "Saab 2000",
        "whyRareScheduled": "Small global fleet; scheduled use is limited and route-specific."
    },
    {
        "icaoType": "B463",
        "tier": "B",
        "name": "BAe 146 / Avro RJ (representative code)",
        "whyRareScheduled": "Distinct family with limited remaining scheduled passenger operators; niche routes."
    }
]

ADSBDB_URL = "https://api.adsbdb.com/v0/aircraft/"
USER_AGENT = "ant-air/1.0 (rare-aircraft-badges)"
MIN_SECONDS_BETWEEN_LOOKUPS = 0.35

_last_lookup_time = 0.0


def _throttle():
    global _last_lookup_time
    now = time.monotonic()
    wait_for = MIN_SECONDS_BETWEEN_LOOKUPS - (now - _last_lookup_time)
    if wait_for > 0:
        time.sleep(wait_for)
    _last_lookup_time = time.monotonic()


def fetch_aircraft_photo(registration, timeout=6):
    """Fetch aircraft photo URL from ADSBDB."""
    if not registration:
        return None

    key = str(registration).strip().upper()
    url = f"{ADSBDB_URL}{quote(key)}"
    request = Request(url, headers={"User-Agent": USER_AGENT})

    try:
        _throttle()
        with urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
        data = json.loads(payload)
    except Exception as e:
        print(f"  ⚠️  Failed to fetch {registration}: {e}")
        return None

    aircraft = data.get("response", {}).get("aircraft")
    if not isinstance(aircraft, dict):
        return None

    photo_url = aircraft.get("url_photo")
    return photo_url


def get_tier_emoji(tier):
    """Get emoji for tier."""
    tier_emojis = {
        "S": "💎",  # Diamond for S-tier
        "A": "⭐",  # Star for A-tier
        "B": "✨",  # Sparkles for B-tier
    }
    return tier_emojis.get(tier, "✈️")


def get_display_order(tier, index):
    """Calculate display order based on tier and index."""
    tier_base = {
        "S": 100,
        "A": 200,
        "B": 300,
    }
    return tier_base.get(tier, 400) + index


with app.app_context():
    print("Seeding rare aircraft achievement badges...\n")

    created_count = 0
    updated_count = 0
    skipped_count = 0

    for idx, aircraft_data in enumerate(RARE_AIRCRAFT_DATA):
        icao_type = aircraft_data["icaoType"]
        tier = aircraft_data["tier"]
        name = aircraft_data["name"]
        why_rare = aircraft_data["whyRareScheduled"]

        badge_name = f"Rare Bird: {name}"

        # Check if badge already exists
        existing = AchievementBadge.query.filter_by(name=badge_name).first()

        # Fetch photo URL - try multiple registrations
        registrations = REPRESENTATIVE_REGISTRATIONS.get(icao_type, [])
        photo_url = None

        if registrations:
            print(f"Fetching photo for {name} ({icao_type})...")
            for registration in registrations:
                print(f"  Trying {registration}...")
                photo_url = fetch_aircraft_photo(registration)
                if photo_url:
                    print(f"  ✓ Found photo: {photo_url}")
                    break
            if not photo_url:
                print(f"  ⚠️  No photo found after trying {len(registrations)} registration(s)")
        else:
            print(f"  ⚠️  No representative registrations for {icao_type}")

        if existing:
            # Update existing badge
            existing.description = f"Fly on a {name}. {why_rare}"
            existing.icon_emoji = get_tier_emoji(tier)
            existing.icon_url = photo_url
            existing.display_order = get_display_order(tier, idx)
            existing.category = "rare_aircraft"
            existing.badge_type = f"rare_aircraft_{icao_type.lower()}"
            existing.threshold_value = 1
            existing.is_active = True

            db.session.commit()
            print(f"  ✓ Updated badge: {badge_name}\n")
            updated_count += 1
        else:
            # Create new badge
            badge = AchievementBadge(
                name=badge_name,
                description=f"Fly on a {name}. {why_rare}",
                category="rare_aircraft",
                badge_type=f"rare_aircraft_{icao_type.lower()}",
                threshold_value=1,
                icon_emoji=get_tier_emoji(tier),
                icon_url=photo_url,
                display_order=get_display_order(tier, idx),
                is_active=True
            )
            db.session.add(badge)
            db.session.commit()
            print(f"  ✓ Created badge: {badge_name}\n")
            created_count += 1

    print(f"\n{'='*60}")
    print(f"✓ Seeded {len(RARE_AIRCRAFT_DATA)} rare aircraft badges")
    print(f"  - Created: {created_count}")
    print(f"  - Updated: {updated_count}")
    print(f"  - Skipped: {skipped_count}")
    print(f"{'='*60}")
