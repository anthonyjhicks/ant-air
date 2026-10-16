"""The MCP server's optional Cloudflare Access check (app/mcp_access.py)."""
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient

from app import mcp_access, mcp_server

TEAM = "https://example.cloudflareaccess.com"
AUD = "test-application-aud"

PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _SigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKS:
    """Stands in for PyJWKClient: serves the test public key, no network."""

    def get_signing_key_from_jwt(self, token):
        return _SigningKey(PRIVATE_KEY.public_key())


def _token(key=PRIVATE_KEY, **overrides):
    now = int(time.time())
    claims = {"iss": TEAM, "aud": [AUD], "iat": now, "exp": now + 300,
              "email": "someone@example.com"}
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test"})


@pytest.fixture
def access_env(monkeypatch):
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "example.cloudflareaccess.com")
    monkeypatch.setenv("CF_ACCESS_AUD", AUD)
    monkeypatch.setattr(mcp_access.AccessConfig, "jwks",
                        property(lambda self: _FakeJWKS()))


@pytest.fixture
def guarded(access_env):
    """The middleware around a trivial app that answers 200 "ok"."""
    async def inner(scope, receive, send):
        await PlainTextResponse("ok")(scope, receive, send)

    cfg = mcp_access.AccessConfig()
    return TestClient(mcp_server._CloudflareAccessMiddleware(inner, cfg))


def _post(client, path="/mcp", token=None):
    headers = {"Cf-Access-Jwt-Assertion": token} if token else {}
    return client.post(path, headers=headers, json={})


def test_config_normalises_team_domain(access_env):
    cfg = mcp_access.AccessConfig()
    assert cfg.enabled and not cfg.partial
    assert cfg.team_domain == TEAM
    assert cfg.certs_url == f"{TEAM}/cdn-cgi/access/certs"


def test_valid_access_jwt_is_let_through(guarded):
    response = _post(guarded, token=_token())
    assert response.status_code == 200
    assert response.text == "ok"


@pytest.mark.parametrize("token", [
    None,
    "not-a-jwt",
    _token(aud=["another-application"]),
    _token(iss="https://other-team.cloudflareaccess.com"),
    _token(exp=int(time.time()) - 60),
    _token(iat=None),
    _token(key=OTHER_KEY),
    jwt.encode({"iss": TEAM, "aud": [AUD], "iat": int(time.time()),
                "exp": int(time.time()) + 300}, "shared-secret", algorithm="HS256"),
], ids=["missing", "garbage", "wrong-aud", "wrong-iss", "expired",
        "no-iat", "wrong-key", "hs256"])
def test_requests_without_a_valid_access_jwt_get_403(guarded, token):
    response = _post(guarded, token=token)
    assert response.status_code == 403
    assert response.json()["error"] == "forbidden"


def test_healthz_stays_open(guarded):
    assert guarded.get("/healthz").status_code == 200


def test_access_check_is_off_without_configuration(monkeypatch):
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    app = mcp_server.build_http_app()
    assert not isinstance(app, mcp_server._CloudflareAccessMiddleware)


def test_half_configured_access_refuses_to_start(monkeypatch):
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", TEAM)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    with pytest.raises(SystemExit):
        mcp_server.build_http_app()


def test_mcp_endpoint_requires_access_end_to_end(access_env):
    app = mcp_server.build_http_app()
    assert isinstance(app, mcp_server._CloudflareAccessMiddleware)
    initialize = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "test", "version": "0"}},
    }
    headers = {"Accept": "application/json, text/event-stream"}
    with TestClient(app) as client:
        denied = client.post("/mcp", json=initialize, headers=headers)
        assert denied.status_code == 403

        allowed = client.post(
            "/mcp", json=initialize,
            headers={**headers, "Cf-Access-Jwt-Assertion": _token()},
        )
        assert allowed.status_code == 200
        assert '"name":"ant-air"' in allowed.text.replace(" ", "")
