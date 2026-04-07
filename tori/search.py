"""
Search API — public listing search, autocomplete, category tree, saved searches (hakuvahti).

Endpoints:
  GET  /search/SEARCH_ID_BAP_COMMON          main search (SEARCH-QUEST-RC)
  GET  /pole-position/api/search/...         promoted listing (POLE-POSITION-API)
  GET  /search/newfrontier/suggest           autocomplete (SEARCH-NEWFRONTIER)
  POST /v1/semantic-search                   AI similar items (RC-SEMANTIC-SEARCH)
  GET  /public/v3/category-explorer          category tree (MARKETPLACE-NAV-BAR)
  GET  /public/search?type=alert             saved searches / hakuvahti (SEARCH-SAVEDSEARCH)
  POST /public/search                        create hakuvahti
  DELETE /public/search?id=...               delete hakuvahti

See tori-api-search.md for full documentation.
"""

from __future__ import annotations

import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .client import ToriClient

_SEARCH_KEY = "SEARCH_ID_BAP_COMMON"


class SearchAPI:
    def __init__(self, client: "ToriClient"):
        self._c = client
        self._category_cache: Optional[dict] = None

    def search(
        self,
        q: str,
        category: Optional[str] = None,
        location: str = "0.100001",
        price_from: Optional[int] = None,
        price_to: Optional[int] = None,
        shipping_only: bool = False,
        page: int = 1,
        include_filters: bool = False,
        with_pole_position: bool = True,
    ) -> dict:
        """
        Search public listings.

        Fetches main results and (optionally) the promoted pole-position listing in parallel.

        Args:
            q:                Free-text query.
            category:         Sub-category code, e.g. "1.93.3217". None = all categories.
            location:         Region code. "0.100001" = all Finland (default).
            price_from:       Min price in EUR.
            price_to:         Max price in EUR.
            shipping_only:    ToriDiili (shipping) items only.
            page:             1-indexed page number.
            include_filters:  Include available filter options in response.
            with_pole_position: Fetch promoted listing in parallel (default True).

        Returns:
            {
              "promoted": <pole-position doc or None>,
              "docs": [...],
              "filters": [...] or None,
              "page": 1,
            }
        """
        params: dict = {
            "client": "NMP-IOS",
            "page": page,
            "include_results": "true",
            "q": q,
        }
        if include_filters:
            params["include_filters"] = "true"
        if category:
            params["sub_category"] = category
        if location:
            params["location"] = location
        if price_from is not None:
            params["price_from"] = price_from
        if price_to is not None:
            params["price_to"] = price_to
        if shipping_only:
            params["shipping_exists"] = "true"

        qs = urllib.parse.urlencode(params)
        main_path = f"/search/{_SEARCH_KEY}?{qs}"
        pp_path = f"/pole-position/api/search/{_SEARCH_KEY}?{_pole_qs(params)}"

        if with_pole_position:
            with ThreadPoolExecutor(max_workers=2) as ex:
                main_fut = ex.submit(self._c.get, main_path, "SEARCH-QUEST-RC")
                pp_fut = ex.submit(self._pp_safe, pp_path)
            main = main_fut.result()
            promoted = pp_fut.result()
        else:
            main = self._c.get(main_path, "SEARCH-QUEST-RC")
            promoted = None

        return {
            "promoted": promoted,
            "docs": main.get("docs", []),
            "filters": main.get("filters"),
            "page": page,
        }

    def _pp_safe(self, path: str) -> Optional[dict]:
        """Fetch pole position, returning None on any error (no results is normal)."""
        try:
            data = self._c.get(path, "POLE-POSITION-API")
            return data.get("result", {}).get("searchEntry")
        except Exception:
            return None

    def suggest(self, term: Optional[str] = None) -> dict:
        """
        Autocomplete suggestions. Pass no term for recent searches.

        Returns grouped suggestion results — see tori-api-search.md § 3.
        """
        params: dict = {"client": "APPS", "where": "FRONTPAGE"}
        if term:
            params["term"] = term
        qs = urllib.parse.urlencode(params)
        return self._c.get(f"/search/newfrontier/suggest?{qs}", "SEARCH-NEWFRONTIER")

    def categories(self) -> dict:
        """
        Full category tree. Cached per client instance (rarely changes).

        Returns recursive tree — see tori-api-search.md § 9.
        Use destination.search.search_parameters to get the exact query param
        to pass to search().
        """
        if self._category_cache is None:
            self._category_cache = self._c.get(
                "/public/v3/category-explorer?profile=mobile", "MARKETPLACE-NAV-BAR"
            )
        return self._category_cache

    def semantic_search(self, q: str, limit: int = 10) -> list:
        """AI-powered similar items. Returns up to `limit` docs."""
        data = self._c.post(
            "/v1/semantic-search", "RC-SEMANTIC-SEARCH",
            {"include": ["filters"], "limit": limit, "q": q},
        )
        return data.get("docs", [])

    def related_searches(self, q: str, categories: Optional[list] = None) -> list:
        """AI-generated related search terms with preview images."""
        data = self._c.post(
            "/v1/related-searches", "RC-RELATED-SEARCHES",
            {"categories": categories or [], "context": "srp", "q": q},
        )
        return data.get("search_term_suggestions", [])

    # ── Hakuvahti (saved search alerts) ───────────────────────────────────────

    def list_saved_searches(self) -> list:
        """List all saved search alerts (hakuvahti)."""
        return self._c.get(
            "/public/search?clientId=IOS&sort=CHANGED&type=alert",
            "SEARCH-SAVEDSEARCH",
        )

    def create_saved_search(
        self,
        q: str,
        description: str,
        category: Optional[str] = None,
        location: str = "0.100001",
        price_from: Optional[int] = None,
        price_to: Optional[int] = None,
        notifications: Optional[list] = None,
    ) -> int:
        """
        Create a new hakuvahti. Returns the new saved search ID.

        Tip: check list_saved_searches() first to avoid duplicates.
        """
        parameters: dict = {"q": [q], "location": [location]}
        if category:
            parameters["sub_category"] = [category]
        if price_from is not None:
            parameters["price_from"] = [str(price_from)]
        if price_to is not None:
            parameters["price_to"] = [str(price_to)]

        body = {
            "description": description,
            "notifications": notifications or ["NC", "EMAIL", "PUSH"],
            "parameters": parameters,
            "searchKey": _SEARCH_KEY,
            "type": "alert",
        }
        result = self._c.post("/public/search?clientId=IOS", "SEARCH-SAVEDSEARCH", body)
        return result

    def delete_saved_search(self, saved_search_id: int) -> None:
        """Delete a hakuvahti by ID. Returns 204."""
        self._c.delete(f"/public/search?clientId=IOS&id={saved_search_id}", "SEARCH-SAVEDSEARCH")


def _pole_qs(params: dict) -> str:
    """Strip main-search-only params for the pole position request."""
    exclude = {"page", "include_results", "include_filters"}
    return urllib.parse.urlencode({k: v for k, v in params.items() if k not in exclude})
