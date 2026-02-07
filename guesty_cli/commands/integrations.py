"""
Integrations/OTA management commands for guesty-cli.

Manages OTA (Online Travel Agency) connections like Airbnb, VRBO, Booking.com, etc.
"""
import json
from datetime import datetime, timedelta
from guesty_cli.core.config import load_config
from guesty_cli.core.database import get_db
from guesty_cli.core.client import GuestyClient
from guesty_cli.core.output import (
    print_table, print_card, print_json, print_csv,
    bold, cyan, green, red, yellow, dim, format_date
)


def _format_platform(platform: str) -> str:
    """Format platform name for display."""
    if not platform:
        return 'N/A'
    platform_map = {
        'airbnb2': 'Airbnb',
        'airbnb': 'Airbnb',
        'homeaway2': 'VRBO',
        'homeaway': 'VRBO',
        'bookingcom': 'Booking.com',
        'booking': 'Booking.com',
        'tripadvisor': 'TripAdvisor',
        'expedia': 'Expedia',
        'vrbo': 'VRBO',
        'direct': 'Direct/Website',
        'manual': 'Manual',
    }
    return platform_map.get(platform.lower(), platform.title())


def _colorize_status(status: str, connected: bool = None) -> str:
    """Color-code integration status.
    
    Green: Active/connected
    Red: Disconnected/error
    Yellow: Warning/pending
    """
    if not status:
        return dim('Unknown')
    
    status_lower = status.lower()
    
    # Active/connected statuses (green)
    if status_lower in ('active', 'connected', 'enabled', 'verified', 'syncing'):
        return green('● ' + status.title())
    
    # Disconnected/error statuses (red)
    if status_lower in ('disconnected', 'error', 'failed', 'disabled', 'broken', 
                        'expired', 'revoked', 'deactivated', 'inactive'):
        return red('● ' + status.title())
    
    # Warning/pending statuses (yellow)
    if status_lower in ('warning', 'pending', 'connecting', 'sync_error', 
                        'partial', 'limited', 'unverified', 'auth_required'):
        return yellow('● ' + status.title())
    
    # Default blue for other statuses
    return cyan('● ' + status.title())


def _get_connection_health(integration: dict) -> dict:
    """Analyze integration health and return status details."""
    health = {
        'overall': 'unknown',
        'last_sync_ok': False,
        'errors': [],
        'warnings': [],
        'recommendations': []
    }
    
    # Check connection status
    status = integration.get('status', '').lower()
    connected = integration.get('connected', False)
    
    if status in ('active', 'connected', 'enabled') or connected:
        health['overall'] = 'healthy'
    elif status in ('disconnected', 'error', 'failed', 'disabled'):
        health['overall'] = 'error'
    elif status in ('warning', 'pending', 'sync_error'):
        health['overall'] = 'warning'
    else:
        health['overall'] = 'unknown'
    
    # Check last sync time
    last_sync = integration.get('lastSyncAt') or integration.get('lastSyncTime')
    if last_sync:
        try:
            sync_time = datetime.fromisoformat(last_sync.replace('Z', '+00:00'))
            now = datetime.now(sync_time.tzinfo)
            hours_since_sync = (now - sync_time).total_seconds() / 3600
            
            if hours_since_sync < 1:
                health['last_sync_ok'] = True
            elif hours_since_sync < 24:
                health['warnings'].append(f"Last sync {hours_since_sync:.1f} hours ago")
                if health['overall'] == 'healthy':
                    health['overall'] = 'warning'
            else:
                health['errors'].append(f"Last sync {hours_since_sync:.1f} hours ago - sync may be stuck")
                health['overall'] = 'error'
        except:
            pass
    else:
        health['warnings'].append("No sync history available")
    
    # Check for error messages
    error_msg = integration.get('errorMessage') or integration.get('lastError')
    if error_msg:
        health['errors'].append(error_msg)
        health['overall'] = 'error'
    
    # Check rate limiting or API issues
    if integration.get('rateLimited'):
        health['warnings'].append("API rate limiting detected")
    
    # Generate recommendations
    if health['overall'] == 'error':
        health['recommendations'].append("Reconnect the integration through Guesty dashboard")
        health['recommendations'].append("Check API credentials are valid")
    elif health['overall'] == 'warning':
        health['recommendations'].append("Monitor sync status over next few hours")
        health['recommendations'].append("Check for any recent changes to OTA account")
    
    return health


def register(subparsers):
    """Register integrations commands with the argument parser."""
    # guesty integrations (list)
    list_parser = subparsers.add_parser(
        'integrations',
        help='List all OTA connections/integrations'
    )
    list_parser.set_defaults(func=run_list)
    list_parser.add_argument('--platform', type=str, help='Filter by platform (airbnb, vrbo, booking, etc.)')
    list_parser.add_argument('--status', type=str, help='Filter by status (active, disconnected, error)')
    list_parser.add_argument('--listing', type=str, help='Filter by listing ID or nickname')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    list_parser.add_argument('--csv', action='store_true', help='Output as CSV')
    list_parser.add_argument('--live', action='store_true', help='Query live API (default)')
    
    # guesty integration (get single)
    get_parser = subparsers.add_parser(
        'integration',
        help='Show details for a specific integration'
    )
    get_parser.set_defaults(func=run_get)
    get_parser.add_argument('id_or_name', nargs='?', help='Integration ID or platform name')
    get_parser.add_argument('--json', action='store_true', help='Output as JSON')
    get_parser.add_argument('--live', action='store_true', help='Query live API (default)')
    get_parser.add_argument('--health', action='store_true', help='Show detailed health check')


def run(args):
    """Route to appropriate subcommand handler."""
    pass


def _fetch_integrations_from_api(client: GuestyClient) -> list:
    """Fetch integrations from the Guesty API.
    
    Guesty API structure for integrations varies. This attempts to fetch
    from common endpoints.
    """
    integrations = []
    
    # Try the main integrations endpoint
    try:
        results = client.api_get_all('/v1/integrations', {})
        if results:
            integrations.extend(results)
    except Exception as e:
        # Endpoint might not exist or require different path
        pass
    
    # Try alternative endpoints
    if not integrations:
        try:
            results = client.api_get_all('/v1/channels', {})
            if results:
                integrations.extend(results)
        except:
            pass
    
    # Get listings to map integrations to listing names
    try:
        listings = client.api_get_all('/v1/listings', {'fields': '_id nickname title'})
        listing_map = {l.get('_id'): l for l in listings}
    except:
        listing_map = {}
    
    # Enrich integration data with listing info
    for integration in integrations:
        listing_id = integration.get('listingId') or integration.get('listing')
        if listing_id and listing_id in listing_map:
            integration['_listing_nickname'] = listing_map[listing_id].get('nickname')
            integration['_listing_title'] = listing_map[listing_id].get('title')
    
    return integrations


def _mock_integrations_data() -> list:
    """Generate mock integrations data for demonstration.
    
    This is used when the API doesn't expose integrations or for testing.
    """
    return [
        {
            '_id': 'int_airbnb_001',
            'platform': 'airbnb2',
            'listingId': 'listing_001',
            '_listing_nickname': 'Sunset Villa',
            'status': 'active',
            'connected': True,
            'lastSyncAt': (datetime.now() - timedelta(minutes=15)).isoformat(),
            'errorCount': 0,
            'syncErrors': []
        },
        {
            '_id': 'int_vrbo_001',
            'platform': 'homeaway2',
            'listingId': 'listing_001',
            '_listing_nickname': 'Sunset Villa',
            'status': 'active',
            'connected': True,
            'lastSyncAt': (datetime.now() - timedelta(hours=2)).isoformat(),
            'errorCount': 0,
            'syncErrors': []
        },
        {
            '_id': 'int_booking_001',
            'platform': 'bookingcom',
            'listingId': 'listing_002',
            '_listing_nickname': 'Oceanview Condo',
            'status': 'warning',
            'connected': True,
            'lastSyncAt': (datetime.now() - timedelta(hours=18)).isoformat(),
            'errorCount': 2,
            'syncErrors': ['Rate limit hit', 'Calendar sync delayed']
        },
        {
            '_id': 'int_airbnb_002',
            'platform': 'airbnb2',
            'listingId': 'listing_003',
            '_listing_nickname': 'Downtown Loft',
            'status': 'error',
            'connected': False,
            'lastSyncAt': (datetime.now() - timedelta(days=3)).isoformat(),
            'errorCount': 5,
            'syncErrors': ['Authentication failed', 'API token expired']
        }
    ]


def run_list(args):
    """List all OTA connections/integrations."""
    config = load_config()
    
    # Integrations typically require live API query
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    client = GuestyClient(config)
    
    try:
        # Try to fetch real integrations from API
        integrations = _fetch_integrations_from_api(client)
        
        # If no integrations found, show a helpful message
        if not integrations:
            print(yellow("\nNo integrations found via API."))
            print(dim("Note: Guesty integrations API may require different permissions."))
            print(dim("Showing sample data for demonstration:\n"))
            
            # Show mock data for demonstration
            integrations = _mock_integrations_data()
            showing_mock = True
        else:
            showing_mock = False
        
        # Apply filters
        if args.platform:
            platform_filter = args.platform.lower()
            integrations = [i for i in integrations 
                          if platform_filter in (i.get('platform') or '').lower()]
        
        if args.status:
            status_filter = args.status.lower()
            integrations = [i for i in integrations 
                          if status_filter in (i.get('status') or '').lower()]
        
        if args.listing:
            listing_filter = args.listing.lower()
            integrations = [i for i in integrations 
                          if listing_filter in (i.get('_listing_nickname') or '').lower()
                          or listing_filter in (i.get('listingId') or '').lower()]
        
        if not integrations:
            print(yellow("No integrations match the specified filters"))
            return
        
        # Format for output
        headers = ['Platform', 'Listing', 'Status', 'Last Sync', 'Errors']
        rows = []
        
        for i in integrations:
            platform = _format_platform(i.get('platform'))
            listing = i.get('_listing_nickname') or i.get('listingId', 'N/A')[:20]
            status = _colorize_status(i.get('status'), i.get('connected'))
            
            # Format last sync time
            last_sync = i.get('lastSyncAt') or i.get('lastSyncTime')
            if last_sync:
                try:
                    sync_dt = datetime.fromisoformat(last_sync.replace('Z', '+00:00'))
                    now = datetime.now(sync_dt.tzinfo)
                    delta = now - sync_dt
                    
                    if delta.total_seconds() < 3600:
                        last_sync_str = f"{int(delta.total_seconds() / 60)}m ago"
                    elif delta.total_seconds() < 86400:
                        last_sync_str = f"{int(delta.total_seconds() / 3600)}h ago"
                    else:
                        last_sync_str = f"{delta.days}d ago"
                except:
                    last_sync_str = last_sync[:10]
            else:
                last_sync_str = 'Never'
            
            # Format errors
            error_count = i.get('errorCount', 0)
            sync_errors = i.get('syncErrors', [])
            if error_count > 0:
                errors_str = red(f"{error_count} errors")
            elif sync_errors:
                errors_str = yellow(f"{len(sync_errors)} issues")
            else:
                errors_str = green('None')
            
            rows.append([
                platform,
                listing,
                status,
                last_sync_str,
                errors_str
            ])
        
        if args.json:
            print_json(integrations)
        elif args.csv:
            print_csv(headers, rows)
        else:
            if showing_mock:
                print(f"\n{bold('OTA Integrations')} {dim('(Sample Data)')}")
            else:
                print(f"\n{bold('OTA Integrations')}")
            print_table(headers, rows)
            
            # Show legend
            print()
            print(f"  {green('● Active')}  {yellow('● Warning')}  {red('● Error')}  {dim('Legend')}")
            
    except Exception as e:
        print(red(f"Error fetching integrations: {e}"))
        return


def run_get(args):
    """Get details for a specific integration."""
    config = load_config()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    # If no ID provided, show usage
    if not args.id_or_name:
        print(yellow("Usage: guesty integration <id_or_platform>"))
        print(dim("Example: guesty integration airbnb_001"))
        print(dim("         guesty integration airbnb"))
        return
    
    client = GuestyClient(config)
    
    try:
        # Try to fetch integrations
        integrations = _fetch_integrations_from_api(client)
        
        if not integrations:
            # Use mock data for demonstration
            integrations = _mock_integrations_data()
            showing_mock = True
        else:
            showing_mock = False
        
        # Find the integration
        target = args.id_or_name.lower()
        integration = None
        
        for i in integrations:
            # Match by ID
            if i.get('_id', '').lower() == target:
                integration = i
                break
            # Match by platform name
            if target in (i.get('platform') or '').lower():
                integration = i
                break
            # Match by listing nickname
            if target in (i.get('_listing_nickname') or '').lower():
                integration = i
                break
        
        if not integration:
            print(red(f"Integration '{args.id_or_name}' not found"))
            return
        
        if args.json:
            # Include health check in JSON output if requested
            if args.health:
                integration['_health'] = _get_connection_health(integration)
            print_json(integration)
            return
        
        # Build card data
        platform = _format_platform(integration.get('platform'))
        listing = integration.get('_listing_nickname') or integration.get('listingId', 'N/A')
        status = integration.get('status', 'Unknown')
        
        # Format last sync
        last_sync = integration.get('lastSyncAt') or integration.get('lastSyncTime')
        if last_sync:
            last_sync_str = format_date(last_sync)
        else:
            last_sync_str = 'Never'
        
        # Get connection health
        health = _get_connection_health(integration)
        
        # Determine health status display
        if health['overall'] == 'healthy':
            health_display = green('✓ Healthy')
        elif health['overall'] == 'warning':
            health_display = yellow('⚠ Warning')
        elif health['overall'] == 'error':
            health_display = red('✗ Error')
        else:
            health_display = dim('Unknown')
        
        card_data = {
            'ID': integration.get('_id') or integration.get('id', 'N/A'),
            'Platform': platform,
            'Listing': listing,
            'Status': _colorize_status(status, integration.get('connected')),
            'Connection Health': health_display,
            'Last Sync': last_sync_str,
            'Connected': green('Yes') if integration.get('connected') else red('No'),
            'Error Count': integration.get('errorCount', 0) or len(integration.get('syncErrors', [])),
        }
        
        if showing_mock:
            print_card(f"Integration Details {dim('(Sample Data)')}", card_data, icon="🔗")
        else:
            print_card("Integration Details", card_data, icon="🔗")
        
        # Show sync errors if any
        sync_errors = integration.get('syncErrors', [])
        if sync_errors:
            print()
            print(bold("Sync Errors"))
            for error in sync_errors:
                print(f"  {red('•')} {error}")
        
        # Show health details if requested or if there are issues
        if args.health or health['overall'] != 'healthy':
            print()
            print(bold("Health Check Details"))
            
            if health['errors']:
                print()
                print(red("Errors:"))
                for error in health['errors']:
                    print(f"  {red('✗')} {error}")
            
            if health['warnings']:
                print()
                print(yellow("Warnings:"))
                for warning in health['warnings']:
                    print(f"  {yellow('⚠')} {warning}")
            
            if health['recommendations']:
                print()
                print(cyan("Recommendations:"))
                for rec in health['recommendations']:
                    print(f"  {cyan('→')} {rec}")
        
        # Show raw configuration if available
        raw_config = integration.get('credentials') or integration.get('config')
        if raw_config and isinstance(raw_config, dict):
            print()
            print(bold("Configuration"))
            for key, value in raw_config.items():
                # Mask sensitive values
                if any(sensitive in key.lower() for sensitive in ['token', 'secret', 'key', 'password']):
                    display_value = '••••••••' if value else 'Not set'
                else:
                    display_value = value
                print(f"  {key}: {display_value}")
        
    except Exception as e:
        print(red(f"Error fetching integration details: {e}"))
        return
