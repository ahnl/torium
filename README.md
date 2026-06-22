<p align="center">
  <img src="docs/torium-kawaii.png" alt="Torium" width="360">
</p>

<p align="center">
  <strong>An unofficial Python client for the Finnish Tori.fi marketplace. 🇫🇮&nbsp;</strong>
</p>
<p align="center">
  Browse listings, manage your own listings, and chat with buyers. From the terminal, your Python code, or Claude.
</p>

<p align="center">
  <a href="#installation">Installation</a> &bull;
  <a href="#cli-reference">CLI</a> &bull;
  <a href="#mcp-tools">MCP Tools</a> &bull;
  <a href="#library-usage">Library</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/MCP-server-7c3aed" alt="MCP server">
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="License: MIT">
</p>

---

## Installation

Choose your preferred installation method:

- [Hosted remote MCP server](#hosted-remote-mcp-server). Easiest, just connect claude.ai or ChatGPT to `https://torium.fi/mcp`.
- [Local install (MCP and CLI)](#local-install-mcp-and-cli). Run the MCP server and CLI on your own machine.
- [Self-hosted remote MCP server](#self-hosted-remote-mcp-server). Host the remote MCP server yourself.

### Hosted remote MCP server

The simplest way to use Torium. We host the MCP server at `https://torium.fi/mcp`. Just add it as a connector in claude.ai and log in with your Tori.fi account.

See **[torium.fi](https://torium.fi)** for setup instructions and a video walkthrough.

### Local install (MCP and CLI)

**1. Clone and install:**

```bash
git clone https://github.com/ahnl/torium
uv tool install ./torium
```

This places `torium-mcp` (and `torium`) on your PATH globally.

**2. Authenticate (once):**

```bash
torium auth setup
```

Opens a browser for OAuth login. On macOS and Linux the redirect is captured automatically (Linux registers a temporary `.desktop` URL handler via `xdg-mime`).

On Windows, after login the browser will show an infinite loading spinner or a "can't open" error. Open the browser's developer tools (F12) → Console, find the failed redirect URL starting with `fi.tori.www...`, right-click it to copy the link address, and paste it into the terminal. **Do this quickly. The code in the URL expires in 30-60 seconds.**

Credentials will be saved to `~/.config/torium/credentials.json`. Alternatively, set `TORI_REFRESH_TOKEN` in your environment. The MCP server will use it directly, no credentials file needed.

**3. MCP: Add to Claude Desktop:**

Go to **Settings → Developer → Edit Config** and add:

```json
{
  "mcpServers": {
    "torium": {
      "command": "torium-mcp"
    }
  }
}
```

Restart Claude Desktop. The torium tools are now available.

**Updating:**

```bash
cd torium && git pull && uv tool install --reinstall .
```

### Self-hosted remote MCP server

You can run `torium-mcp` as a remote HTTPS server that multiple users connect to via claude.ai connectors. Each user authenticates their own Tori.fi account through a one-time OAuth popup.

By default, the server uses an email whitelist. You must allow each user before they can log in.

**1. Allow your email (must be done before first login):**

```bash
torium-mcp allow you@example.com --note "your name"
torium-mcp list-allowed    # see who has access
torium-mcp revoke foo@example.com  # remove access
```

**2. Start the server:**

```bash
torium-mcp --transport streamable-http --host 127.0.0.1 --port 5001 --base-url https://tori.example.com
```

The `--base-url` must be the public HTTPS URL that claude.ai can reach (e.g. via a reverse proxy or SSH tunnel).

**3. Add `https://tori.example.com/mcp` in claude.ai connectors.**

Claude opens a login popup. Click **Log in to Tori.fi**, complete the Schibsted login, then copy the `fi.tori.www...` redirect URL from the browser console and paste it into the form. After that, Claude has a 180-day session, with no further logins needed until it expires.

> Each user's Tori credentials are stored separately in SQLite (`~/.config/torium/mcp.db`). The local `~/.config/torium/credentials.json` file used by stdio mode is never touched by the remote server.

---

## Authentication

```bash
torium auth setup    # first-time OAuth login (see Local install above), saves refresh token
torium auth status   # show stored token info and expiry
```

You can also skip the browser flow entirely by setting `TORI_REFRESH_TOKEN` in your environment.

The refresh token rotates and is saved on each use (valid ~1 year; bearer token valid ~1 hour).

---

## CLI Reference

### Listings

```bash
torium listings                      # active listings (default 50)
torium listings --facet ALL          # ACTIVE | EXPIRED | DRAFT | DISPOSED | ALL
torium listings --limit 200          # auto-paginate beyond default 50
torium listings stats <id>           # clicks, messages, favorites
torium listings dispose <id>         # mark as sold (merkitse myydyksi)
torium listings delete <id>          # permanently delete (asks for confirmation)
torium listings delete <id> --yes    # skip confirmation
torium listings republish <id>       # republish an expired listing as Basic (free)
torium listings edit <id> --price 7  # change price
torium listings edit <id> --title "New title" --description "..."
torium listings edit <id> --dry-run  # inspect current values without saving
torium categories --for-create       # browse categories with IDs for listing creation
torium categories kengät --for-create  # filter by Finnish keyword
torium listings create --title "Kenkä" --description "..." --price 10 --category 193 --postal-code 96100
torium listings create ... --condition 3 --trade-type 1  # condition: 1=Uusi 2=Kuin uusi 3=Hyvä 4=Tyydyttävä
```

### Search

```bash
torium search "iphone"
torium search "iphone" --category 1.93.3217
torium search "iphone" --location 1.100018.110091  # filter by region/municipality
torium search "iphone" --price-from 100 --price-to 500
torium search "iphone" --shipping          # ToriDiili items only
torium search "iphone" --page 2
torium search "iphone" --filters           # show available filter options
torium categories                    # browse categories with codes for search (default, same as --for-search)
torium categories kengät             # filter by Finnish keyword
torium locations                     # browse regions and municipalities
torium locations helsinki            # filter by Finnish keyword
```

Results include a promoted (paalupaikka) listing when one exists. The Type column shows Myydään / Ostetaan / Annetaan.

### Messages

```bash
torium messages                      # list conversations with unread counts
torium messages --ids                # also show full conversation IDs
torium messages read <n>             # show thread (use row number from the list)
torium messages send <n> "text"      # send a message
```

Row numbers are cached at `~/.cache/torium/conversations.json`. Re-run `torium messages` to refresh.

### Show listing

```bash
torium show <id>                     # full details of any listing (own or public)
```

Shows title, price, type, category, location, condition/extras, description, and image URLs.

### Favorites

```bash
torium favorites                     # list favorited items
```

---

## MCP Tools

See [Local install (MCP and CLI)](#local-install-mcp-and-cli) above for setup. The following tools become available once the server is running:


| Tool                  | Description                                                                  |
| --------------------- | ---------------------------------------------------------------------------- |
| `list_my_listings`    | Own listings, optional `facet` filter; returns all (auto-paginated)          |
| `search_my_listings`  | Own listings with full detail; returns all (auto-paginated)                  |
| `get_listing`         | Full detail of any listing: title, description, price, extras, image URLs    |
| `get_listing_stats`   | Clicks / messages / favorites for a listing                                  |
| `get_create_categories` | Find category IDs by Finnish keyword (for create_listing)                  |
| `create_listing`      | Create and submit a new free listing, with optional ToriDiili shipping        |
| `dispose_listing`     | Mark a listing as sold                                                       |
| `delete_listing`      | Permanently delete a listing                                                 |
| `republish_listing`   | Republish an expired listing as Basic (free)                                 |
| `edit_listing`        | Edit price, title, or description of a listing                               |
| `get_unread_count`    | Total unread messages                                                        |
| `list_conversations`  | Inbox with unread counts                                                     |
| `get_conversation`    | Full message thread                                                          |
| `send_message`        | Send a message in a conversation                                             |
| `list_favorites`      | Favorited items                                                              |
| `search_listings`     | Search public Tori.fi listings                                               |
| `get_search_categories` | Find category codes by Finnish keyword (for search_listings)               |
| `get_locations`       | Find region/municipality codes by Finnish keyword (for search_listings)      |
| `list_saved_searches` | Saved search alerts (hakuvahti)                                              |
| `create_saved_search` | Create a hakuvahti                                                           |
| `delete_saved_search` | Delete a hakuvahti                                                           |
| `fetch_image`         | Fetch a listing photo by URL and return it as an image for vision inspection |
| `fetch_image_base64`  | Fetch a listing photo and return it as a base64 data URI for HTML embedding  |


### ToriDiili shipping

`create_listing` (and the `create` / `set_delivery` library methods) can enable ToriDiili
shipping with `shipping=True`. When shipping is enabled, `package_size` selects the parcel
tier and a `city` is required (the API needs `shippingInfo.city` + `shippingInfo.postalCode`):

| `package_size` | Finnish label | Max weight | Max dimensions   |
| -------------- | ------------- | ---------- | ---------------- |
| `"SMALL"`      | Peruspaketti  | 4 kg       | 40 × 32 × 15 cm  |
| `"MEDIUM"`     | Iso paketti   | 10 kg      | 40 × 32 × 26 cm  |
| `"LARGE"`      | Jättipaketti  | 24 kg      | 100 × 60 × 60 cm |

Default is `"SMALL"` (Peruspaketti). The seller's name, phone and address are taken from the
account profile server-side, so only `city` + `postal_code` need to be supplied. Other delivery
options: `meetup` (buyer pickup, default on), `buy_now` ("Osta heti"), and `seller_pays_shipping`.

### Image inspection and display

Claude Desktop's `web_fetch` cannot load URLs that originate from MCP tool responses (a prompt-injection security restriction). Both image tools work around this by fetching server-side.

`**fetch_image**` returns the image as an MCP image object. Use this when you want Claude to inspect a photo with vision: condition, model numbers, serial numbers, spec stickers, visible damage, included accessories, port layout, etc.

`**fetch_image_base64**` returns a `data:image/jpeg;base64,...` URI. Use this to embed photos in an HTML artifact rendered inside Claude Desktop. Drop the returned string straight into an `<img src="...">` tag to build listing cards, search result galleries, or side-by-side comparisons.

```html
<!-- example: listing card from fetch_image_base64 -->
<img src="data:image/jpeg;base64,..." style="width:100%;border-radius:8px">
```

---

## Library Usage

```python
from torium import ToriClient

client = ToriClient()                        # reads ~/.config/torium/credentials.json
client = ToriClient(refresh_token="eyJ...")  # explicit token

# Listings
listings = client.listings.search(facet="ACTIVE")
client.listings.dispose(12345)
client.listings.delete(12345)
stats = client.listings.stats(12345)
client.listings.create("Title", "Desc", price=10, category="193", postal_code="96100")
client.listings.create("Title", "Desc", price=10, category="193", postal_code="96100",
                       shipping=True, package_size="MEDIUM", city="Helsinki")  # offer ToriDiili shipping
client.listings.set_delivery(12345, shipping=True, package_size="LARGE",
                             city="Helsinki", postal_code="00100")  # change delivery options
client.listings.republish(12345)             # republish an expired listing
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

## Disclaimer

Torium is an independent, community-developed interoperability client for
the Tori.fi marketplace. It is not affiliated with, endorsed by, or
sponsored by Tori.fi, Vend Marketplaces Oy, or Schibsted.

This software is provided "as is", without warranty of any kind.

By using Torium, you acknowledge that:
- You are the registered holder of the Tori.fi account you authenticate with
- Your use is your own responsibility and must comply with any agreements
  you have with third parties, including Tori.fi
- The authors assume no liability for any consequences of your use

---

## Project Structure

```
torium/
├── auth.py          # OAuth flow, credential storage, ToriAuth class
├── client.py        # ToriClient: HTTP session, signing, auth retry
├── signing.py       # finn-gw-key HMAC-SHA512 signing
├── listings.py      # ListingsAPI
├── messaging.py     # MessagingAPI
├── favorites.py     # FavoritesAPI
├── search.py        # SearchAPI (public search + hakuvahti)
├── cli.py           # Typer CLI
├── mcp_server.py    # FastMCP server + login routes + CLI (serve/allow/revoke)
├── mcp_auth.py      # MCP OAuth 2.1 provider + Schibsted code exchange
└── mcp_storage.py   # SQLite storage for multi-tenant sessions and tokens
```

---

## Star History

<a href="https://www.star-history.com/?repos=ahnl%2Ftorium&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=ahnl/torium&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=ahnl/torium&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=ahnl/torium&type=date&legend=top-left" />
 </picture>
</a>

---

## License

[MIT](LICENSE)
