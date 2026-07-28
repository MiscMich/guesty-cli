"""
Status dashboard command for guesty-cli.
"""
import sqlite3
from datetime import datetime, timedelta
from guesty_cli import __version__
from guesty_cli.core.config import load_config
from guesty_cli.core.database import get_db, get_sync_status
from guesty_cli.core.client import GuestyClient
from guesty_cli.core.output import (
    print_banner, print_header, print_stats, format_money_short,
    bold, cyan, green, red, yellow, dim, bright_blue
)


def register(subparsers):
    """Register status command with the argument parser."""
    parser = subparsers.add_parser(
        'status',
        help='Show dashboard overview'
    )
    parser.set_defaults(func=run)
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output as JSON'
    )


def run(args):
    """Display dashboard overview."""
    config = load_config()
    
    # Check if configured
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    db = get_db()
    
    # Gather all status data
    status_data = {}
    
    # Record counts per table
    tables = ['listings', 'reservations', 'guests', 'owners', 'reviews', 'tasks', 'financials', 'webhooks']
    record_counts = {}
    for table in tables:
        try:
            cursor = db.execute(f"SELECT COUNT(*) FROM {table}")
            record_counts[table] = cursor.fetchone()[0]
        except:
            record_counts[table] = 0
    status_data['record_counts'] = record_counts
    
    # Last sync info
    sync_status = {}
    try:
        sync_info = get_sync_status(db)
        for table in tables:
            if table in sync_info:
                sync_status[table] = sync_info[table]
            else:
                sync_status[table] = {'timestamp': None, 'records_synced': 0}
    except:
        for table in tables:
            sync_status[table] = {'timestamp': None, 'records_synced': 0}
    status_data['sync_status'] = sync_status
    
    # Token status
    token_status = {'valid': False, 'hours_remaining': 0}
    try:
        # Check auth_tokens table first. It is optional — older databases (and any
        # created by init_db) have no such table, in which case fall through to the
        # token cached in config rather than reporting the token as invalid.
        token_row = None
        try:
            cursor = db.execute("SELECT token, expires_at FROM auth_tokens ORDER BY created_at DESC LIMIT 1")
            token_row = cursor.fetchone()
        except sqlite3.Error:
            pass

        if token_row:
            expires_at = token_row[1]
            if expires_at:
                try:
                    expires = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    now = datetime.now(expires.tzinfo) if expires.tzinfo else datetime.now()
                    hours_remaining = (expires - now).total_seconds() / 3600
                    token_status = {
                        'valid': hours_remaining > 0,
                        'hours_remaining': max(0, hours_remaining),
                        'expires_at': expires_at
                    }
                except Exception:
                    pass
        
        # Fall back to config if no DB token found
        if not token_status['valid']:
            client = GuestyClient(config)
            expires_at = config.get('token_expires_at')
            cached_token = config.get('token')

            if cached_token and expires_at:
                try:
                    expires = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    now = datetime.now(expires.tzinfo) if expires.tzinfo else datetime.now()
                    hours_remaining = (expires - now).total_seconds() / 3600
                    token_status = {
                        'valid': hours_remaining > 0,
                        'hours_remaining': max(0, hours_remaining),
                        'expires_at': expires_at
                    }
                except Exception:
                    pass
    except:
        pass
    status_data['token_status'] = token_status
    
    # Today's check-ins/check-outs
    today = datetime.now().strftime('%Y-%m-%d')
    today_stats = {'checkins': 0, 'checkouts': 0}
    try:
        # Match on the date part of check_in/check_out, which are stored as full
        # ISO timestamps (2026-07-28T20:00:00.000Z).
        cursor = db.execute(
            "SELECT COUNT(*) FROM reservations WHERE check_in LIKE ? AND status = 'confirmed'",
            (f'{today}%',)
        )
        today_stats['checkins'] = cursor.fetchone()[0]

        cursor = db.execute(
            "SELECT COUNT(*) FROM reservations WHERE check_out LIKE ? AND status = 'confirmed'",
            (f'{today}%',)
        )
        today_stats['checkouts'] = cursor.fetchone()[0]
    except sqlite3.Error:
        pass
    status_data['today_stats'] = today_stats
    
    # Active vs inactive listings
    listing_stats = {'active': 0, 'inactive': 0}
    try:
        cursor = db.execute("SELECT COUNT(*) FROM listings WHERE active = 1")
        listing_stats['active'] = cursor.fetchone()[0]
        cursor = db.execute("SELECT COUNT(*) FROM listings WHERE active = 0 OR active IS NULL")
        listing_stats['inactive'] = cursor.fetchone()[0]
    except:
        pass
    status_data['listing_stats'] = listing_stats
    
    # Output
    if args.json:
        from guesty_cli.core.output import print_json
        print_json(status_data)
        return
    
    # Print dashboard
    print_banner(version=__version__)
    print_header(f"Dashboard - {config.get('account_name', 'Guesty Account')}", emoji="📊")
    
    # Key metrics stat boxes
    stats = [
        {'value': listing_stats['active'], 'label': 'Listings'},
        {'value': record_counts.get('guests', 0), 'label': 'Guests'},
        {'value': record_counts.get('reviews', 0), 'label': 'Reviews'},
        {'value': record_counts.get('reservations', 0), 'label': 'Reservations'},
    ]
    print_stats(stats)
    
    # Token status section
    print_header("Authentication", emoji="🔐")
    if token_status['valid']:
        hours = token_status['hours_remaining']
        if hours > 4:
            status_text = green(f"✓ Valid ({hours:.1f}h remaining)")
        elif hours > 1:
            status_text = yellow(f"⚠ Valid ({hours:.1f}h remaining)")
        else:
            status_text = red(f"⚠ Expiring soon ({hours:.1f}h remaining)")
    else:
        status_text = red("✗ Invalid/Expired")
    print(f"  Token: {status_text}")
    print()
    
    # Today's activity
    print_header("Today's Activity", emoji="📅")
    print(f"  Check-ins:  {green(str(today_stats['checkins']))}")
    print(f"  Check-outs: {green(str(today_stats['checkouts']))}")
    print()
    
    # Listings overview
    print_header("Listings Overview", emoji="🏠")
    print(f"  Active:   {green(str(listing_stats['active']))}")
    print(f"  Inactive: {dim(str(listing_stats['inactive']))}")
    print(f"  Total:    {listing_stats['active'] + listing_stats['inactive']}")
    print()
    
    # Database summary
    print_header("Local Database", emoji="💾")
    for table, count in record_counts.items():
        sync_info = sync_status.get(table, {})
        last_sync = sync_info.get('timestamp')
        if last_sync:
            last_sync_str = dim(f"(synced {last_sync})")
        else:
            last_sync_str = dim("(never synced)")
        print(f"  {table:15s} {count:>6,d} {last_sync_str}")
    print()
    
    print(dim("Run 'guesty sync' to update data from Guesty API"))
