"""Schema introspection command — machine-readable CLI structure for agents."""
import json
import sys
from guesty_cli import __version__


def register(subparsers):
    parser = subparsers.add_parser(
        'schema',
        help='Print machine-readable CLI schema (for AI agents and automation)'
    )
    parser.set_defaults(func=run_schema)
    parser.add_argument('target', nargs='?', help='Show schema for a specific command only')
    parser.add_argument('--include-hidden', action='store_true', help='Include hidden commands')


def run_schema(args):
    """Dump the full CLI schema as JSON."""
    schema = {
        "schema_version": 1,
        "name": "guesty",
        "version": __version__,
        "description": "Universal CLI for Guesty PMS",
        "global_flags": [
            {"name": "--json", "short": None, "type": "bool", "help": "Output as JSON", "default": False},
            {"name": "--plain", "short": "-p", "type": "bool", "help": "Output stable TSV (no colors)", "default": False},
            {"name": "--no-color", "short": None, "type": "bool", "help": "Disable colored output", "default": False},
            {"name": "--select", "short": None, "type": "string", "help": "Comma-separated fields for JSON output", "default": None},
            {"name": "--results-only", "short": None, "type": "bool", "help": "Emit only primary results in JSON mode", "default": False},
            {"name": "--dry-run", "short": "-n", "type": "bool", "help": "Preview changes without executing", "default": False},
            {"name": "--force", "short": "-y", "type": "bool", "help": "Skip confirmations", "default": False},
            {"name": "--access-token", "short": None, "type": "string", "help": "Use provided access token directly (bypasses OAuth)", "default": None},
            {"name": "--no-input", "short": None, "type": "bool", "help": "Never prompt; fail instead (for CI/agents)", "default": False},
        ],
        "exit_codes": [
            {"code": 0, "name": "SUCCESS", "description": "Operation completed successfully"},
            {"code": 1, "name": "ERROR", "description": "Generic/unknown error"},
            {"code": 2, "name": "USAGE", "description": "Invalid arguments or command syntax"},
            {"code": 3, "name": "EMPTY", "description": "No results found"},
            {"code": 4, "name": "AUTH", "description": "Authentication required or credentials missing"},
            {"code": 5, "name": "NOT_FOUND", "description": "Resource not found"},
            {"code": 6, "name": "PERMISSION", "description": "Permission denied"},
            {"code": 7, "name": "RATE_LIMIT", "description": "API rate limit exceeded"},
            {"code": 8, "name": "RETRYABLE", "description": "Transient error (network, server 5xx)"},
            {"code": 10, "name": "CONFIG", "description": "Configuration file missing or corrupt"},
            {"code": 130, "name": "INTERRUPTED", "description": "Interrupted (Ctrl-C / SIGINT)"},
        ],
        "commands": _build_commands_schema(args.target),
    }

    print(json.dumps(schema, indent=2))


def _build_commands_schema(filter_command=None):
    """Build the commands schema."""
    commands = {
        "init": {
            "help": "Initialize guesty-cli with API credentials",
            "flags": [
                {"name": "--skip-sync", "type": "bool", "help": "Skip initial data sync"}
            ]
        },
        "auth": {
            "help": "Manage authentication and tokens",
            "flags": [
                {"name": "--refresh", "type": "bool", "help": "Force token refresh"},
                {"name": "--revoke", "type": "bool", "help": "Clear cached token"}
            ]
        },
        "status": {
            "help": "Dashboard overview of account stats",
            "flags": []
        },
        "listings": {
            "help": "Property management",
            "subcommands": {
                "list": {"help": "List all listings", "flags": [
                    {"name": "--active", "type": "bool", "help": "Show only active listings"},
                    {"name": "--city", "type": "string", "help": "Filter by city"},
                    {"name": "--status", "type": "string", "help": "Filter by status"},
                    {"name": "--live", "type": "bool", "help": "Query live API instead of local DB"},
                ]},
                "show": {"help": "Show listing details", "args": [{"name": "listing_id", "required": True}]},
                "update": {"help": "Update listing fields", "args": [{"name": "listing_id", "required": True}]},
            }
        },
        "reservations": {
            "help": "Reservation management",
            "subcommands": {
                "list": {"help": "List reservations", "flags": [
                    {"name": "--status", "type": "string", "help": "Filter by status (confirmed, canceled, inquiry)"},
                    {"name": "--from", "type": "date", "help": "Check-in from date"},
                    {"name": "--to", "type": "date", "help": "Check-in to date"},
                    {"name": "--source", "type": "string", "help": "Filter by source (airbnb, vrbo, direct)"},
                    {"name": "--listing", "type": "string", "help": "Filter by listing ID or nickname"},
                    {"name": "--live", "type": "bool", "help": "Query live API"},
                ]},
                "get": {"help": "Get reservation details", "args": [{"name": "id_or_code", "required": True}]},
                "cancel": {"help": "Cancel a reservation", "args": [{"name": "id", "required": True}]},
            }
        },
        "guests": {
            "help": "Guest profile management",
            "subcommands": {
                "list": {"help": "List guests"},
                "get": {"help": "Get guest details", "args": [{"name": "guest_id", "required": True}]},
            }
        },
        "owners": {
            "help": "Owner management and statements",
            "subcommands": {
                "list": {"help": "List property owners"},
                "get": {"help": "Get owner details", "args": [{"name": "owner_id", "required": True}]},
            }
        },
        "calendar": {
            "help": "Calendar and availability management",
            "flags": [
                {"name": "--listing", "type": "string", "help": "Listing ID or nickname"},
                {"name": "--from", "type": "date", "help": "Start date"},
                {"name": "--to", "type": "date", "help": "End date"},
            ]
        },
        "tasks": {
            "help": "Task management (housekeeping, maintenance)",
            "subcommands": {
                "list": {"help": "List tasks"},
                "get": {"help": "Get task details", "args": [{"name": "task_id", "required": True}]},
                "create": {"help": "Create a new task"},
                "update": {"help": "Update a task", "args": [{"name": "task_id", "required": True}]},
            }
        },
        "reviews": {
            "help": "Review management",
            "subcommands": {
                "list": {"help": "List reviews"},
                "get": {"help": "Get review details", "args": [{"name": "review_id", "required": True}]},
            }
        },
        "webhooks": {
            "help": "Webhook management",
            "subcommands": {
                "list": {"help": "List webhooks"},
                "create": {"help": "Create a webhook"},
                "delete": {"help": "Delete a webhook", "args": [{"name": "webhook_id", "required": True}]},
                "test": {"help": "Test a webhook"},
            }
        },
        "financials": {"help": "Financial analytics and reporting"},
        "occupancy": {"help": "Occupancy analytics and metrics"},
        "integrations": {"help": "OTA integration management"},
        "users": {"help": "Team user management"},
        "sync": {
            "help": "Sync data from Guesty API to local database",
            "flags": [
                {"name": "--full", "type": "bool", "help": "Full sync (re-fetch everything)"},
                {"name": "--incremental", "short": "-i", "type": "bool", "help": "Only sync changes since last sync"},
                {"name": "--dry-run", "short": "-n", "type": "bool", "help": "Show what would be synced"},
            ]
        },
        "search": {"help": "Full-text search across all synced data"},
        "export": {"help": "Export data to CSV/JSON files"},
        "statements": {"help": "Generate owner statements"},
        "schema": {"help": "Print machine-readable CLI schema (for agents)"},
        "completion": {"help": "Generate shell completion scripts"},
        "exit-codes": {"help": "Print stable exit codes for automation"},
        "agent": {"help": "Agent-friendly helpers (schema, exit-codes)"},
        "auth-export": {
            "help": "Export credentials to JSON file (for transferring between machines)",
            "flags": [
                {"name": "--out", "type": "string", "help": "Output file path (default: stdout)", "default": "-"},
                {"name": "--include-secrets", "type": "bool", "help": "Include client_secret in export (dangerous)"},
            ]
        },
        "auth-import": {
            "help": "Import credentials from JSON file",
            "args": [{"name": "file", "required": True, "help": "JSON file path or - for stdin"}]
        },
    }

    if filter_command:
        return {filter_command: commands.get(filter_command, {"error": f"Unknown command: {filter_command}"})}
    return commands
