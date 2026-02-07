# AGENTS.md — AI Agent Instructions for guesty-cli

You are using `guesty-cli`, a terminal tool for managing vacation rentals via the Guesty PMS API.

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

## Common Workflows

### Check today's activity
```bash
guesty sync reservations  # Refresh reservation data
guesty reservations --today
guesty reservations --today --json  # For parsing
```

### Look up a specific reservation
```bash
guesty reservation get HM4STAP88M          # By confirmation code
guesty reservation get 6980991995972a68c2d37aa4  # By Guesty ID
```

### Search across all data
```bash
guesty search "pool heater"   # FTS5 search, no API call
guesty search "marathon"
```

### Block calendar dates
```bash
# Always dry-run first
guesty calendar block "Emerald Oasis" 2025-04-01 --to 2025-04-05 --reason "Maintenance" --dry-run
# Then execute
guesty calendar block "Emerald Oasis" 2025-04-01 --to 2025-04-05 --reason "Maintenance" --live
```

### Create a task
```bash
guesty task create --title "Fix AC unit" --listing "Emerald Oasis" --priority high --dry-run
guesty task create --title "Fix AC unit" --listing "Emerald Oasis" --priority high --live
```

### Create a reservation
```bash
guesty reservation create --listing "Emerald Oasis" --guest-name "John Smith" --guest-email "john@example.com" --checkin 2025-06-01 --checkout 2025-06-05 --dry-run
guesty reservation create --listing "Emerald Oasis" --guest-name "John Smith" --guest-email "john@example.com" --checkin 2025-06-01 --checkout 2025-06-05 --live
```

### Update pricing
```bash
guesty calendar price "Emerald Oasis" 2025-06-01 450 --to 2025-06-30 --dry-run
guesty calendar price "Emerald Oasis" 2025-06-01 450 --to 2025-06-30 --live
```

### Export data
```bash
guesty export reservations --format csv    # Creates reservations_YYYYMMDD.csv
guesty export listings --format json       # Creates listings_YYYYMMDD.json
```

### Financial overview
```bash
guesty financials                          # Revenue by listing, by month
guesty financials --json                   # For parsing
```

## Command Quick Reference

### Read (no API call needed after sync)
- `guesty status` — Dashboard overview
- `guesty listings` — All properties
- `guesty listing get <name_or_id>` — Property detail
- `guesty reservations [--today] [--status X] [--limit N]` — Reservations
- `guesty reservation get <code_or_id>` — Reservation detail + financials
- `guesty guests [--search NAME]` — Guests
- `guesty guest <email_or_id>` — Guest detail
- `guesty owners` — All owners
- `guesty reviews [--limit N]` — Reviews with ratings
- `guesty financials` — Revenue reports
- `guesty tasks` — Tasks
- `guesty search <query>` — Full-text search
- `guesty webhooks` — Registered webhooks
- `guesty calendar <listing>` — Calendar view

### Write (requires --live for API calls)
- `guesty listing create/update/delete`
- `guesty reservation create/update/cancel/approve/decline`
- `guesty owner create/update/delete`
- `guesty task create/update/delete/complete`
- `guesty calendar block/unblock/price`
- `guesty webhook create/update/delete/test`

### System
- `guesty sync [table]` — Sync from API
- `guesty export <table> [--format csv|json]` — Export
- `guesty auth --refresh` — Force token refresh
- `guesty auth --revoke` — Clear token cache

## Output Formats

- **Default**: Colored terminal tables with box-drawing characters
- **`--json`**: Raw JSON array/object (pipe to `jq`, parse in Python, etc.)
- **`--no-color`**: Plain text without ANSI codes

## Important Notes

- **Minimal API responses**: Guesty's reservation endpoint returns minimal fields by default. The `sync` command requests extended fields (`status`, `source`, `money.*`, `guest.*`). If you query the API directly, remember to include a `fields` parameter.
- **Source names**: API returns `airbnb2`, `homeaway2`, `BE-API` — the CLI maps these to `Airbnb`, `VRBO`, `Direct` in display.
- **Token limit**: Max 5 new tokens per 24h. The CLI caches tokens and tracks this. If you hit the limit, wait for tokens to expire (24h rolling window).
- **Database location**: `~/.guesty-cli/guesty.db` — SQLite with FTS5 virtual table for search.
