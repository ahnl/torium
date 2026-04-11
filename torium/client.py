"""
ToriClient — base HTTP client with automatic auth and finn-gw-key signing.

All API namespaces (listings, messaging, favorites) hang off this class.
"""

import json
import urllib.parse
from typing import Callable, Optional

import requests

from .auth import ToriAuth
from .signing import gw_key

BASE_URL = "https://apps-gw-poc.svc.tori.fi"
ADINPUT_BASE_URL = "https://apps-adinput.svc.tori.fi"
_ADINPUT_VERSION = "boatmotor"

_STATIC_HEADERS = {
    "finn-device-info": "iOS, mobile",
    "x-nmp-os-name": "iOS",
    "x-nmp-app-brand": "Tori",
    "x-nmp-os-version": "26.3.1",
    "x-nmp-device": "iPhone",
    "x-nmp-app-version-name": "26.16.0",
    "x-nmp-app-build-number": "26903",
    "buildnumber": "26903",
    "finn-app-installation-id": "hiRMP4JIWqQ",
    "ab-test-device-id": "632EB4DA-E226-4598-B6E9-44FA53B72BBD",
    "cmp-analytics": "1",
    "cmp-personalisation": "1",
    "cmp-marketing": "1",
    "cmp-advertising": "1",
    "accept": "application/json; charset=UTF-8",
    "accept-language": "en-GB,en;q=0.9",
    "user-agent": (
        "ToriApp_iOS/26.16.0-26903 (iPhone; CPU iPhone OS 26.3.1 like Mac OS X) "
        " ToriNativeApp(UA spoofed for tracking) ToriApp_iOS"
    ),
}


class ToriClient:
    """
    Top-level client. Provides access to all API namespaces.

    Examples:
        client = ToriClient()                        # uses ~/.config/tori/credentials.json
        client = ToriClient(refresh_token="eyJ...")  # explicit refresh token

        listings = client.listings.search(facet="ACTIVE")
        client.listings.dispose(12345)

        convs = client.messaging.list_conversations()
        client.messaging.send(conv_id, "Kiinnostaa!")

        client.favorites.list()
    """

    def __init__(
        self,
        refresh_token: Optional[str] = None,
        save_on_refresh: bool = True,
        on_refresh: Optional[Callable[[str, int], None]] = None,
    ):
        self.auth = ToriAuth(refresh_token, save_on_refresh=save_on_refresh, on_refresh=on_refresh)
        self._session = requests.Session()
        self._listings = None
        self._messaging = None
        self._favorites = None
        self._search = None

    @property
    def user_id(self) -> int:
        """Current user's ID. Available after first API call."""
        self.auth.get_bearer()
        return self.auth.user_id  # type: ignore[return-value]

    @property
    def listings(self):
        if self._listings is None:
            from .listings import ListingsAPI
            self._listings = ListingsAPI(self)
        return self._listings

    @property
    def messaging(self):
        if self._messaging is None:
            from .messaging import MessagingAPI
            self._messaging = MessagingAPI(self)
        return self._messaging

    @property
    def favorites(self):
        if self._favorites is None:
            from .favorites import FavoritesAPI
            self._favorites = FavoritesAPI(self)
        return self._favorites

    @property
    def search(self):
        if self._search is None:
            from .search import SearchAPI
            self._search = SearchAPI(self)
        return self._search

    # ── Internal request machinery ────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        service: str,
        json_body: Optional[dict] = None,
        _retried: bool = False,
    ) -> requests.Response:
        parsed = urllib.parse.urlparse(path)
        clean_path = parsed.path
        query = parsed.query

        body = json.dumps(json_body, ensure_ascii=False).encode("utf-8") if json_body is not None else b""
        bearer = self.auth.get_bearer()

        headers = {
            **_STATIC_HEADERS,
            "authorization": f"Bearer {bearer}",
            "finn-gw-service": service,
            "finn-gw-key": gw_key(method, clean_path, service, body, query),
        }
        if body:
            headers["content-type"] = "application/json; charset=UTF-8"

        url = BASE_URL + path
        resp = self._session.request(
            method, url, headers=headers, data=body or None
        )

        if resp.status_code in (401, 403) and not _retried:
            self.auth.refresh()
            return self._request(method, path, service, json_body, _retried=True)

        if not resp.ok:
            body_preview = resp.text[:500] if resp.text else "(empty)"
            raise requests.HTTPError(
                f"{resp.status_code} {resp.reason} for url: {resp.url}\nResponse body: {body_preview}",
                response=resp,
            )
        return resp

    def get(self, path: str, service: str) -> dict:
        return self._request("GET", path, service).json()

    def post(self, path: str, service: str, json_body: Optional[dict] = None) -> dict:
        resp = self._request("POST", path, service, json_body)
        return resp.json() if resp.content else {}

    def put(self, path: str, service: str, json_body: Optional[dict] = None) -> None:
        self._request("PUT", path, service, json_body)

    def delete(self, path: str, service: str) -> None:
        self._request("DELETE", path, service)

    # ── Adinput service (different subdomain) ─────────────────────────────────

    def adinput_get(self, path: str) -> tuple[dict, str]:
        """
        GET from the adinput subdomain. Returns (response_json, etag).
        Uses finn-gw-service: APPS-ADINPUT.
        """
        bearer = self.auth.get_bearer()
        key = gw_key("GET", path, "APPS-ADINPUT")
        headers = {
            **_STATIC_HEADERS,
            "authorization": f"Bearer {bearer}",
            "finn-gw-service": "APPS-ADINPUT",
            "finn-gw-key": key,
            "x-finn-apps-adinput-version-name": _ADINPUT_VERSION,
        }
        url = ADINPUT_BASE_URL + path
        resp = self._session.get(url, headers=headers)
        if resp.status_code in (401, 403):
            self.auth.refresh()
            return self.adinput_get(path)
        resp.raise_for_status()
        return resp.json(), resp.headers.get("ETag", "")

    def adinput_upload_image(self, ad_id: int, image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
        """
        Upload one image to a listing via the adinput upload endpoint.
        POST /adinput/ad/recommerce/{adId}/upload — multipart/form-data, no finn-gw-service.
        Signed with empty body (gw_key ignores multipart payload).
        Returns the Location URL (img.tori.net URL of the uploaded image).
        """
        path = f"/adinput/ad/recommerce/{ad_id}/upload"
        bearer = self.auth.get_bearer()
        key = gw_key("POST", path, "", b"")  # signed with empty body
        # Don't include content-type here — let requests set it from files= so
        # the boundary is consistent between header and body.
        headers = {
            **_STATIC_HEADERS,
            "authorization": f"Bearer {bearer}",
            "finn-gw-key": key,
            "x-finn-apps-adinput-version-name": _ADINPUT_VERSION,
            "upload-draft-interop-version": "6",
            "upload-complete": "?1",
        }
        # Remove accept-encoding so requests doesn't compress our upload
        headers.pop("accept-encoding", None)
        url = ADINPUT_BASE_URL + path
        files = {"file": ("image", image_bytes, mime_type)}
        resp = self._session.post(url, headers=headers, files=files)
        if resp.status_code in (401, 403):
            self.auth.refresh()
            return self.adinput_upload_image(ad_id, image_bytes, mime_type)
        resp.raise_for_status()
        return resp.headers.get("location", "")

    def adinput_post(
        self,
        path: str,
        service: str = "",
        body: bytes = b"",
        content_type: Optional[str] = None,
    ) -> tuple[dict, str, str]:
        """
        POST to the adinput subdomain.
        Returns (response_json, etag, location).
        """
        bearer = self.auth.get_bearer()
        key = gw_key("POST", path, service, body)
        headers = {
            **_STATIC_HEADERS,
            "authorization": f"Bearer {bearer}",
            "finn-gw-key": key,
            "x-finn-apps-adinput-version-name": _ADINPUT_VERSION,
            "content-length": str(len(body)),
        }
        if service:
            headers["finn-gw-service"] = service
        if content_type:
            headers["content-type"] = content_type
        url = ADINPUT_BASE_URL + path
        resp = self._session.post(url, headers=headers, data=body or None)
        if resp.status_code in (401, 403):
            self.auth.refresh()
            return self.adinput_post(path, service, body, content_type)
        resp.raise_for_status()
        data = resp.json() if resp.content else {}
        etag = resp.headers.get("ETag", "")
        location = resp.headers.get("Location", "")
        return data, etag, location

    def adinput_put(self, path: str, json_body: dict, etag: str) -> dict:
        """
        PUT to the adinput subdomain. No finn-gw-service header on PUT.
        Requires If-Match: <etag> for optimistic locking.
        Returns response JSON.
        """
        body = json.dumps(json_body).encode()
        bearer = self.auth.get_bearer()
        key = gw_key("PUT", path, "", body)
        headers = {
            **_STATIC_HEADERS,
            "authorization": f"Bearer {bearer}",
            "finn-gw-key": key,
            "x-finn-apps-adinput-version-name": _ADINPUT_VERSION,
            "If-Match": etag,
            "content-type": "application/json",
        }
        url = ADINPUT_BASE_URL + path
        resp = self._session.put(url, headers=headers, data=body)
        if resp.status_code in (401, 403):
            self.auth.refresh()
            return self.adinput_put(path, json_body, etag)
        resp.raise_for_status()
        return resp.json() if resp.content else {}
