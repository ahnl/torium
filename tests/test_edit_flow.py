"""
Regression tests for the edit flow (silent write loss bug).

Bug: edit_listing submitted only the adinput draft revision (PUT .../update)
and reported success from the returned ETag. The live ad never changed because
the publish/commit step (productcontext + POST /order/choices) was missing,
and the response was never verified.

These tests assert:
  1. edit() publishes after the update PUT (the missing commit step).
  2. edit() raises if the read-back shows the fields did not change.
  3. edit() raises if the update response contains validation violations,
     and does NOT publish in that case.

Run: python -m unittest tests.test_edit_flow -v
"""

import unittest
from unittest.mock import patch

from torium.listings import ListingsAPI


class FakeClient:
    """Records calls; simulates adinput + adview endpoints."""

    def __init__(self, adview_ad: dict, put_response: dict | None = None):
        self.calls: list[tuple] = []
        self.adview_ad = adview_ad
        self.put_response = put_response if put_response is not None else {"etag": 'W/"2"'}

    def adinput_get(self, path):
        self.calls.append(("adinput_get", path))
        if "withModel" in path:
            values = {
                "title": "Vanha otsikko",
                "description": "Vanha kuvaus",
                "price": [{"price_amount": "75"}],
            }
            return {"ad": {"values": values}}, 'W/"1045902423"'
        return {}, ""  # productcontext

    def adinput_put(self, path, json_body, etag):
        self.calls.append(("adinput_put", path, json_body, etag))
        return self.put_response

    def adinput_post(self, path, service="", body=b"", content_type=None):
        self.calls.append(("adinput_post", path, body))
        return {"order-id": 1, "is-completed": True}, "", ""

    def get(self, path, service):
        self.calls.append(("get", path, service))
        return {"ad": self.adview_ad, "meta": {}}

    def paths(self, kind):
        return [c[1] for c in self.calls if c[0] == kind]


class EditFlowTest(unittest.TestCase):
    def test_edit_publishes_after_update(self):
        """The commit step must run — this was the root cause of the bug."""
        client = FakeClient(
            adview_ad={"title": "Vanha otsikko", "description": "Vanha kuvaus", "price": 30}
        )
        api = ListingsAPI(client)

        result = api.edit(12265237, price=30)

        put_paths = client.paths("adinput_put")
        post_paths = client.paths("adinput_post")
        self.assertEqual(put_paths, ["/adinput/ad/recommerce/12265237/update"])
        self.assertEqual(post_paths, ["/adinput/order/choices/12265237"])
        # productcontext must be fetched between update and publish
        self.assertTrue(
            any("productcontext" in p for p in client.paths("adinput_get")),
            "productcontext was not fetched before publish",
        )
        # publish must come after the update PUT
        kinds = [c[0] for c in client.calls]
        self.assertLess(kinds.index("adinput_put"), kinds.index("adinput_post"))
        self.assertEqual(result["changed"], ["price"])

    def test_edit_raises_when_readback_shows_no_change(self):
        """Never report success when the live ad is unchanged (silent write loss)."""
        client = FakeClient(
            adview_ad={"title": "Vanha otsikko", "description": "Vanha kuvaus", "price": 75}
        )
        api = ListingsAPI(client)

        with patch("torium.listings.time.sleep"):
            with self.assertRaises(RuntimeError) as ctx:
                api.edit(12265237, price=30)
        self.assertIn("not visible in adview", str(ctx.exception))

    def test_edit_raises_on_validation_violations_and_skips_publish(self):
        """A 200 response with meta-data violations is a rejected update."""
        client = FakeClient(
            adview_ad={"title": "Vanha otsikko", "description": "Vanha kuvaus", "price": 75},
            put_response={
                "ad": {
                    "meta-data": {
                        "violation-count": 1,
                        "title": {"violations": ["Pakollinen kenttä"], "label": "Otsikko"},
                    }
                }
            },
        )
        api = ListingsAPI(client)

        with self.assertRaises(RuntimeError) as ctx:
            api.edit(12265237, title="Uusi otsikko")
        self.assertIn("validation", str(ctx.exception))
        self.assertEqual(client.paths("adinput_post"), [], "must not publish a rejected revision")

    def test_edit_requires_at_least_one_field(self):
        api = ListingsAPI(FakeClient(adview_ad={}))
        with self.assertRaises(ValueError):
            api.edit(12265237)

    def test_readback_normalizes_whitespace(self):
        """adview may normalize newlines/whitespace — that is not a mismatch."""
        client = FakeClient(
            adview_ad={
                "title": "Vanha otsikko",
                "description": "Uusi  kuvaus\nrivillä kaksi",
                "price": 75,
            }
        )
        api = ListingsAPI(client)
        result = api.edit(12265237, description="Uusi kuvaus rivillä kaksi")
        self.assertEqual(result["changed"], ["description"])


if __name__ == "__main__":
    unittest.main()
