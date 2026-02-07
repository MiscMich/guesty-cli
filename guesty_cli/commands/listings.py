"""
Listings management commands for guesty-cli.
"""
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


def register(subparsers):
    """Register listings commands with the argument parser."""
    # guesty listings (list)
    list_parser = subparsers.add_parser(
        'listings',
        help='List all listings'
    )
    list_parser.set_defaults(func=run_list)
    list_parser.add_argument('--active', action='store_true', help='Show only active listings')
    list_parser.add_argument('--city', type=str, help='Filter by city')
    list_parser.add_argument('--status', type=str, help='Filter by status')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    list_parser.add_argument('--csv', action='store_true', help='Output as CSV')
    list_parser.add_argument('--live', action='store_true', help='Query live API')

    # guesty listing (with subcommands)
    listing_parser = subparsers.add_parser(
        'listing',
        help='Manage a specific listing'
    )
    listing_subparsers = listing_parser.add_subparsers(dest='listing_action')

    # guesty listing get <id_or_nickname>
    get_parser = listing_subparsers.add_parser('get', help='Show details for a specific listing')
    get_parser.add_argument('id_or_nickname', help='Listing ID or nickname')
    get_parser.add_argument('--json', action='store_true', help='Output as JSON')
    get_parser.add_argument('--live', action='store_true', help='Query live API')
    get_parser.set_defaults(func=run_get)

    # guesty listing create
    create_parser = listing_subparsers.add_parser('create', help='Create a new listing')
    create_parser.add_argument('--title', type=str, required=True, help='Listing title (required)')
    create_parser.add_argument('--nickname', type=str, help='Listing nickname')
    create_parser.add_argument('--address', type=str, help='Street address')
    create_parser.add_argument('--city', type=str, help='City')
    create_parser.add_argument('--state', type=str, help='State/Province')
    create_parser.add_argument('--country', type=str, default='US', help='Country code (default: US)')
    create_parser.add_argument('--bedrooms', type=int, help='Number of bedrooms')
    create_parser.add_argument('--bathrooms', type=float, help='Number of bathrooms')
    create_parser.add_argument('--max-guests', type=int, help='Maximum number of guests')
    create_parser.add_argument('--type', type=str, help='Property type (e.g., Villa, Apartment)')
    create_parser.add_argument('--dry-run', action='store_true', help='Show what would be sent without sending')
    create_parser.add_argument('--live', action='store_true', help='Create via live API')
    create_parser.set_defaults(func=run_create)

    # guesty listing update <id_or_nickname>
    update_parser = listing_subparsers.add_parser('update', help='Update an existing listing')
    update_parser.add_argument('id_or_nickname', help='Listing ID or nickname')
    update_parser.add_argument('--title', type=str, help='Listing title')
    update_parser.add_argument('--nickname', type=str, help='Listing nickname')
    update_parser.add_argument('--address', type=str, help='Street address')
    update_parser.add_argument('--city', type=str, help='City')
    update_parser.add_argument('--state', type=str, help='State/Province')
    update_parser.add_argument('--country', type=str, help='Country code')
    update_parser.add_argument('--bedrooms', type=int, help='Number of bedrooms')
    update_parser.add_argument('--bathrooms', type=float, help='Number of bathrooms')
    update_parser.add_argument('--max-guests', type=int, help='Maximum number of guests')
    update_parser.add_argument('--type', type=str, help='Property type')
    update_parser.add_argument('--dry-run', action='store_true', help='Show what would be sent without sending')
    update_parser.add_argument('--live', action='store_true', help='Update via live API')
    update_parser.set_defaults(func=run_update)

    # guesty listing delete <id_or_nickname>
    delete_parser = listing_subparsers.add_parser('delete', help='Delete a listing')
    delete_parser.add_argument('id_or_nickname', help='Listing ID or nickname')
    delete_parser.add_argument('--confirm', action='store_true', help='Confirm deletion (required)')
    delete_parser.add_argument('--live', action='store_true', help='Delete via live API')
    delete_parser.set_defaults(func=run_delete)


def run(args):
    """Route to appropriate subcommand handler."""
    pass  # Handled by subparsers


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
    
    # Format for output
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
            l.get('maxGuests', 'N/A'),
            green('Active') if l.get('active') else red('Inactive')
        ])
    
    if args.json:
        print_json(listings)
    elif args.csv:
        print_csv(headers, rows)
    else:
        print(f"\n{bold('Listings')}")
        print_table(headers, rows)


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
            # Try as ID first
            listing = client.api_get(f'/v1/listings/{listing_id}')
        except:
            # Try to find by nickname
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
        
        # Get related data from API
        upcoming_reservations = []
        recent_reviews = []
        revenue = {'total': 0}
    else:
        db = get_db()
        try:
            # Try as ID first
            cursor = db.execute("SELECT * FROM listings WHERE id = ?", (listing_id,))
            row = cursor.fetchone()
            
            if not row:
                # Try by nickname (exact match first, then partial)
                cursor = db.execute("SELECT * FROM listings WHERE nickname = ?", (listing_id,))
                row = cursor.fetchone()
            
            if not row:
                # Try partial nickname match
                cursor = db.execute("SELECT * FROM listings WHERE nickname LIKE ?", (f'%{listing_id}%',))
                row = cursor.fetchone()
            
            if not row:
                print(red(f"Listing '{args.id_or_nickname}' not found"))
                return
            
            listing = dict(row)
            listing_id = listing.get('id')
            
            # Get upcoming reservations with guest names
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
            
            # Get recent reviews
            cursor = db.execute(
                "SELECT * FROM reviews WHERE listingId = ? ORDER BY createdAt DESC LIMIT 5",
                (listing_id,)
            )
            recent_reviews = [dict(r) for r in cursor.fetchall()]
            
            # Get revenue summary - need to join with reservations since financials uses reservationId
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
    
    # Print detail card
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
        'Max Guests': listing.get('maxGuests', 'N/A'),
        'Status': green('Active') if listing.get('active') else red('Inactive'),
        'Created': listing.get('createdAt', 'N/A'),
    }
    
    print_card(f"Listing: {listing.get('nickname', 'Unknown')}", card_data)
    
    # Upcoming reservations
    if upcoming_reservations:
        print()
        print(bold("Upcoming Reservations"))
        headers = ['Code', 'Guest', 'Check-in', 'Check-out', 'Nights']
        rows = []
        for r in upcoming_reservations:
            # Get guest name from joined columns
            guest_name = r.get('guest_fullName')
            if not guest_name:
                first = r.get('guest_firstName', '')
                last = r.get('guest_lastName', '')
                guest_name = f"{first} {last}".strip()
            if not guest_name:
                guest_name = r.get('guestName', 'N/A')
            
            # Calculate nights if not provided
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
    
    # Recent reviews
    if recent_reviews:
        print()
        print(bold("Recent Reviews"))
        headers = ['Reviewer', 'Rating', 'Platform', 'Date']
        rows = []
        for r in recent_reviews:
            import json
            rating = r.get('rating', 0) or 0
            # Try to get rating from raw_json if direct column is 0
            if not rating and r.get('raw_json'):
                try:
                    raw = json.loads(r['raw_json'])
                    raw_review = raw.get('rawReview', {})
                    if raw_review:
                        rating = raw_review.get('overall_rating', 0)
                except:
                    pass
            stars = '★' * int(rating) + '☆' * (5 - int(rating))
            
            # Try to get reviewer name from raw_json
            reviewer_name = r.get('reviewerName')
            if not reviewer_name and r.get('raw_json'):
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
    
    # Revenue summary
    print()
    print(bold("Revenue Summary"))
    print(f"  Total Income: {format_money(revenue['total'])}")


def run_create(args):
    """Create a new listing."""
    config = load_config()

    if args.live and not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return

    # Build the data payload
    data = {
        'title': args.title,
    }

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


def run_update(args):
    """Update an existing listing."""
    config = load_config()
    db = get_db()

    # Resolve listing ID
    listing_id, nickname = _resolve_listing(db, args.id_or_nickname)
    if not listing_id:
        print(red(f"Listing '{args.id_or_nickname}' not found in local database"))
        return

    # Get current listing data
    cursor = db.execute("SELECT * FROM listings WHERE id = ?", (listing_id,))
    current = dict(cursor.fetchone())

    # Build update payload with only changed fields
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

    # Resolve listing ID
    listing_id, nickname = _resolve_listing(db, args.id_or_nickname)
    if not listing_id:
        print(red(f"Listing '{args.id_or_nickname}' not found in local database"))
        return

    # Get listing details for confirmation
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
