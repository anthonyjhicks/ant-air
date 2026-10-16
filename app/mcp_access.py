"""Cloudflare Access verification for the MCP server's HTTP transport.

Optional: it only applies when CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD are
both set, for an MCP endpoint published through a Cloudflare Tunnel and
protected by a Cloudflare Access self-hosted application (typically with
Managed OAuth turned on, so Claude can sign in through Access):

- Access is the OAuth authorization server. It answers clients that still
  need to sign in with 401 + RFC 9728 metadata, registers clients, runs the
  identity-provider sign-in and issues tokens. Service tokens
  (CF-Access-Client-Id / CF-Access-Client-Secret) work too.
- Every request Access lets through carries a signed JWT in the
  Cf-Access-Jwt-Assertion header. Cloudflare recommends that the origin
  validate it; doing so also keeps the server closed to requests that reach
  it some other way (a LAN address, a NodePort, another pod) and stays
  closed if the Access application is ever removed.

The JWT is RS256, signed by keys published at
<team domain>/cdn-cgi/access/certs, with iss = the team domain and an aud
list containing the Access application's AUD tag.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import jwt

logger = logging.getLogger(__name__)

HEADER = "cf-access-jwt-assertion"
ALGORITHMS = ["RS256"]

# How long a known-good key set is reused. A rotated key doesn't wait for
# this: PyJWKClient refetches on an unknown kid.
JWKS_CACHE_SECONDS = 60 * 60


class AccessConfig:
    """Read from the environment; enabled only when both values are set."""

    def __init__(self) -> None:
        team = os.environ.get("CF_ACCESS_TEAM_DOMAIN", "").strip().rstrip("/")
        if team and "://" not in team:
            team = f"https://{team}"
        self.team_domain: str = team
        self.aud: str = os.environ.get("CF_ACCESS_AUD", "").strip()
        self._jwks: jwt.PyJWKClient | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.team_domain and self.aud)

    @property
    def partial(self) -> bool:
        """Exactly one of the two settings is present: a misconfiguration."""
        return bool(self.team_domain) != bool(self.aud)

    @property
    def certs_url(self) -> str:
        return f"{self.team_domain}/cdn-cgi/access/certs"

    @property
    def jwks(self) -> jwt.PyJWKClient:
        if self._jwks is None:
            self._jwks = jwt.PyJWKClient(
                self.certs_url, cache_jwk_set=True, lifespan=JWKS_CACHE_SECONDS
            )
        return self._jwks


def verify(cfg: AccessConfig, token: str) -> dict[str, Any] | None:
    """Return the token's claims if Access signed it for this application, else None.

    Blocking: on a cold or stale key cache PyJWKClient fetches the certs URL,
    so call this from a worker thread when on the event loop.
    """
    if not token:
        return None
    try:
        key = cfg.jwks.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            key.key,
            algorithms=ALGORITHMS,
            audience=cfg.aud,
            issuer=cfg.team_domain,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
    except jwt.PyJWTError as exc:  # includes PyJWKClientError (certs fetch failed)
        logger.warning("Rejected Cf-Access-Jwt-Assertion: %s", exc)
        return None
