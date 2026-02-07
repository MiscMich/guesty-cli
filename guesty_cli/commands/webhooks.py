"""Webhooks management commands for guesty-cli."""
import json
import urllib.request
import urllib.error
from datetime import datetime
from guesty_cli.core.config import load_config
from guesty_cli.core.client import GuestyClient
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
]


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
    
    # Watch webhooks (local server)
    watch_parser = webhook_subparsers.add_parser('watch', help='Watch for webhooks locally')
    watch_parser.add_argument('--port', type=int, default=8080, help='Port to listen on')
    watch_parser.add_argument('--json', action='store_true', help='Output raw JSON payloads')
    watch_parser.set_defaults(func=run_watch)
    
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
        print("Webhook action required: list, create, update, delete, test, or watch")


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
        'timestamp': datetime.utcnow().isoformat() + 'Z',
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
    """Start local HTTP server to receive webhooks."""
    import http.server
    import socketserver
    import threading
    import sys
    
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
            # Suppress default logging
            pass
        
        def do_POST(self):
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            timestamp = datetime.now()
            
            try:
                data = json.loads(body)
                
                if output_json:
                    # Raw JSON output
                    print(json.dumps(data, indent=2))
                else:
                    # Formatted display
                    format_webhook_display(data, timestamp)
                
            except json.JSONDecodeError:
                print(f"\n🔔 [{cyan(timestamp.strftime('%H:%M:%S'))}] {red('Invalid JSON')}")
                print(f"   {dim(body.decode('utf-8', errors='replace')[:200])}")
            
            # Send 200 OK response
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
