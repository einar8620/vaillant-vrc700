"""Keycloak authentication for the myVAILLANT cloud API.

OAuth2 authorization-code flow with PKCE. There is no official OIDC client,
so the login form action is scraped from the Keycloak HTML and credentials
are POSTed directly — the same approach the myVAILLANT app effectively uses.

Flow adapted from myPyllant (MIT, (c) 2023 Philipp Doerner).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import html as html_lib
import json
import logging
import re
import secrets
import time
from urllib.parse import parse_qs, urlparse

import aiohttp

_LOGGER = logging.getLogger(__name__)

CLIENT_ID = "myvaillant"
REDIRECT_URI = "enduservaillant.page.link://login"
IDENTITY_BASE = "https://identity.vaillant-group.com/auth/realms/{realm}"
AUTHENTICATE_URL = IDENTITY_BASE + "/protocol/openid-connect/auth"
TOKEN_URL = IDENTITY_BASE + "/protocol/openid-connect/token"
ALTCHA_CHALLENGE_URL = "https://identity.vaillant-group.com/api/altcha/challenge"

# Refresh the access token this many seconds before it actually expires.
TOKEN_EXPIRY_MARGIN = 180

# Hard timeout on every auth request (login page, credentials POST, token).
AUTH_TIMEOUT = aiohttp.ClientTimeout(total=30)

_FORM_ACTION_RE = re.compile(r'<form[^>]*\saction="([^"]+)"', re.IGNORECASE)


class AuthenticationError(Exception):
    """Raised when login or token refresh fails."""


def solve_altcha_challenge(challenge: dict) -> str:
    """Solve the ALTCHA proof-of-work challenge served by Vaillant's login page.

    Vaillant added an ALTCHA check to Keycloak (identity.vaillant-group.com);
    the credentials POST is rejected unless it carries a solved challenge in
    the "altcha" form field. This brute-forces the PBKDF2 proof-of-work and
    packages the solution the same way the browser widget does.

    `challenge` is the JSON body of GET /api/altcha/challenge, e.g.
    {"parameters": {"algorithm": "PBKDF2/SHA-256", "cost": 5000,
    "keyLength": 32, "keyPrefix": "00", "nonce": "...", "salt": "..."},
    "signature": "..."}

    CPU-bound — call via run_in_executor from async code.
    """
    parameters = challenge["parameters"]
    nonce_buf = bytes.fromhex(parameters["nonce"])
    salt_buf = bytes.fromhex(parameters["salt"])
    key_prefix_buf = bytes.fromhex(parameters["keyPrefix"])
    cost = parameters["cost"]
    key_length = parameters.get("keyLength", 32)
    digest = {
        "PBKDF2/SHA-512": "sha512",
        "PBKDF2/SHA-384": "sha384",
    }.get(parameters["algorithm"], "sha256")

    counter = 0
    while True:
        password = nonce_buf + counter.to_bytes(4, byteorder="big")
        derived = hashlib.pbkdf2_hmac(digest, password, salt_buf, cost, dklen=key_length)
        if derived.startswith(key_prefix_buf):
            solution = {"counter": counter, "derivedKey": derived.hex(), "time": 0}
            break
        counter += 1

    payload = {
        "challenge": {
            "parameters": parameters,
            "signature": challenge["signature"],
        },
        "solution": solution,
    }
    return base64.b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("utf-8")


def get_realm(brand: str, country: str | None = None) -> str:
    """Build the Keycloak realm name, e.g. vaillant-spain-b2c."""
    brand = brand.strip().lower()
    if country:
        return f"{brand}-{country.strip().lower().replace(' ', '-')}-b2c"
    return f"{brand}-b2c"


class VaillantAuth:
    """Handles login, token storage and refresh against Keycloak."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        brand: str = "vaillant",
        country: str | None = None,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self.realm = get_realm(brand, country)
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: float = 0.0

    @property
    def access_token(self) -> str | None:
        return self._access_token

    async def get_access_token(self) -> str:
        """Return a valid access token, refreshing or re-logging in as needed."""
        if self._access_token and time.time() < self._expires_at - TOKEN_EXPIRY_MARGIN:
            return self._access_token
        if self._refresh_token:
            try:
                await self._refresh()
                return self._access_token  # type: ignore[return-value]
            except AuthenticationError:
                _LOGGER.debug("Token refresh failed, performing full login")
        await self.login()
        return self._access_token  # type: ignore[return-value]

    async def login(self) -> None:
        """Full PKCE login with username/password."""
        code_verifier = secrets.token_urlsafe(96)[:128]
        code_challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode("ascii")).digest()
            )
            .rstrip(b"=")
            .decode("ascii")
        )

        auth_url = AUTHENTICATE_URL.format(realm=self.realm)
        params = {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": "openid",
            "code": "code_challenge",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        async with self._session.get(
            auth_url, params=params, timeout=AUTH_TIMEOUT
        ) as resp:
            if resp.status != 200:
                raise AuthenticationError(
                    f"Keycloak auth page returned HTTP {resp.status} "
                    f"(realm '{self.realm}' — check brand/country)"
                )
            page = await resp.text()

        match = _FORM_ACTION_RE.search(page)
        if not match:
            raise AuthenticationError(
                "Could not find login form on the Keycloak page "
                "(Vaillant may have changed the login flow)"
            )
        login_url = html_lib.unescape(match.group(1))

        login_data = {
            "username": self._username,
            "password": self._password,
            "credentialId": "",
        }
        try:
            async with self._session.get(
                ALTCHA_CHALLENGE_URL, timeout=AUTH_TIMEOUT
            ) as resp:
                if resp.status == 200:
                    challenge = await resp.json()
                    login_data["altcha"] = await asyncio.get_running_loop(
                    ).run_in_executor(None, solve_altcha_challenge, challenge)
        except Exception:
            _LOGGER.debug(
                "Could not fetch or solve ALTCHA challenge, continuing without it",
                exc_info=True,
            )

        async with self._session.post(
            login_url,
            data=login_data,
            allow_redirects=False,
            timeout=AUTH_TIMEOUT,
        ) as resp:
            location = resp.headers.get("Location", "")
            if resp.status != 302 or "code=" not in location:
                raise AuthenticationError(
                    "Login failed — check username/password "
                    f"(HTTP {resp.status})"
                )
        code = parse_qs(urlparse(location).query)["code"][0]

        await self._request_token(
            {
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": REDIRECT_URI,
            }
        )
        _LOGGER.debug("Login successful (realm %s)", self.realm)

    async def _refresh(self) -> None:
        await self._request_token(
            {
                "grant_type": "refresh_token",
                "client_id": CLIENT_ID,
                "refresh_token": self._refresh_token,
            }
        )
        _LOGGER.debug("Access token refreshed")

    async def _request_token(self, data: dict) -> None:
        token_url = TOKEN_URL.format(realm=self.realm)
        async with self._session.post(
            token_url, data=data, timeout=AUTH_TIMEOUT
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise AuthenticationError(
                    f"Token request failed: HTTP {resp.status} {body[:200]}"
                )
            token = await resp.json()
        self._access_token = token["access_token"]
        self._refresh_token = token.get("refresh_token", self._refresh_token)
        self._expires_at = time.time() + token.get("expires_in", 300)
