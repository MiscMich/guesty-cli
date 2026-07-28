"""Users management commands for guesty-cli."""
from guesty_cli.core.config import load_config
from guesty_cli.core.database import get_db
from guesty_cli.core.client import GuestyClient
from guesty_cli.core.output import (
    print_table, print_card, print_json, print_csv,
    bold, cyan, green, red, yellow, dim
)


def register(subparsers):
    """Register users commands with the argument parser."""
    # guesty users (list)
    list_parser = subparsers.add_parser(
        'users',
        help='List all team users'
    )
    list_parser.set_defaults(func=run_list)
    list_parser.add_argument('--active', action='store_true', help='Show only active users')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    list_parser.add_argument('--csv', action='store_true', help='Output as CSV')
    list_parser.add_argument('--live', action='store_true', help='Query live API')
    
    # guesty user (single user operations)
    user_parser = subparsers.add_parser(
        'user',
        help='Manage users'
    )
    user_subparsers = user_parser.add_subparsers(dest='user_action')
    
    # Get user details
    get_parser = user_subparsers.add_parser('get', help='Show details for a specific user')
    get_parser.add_argument('id_or_email', help='User ID or email')
    get_parser.add_argument('--json', action='store_true', help='Output as JSON')
    get_parser.add_argument('--live', action='store_true', help='Query live API')
    get_parser.set_defaults(func=run_get)
    
    # Default handler
    def default_handler(args):
        if hasattr(args, 'func') and args.func != default_handler:
            args.func(args)
        else:
            run_list(args)
    user_parser.set_defaults(func=default_handler)


def run(args):
    """Route to appropriate subcommand handler."""
    pass


def run_list(args):
    """List all users."""
    config = load_config()
    
    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        try:
            # Users returns {"results": []}
            data = client.api_get('users')
            users = data.get('results', []) if isinstance(data, dict) else data
        except Exception as e:
            print(red(f"Error fetching users: {e}"))
            return
    else:
        db = get_db()
        query = "SELECT * FROM users WHERE 1=1"
        params = []
        
        if args.active:
            query += " AND active = 1"
        
        query += " ORDER BY first_name, last_name"
        
        try:
            cursor = db.execute(query, params)
            users = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(red(f"Error querying database: {e}"))
            return
    
    if not users:
        print(yellow("No users found"))
        return
    
    # Format for output
    headers = ['Name', 'Email', 'Role', 'Active', 'Tasks Assigned']
    rows = []
    
    for u in users:
        # Count tasks assigned to this user
        tasks_count = 0
        user_id = u.get('id')
        
        if not args.live and user_id:
            try:
                db = get_db()
                cursor = db.execute(
                    "SELECT COUNT(*) FROM tasks WHERE assignee = ?",
                    (user_id,)
                )
                tasks_count = cursor.fetchone()[0]
            except:
                pass
        
        first_name = u.get('first_name') or u.get('firstName', '')
        last_name = u.get('last_name') or u.get('lastName', '')
        full_name = f"{first_name} {last_name}".strip() or u.get('fullName', 'N/A')
        
        # Determine active status
        is_active = u.get('active', u.get('isActive', 1))
        if isinstance(is_active, int):
            is_active = bool(is_active)
        
        rows.append([
            full_name,
            u.get('email', 'N/A'),
            u.get('role', 'N/A'),
            green('Yes') if is_active else red('No'),
            tasks_count if not args.live else '-',
        ])
    
    if args.json:
        print_json(users)
    elif args.csv:
        print_csv(headers, rows)
    else:
        print(f"\n{bold(f'Team Users ({len(users)} total)')}")
        print_table(headers, rows)


def run_get(args):
    """Get details for a specific user."""
    config = load_config()
    
    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        try:
            user = client.api_get(f'users/{args.id_or_email}')
        except:
            # Try to find by email
            try:
                data = client.api_get('users')
                users = data.get('results', []) if isinstance(data, dict) else data
                for u in users:
                    if u.get('email') == args.id_or_email:
                        user = u
                        break
                else:
                    print(red(f"User '{args.id_or_email}' not found"))
                    return
            except Exception as e:
                print(red(f"Error: {e}"))
                return
        tasks = []
    else:
        db = get_db()
        try:
            # Try as ID first
            cursor = db.execute("SELECT * FROM users WHERE id = ?", (args.id_or_email,))
            row = cursor.fetchone()
            
            if not row:
                # Try by email
                cursor = db.execute("SELECT * FROM users WHERE email = ?", (args.id_or_email,))
                row = cursor.fetchone()
            
            if not row:
                print(red(f"User '{args.id_or_email}' not found"))
                return
            
            user = dict(row)
            user_id = user.get('id')
            
            # Get tasks assigned to this user
            cursor = db.execute(
                """SELECT * FROM tasks
                   WHERE assigned_to = ?
                   ORDER BY created_at DESC""",
                (user_id,)
            )
            tasks = [dict(r) for r in cursor.fetchall()]
            
        except Exception as e:
            print(red(f"Error: {e}"))
            return
    
    if args.json:
        result = {
            'user': user,
            'tasks': tasks
        }
        print_json(result)
        return
    
    # Build full name
    first_name = user.get('first_name') or user.get('firstName', '')
    last_name = user.get('last_name') or user.get('lastName', '')
    full_name = f"{first_name} {last_name}".strip() or user.get('fullName', 'N/A')
    
    # Determine active status
    is_active = user.get('active', user.get('isActive', 1))
    if isinstance(is_active, int):
        is_active = bool(is_active)
    
    # Get last login from raw data if available
    last_login = 'N/A'
    raw_data = user.get('raw_data')
    if raw_data:
        import json
        try:
            raw = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
            last_login = raw.get('lastLoginAt', raw.get('lastLogin', 'N/A'))
            if last_login and last_login != 'N/A':
                # Format the date
                try:
                    from datetime import datetime
                    dt = last_login.replace('Z', '+00:00') if isinstance(last_login, str) else last_login
                    if isinstance(dt, str) and 'T' in dt:
                        dt = datetime.fromisoformat(dt)
                        last_login = dt.strftime('%Y-%m-%d %H:%M')
                except:
                    pass
        except:
            pass
    
    # Print detail card
    card_data = {
        'ID': user.get('id'),
        'Name': full_name,
        'Email': user.get('email', 'N/A'),
        'Role': user.get('role', 'N/A'),
        'Active': green('Yes') if is_active else red('No'),
        'Last Login': last_login,
        'Created': user.get('created_at') or user.get('createdAt', 'N/A'),
    }
    
    print_card(f"User: {card_data['Name']}", card_data, icon="👤")
    
    # Tasks assigned
    if tasks:
        print()
        print(bold("Assigned Tasks"))
        headers = ['ID', 'Title', 'Status', 'Priority', 'Due Date']
        rows = []
        for t in tasks:
            due_date = t.get('due_date') or t.get('dueDate', 'N/A')
            if due_date and due_date != 'N/A':
                due_date = str(due_date)[:10]
            
            # Colorize priority
            priority = t.get('priority', 'N/A')
            if priority == 'high':
                priority = red('High')
            elif priority == 'medium':
                priority = yellow('Medium')
            elif priority == 'low':
                priority = green('Low')
            
            rows.append([
                t.get('id', 'N/A')[:8],
                (t.get('title', 'N/A') or '')[:40],
                t.get('status', 'N/A'),
                priority,
                due_date or 'N/A',
            ])
        print_table(headers, rows)
    else:
        print()
        print(dim("No tasks assigned"))
