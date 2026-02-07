"""Occupancy analytics and reporting commands for guesty-cli.

This module provides occupancy metrics calculation for vacation rental properties:
- Occupancy Rate %: Percentage of available days that were booked
- ADR (Average Daily Rate): Average revenue per booked night
- RevPAR (Revenue Per Available Room): Revenue per available room night

Metrics Calculation Methodology:
==============================

1. OCCUPANCY RATE %
   - Formula: (Booked Days / Available Days) × 100
   - Booked Days: Count of calendar_days where reservation_id IS NOT NULL
   - Available Days: Count of calendar_days where status != 'blocked'
   - Blocked days are excluded from availability (owner stays, maintenance, etc.)

2. ADR (Average Daily Rate)
   - Formula: Total Accommodation Revenue / Total Booked Nights
   - Total Accommodation Revenue: Sum of reservation total_price
   - Total Booked Nights: Sum of reservation nights field
   - Only includes confirmed/completed reservations (excludes cancelled/declined)

3. RevPAR (Revenue Per Available Room)
   - Formula: (Total Revenue / Available Room Nights) OR (ADR × Occupancy Rate)
   - Total Revenue: Sum of all reservation revenue in period
   - Available Room Nights: Number of days the listing was available for booking
   - This measures revenue efficiency across all inventory, not just booked nights

4. GAP ANALYSIS
   - Identifies consecutive available days between bookings
   - Gaps are defined as 1-6 available nights between booked periods
   - Suggests pricing adjustments based on gap length and proximity to stay date
"""
import sqlite3
import argparse
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from guesty_cli.core.config import load_config
from guesty_cli.core.database import get_db
from guesty_cli.core.output import (
    print_table, print_card, print_json, print_stats, print_header,
    bold, cyan, green, red, yellow, dim, format_money, format_date
)


def register(subparsers):
    """Register occupancy commands with the argument parser."""
    # Main occupancy command
    parser = subparsers.add_parser(
        'occupancy',
        help='Occupancy analytics and revenue metrics'
    )
    parser.set_defaults(func=run_summary)
    
    # Time period filters (mutually exclusive)
    period_group = parser.add_mutually_exclusive_group()
    period_group.add_argument('--month', type=str, metavar='YYYY-MM',
                              help='Analyze specific month (e.g., 2024-03)')
    period_group.add_argument('--year', type=int, metavar='YYYY',
                              help='Analyze full year (e.g., 2024)')
    
    # Optional filters
    parser.add_argument('--listing', type=str,
                        help='Filter by listing ID or nickname')
    parser.add_argument('--json', action='store_true',
                        help='Output as JSON')
    
    # Subcommands
    sub = parser.add_subparsers(dest='occupancy_action')
    
    # guesty occupancy gaps
    gaps_parser = sub.add_parser('gaps', help='Identify gap nights between bookings')
    gaps_parser.add_argument('--from', dest='from_date', type=str, required=True,
                             metavar='YYYY-MM-DD', help='Start date')
    gaps_parser.add_argument('--to', dest='to_date', type=str, required=True,
                             metavar='YYYY-MM-DD', help='End date')
    gaps_parser.add_argument('--listing', type=str,
                             help='Filter by listing ID or nickname')
    gaps_parser.add_argument('--max-gap', type=int, default=6,
                             help='Maximum gap nights to report (default: 6)')
    gaps_parser.add_argument('--json', action='store_true', help='Output as JSON')
    gaps_parser.set_defaults(func=run_gaps)


def resolve_listing(db: sqlite3.Connection, identifier: str) -> Optional[str]:
    """Resolve listing ID or nickname to actual ID."""
    cursor = db.execute(
        """SELECT id FROM listings 
           WHERE id = ? OR LOWER(nickname) LIKE LOWER(?)""",
        (identifier, f'%{identifier}%')
    )
    row = cursor.fetchone()
    return row['id'] if row else None


def get_date_range(period_type: str, period_value) -> Tuple[str, str]:
    """Calculate start and end dates for a given period.
    
    Args:
        period_type: 'month' or 'year'
        period_value: YYYY-MM string for month, YYYY int for year
        
    Returns:
        Tuple of (start_date, end_date) in YYYY-MM-DD format
    """
    if period_type == 'month':
        # period_value is string like "2024-03"
        year, month = map(int, period_value.split('-'))
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = datetime(year, month + 1, 1) - timedelta(days=1)
    elif period_type == 'year':
        # period_value is int like 2024
        year = period_value
        start = datetime(year, 1, 1)
        end = datetime(year, 12, 31)
    else:
        raise ValueError(f"Unknown period type: {period_type}")
    
    return start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')


def calculate_monthly_metrics(
    db: sqlite3.Connection,
    start_date: str,
    end_date: str,
    listing_id: Optional[str] = None
) -> Dict:
    """Calculate occupancy metrics for a specific date range.
    
    Returns dict with:
    - total_days: Total days in period
    - available_days: Days available for booking (not blocked)
    - booked_days: Days with confirmed bookings
    - blocked_days: Days blocked (maintenance, owner stays, etc.)
    - occupancy_rate: Percentage of available days booked
    - total_revenue: Sum of reservation revenue
    - total_nights: Sum of booked nights
    - adr: Average Daily Rate
    - revpar: Revenue Per Available Room
    - reservation_count: Number of unique reservations
    """
    params = [start_date, end_date]
    listing_filter = ""
    
    if listing_id:
        listing_filter = "AND cd.listing_id = ?"
        params.append(listing_id)
    
    # Get calendar day counts
    cursor = db.execute(f"""
        SELECT 
            COUNT(*) as total_days,
            SUM(CASE WHEN cd.status != 'blocked' THEN 1 ELSE 0 END) as available_days,
            SUM(CASE WHEN cd.reservation_id IS NOT NULL THEN 1 ELSE 0 END) as booked_days,
            SUM(CASE WHEN cd.status = 'blocked' THEN 1 ELSE 0 END) as blocked_days
        FROM calendar_days cd
        WHERE cd.date >= ? AND cd.date <= ?
        {listing_filter}
    """, params)
    
    calendar_stats = dict(cursor.fetchone())
    
    # Get reservation revenue metrics (only confirmed reservations)
    # Calculate nights from checkIn/checkOut since there's no nights column
    cursor = db.execute(f"""
        SELECT 
            COALESCE(SUM(r.total_price), 0) as total_revenue,
            COALESCE(SUM(
                CAST((julianday(r.check_out) - julianday(r.check_in)) AS INTEGER)
            ), 0) as total_nights,
            COUNT(DISTINCT r.id) as reservation_count,
            COALESCE(AVG(r.total_price / NULLIF(
                CAST((julianday(r.check_out) - julianday(r.check_in)) AS INTEGER), 0
            )), 0) as adr
        FROM reservations r
        WHERE r.check_in >= ? AND r.check_in <= ?
        AND r.status NOT IN ('cancelled', 'canceled', 'declined', 'inquiry', 'pending')
        {listing_filter.replace('cd.', 'r.').replace('listing_id', 'listingId')}
    """, params)
    
    revenue_stats = dict(cursor.fetchone())
    
    # Calculate derived metrics
    available_days = calendar_stats['available_days'] or 0
    booked_days = calendar_stats['booked_days'] or 0
    total_revenue = revenue_stats['total_revenue'] or 0
    total_nights = revenue_stats['total_nights'] or 0
    
    occupancy_rate = (booked_days / available_days * 100) if available_days > 0 else 0
    adr = total_revenue / total_nights if total_nights > 0 else 0
    revpar = total_revenue / available_days if available_days > 0 else 0
    
    return {
        'period_start': start_date,
        'period_end': end_date,
        'total_days': calendar_stats['total_days'] or 0,
        'available_days': available_days,
        'booked_days': booked_days,
        'blocked_days': calendar_stats['blocked_days'] or 0,
        'occupancy_rate': round(occupancy_rate, 2),
        'total_revenue': round(total_revenue, 2),
        'total_nights': total_nights,
        'adr': round(adr, 2),
        'revpar': round(revpar, 2),
        'reservation_count': revenue_stats['reservation_count'] or 0,
    }


def run_summary(args):
    """Run occupancy summary report (monthly or yearly)."""
    db = get_db()
    
    # Resolve listing if provided
    listing_id = None
    listing_name = "All Listings"
    if args.listing:
        listing_id = resolve_listing(db, args.listing)
        if not listing_id:
            print(red(f"Listing '{args.listing}' not found"))
            return
        # Get listing name for display
        cursor = db.execute("SELECT nickname, title FROM listings WHERE id = ?", (listing_id,))
        row = cursor.fetchone()
        listing_name = row['nickname'] or row['title'] or listing_id[:20] if row else listing_id[:20]
    
    if args.month:
        # Single month report
        start_date, end_date = get_date_range('month', args.month)
        metrics = calculate_monthly_metrics(db, start_date, end_date, listing_id)
        
        if args.json:
            print_json(metrics)
            return
        
        print_header(f"Occupancy Report: {args.month}", emoji="📊")
        print(f"{bold('Listing:')} {cyan(listing_name)}")
        print()
        
        # Stats boxes
        print_stats([
            {'value': f"{metrics['occupancy_rate']:.1f}%", 'label': 'Occupancy Rate'},
            {'value': format_money(metrics['adr']), 'label': 'ADR', 'icon': '💰'},
            {'value': format_money(metrics['revpar']), 'label': 'RevPAR', 'icon': '💵'},
        ])
        print()
        
        # Day breakdown
        print(bold("Day Breakdown"))
        headers = ['Metric', 'Days', 'Percentage']
        total = metrics['total_days']
        rows = [
            ['Available', metrics['available_days'], f"{metrics['available_days']/total*100:.1f}%" if total else '0%'],
            ['Booked', metrics['booked_days'], f"{metrics['booked_days']/total*100:.1f}%" if total else '0%'],
            ['Blocked', metrics['blocked_days'], f"{metrics['blocked_days']/total*100:.1f}%" if total else '0%'],
            ['Total', total, '100%'],
        ]
        print_table(headers, rows)
        print()
        
        # Revenue summary
        print(bold("Revenue Summary"))
        headers = ['Metric', 'Value']
        rows = [
            ['Total Revenue', format_money(metrics['total_revenue'])],
            ['Total Booked Nights', metrics['total_nights']],
            ['Reservations', metrics['reservation_count']],
            ['ADR (Average Daily Rate)', format_money(metrics['adr'])],
            ['RevPAR (Revenue per Available Room)', format_money(metrics['revpar'])],
        ]
        print_table(headers, rows)
    
    elif args.year:
        # Annual report with monthly breakdown
        year = args.year
        print_header(f"Annual Occupancy Report: {year}", emoji="📊")
        print(f"{bold('Listing:')} {cyan(listing_name)}")
        print()
        
        # Calculate metrics for each month
        monthly_data = []
        annual_totals = {
            'available_days': 0,
            'booked_days': 0,
            'blocked_days': 0,
            'total_revenue': 0,
            'total_nights': 0,
            'reservation_count': 0,
        }
        
        for month in range(1, 13):
            month_str = f"{year}-{month:02d}"
            start_date, end_date = get_date_range('month', month_str)
            metrics = calculate_monthly_metrics(db, start_date, end_date, listing_id)
            monthly_data.append(metrics)
            
            # Accumulate annual totals
            annual_totals['available_days'] += metrics['available_days']
            annual_totals['booked_days'] += metrics['booked_days']
            annual_totals['blocked_days'] += metrics['blocked_days']
            annual_totals['total_revenue'] += metrics['total_revenue']
            annual_totals['total_nights'] += metrics['total_nights']
            annual_totals['reservation_count'] += metrics['reservation_count']
        
        if args.json:
            print_json({
                'year': year,
                'listing': listing_name,
                'monthly': monthly_data,
                'annual_totals': annual_totals,
            })
            return
        
        # Monthly breakdown table
        print(bold("Monthly Breakdown"))
        headers = ['Month', 'Occ %', 'Revenue', 'Nights', 'ADR', 'RevPAR', 'Res #']
        rows = []
        
        for i, data in enumerate(monthly_data):
            month_name = datetime(year, i + 1, 1).strftime('%b')
            rows.append([
                month_name,
                f"{data['occupancy_rate']:.1f}%",
                format_money(data['total_revenue']),
                data['total_nights'],
                format_money(data['adr']),
                format_money(data['revpar']),
                data['reservation_count'],
            ])
        
        # Add annual totals row
        total_available = annual_totals['available_days']
        annual_occupancy = (annual_totals['booked_days'] / total_available * 100) if total_available > 0 else 0
        annual_adr = annual_totals['total_revenue'] / annual_totals['total_nights'] if annual_totals['total_nights'] > 0 else 0
        annual_revpar = annual_totals['total_revenue'] / total_available if total_available > 0 else 0
        
        rows.append([
            bold('TOTAL'),
            bold(f"{annual_occupancy:.1f}%"),
            bold(format_money(annual_totals['total_revenue'])),
            bold(annual_totals['total_nights']),
            bold(format_money(annual_adr)),
            bold(format_money(annual_revpar)),
            bold(annual_totals['reservation_count']),
        ])
        
        print_table(headers, rows)
        print()
        
        # Annual summary stats
        print_stats([
            {'value': f"{annual_occupancy:.1f}%", 'label': 'Annual Occupancy'},
            {'value': format_money(annual_adr), 'label': 'Annual ADR', 'icon': '💰'},
            {'value': format_money(annual_revpar), 'label': 'Annual RevPAR', 'icon': '💵'},
            {'value': annual_totals['reservation_count'], 'label': 'Total Reservations'},
        ])
    
    else:
        print(yellow("Please specify --month YYYY-MM or --year YYYY"))
        print(dim("Examples:"))
        print(dim("  guesty occupancy --month 2024-03"))
        print(dim("  guesty occupancy --year 2024"))
        print(dim("  guesty occupancy --month 2024-03 --listing 'Beach House'"))


def find_gaps(
    db: sqlite3.Connection,
    start_date: str,
    end_date: str,
    listing_id: Optional[str] = None,
    max_gap: int = 6
) -> List[Dict]:
    """Find gap nights between bookings.
    
    A gap is defined as consecutive available days between booked periods.
    Only gaps of 1 to max_gap nights are reported (larger gaps are market opportunities).
    
    Returns list of dicts with:
    - listing_id, listing_name
    - gap_start, gap_end, gap_nights
    - before_reservation_id, after_reservation_id
    - suggested_price_adjustment (percentage)
    """
    params = [start_date, end_date]
    listing_filter = ""
    
    if listing_id:
        listing_filter = "AND cd.listing_id = ?"
        params.append(listing_id)
    
    # Get all calendar days in range, ordered by listing and date
    cursor = db.execute(f"""
        SELECT 
            cd.listing_id,
            l.nickname as listing_name,
            cd.date,
            cd.status,
            cd.reservation_id,
            cd.price as current_price
        FROM calendar_days cd
        LEFT JOIN listings l ON cd.listing_id = l.id
        WHERE cd.date >= ? AND cd.date <= ?
        {listing_filter}
        ORDER BY cd.listing_id, cd.date
    """, params)
    
    days = [dict(row) for row in cursor.fetchall()]
    
    # Group by listing
    by_listing = defaultdict(list)
    for day in days:
        by_listing[day['listing_id']].append(day)
    
    gaps = []
    
    for listing_id, listing_days in by_listing.items():
        listing_name = listing_days[0]['listing_name'] if listing_days else listing_id[:20]
        
        # Find consecutive available days between booked periods
        gap_start = None
        gap_days = []
        prev_booked = False
        prev_res_id = None
        
        for day in listing_days:
            is_booked = day['reservation_id'] is not None
            is_blocked = day['status'] == 'blocked'
            is_available = not is_booked and not is_blocked
            
            if is_available:
                if prev_booked or gap_days:
                    # We're in or starting a potential gap
                    if gap_start is None:
                        gap_start = day['date']
                    gap_days.append(day)
            elif is_booked:
                if gap_days and 1 <= len(gap_days) <= max_gap:
                    # We found a gap between bookings
                    gap = {
                        'listing_id': listing_id,
                        'listing_name': listing_name,
                        'gap_start': gap_start,
                        'gap_end': gap_days[-1]['date'],
                        'gap_nights': len(gap_days),
                        'before_reservation_id': prev_res_id,
                        'after_reservation_id': day['reservation_id'],
                        'current_avg_price': sum(d['current_price'] or 0 for d in gap_days) / len(gap_days) if gap_days else 0,
                    }
                    gaps.append(gap)
                
                gap_start = None
                gap_days = []
                prev_booked = True
                prev_res_id = day['reservation_id']
            else:
                # Blocked day - reset gap detection
                gap_start = None
                gap_days = []
                prev_booked = False
    
    # Calculate suggested pricing adjustments
    for gap in gaps:
        gap_nights = gap['gap_nights']
        base_adjustment = 0
        
        # Gap size-based adjustment
        if gap_nights == 1:
            base_adjustment = -10  # Small discount for 1-night gap
        elif gap_nights == 2:
            base_adjustment = -5   # Slight discount for 2-night gap
        elif gap_nights <= 4:
            base_adjustment = 0    # No adjustment for medium gaps
        else:
            base_adjustment = 5    # Slight premium for longer gaps
        
        # Urgency adjustment based on how close the gap is
        gap_date = datetime.strptime(gap['gap_start'], '%Y-%m-%d')
        days_until = (gap_date - datetime.now()).days
        
        urgency_adjustment = 0
        if days_until <= 7:
            urgency_adjustment = -15  # Aggressive discount for near-term gaps
        elif days_until <= 14:
            urgency_adjustment = -10  # Moderate discount for 2-week gaps
        elif days_until <= 30:
            urgency_adjustment = -5   # Slight discount for 1-month gaps
        
        gap['suggested_adjustment'] = base_adjustment + urgency_adjustment
        gap['suggested_adjustment_display'] = f"{base_adjustment + urgency_adjustment:+d}%"
        gap['days_until'] = days_until
        gap['urgency'] = 'High' if days_until <= 7 else 'Medium' if days_until <= 14 else 'Low'
    
    # Sort by urgency (closest dates first)
    gaps.sort(key=lambda x: x['gap_start'])
    
    return gaps


def run_gaps(args):
    """Run gap analysis report."""
    db = get_db()
    
    # Validate dates
    try:
        datetime.strptime(args.from_date, '%Y-%m-%d')
        datetime.strptime(args.to_date, '%Y-%m-%d')
    except ValueError:
        print(red("Invalid date format. Use YYYY-MM-DD"))
        return
    
    # Resolve listing if provided
    listing_id = None
    if args.listing:
        listing_id = resolve_listing(db, args.listing)
        if not listing_id:
            print(red(f"Listing '{args.listing}' not found"))
            return
    
    gaps = find_gaps(db, args.from_date, args.to_date, listing_id, args.max_gap)
    
    if args.json:
        print_json(gaps)
        return
    
    print_header(f"Gap Analysis: {args.from_date} to {args.to_date}", emoji="🔍")
    
    if not gaps:
        print(green("✓ No gaps found! All available nights are optimally booked."))
        return
    
    print(f"Found {bold(str(len(gaps)))} gap(s) of 1-{args.max_gap} nights between bookings")
    print()
    
    # Group by listing
    by_listing = defaultdict(list)
    for gap in gaps:
        by_listing[gap['listing_name']].append(gap)
    
    for listing_name, listing_gaps in sorted(by_listing.items()):
        print_card(f"{listing_name}", {
            'Gaps Found': len(listing_gaps),
            'Total Gap Nights': sum(g['gap_nights'] for g in listing_gaps),
        }, icon="🏠")
        
        headers = ['Gap Dates', 'Nights', 'Days Until', 'Urgency', 'Current Price', 'Suggested Adj']
        rows = []
        
        for gap in listing_gaps:
            gap_range = f"{gap['gap_start']} to {gap['gap_end']}"
            rows.append([
                gap_range,
                gap['gap_nights'],
                gap['days_until'],
                gap['urgency'],
                format_money(gap['current_avg_price']),
                gap['suggested_adjustment_display'],
            ])
        
        print_table(headers, rows)
        print()
    
    # Pricing recommendations
    print(bold("Pricing Recommendations"))
    print()
    print("Gap nights represent missed revenue opportunities. Consider:")
    print()
    print("  • " + cyan("High Urgency (≤7 days):") + " Aggressive discounts (-15% to -25%) to fill last-minute gaps")
    print("  • " + cyan("Medium Urgency (8-14 days):") + " Moderate discounts (-10% to -15%) to attract bookings")
    print("  • " + cyan("Low Urgency (15-30 days):") + " Slight discounts (-5% to -10%) or maintain pricing")
    print("  • " + cyan("Single-night gaps:") + " Offer as 'flash deals' with steeper discounts")
    print("  • " + cyan("Multi-night gaps:") + " Market to weekend travelers or business guests")
    print()
    
    # Summary stats
    total_gap_nights = sum(g['gap_nights'] for g in gaps)
    high_urgency = len([g for g in gaps if g['urgency'] == 'High'])
    potential_revenue_at_risk = sum(g['current_avg_price'] * g['gap_nights'] for g in gaps)
    
    print_stats([
        {'value': len(gaps), 'label': 'Total Gaps', 'icon': '🔍'},
        {'value': total_gap_nights, 'label': 'Gap Nights', 'icon': '📅'},
        {'value': high_urgency, 'label': 'High Urgency', 'icon': '⚠️'},
        {'value': format_money(potential_revenue_at_risk), 'label': 'Revenue at Risk', 'icon': '💰'},
    ])
