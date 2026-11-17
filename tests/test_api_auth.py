"""HS256 tokens for the /api/v1/ endpoints (app/api_auth.py)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest

from app import create_app
from app.api_auth import create_access_token, create_refresh_token, decode_token

USER = SimpleNamespace(username="sam", id=7)


@pytest.fixture
def app_ctx():
    application = create_app()
    with application.app_context():
        yield application


def test_access_token_round_trips(app_ctx):
    payload = decode_token(create_access_token(USER, client_id="ios"))
    assert payload["sub"] == "sam"
    assert payload["user_id"] == 7
    assert payload["type"] == "access"
    assert payload["client_id"] == "ios"


def test_refresh_token_round_trips(app_ctx):
    assert decode_token(create_refresh_token(USER))["type"] == "refresh"


def _encode(claims, key="test-secret", algorithm="HS256"):
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": "sam", "type": "access", "iat": now,
                       "exp": now + timedelta(minutes=5), **claims},
                      key, algorithm=algorithm)


@pytest.mark.parametrize("token", [
    "not-a-jwt",
    _encode({}, key="another-secret"),
    _encode({"exp": datetime.now(timezone.utc) - timedelta(minutes=1)}),
    _encode({}, key="test-secret", algorithm="HS512"),
], ids=["garbage", "wrong-secret", "expired", "wrong-alg"])
def test_bad_tokens_are_rejected(app_ctx, token):
    assert decode_token(token) is None


def test_tampered_payload_is_rejected(app_ctx):
    header, _, signature = create_access_token(USER).split(".")
    forged = jwt.utils.base64url_encode(b'{"sub":"admin","type":"access"}').decode()
    assert decode_token(f"{header}.{forged}.{signature}") is None
