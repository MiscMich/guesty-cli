"""
Guests management commands for guesty-cli.
"""
from guesty_cli.core.config import load_config
from guesty_cli.core.database import get_db
from guesty_cli.core.client import GuestyClient
from guesty_cli.core.output import (
    print_table, print_card, print_json, print_csv,
    bold, cyan, green, red, yellow, format_money
)


def register(subparsers):
    """Register guests commands with the argument parser."""
    # guesty guests (list)
    list_parser = subparsers.add_parser(
        'guests',
        help='List all guests'
    )
    list_parser.set_defaults(func=run_list)
    list_parser.add_argument('--search', type=str, help='Search query')
    list_parser.add_argument('--limit', type=int, default=50, help='Limit results')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    list_parser.add_argument('--csv', action='store_true', help='Output as CSV')
    list_parser.add_argument('--live', action='store_true', help='Query live API')
    
    # guesty guest (get single)
    get_parser = subparsers.add_parser(
        'guest',
        help='Show details for a specific guest'
    )
    get_parser.set_defaults(func=run_get)
    get_parser.add_argument('id_or_email', help='Guest ID or email')
    get_parser.add_argument('--json', action='store_true', help='Output as JSON')
    get_parser.add_argument('--live', action='store_true', help='Query live API')


def run(args):
    """Route to appropriate subcommand handler."""
    pass


def run_list(args):
    """List all guests."""
    config = load_config()
    
    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        try:
            guests = client.api_get_all('guests', {'limit': min(args.limit, 100)})
        except Exception as e:
            print(red(f"Error fetching guests: {e}"))
            return
    else:
        db = get_db()
        query = "SELECT * FROM guests WHERE 1=1"
        params = []
        
        if args.search:
            query += " AND (first_name LIKE ? OR last_name LIKE ? OR full_name LIKE ? OR email LIKE ? OR phone LIKE ?)"
            search_term = f'%{args.search}%'
            params.extend([search_term, search_term, search_term, search_term, search_term])
        
        query += " ORDER BY last_name, first_name LIMIT ?"
        params.append(args.limit)
        
        try:
            cursor = db.execute(query, params)
            guests = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(red(f"Error querying database: {e}"))
            return
    
    if not guests:
        print(yellow("No guests found"))
        return
    
    # Format for output
    headers = ['Name', 'Email', 'Phone', 'Reservations']
    rows = []
    for g in guests:
        # Count reservations
        res_count = 0
        if not args.live:
            try:
                cursor = db.execute("SELECT COUNT(*) FROM reservations WHERE guest_id = ?", (g.get('id'),))
                res_count = cursor.fetchone()[0]
            except:
                pass
        
        rows.append([
            g.get('full_name') or g.get('fullName') or ' '.join(filter(None, [g.get('first_name') or g.get('firstName'), g.get('last_name') or g.get('lastName')])) or 'N/A',
            g.get('email', 'N/A'),
            g.get('phone', 'N/A') or 'N/A',
            res_count if not args.live else '-',
        ])
    
    if args.json:
        print_json(guests)
    elif args.csv:
        print_csv(headers, rows)
    else:
        print(f"\n{bold(f'Guests ({len(guests)} shown)')}")
        print_table(headers, rows)


def run_get(args):
    """Get details for a specific guest."""
    config = load_config()
    
    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        try:
            guest = client.api_get(f'guests/{args.id_or_email}')
        except:
            # Try by email
            try:
                guests = client.api_get_all('guests', {'limit': 100})
                for g in guests:
                    if g.get('email') == args.id_or_email:
                        guest = g
                        break
                else:
                    print(red(f"Guest '{args.id_or_email}' not found"))
                    return
            except Exception as e:
                print(red(f"Error: {e}"))
                return
        reservations = []
    else:
        db = get_db()
        try:
            # Try as ID first
            cursor = db.execute("SELECT * FROM guests WHERE id = ?", (args.id_or_email,))
            row = cursor.fetchone()
            
            if not row:
                # Try by email
                cursor = db.execute("SELECT * FROM guests WHERE email = ?", (args.id_or_email,))
                row = cursor.fetchone()
            
            if not row:
                print(red(f"Guest '{args.id_or_email}' not found"))
                return
            
            guest = dict(row)
            
            # Get reservation history
            cursor = db.execute(
                """SELECT * FROM reservations
                   WHERE guest_id = ?
                   ORDER BY check_in DESC""",
                (guest.get('id'),)
            )
            reservations = [dict(r) for r in cursor.fetchall()]
            
        except Exception as e:
            print(red(f"Error: {e}"))
            return
    
    if args.json:
        result = {
            'guest': guest,
            'reservations': reservations
        }
        print_json(result)
        return
    
    # Print detail card
    card_data = {
        'ID': guest.get('id'),
        'Name': guest.get('full_name') or guest.get('fullName') or f"{guest.get('first_name') or guest.get('firstName', '')} {guest.get('last_name') or guest.get('lastName', '')}".strip() or 'N/A',
        'Email': guest.get('email', 'N/A'),
        'Phone': guest.get('phone', 'N/A') or 'N/A',
        'Nationality': guest.get('nationality', 'N/A') or 'N/A',
        'Hometown': guest.get('hometown', 'N/A') or 'N/A',
        'Created': guest.get('createdAt', 'N/A'),
    }
    
    print_card(f"Guest: {card_data['Name']}", card_data)
    
    # Reservation history
    if reservations:
        print()
        print(bold("Reservation History"))
        headers = ['Code', 'Listing', 'Check-in', 'Nights', 'Status', 'Amount']
        rows = []
        total_spent = 0
        for r in reservations:
            amount = r.get('total_price', 0) or 0
            total_spent += amount
            rows.append([
                r.get('confirmation_code', 'N/A'),
                (r.get('listing_id') or 'N/A')[:20],
                r.get('check_in', 'N/A')[:10] if r.get('check_in') else 'N/A',
                r.get('nights', 'N/A'),
                r.get('status', 'N/A'),
                format_money(amount, r.get('currency', 'USD')),
            ])
        print_table(headers, rows)
        print()
        print(f"  Total Reservations: {len(reservations)}")
        print(f"  Total Spent: {format_money(total_spent)}")
    else:
        print()
        print(dim("No reservation history found"))
