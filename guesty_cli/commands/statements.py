"""Owner Statement Generation for guesty-cli.

Simple focused implementation for generating monthly owner statements.
Usage: guesty owner statement <owner_name> --month 2024-01 [--management-fee 20] [--format text|json]
"""
import json
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any


def register(subparsers):
    """Register the 'statements' subcommand."""
    _register_statement(subparsers, name='statements')


def register_owner_statement(subparsers):
    """Register the 'statement' subcommand under 'owner'."""
    _register_statement(subparsers, name='statement')


def _register_statement(subparsers, name: str):
    """Internal: Register statement command with given name."""
    parser = subparsers.add_parser(
        name,
        help='Generate monthly owner statement'
    )
    parser.add_argument('owner_name', help='Owner name or ID')
    parser.add_argument('--month', type=str, required=True,
                        help='Statement month (YYYY-MM, e.g., 2024-01)')
    parser.add_argument('--management-fee', type=float, default=20.0,
                        help='Management fee percentage (default: 20)')
    parser.add_argument('--format', type=str, choices=['text', 'json'],
                        default='text', help='Output format (default: text)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be calculated without querying data')
    parser.set_defaults(func=run_statement)


def parse_month(month_str: str) -> tuple:
    """Parse YYYY-MM into start and end dates."""
    try:
        year, month = map(int, month_str.split('-'))
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = datetime(year, month + 1, 1) - timedelta(days=1)
        return start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')
    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid month format '{month_str}'. Use YYYY-MM") from e


def resolve_owner(db, owner_name: str) -> Optional[Dict[str, Any]]:
    """Resolve owner by name or ID."""
    # Try exact ID match first
    cursor = db.execute("SELECT * FROM owners WHERE id = ?", (owner_name,))
    row = cursor.fetchone()
    if row:
        return dict(row)
    
    # Try exact name match from raw_data JSON
    cursor = db.execute(
        "SELECT * FROM owners WHERE json_extract(raw_data, '$.fullName') = ?",
        (owner_name,)
    )
    row = cursor.fetchone()
    if row:
        return dict(row)
    
    # Try case-insensitive partial match from raw_data
    cursor = db.execute(
        "SELECT * FROM owners WHERE LOWER(json_extract(raw_data, '$.fullName')) LIKE LOWER(?)",
        (f"%{owner_name}%",)
    )
    row = cursor.fetchone()
    if row:
        return dict(row)
    
    return None


def get_owner_listings(db, owner_id: str) -> List[Dict[str, Any]]:
    """Get all listings for an owner."""
    # Check raw_data for owner reference in listings
    cursor = db.execute("SELECT id, nickname, title, raw_data FROM listings")
    owner_listings = []
    for row in cursor.fetchall():
        raw_data = row['raw_data']
        if raw_data:
            try:
                if isinstance(raw_data, str):
                    listing_data = json.loads(raw_data)
                else:
                    listing_data = raw_data
                owners = listing_data.get('owners', [])
                if owner_id in owners:
                    owner_listings.append(dict(row))
            except (json.JSONDecodeError, TypeError):
                continue
    return owner_listings


def get_reservations_for_listings(db, listing_ids: List[str], start: str, end: str) -> List[Dict]:
    """Get confirmed reservations for listings in date range."""
    if not listing_ids:
        return []
    
    # Query using JSON extract for listing_id from raw_data
    results = []
    for listing_id in listing_ids:
        cursor = db.execute("""
            SELECT r.*, l.nickname as listing_nickname
            FROM reservations r
            LEFT JOIN listings l ON l.id = ?
            WHERE json_extract(r.raw_data, '$.listingId') = ?
              AND json_extract(r.raw_data, '$.status') = 'confirmed'
              AND json_extract(r.raw_data, '$.checkIn') >= ?
              AND json_extract(r.raw_data, '$.checkIn') <= ?
            ORDER BY json_extract(r.raw_data, '$.checkIn')
        """, (listing_id, listing_id, f'{start}T00:00:00.000Z', f'{end}T23:59:59.999Z'))
        results.extend([dict(row) for row in cursor.fetchall()])
    
    return results


def extract_financials(reservation: Dict) -> Dict[str, float]:
    """Extract financial values from reservation."""
    result = {
        'gross_revenue': 0.0,
        'cleaning_fee': 0.0,
        'platform_fee': 0.0,
    }
    
    # Parse raw_data JSON
    raw_data = reservation.get('raw_data')
    if raw_data:
        try:
            if isinstance(raw_data, str):
                data = json.loads(raw_data)
            else:
                data = raw_data
            
            money = data.get('money', {})
            
            # Try invoice items first
            invoice_items = money.get('invoiceItems', [])
            for item in invoice_items:
                item_type = item.get('type', '')
                amount = float(item.get('amount', 0) or 0)
                if item_type == 'ACCOMMODATION_FARE':
                    result['gross_revenue'] += amount
                elif item_type == 'CLEANING_FEE':
                    result['cleaning_fee'] += amount
            
            # If no invoice items, try direct money fields
            if result['gross_revenue'] == 0:
                result['gross_revenue'] = float(money.get('fareAccommodation', 0) or 0)
            if result['cleaning_fee'] == 0:
                result['cleaning_fee'] = float(money.get('fareCleaning', 0) or 0)
            
            result['platform_fee'] = float(money.get('platformCommission', 0) or 0)
            
            # Get source for platform fee estimation
            source = data.get('source', '')
            
        except (json.JSONDecodeError, TypeError, ValueError):
            source = ''
    else:
        source = reservation.get('source', '')
    
    # Fallback to column fields if still zero
    if result['gross_revenue'] == 0:
        result['gross_revenue'] = float(reservation.get('total_price', 0) or 0)
    
    # Estimate platform fee if not present (3-15% of gross)
    if result['platform_fee'] == 0 and result['gross_revenue'] > 0:
        source_lower = source.lower()
        if 'airbnb' in source_lower:
            result['platform_fee'] = result['gross_revenue'] * 0.03
        elif 'booking' in source_lower:
            result['platform_fee'] = result['gross_revenue'] * 0.15
        elif 'vrbo' in source_lower or 'homeaway' in source_lower:
            result['platform_fee'] = result['gross_revenue'] * 0.05
        else:
            result['platform_fee'] = result['gross_revenue'] * 0.08
    
    return result


def calculate_statement(
    owner: Dict,
    listings: List[Dict],
    reservations: List[Dict],
    month: str,
    management_fee_pct: float
) -> Dict[str, Any]:
    """Calculate the owner statement."""
    listings_map = {l['id']: l for l in listings}
    
    # Get owner name from raw_data
    raw_data = owner.get('raw_data', '{}')
    try:
        if isinstance(raw_data, str):
            owner_data = json.loads(raw_data)
        else:
            owner_data = raw_data
        owner_name = owner_data.get('fullName', 'Unknown')
    except (json.JSONDecodeError, TypeError):
        owner_name = owner.get('full_name', 'Unknown')
    
    statement = {
        'owner_name': owner_name,
        'month': month,
        'management_fee_rate': management_fee_pct,
        'gross_revenue': 0.0,
        'cleaning_fees': 0.0,
        'platform_fees': 0.0,
        'management_fee': 0.0,
        'net_payout': 0.0,
        'by_property': {},
    }
    
    for res in reservations:
        # Get listing from raw_data
        raw_data = res.get('raw_data', '{}')
        try:
            if isinstance(raw_data, str):
                res_data = json.loads(raw_data)
            else:
                res_data = raw_data
            listing_id = res_data.get('listingId')
        except (json.JSONDecodeError, TypeError):
            listing_id = None
        
        listing = listings_map.get(listing_id, {})
        prop_name = listing.get('nickname') or listing.get('title') or listing_id or 'Unknown'
        
        fin = extract_financials(res)
        
        # Add to totals
        statement['gross_revenue'] += fin['gross_revenue']
        statement['cleaning_fees'] += fin['cleaning_fee']
        statement['platform_fees'] += fin['platform_fee']
        
        # Add to property breakdown
        if prop_name not in statement['by_property']:
            statement['by_property'][prop_name] = 0.0
        statement['by_property'][prop_name] += fin['gross_revenue']
    
    # Calculate management fee and net payout
    management_rate = management_fee_pct / 100.0
    statement['management_fee'] = statement['gross_revenue'] * management_rate
    statement['net_payout'] = (
        statement['gross_revenue'] +
        statement['cleaning_fees'] -
        statement['platform_fees'] -
        statement['management_fee']
    )
    
    return statement


def format_money(amount: float) -> str:
    """Format amount as currency string."""
    return f"${amount:,.2f}"


def print_text_statement(stmt: Dict):
    """Print statement in simple text format."""
    print()
    print(f"Owner Statement: {stmt['owner_name'].upper()}")
    print(f"Period: {stmt['month']}")
    print()
    print(f"Gross Revenue: {format_money(stmt['gross_revenue'])}")
    print(f"Cleaning Fees: {format_money(stmt['cleaning_fees'])}")
    print(f"Platform Fees: -{format_money(stmt['platform_fees'])}")
    print(f"Management Fee ({stmt['management_fee_rate']:.0f}%): -{format_money(stmt['management_fee'])}")
    print("─" * 40)
    print(f"Net Payout: {format_money(stmt['net_payout'])}")
    
    if stmt['by_property']:
        print()
        print("By Property:")
        for prop, amount in sorted(stmt['by_property'].items(), key=lambda x: -x[1]):
            print(f"  - {prop}: {format_money(amount)}")
    print()


def run_statement(args):
    """Execute the owner statement command."""
    from guesty_cli.core.database import get_db
    
    # Parse month
    try:
        start_date, end_date = parse_month(args.month)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Dry run - show what would happen
    if args.dry_run:
        print(f"[DRY RUN] Would generate statement:")
        print(f"  Owner: {args.owner_name}")
        print(f"  Month: {args.month} ({start_date} to {end_date})")
        print(f"  Management Fee: {args.management_fee}%")
        print(f"  Format: {args.format}")
        return
    
    # Get database connection
    db = get_db()
    
    # Resolve owner
    owner = resolve_owner(db, args.owner_name)
    if not owner:
        print(f"Error: Owner '{args.owner_name}' not found", file=sys.stderr)
        print("Tip: Use 'guesty owners' to list available owners", file=sys.stderr)
        sys.exit(1)
    
    # Get owner name for display
    raw_data = owner.get('raw_data', '{}')
    try:
        if isinstance(raw_data, str):
            owner_data = json.loads(raw_data)
        else:
            owner_data = raw_data
        owner_name = owner_data.get('fullName', 'Unknown')
    except (json.JSONDecodeError, TypeError):
        owner_name = owner.get('full_name', 'Unknown')
    
    # Get owner's listings
    listings = get_owner_listings(db, owner['id'])
    if not listings:
        print(f"No listings found for owner: {owner_name}")
        return
    
    listing_ids = [l['id'] for l in listings]
    
    # Get reservations
    reservations = get_reservations_for_listings(db, listing_ids, start_date, end_date)
    if not reservations:
        print(f"No reservations found for {owner_name} in {args.month}")
        return
    
    # Calculate statement
    statement = calculate_statement(
        owner=owner,
        listings=listings,
        reservations=reservations,
        month=args.month,
        management_fee_pct=args.management_fee
    )
    
    # Output
    if args.format == 'json':
        print(json.dumps(statement, indent=2))
    else:
        print_text_statement(statement)
