"""
Tests for seller_ads: another seller's public listings via the org search endpoint.

The endpoint is GET /org/SEARCH_ID_BAP_COMMON?client=…&orgId={ownerId}&include_anonymous=false,
served by the SEARCH-QUEST-RC gateway service — the same service and BAP search key as the
public search. orgId is exactly the ownerId from an adview's meta block, so owner(ad_id)
feeds straight in. Response mirrors public search: {"docs": [...], "metadata": {"paging": {...}}}.
Captured live from the Android app 2026-08-11 (seller 451218839, 28 listings, single page).

Run: python -m unittest tests.test_seller_ads -v
"""

import unittest
import urllib.parse

from torium.listings import ListingsAPI


def _doc(ad_id: int, heading: str, amount: int) -> dict:
    return {
        "ad_id": ad_id,
        "id": str(ad_id),
        "heading": heading,
        "price": {"amount": amount, "currency_code": "EUR"},
        "location": "Paimio, Paimio Keskus, Varsinais-Suomi",
        "trade_type": "Myydään",
        "canonical_url": f"https://www.tori.fi/recommerce/forsale/item/{ad_id}",
        "flags": ["private"],
        "labels": [{"text": "Yksityinen"}],
    }


def _page_of(path: str) -> int:
    """Extract the page param from a request path (defaults to 1)."""
    query = urllib.parse.urlparse(path).query
    return int(urllib.parse.parse_qs(query).get("page", ["1"])[0])


class PagedFakeClient:
    """Serves /org search pages and records each (path, service) call."""

    def __init__(self, pages):
        # pages: list per 1-indexed page of (docs, last_page)
        self.pages = pages
        self.calls: list[tuple] = []

    def get(self, path, service):
        self.calls.append((path, service))
        page = _page_of(path)
        docs, last = self.pages[page - 1]
        return {
            "docs": docs,
            "metadata": {"paging": {"param": "page", "current": page, "last": last}},
        }


class SellerAdsTest(unittest.TestCase):
    def test_single_page_returns_all_docs_and_hits_org_endpoint(self):
        client = PagedFakeClient([([_doc(1, "A", 10), _doc(2, "B", 20)], 1)])
        api = ListingsAPI(client)

        docs = api.seller_ads(451218839)

        self.assertEqual([d["ad_id"] for d in docs], [1, 2])
        self.assertEqual(len(client.calls), 1)
        path, service = client.calls[0]
        self.assertEqual(service, "SEARCH-QUEST-RC")
        self.assertIn("/org/SEARCH_ID_BAP_COMMON", path)
        self.assertIn("orgId=451218839", path)
        self.assertIn("include_anonymous=false", path)

    def test_paginates_until_last_page(self):
        client = PagedFakeClient([
            ([_doc(1, "A", 10)], 2),
            ([_doc(2, "B", 20)], 2),
        ])
        api = ListingsAPI(client)

        docs = api.seller_ads(999)

        self.assertEqual([d["ad_id"] for d in docs], [1, 2])
        self.assertEqual(len(client.calls), 2)
        pages = [_page_of(p) for p, _ in client.calls]
        self.assertEqual(pages, [1, 2])

    def test_max_results_caps_and_stops_early(self):
        client = PagedFakeClient([
            ([_doc(1, "A", 10), _doc(2, "B", 20)], 3),  # more pages exist
        ])
        api = ListingsAPI(client)

        docs = api.seller_ads(999, max_results=1)

        self.assertEqual(len(docs), 1)
        self.assertEqual(len(client.calls), 1)  # did not fetch page 2/3

    def test_empty_seller_returns_empty_list(self):
        client = PagedFakeClient([([], 1)])
        api = ListingsAPI(client)

        self.assertEqual(api.seller_ads(999), [])


if __name__ == "__main__":
    unittest.main()
