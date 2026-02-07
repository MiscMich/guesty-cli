"""
Authentication and setup commands for guesty-cli.
"""
import sys
from guesty_cli.core.config import load_config, save_config, get_db_path
from guesty_cli.core.client import GuestyClient
from guesty_cli.core.output import print_header, green, red, yellow, cyan, bold


def register(subparsers):
    """Register auth commands with the argument parser."""
    # guesty init
    init_parser = subparsers.add_parser(
        'init',
        help='Initialize guesty-cli with API credentials'
    )
    init_parser.set_defaults(func=run_init)
    init_parser.add_argument(
        '--skip-sync',
        action='store_true',
        help='Skip initial data sync'
    )
    
    # guesty auth
    auth_parser = subparsers.add_parser(
        'auth',
        help='Manage authentication and tokens'
    )
    auth_parser.set_defaults(func=run_auth)
    auth_parser.add_argument(
        '--refresh',
        action='store_true',
        help='Force token refresh'
    )
    auth_parser.add_argument(
        '--revoke',
        action='store_true',
        help='Clear cached token'
    )


def run(args):
    """Route to appropriate subcommand handler."""
    if hasattr(args, 'func'):
        args.func(args)
    else:
        print("No auth subcommand specified. Use 'guesty init' or 'guesty auth'")


def run_init(args):
    """Interactive setup wizard."""
    print_header("Guesty CLI Setup")
    print()
    print("Welcome to guesty-cli! Let's get you set up.")
    print("You'll need your Guesty API credentials (from Guesty Dashboard > Integrations > API)")
    print()
    
    # Get credentials interactively
    client_id = input("Client ID: ").strip()
    if not client_id:
        print(red("Error: Client ID is required"))
        sys.exit(1)
    
    client_secret = input("Client Secret: ").strip()
    if not client_secret:
        print(red("Error: Client Secret is required"))
        sys.exit(1)
    
    account_name = input("Account Name (optional, for display): ").strip()
    
    print()
    print("Testing connection to Guesty API...")
    
    # Create config dict
    config = {
        'client_id': client_id,
        'client_secret': client_secret,
        'account_name': account_name or 'Guesty Account'
    }
    
    # Test connection
    try:
        client = GuestyClient(config)
        if client.health_check():
            print(green("✓ Connection successful!"))
        else:
            print(red("✗ Connection failed - please check your credentials"))
            sys.exit(1)
    except Exception as e:
        print(red(f"✗ Connection failed: {e}"))
        sys.exit(1)
    
    # Save config
    try:
        save_config(config)
        print(green(f"✓ Configuration saved to ~/.guesty-cli/config.json"))
    except Exception as e:
        print(red(f"✗ Failed to save configuration: {e}"))
        sys.exit(1)
    
    print()
    print(f"Database location: {cyan(get_db_path())}")
    
    # Ask about initial sync
    if not args.skip_sync:
        print()
        response = input("Run initial data sync now? [Y/n]: ").strip().lower()
        if response in ('', 'y', 'yes'):
            print()
            print("Starting full sync (this may take a few minutes)...")
            # Import and run sync
            from guesty_cli.commands.sync import run_sync
            sync_args = type('Args', (), {'endpoint': None, 'full': True, 'history': False})()
            run_sync(sync_args)
        else:
            print("Skipped. Run 'guesty sync' later to sync data.")
    
    print()
    print(green("Setup complete! Run 'guesty status' to see your dashboard."))


def run_auth(args):
    """Show and manage token status."""
    config = load_config()
    
    if not config or not config.get('client_id'):
        print(red("Error: Not configured. Run 'guesty init' first."))
        sys.exit(1)
    
    client = GuestyClient(config)
    
    # Handle revoke
    if args.revoke:
        config.pop('cached_token', None)
        config.pop('token_expires_at', None)
        save_config(config)
        print(green("✓ Token revoked and cleared from cache"))
        return
    
    # Handle refresh
    if args.refresh:
        print("Refreshing token...")
        try:
            token = client.get_token(force_refresh=True)
            print(green(f"✓ Token refreshed successfully"))
            print(f"  Token: {token[:20]}...{token[-10:]}")
            return
        except Exception as e:
            print(red(f"✗ Failed to refresh token: {e}"))
            sys.exit(1)
    
    # Show token status
    print_header("Authentication Status")
    print()
    print(f"Account: {bold(config.get('account_name', 'Unknown'))}")
    print(f"Client ID: {config.get('client_id', 'Not set')[:20]}...")
    print()
    
    # Check token
    try:
        from datetime import datetime
        expires_at = config.get('token_expires_at')
        cached_token = config.get('cached_token')
        
        if not cached_token:
            print(f"Token Status: {yellow('Not cached')}")
            print("  Run any command that requires API access to fetch a token.")
        elif expires_at:
            expires = datetime.fromisoformat(expires_at)
            now = datetime.now()
            hours_remaining = (expires - now).total_seconds() / 3600
            
            if hours_remaining > 0:
                if hours_remaining > 4:
                    status_color = green
                elif hours_remaining > 1:
                    status_color = yellow
                else:
                    status_color = red
                
                print(f"Token Status: {status_color('Valid')}")
                print(f"  Expires: {expires.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"  Hours remaining: {status_color(f'{hours_remaining:.1f}')}")
            else:
                print(f"Token Status: {red('Expired')}")
                print(f"  Expired: {expires.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"  Hours ago: {abs(hours_remaining):.1f}")
        else:
            print(f"Token Status: {yellow('Unknown')}")
        
        if cached_token:
            print(f"  Token: {cached_token[:20]}...{cached_token[-10:]}")
            
    except Exception as e:
        print(f"Token Status: {red(f'Error: {e}')}")
