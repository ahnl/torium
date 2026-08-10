"""
Tests for seller identity extraction (adview -> owner).

An ad's seller is carried ONLY in the adview `meta` block (ownerId / ownerUrn);
the `ad` body has no seller field at all. That meta pair is the single bridge
from a listing to the person selling it, and every "show me this seller's other
listings" feature depends on it.

Run: python -m unittest tests.test_seller_identity -v
"""

import unittest

from torium.listings import ListingsAPI, owner_from_adview


class FakeClient:
    """Returns a canned adview response and records the path requested."""

    def __init__(self, adview: dict):
        self.adview = adview
        self.calls: list[tuple] = []

    def get(self, path, service):
        self.calls.append((path, service))
        return self.adview


_ADVIEW = {
    "ad": {"title": "OBJEKTIIVI NIKON 50MM F1.4 NIKKOR AI-S"},
    "meta": {
        "adId": 45250535,
        "ownerId": 796756958,
        "ownerUrn": "sdrn:aurora.tori.fi:user:796756958",
    },
}


class OwnerFromAdviewTest(unittest.TestCase):
    def test_extracts_owner_id_and_urn(self):
        self.assertEqual(
            owner_from_adview(_ADVIEW),
            {"owner_id": 796756958, "owner_urn": "sdrn:aurora.tori.fi:user:796756958"},
        )

    def test_missing_meta_yields_none(self):
        self.assertEqual(
            owner_from_adview({"ad": {}}),
            {"owner_id": None, "owner_urn": ""},
        )

    def test_null_meta_does_not_raise(self):
        self.assertEqual(
            owner_from_adview({"ad": {}, "meta": None}),
            {"owner_id": None, "owner_urn": ""},
        )


class ListingsOwnerTest(unittest.TestCase):
    def test_owner_fetches_adview_and_returns_identity(self):
        client = FakeClient(_ADVIEW)
        api = ListingsAPI(client)

        self.assertEqual(api.owner(45250535)["owner_id"], 796756958)
        self.assertEqual(client.calls, [("/adview/45250535", "ADVIEW-PROVIDER-RC")])


if __name__ == "__main__":
    unittest.main()
