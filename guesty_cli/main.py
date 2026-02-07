#!/usr/bin/env python3
"""guesty-cli — Universal Command-Line Interface for Guesty"""

import sys
import argparse
from guesty_cli import __version__

def main():
    parser = argparse.ArgumentParser(
        prog='guesty',
        description='Universal CLI for Guesty PMS — manage your vacation rental operations from the terminal.',
        epilog='Run "guesty <command> --help" for details on each command.'
    )
    parser.add_argument('--version', action='version', version=f'guesty-cli v{__version__}')
    parser.add_argument('--no-color', action='store_true', help='Disable colored output')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Register all commands with graceful fallback for missing modules
    command_modules = [
        ('auth', 'Authentication and setup'),
        ('status', 'Dashboard overview'),
        ('listings', 'Property management'),
        ('reservations', 'Reservation management'),
        ('guests', 'Guest profiles'),
        ('owners', 'Owner management'),
        ('calendar', 'Calendar operations'),
        ('tasks', 'Task management'),
        ('reviews', 'Review management'),
        ('webhooks', 'Webhook management'),
        ('financials', 'Financial analytics'),
        ('search', 'Full-text search'),
        ('sync', 'Data synchronization'),
        ('export', 'Data export'),
    ]
    
    registered_count = 0
    for module_name, description in command_modules:
        try:
            module = __import__(f'guesty_cli.commands.{module_name}', fromlist=['register'])
            module.register(subparsers)
            registered_count += 1
        except ImportError:
            # Module not yet implemented — skip gracefully
            pass
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    # Set global no-color
    if args.no_color:
        import os
        os.environ['NO_COLOR'] = '1'
    
    # Check if command was registered
    if not hasattr(args, 'func'):
        print(f"Error: Command '{args.command}' is not yet implemented.", file=sys.stderr)
        sys.exit(1)
    
    # Run the command
    try:
        args.func(args)
    except KeyboardInterrupt:
        print('\nAborted.')
        sys.exit(130)
    except Exception as e:
        from guesty_cli.core.output import red
        print(red(f'\nError: {e}'))
        sys.exit(1)

if __name__ == '__main__':
    main()
