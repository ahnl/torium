"""
Favorites API.

Endpoints:
  GET  /favorites/minimal               all favorited item IDs (FAVORITE-MANAGEMENT)
  GET  /favorites                       full favorite objects with metadata
  PUT  /favorites/{folderId}/{itemType}/{adId}   add to favorites
  GET  /favorites/{adId}/counter        number of users who favorited a listing
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import ToriClient

_SVC = "FAVORITE-MANAGEMENT"
_DEFAULT_FOLDER = 0


class FavoritesAPI:
    def __init__(self, client: "ToriClient"):
        self._c = client

    def list(self) -> dict:
        """
        All favorited items with folder assignments.
        Response: {"items": [{"itemType": "Ad", "itemId": 123, "folderIds": [0]}, ...]}
        """
        return self._c.get("/favorites/minimal", _SVC)

    def list_full(self) -> dict:
        """Full favorite objects with listing metadata."""
        return self._c.get("/favorites", _SVC)

    def add(self, ad_id: int, item_type: str = "recommerce", folder_id: int = _DEFAULT_FOLDER) -> None:
        """Add a listing to favorites. Returns 204."""
        self._c.put(f"/favorites/{folder_id}/{item_type}/{ad_id}", _SVC)

    def counter(self, ad_id: int) -> int:
        """Number of users who have favorited a listing."""
        data = self._c.get(f"/favorites/{ad_id}/counter", _SVC)
        return data.get("count", data)
