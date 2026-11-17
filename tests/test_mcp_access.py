"""The MCP server's optional Cloudflare Access check (app/mcp_access.py)."""
import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
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


class _JWKSServer:
    """Serves a JWK Set to the real PyJWKClient in place of the network."""

    def __init__(self, *keys):
        self.jwks = {"keys": [
            {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(k.public_key())),
             "kid": kid, "alg": "RS256", "use": "sig"}
            for kid, k in keys
        ]}
        self.urls = []

    def fetch_data(self, client):
        self.urls.append(client.uri)
        return json.loads(json.dumps(self.jwks))


@pytest.fixture
def real_jwks(monkeypatch):
    """AccessConfig with its real PyJWKClient (key parsing, kid lookup,
    caching); only the HTTP fetch of the certs URL is faked."""
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "example.cloudflareaccess.com")
    monkeypatch.setenv("CF_ACCESS_AUD", AUD)
    server = _JWKSServer(("test", PRIVATE_KEY))
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data",
                        lambda client: server.fetch_data(client))
    return mcp_access.AccessConfig(), server


def test_verify_loads_the_signing_key_from_the_access_certs(real_jwks):
    cfg, server = real_jwks
    claims = mcp_access.verify(cfg, _token())
    assert claims is not None
    assert claims["email"] == "someone@example.com"
    assert claims["iss"] == TEAM and claims["aud"] == [AUD]
    assert server.urls == [cfg.certs_url]
    # The key set is cached: a second token does not refetch the certs.
    assert mcp_access.verify(cfg, _token()) is not None
    assert len(server.urls) == 1


def _public_pem():
    return PRIVATE_KEY.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


@pytest.mark.parametrize("make_token", [
    lambda: _token(key=OTHER_KEY),
    lambda: jwt.encode({"iss": TEAM, "aud": [AUD]}, PRIVATE_KEY, algorithm="RS256",
                       headers={"kid": "unknown"}),
    # HS256 signed with the published public key as the HMAC secret: the
    # classic algorithm-confusion forgery, with the line endings mutated
    # the way GHSA-ffc3-869f-jxw9 describes.
    lambda: _forge_hs256(_public_pem()),
    lambda: _forge_hs256(_public_pem().replace(b"\n", b"\r\n")),
    lambda: _forge_hs256(b"  " + _public_pem()),
    lambda: _token(aud=["another-application"]),
    lambda: _token(iss="https://other-team.cloudflareaccess.com"),
    lambda: _token(exp=int(time.time()) - 60),
], ids=["wrong-key", "unknown-kid", "hs256-public-pem", "hs256-crlf-pem",
        "hs256-whitespace-pem", "wrong-aud", "wrong-iss", "expired"])
def test_verify_rejects_forged_or_foreign_tokens(real_jwks, make_token):
    cfg, _ = real_jwks
    assert mcp_access.verify(cfg, make_token()) is None


def _forge_hs256(secret: bytes) -> str:
    """Sign HS256 by hand: PyJWT itself refuses PEM material as an HMAC key."""
    now = int(time.time())

    def b64(data: bytes) -> bytes:
        return base64.urlsafe_b64encode(data).rstrip(b"=")

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": "test"}).encode())
    payload = b64(json.dumps({"iss": TEAM, "aud": [AUD], "iat": now,
                              "exp": now + 300}).encode())
    signing_input = header + b"." + payload
    signature = b64(hmac.new(secret, signing_input, hashlib.sha256).digest())
    return (signing_input + b"." + signature).decode()


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
