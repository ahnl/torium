"""
Tori.fi authentication.

Three-step flow (fully scriptable, no browser after initial setup):
  1. POST https://login.vend.fi/oauth/token       — exchange refresh token for access token
  2. POST https://login.vend.fi/api/2/oauth/exchange — get one-time spidCode
  3. POST https://apps-gw-poc.svc.tori.fi/public/login — exchange spidCode for tori Bearer

Credentials are stored in ~/.config/tori/credentials.json.
Override with env var TORI_REFRESH_TOKEN.

For first-time setup (browser OAuth flow), run: python auth_setup.py
"""

import json
import os
import threading
from typing import Callable, Optional, Tuple

import requests

from .signing import gw_key

CLIENT_ID = "6079834b9b0b741812e7e91f"
SPID_SERVER_CLIENT_ID = "650421cf50eeae31ecd2a2d3"
CREDENTIALS_PATH = os.path.expanduser("~/.config/tori/credentials.json")


def load_credentials() -> dict:
    env = os.environ.get("TORI_REFRESH_TOKEN")
    if env:
        return {"refresh_token": env}
    if os.path.exists(CREDENTIALS_PATH):
        with open(CREDENTIALS_PATH) as f:
            return json.load(f)
    raise RuntimeError(
        "No credentials found. Run 'tori auth setup' or set TORI_REFRESH_TOKEN."
    )


def save_credentials(refresh_token: str, user_id: Optional[int] = None) -> None:
    os.makedirs(os.path.dirname(CREDENTIALS_PATH), exist_ok=True)
    data: dict = {"refresh_token": refresh_token}
    if user_id is not None:
        data["user_id"] = user_id
    with open(CREDENTIALS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def get_tori_token(refresh_token: str) -> Tuple[str, str, int]:
    """
    Exchange a Schibsted refresh token for a tori Bearer token.

    Returns:
        (bearer_token, new_refresh_token, user_id)

    The refresh token rotates on each call — save the new one.
    Bearer is valid ~1h; refresh token is valid ~1 year.
    """
    # Step 1: Schibsted token refresh
    r1 = requests.post(
        "https://login.vend.fi/oauth/token",
        headers={"X-OIDC": "v1"},
        data={
            "client_id": CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )
    r1.raise_for_status()
    access_token = r1.json()["access_token"]
    new_refresh = r1.json()["refresh_token"]

    # Step 2: exchange access token for one-time spidCode
    r2 = requests.post(
        "https://login.vend.fi/api/2/oauth/exchange",
        headers={"Authorization": f"Bearer {access_token}"},
        data={"clientId": SPID_SERVER_CLIENT_ID, "type": "code"},
    )
    r2.raise_for_status()
    spid_code = r2.json()["data"]["code"]

    # Step 3: exchange spidCode for tori Bearer
    body = json.dumps({"spidCode": spid_code, "deviceId": CLIENT_ID}).encode()
    r3 = requests.post(
        "https://apps-gw-poc.svc.tori.fi/public/login",
        headers={
            "finn-gw-key": gw_key("POST", "/public/login", "LOGIN-SERVER-AUTH", body),
            "finn-gw-service": "LOGIN-SERVER-AUTH",
            "content-type": "application/json",
            "user-agent": "ToriApp_iOS/26.16.0-26903",
        },
        data=body,
    )
    r3.raise_for_status()
    data = r3.json()
    return data["token"]["value"], new_refresh, data["userId"]


class ToriAuth:
    """
    Manages a tori Bearer token. Refreshes lazily on first use.

    Usage:
        auth = ToriAuth()                        # load from ~/.config/tori/credentials.json
        auth = ToriAuth(refresh_token="eyJ...")  # explicit
        bearer = auth.get_bearer()
        auth.user_id  # available after first get_bearer() call
    """

    def __init__(
        self,
        refresh_token: Optional[str] = None,
        save_on_refresh: bool = True,
        on_refresh: Optional[Callable[[str, int], None]] = None,
    ):
        if refresh_token is None:
            creds = load_credentials()
            refresh_token = creds["refresh_token"]
            self.user_id: Optional[int] = creds.get("user_id")
        else:
            self.user_id = None
        self._refresh_token = refresh_token
        self._bearer: Optional[str] = None
        self._lock = threading.Lock()
        self._save_on_refresh = save_on_refresh
        self._on_refresh = on_refresh

    def get_bearer(self) -> str:
        if self._bearer is None:
            with self._lock:
                if self._bearer is None:  # double-checked locking
                    self._do_refresh()
        return self._bearer  # type: ignore[return-value]

    def refresh(self) -> str:
        """Force-refresh the Bearer token (call after a 401/403)."""
        with self._lock:
            self._do_refresh()
        return self._bearer  # type: ignore[return-value]

    def _do_refresh(self) -> None:
        bearer, new_refresh, user_id = get_tori_token(self._refresh_token)
        self._bearer = bearer
        self._refresh_token = new_refresh
        self.user_id = user_id
        if self._save_on_refresh:
            save_credentials(new_refresh, user_id)
        if self._on_refresh is not None:
            self._on_refresh(new_refresh, user_id)
