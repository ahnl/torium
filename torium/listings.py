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

import re
import requests
import struct
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from .client import ToriClient


_IMG_BASE = "https://img.tori.net/dynamic/default/"

# Seller ("org") listing search — same BAP search key + SEARCH-QUEST-RC service as
# public search; orgId is the ownerId from an adview's meta block. Captured from the
# Android app 2026-08-11 (GET /org/SEARCH_ID_BAP_COMMON?client=…&orgId=…&include_anonymous=false).
_ORG_SEARCH_KEY = "SEARCH_ID_BAP_COMMON"

# Publish as Basic (free): urn:product:package-specification:10
_PUBLISH_BASIC_BODY = b"choices=urn%3Aproduct%3Apackage-specification%3A10"

# Read-back retry schedule (seconds before each attempt). Adview propagation
# after the order/choices commit takes minutes, not seconds — verified live
# 2026-07-13: a committed price change appeared in adview only after ~2-10 min.
_READBACK_DELAYS = (0, 10, 15, 30, 30, 60, 60, 60, 60)


def _norm_field(v):
    """Normalize a field value for read-back comparison (whitespace runs in strings)."""
    if isinstance(v, str):
        return " ".join(v.split())
    return v


def owner_from_adview(data: dict) -> dict:
    """
    Pull the seller identity out of an adview response.

    The seller appears ONLY in `meta` — the `ad` body has no seller field.
    Returns {"owner_id": int|None, "owner_urn": str}; owner_urn has the form
    "sdrn:aurora.tori.fi:user:{id}".
    """
    meta = data.get("meta") or {}
    return {"owner_id": meta.get("ownerId"), "owner_urn": meta.get("ownerUrn", "")}


def _raise_on_violations(resp: dict) -> None:
    """
    The adinput update PUT can return 200 with validation violations in
    meta-data (e.g. {"violation-count": 3, "title": {"violations": [...]}}).
    A revision with violations never goes live, so treat it as an error.
    """
    meta = resp.get("meta-data") or resp.get("ad", {}).get("meta-data") or {}
    count = meta.get("violation-count", 0)
    if count:
        details = {
            field: info["violations"]
            for field, info in meta.items()
            if isinstance(info, dict) and info.get("violations")
        }
        raise RuntimeError(
            f"Update rejected by validation ({count} violations): {details}"
        )


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

    def search_all(
        self,
        facet: Optional[str] = None,
        max_results: Optional[int] = None,
        offset: int = 0,
    ) -> dict:
        """
        Return ALL of the user's listings for a facet, paginating transparently.

        The /search endpoint hard-caps every response at 50 items regardless of
        the ``limit`` parameter, so this loops with ``offset`` until all pages
        are collected (or ``max_results`` is reached). Power users with hundreds
        of listings would otherwise be truncated to the first 50.

        facet:       ALL | DRAFT | ACTIVE | EXPIRED | PENDING | DISPOSED
                     None → server default (all active).
        max_results: Stop after this many listings. None → fetch everything.
        offset:      Starting offset (for resuming/skipping). Default 0.

        Returns the first page's response dict with its ``summaries`` replaced by
        the full accumulated list; ``total`` stays the server-reported count.
        """
        PAGE_CAP = 50  # server returns at most 50 per request
        all_summaries: list = []
        first: Optional[dict] = None
        pages = 0
        while True:
            page_size = PAGE_CAP
            if max_results is not None:
                remaining = max_results - len(all_summaries)
                if remaining <= 0:
                    break
                page_size = min(PAGE_CAP, remaining)
            page = self.search(facet=facet, limit=page_size, offset=offset)
            if first is None:
                first = page
            batch = page.get("summaries", [])
            if not batch:
                break
            all_summaries.extend(batch)
            offset += len(batch)
            if len(batch) < page_size:
                break  # short page → last page reached
            total = page.get("total")
            if isinstance(total, int) and offset >= total:
                break  # collected everything the server reports
            pages += 1
            if pages > 1000:
                break  # hard safety bound against a misbehaving server
        if first is None:
            return {"summaries": [], "total": 0}
        result = dict(first)
        result["summaries"] = all_summaries
        return result

    def get(self, ad_id: int) -> dict:
        """
        Full listing detail (adview).

        Returns {"ad": {...}, "meta": {...}} where ad contains title, description,
        price, images, extras (condition/brand/etc.), location, category, and
        adViewTypeLabel (Myydään/Ostetaan/Annetaan).
        """
        return self._c.get(f"/adview/{ad_id}", "ADVIEW-PROVIDER-RC")

    def owner(self, ad_id: int) -> dict:
        """
        Who is selling this ad: {"owner_id": int|None, "owner_urn": str}.

        This is the bridge from an ad to the seller behind it — the starting
        point for looking up that seller's other listings.
        """
        return owner_from_adview(self.get(ad_id))

    def seller_ads(self, owner_id: int, max_results: Optional[int] = None) -> list:
        """
        Another seller's public listings, by their ``owner_id``.

        Hits the "org" search endpoint — the same BAP search key and
        SEARCH-QUEST-RC gateway service as the public search. ``orgId`` is exactly
        the ``ownerId`` carried in an adview's ``meta`` block, so
        ``owner(ad_id)["owner_id"]`` feeds straight in. The server sorts newest
        first (PUBLISHED_DESC) and paginates via the ``page`` param; this loops
        until ``metadata.paging.last`` is reached.

        Returns the raw list of ``docs`` (each: ``ad_id``/``id``, ``heading``,
        ``price``, ``location``, ``canonical_url``, ``image_urls``, ``trade_type``,
        ``extras`` …). Same doc shape as ``search.search()``.

        max_results: stop once this many are collected. None → fetch every page.
        """
        all_docs: list = []
        page = 1
        while True:
            # client=NMP-IOS keeps the iOS identity torium spoofs everywhere else;
            # the captured app sent ANDROID, which also works if this ever 400s.
            params = {
                "client": "NMP-IOS",
                "orgId": owner_id,
                "include_anonymous": "false",
                "page": page,
            }
            qs = urllib.parse.urlencode(params)
            data = self._c.get(f"/org/{_ORG_SEARCH_KEY}?{qs}", "SEARCH-QUEST-RC")
            docs = data.get("docs", [])
            all_docs.extend(docs)
            if max_results is not None and len(all_docs) >= max_results:
                return all_docs[:max_results]
            paging = (data.get("metadata") or {}).get("paging") or {}
            last = paging.get("last")
            if not docs or not isinstance(last, int) or page >= last:
                break
            page += 1
        return all_docs

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

        NOTE: this only stores a new adinput draft revision — the live ad does
        NOT change until the publish step runs (see edit()). Raises RuntimeError
        if the server reports validation violations in the response body.

        Returns the response which includes the new ETag and action URLs.
        """
        result = self._c.adinput_put(
            f"/adinput/ad/recommerce/{ad_id}/update", values, etag
        )
        _raise_on_violations(result)
        return result

    def _publish_basic(self, ad_id: int) -> dict:
        """
        Commit the current adinput revision live as Basic (free).

        Same completion sequence create() uses: fresh withModel etag →
        productcontext(adRevision) → POST /order/choices. Without this the
        updated revision is never published (silent write loss).
        """
        _, fresh_etag = self._c.adinput_get(f"/adinput/ad/withModel/{ad_id}")
        ad_revision = re.sub(r"\D", "", fresh_etag) or fresh_etag
        self._c.adinput_get(
            f"/adinput/product/recommerce/{ad_id}/productcontext?adRevision={ad_revision}"
        )
        publish_result, _, _ = self._c.adinput_post(
            f"/adinput/order/choices/{ad_id}",
            body=_PUBLISH_BASIC_BODY,
            content_type="application/x-www-form-urlencoded",
        )
        return publish_result

    def edit(
        self,
        ad_id: int,
        *,
        price: Optional[int] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict:
        """
        Edit a listing's price, title, and/or description, publish the change,
        and verify it actually went live.

        Flow: get_for_edit → update (draft revision) → publish (commit) →
        read-back via adview. Raises RuntimeError if validation rejects the
        update or if the read-back shows the fields did not change.
        """
        if price is None and title is None and description is None:
            raise ValueError("specify at least one of price, title, description")

        values, etag = self.get_for_edit(ad_id)
        expected: dict = {}
        if price is not None:
            values["price"] = [{"price_amount": str(price)}]
            expected["price"] = price
        if title is not None:
            values["title"] = title
            expected["title"] = title
        if description is not None:
            values["description"] = description
            expected["description"] = description

        self.update(ad_id, values, etag)
        publish_result = self._publish_basic(ad_id)

        # Read-back: prove the change is live before reporting success.
        mismatched: dict = {}
        for delay in _READBACK_DELAYS:
            if delay:
                time.sleep(delay)
            after = self.get(ad_id).get("ad", {})
            mismatched = {
                k: after.get(k)
                for k, v in expected.items()
                if _norm_field(after.get(k)) != _norm_field(v)
            }
            if not mismatched:
                break
        if mismatched:
            detail = {k: {"live": v, "expected": expected[k]} for k, v in mismatched.items()}
            raise RuntimeError(
                f"Update was submitted and published for ad {ad_id}, but the change "
                f"was not visible in adview after ~5 min: {detail}. "
                f"It may still propagate — re-check with get_listing before retrying."
            )
        return {"ad_id": ad_id, "changed": sorted(expected), "publish": publish_result}

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

    def set_delivery(
        self,
        ad_id: int,
        *,
        meetup: bool = True,
        shipping: bool = False,
        buy_now: bool = True,
        seller_pays_shipping: bool = False,
        package_size: str = "SMALL",
        city: Optional[str] = None,
        postal_code: Optional[str] = None,
        shipping_info: Optional[dict] = None,
    ) -> None:
        """
        Set trade/delivery options on a listing.

        When shipping=True the Tori delivery API requires a nested
        ``shippingInfo`` object — a flat ``packageSize`` field is ignored and
        the request fails with HTTP 400
        ("ShippingInfo is required when shipping=true, but shippingInfo=null").
        ``shippingInfo.city`` and ``shippingInfo.postalCode`` are validated as
        required (NotEmpty); the seller's name/phone/address are filled in
        server-side from the account profile, so a minimal
        ``{size, city, postalCode}`` is enough.

        package_size: ToriDiili package size, only sent when shipping=True.
            "SMALL"  → Peruspaketti  (max 4 kg,  40×32×15 cm)
            "MEDIUM" → Iso paketti   (max 10 kg, 40×32×26 cm)
            "LARGE"  → Jättipaketti  (max 24 kg, 100×60×60 cm)
        city:         Seller city — required when shipping=True.
        postal_code:  Seller postal code — required when shipping=True.
        shipping_info: Optional extra shippingInfo fields to merge in
            (e.g. name, phoneNumber, address, products).

        Raises:
            ValueError: if shipping=True but city/postal_code are missing.
        """
        body: dict = {
            "buyNow": buy_now,
            "client": "IOS",
            "meetup": meetup,
            "sellerPaysShipping": seller_pays_shipping,
            "shipping": shipping,
        }
        if shipping:
            info: dict = {"size": package_size}
            if city is not None:
                info["city"] = city
            if postal_code is not None:
                info["postalCode"] = postal_code
            if shipping_info:
                info.update(shipping_info)
            if not info.get("city") or not info.get("postalCode"):
                raise ValueError(
                    "set_delivery(shipping=True) requires city and postal_code: "
                    "the Tori API rejects shippingInfo without them (HTTP 400)."
                )
            body["shippingInfo"] = info
        self._c.post(f"/ads/{ad_id}/delivery", "TJT-API", json_body=body)

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
        image_bytes: Optional[List[bytes]] = None,
        meetup: bool = True,
        shipping: bool = False,
        buy_now: bool = True,
        seller_pays_shipping: bool = False,
        package_size: str = "SMALL",
        city: Optional[str] = None,
        dry_run: bool = False,
    ) -> dict:
        """
        Create and submit a new free (Basic) listing.

        Args:
            title:       Listing title.
            description: Listing description.
            price:       Price in euros (integer).
            category:    Tori category ID as a string, e.g. "193" (kengät).
            postal_code: Finnish postal code, e.g. "96100".
            condition:   Condition ID: "1"=Uusi, "2"=Kuin uusi, "3"=Hyvä, "4"=Tyydyttävä.
            trade_type:  "1"=Myydään, "2"=Ostetaan, "3"=Annetaan.
            package_size: ToriDiili package size when shipping=True.
                "SMALL"  → Peruspaketti  (max 4 kg,  40×32×15 cm)
                "MEDIUM" → Iso paketti   (max 10 kg, 40×32×26 cm)
                "LARGE"  → Jättipaketti  (max 24 kg, 100×60×60 cm)
            city:        Seller city — required when shipping=True.

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
        all_image_data: list[bytes] = []
        for img_path in (image_paths or []):
            with open(img_path, "rb") as f:
                all_image_data.append(f.read())
        for data in (image_bytes or []):
            all_image_data.append(data)

        if all_image_data:
            # Upload each image: extract dimensions and upload in the same pass
            entries = []  # (location, width, height)
            for data in all_image_data:
                w, h = _image_dimensions(data)
                loc = self._c.adinput_upload_image(ad_id, data, "image/jpg")
                if not loc:
                    raise RuntimeError(
                        f"Image upload returned no location. Draft ad {ad_id} was NOT submitted."
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

        # Step 2c: refresh withModel to get the post-update etag.
        # iOS app does this before delivery + productcontext.
        _, fresh_etag = self._c.adinput_get(f"/adinput/ad/withModel/{ad_id}")

        # Step 2d: set delivery options
        self.set_delivery(
            ad_id,
            meetup=meetup,
            shipping=shipping,
            buy_now=buy_now,
            seller_pays_shipping=seller_pays_shipping,
            package_size=package_size,
            city=city,
            postal_code=postal_code,
        )

        # Step 2e: fetch productcontext. iOS hits this before /order/choices;
        # publishing without it may cause the listing to stay stuck in review.
        # adRevision = numeric part of the W/"..." weak etag.
        ad_revision = re.sub(r'\D', '', fresh_etag) or fresh_etag
        self._c.adinput_get(
            f"/adinput/product/recommerce/{ad_id}/productcontext?adRevision={ad_revision}"
        )

        # Step 3: publish as Basic (free)
        publish_result, _, _ = self._c.adinput_post(
            f"/adinput/order/choices/{ad_id}",
            body=_PUBLISH_BASIC_BODY,
            content_type="application/x-www-form-urlencoded",
        )
        publish_result["ad_id"] = ad_id
        return publish_result

    def set_price(self, ad_id: int, price: int) -> dict:
        """
        Change the price on a listing. Full edit flow with publish + read-back
        verification (see edit()).
        """
        return self.edit(ad_id, price=price)

    def republish(self, ad_id: int) -> dict:
        """
        Republish an expired listing as Basic (free) without re-uploading
        images or re-entering fields — re-runs the publish step of create()
        for an existing ad_id.

        Returns the publish response: {"order-id": ..., "is-completed": True, ...}
        """
        result, _, _ = self._c.adinput_post(
            f"/adinput/order/choices/{ad_id}",
            body=_PUBLISH_BASIC_BODY,
            content_type="application/x-www-form-urlencoded",
        )
        return result
