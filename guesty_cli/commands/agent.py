"""Agent-friendly helper commands.

These commands help AI agents and automation tools work with guesty-cli.
"""
import json
import sys


def register(subparsers):
    """Register agent commands."""
    # guesty agent (parent)
    agent_parser = subparsers.add_parser(
        'agent',
        help='Agent-friendly helpers for AI and automation'
    )
    agent_sub = agent_parser.add_subparsers(dest='agent_action')

    # guesty agent exit-codes
    ec_parser = agent_sub.add_parser('exit-codes', help='Print stable exit codes')
    ec_parser.set_defaults(func=run_exit_codes)

    # guesty agent capabilities
    cap_parser = agent_sub.add_parser('capabilities', help='Print CLI capabilities summary')
    cap_parser.set_defaults(func=run_capabilities)

    # guesty agent tips
    tips_parser = agent_sub.add_parser('tips', help='Usage tips for AI agents')
    tips_parser.set_defaults(func=run_tips)

    agent_parser.set_defaults(func=lambda a: run_agent_help(a, agent_parser))

    # Also register top-level aliases
    ec_top = subparsers.add_parser('exit-codes', help='Print stable exit codes (alias for agent exit-codes)')
    ec_top.set_defaults(func=run_exit_codes)


def run_agent_help(args, parser):
    parser.print_help()


def run_exit_codes(args):
    """Print stable exit codes as JSON."""
    from guesty_cli.core.exit_codes import EXIT_CODE_TABLE
    from guesty_cli.core.output import is_json, is_plain

    if is_plain():
        for entry in EXIT_CODE_TABLE:
            print(f"{entry['code']}\t{entry['name']}\t{entry['description']}")
    elif is_json() or not sys.stdout.isatty():
        print(json.dumps(EXIT_CODE_TABLE, indent=2))
    else:
        print()
        print("  Guesty CLI \u2014 Stable Exit Codes")
        print("  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
        for entry in EXIT_CODE_TABLE:
            print(f"  {entry['code']:>3}  {entry['name']:<15} {entry['description']}")
        print()


def run_capabilities(args):
    """Print CLI capabilities for agent discovery."""
    from guesty_cli import __version__
    from guesty_cli.core.output import is_json, is_plain

    caps = {
        "name": "guesty-cli",
        "version": __version__,
        "output_modes": ["human", "json", "plain"],
        "auth_method": "oauth2_client_credentials",
        "local_cache": "sqlite_fts5",
        "api_base": "https://open-api.guesty.com/v1",
        "features": [
            "local_sqlite_cache",
            "fts5_search",
            "incremental_sync",
            "rate_limit_tracking",
            "circuit_breaker",
            "stable_exit_codes",
            "tri_modal_output",
            "shell_completion",
            "schema_introspection",
            "dry_run",
            "auto_json_pipe",
            "field_selection",
            "access_token_bypass",
            "token_export_import",
            "non_interactive_mode",
        ],
        "resources": [
            "listings", "reservations", "guests", "owners", "reviews",
            "tasks", "webhooks", "users", "integrations", "financials",
            "calendar", "occupancy",
        ],
        "environment_variables": {
            "GUESTY_AUTO_JSON": "Auto-switch to JSON when stdout is piped",
            "GUESTY_CLIENT_ID": "Override client_id from config",
            "GUESTY_CLIENT_SECRET": "Override client_secret from config",
            "GUESTY_ACCESS_TOKEN": "Use provided access token directly (bypasses OAuth flow)",
            "GUESTY_NO_INPUT": "Never prompt; fail instead (for CI/agents)",
            "NO_COLOR": "Disable colored output",
        },
        "tips": [
            "Use --json for machine-readable output",
            "Use --json --results-only to skip pagination envelope",
            "Use --json --select 'id,status,guest.name' for field projection",
            "Use --plain for stable TSV piping to awk/cut/sort",
            "Use --dry-run on mutating commands to preview",
            "Set GUESTY_AUTO_JSON=1 for auto-JSON when piped",
            "Exit code 3 means empty results (not an error)",
            "Exit code 7 means rate limited -- back off and retry",
            "Use --access-token TOKEN to bypass OAuth (for pre-obtained tokens)",
            "Use --no-input to prevent all interactive prompts (for CI/agents)",
            "Use 'guesty auth-export --include-secrets' to transfer credentials",
            "Use 'guesty auth-import creds.json' to import credentials",
        ]
    }

    if is_plain():
        # TSV output for piping
        for key, value in caps.items():
            if isinstance(value, list):
                print(f"{key}\t{','.join(str(v) for v in value)}")
            elif isinstance(value, dict):
                for k, v in value.items():
                    print(f"{key}.{k}\t{v}")
            else:
                print(f"{key}\t{value}")
    else:
        # JSON for both --json mode and human mode (it's structured data)
        print(json.dumps(caps, indent=2))


def run_tips(args):
    """Print usage tips for AI agents."""
    tips = """
# Guesty CLI -- Agent Tips

## Output Modes
- `guesty --json reservations list` -> JSON output
- `guesty --plain reservations list` -> TSV (tab-separated, no colors)
- `guesty reservations list` -> Human-friendly colored tables

## Field Selection (JSON mode)
- `guesty --json --select id,status,checkIn reservations list`
- `guesty --json --results-only listings list` (drops pagination metadata)

## Auto-JSON (for piped commands)
- `export GUESTY_AUTO_JSON=1`
- Then: `guesty reservations list | jq '.[] | .status'`

## Scripting with Exit Codes
```bash
guesty reservations get CONF123
case $? in
  0) echo "Found" ;;
  3) echo "No results" ;;
  4) echo "Need to re-authenticate" ;;
  5) echo "Not found" ;;
  7) echo "Rate limited, retry later" ;;
esac
```

## Dry Run
- `guesty --dry-run listings update LISTING_ID --title "New Title"`

## Direct Access Token (bypass OAuth)
- `guesty --access-token TOKEN reservations list`
- Or: `export GUESTY_ACCESS_TOKEN=TOKEN && guesty reservations list`

## Non-Interactive Mode (CI/agents)
- `guesty --no-input init` (requires GUESTY_CLIENT_ID + GUESTY_CLIENT_SECRET env vars)
- All prompts are skipped; missing required input causes immediate failure

## Credential Transfer
- `guesty auth-export --out creds.json --include-secrets`
- `guesty auth-import creds.json`

## Introspection
- `guesty schema` -> Full CLI schema as JSON
- `guesty exit-codes` -> Exit code table
- `guesty agent capabilities` -> Feature/resource list
"""
    print(tips.strip())
