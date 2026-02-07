"""
Data synchronization commands for guesty-cli.
"""
import time
from datetime import datetime
from guesty_cli.core.config import load_config
from guesty_cli.core.database import get_db, get_sync_status, log_sync
from guesty_cli.core.client import GuestyClient
from guesty_cli.core.output import (
    print_table, print_json, bold, green, red, yellow, dim
)


def register(subparsers):
    """Register sync commands with the argument parser."""
    parser = subparsers.add_parser(
        'sync',
        help='Sync data from Guesty API to local database'
    )
    parser.set_defaults(func=run_sync)
    parser.add_argument('endpoint', nargs='?', help='Endpoint to sync (listings, reservations, guests, owners, reviews, tasks, financials, webhooks) or "full"')
    parser.add_argument('--full', action='store_true', help='Full sync of all endpoints')
    parser.add_argument('--status', action='store_true', help='Show sync status')
    parser.add_argument('--history', action='store_true', help='Show sync history')


def run(args):
    """Route to appropriate subcommand handler."""
    pass


def run_sync(args):
    """Run synchronization."""
    config = load_config()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    # Show status
    if args.status:
        show_sync_status()
        return
    
    # Show history
    if args.history:
        show_sync_history()
        return
    
    # Determine endpoints to sync
    endpoints = {
        'listings': {'path': 'listings', 'table': 'listings'},
        'reservations': {'path': 'reservations', 'table': 'reservations'},
        'guests': {'path': 'guests', 'table': 'guests'},
        'owners': {'path': 'owners', 'table': 'owners'},
        'reviews': {'path': 'reviews', 'table': 'reviews'},
        'tasks': {'path': 'tasks', 'table': 'tasks'},
        'financials': {'path': 'financials', 'table': 'financials'},
        'webhooks': {'path': 'webhooks', 'table': 'webhooks'},
    }
    
    if args.full or args.endpoint in (None, 'full', 'all'):
        to_sync = list(endpoints.keys())
        print(bold("Starting full sync..."))
    elif args.endpoint in endpoints:
        to_sync = [args.endpoint]
        print(bold(f"Starting sync for {args.endpoint}..."))
    else:
        print(red(f"Unknown endpoint: {args.endpoint}"))
        print(f"Available: {', '.join(endpoints.keys())}")
        return
    
    print()
    
    client = GuestyClient(config)
    db = get_db()
    
    results = []
    
    for endpoint in to_sync:
        info = endpoints[endpoint]
        start_time = time.time()
        
        print(f"Syncing {endpoint}...", end=' ', flush=True)
        
        try:
            # Fetch data
            if endpoint in ['owners', 'webhooks']:
                # These return raw arrays
                data = client.api_get(info['path'])
                records = data if isinstance(data, list) else data.get('results', [])
            elif endpoint == 'reviews':
                # Reviews uses different format
                data = client.api_get_all(info['path'], {})
                records = data if isinstance(data, list) else data.get('data', [])
            elif endpoint == 'reservations':
                # Request all important fields for reservations
                records = client.api_get_all(info['path'], {
                    'fields': 'confirmationCode status source checkIn checkOut checkInDateLocalized checkOutDateLocalized listingId guestId guest.firstName guest.lastName guest.fullName guest.email guest.phone money.hostPayout money.totalPaid money.balanceDue money.currency nightsCount guestsCount createdAt confirmedAt'
                })
            else:
                records = client.api_get_all(info['path'], {})
            
            # Get existing columns for this table
            cursor = db.execute(f"PRAGMA table_info({info['table']})")
            existing_cols = {row[1] for row in cursor.fetchall()}
            
            # Clear and insert
            db.execute(f"DELETE FROM {info['table']}")
            
            for record in records:
                # Map API record to DB columns
                row_data = _map_record_to_db(record, info['table'], existing_cols)
                if not row_data:
                    continue
                
                columns = list(row_data.keys())
                placeholders = ', '.join('?' for _ in columns)
                
                try:
                    db.execute(
                        f"INSERT OR REPLACE INTO {info['table']} ({', '.join(columns)}) VALUES ({placeholders})",
                        list(row_data.values())
                    )
                except Exception:
                    pass
            
            db.commit()
            
            duration = time.time() - start_time
            log_sync(db, endpoint, len(records), duration, 'success')
            
            print(green(f"✓ {len(records)} records ({duration:.1f}s)"))
            results.append({'endpoint': endpoint, 'records': len(records), 'status': 'success'})
            
        except Exception as e:
            duration = time.time() - start_time
            log_sync(db, endpoint, 0, duration, 'error', str(e))
            
            print(red(f"✗ Error: {e}"))
            results.append({'endpoint': endpoint, 'records': 0, 'status': 'error', 'error': str(e)})
    
    print()
    print(green("Sync complete!"))


def _map_record_to_db(record, table, existing_cols):
    """Map a Guesty API record to existing DB columns."""
    import json
    
    row = {}
    rid = record.get('_id') or record.get('id')
    if not rid:
        return None
    row['id'] = rid
    
    # Store raw JSON
    if 'raw_json' in existing_cols:
        row['raw_json'] = json.dumps(record)
    elif 'raw_data' in existing_cols:
        row['raw_data'] = json.dumps(record)
    
    # Direct match: any key that exists as a column
    for key, value in record.items():
        if key == '_id':
            continue
        if key in existing_cols:
            if isinstance(value, (dict, list)):
                row[key] = json.dumps(value)
            else:
                row[key] = value
    
    # Special mappings per table
    if table == 'listings':
        addr = record.get('address', {})
        if isinstance(addr, dict):
            for k in ('city', 'state', 'zipcode', 'country'):
                if k in existing_cols:
                    row[k] = addr.get(k)
            if 'address' in existing_cols and isinstance(addr.get('full'), str):
                row['address'] = addr.get('full')
        if 'maxGuests' in existing_cols:
            row['maxGuests'] = record.get('accommodates')
        if 'active' in existing_cols:
            row['active'] = 1 if record.get('active', True) else 0
    
    elif table == 'reservations':
        guest = record.get('guest', {})
        if isinstance(guest, dict):
            if 'guestId' in existing_cols:
                row['guestId'] = guest.get('_id')
            if 'guestName' in existing_cols:
                name = f"{guest.get('firstName', '')} {guest.get('lastName', '')}".strip()
                if name:
                    row['guestName'] = name
            if 'guestEmail' in existing_cols:
                row['guestEmail'] = guest.get('email')
            if 'guestPhone' in existing_cols:
                row['guestPhone'] = guest.get('phone')
        money = record.get('money', {})
        if isinstance(money, dict):
            if 'totalPrice' in existing_cols:
                row['totalPrice'] = money.get('hostPayout', 0)
            if 'payoutAmount' in existing_cols:
                row['payoutAmount'] = money.get('hostPayout', 0)
            if 'balanceDue' in existing_cols:
                row['balanceDue'] = money.get('balanceDue', 0)
    
    elif table == 'guests':
        if 'fullName' in existing_cols:
            row['fullName'] = f"{record.get('firstName', '')} {record.get('lastName', '')}".strip()
    
    elif table == 'owners':
        if 'isActive' in existing_cols:
            row['isActive'] = 1 if record.get('active', True) else 0
    
    elif table == 'reviews':
        raw_review = record.get('rawReview', {})
        if isinstance(raw_review, dict):
            if 'rating' in existing_cols:
                row['rating'] = raw_review.get('overall_rating')
            if 'content' in existing_cols:
                row['content'] = raw_review.get('public_review')
            if 'response' in existing_cols:
                row['response'] = raw_review.get('reviewee_response')
        if 'reviewerName' in existing_cols:
            row['reviewerName'] = record.get('reviewerName') or (record.get('reviewer', {}) or {}).get('name')
        if 'platform' in existing_cols:
            row['platform'] = record.get('channelId')
    
    return row


def show_sync_status():
    """Show last sync status for all endpoints."""
    endpoints = ['listings', 'reservations', 'guests', 'owners', 'reviews', 'tasks', 'financials', 'webhooks']
    
    db = get_db()
    headers = ['Endpoint', 'Last Sync', 'Records']
    rows = []
    for endpoint in endpoints:
        try:
            cursor = db.execute(
                """SELECT timestamp, records_synced 
                   FROM sync_log 
                   WHERE endpoint = ?
                   ORDER BY timestamp DESC LIMIT 1""",
                (endpoint,)
            )
            row = cursor.fetchone()
            
            if row:
                last_sync = row['timestamp']
                count = row['records_synced']
                
                # Calculate time since last sync
                try:
                    sync_time = datetime.fromisoformat(last_sync.replace('Z', '+00:00'))
                    from datetime import timezone
                    now = datetime.now(timezone.utc)
                    delta = now - sync_time
                    if delta.days > 0:
                        ago = f"{delta.days}d ago"
                    elif delta.seconds > 3600:
                        ago = f"{delta.seconds // 3600}h ago"
                    else:
                        ago = f"{delta.seconds // 60}m ago"
                except:
                    ago = last_sync[:16]
            else:
                ago = 'Never'
                count = 0
            
            rows.append([endpoint, ago, count])
        except Exception as e:
            rows.append([endpoint, 'Error', 0])
    
    print(f"\n{bold('Sync Status')}")
    print_table(headers, rows)


def show_sync_history():
    """Show sync history log."""
    db = get_db()
    
    try:
        cursor = db.execute(
            """SELECT * FROM sync_log 
               ORDER BY timestamp DESC 
               LIMIT 20"""
        )
        rows = cursor.fetchall()
    except Exception as e:
        print(f"Error reading sync log: {e}")
        return
    
    if not rows:
        print("No sync history found")
        return
    
    headers = ['Time', 'Endpoint', 'Records', 'Duration', 'Status']
    data = []
    for row in rows:
        data.append([
            row['timestamp'][:16] if row['timestamp'] else 'N/A',
            row['endpoint'],
            row['records_synced'],
            f"{row['duration_seconds']:.1f}s",
            green('✓') if row['status'] == 'success' else red('✗'),
        ])
    
    print(f"\n{bold('Sync History (last 20)')}")
    print_table(headers, data)
