"""
Listings management commands for guesty-cli.
"""
import argparse
import json
from guesty_cli.core.config import load_config
from guesty_cli.core.database import get_db
from guesty_cli.core.client import GuestyClient
from guesty_cli.core.output import (
    print_table, print_card, print_json, print_csv,
    bold, cyan, green, red, yellow, format_money
)
from guesty_cli.utils.dates import parse_date


def _resolve_listing(db, identifier):
    """Resolve a listing nickname or ID to its actual ID."""
    # Try exact ID match first
    row = db.execute("SELECT id, nickname FROM listings WHERE id = ?", (identifier,)).fetchone()
    if row:
        return row['id'], row['nickname']
    # Try nickname match (case-insensitive partial match)
    row = db.execute("SELECT id, nickname FROM listings WHERE LOWER(nickname) LIKE LOWER(?)", (f'%{identifier}%',)).fetchone()
    if row:
        return row['id'], row['nickname']
    return None, None


KNOWN_LISTING_ACTIONS = {'get', 'create', 'update', 'delete'}


def register(subparsers):
    """Register listings commands with the argument parser."""
    # guesty listings [action] ...
    list_parser = subparsers.add_parser(
        'listings',
        help='List, show, update listings and manage descriptions'
    )
    list_parser.set_defaults(func=run_listings_router)

    # Positional: action + optional ID
    list_parser.add_argument('action', nargs='?', default='list',
                             help='Action: list (default), show, update, descriptions, amenities')
    list_parser.add_argument('listing_id', nargs='?', default=None,
                             help='Listing ID or nickname (for show/update)')

    # List filters
    list_parser.add_argument('--active', action='store_true', help='Show only active listings')
    list_parser.add_argument('--city', type=str, help='Filter by city')
    list_parser.add_argument('--status', type=str, help='Filter by status')

    # Output format
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    list_parser.add_argument('--csv', action='store_true', help='Output as CSV')
    list_parser.add_argument('--live', action='store_true', help='Query live API instead of local DB')

    # Update fields
    list_parser.add_argument('--title', type=str, help='New listing title')
    list_parser.add_argument('--description', type=str, help='Public description summary')
    list_parser.add_argument('--space', type=str, help='Space description (publicDescription.space)')
    list_parser.add_argument('--access', type=str, help='Access info (publicDescription.access)')
    list_parser.add_argument('--neighborhood', type=str, help='Neighborhood info (publicDescription.neighborhood)')
    list_parser.add_argument('--transit', type=str, help='Transit info (publicDescription.transit)')
    list_parser.add_argument('--notes', type=str, help='Host notes (publicDescription.notes)')
    list_parser.add_argument('--interaction', type=str, help='Interaction text (publicDescription.interactionWithGuests)')
    list_parser.add_argument('--house-rules', type=str, dest='house_rules', help='House rules (publicDescription.houseRules)')
    list_parser.add_argument('--from-file', type=str, dest='from_file', help='Read description from file')
    list_parser.add_argument('--confirm', action='store_true', help='Actually send update (dry-run by default)')

    # Show section filter
    list_parser.add_argument('--section', type=str, 
                             choices=['summary', 'space', 'access', 'neighborhood', 'transit', 'notes', 'interaction', 'house-rules', 'amenities', 'all'],
                             help='Show only a specific section (for show action)')

    # Amenities management
    list_parser.add_argument('--add-amenity', type=str, action='append', dest='add_amenities', help='Add amenity (repeatable)')
    list_parser.add_argument('--remove-amenity', type=str, action='append', dest='remove_amenities', help='Remove amenity (repeatable)')

    # guesty listing - single parser for shortcuts
    listing_parser = subparsers.add_parser(
        'listing',
        help='Manage a specific listing'
    )

    listing_parser.add_argument('--json', action='store_true', help='Output as JSON')
    listing_parser.add_argument('--live', action='store_true', help='Query live API')

    listing_parser.add_argument('arg1', nargs='?', default=None,
                                 help='Action (get/create/update/delete) OR listing name for shortcut')
    listing_parser.add_argument('arg2', nargs='?', default=None,
                                 help='Listing name (when action specified)')

    # Create/update options
    listing_parser.add_argument('--title', type=str, help='Listing title (required for create)')
    listing_parser.add_argument('--nickname', type=str, help='Listing nickname')
    listing_parser.add_argument('--address', type=str, help='Street address')
    listing_parser.add_argument('--city', type=str, help='City')
    listing_parser.add_argument('--state', type=str, help='State/Province')
    listing_parser.add_argument('--country', type=str, default='US', help='Country code (default: US)')
    listing_parser.add_argument('--bedrooms', type=int, help='Number of bedrooms')
    listing_parser.add_argument('--bathrooms', type=float, help='Number of bathrooms')
    listing_parser.add_argument('--max-guests', type=int, help='Maximum number of guests')
    listing_parser.add_argument('--type', type=str, help='Property type (e.g., Villa, Apartment)')
    listing_parser.add_argument('--dry-run', action='store_true', help='Show what would be sent without sending')
    listing_parser.add_argument('--confirm', action='store_true', help='Confirm deletion (required)')

    listing_parser.set_defaults(func=run_listing_router)


def run_listings_router(args):
    """Route listings commands based on action."""
    action = args.action

    if action == 'list':
        run_list(args)
    elif action == 'show':
        if not args.listing_id:
            print(red("Error: listings show requires a listing ID or nickname"))
            print(yellow("Usage: guesty listings show <id-or-nickname> [--live] [--json]"))
            return
        run_show(args)
    elif action == 'update':
        if not args.listing_id:
            print(red("Error: listings update requires a listing ID or nickname"))
            print(yellow("Usage: guesty listings update <id-or-nickname> --title 'New Title' [--confirm]"))
            return
        run_update_descriptions(args)
    elif action == 'descriptions':
        run_descriptions(args)
    elif action == 'amenities':
        run_amenities_overview(args)
    else:
        print(red(f"Unknown action: {action}"))
        print(yellow("Available: list, show, update, descriptions, amenities"))


def run_listing_router(args):
    """Route listing commands based on first positional argument."""
    arg1 = getattr(args, 'arg1', None)
    arg2 = getattr(args, 'arg2', None)

    if arg1 in KNOWN_LISTING_ACTIONS:
        action = arg1
        listing_name = arg2
    else:
        action = 'get'
        listing_name = arg1

    if action == 'get':
        if not listing_name:
            print(yellow("Usage: guesty listing <nickname>  (shortcut for 'guesty listing get <nickname>')"))
            print(yellow("       guesty listing get <nickname>"))
            print(yellow("       guesty listing create --title ..."))
            print(yellow("       guesty listing update <nickname> ..."))
            print(yellow("       guesty listing delete <nickname>"))
            return
        args.id_or_nickname = listing_name
        run_get(args)
    elif action == 'create':
        run_create(args)
    elif action == 'update':
        if not listing_name:
            print(red("Error: update requires a listing name"))
            print(yellow("Usage: guesty listing update <nickname> [options]"))
            return
        args.id_or_nickname = listing_name
        run_update_legacy(args)
    elif action == 'delete':
        if not listing_name:
            print(red("Error: delete requires a listing name"))
            print(yellow("Usage: guesty listing delete <nickname>"))
            return
        args.id_or_nickname = listing_name
        run_delete(args)


# ─── listings list ───────────────────────────────────────────────────────────

def run_list(args):
    """List all listings."""
    config = load_config()

    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        try:
            listings = client.api_get_all('/v1/listings', {})
        except Exception as e:
            print(red(f"Error fetching listings: {e}"))
            return
    else:
        db = get_db()
        query = "SELECT * FROM listings WHERE 1=1"
        params = []

        if args.active:
            query += " AND active = 1"
        if args.city:
            query += " AND city LIKE ?"
            params.append(f'%{args.city}%')
        if args.status:
            query += " AND status = ?"
            params.append(args.status)

        query += " ORDER BY nickname"

        try:
            cursor = db.execute(query, params)
            listings = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(red(f"Error querying database: {e}"))
            return

    if not listings:
        print(yellow("No listings found"))
        return

    headers = ['Nickname', 'Title', 'City', 'Beds/Baths', 'Max', 'Status']
    rows = []
    for l in listings:
        beds = l.get('bedrooms', 0) or 0
        baths = l.get('bathrooms', 0) or 0
        rows.append([
            l.get('nickname', 'N/A'),
            l.get('title', 'N/A')[:40],
            l.get('city', 'N/A'),
            f"{beds}/{baths}",
            l.get('max_guests') or l.get('maxGuests', 'N/A'),
            green('Active') if l.get('active') else red('Inactive')
        ])

    if args.json:
        print_json(listings)
    elif args.csv:
        print_csv(headers, rows)
    else:
        print(f"\n{bold('Listings')}")
        print_table(headers, rows)


# ─── listings show ───────────────────────────────────────────────────────────

def _get_raw_data(db, listing_id):
    """Get parsed raw_data JSON for a listing."""
    row = db.execute("SELECT raw_data FROM listings WHERE id = ?", (listing_id,)).fetchone()
    if row and row['raw_data']:
        return json.loads(row['raw_data'])
    return {}


def run_show(args):
    """Show full details for a single listing."""
    db = get_db()
    listing_id, nickname = _resolve_listing(db, args.listing_id)

    if not listing_id:
        print(red(f"Listing '{args.listing_id}' not found"))
        return

    if args.live:
        config = load_config()
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        try:
            raw = client.api_get(f'/v1/listings/{listing_id}')
        except Exception as e:
            print(red(f"Error fetching listing: {e}"))
            return
    else:
        raw = _get_raw_data(db, listing_id)
        if not raw:
            # Fall back to DB columns
            row = db.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
            raw = dict(row) if row else {}

    if getattr(args, 'json', False):
        print_json(raw)
        return

    pub_desc = raw.get('publicDescription', {}) or {}
    amenities = raw.get('amenities', [])
    section = getattr(args, 'section', None)

    # Section-specific output
    section_map = {
        'summary': 'summary',
        'space': 'space',
        'access': 'access',
        'neighborhood': 'neighborhood',
        'transit': 'transit',
        'notes': 'notes',
        'interaction': 'interactionWithGuests',
        'house-rules': 'houseRules',
    }

    if section and section != 'all':
        title = raw.get('nickname') or nickname
        if section == 'amenities':
            print(f"\n{bold(f'{title} — Amenities')} ({len(amenities)} total)\n")
            for a in sorted(amenities):
                print(f"  • {a}")
            return
        
        key = section_map.get(section)
        if key:
            val = pub_desc.get(key, '')
            label = section.replace('-', ' ').title()
            print(f"\n{bold(f'{title} — {label}')}\n")
            if val:
                for line in _wrap_text(val, 76):
                    print(f"  {line}")
            else:
                print(f"  (empty)")
            return

    # Basic info
    address = raw.get('address', {})
    if isinstance(address, dict):
        addr_str = address.get('full', 'N/A')
    else:
        addr_str = address or 'N/A'

    priv_desc_raw = raw.get('privateDescription', '') or ''
    if isinstance(priv_desc_raw, dict):
        priv_desc = '\n'.join(f"  {k}: {v}" for k, v in priv_desc_raw.items() if v)
    else:
        priv_desc = priv_desc_raw

    card_data = {
        'ID': raw.get('_id') or listing_id,
        'Nickname': raw.get('nickname') or nickname,
        'Title': raw.get('title', 'N/A'),
        'Status': green('Active') if raw.get('active') else red('Inactive'),
        'Property Type': raw.get('propertyType', 'N/A'),
        'Address': addr_str,
        'Bedrooms': raw.get('bedrooms', 'N/A'),
        'Bathrooms': raw.get('bathrooms', 'N/A'),
        'Max Guests': raw.get('accommodates', 'N/A'),
        'Check-in': raw.get('defaultCheckInTime', 'N/A'),
        'Check-out': raw.get('defaultCheckOutTime', 'N/A'),
    }

    print_card(f"Listing: {raw.get('nickname') or nickname}", card_data)

    # Amenities
    if amenities:
        print(f"\n{bold('Amenities')}")
        # Show in columns
        for i in range(0, len(amenities), 3):
            row_items = amenities[i:i+3]
            print("  " + "  |  ".join(row_items))

    # Public Description
    if pub_desc:
        print(f"\n{bold('Public Description')}")
        desc_fields = [
            ('Summary', 'summary'),
            ('Space', 'space'),
            ('Access', 'access'),
            ('Neighborhood', 'neighborhood'),
            ('Transit', 'transit'),
            ('Notes', 'notes'),
            ('Interaction with Guests', 'interactionWithGuests'),
            ('House Rules', 'houseRules'),
        ]
        for label, key in desc_fields:
            val = pub_desc.get(key)
            if val:
                print(f"\n  {cyan(label)}:")
                # Word-wrap long text at ~80 chars
                for line in _wrap_text(val, 76):
                    print(f"    {line}")

    # Private Description
    if priv_desc:
        print(f"\n{bold('Private Description')}")
        for line in _wrap_text(priv_desc, 76):
            print(f"    {line}")

    # Terms
    terms = raw.get('terms', {})
    if terms:
        print(f"\n{bold('Terms')}")
        if terms.get('minNights'):
            print(f"  Min Nights: {terms['minNights']}")
        if terms.get('maxNights'):
            print(f"  Max Nights: {terms['maxNights']}")


def _wrap_text(text, width=76):
    """Simple word wrap."""
    if not text:
        return []
    lines = []
    for paragraph in text.split('\n'):
        if not paragraph.strip():
            lines.append('')
            continue
        words = paragraph.split()
        current = ''
        for word in words:
            if current and len(current) + len(word) + 1 > width:
                lines.append(current)
                current = word
            else:
                current = f"{current} {word}" if current else word
        if current:
            lines.append(current)
    return lines


# ─── listings update ─────────────────────────────────────────────────────────

def run_update_descriptions(args):
    """Update listing fields including public description sub-fields."""
    db = get_db()
    listing_id, nickname = _resolve_listing(db, args.listing_id)

    if not listing_id:
        print(red(f"Listing '{args.listing_id}' not found"))
        return

    # Get current raw data for diff
    raw = _get_raw_data(db, listing_id)
    current_pub = raw.get('publicDescription', {}) or {}

    # If --from-file, read description from file
    file_desc = None
    if args.from_file:
        try:
            with open(args.from_file, 'r') as f:
                file_desc = f.read().strip()
        except Exception as e:
            print(red(f"Error reading file: {e}"))
            return

    # Build update payload
    payload = {}
    pub_updates = {}
    changes = []  # (field_path, old_val, new_val)

    # Title (top-level field)
    if args.title is not None:
        old = raw.get('title', '')
        payload['title'] = args.title
        changes.append(('title', old, args.title))

    # Description fields -> publicDescription sub-object
    desc_mapping = {
        'description': 'summary',
        'space': 'space',
        'access': 'access',
        'neighborhood': 'neighborhood',
        'transit': 'transit',
        'notes': 'notes',
        'interaction': 'interactionWithGuests',
        'house_rules': 'houseRules',
    }

    for arg_name, api_key in desc_mapping.items():
        val = getattr(args, arg_name, None)
        # --from-file overrides --description
        if arg_name == 'description' and file_desc is not None:
            val = file_desc
        if val is not None:
            old = current_pub.get(api_key, '')
            pub_updates[api_key] = val
            changes.append((f'publicDescription.{api_key}', old, val))

    if pub_updates:
        payload['publicDescription'] = pub_updates

    # Amenities
    add_amenities = getattr(args, 'add_amenities', None) or []
    remove_amenities = getattr(args, 'remove_amenities', None) or []
    if add_amenities or remove_amenities:
        current_amenities = list(raw.get('amenities', []))
        new_amenities = list(current_amenities)
        added = []
        removed = []
        for a in add_amenities:
            if a not in new_amenities:
                new_amenities.append(a)
                added.append(a)
        for a in remove_amenities:
            if a in new_amenities:
                new_amenities.remove(a)
                removed.append(a)
        if added or removed:
            payload['amenities'] = sorted(new_amenities)
            if added:
                changes.append(('amenities (added)', '', ', '.join(added)))
            if removed:
                changes.append(('amenities (removed)', ', '.join(removed), ''))

    if not changes:
        print(yellow("No changes specified. Use --title, --description, --space, --add-amenity, --remove-amenity, etc."))
        print(yellow("Run 'guesty listings update --help' for all options."))
        return

    # Print diff
    print(bold(f"Update: {nickname or listing_id}"))
    print()
    for field, old_val, new_val in changes:
        old_preview = _truncate(old_val, 80) if old_val else '(empty)'
        new_preview = _truncate(new_val, 80)
        print(f"  {cyan(field)}:")
        print(f"    {red('- ' + old_preview)}")
        print(f"    {green('+ ' + new_preview)}")
        print()

    if not args.confirm:
        print(yellow("[DRY RUN] Add --confirm to send this update to the API."))
        return

    # Send update
    config = load_config()
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return

    client = GuestyClient(config)
    try:
        result = client.api_put(f'/v1/listings/{listing_id}', payload)
        print(green(f"✓ Listing '{nickname}' updated successfully!"))
    except Exception as e:
        print(red(f"Error updating listing: {e}"))


def _truncate(text, max_len=80):
    """Truncate text for display."""
    if not text:
        return ''
    text = str(text).replace('\n', ' ')
    if len(text) > max_len:
        return text[:max_len] + '...'
    return text


# ─── listings amenities overview ──────────────────────────────────────────────

def run_amenities_overview(args):
    """Show all amenities across all listings with counts."""
    db = get_db()
    rows = db.execute("SELECT nickname, raw_data FROM listings WHERE raw_data IS NOT NULL ORDER BY nickname").fetchall()

    amenity_counts = {}  # amenity -> list of nicknames
    for row in rows:
        raw = json.loads(row['raw_data'])
        for a in raw.get('amenities', []):
            amenity_counts.setdefault(a, []).append(row['nickname'])

    total_listings = len(rows)

    if getattr(args, 'json', False):
        print_json({a: {'count': len(listings), 'listings': listings} for a, listings in sorted(amenity_counts.items())})
        return

    print(bold(f"Amenities Across All Listings ({len(amenity_counts)} unique, {total_listings} properties)\n"))

    # Sort by count descending, then name
    sorted_amenities = sorted(amenity_counts.items(), key=lambda x: (-len(x[1]), x[0]))

    for amenity, listings in sorted_amenities:
        count = len(listings)
        bar = '█' * count + '░' * (total_listings - count)
        pct = int(count / total_listings * 100)
        print(f"  {amenity:<45s} {bar} {count}/{total_listings} ({pct}%)")

    print(f"\n  {cyan('Tip:')} Use 'guesty listings show <name> --section amenities' to see a property's amenities")
    print(f"  {cyan('Tip:')} Use 'guesty listings update <name> --add-amenity \"X\" --confirm' to add amenities")


# ─── listings descriptions ───────────────────────────────────────────────────

def run_descriptions(args):
    """Show all listings with their description summaries."""
    db = get_db()
    cursor = db.execute("SELECT id, nickname, title, raw_data FROM listings ORDER BY nickname")
    rows = cursor.fetchall()

    if not rows:
        print(yellow("No listings found"))
        return

    if getattr(args, 'json', False):
        results = []
        for row in rows:
            raw = json.loads(row['raw_data']) if row['raw_data'] else {}
            pub = raw.get('publicDescription', {}) or {}
            results.append({
                'id': row['id'],
                'nickname': row['nickname'],
                'title': row['title'],
                'summary': pub.get('summary', ''),
            })
        print_json(results)
        return

    print(f"\n{bold('Listing Descriptions')}")
    print()

    for row in rows:
        raw = json.loads(row['raw_data']) if row['raw_data'] else {}
        pub = raw.get('publicDescription', {}) or {}
        summary = pub.get('summary', '')

        nick = row['nickname'] or 'N/A'
        if summary:
            preview = summary[:100]
            if len(summary) > 100:
                preview += '...'
            status = green('✓')
        else:
            preview = '(no description)'
            status = red('✗')

        print(f"  {status} {bold(nick)}")
        print(f"    {preview}")
        print()


# ─── listing get (singular, legacy) ─────────────────────────────────────────

def run_get(args):
    """Get details for a specific listing."""
    config = load_config()
    listing_id = args.id_or_nickname

    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        try:
            listing = client.api_get(f'/v1/listings/{listing_id}')
        except:
            try:
                all_listings = client.api_get_all('/v1/listings', {})
                for l in all_listings:
                    if l.get('nickname') == listing_id:
                        listing = l
                        listing_id = l.get('_id')
                        break
                else:
                    print(red(f"Listing '{args.id_or_nickname}' not found"))
                    return
            except Exception as e:
                print(red(f"Error: {e}"))
                return

        upcoming_reservations = []
        recent_reviews = []
        revenue = {'total': 0}
    else:
        db = get_db()
        try:
            cursor = db.execute("SELECT * FROM listings WHERE id = ?", (listing_id,))
            row = cursor.fetchone()

            if not row:
                cursor = db.execute("SELECT * FROM listings WHERE nickname = ?", (listing_id,))
                row = cursor.fetchone()

            if not row:
                cursor = db.execute("SELECT * FROM listings WHERE nickname LIKE ?", (f'%{listing_id}%',))
                row = cursor.fetchone()

            if not row:
                print(red(f"Listing '{args.id_or_nickname}' not found"))
                return

            listing = dict(row)
            listing_id = listing.get('id')

            from datetime import datetime
            today = datetime.now().strftime('%Y-%m-%d')
            cursor = db.execute(
                """SELECT r.*,
                          g.fullName as guest_fullName,
                          g.firstName as guest_firstName,
                          g.lastName as guest_lastName
                   FROM reservations r
                   LEFT JOIN guests g ON r.guestId = g.id
                   WHERE r.listingId = ? AND r.checkIn >= ? AND r.status = 'confirmed'
                   ORDER BY r.checkIn LIMIT 5""",
                (listing_id, today)
            )
            upcoming_reservations = [dict(r) for r in cursor.fetchall()]

            cursor = db.execute(
                "SELECT * FROM reviews WHERE listingId = ? ORDER BY createdAt DESC LIMIT 5",
                (listing_id,)
            )
            recent_reviews = [dict(r) for r in cursor.fetchall()]

            cursor = db.execute(
                """SELECT SUM(f.amount) as total
                   FROM financials f
                   JOIN reservations r ON f.reservationId = r.id
                   WHERE r.listingId = ? AND f.lineType = 'income'""",
                (listing_id,)
            )
            row = cursor.fetchone()
            revenue = {'total': row[0] or 0}

        except Exception as e:
            print(red(f"Error: {e}"))
            return

    if args.json:
        result = {
            'listing': listing,
            'upcoming_reservations': upcoming_reservations,
            'recent_reviews': recent_reviews,
            'revenue': revenue
        }
        print_json(result)
        return

    card_data = {
        'ID': listing.get('id'),
        'Nickname': listing.get('nickname'),
        'Title': listing.get('title'),
        'Description': listing.get('description', 'N/A')[:200] + '...' if listing.get('description') else 'N/A',
        'Type': listing.get('propertyType', 'N/A'),
        'Address': listing.get('address', 'N/A') or 'N/A',
        'City': listing.get('city', 'N/A'),
        'Country': listing.get('country', 'N/A'),
        'Bedrooms': listing.get('bedrooms', 'N/A'),
        'Bathrooms': listing.get('bathrooms', 'N/A'),
        'Max Guests': listing.get('max_guests') or listing.get('maxGuests', 'N/A'),
        'Status': green('Active') if listing.get('active') else red('Inactive'),
        'Created': listing.get('createdAt', 'N/A'),
    }

    print_card(f"Listing: {listing.get('nickname', 'Unknown')}", card_data)

    if upcoming_reservations:
        print()
        print(bold("Upcoming Reservations"))
        headers = ['Code', 'Guest', 'Check-in', 'Check-out', 'Nights']
        rows = []
        for r in upcoming_reservations:
            guest_name = r.get('guest_fullName')
            if not guest_name:
                first = r.get('guest_firstName', '')
                last = r.get('guest_lastName', '')
                guest_name = f"{first} {last}".strip()
            if not guest_name:
                guest_name = r.get('guestName', 'N/A')

            nights = r.get('nightsCount', r.get('nights'))
            if not nights and r.get('checkIn') and r.get('checkOut'):
                try:
                    from datetime import datetime
                    checkin = datetime.strptime(r['checkIn'][:10], '%Y-%m-%d')
                    checkout = datetime.strptime(r['checkOut'][:10], '%Y-%m-%d')
                    nights = (checkout - checkin).days
                except:
                    nights = 'N/A'

            rows.append([
                r.get('confirmationCode', 'N/A'),
                guest_name or 'N/A',
                r.get('checkIn', 'N/A')[:10] if r.get('checkIn') else 'N/A',
                r.get('checkOut', 'N/A')[:10] if r.get('checkOut') else 'N/A',
                nights if nights else 'N/A',
            ])
        print_table(headers, rows)

    if recent_reviews:
        print()
        print(bold("Recent Reviews"))
        headers = ['Reviewer', 'Rating', 'Platform', 'Date']
        rows = []
        for r in recent_reviews:
            rating = r.get('rating', 0) or 0
            if not rating and r.get('raw_json') or r.get('raw_data'):
                try:
                    raw = json.loads(r['raw_json'])
                    raw_review = raw.get('rawReview', {})
                    if raw_review:
                        rating = raw_review.get('overall_rating', 0)
                except:
                    pass
            stars = '★' * int(rating) + '☆' * (5 - int(rating))

            reviewer_name = r.get('reviewerName')
            if not reviewer_name and r.get('raw_json') or r.get('raw_data'):
                try:
                    raw = json.loads(r['raw_json'])
                    raw_review = raw.get('rawReview', {})
                    if raw_review:
                        reviewer_name = raw_review.get('guest_name')
                    if not reviewer_name:
                        guest = raw.get('guest', {})
                        if guest:
                            reviewer_name = guest.get('fullName')
                except:
                    pass

            rows.append([
                reviewer_name or 'Anonymous',
                f"{stars} ({rating})",
                r.get('platform', 'N/A'),
                r.get('createdAt', 'N/A')[:10] if r.get('createdAt') else 'N/A',
            ])
        print_table(headers, rows)

    print()
    print(bold("Revenue Summary"))
    print(f"  Total Income: {format_money(revenue['total'])}")


def run_create(args):
    """Create a new listing."""
    config = load_config()

    if args.live and not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return

    data = {}

    if args.title:
        data['title'] = args.title
    if args.nickname:
        data['nickname'] = args.nickname
    if args.address:
        data['address'] = args.address
    if args.city:
        data['city'] = args.city
    if args.state:
        data['state'] = args.state
    if args.country:
        data['country'] = args.country
    if args.bedrooms is not None:
        data['bedrooms'] = args.bedrooms
    if args.bathrooms is not None:
        data['bathrooms'] = args.bathrooms
    if args.max_guests is not None:
        data['maxGuests'] = args.max_guests
    if args.type:
        data['propertyType'] = args.type

    if args.dry_run:
        print(cyan("[DRY RUN] Would create listing with:"))
        print(json.dumps(data, indent=2))
        return

    if args.live:
        client = GuestyClient(config)
        try:
            result = client.api_post('listings', data)
            print(green(f"✓ Listing created successfully!"))
            print(f"  ID: {result.get('_id', result.get('id', 'N/A'))}")
            print(f"  Title: {result.get('title', 'N/A')}")
            if result.get('nickname'):
                print(f"  Nickname: {result['nickname']}")
        except Exception as e:
            print(red(f"Error creating listing: {e}"))
    else:
        print(yellow("Use --live to actually create the listing via API"))
        print(cyan("Would create listing with:"))
        print(json.dumps(data, indent=2))


def run_update_legacy(args):
    """Update an existing listing (legacy singular command)."""
    config = load_config()
    db = get_db()

    listing_id, nickname = _resolve_listing(db, args.id_or_nickname)
    if not listing_id:
        print(red(f"Listing '{args.id_or_nickname}' not found in local database"))
        return

    cursor = db.execute("SELECT * FROM listings WHERE id = ?", (listing_id,))
    current = dict(cursor.fetchone())

    updates = {}
    if args.title is not None and args.title != current.get('title'):
        updates['title'] = args.title
    if args.nickname is not None and args.nickname != current.get('nickname'):
        updates['nickname'] = args.nickname
    if args.address is not None and args.address != current.get('address'):
        updates['address'] = args.address
    if args.city is not None and args.city != current.get('city'):
        updates['city'] = args.city
    if args.state is not None and args.state != current.get('state'):
        updates['state'] = args.state
    if args.country is not None and args.country != current.get('country'):
        updates['country'] = args.country
    if args.bedrooms is not None and args.bedrooms != current.get('bedrooms'):
        updates['bedrooms'] = args.bedrooms
    if args.bathrooms is not None and args.bathrooms != current.get('bathrooms'):
        updates['bathrooms'] = args.bathrooms
    if args.max_guests is not None and args.max_guests != current.get('maxGuests'):
        updates['maxGuests'] = args.max_guests
    if args.type is not None and args.type != current.get('propertyType'):
        updates['propertyType'] = args.type

    if not updates:
        print(yellow("No changes to apply"))
        return

    if args.dry_run:
        print(cyan("[DRY RUN] Would update listing with:"))
        print(bold("Changes:"))
        for key, value in updates.items():
            old_val = current.get(key, 'N/A')
            print(f"  {key}: {red(old_val)} → {green(value)}")
        return

    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        try:
            result = client.api_put(f'listings/{listing_id}', updates)
            print(green(f"✓ Listing updated successfully!"))
            print(f"  ID: {listing_id}")
            print(f"  Nickname: {nickname}")
            print(bold("Changes applied:"))
            for key, value in updates.items():
                print(f"  {key}: {value}")
        except Exception as e:
            print(red(f"Error updating listing: {e}"))
    else:
        print(yellow("Use --live to actually update the listing via API"))
        print(cyan("Would update listing with:"))
        print(bold("Changes:"))
        for key, value in updates.items():
            old_val = current.get(key, 'N/A')
            print(f"  {key}: {red(old_val)} → {green(value)}")


def run_delete(args):
    """Delete a listing."""
    config = load_config()
    db = get_db()

    listing_id, nickname = _resolve_listing(db, args.id_or_nickname)
    if not listing_id:
        print(red(f"Listing '{args.id_or_nickname}' not found in local database"))
        return

    cursor = db.execute("SELECT * FROM listings WHERE id = ?", (listing_id,))
    listing = dict(cursor.fetchone())

    print(bold("Listing to delete:"))
    print(f"  ID: {listing_id}")
    print(f"  Nickname: {listing.get('nickname', 'N/A')}")
    print(f"  Title: {listing.get('title', 'N/A')}")
    print(f"  Address: {listing.get('address', 'N/A')}, {listing.get('city', 'N/A')}")

    if not args.confirm:
        print()
        print(red("WARNING: This action cannot be undone!"))
        print(yellow("Use --confirm to delete this listing"))
        return

    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        try:
            client.api_delete(f'listings/{listing_id}')
            print(green(f"✓ Listing '{nickname}' deleted successfully"))
        except Exception as e:
            print(red(f"Error deleting listing: {e}"))
    else:
        print(yellow("Use --live to actually delete the listing via API"))
        print(cyan("[DRY RUN] Listing would be deleted"))
