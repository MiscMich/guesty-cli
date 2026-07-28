"""Owners management commands for guesty-cli."""
import json
from guesty_cli.core.config import load_config
from guesty_cli.core.database import get_db
from guesty_cli.core.client import GuestyClient
from guesty_cli.core.output import (
    print_table, print_card, print_json, print_csv,
    bold, cyan, green, red, yellow, dim, format_money
)
from guesty_cli.utils.resolve import resolve_owner, resolve_listing
from guesty_cli.commands.statements import register_owner_statement


def register(subparsers):
    """Register owners commands with the argument parser."""
    # guesty owners (list)
    list_parser = subparsers.add_parser(
        'owners',
        help='List all owners'
    )
    list_parser.set_defaults(func=run_list)
    list_parser.add_argument('--active', action='store_true', help='Show only active owners')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    list_parser.add_argument('--csv', action='store_true', help='Output as CSV')
    list_parser.add_argument('--live', action='store_true', help='Query live API')
    
    # guesty owner (single owner operations)
    owner_parser = subparsers.add_parser(
        'owner',
        help='Manage owners'
    )
    owner_subparsers = owner_parser.add_subparsers(dest='owner_action')
    
    # Get owner details
    get_parser = owner_subparsers.add_parser('get', help='Show details for a specific owner')
    get_parser.add_argument('id_or_name', help='Owner ID or name')
    get_parser.add_argument('--json', action='store_true', help='Output as JSON')
    get_parser.add_argument('--live', action='store_true', help='Query live API')
    get_parser.set_defaults(func=run_get)
    
    # Create owner
    create_parser = owner_subparsers.add_parser('create', help='Create a new owner')
    create_parser.add_argument('--name', required=True, help='Owner full name')
    create_parser.add_argument('--email', help='Owner email address')
    create_parser.add_argument('--phone', help='Owner phone number')
    create_parser.add_argument('--dry-run', action='store_true', help='Show what would be created without calling API')
    create_parser.set_defaults(func=run_create)
    
    # Update owner
    update_parser = owner_subparsers.add_parser('update', help='Update owner')
    update_parser.add_argument('id_or_name', help='Owner ID or name')
    update_parser.add_argument('--email', help='New email address')
    update_parser.add_argument('--phone', help='New phone number')
    update_parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without calling API')
    update_parser.set_defaults(func=run_update)
    
    # Delete owner
    delete_parser = owner_subparsers.add_parser('delete', help='Delete an owner')
    delete_parser.add_argument('id_or_name', help='Owner ID or name')
    delete_parser.add_argument('--confirm', action='store_true', required=True, help='Confirm deletion (required)')
    delete_parser.set_defaults(func=run_delete)

    # Owner reservations
    reservations_parser = owner_subparsers.add_parser('reservations', help='Show reservations for an owner')
    reservations_parser.add_argument('id_or_name', help='Owner ID or name')
    reservations_parser.add_argument('--from', dest='from_date', help='Start date (YYYY-MM-DD)')
    reservations_parser.add_argument('--to', dest='to_date', help='End date (YYYY-MM-DD)')
    reservations_parser.add_argument('--json', action='store_true', help='Output as JSON')
    reservations_parser.add_argument('--live', action='store_true', help='Query live API')
    reservations_parser.add_argument('--dry-run', action='store_true', help='Show what would be queried without calling API')
    reservations_parser.set_defaults(func=run_owner_reservations)

    # Owner statement - register from statements module
    register_owner_statement(owner_subparsers)

    # Default handler
    def default_handler(args):
        if hasattr(args, 'func') and args.func != default_handler:
            args.func(args)
        else:
            run_list(args)
    owner_parser.set_defaults(func=default_handler)


def run(args):
    """Route to appropriate subcommand handler."""
    pass


def run_list(args):
    """List all owners."""
    config = load_config()
    
    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        try:
            # Owners returns raw array
            owners = client.api_get('owners')
            if not isinstance(owners, list):
                owners = owners.get('results', [])
        except Exception as e:
            print(red(f"Error fetching owners: {e}"))
            return
    else:
        db = get_db()
        query = "SELECT * FROM owners WHERE 1=1"
        params = []
        
        if args.active:
            query += " AND active = 1"
        
        query += " ORDER BY full_name"
        
        try:
            cursor = db.execute(query, params)
            owners = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(red(f"Error querying database: {e}"))
            return
    
    if not owners:
        print(yellow("No owners found"))
        return
    
    # Format for output
    headers = ['Name', 'Email', 'Phone', 'Payout Method', 'Active']
    rows = []
    for o in owners:
        payout_method = 'N/A'
        pm = o.get('payoutMethod', {})
        if isinstance(pm, dict):
            payout_method = pm.get('type', 'N/A')
        elif isinstance(pm, str):
            payout_method = pm
        
        rows.append([
            o.get('full_name', 'N/A'),
            o.get('email', 'N/A'),
            o.get('phone', 'N/A') or 'N/A',
            payout_method,
            green('Yes') if o.get('isActive') else red('No'),
        ])
    
    if args.json:
        print_json(owners)
    elif args.csv:
        print_csv(headers, rows)
    else:
        print(f"\n{bold(f'Owners ({len(owners)} total)')}")
        print_table(headers, rows)


def run_get(args):
    """Get details for a specific owner."""
    config = load_config()
    
    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        try:
            owner = client.api_get(f'owners/{args.id_or_name}')
        except:
            # Try to find by name
            try:
                owners = client.api_get('owners')
                if not isinstance(owners, list):
                    owners = owners.get('results', [])
                for o in owners:
                    if o.get('full_name') == args.id_or_name or o.get('full_name') == args.id_or_name:
                        owner = o
                        break
                else:
                    print(red(f"Owner '{args.id_or_name}' not found"))
                    return
            except Exception as e:
                print(red(f"Error: {e}"))
                return
        properties = []
        reservations = []
    else:
        db = get_db()
        try:
            # Try as ID first
            owner = resolve_owner(db, args.id_or_name)
            
            if not owner:
                print(red(f"Owner '{args.id_or_name}' not found"))
                return
            
            # Get full owner details
            cursor = db.execute("SELECT * FROM owners WHERE id = ?", (owner['id'],))
            row = cursor.fetchone()
            owner = dict(row)
            owner_id = owner.get('id')
            
            # Get properties (listings owned by this owner). The owner -> listing
            # mapping is only available in the owner's raw payload; there is no
            # owner_listings join table.
            owned_ids = []
            try:
                owned_ids = json.loads(owner.get('raw_data') or '{}').get('listings') or []
            except (ValueError, AttributeError):
                owned_ids = []

            if owned_ids:
                placeholders = ','.join('?' * len(owned_ids))
                cursor = db.execute(
                    f"SELECT * FROM listings WHERE id IN ({placeholders})",
                    tuple(owned_ids)
                )
                properties = [dict(r) for r in cursor.fetchall()]
            else:
                properties = []
            
            # Get recent reservations for owner's properties
            listing_ids = [p.get('id') for p in properties]
            if listing_ids:
                placeholders = ','.join('?' * len(listing_ids))
                cursor = db.execute(
                    f"""SELECT * FROM reservations
                       WHERE listing_id IN ({placeholders})
                       ORDER BY check_in DESC LIMIT 10""",
                    tuple(listing_ids)
                )
                reservations = [dict(r) for r in cursor.fetchall()]
            else:
                reservations = []
            
        except Exception as e:
            print(red(f"Error: {e}"))
            return
    
    if args.json:
        result = {
            'owner': owner,
            'properties': properties,
            'recent_reservations': reservations
        }
        print_json(result)
        return
    
    # Print detail card
    payout_method = owner.get('payoutMethod', {})
    if isinstance(payout_method, dict):
        payout_info = f"{payout_method.get('type', 'N/A')}"
    else:
        payout_info = str(payout_method) if payout_method else 'N/A'
    
    card_data = {
        'ID': owner.get('id'),
        'Name': owner.get('full_name', 'N/A'),
        'Email': owner.get('email', 'N/A'),
        'Phone': owner.get('phone', 'N/A') or 'N/A',
        'Payout Method': payout_info,
        'Active': green('Yes') if owner.get('isActive') else red('No'),
        'Created': owner.get('createdAt', 'N/A'),
    }
    
    print_card(f"Owner: {card_data['Name']}", card_data)
    
    # Properties
    if properties:
        print()
        print(bold("Properties"))
        headers = ['Nickname', 'Title', 'City', 'Status']
        rows = []
        for p in properties:
            rows.append([
                p.get('nickname', 'N/A'),
                p.get('title', 'N/A')[:30],
                p.get('city', 'N/A'),
                green('Active') if p.get('active') else red('Inactive'),
            ])
        print_table(headers, rows)
    else:
        print()
        print(dim("No properties found"))
    
    # Recent reservations
    if reservations:
        print()
        print(bold("Recent Reservations"))
        headers = ['Code', 'Guest', 'Listing', 'Check-in', 'Status']
        rows = []
        for r in reservations:
            rows.append([
                r.get('confirmationCode', 'N/A'),
                r.get('guestName', 'N/A')[:20],
                r.get('listingId', 'N/A')[:20],
                r.get('checkIn', 'N/A')[:10] if r.get('checkIn') else 'N/A',
                r.get('status', 'N/A'),
            ])
        print_table(headers, rows)
    else:
        print()
        print(dim("No recent reservations"))


def run_create(args):
    """Create a new owner."""
    config = load_config()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    data = {
        'full_name': args.name,
    }
    
    if args.email:
        data['email'] = args.email
    if args.phone:
        data['phone'] = args.phone
    
    if args.dry_run:
        print(yellow("DRY RUN - Would create owner:"))
        print(f"  Name: {data['full_name']}")
        if 'email' in data:
            print(f"  Email: {data['email']}")
        if 'phone' in data:
            print(f"  Phone: {data['phone']}")
        return
    
    client = GuestyClient(config)
    
    try:
        result = client.api_post('owners', data)
        print(green(f"✓ Owner created"))
        print(f"  ID: {result.get('_id')}")
        print(f"  Name: {result.get('full_name')}")
        if result.get('email'):
            print(f"  Email: {result.get('email')}")
    except Exception as e:
        print(red(f"Error creating owner: {e}"))


def run_update(args):
    """Update an owner."""
    config = load_config()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    # Resolve owner
    db = get_db()
    owner = resolve_owner(db, args.id_or_name)
    if not owner:
        print(red(f"Error: Owner '{args.id_or_name}' not found"))
        print(yellow("Tip: Use 'guesty owners' to see available owners"))
        return
    
    data = {}
    
    if args.email:
        data['email'] = args.email
    if args.phone:
        data['phone'] = args.phone
    
    if not data:
        print(yellow("No changes specified"))
        return
    
    if args.dry_run:
        print(yellow(f"DRY RUN - Would update owner {owner['full_name']} ({owner['id']}):"))
        for key, value in data.items():
            print(f"  {key}: {value}")
        return
    
    client = GuestyClient(config)
    
    try:
        result = client.api_put(f'owners/{owner["id"]}', data)
        print(green(f"✓ Owner updated: {result.get('full_name')}"))
    except Exception as e:
        print(red(f"Error updating owner: {e}"))


def run_delete(args):
    """Delete an owner."""
    config = load_config()

    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return

    # Resolve owner
    db = get_db()
    owner = resolve_owner(db, args.id_or_name)
    if not owner:
        print(red(f"Error: Owner '{args.id_or_name}' not found"))
        return

    # Show owner details before deleting
    print(yellow("About to delete the following owner:"))
    print(f"  ID: {owner['id']}")
    print(f"  Name: {owner['full_name']}")
    print()

    client = GuestyClient(config)

    try:
        client.api_delete(f'owners/{owner["id"]}')
        print(green(f"✓ Owner '{owner['full_name']}' deleted"))
    except Exception as e:
        print(red(f"Error deleting owner: {e}"))


def run_owner_reservations(args):
    """Show reservations for a specific owner."""
    config = load_config()
    db = get_db()

    # Resolve owner
    owner = resolve_owner(db, args.id_or_name)
    if not owner:
        print(red(f"Error: Owner '{args.id_or_name}' not found"))
        print(yellow("Tip: Use 'guesty owners' to see available owners"))
        return

    owner_id = owner['id']
    owner_name = owner.get('full_name', 'Unknown')

    # Date range filtering
    date_filter_desc = ""
    if args.from_date:
        date_filter_desc += f" from {args.from_date}"
    if args.to_date:
        date_filter_desc += f" to {args.to_date}"

    if args.dry_run:
        print(yellow(f"DRY RUN - Would query reservations for owner: {owner_name} ({owner_id})"))
        if args.from_date:
            print(f"  Start date: {args.from_date}")
        if args.to_date:
            print(f"  End date: {args.to_date}")
        print(dim("\nAPI endpoint: GET /v1/owners/{id}/reservations"))
        return

    reservations = []
    listings_map = {}
    use_database = True

    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return

        client = GuestyClient(config)

        try:
            # Build query params for date filtering
            params = {}
            if args.from_date:
                params['checkInDateFrom'] = args.from_date
            if args.to_date:
                params['checkInDateTo'] = args.to_date

            # Call the API endpoint
            result = client.api_get(f'owners/{owner_id}/reservations', params=params if params else None)

            # Handle different response formats
            if isinstance(result, list):
                reservations = result
                use_database = False
            elif isinstance(result, dict):
                reservations = result.get('results', [])
                use_database = False
            else:
                reservations = []

        except Exception as e:
            print(yellow(f"Note: Live API endpoint not available ({e}). Falling back to local database..."))
            print(dim("Tip: Run 'guesty sync' to update local data.\n"))
            # Will fall through to database query

    # Query from local database if needed
    if use_database:
        try:
            cursor = db.execute("SELECT id, nickname, raw_json FROM listings")
            owner_listing_ids = []
            for row in cursor.fetchall():
                raw_json = row['raw_json']
                if raw_json:
                    import json
                    listing_data = json.loads(raw_json)
                    owners = listing_data.get('owners', [])
                    if owner_id in owners:
                        owner_listing_ids.append(row['id'])
                        listings_map[row['id']] = row['nickname']

            if not owner_listing_ids:
                print(yellow(f"No listings found for owner: {owner_name}"))
                return

            # Build query for reservations
            placeholders = ','.join('?' * len(owner_listing_ids))
            query = f"""
                SELECT r.*, l.nickname as listing_nickname
                FROM reservations r
                LEFT JOIN listings l ON r.listing_id = l.id
                WHERE r.listing_id IN ({placeholders})
            """
            params = list(owner_listing_ids)

            # Add date filtering
            if args.from_date:
                query += " AND r.check_in >= ?"
                params.append(args.from_date)
            if args.to_date:
                query += " AND r.check_out <= ?"
                params.append(args.to_date)

            query += " ORDER BY r.check_in DESC"

            cursor = db.execute(query, params)
            reservations = [dict(row) for row in cursor.fetchall()]

            # Build listings map for display
            for r in reservations:
                if r.get('listingId') and r['listingId'] not in listings_map:
                    listings_map[r['listingId']] = r.get('listing_nickname', 'Unknown')

        except Exception as e:
            print(red(f"Error querying database: {e}"))
            return

    if not reservations:
        print(yellow(f"No reservations found for owner: {owner_name}{date_filter_desc}"))
        return

    # Calculate total revenue
    total_revenue = 0.0
    currency = 'USD'

    for r in reservations:
        # Try to get revenue from different fields
        revenue = 0.0
        if r.get('payoutAmount'):
            revenue = float(r['payoutAmount'])
        elif r.get('totalPrice'):
            revenue = float(r['totalPrice'])
        elif isinstance(r.get('money'), dict):
            revenue = float(r['money'].get('fareAccommodation', 0))

        total_revenue += revenue

        # Get currency
        if r.get('currency'):
            currency = r['currency']

    if args.json:
        # Build comprehensive JSON output
        output = {
            'owner': {
                'id': owner_id,
                'name': owner_name
            },
            'date_range': {
                'from': args.from_date,
                'to': args.to_date
            },
            'summary': {
                'total_reservations': len(reservations),
                'total_revenue': round(total_revenue, 2),
                'currency': currency
            },
            'reservations': []
        }

        for r in reservations:
            rev = 0.0
            if r.get('payoutAmount'):
                rev = float(r['payoutAmount'])
            elif r.get('totalPrice'):
                rev = float(r['totalPrice'])

            res_data = {
                'confirmation_code': r.get('confirmationCode'),
                'property': listings_map.get(r.get('listingId'), r.get('listingId', 'Unknown')),
                'guest': r.get('guestName', 'N/A'),
                'check_in': r.get('checkIn'),
                'check_out': r.get('checkOut'),
                'revenue': round(rev, 2),
                'currency': r.get('currency', currency),
                'status': r.get('status')
            }
            output['reservations'].append(res_data)

        print_json(output)
        return

    # Print table output
    print(f"\n{bold(f'Reservations for {owner_name}')}")
    if date_filter_desc:
        print(dim(f"Date range:{date_filter_desc}"))
    print()

    headers = ['Confirmation Code', 'Property', 'Guest', 'Check-in', 'Check-out', 'Revenue']
    rows = []

    for r in reservations:
        # Get revenue
        rev = 0.0
        if r.get('payoutAmount'):
            rev = float(r['payoutAmount'])
        elif r.get('totalPrice'):
            rev = float(r['totalPrice'])

        # Get property name
        listing_id = r.get('listingId', '')
        property_name = listings_map.get(listing_id, listing_id[:20])

        # Format dates
        check_in = r.get('checkIn', '')
        check_out = r.get('checkOut', '')
        if check_in:
            check_in = check_in[:10]  # Just the date part
        if check_out:
            check_out = check_out[:10]

        rows.append([
            r.get('confirmationCode', 'N/A'),
            property_name[:25],
            r.get('guestName', 'N/A')[:20],
            check_in or 'N/A',
            check_out or 'N/A',
            format_money(rev, r.get('currency', currency))
        ])

    print_table(headers, rows)

    # Print summary
    print()
    print(f"{bold('Summary:')}")
    print(f"  Total Reservations: {len(reservations)}")
    print(f"  Total Revenue: {green(format_money(total_revenue, currency))}")
