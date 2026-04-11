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

import requests
import struct
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from .client import ToriClient


_IMG_BASE = "https://img.tori.net/dynamic/default/"


def _image_dimensions(data: bytes) -> tuple[int, int]:
    """Return (width, height) by parsing JPEG or PNG file headers."""
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        w, h = struct.unpack('>II', data[16:24])
        return w, h
    # JPEG: skip SOI (FF D8), then walk markers
    i = 2
    while i < len(data) - 1:
        if data[i] != 0xFF:
            break
        marker = data[i + 1]
        i += 2
        if marker == 0xD9:
            break
        if 0xD0 <= marker <= 0xD8:  # RST0-RST7 + SOI — no length
            continue
        if i + 2 > len(data):
            break
        length = struct.unpack('>H', data[i:i + 2])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xCA, 0xCB):
            h, w = struct.unpack('>HH', data[i + 3:i + 7])
            return w, h
        i += length
    return 0, 0


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

    def upload_images(self, ad_id: int, image_paths: list[str]) -> list[str]:
        """
        Upload image files to an existing listing draft.
        Each path is uploaded as a separate request (one image per call).
        Supported: JPEG, PNG (server converts to JPEG).
        Returns list of img.tori.net URLs for the uploaded images.
        """
        locations = []
        for path in image_paths:
            with open(path, "rb") as f:
                data = f.read()
            loc = self._c.adinput_upload_image(ad_id, data, "image/jpg")
            if loc:
                locations.append(loc)
        return locations

    def create(
        self,
        title: str,
        description: str,
        price: int,
        category: str,
        postal_code: str,
        condition: str = "2",
        trade_type: str = "1",
        image_paths: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> dict:
        """
        Create and publish a new free (Basic) listing.

        Args:
            title:       Listing title.
            description: Listing description.
            price:       Price in euros (integer).
            category:    Tori category ID as a string, e.g. "193" (kengät).
            postal_code: Finnish postal code, e.g. "96100".
            condition:   Condition ID: "1"=Uusi, "2"=Kuin uusi, "3"=Hyvä, "4"=Tyydyttävä.
            trade_type:  "1"=Myydään, "2"=Ostetaan, "3"=Annetaan.

        Returns the dict from the publish response: {"order-id": ..., "is-completed": True}.
        """
        # Step 1: create draft
        _, etag, location = self._c.adinput_post(
            "/adinput/ad/withModel/recommerce", service="APPS-ADINPUT"
        )
        # Extract adId from Location: .../adinput/ad/recommerce/{adId}
        ad_id = int(location.rstrip("/").rsplit("/", 1)[-1])

        # Step 2a: upload images. The server returns a Location header (img.tori.net URL)
        # per upload. We use those URLs directly in the PUT body — polling withModel
        # does not work because the draft never auto-populates multi_image.
        multi_image = []
        image_list = []
        if image_paths:
            # Read each file once: extract dimensions and upload in the same pass
            entries = []  # (location, width, height)
            for img_path in image_paths:
                with open(img_path, "rb") as f:
                    data = f.read()
                w, h = _image_dimensions(data)
                loc = self._c.adinput_upload_image(ad_id, data, "image/jpg")
                if not loc:
                    raise RuntimeError(
                        f"Upload of {img_path} returned no location. Draft ad {ad_id} was NOT published."
                    )
                entries.append((loc, w, h))

            # Poll img.tori.net concurrently until all images are available (upload is async)
            def _wait_ready(loc: str) -> None:
                for _ in range(36):  # up to 3 minutes (36 × 5s)
                    if requests.head(loc, timeout=10).status_code == 200:
                        return
                    time.sleep(5)
                raise RuntimeError(f"Image not available after 3 minutes: {loc}")

            with ThreadPoolExecutor() as ex:
                for fut in as_completed(ex.submit(_wait_ready, loc) for loc, _, _ in entries):
                    fut.result()

            _, etag = self._c.adinput_get(f"/adinput/ad/withModel/{ad_id}")

            for loc, w, h in entries:
                path_suffix = loc.removeprefix(_IMG_BASE)
                multi_image.append({"description": "", "height": h, "path": path_suffix, "type": "image/jpg", "url": loc, "width": w})
                image_list.append({"height": str(h), "type": "image/jpg", "uri": path_suffix, "width": str(w)})

        # Step 2b: fill in fields
        values = {
            "title": title,
            "description": description,
            "price": [{"price_amount": str(price)}],
            "category": str(category),
            "condition": str(condition),
            "trade_type": str(trade_type),
            "location": [{"country": "FI", "postal-code": postal_code}],
            "image": image_list,
            "multi_image": multi_image,
        }
        result = self._c.adinput_put(
            f"/adinput/ad/recommerce/{ad_id}/update", values, etag
        )

        if dry_run:
            return {"ad_id": ad_id, "dry_run": True}

        # Step 3: publish as Basic (free)
        body = b"choices=urn%3Aproduct%3Apackage-specification%3A10"
        publish_result, _, _ = self._c.adinput_post(
            f"/adinput/order/choices/{ad_id}",
            body=body,
            content_type="application/x-www-form-urlencoded",
        )
        publish_result["ad_id"] = ad_id
        return publish_result

    def set_price(self, ad_id: int, price: int) -> dict:
        """
        Change the price on a listing. Fetches current values, updates price,
        and submits. Returns the update response.
        """
        values, etag = self.get_for_edit(ad_id)
        values["price"] = [{"price_amount": str(price)}]
        return self.update(ad_id, values, etag)
