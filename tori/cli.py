"""
Tori.fi CLI — tori <command> [args]

Commands:
  tori auth setup              One-time browser OAuth flow, saves refresh token
  tori auth status             Show stored credentials info

  tori listings                List active listings
  tori listings --facet FACET  Filter by state (ACTIVE/EXPIRED/DRAFT/DISPOSED/ALL)
  tori listings stats ID       Show clicks/messages/favorites for a listing
  tori listings dispose ID     Mark a listing as sold
  tori listings delete ID      Delete a listing (asks for confirmation)
  tori listings edit ID        Edit listing fields (--price, --title, --description)
  tori listings create         Create and publish a new listing

  tori messages                List conversations with unread counts
  tori messages read ID        Show full message thread for a conversation
  tori messages send ID TEXT   Send a message in a conversation

  tori favorites               List favorited items
"""

import json
import os
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich import print as rprint

app = typer.Typer(help="Tori.fi API client", no_args_is_help=True)
auth_app = typer.Typer(help="Authentication commands", no_args_is_help=True)
listings_app = typer.Typer(help="Listing management", invoke_without_command=True)
messages_app = typer.Typer(help="Messaging", invoke_without_command=True)

app.add_typer(auth_app, name="auth")
app.add_typer(listings_app, name="listings")
app.add_typer(messages_app, name="messages")

console = Console()


def get_client():
    from tori import ToriClient
    return ToriClient()


def _ad_type_from_subtitle(subtitle: str) -> str:
    """Extract Myydään/Ostetaan/Annetaan from a listing subtitle."""
    s = subtitle.lower()
    if "ostetaan" in s:
        return "Ostetaan"
    if "annetaan" in s:
        return "Annetaan"
    return "Myydään"


def _ad_type_from_title(title: str) -> str:
    """Infer type from listing title prefix (for messages where subtitle isn't available)."""
    t = title.strip().lower()
    if t.startswith("ostetaan"):
        return "Ostetaan"
    if t.startswith("annetaan"):
        return "Annetaan"
    return "Myydään"


# ── Auth ──────────────────────────────────────────────────────────────────────

@auth_app.command("setup")
def auth_setup(
    manual: bool = typer.Option(False, "--manual", help="Paste redirect URL manually (required on Windows/Linux if auto-capture fails)"),
):
    """One-time browser OAuth flow. Saves refresh token to ~/.config/tori/credentials.json."""
    from tori.auth_setup import main as _run_setup
    _run_setup(manual=manual)


@auth_app.command("status")
def auth_status():
    """Show stored credentials info."""
    from tori.auth import load_credentials
    import base64, json as _json
    try:
        creds = load_credentials()
    except RuntimeError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1)

    rt = creds["refresh_token"]
    # Decode JWT payload (no signature verification needed)
    try:
        payload_b64 = rt.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = _json.loads(base64.b64decode(payload_b64))
        import datetime
        exp = datetime.datetime.fromtimestamp(payload["exp"])
        user_id = payload.get("user_id", "unknown")
        rprint(f"[green]✓ Credentials found[/green]")
        rprint(f"  user_id:  {user_id}")
        rprint(f"  expires:  {exp:%Y-%m-%d} ({payload['exp']})")
        rprint(f"  token:    {rt[:40]}...")
    except Exception:
        rprint(f"[green]✓ Credentials found[/green] (could not decode token)")
        rprint(f"  token: {rt[:40]}...")


# ── Listings ──────────────────────────────────────────────────────────────────

@listings_app.callback(invoke_without_command=True)
def listings_default(
    ctx: typer.Context,
    facet: Optional[str] = typer.Option(None, "--facet", "-f", help="Filter: ACTIVE EXPIRED DRAFT DISPOSED ALL"),
):
    """List your Tori.fi listings."""
    if ctx.invoked_subcommand is not None:
        return
    client = get_client()
    with console.status("Fetching listings..."):
        data = client.listings.search(facet=facet)

    summaries = data.get("summaries", [])
    facets = data.get("facets", [])

    if facets:
        parts = [f"{f['label']} [bold]{f['total']}[/bold]" for f in facets]
        rprint("  " + "   ".join(parts))
        rprint()

    if not summaries:
        rprint("[dim]No listings found.[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("ID", style="dim", width=10)
    table.add_column("Title", no_wrap=True)
    table.add_column("Type", width=9)
    table.add_column("State", width=12)
    table.add_column("Clicks", justify="right", width=7)
    table.add_column("Favorites", justify="right", width=9)

    for s in summaries:
        ext = s.get("externalData", {})
        clicks = ext.get("clicks", {}).get("value", "-")
        favs = ext.get("favorites", {}).get("value", "-")
        state = s.get("state", {}).get("label", s.get("state", {}).get("type", "?"))
        title = s.get("data", {}).get("title", str(s.get("id")))
        subtitle = s.get("data", {}).get("subtitle", "")
        ad_type = _ad_type_from_subtitle(subtitle)
        table.add_row(str(s["id"]), title, ad_type, state, str(clicks), str(favs))

    console.print(table)


@listings_app.command("stats")
def listings_stats(ad_id: int = typer.Argument(..., help="Listing ID")):
    """Show performance stats for a listing."""
    client = get_client()
    with console.status("Fetching stats..."):
        data = client.listings.stats(ad_id)
    rprint(f"[bold]{data.get('heading', 'Stats')}[/bold] for listing {ad_id}")
    for item in data.get("items", []):
        rprint(f"  {item['label']}: [bold]{item['count']}[/bold]")
    if url := data.get("viewMoreUrl"):
        rprint(f"\n  [link={url}]{data.get('viewMoreLabel', url)}[/link]")


@listings_app.command("dispose")
def listings_dispose(ad_id: int = typer.Argument(..., help="Listing ID")):
    """Mark a listing as sold (merkitse myydyksi)."""
    client = get_client()
    with console.status(f"Marking {ad_id} as sold..."):
        client.listings.dispose(ad_id)
    rprint(f"[green]✓ Listing {ad_id} marked as sold.[/green]")


@listings_app.command("delete")
def listings_delete(
    ad_id: int = typer.Argument(..., help="Listing ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Permanently delete a listing."""
    if not yes:
        typer.confirm(f"Delete listing {ad_id}? This cannot be undone.", abort=True)
    client = get_client()
    with console.status(f"Deleting {ad_id}..."):
        client.listings.delete(ad_id)
    rprint(f"[green]✓ Listing {ad_id} deleted.[/green]")


@listings_app.command("edit")
def listings_edit(
    ad_id: int = typer.Argument(..., help="Listing ID"),
    price: Optional[int] = typer.Option(None, "--price", "-p", help="New price in euros"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="New title"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="New description"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Fetch and show current values without saving"),
):
    """Edit a listing (price, title, description)."""
    client = get_client()

    with console.status(f"Fetching listing {ad_id}..."):
        values, etag = client.listings.get_for_edit(ad_id)

    if dry_run:
        rprint(f"[bold]Current values for {ad_id}[/bold] (ETag: {etag})")
        rprint(f"  title:       {values.get('title', '-')}")
        cur_price = values.get("price", [{}])
        rprint(f"  price:       {cur_price[0].get('price_amount', '-') if cur_price else '-'} €")
        rprint(f"  description: {str(values.get('description', '-'))[:120]}")
        return

    if price is None and title is None and description is None:
        rprint("[red]Specify at least one of --price, --title, --description (or --dry-run to inspect).[/red]")
        raise typer.Exit(1)

    if price is not None:
        values["price"] = [{"price_amount": str(price)}]
    if title is not None:
        values["title"] = title
    if description is not None:
        values["description"] = description

    with console.status(f"Updating listing {ad_id}..."):
        result = client.listings.update(ad_id, values, etag)

    new_etag = result.get("etag", "")
    rprint(f"[green]✓ Listing {ad_id} updated.[/green]")
    if price is not None:
        rprint(f"  price → {price} €")
    if title is not None:
        rprint(f"  title → {title}")
    if description is not None:
        rprint(f"  description updated")
    if new_etag:
        rprint(f"  new ETag: {new_etag}")


@listings_app.command("create")
def listings_create(
    title: str = typer.Option(..., "--title", "-t", help="Listing title"),
    description: str = typer.Option(..., "--description", "-d", help="Listing description"),
    price: int = typer.Option(..., "--price", "-p", help="Price in euros"),
    category: str = typer.Option(..., "--category", "-c", help="Category ID (e.g. 193)"),
    postal_code: str = typer.Option(..., "--postal-code", "-z", help="Finnish postal code"),
    condition: str = typer.Option("2", "--condition", help="1=Uusi 2=Kuin uusi 3=Hyvä 4=Tyydyttävä"),
    trade_type: str = typer.Option("1", "--trade-type", help="1=Myydään 2=Ostetaan 3=Annetaan"),
    images: Optional[list[str]] = typer.Option(None, "--image", "-i", help="Image file path (repeat for multiple)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Upload and poll images but stop before publishing"),
):
    """Create and publish a new free listing."""
    client = get_client()
    status_msg = "Creating listing..." if not images else f"Creating listing with {len(images)} image(s)..."
    with console.status(status_msg):
        result = client.listings.create(
            title=title,
            description=description,
            price=price,
            category=category,
            postal_code=postal_code,
            condition=condition,
            trade_type=trade_type,
            image_paths=images or [],
            dry_run=dry_run,
        )
    ad_id = result.get("ad_id")
    if result.get("dry_run"):
        rprint(f"[yellow]Dry run complete. Draft {ad_id} left unpublished.[/yellow]")
        rprint(f"  Delete it: [bold]tori listings delete {ad_id}[/bold]")
        return
    completed = result.get("is-completed", False)
    if completed:
        rprint(f"[green]✓ Listing published![/green] ID: {ad_id}")
        rprint(f"  [link=https://www.tori.fi/{ad_id}]https://www.tori.fi/{ad_id}[/link]")
    else:
        rprint(f"[yellow]Listing created (ID: {ad_id}) but publish status unclear.[/yellow]")
        rprint(json.dumps(result, ensure_ascii=False))


# ── Messages ──────────────────────────────────────────────────────────────────

_CONV_CACHE = os.path.expanduser("~/.cache/tori/conversations.json")

def _save_conv_cache(id_map: dict) -> None:
    os.makedirs(os.path.dirname(_CONV_CACHE), exist_ok=True)
    with open(_CONV_CACHE, "w") as f:
        json.dump({str(k): v for k, v in id_map.items()}, f)

def _resolve_conv_id(ref: str) -> str:
    """Accept row number (e.g. '3') or a full conversation ID."""
    if ref.isdigit():
        if os.path.exists(_CONV_CACHE):
            with open(_CONV_CACHE) as f:
                cache = json.load(f)
            conv_id = cache.get(ref)
            if conv_id:
                return conv_id
        rprint(f"[red]No cached conversation #{ref}. Run 'tori messages' first.[/red]")
        raise typer.Exit(1)
    return ref  # treat as literal ID


@messages_app.callback(invoke_without_command=True)
def messages_default(
    ctx: typer.Context,
    show_ids: bool = typer.Option(False, "--ids", help="Show full conversation IDs"),
):
    """List conversations with unread counts."""
    if ctx.invoked_subcommand is not None:
        return
    client = get_client()
    with console.status("Fetching conversations..."):
        unread = client.messaging.unread_count()
        groups = client.messaging.list_conversations()

    rprint(f"[bold]Unread messages: {unread}[/bold]\n")

    if not groups:
        rprint("[dim]No conversations.[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Type", width=9)
    table.add_column("Listing", no_wrap=True)
    table.add_column("With", no_wrap=True)
    table.add_column("Last message", no_wrap=True)
    table.add_column("Unread", justify="right", width=7)
    if show_ids:
        table.add_column("ID", no_wrap=True)

    id_map = {}
    n = 0
    for group in groups:
        basis = group.get("groupBasis", {})
        item_info = basis.get("itemInfo", {})
        listing_title = item_info.get("title", "")
        ad_type = _ad_type_from_title(listing_title) if listing_title else ""

        for conv in group.get("conversations", []):
            n += 1
            conv_id = conv.get("conversationId", conv.get("id", "?"))
            id_map[n] = conv_id
            other = conv.get("partnerName", conv.get("otherParty", {}).get("name", "?"))
            last_msg = conv.get("lastMessagePreview", conv.get("latestMessage", {}).get("text", ""))
            if last_msg and len(last_msg) > 45:
                last_msg = last_msg[:45] + "…"
            unread_conv = conv.get("unseenCounter", conv.get("unreadMessageCount", 0))
            unread_str = f"[bold red]{unread_conv}[/bold red]" if unread_conv else "-"
            row = [str(n), ad_type, listing_title, other, last_msg, unread_str]
            if show_ids:
                row.append(conv_id)
            table.add_row(*row)

    console.print(table)
    _save_conv_cache(id_map)


@messages_app.command("read")
def messages_read(conversation_id: str = typer.Argument(..., help="Row number or full conversation ID")):
    """Show the full message thread for a conversation."""
    conv_id = _resolve_conv_id(conversation_id)
    client = get_client()
    with console.status("Loading messages..."):
        messages = client.messaging.list_messages(conv_id)

    if not messages:
        rprint("[dim]No messages.[/dim]")
        return

    uid = str(client.user_id)
    for msg in reversed(messages):  # show oldest first
        outgoing = msg.get("outgoing", False)
        sender = "You" if outgoing else msg.get("partnerName", "Them")
        date = msg.get("sent", msg.get("sendDate", ""))[:16].replace("T", " ")
        text = msg.get("body", msg.get("text", "[no text]"))
        if outgoing:
            rprint(f"[dim]{date}[/dim] [bold cyan]{sender}:[/bold cyan] {text}")
        else:
            rprint(f"[dim]{date}[/dim] [bold]{sender}:[/bold] {text}")


@messages_app.command("send")
def messages_send(
    conversation_id: str = typer.Argument(..., help="Row number or full conversation ID"),
    text: str = typer.Argument(..., help="Message text"),
):
    """Send a message in a conversation."""
    conv_id = _resolve_conv_id(conversation_id)
    client = get_client()
    with console.status("Sending..."):
        client.messaging.send(conv_id, text)
    rprint(f"[green]✓ Message sent.[/green]")


# ── Categories ────────────────────────────────────────────────────────────────

@app.command("categories")
def categories_cmd(
    query: Optional[str] = typer.Argument(None, help="Filter by name (Finnish keyword)"),
):
    """Browse categories to find the ID for listing creation or search."""
    client = get_client()
    with console.status("Fetching categories..."):
        cats = client.search.find_categories(query or "")

    if not cats:
        rprint(f"[yellow]No categories matching '{query}'.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("ID", style="dim", width=6)
    table.add_column("Category")
    table.add_column("Under", style="dim")
    table.add_column("Section", style="dim")

    for c in cats:
        table.add_row(c["id"], c["label"], c.get("parent", ""), c.get("section", ""))

    console.print(table)
    rprint(f"\n[dim]Use ID with: tori listings create --category ID[/dim]")


# ── Favorites ─────────────────────────────────────────────────────────────────

@app.command("favorites")
def favorites():
    """List favorited items."""
    client = get_client()
    with console.status("Fetching favorites..."):
        data = client.favorites.list()

    items = data.get("items", [])
    if not items:
        rprint("[dim]No favorites.[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("Item ID")
    table.add_column("Type")
    table.add_column("Folders")
    for item in items:
        table.add_row(
            str(item.get("itemId", "?")),
            item.get("itemType", "?"),
            str(item.get("folderIds", [])),
        )
    console.print(table)
    rprint(f"\n[dim]Total: {len(items)} items[/dim]")


# ── Search ────────────────────────────────────────────────────────────────────

@app.command("search")
def search_cmd(
    query: str = typer.Argument(..., help="Search query"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Category code, e.g. 1.93.3217"),
    location: Optional[str] = typer.Option(None, "--location", "-l", help="Region code, e.g. 0.100018 (Uusimaa)"),
    price_from: Optional[int] = typer.Option(None, "--price-from", help="Min price (EUR)"),
    price_to: Optional[int] = typer.Option(None, "--price-to", help="Max price (EUR)"),
    shipping: bool = typer.Option(False, "--shipping", help="ToriDiili items only"),
    page: int = typer.Option(1, "--page", "-p", help="Page number"),
    filters: bool = typer.Option(False, "--filters", help="Show available filter options"),
):
    """Search public Tori.fi listings."""
    client = get_client()
    with console.status(f"Searching for '{query}'..."):
        result = client.search.search(
            q=query,
            category=category,
            location=location or "",
            price_from=price_from,
            price_to=price_to,
            shipping_only=shipping,
            page=page,
            include_filters=filters,
        )

    promoted = result.get("promoted")
    docs = result.get("docs", [])

    if not docs and not promoted:
        rprint("[dim]No results.[/dim]")
        return

    if promoted:
        price = promoted.get("price", {})
        price_str = f"[bold green]{price.get('amount')} {price.get('price_unit', '€')}[/bold green]" if price.get("amount") else ""
        labels = ", ".join(l["text"] for l in promoted.get("labels", []) if l.get("type") == "PRIMARY")
        rprint(f"[bold yellow]📌 Paalupaikka[/bold yellow]  {promoted.get('heading', '')}  {price_str}  [dim]{promoted.get('location', '')}[/dim]")
        rprint()

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Type", width=9)
    table.add_column("Title", no_wrap=True)
    table.add_column("Price", justify="right", width=10, no_wrap=True)
    table.add_column("Location", style="dim", no_wrap=True)
    table.add_column("ID", style="dim", width=10)

    for i, doc in enumerate(docs, 1):
        price = doc.get("price", {})
        price_str = f"{price.get('amount')} {price.get('price_unit', '€')}" if price.get("amount") else "-"
        labels = [l["text"] for l in doc.get("labels", []) if l.get("type") == "PRIMARY"]
        title = doc.get("heading", "?")
        if labels:
            title += f" [dim]({', '.join(labels)})[/dim]"
        ad_type = doc.get("trade_type", "Myydään")
        table.add_row(
            str(i),
            ad_type,
            title,
            price_str,
            doc.get("location", "").split(",")[0],
            str(doc.get("ad_id", doc.get("id", ""))),
        )

    console.print(table)
    rprint(f"\n[dim]Page {page} · {len(docs)} results[/dim]")

    if filters and result.get("filters"):
        rprint("\n[bold]Available filters:[/bold]")
        for f in result["filters"]:
            rprint(f"  {f.get('name', f.get('id', '?'))}")


# ── Show listing ──────────────────────────────────────────────────────────────

@app.command("show")
def show_listing(ad_id: int = typer.Argument(..., help="Listing ID")):
    """Show full details of any listing (own or public)."""
    client = get_client()
    with console.status(f"Fetching listing {ad_id}..."):
        data = client.listings.get(ad_id)

    ad = data.get("ad", {})
    meta = data.get("meta", {})

    # Header
    ad_type = ad.get("adViewTypeLabel", "")
    title = ad.get("title", str(ad_id))
    price = ad.get("price")
    price_str = f"  [bold green]{price} €[/bold green]" if price else ""
    rprint(f"[bold]{title}[/bold]{price_str}  [dim]{ad_type}[/dim]")

    # Category + location
    cat = ad.get("category", {})
    cat_parts = []
    c = cat
    while c:
        cat_parts.insert(0, c.get("value", ""))
        c = c.get("parent")
    location = ad.get("location", {}).get("postalName", "")
    rprint(f"[dim]{' > '.join(cat_parts)}[/dim]  [dim]{location}[/dim]")
    rprint()

    # Extras (condition, brand, etc.)
    extras = ad.get("extras", [])
    if extras:
        for e in extras:
            rprint(f"  {e['label']}: [bold]{e['value']}[/bold]")
        rprint()

    # Description
    desc = ad.get("description", "")
    if desc:
        rprint(desc)
        rprint()

    # Images
    images = ad.get("images", [])
    if images:
        rprint(f"[dim]{len(images)} image(s):[/dim]")
        for img in images:
            rprint(f"  [dim]{img['uri']}[/dim]")
        rprint()

    # Metadata
    edited = meta.get("edited", "")[:10] if meta.get("edited") else ""
    if edited:
        rprint(f"[dim]Updated: {edited}  ID: {ad_id}[/dim]")
    else:
        rprint(f"[dim]ID: {ad_id}[/dim]")


if __name__ == "__main__":
    app()
