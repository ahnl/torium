# tori-client

Python client for the Tori.fi marketplace. Usable as a **library**, a **CLI tool**, and an **MCP server** for Claude Desktop / Claude Code.

## Installation

```bash
cd tori-client
uv venv && uv pip install -e .
```

## Authentication

First-time setup — opens a browser for OAuth login and saves a refresh token to `~/.config/tori/credentials.json`:

```bash
tori auth setup
```

All subsequent commands authenticate automatically. The refresh token rotates and is saved on each use (valid ~1 year; bearer token valid ~1 hour).

```bash
tori auth status   # show stored token info and expiry
```

---

## CLI Reference

### Listings

```bash
tori listings                      # active listings (default)
tori listings --facet ALL          # ACTIVE | EXPIRED | DRAFT | DISPOSED | ALL
tori listings stats <id>           # clicks, messages, favorites
tori listings dispose <id>         # mark as sold (merkitse myydyksi)
tori listings delete <id>          # permanently delete (asks for confirmation)
tori listings delete <id> --yes    # skip confirmation
tori listings edit <id> --price 7  # change price
tori listings edit <id> --title "New title" --description "..."
tori listings edit <id> --dry-run  # inspect current values without saving
```

### Search

```bash
tori search "iphone"
tori search "iphone" --category 1.93.3217
tori search "iphone" --price-from 100 --price-to 500
tori search "iphone" --shipping          # ToriDiili items only
tori search "iphone" --page 2
tori search "iphone" --filters           # show available filter options
```

Results include a promoted (paalupaikka) listing when one exists. The Type column shows Myydään / Ostetaan / Annetaan.

### Messages

```bash
tori messages                      # list conversations with unread counts
tori messages --ids                # also show full conversation IDs
tori messages read <n>             # show thread (use row number from the list)
tori messages send <n> "text"      # send a message
```

Row numbers are cached at `~/.cache/tori/conversations.json`. Re-run `tori messages` to refresh.

### Show listing

```bash
tori show <id>                     # full details of any listing (own or public)
```

Shows title, price, type, category, location, condition/extras, description, and image URLs.

### Favorites

```bash
tori favorites                     # list favorited items
```

---

## MCP Server (Claude Desktop / Claude Code)

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tori": {
      "command": "/path/to/tori-client/.venv/bin/python",
      "args": ["/path/to/tori-client/tori/mcp_server.py"]
    }
  }
}
```

Restart Claude Desktop. The following tools become available:

| Tool | Description |
|------|-------------|
| `list_my_listings` | Own listings, optional `facet` filter |
| `search_my_listings` | Own listings with full detail |
| `get_listing` | Full detail of any listing: title, description, price, extras, image URLs |
| `get_listing_stats` | Clicks / messages / favorites for a listing |
| `dispose_listing` | Mark a listing as sold |
| `delete_listing` | Permanently delete a listing |
| `edit_listing` | Edit price, title, or description of a listing |
| `get_unread_count` | Total unread messages |
| `list_conversations` | Inbox with unread counts |
| `get_conversation` | Full message thread |
| `send_message` | Send a message in a conversation |
| `list_favorites` | Favorited items |
| `search_listings` | Search public Tori.fi listings |
| `get_categories` | Full category tree (cache this) |
| `list_saved_searches` | Saved search alerts (hakuvahti) |
| `create_saved_search` | Create a hakuvahti |
| `delete_saved_search` | Delete a hakuvahti |
| `fetch_image` | Fetch a listing photo by URL and return it as an image for vision inspection |
| `fetch_image_base64` | Fetch a listing photo and return it as a base64 data URI for HTML embedding |

### Image inspection and display

Claude Desktop's `web_fetch` cannot load URLs that originate from MCP tool responses (a prompt-injection security restriction). Both image tools work around this by fetching server-side.

**`fetch_image`** — returns the image as an MCP image object. Use this when you want Claude to inspect a photo with vision: condition, model numbers, serial numbers, spec stickers, visible damage, included accessories, port layout, etc.

**`fetch_image_base64`** — returns a `data:image/jpeg;base64,...` URI. Use this to embed photos in an HTML artifact rendered inside Claude Desktop. Drop the returned string straight into an `<img src="...">` tag to build listing cards, search result galleries, or side-by-side comparisons.

```html
<!-- example: listing card from fetch_image_base64 -->
<img src="data:image/jpeg;base64,..." style="width:100%;border-radius:8px">
```

---

## Library Usage

```python
from tori import ToriClient

client = ToriClient()                        # reads ~/.config/tori/credentials.json
client = ToriClient(refresh_token="eyJ...")  # explicit token

# Listings
listings = client.listings.search(facet="ACTIVE")
client.listings.dispose(12345)
client.listings.delete(12345)
stats = client.listings.stats(12345)
client.listings.set_price(12345, 7)          # change price directly
values, etag = client.listings.get_for_edit(12345)  # fetch for editing
values["title"] = "New title"
client.listings.update(12345, values, etag)  # submit full update

# Messaging
convs = client.messaging.list_conversations()
msgs = client.messaging.list_messages(conv_id)
client.messaging.send(conv_id, "Kiinnostaa!")

# Search
results = client.search.search("iphone", price_from=100, price_to=500)
categories = client.search.categories()

# Favorites
favs = client.favorites.list()
```

---

## Project Structure

```
tori/
├── auth.py        # OAuth flow, credential storage, ToriAuth class
├── client.py      # ToriClient: HTTP session, signing, auth retry
├── signing.py     # finn-gw-key HMAC-SHA512 signing
├── listings.py    # ListingsAPI
├── messaging.py   # MessagingAPI
├── favorites.py   # FavoritesAPI
├── search.py      # SearchAPI (public search + hakuvahti)
├── cli.py         # Typer CLI
└── mcp_server.py  # FastMCP server
```
