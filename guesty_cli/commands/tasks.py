"""Tasks management commands for guesty-cli."""
from datetime import datetime
from guesty_cli.core.config import load_config
from guesty_cli.core.database import get_db
from guesty_cli.core.client import GuestyClient
from guesty_cli.core.output import (
    print_table, print_card, print_json, print_csv,
    bold, cyan, green, red, yellow, dim
)
from guesty_cli.utils.resolve import resolve_listing


def register(subparsers):
    """Register tasks commands with the argument parser."""
    # guesty tasks (list)
    list_parser = subparsers.add_parser(
        'tasks',
        help='List tasks'
    )
    list_parser.set_defaults(func=run_list)
    list_parser.add_argument('--status', type=str, help='Filter by status')
    list_parser.add_argument('--listing', type=str, help='Filter by listing ID')
    list_parser.add_argument('--priority', type=str, help='Filter by priority')
    list_parser.add_argument('--limit', type=int, default=20, help='Limit results')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    list_parser.add_argument('--csv', action='store_true', help='Output as CSV')
    list_parser.add_argument('--live', action='store_true', help='Query live API')
    
    # guesty task (single task operations)
    task_parser = subparsers.add_parser(
        'task',
        help='Manage a specific task'
    )
    task_subparsers = task_parser.add_subparsers(dest='task_action')
    
    # View task
    view_parser = task_subparsers.add_parser('view', help='View task details')
    view_parser.add_argument('id', help='Task ID')
    view_parser.add_argument('--json', action='store_true', help='Output as JSON')
    view_parser.add_argument('--live', action='store_true', help='Query live API')
    view_parser.set_defaults(func=run_view)
    
    # Create task
    create_parser = task_subparsers.add_parser('create', help='Create a new task')
    create_parser.add_argument('--title', required=True, help='Task title')
    create_parser.add_argument('--listing', required=True, help='Listing ID or nickname')
    create_parser.add_argument('--priority', default='medium', choices=['low', 'medium', 'high'])
    create_parser.add_argument('--due', help='Due date (YYYY-MM-DD)')
    create_parser.add_argument('--assignee', help='Assignee user ID')
    create_parser.add_argument('--description', help='Task description')
    create_parser.add_argument('--dry-run', action='store_true', help='Show what would be created without calling API')
    create_parser.set_defaults(func=run_create)
    
    # Update task
    update_parser = task_subparsers.add_parser('update', help='Update task')
    update_parser.add_argument('id', help='Task ID')
    update_parser.add_argument('--status', choices=['pending', 'in_progress', 'completed'])
    update_parser.add_argument('--priority', choices=['low', 'medium', 'high'])
    update_parser.add_argument('--assignee', help='Assignee user ID')
    update_parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without calling API')
    update_parser.set_defaults(func=run_update)
    
    # Complete task (shortcut)
    complete_parser = task_subparsers.add_parser('complete', help='Mark task as completed')
    complete_parser.add_argument('id', help='Task ID')
    complete_parser.add_argument('--dry-run', action='store_true', help='Show what would be done without calling API')
    complete_parser.set_defaults(func=run_complete)
    
    # Delete task
    delete_parser = task_subparsers.add_parser('delete', help='Delete a task')
    delete_parser.add_argument('id', help='Task ID')
    delete_parser.add_argument('--confirm', action='store_true', required=True, help='Confirm deletion (required)')
    delete_parser.set_defaults(func=run_delete)
    
    # Default handler
    task_parser.set_defaults(func=lambda a: print("Task action required: view, create, update, complete, or delete"))


def run(args):
    """Route to appropriate subcommand handler."""
    pass


def priority_color(priority):
    """Return color for priority level."""
    colors = {
        'urgent': red,
        'high': yellow,
        'medium': cyan,
        'low': lambda x: x,
    }
    return colors.get(priority, lambda x: x)


def run_list(args):
    """List tasks."""
    config = load_config()
    
    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        
        # Build filters
        filters = []
        if args.status:
            filters.append({"field": "status", "operator": "$eq", "value": args.status})
        if args.listing:
            filters.append({"field": "listingId", "operator": "$eq", "value": args.listing})
        if args.priority:
            filters.append({"field": "priority", "operator": "$eq", "value": args.priority})
        
        params = {'limit': 100}
        if filters:
            import json
            params['filters'] = json.dumps(filters)
        
        try:
            tasks = client.api_get_all('/v1/tasks', params)
        except Exception as e:
            print(red(f"Error fetching tasks: {e}"))
            return
    else:
        db = get_db()
        query = """SELECT t.*, l.nickname as listingName 
                   FROM tasks t 
                   LEFT JOIN listings l ON t.listingId = l.id 
                   WHERE 1=1"""
        params = []
        
        if args.status:
            query += " AND t.status = ?"
            params.append(args.status)
        if args.listing:
            query += " AND t.listingId = ?"
            params.append(args.listing)
        if args.priority:
            query += " AND t.priority = ?"
            params.append(args.priority)
        
        query += " ORDER BY t.dueDate, t.priority DESC LIMIT ?"
        params.append(args.limit)
        
        try:
            cursor = db.execute(query, params)
            tasks = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(red(f"Error querying database: {e}"))
            return
    
    if not tasks:
        print(yellow("No tasks found"))
        return
    
    # Format for output
    headers = ['Title', 'Listing', 'Status', 'Priority', 'Due', 'Assignee']
    rows = []
    for t in tasks:
        p = t.get('priority', 'medium') or 'medium'
        pc = priority_color(p)
        
        due = t.get('dueDate') or 'N/A'
        if due and len(str(due)) > 10:
            due = str(due)[:10]
        
        title = t.get('title') or 'N/A'
        listing_name = t.get('listingName') or t.get('listingId') or 'N/A'
        status = t.get('status') or 'N/A'
        assignee = t.get('assignee') or 'Unassigned'
        
        rows.append([
            title[:30],
            listing_name[:25],
            status,
            pc(p),
            due,
            assignee[:15],
        ])
    
    if args.json:
        print_json(tasks)
    elif args.csv:
        print_csv(headers, rows)
    else:
        print(f"\n{bold('Tasks')}")
        print_table(headers, rows)


def run_view(args):
    """View task details."""
    config = load_config()
    
    if args.live:
        if not config:
            print(red("Error: Not configured. Run 'guesty init' first."))
            return
        client = GuestyClient(config)
        try:
            task = client.api_get(f'/v1/tasks/{args.id}')
        except Exception as e:
            print(red(f"Error fetching task: {e}"))
            return
    else:
        db = get_db()
        try:
            cursor = db.execute("SELECT * FROM tasks WHERE id = ?", (args.id,))
            row = cursor.fetchone()
            if not row:
                print(red(f"Task '{args.id}' not found"))
                return
            task = dict(row)
        except Exception as e:
            print(red(f"Error: {e}"))
            return
    
    if args.json:
        print_json(task)
        return
    
    # Print detail card
    card_data = {
        'ID': task.get('id'),
        'Title': task.get('title', 'N/A'),
        'Description': task.get('description', 'N/A'),
        'Status': task.get('status', 'N/A'),
        'Priority': priority_color(task.get('priority', 'medium'))(task.get('priority', 'N/A')),
        'Listing': task.get('listingId', 'N/A'),
        'Due Date': task.get('dueDate', 'N/A'),
        'Assignee': task.get('assignee', 'Unassigned'),
        'Created': task.get('createdAt', 'N/A'),
    }
    
    print_card(f"Task: {task.get('title', 'Unknown')}", card_data)


def run_create(args):
    """Create a new task."""
    config = load_config()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    # Resolve listing
    db = get_db()
    listing = resolve_listing(db, args.listing)
    if not listing:
        print(red(f"Error: Listing '{args.listing}' not found"))
        print(yellow("Tip: Use 'guesty listings' to see available listings"))
        return
    
    data = {
        'title': args.title,
        'priority': args.priority,
        'listingId': listing['id'],
    }
    
    if args.due:
        data['dueDate'] = f"{args.due}T00:00:00.000Z"
    if args.assignee:
        data['assigneeId'] = args.assignee
    if args.description:
        data['description'] = args.description
    
    if args.dry_run:
        print(yellow("DRY RUN - Would create task:"))
        print(f"  Title: {data['title']}")
        print(f"  Listing: {listing['nickname']} ({listing['id']})")
        print(f"  Priority: {data['priority']}")
        if 'dueDate' in data:
            print(f"  Due: {args.due}")
        if 'assigneeId' in data:
            print(f"  Assignee: {data['assigneeId']}")
        if 'description' in data:
            print(f"  Description: {data['description']}")
        return
    
    client = GuestyClient(config)
    
    try:
        result = client.api_post('/v1/tasks', data)
        print(green(f"✓ Task created: {result.get('title')}"))
        print(f"  ID: {result.get('_id')}")
        print(f"  Listing: {listing['nickname']}")
    except Exception as e:
        print(red(f"Error creating task: {e}"))


def run_update(args):
    """Update a task."""
    config = load_config()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    data = {}
    
    if args.status:
        data['status'] = args.status
    if args.priority:
        data['priority'] = args.priority
    if args.assignee:
        data['assigneeId'] = args.assignee
    
    if not data:
        print(yellow("No changes specified"))
        return
    
    if args.dry_run:
        print(yellow(f"DRY RUN - Would update task {args.id}:"))
        for key, value in data.items():
            print(f"  {key}: {value}")
        return
    
    client = GuestyClient(config)
    
    try:
        result = client.api_put(f'/v1/tasks/{args.id}', data)
        print(green(f"✓ Task updated: {result.get('title')}"))
    except Exception as e:
        print(red(f"Error updating task: {e}"))


def run_complete(args):
    """Mark a task as completed (shortcut for update --status completed)."""
    config = load_config()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    data = {'status': 'completed'}
    
    if args.dry_run:
        print(yellow(f"DRY RUN - Would mark task {args.id} as completed"))
        return
    
    client = GuestyClient(config)
    
    try:
        result = client.api_put(f'/v1/tasks/{args.id}', data)
        print(green(f"✓ Task completed: {result.get('title')}"))
    except Exception as e:
        print(red(f"Error completing task: {e}"))


def run_delete(args):
    """Delete a task."""
    config = load_config()
    
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    
    # Fetch task details first
    client = GuestyClient(config)
    
    try:
        task = client.api_get(f'/v1/tasks/{args.id}')
    except Exception as e:
        print(red(f"Error fetching task: {e}"))
        return
    
    # Show task details before deleting
    print(yellow("About to delete the following task:"))
    print(f"  ID: {task.get('_id')}")
    print(f"  Title: {task.get('title')}")
    print(f"  Status: {task.get('status')}")
    print(f"  Priority: {task.get('priority')}")
    print()
    
    client = GuestyClient(config)
    
    try:
        client.api_delete(f'/v1/tasks/{args.id}')
        print(green(f"✓ Task {args.id} deleted"))
    except Exception as e:
        print(red(f"Error deleting task: {e}"))
