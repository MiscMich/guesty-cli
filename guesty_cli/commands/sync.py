"""Data synchronization commands for guesty-cli."""
import json
import time
from datetime import datetime, timezone
from guesty_cli.core.config import load_config
from guesty_cli.core.database import (
    get_db, get_sync_status, log_sync,
    upsert_invoice_items, upsert_tax_line_items,
    get_sync_cursor, upsert_sync_cursor
)
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
    parser.add_argument('--full', action='store_true', help='Full sync of all endpoints (clears and re-fetches all data)')
    parser.add_argument('--incremental', '-i', action='store_true', help='Only sync records changed since last successful sync')
    parser.add_argument('--since', type=str, metavar='TIMESTAMP', help='Sync records updated since specific ISO timestamp (e.g., "2024-02-01T00:00:00Z")')
    parser.add_argument('--status', action='store_true', help='Show sync status including incremental sync cursors')
    parser.add_argument('--history', action='store_true', help='Show sync history')
    parser.add_argument('--dry-run', '-n', action='store_true', help='Show what would be synced without writing to database')
    parser.add_argument('--force-full', action='store_true', help='Force full sync even if incremental fails (default: fallback to full)')


def run(args):
    """Route to appropriate subcommand handler."""
    pass


def _get_last_sync_timestamp(db, endpoint, incremental=False):
    """Get the timestamp to use for incremental sync filtering.
    
    Args:
        db: Database connection
        endpoint: The endpoint/table being synced
        incremental: Whether incremental mode is enabled
        
    Returns:
        ISO timestamp string or None for full sync
    """
    if not incremental:
        return None
    
    # Check sync_cursors table for last successful sync
    cursor_info = get_sync_cursor(db, endpoint)
    
    if cursor_info and cursor_info.get('status') == 'success':
        last_synced = cursor_info.get('last_synced_at')
        if last_synced:
            # Parse and format consistently
            try:
                # Handle various ISO formats
                if last_synced.endswith('Z'):
                    last_synced = last_synced[:-1] + '+00:00'
                dt = datetime.fromisoformat(last_synced)
                # Return in Guesty API format
                return dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')
            except (ValueError, TypeError):
                pass
    
    return None


def _build_incremental_filter(timestamp):
    """Build the filter array for incremental sync.
    
    Args:
        timestamp: The ISO timestamp to filter from
        
    Returns:
        Filter array for Guesty API
    """
    return [{
        "operator": "$gt",
        "field": "lastUpdatedAt",
        "value": timestamp
    }]


def _supports_incremental_sync(endpoint):
    """Check if an endpoint supports incremental sync via lastUpdatedAt.
    
    Args:
        endpoint: The endpoint name
        
    Returns:
        True if incremental sync is supported
    """
    # These endpoints support lastUpdatedAt filtering
    supported = {
        'listings', 'reservations', 'guests', 'reviews', 
        'tasks', 'users', 'integrations'
    }
    return endpoint in supported


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
        'listings': {'path': 'listings', 'table': 'listings', 'incremental': True},
        'reservations': {'path': 'reservations', 'table': 'reservations', 'incremental': True},
        'guests': {'path': 'guests', 'table': 'guests', 'incremental': True},
        'owners': {'path': 'owners', 'table': 'owners', 'incremental': False},
        'users': {'path': 'users', 'table': 'users', 'incremental': True},
        'reviews': {'path': 'reviews', 'table': 'reviews', 'incremental': True},
        'tasks': {'path': 'tasks', 'table': 'tasks', 'incremental': True},
        'financials': {'path': 'finance/invoices', 'table': 'financials', 'incremental': False},
        'webhooks': {'path': 'webhooks', 'table': 'webhooks', 'incremental': False},
    }
    
    if args.full or args.endpoint in (None, 'full', 'all'):
        to_sync = list(endpoints.keys())
        mode_str = "full" if args.full else "incremental" if args.incremental else "standard"
        print(bold(f"Starting {mode_str} sync for all endpoints..."))
    elif args.endpoint in endpoints:
        to_sync = [args.endpoint]
        mode_str = "full" if args.full else "incremental" if args.incremental else "standard"
        print(bold(f"Starting {mode_str} sync for {args.endpoint}..."))
    else:
        print(red(f"Unknown endpoint: {args.endpoint}"))
        print(f"Available: {', '.join(endpoints.keys())}")
        return
    
    print()
    
    client = GuestyClient(config)
    db = get_db()
    
    results = []
    overall_start_time = time.time()
    
    for endpoint in to_sync:
        info = endpoints[endpoint]
        start_time = time.time()
        
        # Determine sync mode for this endpoint
        is_full_sync = args.full
        is_incremental = args.incremental and info['incremental']
        
        # If --since is provided, use that timestamp
        if args.since:
            since_timestamp = args.since
            is_incremental = True
        else:
            since_timestamp = None
        
        # Get timestamp for incremental sync
        incremental_timestamp = None
        if not is_full_sync and is_incremental:
            if since_timestamp:
                incremental_timestamp = since_timestamp
                print(f"Syncing {endpoint} (since {incremental_timestamp})...", end=' ', flush=True)
            else:
                incremental_timestamp = _get_last_sync_timestamp(db, endpoint, True)
                if incremental_timestamp:
                    print(f"Syncing {endpoint} (incremental from {incremental_timestamp[:19]})...", end=' ', flush=True)
                else:
                    print(f"Syncing {endpoint} (no cursor, falling back to full)...", end=' ', flush=True)
                    is_full_sync = True
        else:
            if is_full_sync:
                print(f"Syncing {endpoint} (full)...", end=' ', flush=True)
            else:
                print(f"Syncing {endpoint}...", end=' ', flush=True)
        
        try:
            # Build params based on endpoint and sync mode
            params = {}
            
            # Add incremental filter if applicable
            if is_incremental and incremental_timestamp and info['incremental']:
                params['filters'] = json.dumps(_build_incremental_filter(incremental_timestamp))
            
            # Fetch data
            records = _fetch_endpoint_data(client, endpoint, info, params)
            
            # Track invoice items and taxes for reservations
            invoice_items_to_upsert = []
            tax_items_to_upsert = []
            
            # For full sync: clear table first. For incremental: upsert only
            if not args.dry_run:
                if is_full_sync:
                    db.execute(f"DELETE FROM {info['table']}")
                # For incremental, we use INSERT OR REPLACE which handles updates
            
            # Get existing columns for this table
            cursor = db.execute(f"PRAGMA table_info({info['table']})")
            existing_cols = {row[1] for row in cursor.fetchall()}
            
            for record in records:
                # Map API record to DB columns
                result = _map_record_to_db(record, info['table'], existing_cols, args.dry_run)
                if not result:
                    continue
                
                # Handle tuple return for reservations (includes invoice/tax items)
                if endpoint == 'reservations' and isinstance(result, tuple):
                    row_data, invoice_items, tax_items = result
                    invoice_items_to_upsert.extend(invoice_items)
                    tax_items_to_upsert.extend(tax_items)
                else:
                    row_data = result
                
                if args.dry_run:
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
            
            # Upsert invoice items if any were found
            if endpoint == 'reservations' and invoice_items_to_upsert and not args.dry_run:
                upsert_invoice_items(db, invoice_items_to_upsert)
            
            # Upsert tax line items if any were found
            if endpoint == 'reservations' and tax_items_to_upsert and not args.dry_run:
                upsert_tax_line_items(db, tax_items_to_upsert)
            
            if not args.dry_run:
                db.commit()
            
            duration = time.time() - start_time
            
            if not args.dry_run:
                log_sync(db, endpoint, len(records), duration, 'success')
                
                # Update sync cursor for incremental tracking
                if info['incremental']:
                    # For incremental syncs, store current time as the new cursor
                    # For full syncs, store None to indicate a full sync was done
                    if is_incremental and not is_full_sync:
                        # Use current time as the new cursor for next incremental sync
                        from datetime import datetime, timezone
                        new_cursor = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
                    else:
                        new_cursor = None
                    upsert_sync_cursor(db, info['table'], new_cursor, len(records), 'success')
                
                mode_indicator = "i" if is_incremental and not is_full_sync else "F"
                print(green(f"✓ {len(records)} records ({duration:.1f}s) [{mode_indicator}]"))
            else:
                print(yellow(f"⊘ {len(records)} records (dry-run)"))
                
                # Show invoice items and tax items count in dry-run
                if endpoint == 'reservations':
                    if invoice_items_to_upsert:
                        print(dim(f"   → {len(invoice_items_to_upsert)} invoice items would be synced"))
                    if tax_items_to_upsert:
                        print(dim(f"   → {len(tax_items_to_upsert)} tax line items would be synced"))
            
            results.append({
                'endpoint': endpoint, 
                'records': len(records), 
                'status': 'success',
                'duration': duration,
                'incremental': is_incremental and not is_full_sync
            })
            
        except Exception as e:
            duration = time.time() - start_time
            log_sync(db, endpoint, 0, duration, 'error', str(e))
            
            # Update sync cursor with error status
            if info['incremental']:
                cursor_value = incremental_timestamp if is_incremental else None
                upsert_sync_cursor(db, info['table'], cursor_value, 0, 'error')
            
            print(red(f"✗ Error: {e}"))
            
            # Fallback to full sync if incremental failed and --force-full not set
            if is_incremental and not args.force_full and not args.dry_run:
                print(yellow(f"   → Falling back to full sync for {endpoint}..."), end=' ', flush=True)
                try:
                    # Retry as full sync
                    records = _fetch_endpoint_data(client, endpoint, info, {})
                    
                    if not args.dry_run:
                        db.execute(f"DELETE FROM {info['table']}")
                    
                    cursor = db.execute(f"PRAGMA table_info({info['table']})")
                    existing_cols = {row[1] for row in cursor.fetchall()}
                    
                    for record in records:
                        result = _map_record_to_db(record, info['table'], existing_cols, args.dry_run)
                        if not result:
                            continue
                        
                        # Handle tuple return for reservations
                        if endpoint == 'reservations' and isinstance(result, tuple):
                            row_data = result[0]
                        else:
                            row_data = result
                        
                        if args.dry_run:
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
                    
                    if not args.dry_run:
                        db.commit()
                    
                    log_sync(db, endpoint, len(records), duration, 'success')
                    upsert_sync_cursor(db, info['table'], None, len(records), 'success')
                    
                    print(green(f"✓ {len(records)} records (full fallback)"))
                    results.append({
                        'endpoint': endpoint, 
                        'records': len(records), 
                        'status': 'success',
                        'duration': duration,
                        'fallback': True
                    })
                    continue
                    
                except Exception as fallback_error:
                    print(red(f"✗ Fallback also failed: {fallback_error}"))
            
            results.append({
                'endpoint': endpoint, 
                'records': 0, 
                'status': 'error', 
                'error': str(e),
                'duration': duration
            })
    
    print()
    total_duration = time.time() - overall_start_time
    total_records = sum(r['records'] for r in results)
    
    print(green(f"Sync complete! {total_records} records in {total_duration:.1f}s"))
    
    # Print summary table
    if len(results) > 1:
        print()
        headers = ['Endpoint', 'Records', 'Duration', 'Mode']
        rows = []
        for r in results:
            mode = 'incremental' if r.get('incremental') else 'full' if r.get('fallback') else 'standard'
            rows.append([
                r['endpoint'],
                r['records'],
                f"{r.get('duration', 0):.1f}s",
                mode
            ])
        print_table(headers, rows)


def _fetch_endpoint_data(client, endpoint, info, params):
    """Fetch data from a specific endpoint.
    
    Args:
        client: GuestyClient instance
        endpoint: Endpoint name
        info: Endpoint configuration
        params: Query parameters
        
    Returns:
        List of records
    """
    if endpoint in ['owners', 'webhooks']:
        # These return raw arrays
        data = client.api_get(info['path'], params if params else None)
        records = data if isinstance(data, list) else data.get('results', [])
    elif endpoint == 'reviews':
        # Reviews uses different format
        data = client.api_get_all(info['path'], params)
        records = data if isinstance(data, list) else data.get('data', [])
    elif endpoint == 'reservations':
        # Request all important fields for reservations including invoice items and taxes
        fields_params = params.copy()
        fields_params['fields'] = 'confirmationCode status source checkIn checkOut checkInDateLocalized checkOutDateLocalized listingId guestId guest.firstName guest.lastName guest.fullName guest.email guest.phone money money.hostPayout money.totalPaid money.balanceDue money.currency money.invoiceItems money.taxes nightsCount guestsCount createdAt confirmedAt updatedAt lastUpdatedAt customFields tags houseRules checkInDetails paymentMethods cancellationPolicy'
        records = client.api_get_all(info['path'], fields_params)
    else:
        records = client.api_get_all(info['path'], params)
    
    return records


def _map_record_to_db(record, table, existing_cols, dry_run=False):
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
        if 'max_guests' in existing_cols:
            row['max_guests'] = record.get('accommodates')
        if 'active' in existing_cols:
            row['active'] = 1 if record.get('active', True) else 0
        if 'title' in existing_cols:
            row['title'] = record.get('title')
        if 'nickname' in existing_cols:
            row['nickname'] = record.get('nickname')
        if 'status' in existing_cols:
            row['status'] = record.get('status')
        if 'type' in existing_cols:
            row['type'] = record.get('type')
        if 'bedrooms' in existing_cols:
            row['bedrooms'] = record.get('bedrooms')
        if 'bathrooms' in existing_cols:
            row['bathrooms'] = record.get('bathrooms')
        if 'created_at' in existing_cols:
            row['created_at'] = record.get('createdAt')
        if 'updated_at' in existing_cols:
            row['updated_at'] = record.get('updatedAt')
    
    elif table == 'reservations':
        # Initialize lists for invoice items and taxes
        invoice_items = []
        tax_items = []
        
        # Map confirmation_code from API confirmationCode
        if 'confirmation_code' in existing_cols:
            row['confirmation_code'] = record.get('confirmationCode')
        
        # Map check_in and check_out from API checkIn/checkOut
        if 'check_in' in existing_cols:
            row['check_in'] = record.get('checkIn')
        if 'check_out' in existing_cols:
            row['check_out'] = record.get('checkOut')
        
        # Map nights and guests_count from API nightsCount/guestsCount
        if 'nights' in existing_cols:
            row['nights'] = record.get('nightsCount')
        if 'guests_count' in existing_cols:
            row['guests_count'] = record.get('guestsCount')
        
        # Map listing_id from API listingId
        if 'listing_id' in existing_cols:
            row['listing_id'] = record.get('listingId')
        
        guest = record.get('guest', {})
        if isinstance(guest, dict):
            if 'guest_id' in existing_cols:
                row['guest_id'] = guest.get('_id')
            if 'guest_name' in existing_cols:
                name = f"{guest.get('firstName', '')} {guest.get('lastName', '')}".strip()
                if name:
                    row['guest_name'] = name
            if 'guest_email' in existing_cols:
                row['guest_email'] = guest.get('email')
            if 'guest_phone' in existing_cols:
                row['guest_phone'] = guest.get('phone')
        
        money = record.get('money', {}) or {}
        if isinstance(money, dict):
            if 'total_price' in existing_cols:
                row['total_price'] = money.get('fareAccommodation') or money.get('hostPayout', 0)
            if 'subtotal' in existing_cols:
                row['subtotal'] = money.get('subtotal') or money.get('fareAccommodation', 0)
            if 'balance_due' in existing_cols:
                row['balance_due'] = money.get('balanceDue', 0)
            if 'host_payout' in existing_cols:
                row['host_payout'] = money.get('hostPayout')
            if 'total_paid' in existing_cols:
                row['total_paid'] = money.get('totalPaid')
            if 'payment_status' in existing_cols:
                row['payment_status'] = money.get('paymentStatus')
            if 'currency' in existing_cols:
                row['currency'] = money.get('currency') or record.get('currency')
            
            # Extract invoice items from money object
            raw_invoice_items = money.get('invoiceItems', []) or []
            res_id = record.get('_id') or record.get('id')
            listing_id = record.get('listingId')
            for item in raw_invoice_items:
                if isinstance(item, dict):
                    # Add reservation context to item
                    item_with_context = item.copy()
                    item_with_context['reservation_id'] = res_id
                    item_with_context['listing_id'] = listing_id
                    invoice_items.append(item_with_context)
            
            # Extract taxes from money object
            raw_taxes = money.get('taxes', []) or []
            for tax in raw_taxes:
                if isinstance(tax, dict):
                    # Add reservation context to tax
                    tax_with_context = tax.copy()
                    tax_with_context['reservation_id'] = res_id
                    tax_with_context['listing_id'] = listing_id
                    tax_items.append(tax_with_context)
        
        # Additional fields for DR-15 automation
        if 'custom_fields' in existing_cols:
            custom_fields = record.get('customFields', [])
            if custom_fields:
                row['custom_fields'] = json.dumps(custom_fields)
        
        if 'tags' in existing_cols:
            tags = record.get('tags', [])
            if tags:
                row['tags'] = json.dumps(tags)
        
        if 'house_rules' in existing_cols:
            house_rules = record.get('houseRules', '')
            if house_rules:
                row['house_rules'] = house_rules if isinstance(house_rules, str) else json.dumps(house_rules)
        
        if 'check_in_details' in existing_cols:
            check_in_details = record.get('checkInDetails', {})
            if check_in_details:
                row['check_in_details'] = json.dumps(check_in_details)
        
        if 'payment_methods' in existing_cols:
            payment_methods = record.get('paymentMethods', [])
            if payment_methods:
                row['payment_methods'] = json.dumps(payment_methods)
        
        if 'cancellation_policy' in existing_cols:
            cancellation_policy = record.get('cancellationPolicy', {})
            if cancellation_policy:
                row['cancellation_policy'] = json.dumps(cancellation_policy)
        
        # Calculate platform commission
        if 'platform_commission' in existing_cols or 'platform_commission_rate' in existing_cols:
            source = record.get('source', '')
            source_lower = source.lower() if source else ''
            
            if 'airbnb' in source_lower:
                commission_rate = 0.03
            elif 'vrbo' in source_lower or 'homeaway' in source_lower:
                commission_rate = 0.05
            elif 'booking.com' in source_lower or 'bookingcom' in source_lower:
                commission_rate = 0.15
            else:
                commission_rate = 0.0
            
            if 'platform_commission_rate' in existing_cols:
                row['platform_commission_rate'] = commission_rate
            
            if 'platform_commission' in existing_cols:
                total_paid = money.get('totalPaid', 0) or 0
                row['platform_commission'] = total_paid * commission_rate if total_paid else 0
        
        # Return tuple with row data, invoice items, and tax items for reservations
        return (row, invoice_items, tax_items)
    
    elif table == 'guests':
        if 'full_name' in existing_cols:
            row['full_name'] = f"{record.get('firstName', '')} {record.get('lastName', '')}".strip()
        if 'first_name' in existing_cols:
            row['first_name'] = record.get('firstName', '')
        if 'last_name' in existing_cols:
            row['last_name'] = record.get('lastName', '')
        if 'email' in existing_cols:
            row['email'] = record.get('email')
        if 'phone' in existing_cols:
            row['phone'] = record.get('phone')
        if 'country' in existing_cols:
            row['country'] = record.get('country')
    
    elif table == 'owners':
        if 'is_active' in existing_cols:
            row['is_active'] = 1 if record.get('active', True) else 0
        if 'full_name' in existing_cols:
            row['full_name'] = f"{record.get('firstName', '')} {record.get('lastName', '')}".strip()
        if 'first_name' in existing_cols:
            row['first_name'] = record.get('firstName', '')
        if 'last_name' in existing_cols:
            row['last_name'] = record.get('lastName', '')
        if 'email' in existing_cols:
            row['email'] = record.get('email')
        if 'phone' in existing_cols:
            row['phone'] = record.get('phone')
        if 'company' in existing_cols:
            row['company'] = record.get('company')
        if 'notes' in existing_cols:
            row['notes'] = record.get('notes')
    
    elif table == 'users':
        if 'first_name' in existing_cols:
            row['first_name'] = record.get('firstName', '')
        if 'last_name' in existing_cols:
            row['last_name'] = record.get('lastName', '')
        if 'active' in existing_cols:
            row['active'] = 1 if record.get('active', True) else 0
        if 'created_at' in existing_cols:
            row['created_at'] = record.get('createdAt')
        if 'updated_at' in existing_cols:
            row['updated_at'] = record.get('updatedAt')
    
    elif table == 'reviews':
        raw_review = record.get('rawReview', {})
        if isinstance(raw_review, dict):
            if 'rating' in existing_cols:
                row['rating'] = raw_review.get('overall_rating')
            if 'content' in existing_cols:
                row['content'] = raw_review.get('public_review')
            if 'response' in existing_cols:
                row['response'] = raw_review.get('reviewee_response')
        if 'reviewer_name' in existing_cols:
            row['reviewer_name'] = record.get('reviewerName') or (record.get('reviewer', {}) or {}).get('name')
        if 'platform' in existing_cols:
            row['platform'] = record.get('channelId')
        if 'reservation_id' in existing_cols:
            row['reservation_id'] = record.get('reservationId')
        if 'listing_id' in existing_cols:
            row['listing_id'] = record.get('listingId')
        if 'guest_id' in existing_cols:
            row['guest_id'] = record.get('guestId')
        if 'created_at' in existing_cols:
            row['created_at'] = record.get('createdAt')
        if 'updated_at' in existing_cols:
            row['updated_at'] = record.get('updatedAt')
    
    elif table == 'tasks':
        if 'title' in existing_cols:
            row['title'] = record.get('title')
        if 'description' in existing_cols:
            row['description'] = record.get('description')
        if 'status' in existing_cols:
            row['status'] = record.get('status')
        if 'priority' in existing_cols:
            row['priority'] = record.get('priority')
        if 'assigned_to' in existing_cols:
            row['assigned_to'] = record.get('assignedTo')
        if 'listing_id' in existing_cols:
            row['listing_id'] = record.get('listingId')
        if 'reservation_id' in existing_cols:
            row['reservation_id'] = record.get('reservationId')
        if 'due_date' in existing_cols:
            row['due_date'] = record.get('dueDate')
        if 'completed_at' in existing_cols:
            row['completed_at'] = record.get('completedAt')
        if 'created_at' in existing_cols:
            row['created_at'] = record.get('createdAt')
        if 'updated_at' in existing_cols:
            row['updated_at'] = record.get('updatedAt')
    
    elif table == 'integrations':
        if 'name' in existing_cols:
            row['name'] = record.get('name')
        if 'type' in existing_cols:
            row['type'] = record.get('type')
        if 'status' in existing_cols:
            row['status'] = record.get('status')
        if 'platform' in existing_cols:
            row['platform'] = record.get('platform')
        if 'listing_id' in existing_cols:
            row['listing_id'] = record.get('listingId')
        if 'last_sync' in existing_cols:
            row['last_sync'] = record.get('lastSyncAt')
        if 'sync_errors' in existing_cols:
            row['sync_errors'] = record.get('syncErrors')
        if 'created_at' in existing_cols:
            row['created_at'] = record.get('createdAt')
        if 'updated_at' in existing_cols:
            row['updated_at'] = record.get('updatedAt')
    
    elif table == 'webhooks':
        if 'url' in existing_cols:
            row['url'] = record.get('url')
        if 'events' in existing_cols:
            events = record.get('events', [])
            if events:
                row['events'] = json.dumps(events)
        if 'active' in existing_cols:
            row['active'] = 1 if record.get('active', True) else 0
        if 'created_at' in existing_cols:
            row['created_at'] = record.get('createdAt')
        if 'updated_at' in existing_cols:
            row['updated_at'] = record.get('updatedAt')
    
    return row


def show_sync_status():
    """Show last sync status for all endpoints."""
    endpoints = ['listings', 'reservations', 'guests', 'owners', 'users', 'reviews', 'tasks', 'financials', 'webhooks']
    
    db = get_db()
    
    # Get sync log status
    headers = ['Endpoint', 'Last Sync', 'Records', 'Mode']
    rows = []
    
    for endpoint in endpoints:
        try:
            # Get last sync from sync_log
            cursor = db.execute(
                "SELECT timestamp, records_synced FROM sync_log WHERE endpoint = ? ORDER BY timestamp DESC LIMIT 1",
                (endpoint,)
            )
            row = cursor.fetchone()
            
            # Get cursor info for incremental
            cursor_info = get_sync_cursor(db, endpoint)
            
            if row:
                last_sync = row['timestamp']
                count = row['records_synced']
                
                # Calculate time since last sync
                try:
                    sync_time = datetime.fromisoformat(last_sync.replace('Z', '+00:00'))
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
                
                # Determine mode
                if cursor_info and cursor_info.get('last_cursor'):
                    mode = 'incremental'
                else:
                    mode = 'full'
            else:
                ago = 'Never'
                count = 0
                mode = '-'
            
            rows.append([endpoint, ago, count, mode])
        except Exception as e:
            rows.append([endpoint, 'Error', 0, '-'])
    
    print(f"\n{bold('Sync Status')}")
    print_table(headers, rows)
    
    # Show cursor details for endpoints with incremental support
    print(f"\n{bold('Incremental Sync Cursors')}")
    cursor_headers = ['Table', 'Last Cursor', 'Last Synced', 'Records', 'Status']
    cursor_rows = []
    
    for endpoint in ['listings', 'reservations', 'guests', 'reviews', 'tasks', 'users']:
        try:
            cursor_info = get_sync_cursor(db, endpoint)
            if cursor_info:
                last_synced = cursor_info.get('last_synced_at', '')
                if last_synced:
                    try:
                        dt = datetime.fromisoformat(last_synced.replace('Z', '+00:00'))
                        last_synced = dt.strftime('%Y-%m-%d %H:%M')
                    except:
                        pass
                
                cursor_val = cursor_info.get('last_cursor', '')
                if cursor_val:
                    cursor_val = cursor_val[:19] + '...' if len(cursor_val) > 22 else cursor_val
                else:
                    cursor_val = '(full sync)'
                
                cursor_rows.append([
                    endpoint,
                    cursor_val,
                    last_synced,
                    cursor_info.get('record_count', 0),
                    cursor_info.get('status', '-')
                ])
            else:
                cursor_rows.append([endpoint, '-', '-', 0, '-'])
        except Exception as e:
            cursor_rows.append([endpoint, 'Error', '-', 0, '-'])
    
    print_table(cursor_headers, cursor_rows)


def show_sync_history():
    """Show sync history log."""
    db = get_db()
    
    try:
        cursor = db.execute(
            "SELECT * FROM sync_log ORDER BY timestamp DESC LIMIT 20"
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
