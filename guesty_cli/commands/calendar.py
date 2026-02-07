"""Calendar management commands for guesty-cli."""
import json
from datetime import datetime, timedelta
from guesty_cli.core.config import load_config
from guesty_cli.core.database import get_db
from guesty_cli.core.client import GuestyClient
from guesty_cli.core.output import (
    bold, cyan, green, red, yellow, dim, print_json
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


def _generate_date_range(start_date, end_date):
    """Generate a list of dates between start and end (inclusive)."""
    dates = []
    current = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    while current <= end:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)
    return dates


def register(subparsers):
    """Register calendar commands with the argument parser."""
    # guesty calendar (main command)
    calendar_parser = subparsers.add_parser(
        'calendar',
        help='View and manage listing calendar'
    )
    calendar_subparsers = calendar_parser.add_subparsers(dest='calendar_action')
    
    # View calendar
    view_parser = calendar_subparsers.add_parser('view', help='View calendar')
    view_parser.add_argument('listing', help='Listing ID or nickname')
    view_parser.add_argument('--from', dest='from_date', type=str, help='Start date (YYYY-MM-DD)')
    view_parser.add_argument('--to', dest='to_date', type=str, help='End date (YYYY-MM-DD)')
    view_parser.add_argument('--json', action='store_true', help='Output as JSON')
    view_parser.add_argument('--live', action='store_true', help='Query live API')
    view_parser.set_defaults(func=run_view)
    
    # Block dates
    block_parser = calendar_subparsers.add_parser('block', help='Block dates')
    block_parser.add_argument('listing', help='Listing ID or nickname')
    block_parser.add_argument('date', help='Date to block (YYYY-MM-DD)')
    block_parser.add_argument('--to', dest='to_date', type=str, help='Block until date (inclusive)')
    block_parser.add_argument('--reason', type=str, default='manual', help='Block reason')
    block_parser.add_argument('--dry-run', action='store_true', help='Show what would be sent without sending')
    block_parser.add_argument('--live', action='store_true', help='Apply via live API')
    block_parser.set_defaults(func=run_block)
    
    # Unblock dates
    unblock_parser = calendar_subparsers.add_parser('unblock', help='Unblock dates')
    unblock_parser.add_argument('listing', help='Listing ID or nickname')
    unblock_parser.add_argument('date', help='Date to unblock (YYYY-MM-DD)')
    unblock_parser.add_argument('--to', dest='to_date', type=str, help='Unblock until date (inclusive)')
    unblock_parser.add_argument('--dry-run', action='store_true', help='Show what would be sent without sending')
    unblock_parser.add_argument('--live', action='store_true', help='Apply via live API')
    unblock_parser.set_defaults(func=run_unblock)
    
    # Update price
    price_parser = calendar_subparsers.add_parser('price', help='Update nightly price')
    price_parser.add_argument('listing', help='Listing ID or nickname')
    price_parser.add_argument('date', help='Date to update (YYYY-MM-DD)')
    price_parser.add_argument('price', type=float, help='Nightly price')
    price_parser.add_argument('--to', dest='to_date', type=str, help='Apply price until date (inclusive)')
    price_parser.add_argument('--currency', type=str, default='USD', help='Currency code (default: USD)')
    price_parser.add_argument('--dry-run', action='store_true', help='Show what would be sent without sending')
    price_parser.add_argument('--live', action='store_true', help='Apply via live API')
    price_parser.set_defaults(func=run_price)


def run_view(args):
    """View calendar for a listing."""
    config = load_config()
    db = get_db()
    
    if not args.listing:
        print(red("Error: Listing ID or nickname required"))
        return
    
    # Resolve listing ID from local DB
    listing_id, nickname = _resolve_listing(db, args.listing)
    if not listing_id:
        print(red(f"Listing '{args.listing}' not found in local database"))
        return
    
    # Default to next 30 days
    today = datetime.now()
    from_date = args.from_date or today.strftime('%Y-%m-%d')
    to_date = args.to_date or (today + timedelta(days=30)).strftime('%Y-%m-%d')
    
    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        try:
            calendar = client.api_get(
                f'/v1/listings/{listing_id}/calendar',
                {'from': from_date, 'to': to_date}
            )
        except Exception as e:
            print(red(f"Error fetching calendar: {e}"))
            return
    else:
        print(yellow("Use --live to fetch fresh calendar data from API"))
        print(dim("Calendar view requires --live flag"))
        return
    
    if args.json:
        print_json(calendar)
        return
    
    print()
    print(bold(f"Calendar: {nickname or listing_id}"))
    print(f"{dim(from_date)} to {dim(to_date)}")
    print()
    
    # Process calendar data
    days = calendar if isinstance(calendar, list) else calendar.get('days', [])
    
    if not days:
        print(yellow("No calendar data available"))
        return
    
    # Group by month for display
    months = {}
    for day in days:
        date_str = day.get('date', '')
        if not date_str:
            continue
        month_key = date_str[:7]  # YYYY-MM
        if month_key not in months:
            months[month_key] = []
        months[month_key].append(day)
    
    # Print each month
    for month_key, month_days in sorted(months.items()):
        month_name = datetime.strptime(month_key, '%Y-%m').strftime('%B %Y')
        print(bold(month_name))
        
        # Print weekday headers
        print("  " + " ".join(['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']))
        
        # Calculate padding for first day
        first_day = month_days[0]
        first_date = datetime.strptime(first_day.get('date'), '%Y-%m-%d')
        padding = (first_date.weekday() + 1) % 7  # Monday = 0
        
        # Build rows
        current_row = "  " + "   " * padding
        for day in month_days:
            date = datetime.strptime(day.get('date'), '%Y-%m-%d')
            day_num = date.day
            
            # Determine status color
            if day.get('blocked', False):
                color = yellow  # Blocked
                symbol = "B"
            elif day.get('status') == 'reserved' or day.get('reservationId'):
                color = red  # Booked
                symbol = "X"
            else:
                color = green  # Available
                symbol = "·"
            
            current_row += f"{color(f'{day_num:2d}')} "
            
            # New row on Sunday
            if date.weekday() == 6:
                print(current_row)
                current_row = "  "
        
        if current_row.strip():
            print(current_row)
        
        print()
    
    # Legend
    print("Legend: " + green("· Available") + "  " + red("X Booked") + "  " + yellow("B Blocked"))


def run_block(args):
    """Block dates on the calendar."""
    config = load_config()
    db = get_db()
    
    # Resolve listing ID from local DB
    listing_id, nickname = _resolve_listing(db, args.listing)
    if not listing_id:
        print(red(f"Listing '{args.listing}' not found in local database"))
        return
    
    start_date = args.date
    end_date = args.to_date or start_date
    
    # Validate dates
    try:
        dates = _generate_date_range(start_date, end_date)
    except ValueError as e:
        print(red(f"Invalid date format: {e}. Use YYYY-MM-DD"))
        return
    
    # Build the dates array for API
    dates_data = []
    for date_str in dates:
        dates_data.append({
            'date': date_str,
            'status': 'blocked',
            'blockReason': args.reason
        })
    
    data = {'dates': dates_data}
    
    if args.dry_run:
        print(cyan("[DRY RUN] Would block dates with:"))
        print(f"  Listing: {nickname or listing_id}")
        print(f"  Dates: {start_date} to {end_date} ({len(dates)} days)")
        print(f"  Reason: {args.reason}")
        print(json.dumps(data, indent=2))
        return
    
    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        try:
            client.api_put(f'/v1/listings/{listing_id}/calendar', data)
            print(green(f"✓ Blocked {start_date} to {end_date} on '{nickname}' ({len(dates)} days)"))
            print(f"  Reason: {args.reason}")
        except Exception as e:
            print(red(f"Error blocking dates: {e}"))
    else:
        print(yellow("Use --live to actually block dates via API"))
        print(cyan("Would block dates with:"))
        print(f"  Listing: {nickname or listing_id}")
        print(f"  Dates: {start_date} to {end_date} ({len(dates)} days)")
        print(f"  Reason: {args.reason}")


def run_unblock(args):
    """Unblock dates on the calendar."""
    config = load_config()
    db = get_db()
    
    # Resolve listing ID from local DB
    listing_id, nickname = _resolve_listing(db, args.listing)
    if not listing_id:
        print(red(f"Listing '{args.listing}' not found in local database"))
        return
    
    start_date = args.date
    end_date = args.to_date or start_date
    
    # Validate dates
    try:
        dates = _generate_date_range(start_date, end_date)
    except ValueError as e:
        print(red(f"Invalid date format: {e}. Use YYYY-MM-DD"))
        return
    
    # Build the dates array for API
    dates_data = []
    for date_str in dates:
        dates_data.append({
            'date': date_str,
            'status': 'available'
        })
    
    data = {'dates': dates_data}
    
    if args.dry_run:
        print(cyan("[DRY RUN] Would unblock dates with:"))
        print(f"  Listing: {nickname or listing_id}")
        print(f"  Dates: {start_date} to {end_date} ({len(dates)} days)")
        print(json.dumps(data, indent=2))
        return
    
    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        try:
            client.api_put(f'/v1/listings/{listing_id}/calendar', data)
            print(green(f"✓ Unblocked {start_date} to {end_date} on '{nickname}' ({len(dates)} days)"))
        except Exception as e:
            print(red(f"Error unblocking dates: {e}"))
    else:
        print(yellow("Use --live to actually unblock dates via API"))
        print(cyan("Would unblock dates with:"))
        print(f"  Listing: {nickname or listing_id}")
        print(f"  Dates: {start_date} to {end_date} ({len(dates)} days)")


def run_price(args):
    """Update nightly price for dates."""
    config = load_config()
    db = get_db()
    
    # Resolve listing ID from local DB
    listing_id, nickname = _resolve_listing(db, args.listing)
    if not listing_id:
        print(red(f"Listing '{args.listing}' not found in local database"))
        return
    
    start_date = args.date
    end_date = args.to_date or start_date
    price = args.price
    
    # Validate dates
    try:
        dates = _generate_date_range(start_date, end_date)
    except ValueError as e:
        print(red(f"Invalid date format: {e}. Use YYYY-MM-DD"))
        return
    
    # Build the dates array for API
    dates_data = []
    for date_str in dates:
        dates_data.append({
            'date': date_str,
            'price': price,
            'currency': args.currency
        })
    
    data = {'dates': dates_data}
    
    if args.dry_run:
        print(cyan("[DRY RUN] Would update prices with:"))
        print(f"  Listing: {nickname or listing_id}")
        print(f"  Dates: {start_date} to {end_date} ({len(dates)} days)")
        print(f"  Price: {price} {args.currency}")
        print(json.dumps(data, indent=2))
        return
    
    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        try:
            client.api_put(f'/v1/listings/{listing_id}/calendar', data)
            print(green(f"✓ Updated price to {price} {args.currency} for {start_date} to {end_date} on '{nickname}' ({len(dates)} days)"))
        except Exception as e:
            print(red(f"Error updating prices: {e}"))
    else:
        print(yellow("Use --live to actually update prices via API"))
        print(cyan("Would update prices with:"))
        print(f"  Listing: {nickname or listing_id}")
        print(f"  Dates: {start_date} to {end_date} ({len(dates)} days)")
        print(f"  Price: {price} {args.currency}")
