"""
Financials reporting commands for guesty-cli.
"""
from datetime import datetime, timedelta
from collections import defaultdict
from guesty_cli.core.config import load_config
from guesty_cli.core.database import get_db
from guesty_cli.core.output import (
    print_table, print_json, bold, green, cyan, format_money
)


def register(subparsers):
    """Register financials commands with the argument parser."""
    parser = subparsers.add_parser(
        'financials',
        help='Financial reports and summaries'
    )
    parser.set_defaults(func=run_summary)
    parser.add_argument('--listing', type=str, help='Filter by listing ID')
    parser.add_argument('--from', dest='from_date', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--to', dest='to_date', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--type', type=str, help='Filter by line type (income, expense, etc)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')


def run(args):
    """Route to appropriate subcommand handler."""
    pass


def run_summary(args):
    """Show financial summary reports."""
    db = get_db()
    
    # Build base query with JOINs to get listing nickname via reservation
    query = """SELECT f.*, l.nickname as listing_nickname, r.listingId as reservation_listing_id
               FROM financials f
               LEFT JOIN reservations r ON f.reservationId = r.id
               LEFT JOIN listings l ON r.listingId = l.id
               WHERE 1=1"""
    params = []
    
    if args.listing:
        query += " AND (l.nickname LIKE ? OR r.listingId = ?)"
        params.append(f'%{args.listing}%')
        params.append(args.listing)
    if args.type:
        query += " AND f.lineType = ?"
        params.append(args.type)
    if args.from_date:
        query += " AND f.createdAt >= ?"
        params.append(f'{args.from_date}T00:00:00.000Z')
    if args.to_date:
        query += " AND f.createdAt <= ?"
        params.append(f'{args.to_date}T23:59:59.999Z')
    
    try:
        cursor = db.execute(query, params)
        financials = [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"Error querying database: {e}")
        return
    
    if not financials:
        print("No financial records found")
        return
    
    # Calculate summaries
    
    # By listing - use joined nickname
    by_listing = defaultdict(lambda: {'income': 0, 'expenses': 0, 'count': 0})
    for f in financials:
        lid = f.get('listing_nickname') or f.get('reservation_listing_id') or 'unknown'
        by_listing[lid]['count'] += 1
        amount = f.get('amount', 0) or 0
        if f.get('lineType') == 'income' or amount > 0:
            by_listing[lid]['income'] += amount
        else:
            by_listing[lid]['expenses'] += abs(amount)
    
    # By month
    by_month = defaultdict(lambda: {'income': 0, 'expenses': 0, 'count': 0})
    for f in financials:
        date = f.get('createdAt', '')
        month = date[:7] if date else 'unknown'  # YYYY-MM
        by_month[month]['count'] += 1
        amount = f.get('amount', 0) or 0
        if f.get('lineType') == 'income' or amount > 0:
            by_month[month]['income'] += amount
        else:
            by_month[month]['expenses'] += abs(amount)
    
    # By type
    by_type = defaultdict(lambda: {'amount': 0, 'count': 0})
    for f in financials:
        lt = f.get('lineType', 'unknown')
        by_type[lt]['count'] += 1
        by_type[lt]['amount'] += abs(f.get('amount', 0) or 0)
    
    if args.json:
        result = {
            'by_listing': dict(by_listing),
            'by_month': dict(by_month),
            'by_type': dict(by_type),
            'total_records': len(financials),
        }
        print_json(result)
        return
    
    # Print summaries
    print(bold("Financial Summary"))
    print(f"Total records: {len(financials)}")
    print()
    
    # By listing (top earners)
    print(bold("Top Listings"))
    headers = ['Listing', 'Income', 'Expenses', 'Profit', 'Records']
    listing_rows = []
    for lid, data in sorted(by_listing.items(), key=lambda x: x[1]['income'], reverse=True)[:10]:
        # lid is now the nickname (or id if nickname not available)
        name = lid if lid != 'unknown' else 'Unknown'
        
        profit = data['income'] - data['expenses']
        listing_rows.append([
            name[:25],
            format_money(data['income']),
            format_money(data['expenses']),
            format_money(profit),
            data['count'],
        ])
    print_table(headers, listing_rows)
    print()
    
    # By month
    print(bold("By Month"))
    headers = ['Month', 'Income', 'Expenses', 'Profit', 'Records']
    month_rows = []
    for month, data in sorted(by_month.items(), reverse=True):
        profit = data['income'] - data['expenses']
        month_rows.append([
            month,
            format_money(data['income']),
            format_money(data['expenses']),
            format_money(profit),
            data['count'],
        ])
    print_table(headers, month_rows)
    print()
    
    # By type
    print(bold("By Line Type"))
    headers = ['Type', 'Amount', 'Records']
    type_rows = []
    for lt, data in sorted(by_type.items(), key=lambda x: x[1]['amount'], reverse=True):
        type_rows.append([
            lt,
            format_money(data['amount']),
            data['count'],
        ])
    print_table(headers, type_rows)
