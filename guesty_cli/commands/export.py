"""
Export data commands for guesty-cli.
"""
import json
import csv
import sys
from guesty_cli.core.database import get_db
from guesty_cli.core.output import bold, green, red, yellow


def register(subparsers):
    """Register export command with the argument parser."""
    parser = subparsers.add_parser(
        'export',
        help='Export data to file'
    )
    parser.set_defaults(func=run)
    parser.add_argument('table', help='Table to export (listings, reservations, guests, owners, reviews, tasks, financials)')
    parser.add_argument('--format', choices=['csv', 'json'], default='csv', help='Export format')
    parser.add_argument('--output', type=str, help='Output file path')
    parser.add_argument('--where', type=str, help='SQL WHERE clause filter')


def run(args):
    """Export data to file."""
    table = args.table
    fmt = args.format
    
    # Validate table
    valid_tables = ['listings', 'reservations', 'guests', 'owners', 'reviews', 'tasks', 'financials', 'webhooks', 'users']
    if table not in valid_tables:
        print(red(f"Invalid table: {table}"))
        print(f"Valid tables: {', '.join(valid_tables)}")
        return
    
    # Determine output path
    if args.output:
        output_path = args.output
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = f"{table}_{timestamp}.{fmt}"
    
    # Fetch data
    db = get_db()
    
    try:
        query = f"SELECT * FROM {table}"
        params = []
        
        if args.where:
            query += f" WHERE {args.where}"
        
        cursor = db.execute(query, params)
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
    except Exception as e:
        print(red(f"Error querying database: {e}"))
        return
    
    if not rows:
        print(yellow(f"No data found in {table}"))
        return
    
    # Export based on format
    try:
        if fmt == 'json':
            export_json(rows, columns, output_path)
        else:
            export_csv(rows, columns, output_path)
        
        print(green(f"✓ Exported {len(rows)} records to {output_path}"))
    except Exception as e:
        print(red(f"Error exporting: {e}"))


def export_json(rows, columns, output_path):
    """Export to JSON file."""
    data = []
    for row in rows:
        row_dict = dict(zip(columns, row))
        # Parse JSON fields
        for key, value in row_dict.items():
            if isinstance(value, str) and (value.startswith('{') or value.startswith('[')):
                try:
                    row_dict[key] = json.loads(value)
                except:
                    pass
        data.append(row_dict)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, default=str)


def export_csv(rows, columns, output_path):
    """Export to CSV file."""
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)


from datetime import datetime
