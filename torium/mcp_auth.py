"""
MCP-level OAuth 2.1 authorization server for torium-mcp.

Wraps the existing Tori.fi / Schibsted login using the same "paste the redirect
URL" technique documented in the README for Windows/Linux.

Flow:
  1. Claude calls GET /authorize → we redirect to /tori-login
  2. /tori-login shows a "Log in to Tori.fi" button + paste form
  3. User logs in → browser fails on fi.tori.www...://login → user copies URL
  4. User pastes URL into form → POST /tori-login
  5. Server exchanges Schibsted code → gets Tori refresh token
  6. fetch_tori_identity() calls GET /v2/me → extracts email + user_id
  7. Checks email against allowlist in SQLite
  8. Persists per-user Tori session in SQLite
  9. Issues MCP access + refresh tokens (also in SQLite) → redirects to Claude callback

Multi-tenancy:
  All tokens are per-user. Each user's Tori refresh token is stored in tori_sessions
  keyed by tori user_id. MCP tokens (access + refresh) are stored in mcp_access_tokens
  and mcp_refresh_tokens, both linked to tori_sessions by user_id. A per-user ToriClient
  cache in mcp_server.py avoids redundant auth round-trips within the token's ~1h lifetime.
"""

import base64
import hashlib
import json
import secrets
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import requests

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

if TYPE_CHECKING:
    from .mcp_storage import Storage

from .auth import CLIENT_ID as _SCHIBSTED_CLIENT_ID, REDIRECT_URI as _REDIRECT_URI

_SCHIBSTED_AUTH_URL = "https://login.vend.fi/oauth/authorize"

MCP_ACCESS_TOKEN_TTL = 3600           # 1 hour
MCP_REFRESH_TOKEN_TTL = 180 * 86400   # 180 days
_AUTH_CODE_TTL = 300                  # 5 minutes


@dataclass
class _PendingAuth:
    """Stored per MCP OAuth state while the user is completing the login form."""
    client_id: str
    mcp_params: AuthorizationParams
    # Refreshed on every GET /tori-login so users can retry without restarting OAuth:
    schibsted_auth_url: str = ""
    pkce_verifier: str = ""
    schibsted_state: str = ""


@dataclass
class _StoredCode:
    """In-memory only; short-lived (5 min). Cleared after exchange."""
    user_id: int
    auth_code: AuthorizationCode


class ToriMCPAuthProvider(OAuthAuthorizationServerProvider):
    """
    Minimal MCP OAuth 2.1 authorization server.

    Implements OAuthAuthorizationServerProvider so FastMCP's built-in auth
    middleware handles token validation on every MCP request.

    All persistent state (clients, access tokens, refresh tokens, Tori sessions)
    is stored in SQLite via the Storage instance. Only _pending and _codes are
    in-memory because they are short-lived and bounded to active OAuth flows.
    """

    def __init__(self, base_url: str, storage: "Storage") -> None:
        self._base_url = base_url.rstrip("/")
        self._storage = storage
        self._pending: dict[str, _PendingAuth] = {}   # mcp_state → pending (in-memory)
        self._codes: dict[str, _StoredCode] = {}       # mcp auth code → stored (in-memory)

    # ── DCR ───────────────────────────────────────────────────────────────────

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        raw = self._storage.get_client_json(client_id)
        if raw is None:
            return None
        return OAuthClientInformationFull.model_validate_json(raw)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self._storage.put_client(client_info.client_id, client_info.model_dump_json())

    # ── Authorization ─────────────────────────────────────────────────────────

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        mcp_state = params.state or secrets.token_urlsafe(16)
        self._pending[mcp_state] = _PendingAuth(
            client_id=client.client_id,
            mcp_params=params,
        )
        # Schibsted URL is generated fresh on each GET /tori-login (so users can retry).
        return f"{self._base_url}/tori-login?state={urllib.parse.quote(mcp_state)}"

    def get_pending(self, mcp_state: str) -> _PendingAuth | None:
        return self._pending.get(mcp_state)

    def refresh_schibsted_session(self, mcp_state: str) -> _PendingAuth | None:
        """Generate a fresh Schibsted auth URL for this MCP state. Called on GET /tori-login."""
        pending = self._pending.get(mcp_state)
        if pending is None:
            return None

        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        schibsted_state = secrets.token_urlsafe(16)

        pending.pkce_verifier = verifier
        pending.schibsted_state = schibsted_state
        pending.schibsted_auth_url = _SCHIBSTED_AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": _SCHIBSTED_CLIENT_ID,
            "redirect_uri": _REDIRECT_URI,
            "response_type": "code",
            "scope": "openid offline_access",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": schibsted_state,
            "nonce": secrets.token_urlsafe(16),
        })
        return pending

    def complete_login(
        self,
        mcp_state: str,
        tori_refresh_token: str,
        user_id: int,
        email: str,
    ) -> str:
        """
        Called after successful Tori.fi authentication and identity verification.

        Persists the user's Tori session in SQLite, issues an MCP auth code,
        and returns the Claude callback redirect URL.

        The caller (POST /tori-login in mcp_server.py) is responsible for:
          - Checking the email against the allowlist before calling this.
          - Passing the rotated tori_refresh_token (from fetch_tori_identity).
        """
        pending = self._pending.pop(mcp_state, None)
        if pending is None:
            raise ValueError(f"No pending auth for state: {mcp_state!r}")

        # Persist the Tori session. This is also called on re-auth to rotate the token.
        self._storage.upsert_tori_session(user_id, email, tori_refresh_token)

        params = pending.mcp_params
        mcp_code = secrets.token_urlsafe(32)
        self._codes[mcp_code] = _StoredCode(
            user_id=user_id,
            auth_code=AuthorizationCode(
                code=mcp_code,
                scopes=params.scopes or [],
                expires_at=time.time() + _AUTH_CODE_TTL,
                client_id=pending.client_id,
                code_challenge=params.code_challenge,
                redirect_uri=params.redirect_uri,
                redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            ),
        )

        return construct_redirect_uri(str(params.redirect_uri), code=mcp_code, state=mcp_state)

    # ── Token exchange ─────────────────────────────────────────────────────────

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        stored = self._codes.get(authorization_code)
        if stored is None:
            return None
        if time.time() > stored.auth_code.expires_at:
            del self._codes[authorization_code]
            return None
        return stored.auth_code

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        stored = self._codes.pop(authorization_code.code, None)
        if stored is None:
            raise TokenError(error="invalid_grant", error_description="Authorization code not found")

        mcp_access = secrets.token_urlsafe(32)
        mcp_refresh = secrets.token_urlsafe(32)
        now = int(time.time())
        scopes = authorization_code.scopes

        self._storage.put_mcp_access(
            mcp_access, stored.user_id, client.client_id, scopes,
            expires_at=now + MCP_ACCESS_TOKEN_TTL,
        )
        self._storage.put_mcp_refresh(
            mcp_refresh, stored.user_id, client.client_id, scopes,
        )

        return OAuthToken(
            access_token=mcp_access,
            token_type="Bearer",
            expires_in=MCP_ACCESS_TOKEN_TTL,
            refresh_token=mcp_refresh,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        row = self._storage.get_mcp_refresh(refresh_token)
        if row is None or row["client_id"] != client.client_id:
            return None
        scopes = json.loads(row["scopes_json"])
        return RefreshToken(
            token=refresh_token,
            client_id=client.client_id,
            scopes=scopes,
            expires_at=None,
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        row = self._storage.pop_mcp_refresh(refresh_token.token)
        if row is None:
            raise TokenError(error="invalid_grant", error_description="Refresh token not found")

        user_id = row["user_id"]
        new_access = secrets.token_urlsafe(32)
        new_refresh = secrets.token_urlsafe(32)
        now = int(time.time())
        effective_scopes = scopes or json.loads(row["scopes_json"])

        self._storage.put_mcp_access(
            new_access, user_id, client.client_id, effective_scopes,
            expires_at=now + MCP_ACCESS_TOKEN_TTL,
        )
        self._storage.put_mcp_refresh(
            new_refresh, user_id, client.client_id, effective_scopes,
        )

        return OAuthToken(
            access_token=new_access,
            token_type="Bearer",
            expires_in=MCP_ACCESS_TOKEN_TTL,
            refresh_token=new_refresh,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        row = self._storage.get_mcp_access(token)
        if row is None:
            return None
        scopes = json.loads(row["scopes_json"])
        return AccessToken(
            token=token,
            client_id=row["client_id"],
            scopes=scopes,
            expires_at=row["expires_at"],
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        if isinstance(token, AccessToken):
            self._storage.delete_mcp_access(token.token)
        else:
            self._storage.pop_mcp_refresh(token.token)


# ── Schibsted code exchange ────────────────────────────────────────────────────

def exchange_schibsted_code(code: str, verifier: str) -> str:
    """Exchange a Schibsted authorization code + PKCE verifier for a Tori refresh token."""
    r = requests.post(
        "https://login.vend.fi/oauth/token",
        headers={"X-OIDC": "v1"},
        data={
            "client_id": _SCHIBSTED_CLIENT_ID,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _REDIRECT_URI,
            "code_verifier": verifier,
        },
    )
    r.raise_for_status()
    return r.json()["refresh_token"]


# ── Tori identity fetch ────────────────────────────────────────────────────────

def fetch_tori_identity(tori_refresh_token: str) -> tuple[str, int, str]:
    """
    After a successful Schibsted code exchange, call the Tori API to get the
    user's identity. Returns (new_refresh_token, user_id, email).

    This call rotates the Schibsted refresh token (standard behaviour) and then
    hits GET /v2/me on the Tori gateway using the resulting bearer, which returns
    identity.email and identity.localProfileId.

    The new_refresh_token must replace the initial one in storage so future token
    rotations have the latest value.
    """
    from .auth import get_tori_token
    from .signing import gw_key

    bearer, new_refresh, user_id = get_tori_token(tori_refresh_token)

    r = requests.get(
        "https://apps-gw-poc.svc.tori.fi/v2/me",
        headers={
            "authorization": f"Bearer {bearer}",
            "finn-gw-service": "TRUST-PROFILE-API",
            "finn-gw-key": gw_key("GET", "/v2/me", "TRUST-PROFILE-API"),
            "x-client-id": "com.schibsted.iberica.tori-260330-6c7b482",
            "finn-device-info": "iOS, mobile",
            "user-agent": "ToriApp_iOS/26.16.0-26903",
        },
    )
    r.raise_for_status()
    email = r.json()["identity"]["email"]

    return new_refresh, user_id, email
