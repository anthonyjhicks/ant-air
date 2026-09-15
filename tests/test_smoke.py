"""Render every page and API endpoint against the fictional demo data."""
import pytest

from app import create_app
from app.extensions import db

PAGES = [
    "/",
    "/flights",
    "/flights/new",
    "/flights/1/edit",
    "/aircraft",
    "/trips",
    "/trips/new",
    "/trips/1",
    "/trips/1/edit",
    "/timeline",
    "/achievements",
    "/insights",
    "/inbox",
    "/import",
    "/audit/duplicates",
    "/audit/duplicates/exact",
    "/audit/missing",
    "/audit/missing/airline",
    "/audit/missing/aircraft",
    "/audit/missing/registration",
    "/audit/missing/routes",
    "/audit/missing-legs",
    "/audit/routes/pair",
    "/audit/routes/pair?a=London&b=Lisbon",
    "/audit/gemini/guesses",
    "/audit/gemini/codeshares",
    "/admin/badges",
    "/admin/badges/new",
    "/utilities/scripts",
]


@pytest.fixture(scope="session")
def app():
    application = create_app()
    application.config["TESTING"] = True
    with application.app_context():
        db.create_all()
        import seed_demo_data  # scripts/ is on sys.path (see conftest.py)

        assert seed_demo_data.seed() == 0
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


def test_configuration_comes_from_environment(app):
    assert app.config["APP_NAME"] == "Ant Air"
    assert app.config["HOME_CITY"] == "London"
    assert app.config["HOME_AIRPORTS"] == ["LHR", "LGW", "LCY"]
    assert app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:///")


@pytest.mark.parametrize("path", PAGES)
def test_page_renders(client, path):
    response = client.get(path)
    assert response.status_code == 200, path
    assert b"Ant Air" in response.data


def test_dashboard_shows_demo_data(client):
    html = client.get("/").data.decode()
    assert "Your flight log" in html
    assert "boarding-pass__code" in html  # the seeded future flight
    assert "Sam Rivers" in html  # the fictional demo traveller in the filters


def test_health_reports_version(client):
    payload = client.get("/health").get_json()
    assert payload["status"] == "ok"
    assert payload["version"]


def test_search_finds_a_demo_flight(client):
    payload = client.get("/api/search?q=lisbon").get_json()
    assert payload
    assert "lisbon" in str(payload).lower()


def test_city_pair_audit_counts_both_directions(client):
    html = client.get("/audit/routes/pair?a=London&b=Lisbon").data.decode()
    assert "London → Lisbon" in html
    assert "Lisbon → London" in html


def test_missing_leg_audit_uses_home_base(client):
    html = client.get("/audit/missing-legs").data.decode()
    assert "London base" in html
