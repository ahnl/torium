"""
Listings API — my listings and per-listing actions.

Endpoints:
  GET  /search                          list own listings (AD-SUMMARIES)
  GET  /{adId}                          basic listing detail
  PUT  /ads/dispose/{adId}              mark as sold (AD-ACTION)
  PUT  /ads/pause/{adId}                hide from search (AD-ACTION) [path assumed]
  DELETE /ads/{adId}                    delete listing (AD-ACTION)
  GET  /legacy/front/summary/{adId}     statistics: clicks/messages/favorites (RECOMMERCE-STATISTICS-API)
  GET  /public/tradeState?adId={adId}   recommerce trade state (REVIEW-RUNWAY)
  GET  /public/reviewCandidates?adId={adId}  buyers eligible to leave review (REVIEW-RUNWAY)
  GET  /contexts/{adId}                 available packages/products (CLASSIFIED_PRODUCT_MANAGEMENT)
  GET  /selectedproducts/{adId}         active products on listing (CLASSIFIED_PRODUCT_MANAGEMENT)
"""

from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from .client import ToriClient


class ListingsAPI:
    def __init__(self, client: "ToriClient"):
        self._c = client

    def search(
        self,
        facet: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """
        Return own listings.

        facet: ALL | DRAFT | ACTIVE | EXPIRED | PENDING | DISPOSED
               None → server default (all active)
        """
        params: dict = {"limit": limit, "offset": offset}
        if facet:
            params["facet"] = facet
        qs = urllib.parse.urlencode(params)
        return self._c.get(f"/search?{qs}", "AD-SUMMARIES")

    def get(self, ad_id: int) -> dict:
        """
        Full listing detail (adview).

        Returns {"ad": {...}, "meta": {...}} where ad contains title, description,
        price, images, extras (condition/brand/etc.), location, category, and
        adViewTypeLabel (Myydään/Ostetaan/Annetaan).
        """
        return self._c.get(f"/adview/{ad_id}", "ADVIEW-PROVIDER-RC")

    def dispose(self, ad_id: int) -> None:
        """Merkitse myydyksi — mark listing as sold. No body. Returns 204."""
        self._c.put(f"/ads/dispose/{ad_id}", "AD-ACTION")

    def pause(self, ad_id: int) -> None:
        """Hide listing from search results. No body. Returns 204."""
        self._c.put(f"/ads/pause/{ad_id}", "AD-ACTION")

    def delete(self, ad_id: int) -> None:
        """Permanently delete a listing. No body. Returns 204."""
        self._c.delete(f"/ads/{ad_id}", "AD-ACTION")

    def stats(self, ad_id: int) -> dict:
        """
        Listing performance stats (clicks, messages received, favorites).

        Response:
            {"heading": "Tilastot",
             "items": [{"count": 27, "label": "Klikkaukset", "type": "CLICKS"}, ...]}
        """
        return self._c.get(f"/legacy/front/summary/{ad_id}", "RECOMMERCE-STATISTICS-API")

    def trade_state(self, ad_id: int) -> dict:
        """
        Recommerce trade/transaction state for a listing.
        Response: {"state": "TRADE_NOT_CREATED"}
        Known states: TRADE_NOT_CREATED, TRADE_IN_PROGRESS, TRADE_COMPLETED
        """
        return self._c.get(f"/public/tradeState?adId={ad_id}", "REVIEW-RUNWAY")

    def review_candidates(self, ad_id: int) -> dict:
        """
        Buyers eligible to leave a review after a sale.
        Response: {"items": 0, "conversations": []}
        """
        return self._c.get(f"/public/reviewCandidates?adId={ad_id}", "REVIEW-RUNWAY")

    def packages(self, ad_id: int) -> dict:
        """
        Available listing packages (Basic, Plus, etc.) with pricing.
        Used to show upgrade options. Returns HAL+JSON.
        """
        return self._c.get(f"/contexts/{ad_id}", "CLASSIFIED_PRODUCT_MANAGEMENT")

    def selected_products(self, ad_id: int) -> list:
        """Currently purchased/active products for a listing. [] if none."""
        return self._c.get(f"/selectedproducts/{ad_id}", "CLASSIFIED_PRODUCT_MANAGEMENT")

    # ── Ad editing (adinput subdomain) ────────────────────────────────────────

    def get_for_edit(self, ad_id: int) -> tuple[dict, str]:
        """
        Fetch current ad values for editing from the adinput service.

        Returns (values_dict, etag). The etag must be passed to update().
        `values_dict` is the 'values' key from the response — the field map
        you edit and send back in update().
        """
        data, etag = self._c.adinput_get(f"/adinput/ad/withModel/{ad_id}")
        values = data.get("ad", data).get("values", data)
        return values, etag

    def update(self, ad_id: int, values: dict, etag: str) -> dict:
        """
        Submit a full ad update. values must be the complete field map (from
        get_for_edit), with any desired changes applied.

        Returns the response which includes the new ETag and action URLs.
        """
        return self._c.adinput_put(
            f"/adinput/ad/recommerce/{ad_id}/update", values, etag
        )

    def set_price(self, ad_id: int, price: int) -> dict:
        """
        Change the price on a listing. Fetches current values, updates price,
        and submits. Returns the update response.
        """
        values, etag = self.get_for_edit(ad_id)
        values["price"] = [{"price_amount": str(price)}]
        return self.update(ad_id, values, etag)
