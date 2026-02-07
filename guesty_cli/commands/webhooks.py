"""Webhooks management commands for guesty-cli.

Enhanced webhook server with queue processing, persistence, and auto-retry.
"""
import json
import urllib.request
import urllib.error
import http.server
import socketserver
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, Any, Optional

from guesty_cli.core.config import load_config, get_db_path
from guesty_cli.core.client import GuestyClient
from guesty_cli.core.database import (
    get_db,
    insert_webhook_event,
    get_pending_webhook_events,
    get_webhook_event_by_id,
    update_webhook_event_status,
    get_webhook_event_log,
    get_webhook_stats,
    upsert_reservations,
    upsert_guests,
    upsert_reviews,
)
from guesty_cli.core.output import (
    print_table, print_json, bold, green, red, yellow, cyan, dim
)

# Valid webhook events per Guesty API
VALID_WEBHOOK_EVENTS = [
    'reservation.new',
    'reservation.updated',
    'reservation.canceled',
    'reservation.confirmed',
    'listing.new',
    'listing.updated',
    'listing.removed',
    'listing.calendar.updated',
    'calendar.updated.v2',
    'task.created',
    'task.updated',
    'task.deleted',
    'guest.created',
    'guest.updated',
    'guest.deleted',
    'reservation.messageReceived',
    'reservation.messageSent',
    'payments.received',
    'payments.failed',
    'payments.refunded',
    'review.created',
]

# Event handler registry
EVENT_HANDLERS: Dict[str, Callable] = {}

# Global flag for graceful shutdown
_shutdown_requested = False


def register_handler(event_type: str):
    """Decorator to register an event handler."""
    def decorator(func: Callable):
        EVENT_HANDLERS[event_type] = func
        return func
    return decorator


def get_nested_value(data: dict, path: str, default=None):
    """Get a nested value from dict using dot notation."""
    keys = path.split('.')
    value = data
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key, default)
        else:
            return default
    return value


# =============================================================================
# EVENT HANDLERS
# =============================================================================

@register_handler('reservation.new')
@register_handler('reservation.created')
def handle_reservation_created(payload: dict, client: GuestyClient, db) -> dict:
    """Handle reservation created/updated events."""
    reservation = payload.get('reservation', {})
    guest = payload.get('guest', {})
    
    res_id = reservation.get('_id') or reservation.get('id')
    if not res_id:
        raise ValueError("No reservation ID in payload")
    
    # Fetch full reservation from API
    try:
        full_res = client.api_get(f'/v1/reservations/{res_id}')
        if isinstance(full_res, dict):
            # Upsert to database
            upsert_reservations(db, [full_res])
            
            # Also sync guest if present
            guest_data = full_res.get('guest', {})
            if guest_data and isinstance(guest_data, dict):
                upsert_guests(db, [guest_data])
            
            return {'status': 'success', 'action': 'synced', 'id': res_id}
    except Exception as e:
        raise ValueError(f"Failed to sync reservation: {e}")
    
    return {'status': 'skipped', 'reason': 'no_data'}


@register_handler('reservation.updated')
def handle_reservation_updated(payload: dict, client: GuestyClient, db) -> dict:
    """Handle reservation updated events."""
    return handle_reservation_created(payload, client, db)


@register_handler('reservation.canceled')
def handle_reservation_canceled(payload: dict, client: GuestyClient, db) -> dict:
    """Handle reservation canceled events."""
    reservation = payload.get('reservation', {})
    res_id = reservation.get('_id') or reservation.get('id')
    
    # Fetch updated status from API
    try:
        full_res = client.api_get(f'/v1/reservations/{res_id}')
        if isinstance(full_res, dict):
            upsert_reservations(db, [full_res])
            return {'status': 'success', 'action': 'synced_canceled', 'id': res_id}
    except Exception as e:
        raise ValueError(f"Failed to sync canceled reservation: {e}")
    
    return {'status': 'skipped', 'reason': 'no_data'}


@register_handler('listing.calendar.updated')
@register_handler('calendar.updated.v2')
def handle_calendar_updated(payload: dict, client: GuestyClient, db) -> dict:
    """Handle calendar update events."""
    listing_id = payload.get('listingId')
    calendar = payload.get('calendar', {})
    listing = payload.get('listing', {})
    
    if not listing_id:
        listing_id = listing.get('_id') if listing else None
    
    if not listing_id:
        raise ValueError("No listing ID in payload")
    
    # For calendar updates, we just acknowledge and let the next sync handle it
    # This could be extended to fetch calendar data directly
    return {
        'status': 'success',
        'action': 'noted',
        'listing_id': listing_id,
        'date': calendar.get('date'),
        'status': calendar.get('status'),
    }


@register_handler('review.created')
def handle_review_created(payload: dict, client: GuestyClient, db) -> dict:
    """Handle review created events."""
    review = payload.get('review', {})
    review_id = review.get('_id') or review.get('id')
    
    if not review_id:
        raise ValueError("No review ID in payload")
    
    try:
        # Fetch full review from API
        full_review = client.api_get(f'/v1/reviews/{review_id}')
        if isinstance(full_review, dict):
            upsert_reviews(db, [full_review])
            return {'status': 'success', 'action': 'synced', 'id': review_id}
    except Exception as e:
        raise ValueError(f"Failed to sync review: {e}")
    
    return {'status': 'skipped', 'reason': 'no_data'}


@register_handler('guest.created')
@register_handler('guest.updated')
def handle_guest_updated(payload: dict, client: GuestyClient, db) -> dict:
    """Handle guest created/updated events."""
    guest = payload.get('guest', {})
    guest_id = guest.get('_id') or guest.get('id')
    
    if not guest_id:
        raise ValueError("No guest ID in payload")
    
    try:
        full_guest = client.api_get(f'/v1/guests/{guest_id}')
        if isinstance(full_guest, dict):
            upsert_guests(db, [full_guest])
            return {'status': 'success', 'action': 'synced', 'id': guest_id}
    except Exception as e:
        raise ValueError(f"Failed to sync guest: {e}")
    
    return {'status': 'skipped', 'reason': 'no_data'}


# =============================================================================
# COMMAND REGISTRATION
# =============================================================================

def register(subparsers):
    """Register webhooks commands with the argument parser."""
    # guesty webhooks (list) - keep for backward compatibility
    list_parser = subparsers.add_parser(
        'webhooks',
        help='List webhooks'
    )
    list_parser.set_defaults(func=run_list)
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    list_parser.add_argument('--live', action='store_true', help='Query live API')
    
    # guesty webhook (single webhook operations)
    webhook_parser = subparsers.add_parser(
        'webhook',
        help='Manage webhooks'
    )
    webhook_subparsers = webhook_parser.add_subparsers(dest='webhook_action')
    
    # List webhooks
    list_cmd = webhook_subparsers.add_parser('list', help='List webhooks')
    list_cmd.add_argument('--json', action='store_true', help='Output as JSON')
    list_cmd.add_argument('--live', action='store_true', help='Query live API')
    list_cmd.set_defaults(func=run_list)
    
    # Create webhook
    create_parser = webhook_subparsers.add_parser('create', help='Create webhook')
    create_parser.add_argument('--url', required=True, help='Webhook URL')
    create_parser.add_argument('--events', required=True, help='Comma-separated event types')
    create_parser.add_argument('--active', action='store_true', default=True, help='Active status')
    create_parser.add_argument('--dry-run', action='store_true', help='Show what would be created without calling API')
    create_parser.set_defaults(func=run_create)
    
    # Update webhook
    update_parser = webhook_subparsers.add_parser('update', help='Update webhook')
    update_parser.add_argument('id', help='Webhook ID')
    update_parser.add_argument('--events', required=True, help='Comma-separated event types')
    update_parser.set_defaults(func=run_update)
    
    # Delete webhook
    delete_parser = webhook_subparsers.add_parser('delete', help='Delete webhook')
    delete_parser.add_argument('id', help='Webhook ID')
    delete_parser.add_argument('--confirm', action='store_true', required=True, help='Confirm deletion (required)')
    delete_parser.set_defaults(func=run_delete)
    
    # Test webhook
    test_parser = webhook_subparsers.add_parser('test', help='Test webhook URL')
    test_parser.add_argument('id', help='Webhook ID')
    test_parser.set_defaults(func=run_test)
    
    # Watch webhooks (local server - legacy)
    watch_parser = webhook_subparsers.add_parser('watch', help='Watch for webhooks locally (legacy)')
    watch_parser.add_argument('--port', type=int, default=8080, help='Port to listen on')
    watch_parser.add_argument('--json', action='store_true', help='Output raw JSON payloads')
    watch_parser.set_defaults(func=run_watch)
    
    # =================================================================
    # NEW ENHANCED COMMANDS
    # =================================================================
    
    # Server command - Start webhook server with queue and persistence
    server_parser = webhook_subparsers.add_parser('server', help='Start webhook server with queue processing')
    server_parser.add_argument('--port', type=int, default=8080, help='Port to listen on')
    server_parser.add_argument('--persist', action='store_true', help='Persist events to database')
    server_parser.add_argument('--queue', action='store_true', help='Enable queue processing')
    server_parser.add_argument('--process-interval', type=int, default=30, help='Queue processing interval (seconds)')
    server_parser.add_argument('--auto-process', action='store_true', help='Auto-start queue processor')
    server_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    server_parser.set_defaults(func=run_server)
    
    # Process command - Process pending events in queue
    process_parser = webhook_subparsers.add_parser('process', help='Process pending webhook events')
    process_parser.add_argument('--limit', type=int, default=100, help='Max events to process')
    process_parser.add_argument('--type', help='Filter by event type')
    process_parser.add_argument('--dry-run', action='store_true', help='Show what would be processed')
    process_parser.add_argument('--continuous', action='store_true', help='Run continuously')
    process_parser.add_argument('--interval', type=int, default=30, help='Interval between runs (seconds)')
    process_parser.set_defaults(func=run_process)
    
    # Replay command - Replay a specific event
    replay_parser = webhook_subparsers.add_parser('replay', help='Replay a specific webhook event')
    replay_parser.add_argument('--event-id', required=True, help='Event ID to replay')
    replay_parser.add_argument('--force', action='store_true', help='Force replay even if completed')
    replay_parser.add_argument('--dry-run', action='store_true', help='Show what would be replayed')
    replay_parser.set_defaults(func=run_replay)
    
    # Log command - Show webhook event log
    log_parser = webhook_subparsers.add_parser('log', help='Show webhook event log')
    log_parser.add_argument('--limit', type=int, default=50, help='Number of events to show')
    log_parser.add_argument('--type', help='Filter by event type (e.g., reservation.created)')
    log_parser.add_argument('--status', help='Filter by status (pending, processing, completed, failed)')
    log_parser.add_argument('--json', action='store_true', help='Output as JSON')
    log_parser.add_argument('--stats', action='store_true', help='Show statistics')
    log_parser.set_defaults(func=run_log)
    
    # Stats command - Show webhook statistics
    stats_parser = webhook_subparsers.add_parser('stats', help='Show webhook processing statistics')
    stats_parser.add_argument('--json', action='store_true', help='Output as JSON')
    stats_parser.set_defaults(func=run_stats)
    
    # Default handler
    def default_handler(args):
        if hasattr(args, 'func') and args.func != default_handler:
            args.func(args)
        else:
            run_list(args)
    webhook_parser.set_defaults(func=default_handler)


def run(args):
    """Route to appropriate subcommand handler."""
    if hasattr(args, 'func'):
        args.func(args)
    else:
        print("Webhook action required: list, create, update, delete, test, watch, server, process, replay, log, stats")


# =============================================================================
# EXISTING COMMANDS
# =============================================================================

def run_list(args):
    """List webhooks."""
    config = load_config()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    client = GuestyClient(config)
    
    try:
        # Webhooks returns raw array
        webhooks = client.api_get('/v1/webhooks')
        if not isinstance(webhooks, list):
            webhooks = webhooks.get('results', [])
    except Exception as e:
        print(red(f"Error fetching webhooks: {e}"))
        return
    
    if args.json:
        print_json(webhooks)
        return
    
    if not webhooks:
        print(yellow("No webhooks configured"))
        return
    
    headers = ['ID', 'URL', 'Events', 'Active']
    rows = []
    for w in webhooks:
        events = w.get('events', [])
        event_str = ', '.join(events[:3])
        if len(events) > 3:
            event_str += f" (+{len(events) - 3} more)"
        
        rows.append([
            w.get('_id', 'N/A')[:16] + '...',
            w.get('url', 'N/A')[:40],
            event_str,
            green('Yes') if w.get('active') else red('No'),
        ])
    
    print(f"\n{bold('Webhooks')}")
    print_table(headers, rows)


def run_create(args):
    """Create a new webhook."""
    config = load_config()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    # Validate events
    events = [e.strip() for e in args.events.split(',')]
    invalid_events = [e for e in events if e not in VALID_WEBHOOK_EVENTS]
    
    if invalid_events:
        print(red(f"Invalid event(s): {', '.join(invalid_events)}"))
        print(yellow(f"Valid events: {', '.join(VALID_WEBHOOK_EVENTS)}"))
        return
    
    data = {
        'url': args.url,
        'events': events,
        'active': args.active,
    }
    
    if args.dry_run:
        print(yellow("DRY RUN - Would create webhook:"))
        print(f"  URL: {data['url']}")
        print(f"  Events: {', '.join(data['events'])}")
        print(f"  Active: {data['active']}")
        return
    
    client = GuestyClient(config)
    
    try:
        result = client.api_post('/v1/webhooks', data)
        print(green(f"✓ Webhook created"))
        print(f"  ID: {result.get('_id')}")
        print(f"  URL: {result.get('url')}")
        print(f"  Events: {', '.join(result.get('events', []))}")
    except Exception as e:
        print(red(f"Error creating webhook: {e}"))


def run_update(args):
    """Update a webhook (events only - Guesty removed URL update capability)."""
    config = load_config()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    # Validate events
    events = [e.strip() for e in args.events.split(',')]
    invalid_events = [e for e in events if e not in VALID_WEBHOOK_EVENTS]
    
    if invalid_events:
        print(red(f"Invalid event(s): {', '.join(invalid_events)}"))
        print(yellow(f"Valid events: {', '.join(VALID_WEBHOOK_EVENTS)}"))
        return
    
    data = {
        'events': events,
    }
    
    client = GuestyClient(config)
    
    try:
        result = client.api_put(f'/v1/webhooks/{args.id}', data)
        print(green(f"✓ Webhook updated"))
        print(f"  ID: {args.id}")
        print(f"  Events: {', '.join(result.get('events', []))}")
    except Exception as e:
        print(red(f"Error updating webhook: {e}"))


def run_delete(args):
    """Delete a webhook."""
    config = load_config()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    # Fetch webhook details first
    client = GuestyClient(config)
    
    try:
        webhooks = client.api_get('/v1/webhooks')
        if not isinstance(webhooks, list):
            webhooks = webhooks.get('results', [])
        
        webhook = None
        for w in webhooks:
            if w.get('_id') == args.id:
                webhook = w
                break
        
        if not webhook:
            print(red(f"Webhook '{args.id}' not found"))
            return
        
        # Show webhook details before deleting
        print(yellow("About to delete the following webhook:"))
        print(f"  ID: {webhook.get('_id')}")
        print(f"  URL: {webhook.get('url')}")
        print(f"  Events: {', '.join(webhook.get('events', []))}")
        print()
        
    except Exception as e:
        print(red(f"Error fetching webhook: {e}"))
        return
    
    try:
        client.api_delete(f'/v1/webhooks/{args.id}')
        print(green(f"✓ Webhook {args.id} deleted"))
    except Exception as e:
        print(red(f"Error deleting webhook: {e}"))


def run_test(args):
    """Send a test ping to the webhook URL."""
    config = load_config()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    # Fetch webhook details
    client = GuestyClient(config)
    
    try:
        webhooks = client.api_get('/v1/webhooks')
        if not isinstance(webhooks, list):
            webhooks = webhooks.get('results', [])
        
        webhook = None
        for w in webhooks:
            if w.get('_id') == args.id:
                webhook = w
                break
        
        if not webhook:
            print(red(f"Webhook '{args.id}' not found"))
            return
        
        url = webhook.get('url')
        print(f"Testing webhook URL: {url}")
        print()
        
    except Exception as e:
        print(red(f"Error fetching webhook: {e}"))
        return
    
    # Send test ping
    test_payload = {
        'event': 'test.ping',
        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z',
        'message': 'Test ping from guesty-cli'
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(test_payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            status = response.status
            if status == 200:
                print(green(f"✓ Webhook test successful (HTTP {status})"))
            else:
                print(yellow(f"⚠ Webhook returned HTTP {status}"))
    except urllib.error.HTTPError as e:
        print(red(f"✗ Webhook test failed: HTTP {e.code} - {e.reason}"))
    except urllib.error.URLError as e:
        print(red(f"✗ Webhook test failed: {e.reason}"))
    except Exception as e:
        print(red(f"✗ Webhook test failed: {e}"))


def run_watch(args):
    """Start local HTTP server to receive webhooks (legacy mode)."""
    port = args.port
    output_json = args.json
    
    def format_webhook_display(data, timestamp):
        """Format webhook payload for display."""
        event = data.get('event', 'unknown')
        
        # Format timestamp
        time_str = timestamp.strftime('%H:%M:%S')
        
        # Color by event type
        if event.startswith('reservation.'):
            event_color = cyan
        elif event.startswith('listing.'):
            event_color = green
        elif event.startswith('task.'):
            event_color = yellow
        elif event.startswith('guest.'):
            event_color = bold
        else:
            event_color = lambda x: x
        
        # Print header
        print(f"\n🔔 [{cyan(time_str)}] {event_color(event)}")
        
        # Extract key data based on event type
        if event.startswith('reservation.'):
            res = data.get('reservation', {})
            guest = data.get('guest', {})
            listing = data.get('listing', {})
            
            code = res.get('confirmationCode', 'N/A')
            guest_name = guest.get('fullName', 'N/A') if guest else 'N/A'
            listing_name = listing.get('nickname', res.get('listingId', 'N/A')) if listing else res.get('listingId', 'N/A')
            check_in = res.get('checkIn', 'N/A')
            check_out = res.get('checkOut', 'N/A')
            
            print(f"   Code: {bold(code)}  |  Guest: {guest_name}  |  Listing: {listing_name}")
            if check_in != 'N/A':
                print(f"   Check-in: {check_in[:10] if len(check_in) > 10 else check_in}  |  Check-out: {check_out[:10] if check_out and len(check_out) > 10 else check_out}")
        
        elif event == 'listing.calendar.updated' or event == 'calendar.updated.v2':
            listing = data.get('listing', {})
            calendar = data.get('calendar', {})
            
            listing_name = listing.get('nickname', data.get('listingId', 'N/A')) if listing else data.get('listingId', 'N/A')
            date = calendar.get('date', 'N/A') if calendar else 'N/A'
            status = calendar.get('status', 'N/A') if calendar else 'N/A'
            
            print(f"   Listing: {listing_name}  |  Date: {date}  |  Status: {status}")
        
        elif event.startswith('listing.'):
            listing = data.get('listing', {})
            listing_name = listing.get('nickname', listing.get('_id', 'N/A'))
            print(f"   Listing: {listing_name}")
        
        elif event.startswith('task.'):
            task = data.get('task', {})
            task_title = task.get('title', task.get('_id', 'N/A'))
            print(f"   Task: {task_title}")
        
        elif event.startswith('guest.'):
            guest = data.get('guest', {})
            guest_name = guest.get('fullName', guest.get('_id', 'N/A'))
            print(f"   Guest: {guest_name}")
        
        elif event.startswith('payments.'):
            payment = data.get('payment', {})
            amount = payment.get('amount', 'N/A')
            currency = payment.get('currency', 'USD')
            print(f"   Amount: {amount} {currency}")
    
    class WebhookHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass
        
        def do_POST(self):
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            timestamp = datetime.now()
            
            try:
                data = json.loads(body)
                
                if output_json:
                    print(json.dumps(data, indent=2))
                else:
                    format_webhook_display(data, timestamp)
                
            except json.JSONDecodeError:
                print(f"\n🔔 [{cyan(timestamp.strftime('%H:%M:%S'))}] {red('Invalid JSON')}")
                print(f"   {dim(body.decode('utf-8', errors='replace')[:200])}")
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok'}).encode())
        
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Webhook listener active')
    
    print(bold(f"Starting webhook listener on port {port}"))
    print(dim("Press Ctrl+C to stop"))
    print(dim(f"Listening for events: {', '.join(VALID_WEBHOOK_EVENTS[:5])}..."))
    print()
    
    with socketserver.TCPServer(("", port), WebhookHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print()
            print(yellow("\nWebhook listener stopped"))
            httpd.shutdown()


# =============================================================================
# ENHANCED SERVER COMMAND
# =============================================================================

def run_server(args):
    """Start enhanced webhook server with queue and persistence."""
    config = load_config()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    port = args.port
    persist = args.persist
    queue = args.queue
    process_interval = args.process_interval
    auto_process = args.auto_process
    verbose = args.verbose
    
    # Get database connection
    db_path = get_db_path(config)
    
    print(bold(f"🚀 Starting Enhanced Webhook Server"))
    print(f"   Port: {port}")
    print(f"   Persist: {green('Yes') if persist else red('No')}")
    print(f"   Queue: {green('Yes') if queue else red('No')}")
    print(f"   Auto-process: {green('Yes') if auto_process else red('No')}")
    print()
    
    # Initialize Guesty client
    client = GuestyClient(config)
    
    # Test API connection
    print("Testing Guesty API connection...")
    try:
        client.api_get('/v1/listings', params={'limit': 1})
        print(green("✓ API connection successful"))
    except Exception as e:
        print(red(f"✗ API connection failed: {e}"))
        return
    print()
    
    # Create HTTP request handler
    class WebhookServerHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            if verbose:
                print(dim(f"[{datetime.now().strftime('%H:%M:%S')}] {format % args}"))
        
        def do_POST(self):
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            timestamp = datetime.now()
            
            try:
                data = json.loads(body)
                event_type = data.get('event', 'unknown')
                
                # Generate event ID if not present
                event_id = data.get('eventId') or str(uuid.uuid4())
                
                # Extract related IDs
                reservation_id = None
                listing_id = None
                guest_id = None
                
                if 'reservation' in data:
                    reservation_id = data['reservation'].get('_id') or data['reservation'].get('id')
                if 'listing' in data:
                    listing_id = data['listing'].get('_id') or data['listing'].get('id')
                if 'guest' in data:
                    guest_id = data['guest'].get('_id') or data['guest'].get('id')
                
                # Also check top-level IDs
                reservation_id = reservation_id or data.get('reservationId')
                listing_id = listing_id or data.get('listingId')
                guest_id = guest_id or data.get('guestId')
                
                if persist:
                    # Store in database
                    db = get_db(config)
                    try:
                        insert_webhook_event(
                            db, event_id, event_type, data,
                            reservation_id, listing_id, guest_id
                        )
                        if verbose:
                            print(f"📥 Stored {cyan(event_type)} ({event_id[:8]})")
                    except Exception as e:
                        print(red(f"Failed to store event: {e}"))
                
                if queue and not persist:
                    # In-memory queue (not implemented - use persist)
                    pass
                
                # Immediate processing if not using queue
                if not queue and persist:
                    try:
                        process_single_event(event_id, data, event_type, client, db)
                        print(f"✓ Processed {green(event_type)} ({event_id[:8]})")
                    except Exception as e:
                        print(red(f"✗ Failed to process {event_type}: {e}"))
                else:
                    print(f"📨 Received {cyan(event_type)} ({event_id[:8]})")
                
                # Send 200 OK response
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'status': 'ok',
                    'event_id': event_id,
                }).encode())
                
            except json.JSONDecodeError:
                print(red(f"[{timestamp.strftime('%H:%M:%S')}] Invalid JSON received"))
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'error', 'message': 'Invalid JSON'}).encode())
        
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            # Get stats
            if persist:
                db = get_db(config)
                stats = get_webhook_stats(db)
            else:
                stats = {'status': 'running', 'persist': False}
            
            self.wfile.write(json.dumps({
                'status': 'ok',
                'message': 'Guesty Webhook Server',
                'stats': stats,
            }).encode())
    
    # Start queue processor if auto_process enabled
    processor_thread = None
    if auto_process and persist:
        def processor_loop():
            global _shutdown_requested
            while not _shutdown_requested:
                try:
                    db = get_db(config)
                    process_queue(db, client, limit=10, verbose=verbose)
                    time.sleep(process_interval)
                except Exception as e:
                    print(red(f"Queue processor error: {e}"))
                    time.sleep(5)
        
        processor_thread = threading.Thread(target=processor_loop, daemon=True)
        processor_thread.start()
        print(green("✓ Queue processor started"))
    
    # Start HTTP server
    print(bold(f"\n🌐 Server listening on port {port}"))
    print(dim("Press Ctrl+C to stop\n"))
    
    with socketserver.TCPServer(("", port), WebhookServerHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            global _shutdown_requested
            _shutdown_requested = True
            print()
            print(yellow("\n⚠️  Shutdown requested..."))
            httpd.shutdown()
            if processor_thread:
                processor_thread.join(timeout=5)
            print(green("✓ Server stopped"))


def process_single_event(event_id: str, payload: dict, event_type: str, 
                         client: GuestyClient, db, retry_count: int = 0) -> dict:
    """Process a single webhook event.
    
    Args:
        event_id: Event identifier
        payload: Event payload
        event_type: Event type string
        client: GuestyClient instance
        db: Database connection
        retry_count: Current retry attempt
        
    Returns:
        dict: Processing result
    """
    # Check if handler exists
    handler = EVENT_HANDLERS.get(event_type)
    
    if not handler:
        # No handler registered - mark as completed
        update_webhook_event_status(db, event_id, 'completed', 
                                    error_message=f'No handler for {event_type}')
        return {'status': 'no_handler', 'event_type': event_type}
    
    # Update status to processing
    update_webhook_event_status(db, event_id, 'processing')
    
    try:
        # Execute handler
        result = handler(payload, client, db)
        
        # Mark as completed
        update_webhook_event_status(db, event_id, 'completed')
        return {'status': 'success', 'result': result}
        
    except Exception as e:
        error_msg = str(e)
        max_retries = 3
        
        if retry_count < max_retries:
            # Mark for retry
            update_webhook_event_status(db, event_id, 'pending', error_msg, increment_attempts=True)
            
            # Exponential backoff
            backoff = 2 ** retry_count
            time.sleep(backoff)
            return process_single_event(event_id, payload, event_type, client, db, retry_count + 1)
        else:
            # Max retries reached
            update_webhook_event_status(db, event_id, 'failed', error_msg, increment_attempts=True)
            return {'status': 'failed', 'error': error_msg}


def process_queue(db, client: GuestyClient, limit: int = 100, verbose: bool = False) -> dict:
    """Process pending events in the queue.
    
    Args:
        db: Database connection
        client: GuestyClient instance
        limit: Maximum events to process
        verbose: Verbose output
        
    Returns:
        dict: Processing summary
    """
    events = get_pending_webhook_events(db, limit)
    
    if not events:
        return {'processed': 0, 'skipped': 0, 'failed': 0}
    
    processed = 0
    skipped = 0
    failed = 0
    
    for event in events:
        event_id = event['event_id']
        event_type = event['event_type']
        
        try:
            payload = json.loads(event['payload'])
            result = process_single_event(event_id, payload, event_type, client, db)
            
            if result['status'] == 'success':
                processed += 1
                if verbose:
                    print(f"✓ {event_type} ({event_id[:8]})")
            elif result['status'] == 'no_handler':
                skipped += 1
            else:
                failed += 1
                if verbose:
                    print(red(f"✗ {event_type} ({event_id[:8]}): {result.get('error', 'Unknown error')}"))
                    
        except Exception as e:
            failed += 1
            update_webhook_event_status(db, event_id, 'failed', str(e), increment_attempts=True)
            if verbose:
                print(red(f"✗ {event_type} ({event_id[:8]}): {e}"))
    
    return {'processed': processed, 'skipped': skipped, 'failed': failed}


# =============================================================================
# PROCESS COMMAND
# =============================================================================

def run_process(args):
    """Process pending webhook events."""
    config = load_config()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    limit = args.limit
    event_type = args.type
    dry_run = args.dry_run
    continuous = args.continuous
    interval = args.interval
    
    db = get_db(config)
    client = GuestyClient(config)
    
    if dry_run:
        print(yellow("DRY RUN - Would process pending events"))
    
    print(bold("Processing webhook queue"))
    print(f"Limit: {limit} events per batch")
    if event_type:
        print(f"Filter: {event_type}")
    print()
    
    while True:
        try:
            # Get pending events
            if event_type:
                cursor = db.execute(
                    "SELECT * FROM webhook_events WHERE status = 'pending' AND event_type = ? LIMIT ?",
                    (event_type, limit)
                )
                events = [dict(row) for row in cursor.fetchall()]
            else:
                events = get_pending_webhook_events(db, limit)
            
            if not events:
                if not continuous:
                    print(dim("No pending events to process"))
                    break
                print(dim(f"[{datetime.now().strftime('%H:%M:%S')}] No pending events, waiting..."))
                time.sleep(interval)
                continue
            
            print(f"Processing {len(events)} events...")
            
            if dry_run:
                for event in events:
                    print(f"  Would process: {event['event_type']} ({event['event_id'][:8]})")
                break
            
            # Process events
            result = process_queue(db, client, limit, verbose=True)
            
            print(f"\n{bold('Summary:')}")
            print(f"  Processed: {green(str(result['processed']))}")
            print(f"  Skipped: {yellow(str(result['skipped']))}")
            print(f"  Failed: {red(str(result['failed']))}")
            
            if not continuous:
                break
            
            if result['processed'] == 0 and result['failed'] == 0:
                time.sleep(interval)
            
        except KeyboardInterrupt:
            print()
            print(yellow("\nProcessing interrupted"))
            break


# =============================================================================
# REPLAY COMMAND
# =============================================================================

def run_replay(args):
    """Replay a specific webhook event."""
    config = load_config()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    event_id = args.event_id
    force = args.force
    dry_run = args.dry_run
    
    db = get_db(config)
    client = GuestyClient(config)
    
    # Get event from database
    event = get_webhook_event_by_id(db, event_id)
    
    if not event:
        print(red(f"Event '{event_id}' not found"))
        return
    
    print(bold(f"Replaying webhook event"))
    print(f"Event ID: {event['event_id']}")
    print(f"Type: {event['event_type']}")
    print(f"Status: {event['status']}")
    print(f"Attempts: {event['attempts']}/{event['max_attempts']}")
    print()
    
    if event['status'] == 'completed' and not force:
        print(yellow("Event already completed. Use --force to replay."))
        return
    
    if dry_run:
        print(yellow("DRY RUN - Would replay event"))
        print(f"  Handler: {EVENT_HANDLERS.get(event['event_type'], 'None')}")
        return
    
    # Reset status and replay
    update_webhook_event_status(db, event_id, 'pending', error_message=None)
    
    try:
        payload = json.loads(event['payload'])
        result = process_single_event(event_id, payload, event['event_type'], client, db)
        
        if result['status'] == 'success':
            print(green("✓ Event replayed successfully"))
            print(f"  Result: {result.get('result', {})}")
        elif result['status'] == 'no_handler':
            print(yellow("⚠ No handler registered for this event type"))
        else:
            print(red(f"✗ Failed: {result.get('error', 'Unknown error')}"))
            
    except Exception as e:
        print(red(f"✗ Error replaying event: {e}"))


# =============================================================================
# LOG COMMAND
# =============================================================================

def run_log(args):
    """Show webhook event log."""
    limit = args.limit
    event_type = args.type
    status = args.status
    output_json = args.json
    show_stats = args.stats
    
    db = get_db()
    
    if show_stats:
        run_stats(args)
        print()
    
    events = get_webhook_event_log(db, limit, event_type, status)
    
    if output_json:
        print_json(events)
        return
    
    if not events:
        print(yellow("No events found"))
        return
    
    headers = ['Time', 'Type', 'Status', 'Attempts', 'ID', 'Details']
    rows = []
    
    for event in events:
        # Format timestamp
        created = event['created_at']
        if created and len(created) > 16:
            created = created[11:16]  # HH:MM
        
        # Color status
        status_str = event['status']
        if status_str == 'completed':
            status_colored = green(status_str)
        elif status_str == 'failed':
            status_colored = red(status_str)
        elif status_str == 'processing':
            status_colored = yellow(status_str)
        else:
            status_colored = dim(status_str)
        
        # Truncate event type
        event_type_str = event['event_type']
        if len(event_type_str) > 25:
            event_type_str = event_type_str[:22] + '...'
        
        # Get details
        details = ""
        if event['reservation_id']:
            details = f"res:{event['reservation_id'][:8]}"
        elif event['listing_id']:
            details = f"lst:{event['listing_id'][:8]}"
        
        rows.append([
            created or 'N/A',
            event_type_str,
            status_colored,
            f"{event['attempts']}/{event['max_attempts']}",
            event['event_id'][:8] + '...',
            details,
        ])
    
    print(f"\n{bold(f'Webhook Events ({len(events)} shown)')}")
    print_table(headers, rows)


# =============================================================================
# STATS COMMAND
# =============================================================================

def run_stats(args):
    """Show webhook processing statistics."""
    output_json = args.json if hasattr(args, 'json') else False
    
    db = get_db()
    stats = get_webhook_stats(db)
    
    if output_json:
        print_json(stats)
        return
    
    print(f"\n{bold('Webhook Statistics')}")
    print(f"  Total events: {bold(str(stats.get('total', 0)))}")
    print(f"  {green('Completed')}: {stats.get('completed', 0)}")
    print(f"  {yellow('Pending')}: {stats.get('pending', 0)}")
    print(f"  {red('Failed')}: {stats.get('failed', 0)}")
    print(f"  {dim('Processing')}: {stats.get('processing', 0)}")
    
    # Show success rate
    total = stats.get('total', 0)
    completed = stats.get('completed', 0)
    if total > 0:
        rate = (completed / total) * 100
        print(f"\n  Success rate: {green(f'{rate:.1f}%')}")
