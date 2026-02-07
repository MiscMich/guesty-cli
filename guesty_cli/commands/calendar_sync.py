"""Calendar sync commands for guesty-cli.

Simple focused calendar sync - just 2 commands:
1. guesty calendar sync-all --from DATE --to DATE
2. guesty calendar sync <listing_name> --from DATE --to DATE
"""
import json
import time
from datetime import datetime
from typing import Dict, List, Optional

from guesty_cli.core.config import load_config
from guesty_cli.core.database import get_db
from guesty_cli.core.client import GuestyClient
from guesty_cli.core.output import (
    bold, cyan, green, red, yellow, dim, print_json
)


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


def _parse_calendar_day(day_data: dict, listing_id: str) -> Optional[Dict]:
    """Parse a single calendar day from API response into DB format."""
    date_str = day_data.get('date')
    if not date_str:
        return None
    
    # Determine status
    status = 'available'
    if day_data.get('blocked', False):
        status = 'blocked'
    elif day_data.get('reservationId'):
        status = 'reserved'
    
    # Build the calendar day record
    record = {
        'id': f"{listing_id}_{date_str}",
        'listing_id': listing_id,
        'date': date_str,
        'status': status,
        'price': day_data.get('price'),
        'min_stay': day_data.get('minNights') or day_data.get('minimumStay'),
        'reservation_id': day_data.get('reservationId'),
        'raw_data': json.dumps(day_data),
    }
    
    return record


def _upsert_calendar_days(db, records: List[Dict]) -> int:
    """Upsert calendar day records into the database."""
    cursor = db.cursor()
    count = 0
    
    for record in records:
        if not record:
            continue
        
        cursor.execute("""
            INSERT OR REPLACE INTO calendar_days (
                id, listing_id, date, status, price, min_stay,
                reservation_id, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record['id'],
            record['listing_id'],
            record['date'],
            record['status'],
            record['price'],
            record['min_stay'],
            record['reservation_id'],
            record['raw_data'],
        ))
        count += 1
    
    db.commit()
    return count


def run_sync(args):
    """Sync calendar for a single listing by name."""
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
    print(bold(f"Syncing calendar: {nickname}"))
    print(f"  Date range: {dim(args.from_date)} to {dim(args.to_date)}")
    if args.dry_run:
        print(cyan("  Mode: DRY RUN (no data will be stored)"))
    print()
    
    # Fetch from API
    client = GuestyClient(config)
    
    try:
        start_time = time.time()
        
        # Fetch calendar from API
        calendar_data = client.api_get(
            f'listings/{listing_id}/calendar',
            {'from': args.from_date, 'to': args.to_date}
        )
        
        # Handle different response formats
        days = calendar_data if isinstance(calendar_data, list) else calendar_data.get('days', [])
        days_fetched = len(days)
        
        if args.dry_run:
            print(cyan(f"[DRY RUN] Would fetch and store {days_fetched} days"))
            print(f"  Duration: {time.time() - start_time:.2f}s")
            return
        
        # Parse and upsert into database
        records = [_parse_calendar_day(day, listing_id) for day in days]
        records = [r for r in records if r is not None]
        days_stored = _upsert_calendar_days(db, records)
        
        duration = time.time() - start_time
        
        print(green(f"✓ Synced {days_stored} days"))
        print(f"  Fetched: {days_fetched} days from API")
        print(f"  Duration: {duration:.2f}s")
        
    except Exception as e:
        print(red(f"✗ Error: {e}"))


def run_sync_all(args):
    """Sync calendar for all listings."""
    config = load_config()
    db = get_db()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    # Get all listings
    cursor = db.execute("SELECT id, nickname FROM listings ORDER BY nickname")
    listings = [dict(row) for row in cursor.fetchall()]
    
    if not listings:
        print(red("No listings found in local database"))
        print(yellow("Run 'guesty sync listings' to refresh the listings database."))
        return
    
    total_listings = len(listings)
    
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
    print(bold("Calendar Sync All"))
    print(f"  Properties: {total_listings}")
    print(f"  Date range: {dim(args.from_date)} to {dim(args.to_date)}")
    if args.dry_run:
        print(cyan("  Mode: DRY RUN (no data will be stored)"))
    print()
    
    # Track stats
    total_days_fetched = 0
    total_days_stored = 0
    errors = []
    
    client = GuestyClient(config)
    
    for idx, listing in enumerate(listings, 1):
        listing_id = listing['id']
        nickname = listing['nickname']
        
        # Show simple progress
        print(f"Syncing {idx}/{total_listings}... {dim(nickname)}", end='', flush=True)
        
        try:
            # Fetch calendar from API
            calendar_data = client.api_get(
                f'listings/{listing_id}/calendar',
                {'from': args.from_date, 'to': args.to_date}
            )
            
            days = calendar_data if isinstance(calendar_data, list) else calendar_data.get('days', [])
            days_fetched = len(days)
            total_days_fetched += days_fetched
            
            if not args.dry_run:
                # Parse and upsert into database
                records = [_parse_calendar_day(day, listing_id) for day in days]
                records = [r for r in records if r is not None]
                days_stored = _upsert_calendar_days(db, records)
                total_days_stored += days_stored
            
            print(f" \033[32m✓ {days_fetched} days\033[0m")
            
        except Exception as e:
            print(f" \033[31m✗ {e}\033[0m")
            errors.append((nickname, str(e)))
    
    print()
    print(bold("Sync Complete!"))
    print(f"  Total properties: {total_listings}")
    print(f"  Total days fetched: {total_days_fetched}")
    if not args.dry_run:
        print(f"  Total days stored: {total_days_stored}")
    print(f"  Errors: {len(errors)}")
    
    if errors:
        print()
        print(bold("Errors:"))
        for nickname, error in errors:
            print(f"  {red(nickname)}: {error}")


def register(subparsers):
    """Register calendar sync commands with the argument parser."""
    # guesty calendar (main command)
    calendar_parser = subparsers.add_parser(
        'calendar',
        help='Calendar sync operations'
    )
    calendar_subparsers = calendar_parser.add_subparsers(dest='calendar_action')
    
    # Sync single listing
    sync_parser = calendar_subparsers.add_parser('sync', help='Sync calendar for a single listing')
    sync_parser.add_argument('listing', help='Listing ID or nickname')
    sync_parser.add_argument('--from', dest='from_date', type=str, required=True,
                            help='Start date (YYYY-MM-DD)')
    sync_parser.add_argument('--to', dest='to_date', type=str, required=True,
                            help='End date (YYYY-MM-DD)')
    sync_parser.add_argument('--dry-run', action='store_true',
                            help='Show what would be synced without storing')
    sync_parser.set_defaults(func=run_sync)
    
    # Sync all listings
    sync_all_parser = calendar_subparsers.add_parser('sync-all', help='Sync calendar for all listings')
    sync_all_parser.add_argument('--from', dest='from_date', type=str, required=True,
                                 help='Start date (YYYY-MM-DD)')
    sync_all_parser.add_argument('--to', dest='to_date', type=str, required=True,
                                 help='End date (YYYY-MM-DD)')
    sync_all_parser.add_argument('--dry-run', action='store_true',
                                 help='Show what would be synced without storing')
    sync_all_parser.set_defaults(func=run_sync_all)
