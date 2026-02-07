# AGENTS.md — AI Agent Instructions for guesty-cli

> **⚠️ PRIMARY INTERFACE**: This CLI is Lucy's main tool for accessing Guesty PMS data. Always use `guesty` commands instead of raw API calls or database queries.

## Lucy's Guesty Workflow

As Lucy (VPVR AI Operations), I use this CLI for ALL Guesty operations:

```bash
# Morning routine — sync fresh data
guesty sync

# Check today's activity
guesty reservations --today
guesty status

# Look up anything — properties, guests, reservations
guesty listing get "Emerald Oasis"
guesty reservation get HM4STAP88M
guesty guest "john@example.com"
guesty search "pool heater"

# Export for analysis
guesty export reservations --format json
```

**Never** bypass the CLI to query the SQLite DB directly — always use `guesty` commands for consistency, safety, and audit trails.

---

## Setup

```bash
# Check if configured
python -m guesty_cli.main status

# If not configured, initialize with your Guesty API credentials:
python -m guesty_cli.main init
# You'll need: client_id and client_secret from Guesty Dashboard → Marketplace → Open API
```

## Core Concepts

1. **Local-first**: Data is synced to a local SQLite database. Most read commands query locally (fast, no API calls). Use `guesty sync` to refresh from API.
2. **Safe writes**: All write commands require `--live` to actually call the API. Without it, they either show a `--dry-run` preview or error. All deletes also require `--confirm`.
3. **Nickname resolution**: Listings can be referenced by nickname ("Emerald Oasis") instead of Guesty ID. Owners by name. Reservations by confirmation code.
4. **Rate limits**: Guesty allows max 5 new OAuth tokens per 24h, 15 requests/sec, 120/min, 5000/hr. The CLI handles this automatically — don't call `auth --revoke` unless necessary.

## Lucy's Common Workflows

### Daily Morning Check
```bash
guesty sync                              # Refresh all data
guesty status                            # Dashboard overview
guesty reservations --today --json       # Today's check-ins (for parsing)
```

### Guest Inquiry Response
```bash
# Find reservation by confirmation code
guesty reservation get HM4STAP88M

# Or search for guest
guesty guests --search "john"
guesty guest "john@example.com"
```

### Property Information
```bash
guesty listing get "Emerald Oasis"       # Property details
guesty listings | grep "Emerald"         # Find by partial name
guesty search "pool"                     # Search descriptions
```

### Financial Queries
```bash
guesty financials                        # Revenue summary
guesty financials --json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Total profit: ${sum(x[\"profit\"] for x in d[\"by_listing\"]):,.2f}')"
```

### Calendar Operations
```bash
# View calendar (requires --live for fresh data)
guesty calendar view "Emerald Oasis" --live

# Block dates for maintenance
guesty calendar block "Emerald Oasis" 2025-04-01 --to 2025-04-05 --reason "Pool repair" --dry-run
guesty calendar block "Emerald Oasis" 2025-04-01 --to 2025-04-05 --reason "Pool repair" --live

# Update pricing
guesty calendar price "Emerald Oasis" 2025-06-01 450 --to 2025-06-30 --dry-run
guesty calendar price "Emerald Oasis" 2025-06-01 450 --to 2025-06-30 --live
```

### Task Management
```bash
guesty tasks --limit 20                  # View open tasks
guesty task create --title "Fix AC" --listing "Emerald Oasis" --priority high --live
```

### Damage Claims Workflow
```bash
# Find reservation that just checked out
guesty reservations --today              # Recent check-outs
guesty reservation get CODE --json       # Get full details for claim
```

## Command Quick Reference

### Read Operations (Local DB, Fast)
| Command | Purpose |
|---------|---------|
| `guesty status` | Dashboard overview with stats |
| `guesty listings` | All properties table |
| `guesty listing get <nickname>` | Property details by nickname |
| `guesty reservations [--today] [--limit N]` | Reservations list |
| `guesty reservation get <code>` | Reservation detail + financials |
| `guesty guests --search <name>` | Search guests |
| `guesty guest <email>` | Guest details |
| `guesty owners` | All owners |
| `guesty reviews [--limit N]` | Reviews with star ratings |
| `guesty financials` | Revenue by listing, by month |
| `guesty tasks [--limit N]` | Tasks list |
| `guesty search <query>` | Full-text search across all data |
| `guesty webhooks` | Registered webhooks |
| `guesty calendar view <listing> --live` | Calendar view (API call) |

### Write Operations (Require `--live`)
| Command | Purpose |
|---------|---------|
| `guesty listing create --title X --nickname X --city X` | Create property |
| `guesty listing update <id> --title X` | Update property |
| `guesty listing delete <id> --confirm` | Delete property |
| `guesty reservation create --listing X --guest-name X...` | Create booking |
| `guesty reservation update <id> --status X` | Update reservation |
| `guesty reservation cancel <id> --confirm` | Cancel reservation |
| `guesty calendar block <listing> <date> [--to DATE]` | Block dates |
| `guesty calendar price <listing> <date> <price>` | Set price |
| `guesty task create --title X --listing X` | Create task |

### System Operations
| Command | Purpose |
|---------|---------|
| `guesty sync [table]` | Sync data from API to local DB |
| `guesty export <table> [--format csv\|json]` | Export to file |
| `guesty auth --refresh` | Force token refresh |
| `guesty auth --revoke` | Clear cached token |

## Output Formats

- **Default**: Colored terminal tables with box-drawing characters
- **`--json`**: Raw JSON for scripting/parsing
- **`--no-color`**: Plain text without ANSI codes

## Important Notes for AI Agents

### Always Sync Before Important Queries
The local DB may be stale. For time-sensitive data (today's check-ins, recent bookings), run `guesty sync` first.

### Never Bypass the CLI
❌ **Wrong**: Querying SQLite directly  
✅ **Right**: Using `guesty` commands

The CLI handles:
- Field mapping (API returns minimal data by default)
- Source name translation (airbnb2→Airbnb)
- Date formatting
- Price formatting
- Error handling

### Token Management
The CLI auto-manages OAuth tokens:
- Caches tokens for 24h
- Tracks 5 token/day limit
- Auto-refreshes 5 min before expiry

**Don't** manually revoke tokens unless troubleshooting auth issues.

### Safety First
All write operations require explicit flags:
- `--dry-run` to preview changes
- `--live` to actually execute
- `--confirm` for destructive operations

Example safe workflow:
```bash
# 1. Preview
guesty calendar block "Emerald Oasis" 2025-04-01 --to 2025-04-05 --reason "Maintenance" --dry-run

# 2. Review output

# 3. Execute
guesty calendar block "Emerald Oasis" 2025-04-01 --to 2025-04-05 --reason "Maintenance" --live
```

### Database Location
- **Path**: `~/.guesty-cli/guesty.db`
- **Format**: SQLite with FTS5 full-text search
- **Tables**: listings, reservations, guests, owners, reviews, tasks, webhooks, financials
- **Access**: Via `guesty` CLI only — do not query directly

## Troubleshooting

### "Token expired" or "401 Unauthorized"
```bash
guesty auth --refresh    # Force new token
guesty status            # Verify auth
```

### "Rate limit exceeded"
Wait a few seconds — the CLI has built-in retry with exponential backoff.

### "Listing not found"
Check the nickname:
```bash
guesty listings | grep -i "partial name"
```

### Sync appears stale
```bash
guesty sync              # Full sync
guesty sync reservations # Sync just reservations
```

## API Compliance

This CLI fully respects Guesty API constraints:
- **OAuth2**: `client_credentials` flow
- **Token limit**: Max 5 per 24h (tracked + enforced)
- **Rate limits**: 15/sec, 120/min, 5000/hr (throttled automatically)
- **Pagination**: Auto-handled via `limit` + `skip`

---

*Last updated: 2026-02-07 | For Lucy VPVR AI Operations*
