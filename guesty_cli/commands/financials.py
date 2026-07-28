"""
Financials reporting commands for guesty-cli.

Commands:
  guesty financials revenue --month 2024-01 [--listing <name>] [--owner <name>]
  guesty financials taxes --month 2024-01 [--county monroe|miami-dade]
  guesty financials dr15 --month 2024-01
"""
import argparse
import calendar
import json
from datetime import datetime
from collections import defaultdict
from guesty_cli.core.config import load_config
from guesty_cli.core.database import get_db
from guesty_cli.core.output import (
    print_table, print_card, print_json, print_csv,
    bold, cyan, green, red, yellow, dim, format_money, format_date, format_money_plain
)


# Tax rates by county
TAX_RATES = {
    'monroe': {
        'name': 'Monroe County',
        'tdt_rate': 0.05,  # 5% Tourist Development Tax
        'sales_tax_rate': 0.075,  # 7.5% Sales Tax
        'description': '5% TDT + 7.5% Sales Tax'
    },
    'miami-dade': {
        'name': 'Miami-Dade County',
        'cdt_rate': 0.06,  # 6% Convention Development Tax
        'tdt_rate': 0.02,  # 2% Tourist Development Tax  
        'sales_tax_rate': 0.07,  # 7% Sales Tax
        'description': '6% CDT + 2% TDT + 7% Sales Tax'
    }
}


def _enrich_invoice_row(row):
    """Surface Guesty's own invoice-item field names as top-level keys.

    invoice_items stores normalType/lineType only inside the raw_data payload, and
    ids in snake_case columns. The reports below key off the Guesty names, so
    without this every line item categorizes as 'unknown' and the revenue, tax and
    DR-15 breakdowns silently come out as zero.
    """
    try:
        raw = json.loads(row.get('raw_data') or '{}')
    except (ValueError, TypeError):
        raw = {}

    row['normalType'] = raw.get('normalType') or ''
    row['lineType'] = row.get('type') or raw.get('type') or ''
    row['listingId'] = row.get('listing_id') or raw.get('listing_id') or ''
    row['reservationId'] = row.get('reservation_id') or raw.get('reservation_id') or ''
    return row


def _get_listing_county(listing_city):
    """Determine county based on listing city."""
    if not listing_city:
        return 'unknown'
    
    city_lower = listing_city.lower()
    
    # Monroe County cities
    monroe_cities = ['marathon', 'key colony beach', 'key west', 'islamorada', 
                     'key largo', 'big pine key', 'tavernier', 'duck key']
    
    # Miami-Dade cities
    miami_cities = ['miami']
    
    if any(city in city_lower for city in monroe_cities):
        return 'monroe'
    elif any(city in city_lower for city in miami_cities):
        return 'miami-dade'
    
    return 'unknown'


def _get_owner_for_listing(db, listing_id):
    """Get owner information for a listing."""
    cursor = db.execute("""
        SELECT o.id, o.full_name, o.email
        FROM owners o
        WHERE o.raw_data LIKE ?
    """, (f'%"{listing_id}"%',))

    row = cursor.fetchone()
    if row:
        return {'id': row['id'], 'name': row['full_name'], 'email': row['email']}
    return None


def register(subparsers):
    """Register financials commands with the argument parser."""
    parser = subparsers.add_parser(
        'financials',
        help='Financial reports and analytics'
    )
    
    sub = parser.add_subparsers(dest='financials_action', help='Financial commands')
    
    # guesty financials revenue --month 2024-01 [--listing <name>] [--owner <name>]
    revenue_parser = sub.add_parser('revenue', help='Calculate revenue report')
    revenue_parser.add_argument('--month', type=str, required=True, 
                                help='Month in YYYY-MM format (e.g., 2024-01)')
    revenue_parser.add_argument('--listing', type=str, help='Filter by listing nickname or ID')
    revenue_parser.add_argument('--owner', type=str, help='Filter by owner name')
    revenue_parser.add_argument('--json', action='store_true', help='Output as JSON')
    revenue_parser.add_argument('--csv', action='store_true', help='Output as CSV')
    revenue_parser.set_defaults(func=run_revenue)
    
    # guesty financials taxes --month 2024-01 [--county monroe|miami-dade]
    taxes_parser = sub.add_parser('taxes', help='Calculate tourist and sales taxes')
    taxes_parser.add_argument('--month', type=str, required=True,
                              help='Month in YYYY-MM format (e.g., 2024-01)')
    taxes_parser.add_argument('--county', type=str, choices=['monroe', 'miami-dade'],
                              help='Filter by county')
    taxes_parser.add_argument('--json', action='store_true', help='Output as JSON')
    taxes_parser.add_argument('--csv', action='store_true', help='Output as CSV')
    taxes_parser.set_defaults(func=run_taxes)
    
    # guesty financials dr15 --month 2024-01
    dr15_parser = sub.add_parser('dr15', help='Generate DR-15 ready tax report')
    dr15_parser.add_argument('--month', type=str, required=True,
                             help='Month in YYYY-MM format (e.g., 2024-01)')
    dr15_parser.add_argument('--json', action='store_true', help='Output as JSON')
    dr15_parser.add_argument('--csv', action='store_true', help='Output as CSV')
    dr15_parser.set_defaults(func=run_dr15)
    
    # Keep old summary command for backwards compatibility
    summary_parser = sub.add_parser('summary', help='Show financial summary (legacy)')
    summary_parser.add_argument('--listing', type=str, help='Filter by listing ID')
    summary_parser.add_argument('--from', dest='from_date', type=str, help='Start date (YYYY-MM-DD)')
    summary_parser.add_argument('--to', dest='to_date', type=str, help='End date (YYYY-MM-DD)')
    summary_parser.add_argument('--type', type=str, help='Filter by line type (income, expense, etc)')
    summary_parser.add_argument('--json', action='store_true', help='Output as JSON')
    summary_parser.set_defaults(func=run_summary)
    
    # Default to help if no subcommand
    parser.set_defaults(func=lambda args: parser.print_help())


def run(args):
    """Route to appropriate subcommand handler."""
    pass


def run_revenue(args):
    """Calculate revenue report for a specific month."""
    db = get_db()
    
    # Validate month format
    try:
        year, month = args.month.split('-')
        start_date = f"{year}-{month}-01"
        # Calculate end of month
        if month == '12':
            end_date = f"{int(year)+1}-01-01"
        else:
            end_date = f"{year}-{int(month)+1:02d}-01"
    except ValueError:
        print(red("Error: Invalid month format. Use YYYY-MM (e.g., 2024-01)"))
        return
    
    # Build query to get financial data with listing and owner info
    query = """
        SELECT 
            f.*,
            l.nickname as listing_nickname,
            l.city as listing_city,
            r.confirmation_code,
            r.check_in,
            r.check_out,
            r.guest_name
        FROM invoice_items f
        LEFT JOIN reservations r ON f.reservation_id = r.id
        LEFT JOIN listings l ON r.listing_id = l.id
        WHERE r.check_in >= ? AND r.check_in < ?
    """
    params = [start_date, end_date]
    
    if args.listing:
        query += " AND (l.nickname LIKE ? OR l.id = ? OR r.listing_id = ?)"
        search_term = f'%{args.listing}%'
        params.extend([search_term, args.listing, args.listing])
    
    try:
        cursor = db.execute(query, params)
        financials = [_enrich_invoice_row(dict(row)) for row in cursor.fetchall()]
    except Exception as e:
        print(red(f"Error querying database: {e}"))
        return
    
    if not financials:
        print(yellow(f"No financial records found for {args.month}"))
        return
    
    # Filter by owner if specified
    if args.owner:
        filtered_financials = []
        for f in financials:
            listing_id = f.get('listingId') or ''
            owner = _get_owner_for_listing(db, listing_id)
            if owner and args.owner.lower() in owner['name'].lower():
                filtered_financials.append(f)
        financials = filtered_financials
        
        if not financials:
            print(yellow(f"No financial records found for owner '{args.owner}' in {args.month}"))
            return
    
    # Calculate revenue metrics
    metrics = {
        'total_revenue': 0,
        'accommodation_fare': 0,
        'cleaning_fees': 0,
        'additional_fees': 0,
        'platform_fees': 0,
        'discounts': 0,
        'taxes_collected': 0,
        'net_revenue': 0,
        'reservation_count': set()
    }
    
    # Group by listing
    by_listing = defaultdict(lambda: {
        'revenue': 0, 'cleaning': 0, 'platform_fees': 0, 
        'net': 0, 'count': 0, 'reservations': set()
    })
    
    # Group by owner
    by_owner = defaultdict(lambda: {
        'revenue': 0, 'cleaning': 0, 'platform_fees': 0,
        'net': 0, 'count': 0, 'reservations': set()
    })
    
    for f in financials:
        amount = f.get('amount', 0) or 0
        normal_type = f.get('normalType', '') or ''
        line_type = f.get('lineType', '') or ''
        listing_id = f.get('listingId') or f.get('listing_nickname') or 'Unknown'
        listing_nickname = f.get('listing_nickname') or listing_id
        
        # Track unique reservations
        res_id = f.get('reservationId')
        if res_id:
            metrics['reservation_count'].add(res_id)
            by_listing[listing_nickname]['reservations'].add(res_id)
        
        # Categorize amounts
        if normal_type == 'AF':  # Accommodation fare
            metrics['accommodation_fare'] += amount
            metrics['total_revenue'] += amount
            by_listing[listing_nickname]['revenue'] += amount
        elif normal_type == 'CF':  # Cleaning fee
            metrics['cleaning_fees'] += amount
            metrics['total_revenue'] += amount
            by_listing[listing_nickname]['cleaning'] += amount
        elif normal_type == 'AFE':  # Additional fees
            metrics['additional_fees'] += amount
            metrics['total_revenue'] += amount
        elif normal_type == 'PCM':  # Platform/Channel fees (negative)
            metrics['platform_fees'] += abs(amount)
            by_listing[listing_nickname]['platform_fees'] += abs(amount)
        elif normal_type in ('GCD', 'CO', 'LOSD', 'AFWD'):  # Discounts (negative)
            metrics['discounts'] += abs(amount)
        elif normal_type in ('TT', 'ST', 'TOT', 'TAXD'):  # Taxes
            metrics['taxes_collected'] += amount
        elif amount > 0:
            metrics['total_revenue'] += amount
            by_listing[listing_nickname]['revenue'] += amount
        
        # Get owner for this listing
        owner = _get_owner_for_listing(db, f.get('listingId') or '')
        owner_name = owner['name'] if owner else 'No Owner'
        
        if amount > 0 and normal_type not in ('TT', 'ST', 'TOT', 'TAXD'):
            by_owner[owner_name]['revenue'] += amount
            by_owner[owner_name]['count'] += 1
            if res_id:
                by_owner[owner_name]['reservations'].add(res_id)
    
    # Calculate net revenue
    metrics['net_revenue'] = (metrics['total_revenue'] - metrics['platform_fees'] - 
                              metrics['discounts'])
    
    # Calculate net for each listing
    for listing in by_listing:
        by_listing[listing]['net'] = (by_listing[listing]['revenue'] + 
                                       by_listing[listing]['cleaning'] - 
                                       by_listing[listing]['platform_fees'])
        by_listing[listing]['count'] = len(by_listing[listing]['reservations'])
    
    # Calculate net for each owner
    for owner in by_owner:
        by_owner[owner]['net'] = by_owner[owner]['revenue'] - by_owner[owner].get('platform_fees', 0)
        by_owner[owner]['count'] = len(by_owner[owner]['reservations'])
    
    # Output formatting
    if args.json:
        result = {
            'month': args.month,
            'summary': {
                'total_revenue': round(metrics['total_revenue'], 2),
                'accommodation_fare': round(metrics['accommodation_fare'], 2),
                'cleaning_fees': round(metrics['cleaning_fees'], 2),
                'additional_fees': round(metrics['additional_fees'], 2),
                'platform_fees': round(metrics['platform_fees'], 2),
                'discounts': round(metrics['discounts'], 2),
                'taxes_collected': round(metrics['taxes_collected'], 2),
                'net_revenue': round(metrics['net_revenue'], 2),
                'reservation_count': len(metrics['reservation_count'])
            },
            'by_listing': {k: {
                'revenue': round(v['revenue'], 2),
                'cleaning_fees': round(v['cleaning'], 2),
                'platform_fees': round(v['platform_fees'], 2),
                'net_revenue': round(v['net'], 2),
                'reservation_count': v['count']
            } for k, v in sorted(by_listing.items(), key=lambda x: x[1]['revenue'], reverse=True)},
            'by_owner': {k: {
                'revenue': round(v['revenue'], 2),
                'net_revenue': round(v['net'], 2),
                'reservation_count': v['count']
            } for k, v in sorted(by_owner.items(), key=lambda x: x[1]['revenue'], reverse=True)}
        }
        print_json(result)
        return
    
    # Print report
    print()
    print(bold(f"📊 Revenue Report for {cyan(args.month)}"))
    print()
    
    # Summary card
    summary_data = {
        'Total Revenue': format_money(metrics['total_revenue']),
        'Accommodation Fare': format_money(metrics['accommodation_fare']),
        'Cleaning Fees': format_money(metrics['cleaning_fees']),
        'Additional Fees': format_money(metrics['additional_fees']),
        'Platform Fees': format_money(-metrics['platform_fees']),
        'Discounts': format_money(-metrics['discounts']),
        'Taxes Collected': format_money(metrics['taxes_collected']),
        'Net Revenue': format_money(metrics['net_revenue']),
        'Reservations': len(metrics['reservation_count'])
    }
    print_card(f"Summary - {args.month}", summary_data, icon="💰")
    
    # By listing
    if by_listing:
        print()
        print(bold("By Listing"))
        headers = ['Listing', 'Revenue', 'Cleaning', 'Platform Fees', 'Net', 'Reservations']
        rows = []
        for listing, data in sorted(by_listing.items(), key=lambda x: x[1]['revenue'], reverse=True):
            rows.append([
                listing[:30],
                format_money_plain(data['revenue']),
                format_money_plain(data['cleaning']),
                format_money_plain(-data['platform_fees']),
                format_money_plain(data['net']),
                data['count']
            ])
        print_table(headers, rows)
    
    # By owner
    if by_owner and len(by_owner) > 1:
        print()
        print(bold("By Owner"))
        headers = ['Owner', 'Revenue', 'Net Revenue', 'Reservations']
        rows = []
        for owner, data in sorted(by_owner.items(), key=lambda x: x[1]['revenue'], reverse=True):
            rows.append([
                owner[:30],
                format_money_plain(data['revenue']),
                format_money_plain(data['net']),
                data['count']
            ])
        print_table(headers, rows)


def run_taxes(args):
    """Calculate tourist and sales taxes for a specific month."""
    db = get_db()
    
    # Validate month format
    try:
        year, month = args.month.split('-')
        start_date = f"{year}-{month}-01"
        if month == '12':
            end_date = f"{int(year)+1}-01-01"
        else:
            end_date = f"{year}-{int(month)+1:02d}-01"
    except ValueError:
        print(red("Error: Invalid month format. Use YYYY-MM (e.g., 2024-01)"))
        return
    
    # Query financials with listing info
    query = """
        SELECT 
            f.*,
            l.nickname as listing_nickname,
            l.city as listing_city,
            l.address as listing_address,
            r.confirmation_code,
            r.check_in
        FROM invoice_items f
        LEFT JOIN reservations r ON f.reservation_id = r.id
        LEFT JOIN listings l ON r.listing_id = l.id
        WHERE r.check_in >= ? AND r.check_in < ?
    """
    params = [start_date, end_date]
    
    if args.county:
        # Filter by county - need to check city in Python
        pass
    
    try:
        cursor = db.execute(query, params)
        financials = [_enrich_invoice_row(dict(row)) for row in cursor.fetchall()]
    except Exception as e:
        print(red(f"Error querying database: {e}"))
        return
    
    if not financials:
        print(yellow(f"No financial records found for {args.month}"))
        return
    
    # Calculate taxes by county
    county_data = defaultdict(lambda: {
        'tourist_tax': 0,
        'sales_tax': 0,
        'taxable_revenue': 0,
        'reservations': set(),
        'listings': set()
    })
    
    for f in financials:
        normal_type = f.get('normalType', '') or ''
        amount = f.get('amount', 0) or 0
        city = f.get('listing_city', '')
        listing_id = f.get('listingId') or f.get('listing_nickname') or 'Unknown'
        county = _get_listing_county(city)
        
        # Filter by county if specified
        if args.county and county != args.county:
            continue
        
        res_id = f.get('reservationId')
        
        # Track taxes
        if normal_type in ('TT', 'TOT'):  # Tourist taxes
            county_data[county]['tourist_tax'] += amount
            county_data[county]['reservations'].add(res_id)
            county_data[county]['listings'].add(listing_id)
        elif normal_type == 'ST':  # Sales tax
            county_data[county]['sales_tax'] += amount
            county_data[county]['reservations'].add(res_id)
            county_data[county]['listings'].add(listing_id)
        elif amount > 0 and normal_type not in ('PCM', 'GCD', 'CO'):
            # Track taxable revenue (accommodation + fees)
            county_data[county]['taxable_revenue'] += amount
    
    # Remove empty counties
    county_data = {k: v for k, v in county_data.items() if v['tourist_tax'] > 0 or v['sales_tax'] > 0}
    
    if not county_data:
        print(yellow(f"No tax records found for {args.month}"))
        return
    
    # Output
    if args.json:
        result = {
            'month': args.month,
            'by_county': {}
        }
        for county, data in county_data.items():
            rates = TAX_RATES.get(county, {})
            result['by_county'][county] = {
                'county_name': rates.get('name', county.title()),
                'tourist_tax': round(data['tourist_tax'], 2),
                'sales_tax': round(data['sales_tax'], 2),
                'total_tax': round(data['tourist_tax'] + data['sales_tax'], 2),
                'taxable_revenue': round(data['taxable_revenue'], 2),
                'reservation_count': len(data['reservations']),
                'listing_count': len(data['listings']),
                'tax_rates': rates.get('description', 'Unknown')
            }
        print_json(result)
        return
    
    # Print report
    print()
    print(bold(f"🧾 Tax Report for {cyan(args.month)}"))
    print()
    
    for county, data in county_data.items():
        rates = TAX_RATES.get(county, {})
        total_tax = data['tourist_tax'] + data['sales_tax']
        
        tax_data = {
            'County': rates.get('name', county.title()),
            'Tax Rates': rates.get('description', 'Unknown'),
            'Tourist Tax': format_money(data['tourist_tax']),
            'Sales Tax': format_money(data['sales_tax']),
            'Total Tax Due': format_money(total_tax),
            'Taxable Revenue': format_money(data['taxable_revenue']),
            'Reservations': len(data['reservations']),
            'Listings': len(data['listings'])
        }
        print_card(f"{county.title()} County", tax_data, icon="🏛️")
    
    # Summary table
    print()
    print(bold("Tax Summary by County"))
    headers = ['County', 'Tourist Tax', 'Sales Tax', 'Total Tax', 'Reservations']
    rows = []
    for county, data in county_data.items():
        rates = TAX_RATES.get(county, {})
        total = data['tourist_tax'] + data['sales_tax']
        rows.append([
            rates.get('name', county.title()),
            format_money_plain(data['tourist_tax']),
            format_money_plain(data['sales_tax']),
            format_money_plain(total),
            len(data['reservations'])
        ])
    print_table(headers, rows)


def run_dr15(args):
    """Generate DR-15 ready tax report for Florida Department of Revenue."""
    db = get_db()
    
    # Validate month format
    try:
        year, month = args.month.split('-')
        start_date = f"{year}-{month}-01"
        if month == '12':
            end_date = f"{int(year)+1}-01-01"
        else:
            end_date = f"{year}-{int(month)+1:02d}-01"
        
        # Format for DR-15 (MM/DD/YYYY). Use the real last day of the month:
        # hardcoding 30 mislabelled every 31-day month, and 02/28 was wrong in
        # leap years. The queried window is already correct; this is the period
        # printed on the filing.
        dr15_period_start = f"{month}/01/{year}"
        last_day = calendar.monthrange(int(year), int(month))[1]
        dr15_period_end = f"{month}/{last_day}/{year}"


    except ValueError:
        print(red("Error: Invalid month format. Use YYYY-MM (e.g., 2024-01)"))
        return
    
    # Query financials
    query = """
        SELECT 
            f.*,
            l.nickname as listing_nickname,
            l.city as listing_city,
            r.confirmation_code,
            r.check_in
        FROM invoice_items f
        LEFT JOIN reservations r ON f.reservation_id = r.id
        LEFT JOIN listings l ON r.listing_id = l.id
        WHERE r.check_in >= ? AND r.check_in < ?
    """
    
    try:
        cursor = db.execute(query, [start_date, end_date])
        financials = [_enrich_invoice_row(dict(row)) for row in cursor.fetchall()]
    except Exception as e:
        print(red(f"Error querying database: {e}"))
        return
    
    if not financials:
        print(yellow(f"No financial records found for {args.month}"))
        return
    
    # DR-15 Line items we need to calculate
    # Line 1: Gross Sales
    # Line 2: Exempt Sales
    # Line 3: Taxable Sales (Line 1 - Line 2)
    # Line 4: Tax Due (Line 3 × tax rate)
    
    dr15_data = {
        'monroe': {
            'county_name': 'Monroe County',
            'gross_sales': 0,
            'exempt_sales': 0,
            'taxable_sales': 0,
            'state_sales_tax': 0,  # 6% state portion
            'county_sales_tax': 0,  # 1.5% Monroe discretionary
            'tdt_tax': 0,  # 5% Tourist Development Tax
            'total_tax_due': 0
        },
        'miami-dade': {
            'county_name': 'Miami-Dade County',
            'gross_sales': 0,
            'exempt_sales': 0,
            'taxable_sales': 0,
            'state_sales_tax': 0,  # 6% state
            'county_cdt': 0,  # 6% Convention Development Tax
            'county_tdt': 0,  # 2% Tourist Development Tax
            'county_sales_tax': 0,  # 1% Local option
            'total_tax_due': 0
        }
    }
    
    for f in financials:
        normal_type = f.get('normalType', '') or ''
        amount = f.get('amount', 0) or 0
        city = f.get('listing_city', '')
        county = _get_listing_county(city)
        
        if county not in dr15_data:
            continue
        
        # Track gross sales (accommodation + fees, excluding taxes)
        if amount > 0 and normal_type not in ('TT', 'ST', 'TOT', 'TAXD', 'PCM'):
            dr15_data[county]['gross_sales'] += amount
            dr15_data[county]['taxable_sales'] += amount
        
        # Track taxes collected
        if normal_type == 'ST':  # State/County sales tax
            dr15_data[county]['state_sales_tax'] += amount * 0.8  # Approximate split
            dr15_data[county]['county_sales_tax'] += amount * 0.2
        elif normal_type in ('TT', 'TOT'):  # Tourist taxes
            if county == 'monroe':
                dr15_data[county]['tdt_tax'] += amount
            else:
                # Split between CDT and TDT for Miami-Dade
                dr15_data[county]['county_cdt'] += amount * 0.75  # 6% vs 2% = 75%
                dr15_data[county]['county_tdt'] += amount * 0.25
    
    # Calculate totals
    for county in dr15_data:
        data = dr15_data[county]
        if county == 'monroe':
            data['total_tax_due'] = (data['state_sales_tax'] + data['county_sales_tax'] + 
                                     data['tdt_tax'])
        else:
            data['total_tax_due'] = (data['state_sales_tax'] + data['county_cdt'] + 
                                     data['county_tdt'] + data['county_sales_tax'])
    
    # Output
    if args.json:
        result = {
            'report_type': 'DR-15',
            'reporting_period': args.month,
            'period_start': dr15_period_start,
            'period_end': dr15_period_end,
            'by_county': {k: {
                'county_name': v['county_name'],
                'gross_sales': round(v['gross_sales'], 2),
                'exempt_sales': round(v['exempt_sales'], 2),
                'taxable_sales': round(v['taxable_sales'], 2),
                'state_sales_tax': round(v['state_sales_tax'], 2),
                'county_sales_tax': round(v['county_sales_tax'], 2),
                'tdt_tax': round(v.get('tdt_tax', 0), 2),
                'county_cdt': round(v.get('county_cdt', 0), 2),
                'county_tdt': round(v.get('county_tdt', 0), 2),
                'total_tax_due': round(v['total_tax_due'], 2)
            } for k, v in dr15_data.items() if v['gross_sales'] > 0}
        }
        print_json(result)
        return
    
    if args.csv:
        # CSV format for importing to spreadsheet
        headers = ['County', 'Line', 'Description', 'Amount']
        rows = []
        for county, data in dr15_data.items():
            if data['gross_sales'] <= 0:
                continue
            rows.append([data['county_name'], '1', 'Gross Sales', data['gross_sales']])
            rows.append([data['county_name'], '2', 'Exempt Sales', data['exempt_sales']])
            rows.append([data['county_name'], '3', 'Taxable Sales', data['taxable_sales']])
            rows.append([data['county_name'], '4A', 'State Sales Tax (6%)', data['state_sales_tax']])
            if county == 'monroe':
                rows.append([data['county_name'], '4B', 'County Sales Tax (1.5%)', data['county_sales_tax']])
                rows.append([data['county_name'], 'TDT', 'Tourist Development Tax (5%)', data['tdt_tax']])
            else:
                rows.append([data['county_name'], 'CDT', 'Convention Development Tax (6%)', data['county_cdt']])
                rows.append([data['county_name'], 'TDT', 'Tourist Development Tax (2%)', data['county_tdt']])
            rows.append([data['county_name'], 'TOTAL', 'Total Tax Due', data['total_tax_due']])
        print_csv(headers, rows)
        return
    
    # Print DR-15 formatted report
    print()
    print(bold(f"📋 DR-15 Tax Report for {cyan(args.month)}"))
    print(dim(f"   Reporting Period: {dr15_period_start} - {dr15_period_end}"))
    print()
    
    for county, data in dr15_data.items():
        if data['gross_sales'] <= 0:
            continue
        
        dr15_lines = {
            'Line 1 - Gross Sales': format_money(data['gross_sales']),
            'Line 2 - Exempt Sales': format_money(data['exempt_sales']),
            'Line 3 - Taxable Sales (1-2)': format_money(data['taxable_sales']),
            '': '',
            'Line 4A - State Sales Tax (6%)': format_money(data['state_sales_tax']),
        }
        
        if county == 'monroe':
            dr15_lines['Line 4B - Monroe Co Sales Tax (1.5%)'] = format_money(data['county_sales_tax'])
            dr15_lines['Line TDT - Tourist Development Tax (5%)'] = format_money(data['tdt_tax'])
        else:
            dr15_lines['Line CDT - Convention Dev Tax (6%)'] = format_money(data['county_cdt'])
            dr15_lines['Line TDT - Tourist Development Tax (2%)'] = format_money(data['county_tdt'])
            dr15_lines['Line 4B - Local Option Tax (1%)'] = format_money(data['county_sales_tax'])
        
        dr15_lines['__TOTAL__'] = format_money(data['total_tax_due'])
        
        print_card(f"DR-15 - {data['county_name']}", dr15_lines, icon="📄")
        print()
    
    # Summary table for quick reference
    print(bold("DR-15 Summary"))
    headers = ['County', 'Taxable Sales', 'State Tax', 'County Tax', 'Total Due']
    rows = []
    for county, data in dr15_data.items():
        if data['gross_sales'] <= 0:
            continue
        rows.append([
            data['county_name'],
            format_money_plain(data['taxable_sales']),
            format_money_plain(data['state_sales_tax']),
            format_money_plain(data['county_sales_tax'] + data.get('tdt_tax', 0) + data.get('county_cdt', 0) + data.get('county_tdt', 0)),
            format_money_plain(data['total_tax_due'])
        ])
    print_table(headers, rows)
    
    print()
    print(yellow("⚠️  Note: This is a preliminary report. Verify all amounts before filing."))
    print(dim("    Florida DOR requires DR-15 to be filed by the 1st and late after the 20th of each month."))


def run_summary(args):
    """Show financial summary reports (legacy command)."""
    db = get_db()
    
    # Build base query with JOINs to get listing nickname via reservation
    query = """SELECT f.*, l.nickname as listing_nickname, r.listing_id as reservation_listing_id
               FROM invoice_items f
               LEFT JOIN reservations r ON f.reservation_id = r.id
               LEFT JOIN listings l ON r.listing_id = l.id
               WHERE 1=1"""
    params = []
    
    if args.listing:
        query += " AND (l.nickname LIKE ? OR r.listing_id = ?)"
        params.append(f'%{args.listing}%')
        params.append(args.listing)
    if args.type:
        query += " AND f.type = ?"
        params.append(args.type)
    if args.from_date:
        query += " AND f.created_at >= ?"
        params.append(f'{args.from_date}T00:00:00.000Z')
    if args.to_date:
        query += " AND f.created_at <= ?"
        params.append(f'{args.to_date}T23:59:59.999Z')
    
    try:
        cursor = db.execute(query, params)
        financials = [_enrich_invoice_row(dict(row)) for row in cursor.fetchall()]
    except Exception as e:
        print(red(f"Error querying database: {e}"))
        return
    
    if not financials:
        print(yellow("No financial records found"))
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
        date = f.get('created_at', '')
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
            format_money_plain(data['income']),
            format_money_plain(data['expenses']),
            format_money_plain(profit),
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
            format_money_plain(data['income']),
            format_money_plain(data['expenses']),
            format_money_plain(profit),
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
            format_money_plain(data['amount']),
            data['count'],
        ])
    print_table(headers, type_rows)
