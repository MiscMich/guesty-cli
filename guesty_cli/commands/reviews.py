"""
Reviews management commands for guesty-cli.
"""
import json
from guesty_cli.core.config import load_config
from guesty_cli.core.database import get_db
from guesty_cli.core.client import GuestyClient
from guesty_cli.core.output import (
    print_table, print_card, print_json, print_csv,
    bold, green, red, yellow, dim
)


def _get_rating_from_row(row):
    """Extract rating from row, using direct column or parsing from raw_json."""
    rating = row.get('rating')
    if rating:
        return float(rating)
    
    raw_json = row.get('raw_json') or r.get('raw_data') or row.get('raw_data')
    if raw_json:
        try:
            raw = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
            # Try raw_review.overall_rating
            raw_review = raw.get('raw_review', {})
            if raw_review:
                rating = raw_review.get('overall_rating')
                if rating:
                    return float(rating)
            # Try other paths
            rating = raw.get('rating') or raw.get('overallRating')
            if rating:
                return float(rating)
        except (json.JSONDecodeError, AttributeError, ValueError):
            pass
    
    return 0


def _get_reviewer_name_from_row(row, db=None):
    """Extract reviewer name from row."""
    # Try direct column
    name = row.get('reviewer_name')
    if name:
        return name
    
    # Try joined guest column from reservation
    name = row.get('res_guest_name') or row.get('guest_fullName')
    if name:
        return name
    
    # Try parsing from raw_json
    raw_json = row.get('raw_json') or r.get('raw_data') or row.get('raw_data')
    if raw_json:
        try:
            raw = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
            # Try raw_review.guest_name
            raw_review = raw.get('raw_review', {})
            if raw_review:
                name = raw_review.get('guest_name')
                if name:
                    return name
            # Try guestInfo
            guest = raw.get('guestInfo', {})
            if guest:
                name = guest.get('fullName')
                if name:
                    return name
            # Try guestId lookup
            guest_id = raw.get('guestId')
            if guest_id and db:
                try:
                    cursor = db.execute("SELECT fullName FROM guests WHERE id = ?", (guest_id,))
                    guest_row = cursor.fetchone()
                    if guest_row:
                        return guest_row['fullName']
                except:
                    pass
        except (json.JSONDecodeError, AttributeError):
            pass
    
    return 'Anonymous'


def _get_platform_from_row(row):
    """Extract platform from row."""
    # Try direct column
    platform = row.get('platform')
    if platform:
        return platform
    
    # Try parsing from raw_json
    raw_json = row.get('raw_json') or r.get('raw_data') or row.get('raw_data')
    if raw_json:
        try:
            raw = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
            platform = raw.get('source')
            if platform:
                return platform
            # Try raw_review
            raw_review = raw.get('raw_review', {})
            if raw_review:
                platform = raw_review.get('channel_name') or raw_review.get('platform')
                if platform:
                    return platform
        except (json.JSONDecodeError, AttributeError):
            pass
    
    return 'N/A'


def _get_content_from_row(row):
    """Extract review content from row."""
    # Try direct column
    content = row.get('content')
    if content:
        return content
    
    # Try parsing from raw_json
    raw_json = row.get('raw_json') or r.get('raw_data') or row.get('raw_data')
    if raw_json:
        try:
            raw = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
            content = raw.get('publicReview') or raw.get('review')
            if content:
                return content
            # Try raw_review
            raw_review = raw.get('raw_review', {})
            if raw_review:
                content = raw_review.get('public_review') or raw_review.get('review')
                if content:
                    return content
        except (json.JSONDecodeError, AttributeError):
            pass
    
    return ''


def register(subparsers):
    """Register reviews commands with the argument parser."""
    # guesty reviews
    parser = subparsers.add_parser(
        'reviews',
        help='List and view reviews'
    )
    parser.set_defaults(func=run_list)
    parser.add_argument('--listing', type=str, help='Filter by listing ID')
    parser.add_argument('--rating', type=int, help='Minimum rating (1-5)')
    parser.add_argument('--platform', type=str, help='Filter by platform (airbnb, bookingcom, etc)')
    parser.add_argument('--limit', type=int, default=20, help='Limit results')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--csv', action='store_true', help='Output as CSV')
    parser.add_argument('--live', action='store_true', help='Query live API')


def run(args):
    """Route to appropriate subcommand handler."""
    pass


def run_list(args):
    """List reviews."""
    config = load_config()
    
    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        
        # Build filters
        filters = {}
        if args.listing:
            filters['listingId'] = args.listing
        if args.platform:
            filters['source'] = args.platform
        
        params = {'limit': min(args.limit, 100)}
        params.update(filters)
        
        try:
            # Reviews uses different format
            result = client.api_get('/v1/reviews', params)
            reviews = result.get('data', []) if isinstance(result, dict) else result
        except Exception as e:
            print(red(f"Error fetching reviews: {e}"))
            return
    else:
        db = get_db()
        # Use JOIN to get listing nickname
        query = """SELECT r.*, l.nickname as listing_nickname
                   FROM reviews r
                   LEFT JOIN listings l ON r.listing_id = l.id
                   WHERE 1=1"""
        params = []

        if args.listing:
            query += " AND r.listing_id = ?"
            params.append(args.listing)
        if args.rating:
            query += " AND (r.rating >= ? OR (r.rating IS NULL OR r.rating = 0))"
            params.append(args.rating)
        if args.platform:
            query += " AND (r.platform = ? OR r.platform IS NULL)"
            params.append(args.platform)

        query += " ORDER BY r.created_at DESC LIMIT ?"
        params.append(args.limit)

        try:
            cursor = db.execute(query, params)
            reviews = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(red(f"Error querying database: {e}"))
            return

    if not reviews:
        print(yellow("No reviews found"))
        return

    # Post-process to get guest names from raw_json guestId
    db = get_db()
    guest_cache = {}
    for r in reviews:
        if not r.get('reviewer_name'):
            # Try to get guestId from raw_json
            raw_json = r.get('raw_json') or r.get('raw_data')
            if raw_json:
                try:
                    raw = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
                    guest_id = raw.get('guestId')
                    if guest_id:
                        if guest_id not in guest_cache:
                            try:
                                cursor = db.execute("SELECT fullName FROM guests WHERE id = ?", (guest_id,))
                                guest_row = cursor.fetchone()
                                guest_cache[guest_id] = guest_row['fullName'] if guest_row else None
                            except:
                                guest_cache[guest_id] = None
                        if guest_cache[guest_id]:
                            r['reviewer_name'] = guest_cache[guest_id]
                except:
                    pass

    # Format for output
    headers = ['Reviewer', 'Listing', 'Rating', 'Platform', 'Date', 'Snippet']
    rows = []
    for r in reviews:
        rating = _get_rating_from_row(r)
        stars = '★' * int(rating) + '☆' * (5 - int(rating))

        # Truncate review text
        text = _get_content_from_row(r) or ''
        snippet = text[:50] + '...' if len(text) > 50 else text

        reviewer_name = _get_reviewer_name_from_row(r)
        listing_name = r.get('listing_nickname') or r.get('listingId') or 'N/A'
        platform = _get_platform_from_row(r)
        created_at = r.get('created_at')

        rows.append([
            reviewer_name[:20],
            listing_name[:20],
            f"{stars} ({rating})",
            platform,
            created_at[:10] if created_at else 'N/A',
            snippet,
        ])
    
    if args.json:
        print_json(reviews)
    elif args.csv:
        print_csv(headers, rows)
    else:
        print(f"\n{bold(f'Reviews ({len(reviews)} shown)')}")
        print_table(headers, rows)
    
    # Print full review detail for top review if not JSON/CSV
    if not args.json and not args.csv and reviews:
        print()
        top_review = reviews[0]
        text = _get_content_from_row(top_review)
        if text:
            print(bold("Latest Review:"))
            reviewer = _get_reviewer_name_from_row(top_review)
            print(f"  Guest: {reviewer}")
            rating = _get_rating_from_row(top_review)
            stars = '★' * int(rating) + '☆' * (5 - int(rating))
            print(f"  Rating: {stars} ({rating})")
            print()
            # Wrap text
            words = text.split()
            line = "  "
            for word in words:
                if len(line) + len(word) > 80:
                    print(line)
                    line = "  " + word
                else:
                    line += " " + word
            if line.strip():
                print(line)
            
            # Host response
            response = top_review.get('response') or ''
            if response:
                print()
                print(bold("Host Response:"))
                words = response.split()
                line = "  "
                for word in words:
                    if len(line) + len(word) > 80:
                        print(line)
                        line = "  " + word
                    else:
                        line += " " + word
                if line.strip():
                    print(line)
