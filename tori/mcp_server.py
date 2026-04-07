"""
Tori.fi MCP Server.

Install globally:
  uv tool install ./tori-client

Run:
  tori-mcp

Claude Desktop config (~/Library/Application Support/Claude/claude_desktop_config.json):
  {
    "mcpServers": {
      "tori": {
        "command": "tori-mcp"
      }
    }
  }
"""

import json
import os
from functools import lru_cache

import requests
import typer
from mcp.server.fastmcp import FastMCP, Image

mcp = FastMCP("tori", instructions=(
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
    "comparison. fetch_image_base64 is for rendering; fetch_image is for vision inspection."
))


@lru_cache(maxsize=1)
def _client():
    from tori import ToriClient
    return ToriClient()


# ── Listings ──────────────────────────────────────────────────────────────────

@mcp.tool()
def list_my_listings(facet: str = "ACTIVE") -> str:
    """
    List the user's own Tori.fi listings.

    facet: ACTIVE (default) | EXPIRED | DRAFT | DISPOSED | ALL
    Returns listing summaries with IDs, titles, states, click counts.
    """
    data = _client().listings.search(facet=facet if facet != "ACTIVE" or facet else None)
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
    data = _client().listings.get(ad_id)
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
    data = _client().listings.stats(ad_id)
    return json.dumps(data, ensure_ascii=False)


@mcp.tool()
def dispose_listing(ad_id: int) -> str:
    """
    Mark a listing as sold (merkitse myydyksi). This hides it from search results
    and moves it to the "Myydyt" (sold) category.

    ad_id: The listing ID to mark as sold.
    """
    _client().listings.dispose(ad_id)
    return f"Listing {ad_id} marked as sold."


@mcp.tool()
def delete_listing(ad_id: int) -> str:
    """
    Permanently delete a listing. This action cannot be undone.

    ad_id: The listing ID to delete.
    """
    _client().listings.delete(ad_id)
    return f"Listing {ad_id} deleted."


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
) -> str:
    """
    Create and publish a new free (Basic) listing on Tori.fi.

    title:        Listing title.
    description:  Listing description.
    price:        Price in euros (integer). Use 0 for free items.
    category:     Tori category ID as a string. Use get_create_categories() to find IDs.
    postal_code:  Finnish postal code, e.g. "96100".
    condition:    "1"=Uusi, "2"=Kuin uusi (default), "3"=Hyvä, "4"=Tyydyttävä.
    trade_type:   "1"=Myydään (default), "2"=Ostetaan, "3"=Annetaan.
    image_paths:  Comma-separated absolute paths to local image files (JPEG/PNG).
                  e.g. "/Users/me/photo1.jpg,/Users/me/photo2.jpg"
    """
    paths = [p.strip() for p in image_paths.split(",") if p.strip()] if image_paths else []
    result = _client().listings.create(
        title=title,
        description=description,
        price=price,
        category=category,
        postal_code=postal_code,
        condition=condition,
        trade_type=trade_type,
        image_paths=paths,
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

    c = _client()
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
    count = _client().messaging.unread_count()
    return json.dumps({"unread_message_count": count})


@mcp.tool()
def list_conversations(limit: int = 20, offset: int = 0) -> str:
    """
    List conversation groups, each grouped by listing.

    Returns conversation IDs, listing titles, other party names, last messages,
    and unread counts.
    """
    client = _client()
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
    client = _client()
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
    result = _client().messaging.send(conversation_id, text)
    return json.dumps({"success": True, "message": result}, ensure_ascii=False)


# ── Favorites ─────────────────────────────────────────────────────────────────

@mcp.tool()
def list_favorites() -> str:
    """List all items the user has added to favorites, with item IDs and types."""
    data = _client().favorites.list()
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
    data = _client().listings.search(
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
    result = _client().search.search(
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
    cats = _client().search.find_search_categories(query)
    return json.dumps(cats, ensure_ascii=False)


@mcp.tool()
def get_create_categories(query: str = "") -> str:
    """
    Search categories by Finnish name. Returns category IDs for create_listing().

    query: Finnish keyword (e.g. "kengät", "puhelin"). Empty = all categories.

    Use the 'id' field as the category param in create_listing().
    """
    cats = _client().search.find_categories(query)
    return json.dumps(cats, ensure_ascii=False)


@mcp.tool()
def get_locations(query: str = "") -> str:
    """
    Get available location/region codes for filtering search results.

    Returns regions (maakunnat) and municipalities (kunnat) with their codes.
    Use the 'code' field as the location parameter in search_listings().

    query: Finnish keyword to filter by (e.g. "Helsinki", "Uusimaa"). Empty = all.
    """
    locs = _client().search.find_locations(query)
    return json.dumps(locs, ensure_ascii=False)


@mcp.tool()
def list_saved_searches() -> str:
    """List all saved search alerts (hakuvahti) for the user."""
    data = _client().search.list_saved_searches()
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
    new_id = _client().search.create_saved_search(
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
    _client().search.delete_saved_search(saved_search_id)
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


_app = typer.Typer(add_completion=False, invoke_without_command=True)


@_app.command()
def _cmd(
    transport: str = typer.Option("stdio", "--transport", "-t", help="Transport: stdio | sse | streamable-http"),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host (HTTP transports only)"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port (HTTP transports only)"),
) -> None:
    if transport in ("sse", "streamable-http"):
        os.environ.setdefault("FASTMCP_HOST", host)
        os.environ.setdefault("FASTMCP_PORT", str(port))
    mcp.run(transport=transport)


def main() -> None:
    _app()


if __name__ == "__main__":
    main()
