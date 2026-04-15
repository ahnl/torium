"""
Tori.fi MCP Server.

Install globally:
  uv tool install ./torium

Run (local stdio, existing behaviour):
  torium-mcp

Run (remote HTTP for claude.ai):
  torium-mcp --transport streamable-http --host 0.0.0.0 --port 8000 --base-url https://example.com

Manage the email allowlist (required before first remote login):
  torium-mcp allow mikael@example.com
  torium-mcp revoke mikael@example.com
  torium-mcp list-allowed

Claude Desktop config (~/Library/Application Support/Claude/claude_desktop_config.json):
  {
    "mcpServers": {
      "torium": {
        "command": "torium-mcp"
      }
    }
  }
"""

import html
import json
import os
import secrets
import sys
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Optional

import requests
import typer
from mcp.server.fastmcp import FastMCP, Image
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

# ── Module-level state ────────────────────────────────────────────────────────
# _storage: None in stdio mode; set to Storage instance in HTTP/remote mode.
# _client_cache: one ToriClient per tori user_id, populated lazily on first tool call.
#   Why cache? ToriAuth caches the bearer token (~1h lifetime) in self._bearer and
#   ToriClient holds a requests.Session for connection pooling. Creating a new instance
#   per request would force 3 Schibsted auth round-trips on every tool call.
# _auth_provider: ToriMCPAuthProvider; set in _cmd() for HTTP transports.

_storage: Optional["Storage"] = None           # type: ignore[name-defined]
_client_cache: dict[int, "ToriClient"] = {}    # type: ignore[name-defined]
_auth_provider = None

TEMP_IMAGE_DIR = os.path.expanduser("~/.config/torium/tmp-images")


def _get_client():
    """
    Returns a per-user ToriClient, cached by tori user_id.

    Stdio mode (no --base-url): falls back to the local credentials file or
    TORI_REFRESH_TOKEN env variable — unchanged from original behaviour.

    HTTP/remote mode: resolves the current request's MCP access token to a
    user_id via SQLite, then returns the cached ToriClient for that user
    (creating it on first call per user after server start).
    """
    if _storage is None:
        # stdio / local mode — load credentials from disk / env as before
        from torium import ToriClient
        return ToriClient()

    from mcp.server.auth.middleware.auth_context import get_access_token
    from torium import ToriClient

    access = get_access_token()
    if access is None:
        raise RuntimeError("No authenticated user in request context")

    row = _storage.get_mcp_access(access.token)
    if row is None:
        raise RuntimeError("Access token not found in storage")

    user_id = row["user_id"]

    if user_id not in _client_cache:
        session = _storage.get_tori_session(user_id)
        if session is None:
            raise RuntimeError(f"No Tori session for user {user_id}")

        def _persist_rotation(new_refresh: str, _ignored_uid: int) -> None:
            _storage.update_tori_refresh(user_id, new_refresh)  # type: ignore[union-attr]

        _client_cache[user_id] = ToriClient(
            refresh_token=session["tori_refresh_token"],
            save_on_refresh=False,       # DO NOT touch ~/.config/torium/credentials.json
            on_refresh=_persist_rotation,  # persist rotation to SQLite instead
        )

    return _client_cache[user_id]


def _resolve_user_id() -> str:
    """Return the tori user_id for the current request (HTTP mode only)."""
    if _storage is None:
        raise RuntimeError("get_upload_url is only available in remote HTTP mode")
    from mcp.server.auth.middleware.auth_context import get_access_token
    access = get_access_token()
    if access is None:
        raise RuntimeError("No authenticated user in request context")
    row = _storage.get_mcp_access(access.token)
    if row is None:
        raise RuntimeError("Access token not found in storage")
    return str(row["user_id"])


def _make_upload_url(upload_token: str) -> str:
    base = os.environ.get("TORIUM_BASE_URL", "https://torium.fi")
    return f"{base}/upload/{upload_token}"


mcp = FastMCP("torium", instructions=(
    "Access the user's Tori.fi marketplace account. "
    "Can read listings, conversations, messages, favorites, and perform actions like "
    "marking items as sold, deleting listings, editing listing details (price/title/description), "
    "and sending messages.\n\n"
    "Formatting: when returning lists of listings, conversations, or other multi-item "
    "results, present them as a markdown table. Use prose only when individual items "
    "have too much text to fit naturally in a table.\n\n"
    "Image inspection: when the user is searching for something specific, proactively "
    "use fetch_image + vision on promising listings to find details that aren't in the "
    "text — model numbers, condition, included accessories, visible damage, spec labels, "
    "etc. This is especially valuable for electronics, vehicles, and other items where "
    "the photos often contain more useful information than the description.\n\n"
    "Visual HTML artifacts: use fetch_image_base64 to get a data URI and embed it in "
    "an HTML artifact with <img src=\"...\"> when showing a listing visually would help "
    "the user — e.g. a gallery of search results, a listing detail card, or a side-by-side "
    "comparison. fetch_image_base64 is for rendering; fetch_image is for vision inspection.\n\n"
    "Creating listings with images (remote/HTTP mode):\n"
    "1. For each image file, call get_upload_url() to get a presigned upload_url and image_id.\n"
    "2. Upload the files using bash curl. To avoid execution timeouts, upload in batches of at\n"
    "   most 5 files per bash call — do not upload all files in a single long-running call.\n"
    "   Run each batch as a separate bash execution, e.g.:\n"
    "     curl -s -X PUT --data-binary @img1.jpg \"<url1>\"\n"
    "     curl -s -X PUT --data-binary @img2.jpg \"<url2>\"\n"
    "     curl -s -X PUT --data-binary @img3.jpg \"<url3>\"\n"
    "   Verify every curl returned 'ok' before proceeding to the next batch.\n"
    "3. Only call create_listing once ALL uploads are confirmed successful.\n"
    "   Pass all image_ids comma-separated to create_listing(image_ids=...).\n"
    "In stdio/local mode, use create_listing(image_paths=...) directly instead."
))


# ── Listings ──────────────────────────────────────────────────────────────────

@mcp.tool()
def list_my_listings(facet: str = "ACTIVE") -> str:
    """
    List the user's own Tori.fi listings.

    facet: ACTIVE (default) | EXPIRED | DRAFT | DISPOSED | ALL
    Returns listing summaries with IDs, titles, states, click counts.
    """
    data = _get_client().listings.search(facet=facet if facet != "ACTIVE" or facet else None)
    summaries = data.get("summaries", [])
    result = []
    for s in summaries:
        ext = s.get("externalData", {})
        result.append({
            "id": s["id"],
            "title": s.get("data", {}).get("title", ""),
            "subtitle": s.get("data", {}).get("subtitle", ""),
            "state": s.get("state", {}).get("type", ""),
            "clicks": ext.get("clicks", {}).get("value", "0"),
            "favorites": ext.get("favorites", {}).get("value", "0"),
            "created": s.get("created", ""),
            "expires": s.get("expires", ""),
        })
    return json.dumps({"total": data.get("total", len(result)), "listings": result}, ensure_ascii=False)


@mcp.tool()
def get_listing(ad_id: int) -> str:
    """
    Get full details of any listing (own or public): title, description, price,
    category, location, condition, extras (brand, model, etc.), and image URLs.

    ad_id: The listing ID (integer).

    The returned 'images' list contains direct image URLs. Use the fetch_image tool
    to load them and inspect with vision when the user asks about anything that might
    be visible in photos — condition, model number, serial number, visible damage,
    ports, included accessories, spec stickers. Electronics listings in particular
    often show model numbers, spec labels, or damage in photos that are never
    mentioned in the text description. Proactively fetch and inspect images when
    such details would be useful to the user.
    """
    data = _get_client().listings.get(ad_id)
    ad = data.get("ad", {})
    meta = data.get("meta", {})

    cat = ad.get("category", {})
    cat_parts = []
    c = cat
    while c:
        cat_parts.insert(0, c.get("value", ""))
        c = c.get("parent")

    result = {
        "id": ad_id,
        "title": ad.get("title", ""),
        "type": ad.get("adViewTypeLabel", ""),
        "price": ad.get("price"),
        "description": ad.get("description", ""),
        "category": " > ".join(cat_parts),
        "location": ad.get("location", {}).get("postalName", ""),
        "extras": {e["label"]: e["value"] for e in ad.get("extras", [])},
        "images": [img["uri"] for img in ad.get("images", [])],
        "disposed": ad.get("disposed", False),
        "edited": meta.get("edited", ""),
    }
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def get_listing_stats(ad_id: int) -> str:
    """
    Get performance statistics for a listing: clicks, messages received, favorites count.

    ad_id: The listing ID (integer).
    """
    data = _get_client().listings.stats(ad_id)
    return json.dumps(data, ensure_ascii=False)


@mcp.tool()
def dispose_listing(ad_id: int) -> str:
    """
    Mark a listing as sold (merkitse myydyksi). This hides it from search results
    and moves it to the "Myydyt" (sold) category.

    ad_id: The listing ID to mark as sold.
    """
    _get_client().listings.dispose(ad_id)
    return f"Listing {ad_id} marked as sold."


@mcp.tool()
def delete_listing(ad_id: int) -> str:
    """
    Permanently delete a listing. This action cannot be undone.

    ad_id: The listing ID to delete.
    """
    _get_client().listings.delete(ad_id)
    return f"Listing {ad_id} deleted."


@mcp.tool()
def get_upload_url(filename: str = "image.jpg") -> str:
    """
    Get a presigned upload URL for a single image file.

    Call this once per image BEFORE calling create_listing.
    Then upload the image file directly to the returned upload_url using HTTP PUT:
        curl -s -X PUT --data-binary @/path/to/photo.jpg "<upload_url>"
    Finally pass the returned image_id to create_listing's image_ids parameter.

    The upload URL is valid for 30 minutes.

    Example workflow for 2 images:
        r1 = get_upload_url("photo1.jpg")
        curl -s -X PUT --data-binary @/path/photo1.jpg <r1.upload_url>
        r2 = get_upload_url("photo2.jpg")
        curl -s -X PUT --data-binary @/path/photo2.jpg <r2.upload_url>
        create_listing(..., image_ids="<r1.image_id>,<r2.image_id>")
    """
    user_id = _resolve_user_id()
    image_id = str(uuid.uuid4())
    upload_token = secrets.token_urlsafe(32)
    os.makedirs(TEMP_IMAGE_DIR, exist_ok=True)
    file_path = os.path.join(TEMP_IMAGE_DIR, f"{image_id}.jpg")
    upload_url = _make_upload_url(upload_token)

    _storage.cleanup_old_temp_images()  # type: ignore[union-attr]
    _storage.register_temp_image(image_id, upload_token, user_id, file_path, "image/jpeg")  # type: ignore[union-attr]

    return json.dumps({"image_id": image_id, "upload_url": upload_url})


@mcp.tool()
def create_listing(
    title: str,
    description: str,
    price: int,
    category: str,
    postal_code: str,
    condition: str = "2",
    trade_type: str = "1",
    image_paths: str = "",
    image_ids: str = "",
) -> str:
    """
    Create and publish a new free (Basic) listing on Tori.fi.

    title:       Listing title.
    description: Listing description.
    price:       Price in euros (integer). Use 0 for free items.
    category:    Tori category ID as a string. Use get_create_categories() to find IDs.
    postal_code: Finnish postal code, e.g. "96100".
    condition:   "1"=Uusi, "2"=Kuin uusi (default), "3"=Hyvä, "4"=Tyydyttävä.
    trade_type:  "1"=Myydään (default), "2"=Ostetaan, "3"=Annetaan.
    image_paths: Comma-separated absolute local file paths. Works only when the MCP
                 server runs as a local stdio process on the same machine as the files.
                 e.g. "/Users/me/photo1.jpg,/Users/me/photo2.jpg"
    image_ids:   Comma-separated image IDs from get_upload_url(). Use in remote/HTTP
                 mode after uploading each file to its presigned upload_url.
                 e.g. "abc123,def456"
    """
    paths = [p.strip() for p in image_paths.split(",") if p.strip()] if image_paths else []

    if _storage is not None:
        _storage.cleanup_old_temp_images()

    image_bytes_list: list[bytes] = []
    if image_ids and _storage is not None:
        user_id = _resolve_user_id()
        for iid in [i.strip() for i in image_ids.split(",") if i.strip()]:
            try:
                image_bytes_list.append(_storage.consume_temp_image(iid, user_id))
            except ValueError as e:
                return f"Error: {e}"

    result = _get_client().listings.create(
        title=title,
        description=description,
        price=price,
        category=category,
        postal_code=postal_code,
        condition=condition,
        trade_type=trade_type,
        image_paths=paths,
        image_bytes=image_bytes_list,
    )
    ad_id = result.get("ad_id")
    if result.get("is-completed"):
        return f"Listing published! ID: {ad_id}. URL: https://www.tori.fi/{ad_id}"
    return f"Listing created (ID: {ad_id}) but publish status unclear: {result}"


@mcp.tool()
def edit_listing(
    ad_id: int,
    price: int = 0,
    title: str = "",
    description: str = "",
) -> str:
    """
    Edit a listing's price, title, or description. Fetches current values from
    the adinput service, applies the requested changes, and submits the update.
    At least one of price/title/description must be provided.

    ad_id:       The listing ID to update.
    price:       New price in euros. 0 = keep current price.
    title:       New title. Empty string = keep current title.
    description: New description. Empty string = keep current description.
    """
    if not price and not title and not description:
        return "Error: specify at least one of price, title, or description."

    c = _get_client()
    values, etag = c.listings.get_for_edit(ad_id)

    changed = []
    if price:
        values["price"] = [{"price_amount": str(price)}]
        changed.append(f"price → {price} €")
    if title:
        values["title"] = title
        changed.append(f"title → {title!r}")
    if description:
        values["description"] = description
        changed.append("description updated")

    result = c.listings.update(ad_id, values, etag)
    new_etag = result.get("etag", "")
    summary = ", ".join(changed)
    return f"Listing {ad_id} updated: {summary}. New ETag: {new_etag}"


# ── Messaging ─────────────────────────────────────────────────────────────────

@mcp.tool()
def get_unread_count() -> str:
    """Get the total number of unread messages across all conversations."""
    count = _get_client().messaging.unread_count()
    return json.dumps({"unread_message_count": count})


@mcp.tool()
def list_conversations(limit: int = 20, offset: int = 0) -> str:
    """
    List conversation groups, each grouped by listing.

    Returns conversation IDs, listing titles, other party names, last messages,
    and unread counts.
    """
    client = _get_client()
    groups = client.messaging.list_conversations(limit=limit, offset=offset)
    result = []
    for group in groups:
        basis = group.get("groupBasis", {})
        item_info = basis.get("itemInfo", {})
        for conv in group.get("conversations", []):
            result.append({
                "conversation_id": conv.get("conversationId", conv.get("id")),
                "listing_title": item_info.get("title", ""),
                "listing_id": item_info.get("itemId", item_info.get("adId")),
                "other_party": conv.get("partnerName", conv.get("otherParty", {}).get("name", "")),
                "other_party_id": conv.get("partnerId", conv.get("otherParty", {}).get("userId")),
                "unread": conv.get("unseenCounter", conv.get("unreadMessageCount", 0)),
                "last_message": conv.get("lastMessagePreview", conv.get("latestMessage", {}).get("text", "")),
                "last_message_date": conv.get("lastMessageDate", conv.get("latestMessage", {}).get("sendDate", "")),
            })
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def get_conversation(conversation_id: str) -> str:
    """
    Get the full message thread for a conversation.

    conversation_id: The conversation ID string (from list_conversations).
    Returns messages in chronological order with sender and timestamps.
    """
    client = _get_client()
    messages = client.messaging.list_messages(conversation_id)
    result = []
    for msg in reversed(messages):  # oldest first
        result.append({
            "id": msg.get("id"),
            "outgoing": msg.get("outgoing", False),
            "text": msg.get("body", msg.get("text", "")),
            "date": msg.get("sent", msg.get("sendDate", "")),
            "type": msg.get("type", msg.get("messageType", "")),
        })
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def send_message(conversation_id: str, text: str) -> str:
    """
    Send a text message in an existing conversation.

    conversation_id: The conversation ID.
    text: The message text to send.
    """
    result = _get_client().messaging.send(conversation_id, text)
    return json.dumps({"success": True, "message": result}, ensure_ascii=False)


@mcp.tool()
def start_conversation(ad_id: int, text: str, item_type: str = "recommerce") -> dict:
    """
    Start a new conversation with a seller by sending the first message.

    Use this when there is no existing conversation yet — i.e. you have a
    listing ID but no conversation ID.

    ad_id: The listing/ad ID (integer).
    text: The first message to send.
    item_type: "recommerce" for recommerce listings, "Ad" for classifieds (default: "recommerce").
    """
    result = _get_client().messaging.start_conversation(ad_id=ad_id, text=text, item_type=item_type)
    return json.dumps({"success": True, "conversation": result}, ensure_ascii=False)


# ── Favorites ─────────────────────────────────────────────────────────────────

@mcp.tool()
def list_favorites() -> str:
    """List all items the user has added to favorites, with item IDs and types."""
    data = _get_client().favorites.list()
    return json.dumps(data, ensure_ascii=False)


# ── Search ────────────────────────────────────────────────────────────────────

@mcp.tool()
def search_my_listings(
    facet: str = "",
    limit: int = 50,
    offset: int = 0,
) -> str:
    """
    Search and filter the user's own listings.

    facet: Optional filter — ACTIVE | EXPIRED | DRAFT | DISPOSED | PENDING | ALL
    Returns full listing summaries including available actions.
    """
    data = _get_client().listings.search(
        facet=facet or None,
        limit=limit,
        offset=offset,
    )
    return json.dumps(data, ensure_ascii=False)


# ── Public search ─────────────────────────────────────────────────────────────

@mcp.tool()
def search_listings(
    q: str,
    category: str = "",
    location: str = "",
    price_from: int = 0,
    price_to: int = 0,
    shipping_only: bool = False,
    page: int = 1,
) -> str:
    """
    Search public Tori.fi listings.

    Always fetches the promoted pole-position listing in parallel and includes it
    first in the result (labeled as promoted=True). Always use canonical_url as
    the item link.

    Args:
        q:             Search query, e.g. "iphone"
        category:      Sub-category code, e.g. "1.93.3217". Empty = all categories.
        location:      Region code from get_locations(), e.g. "0.100018" for Uusimaa.
                       Empty = all Finland.
        price_from:    Minimum price in EUR. 0 = no minimum.
        price_to:      Maximum price in EUR. 0 = no maximum.
        shipping_only: If True, return only ToriDiili (shipping available) items.
        page:          Page number, 1-indexed.
    """
    result = _get_client().search.search(
        q=q,
        category=category or None,
        location=location,
        price_from=price_from or None,
        price_to=price_to or None,
        shipping_only=shipping_only,
        page=page,
        include_filters=False,
    )

    out = []
    if result["promoted"]:
        p = result["promoted"]
        price = p.get("price", {})
        out.append({
            "promoted": True,
            "id": p.get("id") or p.get("ad_id"),
            "title": p.get("heading", ""),
            "price": price.get("amount"),
            "currency": price.get("currency_code", "EUR"),
            "location": p.get("location", ""),
            "labels": [l["text"] for l in p.get("labels", [])],
            "url": p.get("canonical_url", ""),
        })

    for doc in result["docs"]:
        price = doc.get("price", {})
        out.append({
            "promoted": False,
            "id": doc.get("ad_id") or doc.get("id"),
            "title": doc.get("heading", ""),
            "price": price.get("amount"),
            "currency": price.get("currency_code", "EUR"),
            "location": doc.get("location", ""),
            "labels": [l["text"] for l in doc.get("labels", [])],
            "url": doc.get("canonical_url", ""),
            "flags": doc.get("flags", []),
        })

    return json.dumps({"page": page, "count": len(out), "results": out}, ensure_ascii=False)


@mcp.tool()
def get_search_categories(query: str = "") -> str:
    """
    Search categories by Finnish name. Returns category codes for search_listings().

    query: Finnish keyword (e.g. "kengät", "puhelin"). Empty = all categories.

    Use the 'code' field as the category param in search_listings().
    """
    cats = _get_client().search.find_search_categories(query)
    return json.dumps(cats, ensure_ascii=False)


@mcp.tool()
def get_create_categories(query: str = "") -> str:
    """
    Search categories by Finnish name. Returns category IDs for create_listing().

    query: Finnish keyword (e.g. "kengät", "puhelin"). Empty = all categories.

    Use the 'id' field as the category param in create_listing().
    """
    cats = _get_client().search.find_categories(query)
    return json.dumps(cats, ensure_ascii=False)


@mcp.tool()
def get_locations(query: str = "") -> str:
    """
    Get available location/region codes for filtering search results.

    Returns regions (maakunnat) and municipalities (kunnat) with their codes.
    Use the 'code' field as the location parameter in search_listings().

    query: Finnish keyword to filter by (e.g. "Helsinki", "Uusimaa"). Empty = all.
    """
    locs = _get_client().search.find_locations(query)
    return json.dumps(locs, ensure_ascii=False)


@mcp.tool()
def list_saved_searches() -> str:
    """List all saved search alerts (hakuvahti) for the user."""
    data = _get_client().search.list_saved_searches()
    return json.dumps(data, ensure_ascii=False)


@mcp.tool()
def create_saved_search(
    q: str,
    description: str,
    category: str = "",
    price_from: int = 0,
    price_to: int = 0,
) -> str:
    """
    Create a hakuvahti (saved search alert). The user will be notified by email,
    push notification, and notification center when matching new listings appear.

    Check list_saved_searches() first to avoid creating duplicates.

    Args:
        q:           Search query to watch for.
        description: Human-readable name, e.g. "iphone, Puhelimet ja tarvikkeet".
        category:    Sub-category code. Empty = all categories.
        price_from:  Min price filter. 0 = no minimum.
        price_to:    Max price filter. 0 = no maximum.
    """
    new_id = _get_client().search.create_saved_search(
        q=q,
        description=description,
        category=category or None,
        price_from=price_from or None,
        price_to=price_to or None,
    )
    return json.dumps({"created": True, "id": new_id}, ensure_ascii=False)


@mcp.tool()
def delete_saved_search(saved_search_id: int) -> str:
    """Delete a hakuvahti by its numeric ID (from list_saved_searches)."""
    _get_client().search.delete_saved_search(saved_search_id)
    return json.dumps({"deleted": True, "id": saved_search_id})


# ── Images ────────────────────────────────────────────────────────────────────

def _fetch_raw(url: str) -> tuple[bytes, str]:
    """Fetch image bytes and mime type."""
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    mime = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    return resp.content, mime


@mcp.tool()
def fetch_image(url: str) -> Image:
    """
    Fetch a listing image by URL and return it as an image object for vision inspection.

    Use this whenever a listing's photo might contain information not in the text:
    model numbers, serial numbers, spec stickers, visible damage, included
    accessories, ports, screen condition, etc.

    url: A direct image URL from the 'images' field of get_listing or search_listings.
    """
    data, mime = _fetch_raw(url)
    return Image(data=data, format=mime.split("/")[-1])


@mcp.tool()
def fetch_image_base64(url: str) -> str:
    """
    Fetch a listing image by URL and return it as a base64 data URI string.

    Use this to embed images in HTML for visual display in Claude Desktop's artifact
    renderer. The returned string is a complete data URI (e.g. "data:image/jpeg;base64,...")
    that can be dropped directly into an <img src="..."> tag or used in a CSS
    background-image.

    Example usage — build an HTML widget showing listing photos:
      1. Call get_listing to get image URLs.
      2. Call fetch_image_base64 for each URL.
      3. Produce an HTML artifact with <img src="<data_uri>"> tags.

    Use fetch_image (not this tool) when you only need vision inspection without
    rendering an HTML artifact.

    url: A direct image URL from the 'images' field of get_listing or search_listings.
    """
    import base64
    data, mime = _fetch_raw(url)
    b64 = base64.b64encode(data).decode()
    return f"data:{mime};base64,{b64}"


# ── Login routes (OAuth flow) ──────────────────────────────────────────────────

_LOGIN_PAGE = """\
<!doctype html>
<html lang="fi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kirjaudu · Torium</title>
  <link rel="icon" type="image/x-icon" href="/favicon.ico">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Unbounded:wght@600&family=Inter:wght@400;500&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet">
  <style>
    :root {{
      --purple: #9333ea;
      --purple-dark: #7c3aed;
      --purple-subtle: #faf5ff;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', system-ui, sans-serif;
      background: #f5f5f5;
      color: #111;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 24px;
      -webkit-font-smoothing: antialiased;
    }}
    .card {{
      background: #fff;
      border-radius: 12px;
      border: 1px solid #e5e5e5;
      padding: 40px 36px;
      max-width: 520px;
      width: 100%;
      box-shadow: 0 2px 16px rgba(0,0,0,0.06);
    }}
    .logo {{
      font-family: 'Unbounded', sans-serif;
      font-weight: 600;
      font-size: 20px;
      color: var(--purple);
      text-decoration: none;
      display: block;
      margin-bottom: 24px;
    }}
    h1 {{
      font-family: 'Unbounded', sans-serif;
      font-weight: 600;
      font-size: 21px;
      margin-bottom: 6px;
    }}
    .subtitle {{
      color: #666;
      font-size: 14px;
      margin-bottom: 28px;
      line-height: 1.5;
    }}
    .step-label {{
      font-weight: 500;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: #888;
      margin: 22px 0 9px;
    }}
    .btn {{
      display: inline-block;
      padding: 10px 20px;
      border-radius: 7px;
      background: var(--purple);
      color: #fff;
      font-size: 14px;
      font-weight: 500;
      text-decoration: none;
      border: none;
      cursor: pointer;
      font-family: inherit;
      transition: background 0.15s;
    }}
    .btn:hover {{ background: var(--purple-dark); }}
    .btn:disabled {{ opacity: 0.65; cursor: not-allowed; }}
    ol {{
      padding-left: 1.4em;
      color: #555;
      font-size: 14px;
      line-height: 1.75;
    }}
    .notice {{
      background: var(--purple-subtle);
      border-radius: 6px;
      padding: 9px 14px;
      font-size: 13px;
      margin: 12px 0 16px;
      color: #555;
    }}
    textarea {{
      width: 100%;
      height: 76px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      padding: 9px 12px;
      border: 1px solid #ddd;
      border-radius: 6px;
      resize: vertical;
      margin-bottom: 12px;
      color: #111;
      line-height: 1.5;
    }}
    textarea:focus {{ outline: 2px solid var(--purple); border-color: transparent; }}
    .error {{
      background: #faf5ff;
      border: 1px solid #d8b4fe;
      border-radius: 6px;
      padding: 10px 14px;
      margin-bottom: 18px;
      color: #581c87;
      font-size: 14px;
    }}
    code {{
      background: #f0f0f0;
      padding: 1px 5px;
      border-radius: 3px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
    }}
    .footer-note {{
      margin-top: 24px;
      font-size: 12px;
      color: #aaa;
      text-align: center;
    }}
    .footer-note a {{ color: #aaa; }}
  </style>
</head>
<body>
  <div class="card">
    <a class="logo" href="/">Torium</a>
    <h1>Kirjaudu Tori.fi-tilillesi</h1>
    <p class="subtitle">Tämä ei ole virallinen Tori.fi-tuote. Jatkamalla annat suostumuksen <a href="/privacy" style="color: var(--purple);">henkilötietojen käsittelyyn</a>.</p>

    {error}

    <p class="step-label">Vaihe 1: Avaa Tori.fi-kirjautuminen</p>
    <a class="btn" href="{auth_url}" target="_blank" rel="noopener">Kirjaudu Tori.fi:hin &rarr;</a>

    <p class="step-label">Vaihe 2: Kopioi tunnistautumistieto</p>
    <ol>
      <li>Kirjaudu sisään avautuneessa välilehdessä.</li>
      <li>Sivu jää lataamaan tai näyttää virheen, tämä on normaalia.</li>
      <li>Avaa kehittäjätyökalut: <strong>F12</strong> (Win/Linux) tai <strong>Cmd+Option+I</strong> (Mac).</li>
      <li>Mene <strong>Console</strong>-välilehdelle ja etsi URL, joka alkaa <code>fi.tori.www</code>.</li>
      <li>Kopioi koko URL ja liitä se alla olevaan kenttään.</li>
    </ol>
    <div class="notice">Toimi nopeasti, URL vanhenee 30&ndash;60 sekunnissa.</div>

    <form method="POST">
      <input type="hidden" name="state" value="{state}">
      <textarea name="callback_url"
        placeholder="fi.tori.www.6079834b9b0b741812e7e91f://login?code=...&state=..."
        required></textarea>
      <button class="btn" type="submit"
        onclick="this.disabled=true;this.textContent='Yhdistetään\u2026';this.form.submit()">
        Yhdistä
      </button>
    </form>

  </div>
</body>
</html>
"""


_GIT_COMMIT = os.environ.get("GIT_COMMIT", "unknown")


@mcp.custom_route("/upload/{upload_token}", methods=["PUT", "POST"])
async def _receive_upload(request: Request):
    from starlette.responses import Response

    if _storage is None:
        return Response("not available in stdio mode", status_code=404)

    upload_token = request.path_params["upload_token"]
    row = _storage.get_temp_image_by_token(upload_token)
    if not row or row["used"]:
        return Response("not found", status_code=404)

    if time.time() > row["created_at"] + 1800:
        return Response("upload URL expired", status_code=403)

    content_length = int(request.headers.get("content-length", 0))
    if content_length > 30 * 1024 * 1024:
        return Response("too large", status_code=413)

    data = await request.body()
    os.makedirs(TEMP_IMAGE_DIR, exist_ok=True)
    with open(row["file_path"], "wb") as f:
        f.write(data)

    _storage.mark_temp_image_uploaded(row["image_id"])
    return Response("ok", status_code=200)


@mcp.custom_route("/", methods=["GET"])
async def _frontpage(request: Request) -> HTMLResponse:
    return HTMLResponse(f"""\
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Torium</title>
  <link rel="icon" type="image/x-icon" href="/favicon.ico">
</head>
<body>
  <p>commit: {_GIT_COMMIT}</p>
</body>
</html>
""")



_DELETE_CONFIRM_PAGE = """\
<!doctype html>
<html lang="fi">
<head>
  <meta charset="utf-8">
  <title>{title} · torium</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@600&family=Inter:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {{ --red: #e8002d; }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Inter', system-ui, sans-serif; background: #f5f5f5; color: #111;
            min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px; }}
    .card {{ background: #fff; border-radius: 12px; border: 1px solid #e5e5e5;
             padding: 48px 40px; max-width: 480px; width: 100%; text-align: center;
             box-shadow: 0 2px 16px rgba(0,0,0,0.06); }}
    h1 {{ font-family: 'Montserrat', sans-serif; font-weight: 600; font-size: 24px; margin: 16px 0 10px; }}
    p {{ color: #666; line-height: 1.6; }}
    .icon {{ font-size: 48px; }}
    a {{ color: var(--red); }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">{icon}</div>
    <h1>{title}</h1>
    <p>{message}</p>
    <p style="margin-top:20px"><a href="/">← Etusivulle</a></p>
  </div>
</body>
</html>
"""


@mcp.custom_route("/delete-request", methods=["POST"])
async def _delete_request(request: Request):
    from starlette.responses import JSONResponse
    if _storage is None:
        return JSONResponse({"error": "not_configured"}, status_code=503)

    try:
        body = await request.body()
        data = json.loads(body)
        email = str(data.get("email", "")).strip().lower()
    except Exception:
        return JSONResponse({"error": "bad_request"}, status_code=400)

    if not email or "@" not in email:
        return JSONResponse({"error": "invalid_email"}, status_code=400)

    import resend
    resend.api_key = os.environ.get("RESEND_API_KEY", "")
    base_url = os.environ.get("TORIUM_BASE_URL", "https://torium.fi")

    if not _storage.email_has_data(email):
        # Always respond ok — don't reveal whether the account exists
        try:
            resend.Emails.send({
                "from": "torium <torium@torium.fi>",
                "to": [email],
                "subject": "Vahvista tietojen poistaminen",
                "html": """
<p>Hei,</p>
<p>Saimme pyynnön poistaa toriumiin liitetyt tietosi, mutta tällä sähköpostiosoitteella
ei löydy tallennettuja tietoja palvelimeltamme.</p>
<p>Jos kirjauduit palveluun eri sähköpostiosoitteella, lähetä pyyntö uudelleen sillä osoitteella.</p>
<hr>
<p style="color:#888;font-size:12px;"><a href="https://torium.fi" style="color:#888;">torium.fi</a></p>
""",
            })
        except Exception as exc:
            print(f"[delete-request] Resend error (not found): {exc}", file=sys.stderr)
        return JSONResponse({"ok": True})

    token = _storage.create_deletion_token(email)
    confirm_url = f"{base_url}/delete-confirm?token={token}"

    try:
        resend.Emails.send({
            "from": "torium <torium@torium.fi>",
            "to": [email],
            "subject": "Vahvista tietojen poistaminen",
            "html": f"""
<p>Hei,</p>
<p>Pyysit kaikkien toriumiin tallennettujen tietojesi poistamista.</p>
<p><a href="{confirm_url}">Vahvista poistaminen klikkaamalla tätä linkkiä</a></p>
<p>Linkki on voimassa 24 tuntia. Jos et pyytänyt tätä, voit jättää viestin huomiotta.</p>
<hr>
<p style="color:#888;font-size:12px;"><a href="https://torium.fi" style="color:#888;">torium.fi</a></p>
""",
        })
    except Exception as exc:
        print(f"[delete-request] Resend error: {exc}", file=sys.stderr)
        return JSONResponse({"error": "email_failed"}, status_code=500)

    return JSONResponse({"ok": True})


@mcp.custom_route("/delete-confirm", methods=["GET"])
async def _delete_confirm(request: Request) -> HTMLResponse:
    if _storage is None:
        return HTMLResponse("Palvelu ei ole käytettävissä.", status_code=503)

    token = request.query_params.get("token", "")
    email = _storage.consume_deletion_token(token)

    if email is None:
        return HTMLResponse(_DELETE_CONFIRM_PAGE.format(
            icon="⚠️",
            title="Virheellinen linkki",
            message="Linkki on vanhentunut tai jo käytetty. Pyydä uusi poistolinkki "
                    "<a href='/delete'>tietojen poistosivulta</a>.",
        ), status_code=400)

    deleted = _storage.delete_user_data(email)
    _client_cache.clear()

    if deleted:
        return HTMLResponse(_DELETE_CONFIRM_PAGE.format(
            icon="✅",
            title="Tiedot poistettu",
            message=f"Kaikki osoitteeseen <strong>{html.escape(email)}</strong> liittyvät "
                    "tiedot on poistettu palvelimeltamme pysyvästi.",
        ))
    return HTMLResponse(_DELETE_CONFIRM_PAGE.format(
        icon="ℹ️",
        title="Tietoja ei löydy",
        message="Tiedot on jo poistettu tai niitä ei löydy palvelimelta.",
    ))


@mcp.custom_route("/tori-login", methods=["GET", "POST"])
async def _tori_login(request: Request) -> HTMLResponse | RedirectResponse:
    import traceback
    try:
        return await _tori_login_inner(request)
    except Exception as exc:
        tb = traceback.format_exc()
        print(f"[tori-login] {request.method} {request.url} → UNHANDLED {type(exc).__name__}: {exc}\n{tb}",
              file=sys.stderr, flush=True)
        return HTMLResponse(
            f"<h2>Internal server error</h2><pre>{html.escape(str(exc))}\n\n{html.escape(tb)}</pre>",
            status_code=500,
        )


async def _tori_login_inner(request: Request) -> HTMLResponse | RedirectResponse:
    if _auth_provider is None:
        return HTMLResponse("Auth not configured.", status_code=500)

    if request.method == "GET":
        mcp_state = request.query_params.get("state", "")
        print(f"[tori-login] GET state={mcp_state!r}", file=sys.stderr, flush=True)
        pending = _auth_provider.refresh_schibsted_session(mcp_state)
        if pending is None:
            known = list(_auth_provider._pending.keys())
            print(f"[tori-login] GET: state not in _pending. known states: {known}",
                  file=sys.stderr, flush=True)
            return HTMLResponse("Invalid or expired login session.", status_code=400)
        return HTMLResponse(_LOGIN_PAGE.format(
            auth_url=html.escape(pending.schibsted_auth_url),
            state=html.escape(mcp_state),
            error="",
        ))

    # POST — process pasted callback URL
    form = await request.form()
    mcp_state = form.get("state", "")
    callback_url = str(form.get("callback_url", "")).strip()
    print(f"[tori-login] POST state={mcp_state!r} callback_url_len={len(callback_url)}",
          file=sys.stderr, flush=True)
    pending = _auth_provider.get_pending(mcp_state)

    def _error(msg: str) -> HTMLResponse:
        pending2 = _auth_provider.refresh_schibsted_session(mcp_state)
        if pending2 is None:
            return HTMLResponse("Invalid or expired login session.", status_code=400)
        return HTMLResponse(_LOGIN_PAGE.format(
            auth_url=html.escape(pending2.schibsted_auth_url),
            state=html.escape(mcp_state),
            error=f'<div class="error">{html.escape(msg)}</div>',
        ))

    if pending is None:
        return HTMLResponse("Invalid or expired login session.", status_code=400)

    # Parse the pasted callback URL
    try:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(callback_url).query)
    except Exception:
        return _error("Could not parse the URL. Please paste the full address bar URL.")

    if "error" in qs:
        return _error(f"Tori.fi login error: {qs['error'][0]}")

    if qs.get("state", [None])[0] != pending.schibsted_state:
        return _error("State mismatch. Please click the Tori.fi button again to get a fresh login link.")

    code_list = qs.get("code")
    if not code_list:
        return _error("No authorization code found in the URL. Did you paste the right URL?")

    # Exchange Schibsted code for Tori refresh token, then fetch identity from /v2/me
    from .mcp_auth import exchange_schibsted_code, fetch_tori_identity
    try:
        initial_refresh = exchange_schibsted_code(code_list[0], pending.pkce_verifier)
    except requests.HTTPError as exc:
        body = exc.response.text[:500] if exc.response is not None else ""
        status = exc.response.status_code if exc.response is not None else "?"
        print(f"[tori-login] exchange_schibsted_code failed {status}: {body}", file=sys.stderr, flush=True)
        return _error(
            f"Schibsted code exchange failed ({status}). "
            "The code may have expired — it's valid for ~30 seconds. Please log in again."
        )
    except Exception as exc:
        print(f"[tori-login] exchange_schibsted_code unexpected error: {exc}", file=sys.stderr, flush=True)
        return _error(f"Unexpected error during code exchange: {exc}")

    try:
        new_refresh, user_id, email = fetch_tori_identity(initial_refresh)
    except requests.HTTPError as exc:
        body = exc.response.text[:500] if exc.response is not None else ""
        status = exc.response.status_code if exc.response is not None else "?"
        print(f"[tori-login] fetch_tori_identity failed {status}: {body}", file=sys.stderr, flush=True)
        return _error(f"Failed to fetch Tori identity ({status}). Please try again.")
    except Exception as exc:
        print(f"[tori-login] fetch_tori_identity unexpected error: {exc}", file=sys.stderr, flush=True)
        return _error(f"Unexpected error fetching Tori identity: {exc}")

    # Check allowlist before issuing any MCP tokens
    _open_access = os.environ.get("TORIUM_OPEN", "").strip() not in ("", "0", "false")
    if not _open_access and not _storage.is_allowed(email):
        return _error("Sähköpostiosoitettasi ei ole sallittujen listalla. Ota yhteyttä palvelimen ylläpitäjään.")

    # Persist Tori session + issue MCP tokens, redirect Claude to its callback
    redirect_url = _auth_provider.complete_login(mcp_state, new_refresh, user_id, email)
    print(f"[tori-login] POST user_id={user_id} email={email} → redirecting to {redirect_url}",
          file=sys.stderr, flush=True)
    return RedirectResponse(redirect_url, status_code=302)


# ── CLI ────────────────────────────────────────────────────────────────────────

_app = typer.Typer(add_completion=False)


@_app.callback(invoke_without_command=True)
def _cmd(
    ctx: typer.Context,
    transport: str = typer.Option("stdio", "--transport", "-t", help="Transport: stdio | sse | streamable-http"),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host (HTTP transports only)"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port (HTTP transports only)"),
    base_url: str = typer.Option("", "--base-url", help="Public HTTPS base URL for MCP OAuth (e.g. https://tori.example.com). Required for remote MCP on claude.ai."),
) -> None:
    """Run the Tori.fi MCP server."""
    if ctx.invoked_subcommand is not None:
        return  # let the subcommand handle it

    global _auth_provider, _storage

    if transport in ("sse", "streamable-http"):
        mcp.settings.host = host
        mcp.settings.port = port
        # Disable DNS-rebinding protection when:
        # - binding to a non-loopback address (exposed directly), or
        # - running behind a reverse proxy (--base-url set), where the Host
        #   header will be the public domain, not 127.0.0.1
        if host not in ("127.0.0.1", "localhost", "::1") or base_url:
            mcp.settings.transport_security = None

    if base_url and transport in ("sse", "streamable-http"):
        from mcp.server.auth.provider import ProviderTokenVerifier
        from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
        from .mcp_auth import ToriMCPAuthProvider
        from .mcp_storage import Storage

        _storage = Storage.open()
        _auth_provider = ToriMCPAuthProvider(base_url, storage=_storage)

        mcp._auth_server_provider = _auth_provider
        mcp._token_verifier = ProviderTokenVerifier(_auth_provider)
        mcp.settings.auth = AuthSettings(
            issuer_url=base_url,  # type: ignore[arg-type]
            client_registration_options=ClientRegistrationOptions(enabled=True),
            resource_server_url=None,
        )

    mcp.run(transport=transport)


@_app.command("allow")
def _allow_cmd(
    email: str = typer.Argument(..., help="Email address to allow"),
    note: str = typer.Option("", "--note", "-n", help="Optional note (e.g. the person's name)"),
) -> None:
    """Allow an email address to use the remote MCP server."""
    from .mcp_storage import Storage
    Storage.open().allow_email(email, note or None)
    typer.echo(f"Allowed: {email}")


@_app.command("revoke")
def _revoke_cmd(
    email: str = typer.Argument(..., help="Email address to revoke"),
) -> None:
    """Revoke access for an email address and clear their stored session."""
    from .mcp_storage import Storage
    user_id = Storage.open().revoke_email(email)
    # Evict the in-memory client cache if the server happens to be running
    # in the same process (rare, but harmless to do unconditionally).
    if user_id is not None:
        _client_cache.pop(user_id, None)
    typer.echo(f"Revoked: {email}" + (f" (user_id={user_id})" if user_id else " (was not found)"))


@_app.command("list-allowed")
def _list_allowed_cmd() -> None:
    """List all email addresses allowed to use the remote MCP server."""
    from .mcp_storage import Storage
    import datetime
    rows = Storage.open().list_allowed()
    if not rows:
        typer.echo("No allowed emails.")
        return
    for row in rows:
        added = datetime.datetime.fromtimestamp(row["added_at"]).strftime("%Y-%m-%d")
        note = f"  # {row['note']}" if row["note"] else ""
        typer.echo(f"{row['email']:40s}  {added}{note}")


def main() -> None:
    _app()


if __name__ == "__main__":
    main()
