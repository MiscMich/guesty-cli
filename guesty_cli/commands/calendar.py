"""Calendar management commands for guesty-cli."""
import concurrent.futures
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from guesty_cli.core.config import load_config
from guesty_cli.core.database import get_db
from guesty_cli.core.client import GuestyClient, RateLimitError
from guesty_cli.core.output import (
    bold, cyan, green, red, yellow, dim, print_json, print_table
)
from guesty_cli.utils.dates import parse_date


# Block flag decoder mapping
BLOCK_FLAG_DECODER = {
    'm': 'manual',
    'r': 'reservation',
    'b': 'block',
    'o': 'owner_block',
    'p': 'price_unavailable',
    'n': 'min_stay_unavailable',
    't': 'turnover_day',
    'a': 'arrival_rule',
    'd': 'departure_rule',
    'f': 'far_booking',
    'l': 'length_of_stay',
}


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


def run_availability_report(args):
    """Generate availability report."""
    print(yellow("Calendar availability-report not yet implemented."))


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
    
    # Sync single listing calendar
    sync_parser = calendar_subparsers.add_parser('sync', help='Sync calendar data to local database')
    sync_parser.add_argument('listing', help='Listing ID or nickname')
    sync_parser.add_argument('--from', dest='from_date', type=str, required=True,
                            help='Start date (YYYY-MM-DD)')
    sync_parser.add_argument('--to', dest='to_date', type=str, required=True,
                            help='End date (YYYY-MM-DD)')
    sync_parser.add_argument('--dry-run', action='store_true',
                            help='Show what would be synced without storing')
    sync_parser.add_argument('--json', action='store_true', help='Output as JSON')
    sync_parser.set_defaults(func=run_sync)
    
    # Sync all listings
    sync_all_parser = calendar_subparsers.add_parser('sync-all', help='Sync calendar for all listings')
    sync_all_parser.add_argument('--from', dest='from_date', type=str, required=True,
                                 help='Start date (YYYY-MM-DD)')
    sync_all_parser.add_argument('--to', dest='to_date', type=str, required=True,
                                 help='End date (YYYY-MM-DD)')
    sync_all_parser.add_argument('--parallel', type=int, default=5,
                                 help='Maximum parallel API calls (default: 5)')
    sync_all_parser.add_argument('--dry-run', action='store_true',
                                 help='Show what would be synced without storing')
    sync_all_parser.add_argument('--json', action='store_true', help='Output as JSON')
    sync_all_parser.set_defaults(func=run_sync_all)
    
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
    
    # Block dates across multiple listings
    block_all_parser = calendar_subparsers.add_parser('block-all', help='Block dates across multiple listings')
    block_all_parser.add_argument('--from', dest='from_date', type=str, required=True, help='Start date (YYYY-MM-DD)')
    block_all_parser.add_argument('--to', dest='to_date', type=str, required=True, help='End date (YYYY-MM-DD)')
    block_all_parser.add_argument('--listings', type=str, required=True, help='Comma-separated listing IDs or nicknames')
    block_all_parser.add_argument('--reason', type=str, default='manual', help='Block reason')
    block_all_parser.add_argument('--parallel', type=int, default=5, help='Maximum parallel API calls (default: 5)')
    block_all_parser.add_argument('--dry-run', action='store_true', help='Show what would be sent without sending')
    block_all_parser.add_argument('--live', action='store_true', help='Apply via live API')
    block_all_parser.set_defaults(func=run_block_all)
    
    # Unblock dates across multiple listings
    unblock_all_parser = calendar_subparsers.add_parser('unblock-all', help='Unblock dates across multiple listings')
    unblock_all_parser.add_argument('--from', dest='from_date', type=str, required=True, help='Start date (YYYY-MM-DD)')
    unblock_all_parser.add_argument('--to', dest='to_date', type=str, required=True, help='End date (YYYY-MM-DD)')
    unblock_all_parser.add_argument('--listings', type=str, required=True, help='Comma-separated listing IDs or nicknames')
    unblock_all_parser.add_argument('--parallel', type=int, default=5, help='Maximum parallel API calls (default: 5)')
    unblock_all_parser.add_argument('--dry-run', action='store_true', help='Show what would be sent without sending')
    unblock_all_parser.add_argument('--live', action='store_true', help='Apply via live API')
    unblock_all_parser.set_defaults(func=run_unblock_all)
    
    # Bulk price updates across multiple listings
    price_all_parser = calendar_subparsers.add_parser('price-all', help='Bulk price updates across multiple listings')
    price_all_parser.add_argument('--from', dest='from_date', type=str, required=True, help='Start date (YYYY-MM-DD)')
    price_all_parser.add_argument('--to', dest='to_date', type=str, required=True, help='End date (YYYY-MM-DD)')
    price_all_parser.add_argument('--listings', type=str, required=True, help='Comma-separated listing IDs or nicknames')
    price_all_parser.add_argument('--set', dest='price', type=float, required=True, help='Nightly price to set')
    price_all_parser.add_argument('--currency', type=str, default='USD', help='Currency code (default: USD)')
    price_all_parser.add_argument('--parallel', type=int, default=5, help='Maximum parallel API calls (default: 5)')
    price_all_parser.add_argument('--dry-run', action='store_true', help='Show what would be sent without sending')
    price_all_parser.add_argument('--live', action='store_true', help='Apply via live API')
    price_all_parser.set_defaults(func=run_price_all)
    
    # Dynamic pricing based on occupancy
    price_dynamic_parser = calendar_subparsers.add_parser('price-dynamic', help='Auto-adjust pricing based on occupancy (dry-run by default)')
    price_dynamic_parser.add_argument('listing', help='Listing ID or nickname')
    price_dynamic_parser.add_argument('--from', dest='from_date', type=str, required=True, help='Start date (YYYY-MM-DD)')
    price_dynamic_parser.add_argument('--to', dest='to_date', type=str, required=True, help='End date (YYYY-MM-DD)')
    price_dynamic_parser.add_argument('--low-occupancy-threshold', type=int, default=30, help='Occupancy % below which to consider low (default: 30)')
    price_dynamic_parser.add_argument('--high-occupancy-threshold', type=int, default=70, help='Occupancy % above which to consider high (default: 70)')
    price_dynamic_parser.add_argument('--decrease-percent', type=int, default=10, help='Price decrease % for low occupancy (default: 10)')
    price_dynamic_parser.add_argument('--increase-percent', type=int, default=15, help='Price increase % for high occupancy (default: 15)')
    price_dynamic_parser.add_argument('--lookback-days', type=int, default=30, help='Days to look back for occupancy calculation (default: 30)')
    price_dynamic_parser.add_argument('--base-price', type=float, help='Base price to use (auto-detect if not provided)')
    price_dynamic_parser.add_argument('--min-price', type=float, help='Minimum price floor')
    price_dynamic_parser.add_argument('--max-price', type=float, help='Maximum price ceiling')
    price_dynamic_parser.add_argument('--dry-run', action='store_true', help='Show what would be sent without sending (default)')
    price_dynamic_parser.add_argument('--live', action='store_true', help='Apply via live API')
    price_dynamic_parser.set_defaults(func=run_price_dynamic)


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
                f'listings/{listing_id}/calendar',
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
            client.api_put(f'listings/{listing_id}/calendar', data)
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
            client.api_put(f'listings/{listing_id}/calendar', data)
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
            client.api_put(f'listings/{listing_id}/calendar', data)
            print(green(f"✓ Updated price to {price} {args.currency} for {start_date} to {end_date} on '{nickname}' ({len(dates)} days)"))
        except Exception as e:
            print(red(f"Error updating prices: {e}"))
    else:
        print(yellow("Use --live to actually update prices via API"))
        print(cyan("Would update prices with:"))
        print(f"  Listing: {nickname or listing_id}")
        print(f"  Dates: {start_date} to {end_date} ({len(dates)} days)")
        print(f"  Price: {price} {args.currency}")


# ============ BULK CALENDAR OPERATIONS ============

def _resolve_listings(db, listings_str: str) -> List[Tuple[str, str]]:
    """Resolve a comma-separated string of listing IDs or nicknames to (id, nickname) tuples.
    
    Returns a list of successfully resolved listings.
    """
    resolved = []
    identifiers = [s.strip() for s in listings_str.split(',') if s.strip()]
    
    for identifier in identifiers:
        listing_id, nickname = _resolve_listing(db, identifier)
        if listing_id:
            resolved.append((listing_id, nickname))
        else:
            print(yellow(f"Warning: Listing '{identifier}' not found, skipping"))
    
    return resolved


def _block_listing(
    listing_id: str,
    nickname: str,
    dates: List[str],
    reason: str,
    client: GuestyClient,
    dry_run: bool = False
) -> Dict:
    """Block dates for a single listing.
    
    Returns a dict with operation results.
    """
    result = {
        'listing_id': listing_id,
        'nickname': nickname,
        'status': 'pending',
        'dates_count': len(dates),
        'error': None,
    }
    
    dates_data = [{'date': d, 'status': 'blocked', 'blockReason': reason} for d in dates]
    data = {'dates': dates_data}
    
    if dry_run:
        result['status'] = 'dry_run'
        return result
    
    try:
        client.api_put(f'listings/{listing_id}/calendar', data)
        result['status'] = 'success'
    except RateLimitError as e:
        result['status'] = 'rate_limited'
        result['error'] = str(e)
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)
    
    return result


def _unblock_listing(
    listing_id: str,
    nickname: str,
    dates: List[str],
    client: GuestyClient,
    dry_run: bool = False
) -> Dict:
    """Unblock dates for a single listing.
    
    Returns a dict with operation results.
    """
    result = {
        'listing_id': listing_id,
        'nickname': nickname,
        'status': 'pending',
        'dates_count': len(dates),
        'error': None,
    }
    
    dates_data = [{'date': d, 'status': 'available'} for d in dates]
    data = {'dates': dates_data}
    
    if dry_run:
        result['status'] = 'dry_run'
        return result
    
    try:
        client.api_put(f'listings/{listing_id}/calendar', data)
        result['status'] = 'success'
    except RateLimitError as e:
        result['status'] = 'rate_limited'
        result['error'] = str(e)
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)
    
    return result


def _price_listing(
    listing_id: str,
    nickname: str,
    dates: List[str],
    price: float,
    currency: str,
    client: GuestyClient,
    dry_run: bool = False
) -> Dict:
    """Update prices for a single listing.
    
    Returns a dict with operation results.
    """
    result = {
        'listing_id': listing_id,
        'nickname': nickname,
        'status': 'pending',
        'dates_count': len(dates),
        'price': price,
        'error': None,
    }
    
    dates_data = [{'date': d, 'price': price, 'currency': currency} for d in dates]
    data = {'dates': dates_data}
    
    if dry_run:
        result['status'] = 'dry_run'
        return result
    
    try:
        client.api_put(f'listings/{listing_id}/calendar', data)
        result['status'] = 'success'
    except RateLimitError as e:
        result['status'] = 'rate_limited'
        result['error'] = str(e)
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)
    
    return result


def run_block_all(args):
    """Block dates across multiple listings."""
    config = load_config()
    db = get_db()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    # Resolve listings
    listings = _resolve_listings(db, args.listings)
    if not listings:
        print(red("No valid listings found"))
        return
    
    # Validate dates
    try:
        dates = _generate_date_range(args.from_date, args.to_date)
        if not dates:
            print(red("Error: No dates generated"))
            return
    except ValueError as e:
        print(red(f"Invalid date format: {e}. Use YYYY-MM-DD"))
        return
    
    parallel = max(1, min(args.parallel, 10))
    
    print()
    print(bold("Block All Listings"))
    print(f"  Properties: {len(listings)}")
    print(f"  Date range: {dim(args.from_date)} to {dim(args.to_date)} ({len(dates)} days)")
    print(f"  Reason: {args.reason}")
    print(f"  Parallel: {parallel} concurrent calls")
    if args.dry_run:
        print(cyan("  Mode: DRY RUN (no changes will be made)"))
    elif not args.live:
        print(yellow("  Mode: PREVIEW (use --live to apply changes)"))
    else:
        print(green("  Mode: LIVE (changes will be applied)"))
    print()
    
    # Preview
    print("Listings to block:")
    for listing_id, nickname in listings:
        print(f"  • {nickname} ({listing_id})")
    print()
    
    if args.dry_run or not args.live:
        print(cyan("[DRY RUN] No changes made. Use --live to apply."))
        return
    
    # Execute
    client = GuestyClient(config)
    results = []
    completed = 0
    success_count = 0
    error_count = 0
    
    def block_with_progress(listing_tuple: Tuple[str, str]) -> Dict:
        listing_id, nickname = listing_tuple
        nonlocal completed
        result = _block_listing(listing_id, nickname, dates, args.reason, client, dry_run=False)
        completed += 1
        progress_bar = _format_progress_bar(completed, len(listings))
        print(f"\r{progress_bar} {completed}/{len(listings)} {dim(nickname[:30])}", end='', flush=True)
        return result
    
    print("Blocking dates...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = {executor.submit(block_with_progress, listing): listing for listing in listings}
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                results.append(result)
                if result['status'] == 'success':
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                listing = futures[future]
                error_count += 1
                results.append({
                    'listing_id': listing[0],
                    'nickname': listing[1],
                    'status': 'error',
                    'error': str(e),
                })
    
    print()
    print()
    print(bold("Block Complete!"))
    print(f"  Successful: {green(success_count)}")
    print(f"  Errors: {red(error_count) if error_count > 0 else '0'}")
    
    if error_count > 0:
        print()
        print(bold("Errors:"))
        for result in results:
            if result['status'] == 'error':
                print(f"  {red(result['nickname'])}: {result.get('error', 'Unknown error')}")


def run_unblock_all(args):
    """Unblock dates across multiple listings."""
    config = load_config()
    db = get_db()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    # Resolve listings
    listings = _resolve_listings(db, args.listings)
    if not listings:
        print(red("No valid listings found"))
        return
    
    # Validate dates
    try:
        dates = _generate_date_range(args.from_date, args.to_date)
        if not dates:
            print(red("Error: No dates generated"))
            return
    except ValueError as e:
        print(red(f"Invalid date format: {e}. Use YYYY-MM-DD"))
        return
    
    parallel = max(1, min(args.parallel, 10))
    
    print()
    print(bold("Unblock All Listings"))
    print(f"  Properties: {len(listings)}")
    print(f"  Date range: {dim(args.from_date)} to {dim(args.to_date)} ({len(dates)} days)")
    print(f"  Parallel: {parallel} concurrent calls")
    if args.dry_run:
        print(cyan("  Mode: DRY RUN (no changes will be made)"))
    elif not args.live:
        print(yellow("  Mode: PREVIEW (use --live to apply changes)"))
    else:
        print(green("  Mode: LIVE (changes will be applied)"))
    print()
    
    # Preview
    print("Listings to unblock:")
    for listing_id, nickname in listings:
        print(f"  • {nickname} ({listing_id})")
    print()
    
    if args.dry_run or not args.live:
        print(cyan("[DRY RUN] No changes made. Use --live to apply."))
        return
    
    # Execute
    client = GuestyClient(config)
    results = []
    completed = 0
    success_count = 0
    error_count = 0
    
    def unblock_with_progress(listing_tuple: Tuple[str, str]) -> Dict:
        listing_id, nickname = listing_tuple
        nonlocal completed
        result = _unblock_listing(listing_id, nickname, dates, client, dry_run=False)
        completed += 1
        progress_bar = _format_progress_bar(completed, len(listings))
        print(f"\r{progress_bar} {completed}/{len(listings)} {dim(nickname[:30])}", end='', flush=True)
        return result
    
    print("Unblocking dates...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = {executor.submit(unblock_with_progress, listing): listing for listing in listings}
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                results.append(result)
                if result['status'] == 'success':
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                listing = futures[future]
                error_count += 1
                results.append({
                    'listing_id': listing[0],
                    'nickname': listing[1],
                    'status': 'error',
                    'error': str(e),
                })
    
    print()
    print()
    print(bold("Unblock Complete!"))
    print(f"  Successful: {green(success_count)}")
    print(f"  Errors: {red(error_count) if error_count > 0 else '0'}")
    
    if error_count > 0:
        print()
        print(bold("Errors:"))
        for result in results:
            if result['status'] == 'error':
                print(f"  {red(result['nickname'])}: {result.get('error', 'Unknown error')}")


def run_price_all(args):
    """Bulk price updates across multiple listings."""
    config = load_config()
    db = get_db()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    # Resolve listings
    listings = _resolve_listings(db, args.listings)
    if not listings:
        print(red("No valid listings found"))
        return
    
    # Validate dates
    try:
        dates = _generate_date_range(args.from_date, args.to_date)
        if not dates:
            print(red("Error: No dates generated"))
            return
    except ValueError as e:
        print(red(f"Invalid date format: {e}. Use YYYY-MM-DD"))
        return
    
    parallel = max(1, min(args.parallel, 10))
    
    print()
    print(bold("Price Update All Listings"))
    print(f"  Properties: {len(listings)}")
    print(f"  Date range: {dim(args.from_date)} to {dim(args.to_date)} ({len(dates)} days)")
    print(f"  Price: {args.price} {args.currency}")
    print(f"  Parallel: {parallel} concurrent calls")
    if args.dry_run:
        print(cyan("  Mode: DRY RUN (no changes will be made)"))
    elif not args.live:
        print(yellow("  Mode: PREVIEW (use --live to apply changes)"))
    else:
        print(green("  Mode: LIVE (changes will be applied)"))
    print()
    
    # Preview
    print("Listings to update:")
    for listing_id, nickname in listings:
        print(f"  • {nickname} ({listing_id})")
    print()
    
    if args.dry_run or not args.live:
        print(cyan("[DRY RUN] No changes made. Use --live to apply."))
        return
    
    # Execute
    client = GuestyClient(config)
    results = []
    completed = 0
    success_count = 0
    error_count = 0
    
    def price_with_progress(listing_tuple: Tuple[str, str]) -> Dict:
        listing_id, nickname = listing_tuple
        nonlocal completed
        result = _price_listing(listing_id, nickname, dates, args.price, args.currency, client, dry_run=False)
        completed += 1
        progress_bar = _format_progress_bar(completed, len(listings))
        print(f"\r{progress_bar} {completed}/{len(listings)} {dim(nickname[:30])}", end='', flush=True)
        return result
    
    print("Updating prices...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = {executor.submit(price_with_progress, listing): listing for listing in listings}
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                results.append(result)
                if result['status'] == 'success':
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                listing = futures[future]
                error_count += 1
                results.append({
                    'listing_id': listing[0],
                    'nickname': listing[1],
                    'status': 'error',
                    'error': str(e),
                })
    
    print()
    print()
    print(bold("Price Update Complete!"))
    print(f"  Successful: {green(success_count)}")
    print(f"  Errors: {red(error_count) if error_count > 0 else '0'}")
    
    if error_count > 0:
        print()
        print(bold("Errors:"))
        for result in results:
            if result['status'] == 'error':
                print(f"  {red(result['nickname'])}: {result.get('error', 'Unknown error')}")


def _calculate_occupancy(db, listing_id: str, lookback_days: int) -> float:
    """Calculate occupancy rate for a listing over the lookback period.
    
    Returns occupancy percentage (0-100).
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_days)
    
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    cursor = db.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN status = 'reserved' OR status = 'blocked' THEN 1 ELSE 0 END) as occupied
        FROM calendar_days
        WHERE listing_id = ? AND date >= ? AND date <= ?
    """, (listing_id, start_str, end_str))
    
    row = cursor.fetchone()
    if row and row['total'] > 0:
        return (row['occupied'] / row['total']) * 100
    return 50.0  # Default to 50% if no data


def _get_average_price(db, listing_id: str, lookback_days: int) -> float:
    """Get average price from recent calendar data."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_days)
    
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    cursor = db.execute("""
        SELECT AVG(price) as avg_price
        FROM calendar_days
        WHERE listing_id = ? AND date >= ? AND date <= ? AND price IS NOT NULL
    """, (listing_id, start_str, end_str))
    
    row = cursor.fetchone()
    if row and row['avg_price']:
        return float(row['avg_price'])
    return 200.0  # Default fallback


def run_price_dynamic(args):
    """Auto-adjust pricing based on occupancy analysis.
    
    Analyzes historical occupancy and suggests price adjustments.
    Dry-run by default - use --live to apply.
    """
    config = load_config()
    db = get_db()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    # Resolve listing
    listing_id, nickname = _resolve_listing(db, args.listing)
    if not listing_id:
        print(red(f"Listing '{args.listing}' not found in local database"))
        return
    
    # Validate dates
    try:
        dates = _generate_date_range(args.from_date, args.to_date)
        if not dates:
            print(red("Error: No dates generated"))
            return
    except ValueError as e:
        print(red(f"Invalid date format: {e}. Use YYYY-MM-DD"))
        return
    
    # Calculate occupancy
    occupancy = _calculate_occupancy(db, listing_id, args.lookback_days)
    
    # Determine base price
    if args.base_price:
        base_price = args.base_price
    else:
        base_price = _get_average_price(db, listing_id, args.lookback_days)
    
    # Determine price adjustment based on occupancy
    if occupancy < args.low_occupancy_threshold:
        # Low occupancy - decrease price
        adjustment_pct = -args.decrease_percent
        strategy = "Low occupancy - decreasing prices"
    elif occupancy > args.high_occupancy_threshold:
        # High occupancy - increase price
        adjustment_pct = args.increase_percent
        strategy = "High occupancy - increasing prices"
    else:
        # Medium occupancy - keep base price
        adjustment_pct = 0
        strategy = "Medium occupancy - maintaining base price"
    
    # Calculate new price
    new_price = base_price * (1 + adjustment_pct / 100)
    
    # Apply min/max constraints
    if args.min_price is not None:
        new_price = max(new_price, args.min_price)
    if args.max_price is not None:
        new_price = min(new_price, args.max_price)
    
    new_price = round(new_price, 2)
    
    print()
    print(bold(f"Dynamic Pricing Analysis: {nickname}"))
    print()
    print(bold("Occupancy Analysis:"))
    print(f"  Historical occupancy ({args.lookback_days} days): {occupancy:.1f}%")
    print(f"  Low threshold: {args.low_occupancy_threshold}%")
    print(f"  High threshold: {args.high_occupancy_threshold}%")
    print()
    print(bold("Pricing Strategy:"))
    print(f"  {strategy}")
    print(f"  Base price: ${base_price:.2f}")
    print(f"  Adjustment: {adjustment_pct:+.0f}%")
    print(f"  Suggested price: ${new_price:.2f}")
    if args.min_price:
        print(f"  Min price floor: ${args.min_price:.2f}")
    if args.max_price:
        print(f"  Max price ceiling: ${args.max_price:.2f}")
    print()
    print(bold("Date Range:"))
    print(f"  {args.from_date} to {args.to_date} ({len(dates)} days)")
    print()
    
    if args.dry_run or not args.live:
        print(cyan("[DRY RUN] No changes made. Use --live to apply suggested pricing."))
        print()
        print("Would update prices to:")
        print(f"  ${new_price:.2f} for {len(dates)} days")
        return
    
    # Apply pricing
    print(green("Applying dynamic pricing..."))
    print()
    
    client = GuestyClient(config)
    dates_data = [{'date': d, 'price': new_price, 'currency': 'USD'} for d in dates]
    data = {'dates': dates_data}
    
    try:
        client.api_put(f'listings/{listing_id}/calendar', data)
        print(green(f"✓ Updated price to ${new_price:.2f} for {len(dates)} days on '{nickname}'"))
        print(f"  Occupancy: {occupancy:.1f}% | Strategy: {strategy}")
    except Exception as e:
        print(red(f"Error updating prices: {e}"))


# ============ CALENDAR SYNC FUNCTIONS ============

def _get_all_listings(db) -> List[Dict]:
    """Get all active listings from the database."""
    cursor = db.execute(
        "SELECT id, nickname FROM listings WHERE status = 'ACTIVE' OR status IS NULL ORDER BY nickname"
    )
    return [dict(row) for row in cursor.fetchall()]


def _decode_block_flags(flags: str) -> List[str]:
    """Decode block flags string into human-readable list.
    
    Example: "m,r" -> ["manual", "reservation"]
    """
    if not flags:
        return []
    
    decoded = []
    for flag in flags.split(','):
        flag = flag.strip()
        if flag in BLOCK_FLAG_DECODER:
            decoded.append(BLOCK_FLAG_DECODER[flag])
        else:
            decoded.append(f"unknown({flag})")
    
    return decoded


def _parse_calendar_day(day_data: dict, listing_id: str) -> Optional[Dict]:
    """Parse a single calendar day from API response into DB format.
    
    Returns None if the data is invalid.
    """
    date_str = day_data.get('date')
    if not date_str:
        return None
    
    # Determine status based on various fields
    status = 'available'
    if day_data.get('blocked', False):
        status = 'blocked'
    elif day_data.get('reservationId'):
        status = 'reserved'
    elif day_data.get('status') == 'blocked':
        status = 'blocked'
    elif day_data.get('status') == 'reserved':
        status = 'reserved'
    
    # Decode block reasons/flags
    block_flags = []
    if day_data.get('blockFlags'):
        block_flags = _decode_block_flags(day_data['blockFlags'])
    elif day_data.get('blockReason'):
        block_flags = [day_data['blockReason']]
    
    # Build the calendar day record
    record = {
        'id': f"{listing_id}_{date_str}",
        'listing_id': listing_id,
        'date': date_str,
        'status': status,
        'price': day_data.get('price'),
        'minimum_stay': day_data.get('minNights') or day_data.get('minimumStay'),
        'maximum_stay': day_data.get('maxNights') or day_data.get('maximumStay'),
        'reservation_id': day_data.get('reservationId'),
        'updated_at': datetime.now().isoformat(),
        'raw_data': json.dumps(day_data),
    }
    
    return record


def _upsert_calendar_days(db, records: List[Dict]) -> int:
    """Upsert calendar day records into the database.
    
    Returns the number of records upserted.
    """
    cursor = db.cursor()
    count = 0
    
    for record in records:
        if not record:
            continue
            
        cursor.execute("""
            INSERT OR REPLACE INTO calendar_days (
                id, listing_id, date, status, price, minimum_stay, maximum_stay,
                reservation_id, updated_at, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record['id'],
            record['listing_id'],
            record['date'],
            record['status'],
            record['price'],
            record['minimum_stay'],
            record['maximum_stay'],
            record['reservation_id'],
            record['updated_at'],
            record['raw_data'],
        ))
        count += 1
    
    db.commit()
    return count


def _sync_single_listing(
    listing_id: str,
    nickname: str,
    from_date: str,
    to_date: str,
    client: GuestyClient,
    dry_run: bool = False,
) -> Dict:
    """Sync calendar for a single listing.
    
    Returns a dict with sync results.
    """
    result = {
        'listing_id': listing_id,
        'nickname': nickname,
        'from_date': from_date,
        'to_date': to_date,
        'days_fetched': 0,
        'days_stored': 0,
        'status': 'pending',
        'error': None,
        'duration_seconds': 0,
    }
    
    start_time = time.time()
    
    try:
        # Fetch calendar from API
        calendar_data = client.api_get(
            f'listings/{listing_id}/calendar',
            {'from': from_date, 'to': to_date}
        )
        
        # Handle different response formats
        days = calendar_data if isinstance(calendar_data, list) else calendar_data.get('days', [])
        result['days_fetched'] = len(days)
        
        if dry_run:
            result['status'] = 'dry_run'
            result['duration_seconds'] = time.time() - start_time
            return result
        
        # Parse and upsert into database
        db = get_db()
        records = [_parse_calendar_day(day, listing_id) for day in days]
        records = [r for r in records if r is not None]
        
        stored_count = _upsert_calendar_days(db, records)
        result['days_stored'] = stored_count
        result['status'] = 'success'
        
    except RateLimitError as e:
        result['status'] = 'rate_limited'
        result['error'] = str(e)
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)
    
    result['duration_seconds'] = time.time() - start_time
    return result


def _format_progress_bar(current: int, total: int, width: int = 40) -> str:
    """Format a progress bar string."""
    if total == 0:
        return "[" + " " * width + "] 0%"
    
    percent = current / total
    filled = int(width * percent)
    empty = width - filled
    
    bar = "█" * filled + "░" * empty
    return f"[{bar}] {int(percent * 100)}%"


def run_sync(args):
    """Sync calendar for a single listing."""
    config = load_config()
    db = get_db()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    # Resolve listing
    listing_id, nickname = _resolve_listing(db, args.listing)
    if not listing_id:
        print(red(f"Listing '{args.listing}' not found in local database"))
        print(yellow("Run 'guesty sync listings' to refresh the listings database."))
        return
    
    # Validate dates
    try:
        from_dt = datetime.strptime(args.from_date, '%Y-%m-%d')
        to_dt = datetime.strptime(args.to_date, '%Y-%m-%d')
        if from_dt > to_dt:
            print(red("Error: --from date must be before or equal to --to date"))
            return
    except ValueError:
        print(red("Error: Invalid date format. Use YYYY-MM-DD"))
        return
    
    print()
    print(bold(f"Syncing calendar for: {nickname}"))
    print(f"  Date range: {dim(args.from_date)} to {dim(args.to_date)}")
    if args.dry_run:
        print(cyan("  Mode: DRY RUN (no data will be stored)"))
    print()
    
    # Perform sync
    client = GuestyClient(config)
    result = _sync_single_listing(
        listing_id, nickname,
        args.from_date, args.to_date,
        client, dry_run=args.dry_run
    )
    
    if args.json:
        print_json(result)
        return
    
    # Print results
    if result['status'] == 'success':
        print(green(f"✓ Synced {result['days_stored']} days"))
        print(f"  Fetched: {result['days_fetched']} days from API")
        print(f"  Duration: {result['duration_seconds']:.2f}s")
    elif result['status'] == 'dry_run':
        print(cyan(f"[DRY RUN] Would fetch {result['days_fetched']} days"))
        print(f"  Duration: {result['duration_seconds']:.2f}s")
    elif result['status'] == 'rate_limited':
        print(red(f"✗ Rate limited: {result['error']}"))
    else:
        print(red(f"✗ Error: {result['error']}"))


def run_sync_all(args):
    """Sync calendar for all listings with parallel processing."""
    config = load_config()
    db = get_db()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    # Get all listings
    listings = _get_all_listings(db)
    if not listings:
        print(red("No listings found in local database"))
        print(yellow("Run 'guesty sync listings' to refresh the listings database."))
        return
    
    # Validate dates
    try:
        from_dt = datetime.strptime(args.from_date, '%Y-%m-%d')
        to_dt = datetime.strptime(args.to_date, '%Y-%m-%d')
        if from_dt > to_dt:
            print(red("Error: --from date must be before or equal to --to date"))
            return
        
        # Calculate total days being synced
        total_days = (to_dt - from_dt).days + 1
    except ValueError:
        print(red("Error: Invalid date format. Use YYYY-MM-DD"))
        return
    
    parallel = max(1, min(args.parallel, 10))  # Clamp between 1 and 10
    
    print()
    print(bold("Calendar Sync All"))
    print(f"  Properties: {len(listings)}")
    print(f"  Date range: {dim(args.from_date)} to {dim(args.to_date)} ({total_days} days per property)")
    print(f"  Parallel: {parallel} concurrent calls")
    if args.dry_run:
        print(cyan("  Mode: DRY RUN (no data will be stored)"))
    print()
    
    # Track overall stats
    start_time = time.time()
    results = []
    completed = 0
    success_count = 0
    error_count = 0
    rate_limited_count = 0
    total_days_fetched = 0
    total_days_stored = 0
    
    # Create shared client for rate limit tracking
    client = GuestyClient(config)
    
    def sync_with_progress(listing: Dict) -> Dict:
        """Sync a single listing and update progress."""
        nonlocal completed
        result = _sync_single_listing(
            listing['id'],
            listing['nickname'],
            args.from_date,
            args.to_date,
            client,
            dry_run=args.dry_run
        )
        completed += 1
        
        # Print progress
        progress_bar = _format_progress_bar(completed, len(listings))
        print(f"\r{progress_bar} {completed}/{len(listings)} {dim(listing['nickname'][:30])}", end='', flush=True)
        
        return result
    
    print("Starting sync...")
    
    # Execute parallel sync with ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = {executor.submit(sync_with_progress, listing): listing for listing in listings}
        
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                results.append(result)
                
                if result['status'] == 'success':
                    success_count += 1
                    total_days_fetched += result['days_fetched']
                    total_days_stored += result['days_stored']
                elif result['status'] == 'rate_limited':
                    rate_limited_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                listing = futures[future]
                error_count += 1
                results.append({
                    'listing_id': listing['id'],
                    'nickname': listing['nickname'],
                    'status': 'error',
                    'error': str(e),
                })
    
    # Clear the progress line
    print()
    print()
    
    total_duration = time.time() - start_time
    
    # Print summary
    if args.json:
        summary = {
            'total_properties': len(listings),
            'successful': success_count,
            'errors': error_count,
            'rate_limited': rate_limited_count,
            'total_days_fetched': total_days_fetched,
            'total_days_stored': total_days_stored,
            'total_duration_seconds': round(total_duration, 2),
            'properties_per_second': round(len(listings) / total_duration, 2) if total_duration > 0 else 0,
            'results': results,
        }
        print_json(summary)
        return
    
    # Print formatted summary
    print(bold("Sync Complete!"))
    print()
    
    # Performance metrics table
    headers = ['Metric', 'Value']
    rows = [
        ['Properties', len(listings)],
        ['Successful', green(success_count)],
        ['Errors', red(error_count) if error_count > 0 else '0'],
        ['Rate Limited', yellow(rate_limited_count) if rate_limited_count > 0 else '0'],
        ['Total Days Fetched', total_days_fetched],
        ['Total Days Stored', total_days_stored if not args.dry_run else cyan('(dry run)')],
        ['Total Duration', f"{total_duration:.2f}s"],
        ['Properties/sec', f"{len(listings) / total_duration:.2f}" if total_duration > 0 else "N/A"],
        ['Avg per Property', f"{total_duration / len(listings):.2f}s" if listings else "N/A"],
    ]
    
    print_table(headers, rows)
    
    # Show errors if any
    if error_count > 0 or rate_limited_count > 0:
        print()
        print(bold("Issues:"))
        for result in results:
            if result['status'] in ('error', 'rate_limited'):
                status_color = yellow if result['status'] == 'rate_limited' else red
                print(f"  {status_color(result['nickname'])}: {result.get('error', 'Unknown error')}")
