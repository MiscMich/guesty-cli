"""
Authentication and setup commands for guesty-cli.
"""
import os
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

    # guesty auth-token (agent-friendly: get a valid token, print it, done)
    token_parser = subparsers.add_parser(
        'auth-token',
        help='Print a valid access token (for agents: use with --access-token on subsequent calls)'
    )
    token_parser.set_defaults(func=run_auth_token)

    # guesty auth-export
    export_parser = subparsers.add_parser(
        'auth-export',
        help='Export credentials to JSON file (for transferring between machines)'
    )
    export_parser.set_defaults(func=run_auth_export)
    export_parser.add_argument('--out', type=str, default='-', help='Output file path (default: stdout)')
    export_parser.add_argument('--include-secrets', action='store_true', help='Include client_secret in export (dangerous)')

    # guesty auth-import
    import_parser = subparsers.add_parser(
        'auth-import',
        help='Import credentials from JSON file'
    )
    import_parser.set_defaults(func=run_auth_import)
    import_parser.add_argument('file', type=str, help='JSON file path or - for stdin')


def run(args):
    """Route to appropriate subcommand handler."""
    if hasattr(args, 'func'):
        args.func(args)
    else:
        print("No auth subcommand specified. Use 'guesty init' or 'guesty auth'")


def run_init(args):
    """Interactive setup wizard."""
    # Support non-interactive auth via env vars or flags
    no_input = os.environ.get('GUESTY_NO_INPUT')
    client_id = os.environ.get('GUESTY_CLIENT_ID', '').strip()
    client_secret = os.environ.get('GUESTY_CLIENT_SECRET', '').strip()

    if no_input and (not client_id or not client_secret):
        print(red("Error: --no-input requires GUESTY_CLIENT_ID and GUESTY_CLIENT_SECRET environment variables"))
        sys.exit(1)

    print_header("Guesty CLI Setup")
    print()
    print("Welcome to guesty-cli! Let's get you set up.")
    print("You'll need your Guesty API credentials (from Guesty Dashboard > Integrations > API)")
    print()

    # Get credentials (from env or interactively)
    if not client_id:
        client_id = input("Client ID: ").strip()
    if not client_id:
        print(red("Error: Client ID is required"))
        sys.exit(1)

    if not client_secret:
        client_secret = input("Client Secret: ").strip()
    if not client_secret:
        print(red("Error: Client Secret is required"))
        sys.exit(1)

    account_name = os.environ.get('GUESTY_ACCOUNT_NAME', '').strip()
    if not account_name and not no_input:
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
    
    # Save config — try keychain for secrets first
    try:
        from guesty_cli.core.secrets import store_secret, is_keyring_available
        if is_keyring_available():
            backend = store_secret('client_secret', client_secret)
            if backend == 'keychain':
                config['client_secret'] = ''  # Don't store in plaintext
                print(green("✓ Client secret stored in OS keychain"))
            else:
                print(yellow("⚠ Keychain unavailable — secret stored in config file"))
        save_config(config)
        print(green(f"✓ Configuration saved to ~/.guesty-cli/config.json"))
    except Exception as e:
        print(red(f"✗ Failed to save configuration: {e}"))
        sys.exit(1)
    
    print()
    print(f"Database location: {cyan(get_db_path())}")
    
    # Ask about initial sync
    if not args.skip_sync and not no_input:
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
    elif not args.skip_sync and no_input:
        print("Skipped sync (--no-input mode). Run 'guesty sync' later.")
    
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
        from guesty_cli.core.output import is_json, is_plain
        from guesty_cli.core.exit_codes import exit_for_error
        if not is_json() and not is_plain():
            print(yellow("⚠ Guesty allows max 5 token refreshes per 24h (shared across all API key users)"))
            print("Refreshing token...")
        try:
            token = client.get_token(force_refresh=True)
            if is_json():
                import json as _json
                print(_json.dumps({"status": "ok", "token": f"{token[:20]}...{token[-10:]}"}))
            elif is_plain():
                print(f"status\tok")
                print(f"token\t{token[:20]}...{token[-10:]}")
            else:
                print(green(f"✓ Token refreshed successfully"))
                print(f"  Token: {token[:20]}...{token[-10:]}")
            return
        except Exception as e:
            code = exit_for_error(e)
            if is_json():
                import json as _json
                print(_json.dumps({"error": str(e), "exit_code": code}))
            elif is_plain():
                print(f"error\t{e}")
            else:
                print(red(f"✗ Failed to refresh token: {e}"))
            sys.exit(code)
    
    # Show token status (default action when no flags)
    print_header("Authentication Status")
    print()
    print(f"Account: {bold(config.get('account_name', 'Unknown'))}")
    print(f"Client ID: {config.get('client_id', 'Not set')[:20]}...")
    print()
    
    # Check token
    try:
        from datetime import datetime
        expires_at = config.get('token_expires_at')
        cached_token = config.get('cached_token') or config.get('token')
        
        if not cached_token:
            print(f"Token Status: {yellow('Not cached')}")
            print("  Run any command that requires API access to fetch a token.")
        elif expires_at:
            from datetime import timezone
            expires = datetime.fromisoformat(expires_at)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
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


def run_auth_token(args):
    """Print a valid access token for agent use.

    Agent workflow:
      1. TOKEN=$(guesty auth-token)
      2. guesty --access-token "$TOKEN" listings list
      3. guesty --access-token "$TOKEN" reservations list
      ... (no additional token requests, all 5 daily slots preserved)
    """
    from guesty_cli.core.output import is_json, is_plain
    from guesty_cli.core.exit_codes import exit_for_error

    config = load_config()
    if not config.get('client_id'):
        print(red("Error: Not configured. Run 'guesty init' first."), file=sys.stderr)
        sys.exit(1)

    client = GuestyClient(config)
    try:
        token = client.get_token()
    except Exception as e:
        code = exit_for_error(e)
        if is_json():
            import json as _json
            print(_json.dumps({"error": str(e), "exit_code": code}), file=sys.stderr)
        else:
            print(str(e), file=sys.stderr)
        sys.exit(code)

    if is_json():
        import json as _json
        from datetime import datetime, timezone
        expires = config.get('token_expires_at', '')
        print(_json.dumps({
            "access_token": token,
            "expires_at": expires,
            "usage": "guesty --access-token TOKEN <command>",
        }))
    elif is_plain():
        print(token)
    else:
        # Human mode — just the token, suitable for: TOKEN=$(guesty auth-token)
        print(token)


def run_auth_export(args):
    """Export credentials (without secrets) for transfer."""
    import json as _json
    config = load_config()

    export_data = {
        "guesty_cli_version": "0.2.0",
        "account_name": config.get('account_name', ''),
        "client_id": config.get('client_id', ''),
        "api_base_url": config.get('api_base_url', 'https://open-api.guesty.com'),
    }

    # Include secret only if user explicitly confirms
    if getattr(args, 'include_secrets', False) or os.environ.get('GUESTY_NO_INPUT'):
        export_data['client_secret'] = config.get('client_secret', '')
        print("WARNING: exported file contains client_secret -- keep it safe!", file=sys.stderr)

    output = _json.dumps(export_data, indent=2)

    if args.out == '-':
        print(output)
    else:
        with open(args.out, 'w') as f:
            f.write(output)
        os.chmod(args.out, 0o600)
        print(green(f"Credentials exported to {args.out}"))


def run_auth_import(args):
    """Import credentials from JSON file."""
    import json as _json

    if args.file == '-':
        data = _json.loads(sys.stdin.read())
    else:
        with open(args.file, 'r') as f:
            data = _json.load(f)

    config = load_config()

    for key in ('client_id', 'client_secret', 'account_name', 'api_base_url'):
        if key in data and data[key]:
            config[key] = data[key]

    save_config(config)
    print(green("Credentials imported successfully"))

    # Test connection
    try:
        client = GuestyClient(config)
        if client.health_check():
            print(green("Connection verified"))
        else:
            print(yellow("Could not verify connection -- check credentials"))
    except Exception as e:
        print(yellow(f"Connection test failed: {e}"))
