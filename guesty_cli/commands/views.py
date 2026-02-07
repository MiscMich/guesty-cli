"""Views management commands for guesty-cli.

This module provides access to Guesty's built-in reports/views via the /v1/views endpoint.
These are READ-ONLY endpoints that return pre-built reports for reservations and listings.
"""
import argparse
import json
from guesty_cli.core.config import load_config
from guesty_cli.core.client import GuestyClient
from guesty_cli.core.output import (
    print_table, print_card, print_json,
    bold, cyan, green, red, yellow, dim
)


VALID_SECTIONS = {'reservations', 'listings'}


def register(subparsers):
    """Register views commands with the argument parser."""
    views_parser = subparsers.add_parser(
        'views',
        help='Access Guesty built-in reports and views'
    )
    views_parser.set_defaults(func=run_views)
    views_parser.add_argument(
        '--section',
        type=str,
        required=True,
        choices=['reservations', 'listings'],
        help='Report section to retrieve (reservations or listings)'
    )
    views_parser.add_argument(
        '--json',
        action='store_true',
        help='Output as JSON'
    )
    views_parser.add_argument(
        '--live',
        action='store_true',
        help='Query live API (default: uses cached data if available)'
    )


def run_views(args):
    """Fetch and display Guesty views/reports."""
    config = load_config()

    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return

    section = args.section.lower()
    
    if section not in VALID_SECTIONS:
        print(red(f"Error: Invalid section '{section}'. Must be one of: {', '.join(VALID_SECTIONS)}"))
        return

    # Always use live API for views (no local cache for this endpoint)
    client = GuestyClient(config)
    
    try:
        # Build query parameters
        params = {'section': section}
        
        # Make API request to views endpoint
        response = client.api_get('views', params=params)
        
        if args.json:
            print_json(response)
            return
        
        # Format output based on section type
        if section == 'reservations':
            _display_reservations_view(response)
        elif section == 'listings':
            _display_listings_view(response)
            
    except Exception as e:
        print(red(f"Error fetching views: {e}"))
        return


def _display_reservations_view(data):
    """Display reservations view in formatted table."""
    # The API returns a response with results array
    results = data.get('results', []) if isinstance(data, dict) else data
    
    if not results:
        print(yellow("No reservation views found"))
        return
    
    print(f"\n{bold('Guesty Reservations Report')}")
    print(f"{dim(f'Found {len(results)} reservation view(s)')}")
    
    # Display summary for each view/report
    for i, view in enumerate(results, 1):
        if isinstance(view, dict):
            view_name = view.get('name', view.get('title', f'View {i}'))
            view_id = view.get('_id', view.get('id', 'N/A'))
            view_type = view.get('type', 'N/A')
            
            print(f"\n{cyan(f'[{i}]')} {bold(view_name)}")
            print(f"    ID: {view_id}")
            print(f"    Type: {view_type}")
            
            # Display any additional metadata
            if 'createdAt' in view:
                print(f"    Created: {view['createdAt']}")
            if 'updatedAt' in view:
                print(f"    Updated: {view['updatedAt']}")
            
            # Display filters if present
            filters = view.get('filters', {})
            if filters:
                print(f"    Filters: {json.dumps(filters, indent=2)}")
        else:
            # Handle simple string or array items
            print(f"\n{cyan(f'[{i}]')} {view}")


def _display_listings_view(data):
    """Display listings view in formatted table."""
    # The API returns a response with results array
    results = data.get('results', []) if isinstance(data, dict) else data
    
    if not results:
        print(yellow("No listing views found"))
        return
    
    print(f"\n{bold('Guesty Listings Report')}")
    print(f"{dim(f'Found {len(results)} listing view(s)')}")
    
    # Display summary for each view/report
    for i, view in enumerate(results, 1):
        if isinstance(view, dict):
            view_name = view.get('name', view.get('title', f'View {i}'))
            view_id = view.get('_id', view.get('id', 'N/A'))
            view_type = view.get('type', 'N/A')
            
            print(f"\n{cyan(f'[{i}]')} {bold(view_name)}")
            print(f"    ID: {view_id}")
            print(f"    Type: {view_type}")
            
            # Display any additional metadata
            if 'createdAt' in view:
                print(f"    Created: {view['createdAt']}")
            if 'updatedAt' in view:
                print(f"    Updated: {view['updatedAt']}")
            
            # Display filters if present
            filters = view.get('filters', {})
            if filters:
                print(f"    Filters: {json.dumps(filters, indent=2)}")
            
            # Display property count if available
            if 'propertyCount' in view:
                print(f"    Properties: {view['propertyCount']}")
            elif 'listingCount' in view:
                print(f"    Listings: {view['listingCount']}")
        else:
            # Handle simple string or array items
            print(f"\n{cyan(f'[{i}]')} {view}")
