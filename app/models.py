from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class Trip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    trip_code = db.Column(db.String(64), unique=True)
    trip_type = db.Column(db.String(64))
    notes = db.Column(db.Text)
    start_date = db.Column(db.Date)
    start_date_precision = db.Column(db.String(8))
    start_date_year = db.Column(db.Integer)
    start_date_month = db.Column(db.Integer)
    start_date_day = db.Column(db.Integer)
    end_date = db.Column(db.Date)
    end_date_precision = db.Column(db.String(8))
    end_date_year = db.Column(db.Integer)
    end_date_month = db.Column(db.Integer)
    end_date_day = db.Column(db.Integer)
    legs = db.relationship(
        "TripLeg",
        backref="trip",
        cascade="all, delete-orphan",
        order_by="TripLeg.sequence",
        lazy=True,
    )

    sync_revision = db.Column(db.BigInteger, nullable=False, default=0)
    deleted_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class TripLeg(db.Model):
    __tablename__ = "trip_leg"
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trip.id"), nullable=False)
    sequence = db.Column(db.Integer, nullable=False, default=0)
    mode = db.Column(db.String(32), nullable=False, default="flight")
    carrier_name = db.Column(db.String(128))
    carrier_code = db.Column(db.String(16))
    service_class = db.Column(db.String(64))
    flight_number = db.Column(db.String(32))
    aircraft_type = db.Column(db.String(64))
    aircraft_registration = db.Column(db.String(32))
    start_country = db.Column(db.String(128))
    start_city_name = db.Column(db.String(128))
    start_airport = db.Column(db.String(64))
    end_country = db.Column(db.String(128))
    end_city_name = db.Column(db.String(128))
    end_airport = db.Column(db.String(64))
    start_date = db.Column(db.Date)
    start_date_precision = db.Column(db.String(8))
    start_date_year = db.Column(db.Integer)
    start_date_month = db.Column(db.Integer)
    start_date_day = db.Column(db.Integer)
    end_date = db.Column(db.Date)
    end_date_precision = db.Column(db.String(8))
    end_date_year = db.Column(db.Integer)
    end_date_month = db.Column(db.Integer)
    end_date_day = db.Column(db.Integer)
    notes = db.Column(db.Text)
    flight = db.relationship("Flight", backref="trip_leg", uselist=False)

    sync_revision = db.Column(db.BigInteger, nullable=False, default=0)
    deleted_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class Flight(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(16), default="approved", nullable=False)
    trip_name = db.Column(db.String(255))
    trip_id = db.Column(db.String(64))
    trip_type = db.Column(db.String(64))
    trip_leg_id = db.Column(db.Integer, db.ForeignKey("trip_leg.id"))
    activity_id = db.Column(db.String(64))
    activity_cost = db.Column(db.Numeric(10, 2))
    url = db.Column(db.Text)
    booking_site = db.Column(db.String(255))
    supplier_confirmation = db.Column(db.String(128))
    booking_date = db.Column(db.Date)
    booking_site_phone = db.Column(db.String(64))
    traveller = db.Column(db.String(128))
    ticket_number = db.Column(db.String(64))
    airline_code = db.Column(db.String(16))
    operating_airline_code = db.Column(db.String(16))
    aircraft = db.Column(db.String(64))
    aircraft_type_normalized = db.Column(db.String(64))
    aircraft_registration = db.Column(db.String(32))
    service_class = db.Column(db.String(64))
    flight_number = db.Column(db.String(32))
    operating_flight_number = db.Column(db.String(32))
    start_country = db.Column(db.String(128))
    start_city_name = db.Column(db.String(128))
    start_airport = db.Column(db.String(64))
    start_terminal = db.Column(db.String(32))
    start_lat = db.Column(db.Float)
    start_long = db.Column(db.Float)
    start_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time)
    end_country = db.Column(db.String(128))
    end_city_name = db.Column(db.String(128))
    end_airport = db.Column(db.String(64))
    end_terminal = db.Column(db.String(32))
    end_lat = db.Column(db.Float)
    end_long = db.Column(db.Float)
    end_date = db.Column(db.Date)
    end_time = db.Column(db.Time)
    stops = db.Column(db.Integer)
    distance = db.Column(db.Float)
    route_direction = db.Column(db.String(8))
    source_file = db.Column(db.String(255))
    grouping_id = db.Column(db.String(36))
    audit_missing_leg_ignored = db.Column(db.Boolean, default=False, nullable=False)
    follow_up = db.Column(db.Boolean, default=False, nullable=False)
    exclude_from_stats = db.Column(db.Boolean, default=False, nullable=False)
    sync_revision = db.Column(db.BigInteger, nullable=False, default=0)
    deleted_at = db.Column(db.DateTime)
    flight_histories = db.relationship(
        "FlightHistory", backref="flight", cascade="all, delete-orphan", lazy=True
    )
    airnav_histories = db.relationship(
        "FlightHistoryAirNavRadar",
        backref="flight",
        cascade="all, delete-orphan",
        lazy=True,
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    @property
    def origin_name(self):
        return self.start_city_name or self.start_airport or self.start_country or "-"

    @property
    def destination_name(self):
        return self.end_city_name or self.end_airport or self.end_country or "-"


class AuditDuplicateIgnore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    signature = db.Column(db.Text, unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class AchievementBadge(db.Model):
    __tablename__ = "achievement_badge"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(64))  # e.g., 'milestones', 'geographic', 'equipment'
    badge_type = db.Column(db.String(64), nullable=False)  # e.g., 'flight_count', 'total_miles'
    threshold_value = db.Column(db.Integer, nullable=False)
    icon_emoji = db.Column(db.String(8))  # Emoji character
    icon_url = db.Column(db.String(255))  # Optional image URL
    display_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    sync_revision = db.Column(db.BigInteger, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<AchievementBadge {self.name}>"


class InsightCache(db.Model):
    __tablename__ = "insight_cache"
    id = db.Column(db.Integer, primary_key=True)
    cache_key = db.Column(db.String(64), unique=True, nullable=False)
    flight_count = db.Column(db.Integer)
    total_miles = db.Column(db.Float)
    insights_json = db.Column(db.Text)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FlightHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flight_id = db.Column(db.Integer, db.ForeignKey("flight.id"), nullable=False)
    dep_iata = db.Column(db.String(8))
    dep_icao = db.Column(db.String(8))
    arr_iata = db.Column(db.String(8))
    arr_icao = db.Column(db.String(8))
    dep_date = db.Column(db.Date, nullable=False)
    dep_scheduled_time = db.Column(db.DateTime)
    arr_scheduled_time = db.Column(db.DateTime)
    airline_iata = db.Column(db.String(8))
    airline_icao = db.Column(db.String(8))
    flight_iata = db.Column(db.String(16))
    flight_icao = db.Column(db.String(16))
    aircraft_icao = db.Column(db.String(8))
    aircraft_icao24 = db.Column(db.String(16))
    aircraft_reg_number = db.Column(db.String(32))
    status = db.Column(db.String(32))
    system_squawk = db.Column(db.String(16))
    system_updated = db.Column(db.DateTime)
    raw_payload = db.Column(db.JSON, nullable=False)

    positions = db.relationship(
        "FlightPosition", backref="history", cascade="all, delete-orphan", lazy=True
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class FlightPosition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    history_id = db.Column(
        db.Integer, db.ForeignKey("flight_history.id"), nullable=False
    )
    altitude = db.Column(db.Float)
    direction = db.Column(db.Float)
    horizontal_speed = db.Column(db.Float)
    vertical_speed = db.Column(db.Float)
    is_ground = db.Column(db.Boolean)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    position_updated = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class FlightHistoryAirNavRadar(db.Model):
    __tablename__ = "flight_history_air_nav_radar"
    id = db.Column(db.Integer, primary_key=True)
    flight_id = db.Column(db.Integer, db.ForeignKey("flight.id"), nullable=False)
    dep_date = db.Column(db.Date, nullable=False)
    callsign = db.Column(db.String(32))
    flight_number_iata = db.Column(db.String(16))
    flight_number_icao = db.Column(db.String(16))
    aircraft_registration = db.Column(db.String(32))
    aircraft_mode_s = db.Column(db.String(16))
    aircraft_serial_number = db.Column(db.String(32))
    aircraft_type = db.Column(db.String(16))
    aircraft_classes = db.Column(db.JSON)
    aircraft_type_description = db.Column(db.String(128))
    airline_iata = db.Column(db.String(16))
    airline_icao = db.Column(db.String(16))
    airline_name = db.Column(db.String(128))
    dep_airport_icao = db.Column(db.String(16))
    dep_airport_iata = db.Column(db.String(16))
    dep_airport_name = db.Column(db.String(255))
    dep_airport_city = db.Column(db.String(128))
    dep_airport_state = db.Column(db.String(128))
    dep_airport_country = db.Column(db.String(128))
    dep_airport_country_iso2 = db.Column(db.String(8))
    dep_airport_country_iso3 = db.Column(db.String(8))
    dep_airport_latitude = db.Column(db.Float)
    dep_airport_longitude = db.Column(db.Float)
    dep_airport_tz = db.Column(db.String(64))
    dep_airport_tz_diff_utc = db.Column(db.Float)
    scheduled_departure = db.Column(db.DateTime)
    estimated_departure = db.Column(db.DateTime)
    actual_departure = db.Column(db.DateTime)
    actual_takeoff = db.Column(db.DateTime)
    calculated_takeoff = db.Column(db.DateTime)
    arr_airport_icao = db.Column(db.String(16))
    arr_airport_iata = db.Column(db.String(16))
    arr_airport_name = db.Column(db.String(255))
    arr_airport_city = db.Column(db.String(128))
    arr_airport_state = db.Column(db.String(128))
    arr_airport_country = db.Column(db.String(128))
    arr_airport_country_iso2 = db.Column(db.String(8))
    arr_airport_country_iso3 = db.Column(db.String(8))
    arr_airport_latitude = db.Column(db.Float)
    arr_airport_longitude = db.Column(db.Float)
    arr_airport_tz = db.Column(db.String(64))
    arr_airport_tz_diff_utc = db.Column(db.Float)
    scheduled_arrival = db.Column(db.DateTime)
    estimated_arrival = db.Column(db.DateTime)
    actual_arrival = db.Column(db.DateTime)
    actual_landing = db.Column(db.DateTime)
    calculated_landing = db.Column(db.DateTime)
    departure_status = db.Column(db.String(16))
    departure_delay_reason = db.Column(db.String(32))
    departure_delay_detail = db.Column(db.String(32))
    departure_gate = db.Column(db.String(16))
    departure_terminal = db.Column(db.String(16))
    arrival_status = db.Column(db.String(16))
    arrival_delay_reason = db.Column(db.String(32))
    arrival_delay_detail = db.Column(db.String(32))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    squawk_code = db.Column(db.Integer)
    distance = db.Column(db.Integer)
    duration = db.Column(db.Integer)
    planned_duration = db.Column(db.Integer)
    source = db.Column(db.String(32))
    created = db.Column(db.DateTime)
    updated = db.Column(db.DateTime)
    flight_url = db.Column(db.Text)
    flight_kml = db.Column(db.Text)
    flight_csv = db.Column(db.Text)
    flight_geojson = db.Column(db.Text)
    icao_route = db.Column(db.Text)
    waypoints = db.Column(db.Text)
    status = db.Column(db.String(32))
    raw_payload = db.Column(db.JSON, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class Aircraft(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    registration = db.Column(db.String(32), unique=True, nullable=False)
    type = db.Column(db.String(64))
    icao_type = db.Column(db.String(16))
    manufacturer = db.Column(db.String(64))
    mode_s = db.Column(db.String(16))
    registered_owner_country_iso_name = db.Column(db.String(8))
    registered_owner_country_name = db.Column(db.String(128))
    registered_owner_operator_flag_code = db.Column(db.String(16))
    registered_owner = db.Column(db.String(255))
    url_photo = db.Column(db.Text)
    url_photo_thumbnail = db.Column(db.Text)
    source_url = db.Column(db.Text)
    raw_payload = db.Column(db.JSON)
    fetched_at = db.Column(db.DateTime)

    sync_revision = db.Column(db.BigInteger, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class SyncState(db.Model):
    __tablename__ = "sync_state"
    id = db.Column(db.Integer, primary_key=True, default=1)
    current_revision = db.Column(db.BigInteger, nullable=False, default=0)

    __table_args__ = (
        db.CheckConstraint("id = 1", name="sync_state_singleton"),
    )

    @classmethod
    def bump(cls):
        """Increment and return the next global sync revision."""
        state = cls.query.first()
        if state is None:
            state = cls(id=1, current_revision=1)
            db.session.add(state)
        else:
            state.current_revision += 1
        db.session.flush()
        return state.current_revision

    @classmethod
    def current(cls):
        state = cls.query.first()
        return state.current_revision if state else 0


class ApiUser(db.Model):
    __tablename__ = "api_user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_login = db.Column(db.DateTime)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
