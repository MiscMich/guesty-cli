"""
Reservations management commands for guesty-cli.
"""
import argparse
import json
from datetime import datetime, timedelta
from guesty_cli.core.config import load_config
from guesty_cli.core.database import get_db
from guesty_cli.core.client import GuestyClient
from guesty_cli.core.output import (
    print_table, print_card, print_json, print_csv,
    bold, cyan, green, red, yellow, dim, format_money, format_date
)
from guesty_cli.utils.dates import parse_date
from guesty_cli.utils.filters import (
    parse_filter_string, build_filters_dict, today_checkins,
    today_checkouts, unpaid_reservations, get_valid_fields
)


def clean_date(iso_str):
    """Format ISO date string to clean YYYY-MM-DD format."""
    if not iso_str:
        return 'N/A'
    return iso_str[:10]  # Just YYYY-MM-DD


def format_source(source_str):
    """Map API source values to friendly names."""
    if not source_str:
        return 'N/A'
    source_map = {
        'airbnb2': 'Airbnb',
        'homeaway2': 'VRBO',
        'bookingcom': 'Booking',
        'BE-API': 'Direct',
        'manual': 'Manual',
    }
    return source_map.get(source_str, source_str)


def _get_guest_name(row):
    """Extract guest name from row, using direct column or joining from guests table."""
    # First try direct guestName column
    guest_name = row.get('guestName')
    if guest_name:
        return guest_name

    # Try joined guest columns
    guest_name = row.get('guest_fullName')
    if guest_name:
        return guest_name

    first_name = row.get('guest_firstName', '')
    last_name = row.get('guest_lastName', '')
    if first_name or last_name:
        return f"{first_name} {last_name}".strip()

    # Try parsing from raw_json
    raw_json = row.get('raw_json')
    if raw_json:
        try:
            raw = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
            # Try guestInfo
            guest_info = raw.get('guestInfo', {})
            if guest_info:
                full_name = guest_info.get('fullName')
                if full_name:
                    return full_name
                first = guest_info.get('firstName', '')
                last = guest_info.get('lastName', '')
                if first or last:
                    return f"{first} {last}".strip()
            # Try guest nested object (common in Guesty API)
            guest = raw.get('guest', {})
            if guest:
                full_name = guest.get('fullName')
                if full_name:
                    return full_name
                first = guest.get('firstName', '')
                last = guest.get('lastName', '')
                if first or last:
                    return f"{first} {last}".strip()
        except (json.JSONDecodeError, AttributeError):
            pass

    return 'N/A'


def _get_price_from_row(row, price_field='totalPrice'):
    """Extract price from row, using direct column, calculated from financials, or parsing from raw_json."""
    # First try direct column
    price = row.get(price_field, 0)
    if price:
        return float(price)

    # Try calculated price from financials subquery
    calculated = row.get('calculated_price') or row.get('total_financials')
    if calculated:
        return float(calculated)

    # Try payoutAmount if looking for totalPrice and it's 0
    if price_field == 'totalPrice':
        price = row.get('payoutAmount', 0)
        if price:
            return float(price)

    # Parse from raw_json
    raw_json = row.get('raw_json')
    if raw_json:
        try:
            raw = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
            money = raw.get('money', {})

            if price_field == 'payoutAmount' or price_field == 'hostPayout':
                host_payout = money.get('hostPayout')
                if host_payout:
                    return float(host_payout)

            # Try various price fields
            total_paid = money.get('totalPaid')
            if total_paid:
                return float(total_paid)

            fare = money.get('fare', {})
            if fare:
                total = fare.get('total')
                if total:
                    return float(total)
        except (json.JSONDecodeError, AttributeError, ValueError):
            pass

    return 0


def _get_balance_due_from_row(row):
    """Extract balance due from row data."""
    # Try direct column
    balance = row.get('balanceDue')
    if balance is not None:
        return float(balance)

    # Try to calculate from raw_json
    raw_json = row.get('raw_json')
    if raw_json:
        try:
            raw = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
            money = raw.get('money', {})
            balance = money.get('balanceDue')
            if balance is not None:
                return float(balance)
            # Calculate: total - paid
            fare = money.get('fare', {})
            total = fare.get('total', 0) if fare else 0
            total_paid = money.get('totalPaid', 0)
            if total:
                return float(total) - float(total_paid)
        except (json.JSONDecodeError, AttributeError, ValueError):
            pass

    return 0


def _get_status_from_row(row):
    """Extract status from row, using direct column or parsing from raw_json."""
    status = row.get('status')
    if status:
        return status

    raw_json = row.get('raw_json')
    if raw_json:
        try:
            raw = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
            status = raw.get('status')
            if status:
                return status
        except (json.JSONDecodeError, AttributeError):
            pass

    return 'N/A'


def _get_source_from_row(row):
    """Extract source from row, using direct column or parsing from raw_json."""
    source = row.get('source')
    if source:
        return source

    raw_json = row.get('raw_json')
    if raw_json:
        try:
            raw = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
            source = raw.get('source')
            if source:
                return source
            # Try integration.platform
            integration = raw.get('integration', {})
            if integration:
                platform = integration.get('platform')
                if platform:
                    return platform
        except (json.JSONDecodeError, AttributeError):
            pass

    return 'N/A'


def _resolve_reservation(db, identifier):
    """Resolve a confirmation code or ID to its actual ID."""
    row = db.execute("SELECT id, confirmation_code FROM reservations WHERE id = ? OR confirmation_code = ?", (identifier, identifier)).fetchone()
    if row:
        return row['id'], row['confirmation_code']
    return None, None


KNOWN_RESERVATION_ACTIONS = {'get', 'create', 'update', 'cancel', 'approve', 'decline'}


def register(subparsers):
    """Register reservations commands with the argument parser."""
    # guesty reservations (list)
    list_parser = subparsers.add_parser(
        'reservations',
        help='List reservations'
    )
    list_parser.set_defaults(func=run_list)
    list_parser.add_argument('--status', type=str, help='Filter by status')
    list_parser.add_argument('--listing', type=str, help='Filter by listing ID')
    list_parser.add_argument('--from', dest='from_date', type=str, help='Check-in from date (YYYY-MM-DD)')
    list_parser.add_argument('--to', dest='to_date', type=str, help='Check-in to date (YYYY-MM-DD)')
    list_parser.add_argument('--source', type=str, help='Filter by source/channel')
    list_parser.add_argument('--today', action='store_true', help='Show today\'s check-ins')
    list_parser.add_argument('--upcoming', action='store_true', help='Show upcoming next 7 days')
    list_parser.add_argument('--guest', type=str, help='Filter by guest name/email')
    list_parser.add_argument('--limit', type=int, default=20, help='Limit results (default: 20)')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    list_parser.add_argument('--csv', action='store_true', help='Output as CSV')
    list_parser.add_argument('--live', action='store_true', help='Query live API')

    # Enhanced filter system
    list_parser.add_argument('--filter', type=str, help='Advanced filter expression (e.g., "status=confirmed,balanceDue>0")')
    list_parser.add_argument('--checkin-today', action='store_true', help='Show reservations checking in today')
    list_parser.add_argument('--checkout-today', action='store_true', help='Show reservations checking out today')
    list_parser.add_argument('--unpaid', action='store_true', help='Show reservations with balance due > 0')

    # guesty reservation (with subcommands)
    reservation_parser = subparsers.add_parser(
        'reservation',
        help='Manage a specific reservation'
    )
    reservation_subparsers = reservation_parser.add_subparsers(dest='reservation_action')

    # guesty reservation get <id_or_code>
    get_parser = reservation_subparsers.add_parser('get', help='Show details for a specific reservation')
    get_parser.add_argument('id_or_code', help='Reservation ID or confirmation code')
    get_parser.add_argument('--json', action='store_true', help='Output as JSON')
    get_parser.add_argument('--live', action='store_true', help='Query live API')
    get_parser.set_defaults(func=run_get)
    
    # Add shortcut argument directly to reservation_parser
    # This allows: guesty reservation "CODE" -> acts as get
    reservation_parser.add_argument('shortcut_code', nargs='?', help=argparse.SUPPRESS)
    reservation_parser.add_argument('--json', action='store_true', help='Output as JSON')
    reservation_parser.add_argument('--live', action='store_true', help='Query live API')
    reservation_parser.set_defaults(func=run_reservation_shortcut)

    # guesty reservation create
    create_parser = reservation_subparsers.add_parser('create', help='Create a new reservation')
    create_parser.add_argument('--listing', type=str, required=True, help='Listing ID or nickname (required)')
    create_parser.add_argument('--guest-name', type=str, required=True, help='Guest full name (required)')
    create_parser.add_argument('--guest-email', type=str, required=True, help='Guest email (required)')
    create_parser.add_argument('--guest-phone', type=str, help='Guest phone number')
    create_parser.add_argument('--checkin', type=str, required=True, help='Check-in date (YYYY-MM-DD) (required)')
    create_parser.add_argument('--checkout', type=str, required=True, help='Check-out date (YYYY-MM-DD) (required)')
    create_parser.add_argument('--guests', type=int, help='Number of guests')
    create_parser.add_argument('--source', type=str, default='manual', help='Booking source (default: manual)')
    create_parser.add_argument('--notes', type=str, help='Internal notes')
    create_parser.add_argument('--dry-run', action='store_true', help='Show what would be sent without sending')
    create_parser.add_argument('--live', action='store_true', help='Create via live API')
    create_parser.set_defaults(func=run_create)

    # guesty reservation update <id_or_code>
    update_parser = reservation_subparsers.add_parser('update', help='Update an existing reservation')
    update_parser.add_argument('id_or_code', help='Reservation ID or confirmation code')
    update_parser.add_argument('--status', type=str, help='Reservation status (e.g., confirmed, cancelled)')
    update_parser.add_argument('--notes', type=str, help='Internal notes')
    update_parser.add_argument('--guest-name', type=str, help='Guest name')
    update_parser.add_argument('--guest-email', type=str, help='Guest email')
    update_parser.add_argument('--guest-phone', type=str, help='Guest phone')
    update_parser.add_argument('--checkin', type=str, help='Check-in date (YYYY-MM-DD)')
    update_parser.add_argument('--checkout', type=str, help='Check-out date (YYYY-MM-DD)')
    update_parser.add_argument('--guests', type=int, help='Number of guests')
    update_parser.add_argument('--dry-run', action='store_true', help='Show what would be sent without sending')
    update_parser.add_argument('--live', action='store_true', help='Update via live API')
    update_parser.set_defaults(func=run_update)

    # guesty reservation cancel <id_or_code>
    cancel_parser = reservation_subparsers.add_parser('cancel', help='Cancel a reservation')
    cancel_parser.add_argument('id_or_code', help='Reservation ID or confirmation code')
    cancel_parser.add_argument('--reason', type=str, help='Cancellation reason')
    cancel_parser.add_argument('--confirm', action='store_true', help='Confirm cancellation (required)')
    cancel_parser.add_argument('--live', action='store_true', help='Cancel via live API')
    cancel_parser.set_defaults(func=run_cancel)

    # guesty reservation approve <id_or_code>
    approve_parser = reservation_subparsers.add_parser('approve', help='Approve a channel reservation inquiry')
    approve_parser.add_argument('id_or_code', help='Reservation ID or confirmation code')
    approve_parser.add_argument('--live', action='store_true', help='Approve via live API')
    approve_parser.set_defaults(func=run_approve)

    # guesty reservation decline <id_or_code>
    decline_parser = reservation_subparsers.add_parser('decline', help='Decline a channel reservation inquiry')
    decline_parser.add_argument('id_or_code', help='Reservation ID or confirmation code')
    decline_parser.add_argument('--reason', type=str, help='Decline reason')
    decline_parser.add_argument('--live', action='store_true', help='Decline via live API')
    decline_parser.set_defaults(func=run_decline)
    
    # Set default handler for shortcut
    reservation_parser.set_defaults(func=run_reservation_shortcut)


def run_reservation_shortcut(args):
    """Handle shortcut: guesty reservation <code> -> guesty reservation get <code>."""
    # If reservation_action is set, it means a subcommand was used
    if getattr(args, 'reservation_action', None):
        # This shouldn't happen as subcommands have their own func
        return
    
    # Check if reservation_code was provided (not a known action)
    code = getattr(args, 'shortcut_code', None)
    if code and code not in KNOWN_RESERVATION_ACTIONS:
        # Treat as reservation code for get command
        args.id_or_code = code
        run_get(args)
    else:
        print(yellow("Usage: guesty reservation <code>  (shortcut for 'guesty reservation get <code>')"))
        print(yellow("       guesty reservation get <code>"))
        print(yellow("       guesty reservation create ..."))
        print(yellow("       guesty reservation update <code> ..."))
        print(yellow("       guesty reservation cancel <code> ..."))


def run(args):
    """Route to appropriate subcommand handler."""
    pass


def run_list(args):
    """List reservations."""
    config = load_config()

    today = datetime.now().strftime('%Y-%m-%d')

    # Build filters from enhanced filter system
    enhanced_filters = []

    # Parse --filter expression if provided
    if args.filter:
        try:
            enhanced_filters.extend(parse_filter_string(args.filter))
        except ValueError as e:
            print(red(f"Filter error: {e}"))
            print(yellow(f"\nValid filter fields: {', '.join(get_valid_fields())}"))
            print(yellow("Operators: =, !=, >, <, >=, <="))
            print(yellow("Example: --filter \"status=confirmed,balanceDue>0\""))
            return

    # Handle convenience flags
    if args.checkin_today:
        enhanced_filters.extend(today_checkins())
    if args.checkout_today:
        enhanced_filters.extend(today_checkouts())
    if args.unpaid:
        enhanced_filters.extend(unpaid_reservations())

    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)

        # Build filters
        filters = []
        if args.status:
            filters.append({"field": "status", "operator": "$eq", "value": args.status})
        if args.listing:
            filters.append({"field": "listing", "operator": "$eq", "value": args.listing})
        if args.source:
            filters.append({"field": "source", "operator": "$eq", "value": args.source})
        if args.today:
            filters.append({"field": "checkIn", "operator": "$eq", "value": today})
        if args.upcoming:
            next_week = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
            filters.append({"field": "checkIn", "operator": "$between", "value": [today, next_week]})
        if args.from_date:
            filters.append({"field": "checkIn", "operator": "$gte", "value": args.from_date})
        if args.to_date:
            filters.append({"field": "checkIn", "operator": "$lte", "value": args.to_date})

        # Add enhanced filters
        filters.extend(enhanced_filters)

        params = {'limit': min(args.limit, 100)}
        if filters:
            params['filters'] = json.dumps(filters)

        try:
            reservations = client.api_get_all('/v1/reservations', params)
        except Exception as e:
            print(red(f"Error fetching reservations: {e}"))
            return
    else:
        db = get_db()
        # Use JOINs to get listing nickname and guest name, plus calculated prices from invoice_items
        query = """SELECT r.*,
                          l.nickname as listing_nickname,
                          l.title as listing_title,
                          g.full_name as guest_fullName,
                          g.first_name as guest_firstName,
                          g.last_name as guest_lastName,
                          COALESCE((SELECT SUM(amount) FROM invoice_items ii
                                    WHERE ii.reservation_id = r.id
                                    AND ii.type IN ('accommodation', 'cleaning_fee')
                                    AND ii.amount > 0), 0) as calculated_price,
                          COALESCE((SELECT SUM(amount) FROM invoice_items ii
                                    WHERE ii.reservation_id = r.id
                                    AND ii.amount > 0), 0) as total_invoice_items
                   FROM reservations r
                   LEFT JOIN listings l ON r.listing_id = l.id
                   LEFT JOIN guests g ON r.guest_id = g.id
                   WHERE 1=1"""
        params = []

        if args.status:
            query += " AND r.status = ?"
            params.append(args.status)
        if args.listing:
            query += " AND r.listing_id = ?"
            params.append(args.listing)
        if args.source:
            query += " AND r.source = ?"
            params.append(args.source)
        if args.today:
            query += " AND r.check_in LIKE ?"
            params.append(f'{today}%')
        if args.upcoming:
            next_week = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
            query += " AND r.check_in BETWEEN ? AND ?"
            params.append(f'{today}T00:00:00.000Z')
            params.append(f'{next_week}T23:59:59.999Z')
        if args.from_date:
            query += " AND r.check_in >= ?"
            params.append(f'{args.from_date}T00:00:00.000Z')
        if args.to_date:
            query += " AND r.check_in <= ?"
            params.append(f'{args.to_date}T23:59:59.999Z')
        if args.guest:
            query += " AND (r.guestName LIKE ? OR r.guestEmail LIKE ? OR g.fullName LIKE ? OR g.firstName LIKE ? OR g.lastName LIKE ?)"
            search_term = f'%{args.guest}%'
            params.extend([search_term, search_term, search_term, search_term, search_term])

        # Apply enhanced filters to SQL query
        try:
            query, params = _apply_enhanced_filters_to_sql(query, params, enhanced_filters)
        except ValueError as e:
            print(red(f"Filter error: {e}"))
            return

        query += " ORDER BY r.check_in DESC LIMIT ?"
        params.append(args.limit)

        try:
            cursor = db.execute(query, params)
            reservations = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(red(f"Error querying database: {e}"))
            return

    if not reservations:
        print(yellow("No reservations found"))
        return

    # Format for output
    headers = ['Code', 'Guest', 'Listing', 'Check-in', 'Check-out', 'Status', 'Source', 'Price']
    rows = []
    for r in reservations:
        guest_name = _get_guest_name(r)
        price = _get_price_from_row(r, 'payoutAmount')
        status = _get_status_from_row(r)
        source = _get_source_from_row(r)
        listing_name = r.get('listing_nickname') or r.get('listingId', 'N/A')

        rows.append([
            r.get('confirmation_code', 'N/A'),
            guest_name[:30] if guest_name else 'N/A',
            listing_name[:25] if listing_name else 'N/A',
            clean_date(r.get('checkIn')),
            clean_date(r.get('checkOut')),
            status,
            format_source(source),
            format_money(price, r.get('currency', 'USD')),
        ])

    if args.json:
        print_json(reservations)
    elif args.csv:
        print_csv(headers, rows)
    else:
        print(f"\n{bold(f'Reservations ({len(reservations)} shown)')}")
        print_table(headers, rows)


def _apply_enhanced_filters_to_sql(query, params, filters):
    """Apply enhanced filters to SQL query.
    
    Args:
        query: Current SQL query string.
        params: Current query parameters.
        filters: List of filter dictionaries from parse_filter_string.
        
    Returns:
        Tuple of (updated_query, updated_params).
    """
    operator_map = {
        '$eq': '=',
        '$ne': '!=',
        '$gt': '>',
        '$lt': '<',
        '$gte': '>=',
        '$lte': '<=',
    }
    
    for f in filters:
        field = f.get('field')
        operator = f.get('operator')
        value = f.get('value')
        
        if not field or operator not in operator_map:
            continue
        
        sql_op = operator_map[operator]
        
        # Map API field names to SQL column names
        column_map = {
            'listingId': 'r.listing_id',
            'guestId': 'r.guest_id',
            'confirmation_code': 'r.confirmation_code',
            'status': 'r.status',
            'source': 'r.source',
            'checkIn': 'r.check_in',
            'checkOut': 'r.check_out',
            'nightsCount': 'r.nightsCount',
            'guestsCount': 'r.guestsCount',
            'totalPrice': 'r.totalPrice',
            'balanceDue': 'r.balanceDue',
            'payoutAmount': 'r.payoutAmount',
            'guestName': 'r.guestName',
            'guestEmail': 'r.guestEmail',
        }
        
        column = column_map.get(field, f'r.{field}')
        
        # Special handling for balanceDue (may need calculation)
        if field == 'balanceDue':
            # For now, skip balanceDue filters in local mode or use raw_json
            # This is complex because balanceDue might not be a direct column
            continue
        
        query += f" AND {column} {sql_op} ?"
        params.append(value)
    
    return query, params


def run_get(args):
    """Get details for a specific reservation."""
    config = load_config()

    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        try:
            reservation = client.api_get(f'/v1/reservations/{args.id_or_code}')
        except:
            # Try by confirmation code
            try:
                params = {'filters': json.dumps([{"field": "confirmation_code", "operator": "$eq", "value": args.id_or_code}])}
                results = client.api_get_all('/v1/reservations', params)
                if results:
                    reservation = results[0]
                else:
                    print(red(f"Reservation '{args.id_or_code}' not found"))
                    return
            except Exception as e:
                print(red(f"Error: {e}"))
                return
        financials = []
    else:
        db = get_db()
        try:
            # Try as ID first with JOINs
            cursor = db.execute("""
                SELECT r.*,
                       l.nickname as listing_nickname,
                       g.fullName as guest_fullName,
                       g.firstName as guest_firstName,
                       g.lastName as guest_lastName
                FROM reservations r
                LEFT JOIN listings l ON r.listing_id = l.id
                LEFT JOIN guests g ON r.guest_id = g.id
                WHERE r.id = ?
            """, (args.id_or_code,))
            row = cursor.fetchone()

            if not row:
                # Try by confirmation code with JOINs
                cursor = db.execute("""
                    SELECT r.*,
                           l.nickname as listing_nickname,
                           g.fullName as guest_fullName,
                           g.firstName as guest_firstName,
                           g.lastName as guest_lastName
                    FROM reservations r
                    LEFT JOIN listings l ON r.listing_id = l.id
                    LEFT JOIN guests g ON r.guest_id = g.id
                    WHERE r.confirmation_code = ?
                """, (args.id_or_code,))
                row = cursor.fetchone()

            if not row:
                print(red(f"Reservation '{args.id_or_code}' not found"))
                return

            reservation = dict(row)

            # Get invoice_items
            cursor = db.execute(
                "SELECT * FROM invoice_items WHERE reservation_id = ? ORDER BY type",
                (reservation.get('id'),)
            )
            invoice_items = [dict(r) for r in cursor.fetchall()]

        except Exception as e:
            print(red(f"Error: {e}"))
            return

    if args.json:
        result = {
            'reservation': reservation,
            'invoice_items': invoice_items
        }
        print_json(result)
        return

    # Print detail card
    guest_name = _get_guest_name(reservation)
    status = _get_status_from_row(reservation)
    source = _get_source_from_row(reservation)
    listing_name = reservation.get('listing_nickname') or reservation.get('listingId', 'N/A')
    total_price = _get_price_from_row(reservation, 'totalPrice')
    payout = _get_price_from_row(reservation, 'payoutAmount')
    balance_due = _get_balance_due_from_row(reservation)
    
    # Extract nights and guests from raw_json if not directly available
    nights_count = reservation.get('nightsCount')
    guests_count = reservation.get('guestsCount')
    
    if not nights_count or not guests_count:
        raw_json = reservation.get('raw_json')
        if raw_json:
            try:
                raw = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
                if not nights_count:
                    nights_count = raw.get('nightsCount')
                if not guests_count:
                    guests_count = raw.get('guestsCount')
                    # Also try nested in guestInfo
                    if not guests_count:
                        guest_info = raw.get('guestInfo', {})
                        guests_count = guest_info.get('numberOfGuests')
            except (json.JSONDecodeError, AttributeError):
                pass

    card_data = {
        'ID': reservation.get('id'),
        'Confirmation Code': reservation.get('confirmation_code'),
        'Guest': guest_name,
        'Guest Email': reservation.get('guestEmail', 'N/A'),
        'Guest Phone': reservation.get('guestPhone', 'N/A') or 'N/A',
        'Listing': listing_name,
        'Check-in': clean_date(reservation.get('checkIn')),
        'Check-out': clean_date(reservation.get('checkOut')),
        'Nights': nights_count if nights_count is not None else 'N/A',
        'Guests': guests_count if guests_count is not None else 'N/A',
        'Status': status,
        'Source': format_source(source),
        'Booked': clean_date(reservation.get('createdAt')),
        'Total Price': format_money(total_price, reservation.get('currency', 'USD')),
        'Payout': format_money(payout, reservation.get('currency', 'USD')),
        'Balance Due': format_money(balance_due, reservation.get('currency', 'USD')),
    }

    print_card(f"Reservation {reservation.get('confirmation_code', 'Unknown')}", card_data)

    # Invoice items breakdown
    if invoice_items:
        print()
        print(bold("Invoice Items"))
        headers = ['Type', 'Description', 'Amount']
        rows = []
        for ii in invoice_items:
            rows.append([
                ii.get('type') or 'N/A',
                (ii.get('description') or 'N/A')[:30],
                format_money(ii.get('amount', 0), ii.get('currency', 'USD')),
            ])
        print_table(headers, rows)
    else:
        print()
        print(dim("No detailed invoice items"))


def run_create(args):
    """Create a new reservation."""
    import json
    config = load_config()
    db = get_db()

    if args.live and not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return

    # Resolve listing ID
    cursor = db.execute("SELECT id FROM listings WHERE id = ? OR LOWER(nickname) LIKE LOWER(?)", 
                        (args.listing, f'%{args.listing}%'))
    row = cursor.fetchone()
    if not row:
        print(red(f"Listing '{args.listing}' not found in local database"))
        return
    listing_id = row['id']

    # Calculate nights
    try:
        checkin = datetime.strptime(args.checkin, '%Y-%m-%d')
        checkout = datetime.strptime(args.checkout, '%Y-%m-%d')
        nights = (checkout - checkin).days
    except ValueError:
        print(red("Error: Invalid date format. Use YYYY-MM-DD"))
        return

    # Build the data payload
    data = {
        'listingId': listing_id,
        'checkIn': args.checkin,
        'checkOut': args.checkout,
        'nightsCount': nights,
        'guestName': args.guest_name,
        'guestEmail': args.guest_email,
        'source': args.source,
    }

    if args.guest_phone:
        data['guestPhone'] = args.guest_phone
    if args.guests:
        data['guestsCount'] = args.guests
    if args.notes:
        data['internalNotes'] = args.notes

    if args.dry_run:
        print(cyan("[DRY RUN] Would create reservation with:"))
        print(json.dumps(data, indent=2))
        return

    if args.live:
        client = GuestyClient(config)
        try:
            result = client.api_post('reservations', data)
            print(green(f"✓ Reservation created successfully!"))
            print(f"  ID: {result.get('_id', result.get('id', 'N/A'))}")
            print(f"  Confirmation Code: {result.get('confirmation_code', 'N/A')}")
            print(f"  Guest: {args.guest_name}")
            print(f"  Dates: {args.checkin} to {args.checkout}")
        except Exception as e:
            print(red(f"Error creating reservation: {e}"))
    else:
        print(yellow("Use --live to actually create the reservation via API"))
        print(cyan("Would create reservation with:"))
        print(json.dumps(data, indent=2))


def run_update(args):
    """Update an existing reservation."""
    import json
    config = load_config()
    db = get_db()

    # Resolve reservation ID
    reservation_id, confirmation_code = _resolve_reservation(db, args.id_or_code)
    if not reservation_id:
        print(red(f"Reservation '{args.id_or_code}' not found in local database"))
        return

    # Get current reservation data
    cursor = db.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
    current = dict(cursor.fetchone())

    # Build update payload with only changed fields
    updates = {}
    if args.status is not None and args.status != current.get('status'):
        updates['status'] = args.status
    if args.notes is not None:
        updates['internalNotes'] = args.notes
    if args.guest_name is not None and args.guest_name != current.get('guestName'):
        updates['guestName'] = args.guest_name
    if args.guest_email is not None and args.guest_email != current.get('guestEmail'):
        updates['guestEmail'] = args.guest_email
    if args.guest_phone is not None and args.guest_phone != current.get('guestPhone'):
        updates['guestPhone'] = args.guest_phone
    if args.checkin is not None and args.checkin != current.get('checkIn', '')[:10]:
        updates['checkIn'] = args.checkin
    if args.checkout is not None and args.checkout != current.get('checkOut', '')[:10]:
        updates['checkOut'] = args.checkout
    if args.guests is not None and args.guests != current.get('guestsCount'):
        updates['guestsCount'] = args.guests

    if not updates:
        print(yellow("No changes to apply"))
        return

    if args.dry_run:
        print(cyan("[DRY RUN] Would update reservation with:"))
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
            result = client.api_put(f'reservations/{reservation_id}', updates)
            print(green(f"✓ Reservation updated successfully!"))
            print(f"  ID: {reservation_id}")
            print(f"  Code: {confirmation_code or 'N/A'}")
            print(bold("Changes applied:"))
            for key, value in updates.items():
                print(f"  {key}: {value}")
        except Exception as e:
            print(red(f"Error updating reservation: {e}"))
    else:
        print(yellow("Use --live to actually update the reservation via API"))
        print(cyan("Would update reservation with:"))
        print(bold("Changes:"))
        for key, value in updates.items():
            old_val = current.get(key, 'N/A')
            print(f"  {key}: {red(old_val)} → {green(value)}")


def run_cancel(args):
    """Cancel a reservation."""
    config = load_config()
    db = get_db()

    # Resolve reservation ID
    reservation_id, confirmation_code = _resolve_reservation(db, args.id_or_code)
    if not reservation_id:
        print(red(f"Reservation '{args.id_or_code}' not found in local database"))
        return

    # Get reservation details for confirmation
    cursor = db.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
    reservation = dict(cursor.fetchone())

    print(bold("Reservation to cancel:"))
    print(f"  ID: {reservation_id}")
    print(f"  Code: {confirmation_code or 'N/A'}")
    print(f"  Guest: {reservation.get('guestName', 'N/A')}")
    print(f"  Dates: {reservation.get('checkIn', 'N/A')[:10] if reservation.get('checkIn') else 'N/A'} to {reservation.get('checkOut', 'N/A')[:10] if reservation.get('checkOut') else 'N/A'}")
    if args.reason:
        print(f"  Reason: {args.reason}")

    if not args.confirm:
        print()
        print(red("WARNING: This will cancel the reservation!"))
        print(yellow("Use --confirm to cancel this reservation"))
        return

    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        try:
            # Note: Some APIs use DELETE, some use POST to cancel endpoint
            client.api_delete(f'reservations/{reservation_id}')
            print(green(f"✓ Reservation '{confirmation_code or reservation_id}' cancelled successfully"))
        except Exception as e:
            print(red(f"Error cancelling reservation: {e}"))
    else:
        print(yellow("Use --live to actually cancel the reservation via API"))
        print(cyan("[DRY RUN] Reservation would be cancelled"))


def run_approve(args):
    """Approve a channel reservation inquiry."""
    config = load_config()
    db = get_db()

    # Resolve reservation ID
    reservation_id, confirmation_code = _resolve_reservation(db, args.id_or_code)
    if not reservation_id:
        print(red(f"Reservation '{args.id_or_code}' not found in local database"))
        return

    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        try:
            # Try v3 endpoint first, fall back to v1
            try:
                result = client.api_post(f'reservations/{reservation_id}/approve', {})
            except:
                # Try alternative endpoint
                result = client.api_post(f'reservations-v3/{reservation_id}/approve', {})
            print(green(f"✓ Reservation '{confirmation_code or reservation_id}' approved successfully"))
        except Exception as e:
            print(red(f"Error approving reservation: {e}"))
            print(dim("Note: This endpoint may require v3 API access or special permissions"))
    else:
        print(yellow("Use --live to actually approve the reservation via API"))
        print(cyan("[DRY RUN] Would approve reservation via POST /reservations/{id}/approve"))


def run_decline(args):
    """Decline a channel reservation inquiry."""
    config = load_config()
    db = get_db()

    # Resolve reservation ID
    reservation_id, confirmation_code = _resolve_reservation(db, args.id_or_code)
    if not reservation_id:
        print(red(f"Reservation '{args.id_or_code}' not found in local database"))
        return

    data = {}
    if args.reason:
        data['reason'] = args.reason

    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        try:
            # Try v3 endpoint first, fall back to v1
            try:
                result = client.api_post(f'reservations/{reservation_id}/decline', data)
            except:
                # Try alternative endpoint
                result = client.api_post(f'reservations-v3/{reservation_id}/decline', data)
            print(green(f"✓ Reservation '{confirmation_code or reservation_id}' declined successfully"))
        except Exception as e:
            print(red(f"Error declining reservation: {e}"))
            print(dim("Note: This endpoint may require v3 API access or special permissions"))
    else:
        print(yellow("Use --live to actually decline the reservation via API"))
        print(cyan("[DRY RUN] Would decline reservation via POST /reservations/{id}/decline"))
        if args.reason:
            print(f"  Reason: {args.reason}")


def _resolve_reservation(db, id_or_code):
    """Resolve a reservation ID or confirmation code to (id, confirmation_code)."""
    # Try as ID first
    cursor = db.execute("SELECT id, confirmation_code FROM reservations WHERE id = ?", (id_or_code,))
    row = cursor.fetchone()
    if row:
        return row['id'], row['confirmation_code']
    
    # Try as confirmation code
    cursor = db.execute("SELECT id, confirmation_code FROM reservations WHERE confirmation_code = ?", (id_or_code,))
    row = cursor.fetchone()
    if row:
        return row['id'], row['confirmation_code']
    
    return None, None
