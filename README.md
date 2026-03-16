# guesty-cli

> The missing CLI for [Guesty PMS](https://guesty.com) — manage your vacation rental operations from the terminal.

**60+ commands** · **Zero dependencies** · **Local-first** · **AI-agent friendly**

```
██████╗ ██╗   ██╗███████╗███████╗████████╗██╗   ██╗
██╔════╝ ██║   ██║██╔════╝██╔════╝╚══██╔══╝╚██╗ ██╔╝
██║  ███╗██║   ██║█████╗  ███████╗   ██║    ╚████╔╝
██║   ██║██║   ██║██╔══╝  ╚════██║   ██║     ╚██╔╝
╚██████╔╝╚██████╔╝███████║███████║   ██║      ██║
 ╚═════╝  ╚═════╝ ╚══════╝╚══════╝   ╚═╝      ╚═╝
```

## Why?

Guesty has no official CLI. If you manage vacation rentals and want to:
- Query reservations from the terminal
- Sync data locally for fast offline access
- Automate operations with scripts or AI agents
- Export data to CSV/JSON for analysis
- Block calendar dates, update prices, manage tasks
- Generate owner statements and tax reports
- Monitor occupancy metrics and gap nights

...this is for you.

## Features

- **Zero external dependencies** — Python 3.8+ stdlib only (optional `keyring` for OS keychain)
- **Local-first** — SQLite database with FTS5 full-text search. Query instantly without API calls
- **API-compliant** — Respects all Guesty rate limits (15/s, 120/m, 5000/h), 5 tokens/day with aggressive caching
- **Secure credentials** — OS keychain storage (macOS Keychain, Linux SecretService) with file fallback
- **Safe writes** — Global `--dry-run` / `--force` on mutating commands, `--confirm` on deletes
- **Tri-modal output** — `--json` (scripting), `--plain` (TSV piping), or human-friendly tables
- **Agent-first** — Stable exit codes, `--access-token` bypass, `--no-input` mode, schema introspection, shell completions

## Quick Start

### 1. Install

```bash
# Clone and install
git clone https://github.com/YOUR_ORG/guesty-cli.git
cd guesty-cli
pip install .

# Or run directly
python -m guesty_cli.main --help
```

### 2. Configure

```bash
guesty init
```

You'll need your Guesty API credentials:
1. Log into [Guesty Dashboard](https://app.guesty.com)
2. Go to **Marketplace → Development Tools → Guesty Open API**
3. Create an application → get your **Client ID** and **Client Secret**

### 3. Sync Data

```bash
guesty sync          # Sync all data from Guesty API
guesty sync listings # Sync just listings
guesty status        # See your dashboard
```

### 4. Use

```bash
guesty reservations --today            # Today's check-ins
guesty reservation get HM4STAP88M      # Reservation detail + financials
guesty listings                        # All properties
guesty search "pool heater"            # Full-text search
guesty export reservations --format csv # Export to CSV
```

## Agent & Automation

guesty-cli is designed for AI agents, CI pipelines, and shell scripts.

### Token-Efficient Workflow

Guesty allows **5 token requests per day** per API key. Use `auth-token` to get one token, then pass it to all commands:

```bash
# Get token once (burns 1 of 5 daily slots)
TOKEN=$(guesty auth-token)

# Use for unlimited commands (0 slots burned)
guesty --access-token "$TOKEN" --json listings list
guesty --access-token "$TOKEN" --json reservations list --status confirmed
guesty --access-token "$TOKEN" --plain occupancy | awk '{print $1, $3}'
```

### Output Modes

```bash
guesty listings list              # Human-friendly colored tables
guesty --json listings list       # JSON (for scripts and agents)
guesty --plain listings list      # TSV (pipe to awk/cut/sort)

# Field selection (JSON mode)
guesty --json --select id,status,checkIn reservations list

# Strip pagination envelope
guesty --json --results-only reservations list
```

### Exit Codes

| Code | Meaning | Agent Action |
|------|---------|--------------|
| 0 | Success | Continue |
| 3 | Empty results | Handle no-data case |
| 4 | Auth required | Re-authenticate or check credentials |
| 7 | Rate limited | Back off and retry later |
| 8 | Retryable error | Retry the command |

Full list: `guesty exit-codes`

### Non-Interactive Mode

```bash
# CI/agent setup (no prompts)
export GUESTY_CLIENT_ID="your-id"
export GUESTY_CLIENT_SECRET="your-secret"
guesty --no-input init

# Auto-JSON when piped
export GUESTY_AUTO_JSON=1
guesty reservations list | jq '.'
```

### Introspection

```bash
guesty schema              # Full CLI as machine-readable JSON
guesty agent capabilities  # Feature and resource list
guesty agent tips          # Usage guide for agents
guesty completion bash     # Shell completions (also zsh, fish)
```

## Commands Reference

### Setup & Status

| Command | Description |
|---------|-------------|
| `guesty init [--skip-sync]` | Initialize with API credentials |
| `guesty status [--json]` | Dashboard overview with stat boxes |
| `guesty auth --refresh` | Force token refresh |
| `guesty auth --revoke` | Clear cached token |
| `guesty auth-token` | Print valid access token (for `--access-token` workflow) |
| `guesty auth-export [--out FILE] [--include-secrets]` | Export credentials to JSON |
| `guesty auth-import <file>` | Import credentials from JSON file |
| `guesty schema [command]` | Print CLI schema as JSON (for agents) |
| `guesty completion bash\|zsh\|fish` | Generate shell completion scripts |
| `guesty exit-codes` | Print stable exit codes |
| `guesty agent capabilities\|tips` | Agent-friendly helpers |

### Listings (Properties)

| Command | Description | Options |
|---------|-------------|---------|
| `guesty listings [--active] [--city X] [--status X] [--json] [--csv] [--live]` | List all properties | Filter by city, status |
| `guesty listing <nickname>` (shortcut) | Get property details | Auto-resolves nickname |
| `guesty listing get <id_or_nickname>` | Get property details | |
| `guesty listing create --title X [--nickname X] [--address X] [--city X] [--bedrooms N] [--bathrooms N] [--max-guests N] [--dry-run]` | Create listing | |
| `guesty listing update <id_or_nickname> [--title X] [--nickname X] [--address X] [--city X] [--dry-run]` | Update listing | |
| `guesty listing delete <id_or_nickname> --confirm` | Delete listing | Requires confirmation |

### Reservations

| Command | Description | Options |
|---------|-------------|---------|
| `guesty reservations [--today] [--tomorrow] [--checkin YYYY-MM-DD] [--checkout YYYY-MM-DD] [--listing X] [--guest X] [--status X] [--unpaid] [--json] [--csv] [--live]` | List reservations | Multiple filters supported |
| `guesty reservation <code>` (shortcut) | Get reservation details | Auto-resolves confirmation code |
| `guesty reservation get <id_or_code>` | Get reservation + financials | Shows full breakdown |
| `guesty reservation create --listing X --guest-name X --checkin YYYY-MM-DD --checkout YYYY-MM-DD [--dry-run] [--live]` | Create reservation | Dry-run by default |
| `guesty reservation update <id_or_code> [--status X] [--notes X] [--dry-run] [--live]` | Update reservation | |
| `guesty reservation cancel <id_or_code> [--confirm] [--live]` | Cancel reservation | Requires confirmation |
| `guesty reservation approve <id_or_code> [--live]` | Approve inquiry | |
| `guesty reservation decline <id_or_code> [--live]` | Decline inquiry | |

### Calendar Management

| Command | Description | Safety |
|---------|-------------|--------|
| `guesty calendar view <listing> [--from DATE] [--to DATE]` | View calendar | Read-only |
| `guesty calendar sync <listing> --from DATE --to DATE [--dry-run]` | Sync calendar to local DB | Dry-run available |
| `guesty calendar sync-all --from DATE --to DATE [--parallel N] [--dry-run]` | Sync all listings | Parallel processing |
| `guesty calendar block <listing> <date> [--to DATE] [--reason X] [--dry-run] [--live]` | Block dates | Dry-run by default |
| `guesty calendar unblock <listing> <date> [--to DATE] [--dry-run] [--live]` | Unblock dates | Dry-run by default |
| `guesty calendar price <listing> <date> <price> [--to DATE] [--currency USD] [--dry-run] [--live]` | Update pricing | Dry-run by default |
| `guesty calendar block-all --from DATE --to DATE --listings A,B,C [--reason X] [--parallel N] [--live]` | Block multiple | Parallel API calls |
| `guesty calendar unblock-all --from DATE --to DATE --listings A,B,C [--parallel N] [--live]` | Unblock multiple | Parallel API calls |
| `guesty calendar price-all --from DATE --to DATE --listings A,B,C --set PRICE [--live]` | Bulk price update | Parallel API calls |
| `guesty calendar price-dynamic <listing> --from DATE --to DATE [--low-occupancy-threshold 30] [--high-occupancy-threshold 70] [--decrease-percent 10] [--increase-percent 15] [--min-price X] [--max-price X] [--live]` | Auto-adjust pricing | Based on occupancy |

### Guests

| Command | Description | Options |
|---------|-------------|---------|
| `guesty guests [--search NAME] [--limit N] [--json] [--csv] [--live]` | List/search guests | Search across names, email, phone |
| `guesty guest <id_or_email> [--json] [--live]` | Guest details + reservation history | Shows full history |

### Owners

| Command | Description | Options |
|---------|-------------|---------|
| `guesty owners [--active] [--json] [--csv] [--live]` | List all owners | |
| `guesty owner get <id_or_name> [--json] [--live]` | Owner details + properties | Shows owned properties |
| `guesty owner create --name X [--email X] [--phone X] [--dry-run] [--live]` | Create owner | |
| `guesty owner update <id_or_name> [--email X] [--phone X] [--dry-run] [--live]` | Update owner | |
| `guesty owner delete <id_or_name> --confirm [--live]` | Delete owner | Requires confirmation |
| `guesty owner reservations <id_or_name> [--from DATE] [--to DATE] [--json] [--live]` | Owner's reservations | Date range filter |
| `guesty owner statement <id_or_name> --month YYYY-MM [--management-fee 20] [--format text\|json]` | Generate owner statement | Payout calculation |

### Users (Team)

| Command | Description | Options |
|---------|-------------|---------|
| `guesty users [--active] [--json] [--csv] [--live]` | List team users | Shows task counts |
| `guesty user get <id_or_email> [--json] [--live]` | User details + assigned tasks | Shows workload |

### Integrations (OTA Connections)

| Command | Description | Options |
|---------|-------------|---------|
| `guesty integrations [--platform X] [--status X] [--listing X] [--json] [--csv] [--live]` | List OTA connections | Filter by platform, status |
| `guesty integration <id_or_name> [--health] [--json] [--live]` | Integration details | Health check included |

### Tasks

| Command | Description | Options |
|---------|-------------|---------|
| `guesty tasks [--status X] [--listing X] [--priority X] [--limit N] [--json] [--csv] [--live]` | List tasks | Filter by status, priority |
| `guesty task view <id> [--json] [--live]` | Task details | |
| `guesty task create --title X --listing X [--priority medium] [--due DATE] [--assignee ID] [--description X] [--dry-run] [--live]` | Create task | |
| `guesty task update <id> [--status X] [--priority X] [--assignee ID] [--dry-run] [--live]` | Update task | |
| `guesty task complete <id> [--dry-run] [--live]` | Mark task completed | Shortcut for update --status |
| `guesty task delete <id> --confirm [--live]` | Delete task | Requires confirmation |

### Reviews

| Command | Description | Options |
|---------|-------------|---------|
| `guesty reviews [--listing X] [--rating N] [--platform X] [--limit N] [--json] [--csv] [--live]` | List reviews | Filter by rating, platform |

### Webhooks

| Command | Description | Safety |
|---------|-------------|--------|
| `guesty webhooks [--json] [--live]` | List registered webhooks | Read-only |
| `guesty webhook create --url X --events X [--secret X] [--dry-run] [--live]` | Create webhook | Dry-run by default |
| `guesty webhook update <id> --events X [--dry-run] [--live]` | Update webhook | Dry-run by default |
| `guesty webhook delete <id> --confirm [--live]` | Delete webhook | Requires confirmation |
| `guesty webhook test <id> [--live]` | Send test ping | |
| `guesty webhook watch [--port 8080] [--json] [--queue] [--retry] [--persist]` | Local webhook listener | With queue & retry |
| `guesty webhook queue [--pending] [--failed] [--retry] [--clear]` | Manage webhook queue | Process failed events |

### Financials & Reporting

| Command | Description | Output |
|---------|-------------|--------|
| `guesty financials revenue --month YYYY-MM [--listing X] [--owner X] [--json] [--csv]` | Monthly revenue report | By listing, by owner |
| `guesty financials taxes --month YYYY-MM [--county monroe\|miami-dade] [--json] [--csv]` | Tourist/sales tax report | County breakdown |
| `guesty financials dr15 --month YYYY-MM [--json] [--csv]` | DR-15 tax form ready | Florida DOR format |
| `guesty financials summary [--listing X] [--from DATE] [--to DATE] [--type X] [--json]` | Financial summary | Legacy command |

### Occupancy Analytics

| Command | Description | Metrics |
|---------|-------------|---------|
| `guesty occupancy --month YYYY-MM [--listing X] [--json]` | Monthly occupancy report | Occ%, ADR, RevPAR |
| `guesty occupancy --year YYYY [--listing X] [--json]` | Annual occupancy report | Monthly breakdown |
| `guesty occupancy gaps --from DATE --to DATE [--listing X] [--max-gap 6] [--json]` | Gap night analysis | Revenue opportunities |

### Views (Built-in Reports)

| Command | Description | Options |
|---------|-------------|---------|
| `guesty views --section reservations [--json] [--live]` | Guesty reservation views | Built-in reports |
| `guesty views --section listings [--json] [--live]` | Guesty listing views | Built-in reports |

### Statements

| Command | Description | Options |
|---------|-------------|---------|
| `guesty statements <owner_name> --month YYYY-MM [--management-fee 20] [--format text\|json] [--dry-run]` | Generate owner statement | Payout breakdown |

### Search

| Command | Description | Options |
|---------|-------------|---------|
| `guesty search <query> [--table X] [--limit N] [--json] [--rebuild]` | Full-text search | FTS5 powered |

### Sync

| Command | Description | Options |
|---------|-------------|---------|
| `guesty sync [endpoint] [--full] [--incremental] [--since TIMESTAMP] [--dry-run]` | Sync data from API | Endpoint or all |
| `guesty sync --status` | Show sync status | With cursors |
| `guesty sync --history` | Show sync history | Last 20 syncs |

### Export

| Command | Description | Options |
|---------|-------------|---------|
| `guesty export <table> [--format csv\|json] [--output PATH] [--where "SQL"]` | Export table to file | SQL WHERE supported |

### Global Flags

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | | Output as JSON |
| `--plain` | `-p` | Output stable TSV (no colors, pipe-friendly) |
| `--select FIELDS` | | Comma-separated fields for JSON output |
| `--results-only` | | Strip pagination envelope in JSON mode |
| `--dry-run` | `-n` | Preview changes without executing |
| `--force` | `-y` | Skip confirmations |
| `--access-token TOKEN` | | Use provided token (bypass OAuth) |
| `--no-input` | | Never prompt (CI/agent mode) |
| `--no-color` | | Disable colored output |
| `--csv` | | Output as CSV (for spreadsheets) |
| `--version` | | Show version |
| `--help` | | Show help for any command |

## Architecture

```
~/.guesty-cli/
├── config.json    # Credentials + token cache (NEVER commit this)
└── guesty.db      # SQLite database with FTS5 search

guesty_cli/
├── main.py            # Entry point + command routing
├── core/
│   ├── client.py      # HTTP client, OAuth2, rate limiting, retries
│   ├── config.py      # Config management, token caching
│   ├── database.py    # SQLite schema, CRUD, FTS5 setup
│   └── output.py      # Table formatting, colors, stat boxes
├── commands/
│   ├── auth.py        # init, auth refresh/revoke
│   ├── status.py      # Dashboard overview
│   ├── listings.py    # Listings CRUD
│   ├── reservations.py # Reservations CRUD
│   ├── calendar.py    # Calendar view, block/unblock/price
│   ├── calendar_sync.py # Calendar sync operations
│   ├── guests.py      # Guest lookup
│   ├── owners.py      # Owners CRUD + statements
│   ├── users.py       # Team user management
│   ├── integrations.py # OTA integrations
│   ├── tasks.py       # Tasks CRUD
│   ├── reviews.py     # Review display
│   ├── webhooks.py    # Webhooks CRUD + watch server
│   ├── financials.py  # Revenue, tax reports
│   ├── occupancy.py   # Occupancy analytics
│   ├── views.py       # Guesty built-in views
│   ├── statements.py  # Owner statement generation
│   ├── search.py      # FTS5 full-text search
│   ├── sync.py        # API → SQLite sync (with incremental)
│   └── export.py      # CSV/JSON export
└── utils/
    ├── dates.py       # Date parsing + formatting
    ├── filters.py     # Query filter builders
    └── resolve.py     # Nickname/name → ID resolution
```

## API Coverage Matrix

| Guesty API Endpoint | CLI Commands | Methods | Status |
|---------------------|--------------|---------|--------|
| **Authentication** | | | |
| `POST /oauth2/token` | `guesty init`, `guesty auth` | POST | ✅ Full |
| **Listings** | | | |
| `GET /v1/listings` | `guesty listings`, `guesty sync listings` | GET | ✅ Full |
| `GET /v1/listings/{id}` | `guesty listing get` | GET | ✅ Full |
| `POST /v1/listings` | `guesty listing create --live` | POST | ✅ Full |
| `PUT /v1/listings/{id}` | `guesty listing update --live` | PUT | ✅ Full |
| `DELETE /v1/listings/{id}` | `guesty listing delete --live` | DELETE | ✅ Full |
| **Reservations** | | | |
| `GET /v1/reservations` | `guesty reservations`, `guesty sync reservations` | GET | ✅ Full |
| `GET /v1/reservations/{id}` | `guesty reservation get` | GET | ✅ Full |
| `POST /v1/reservations` | `guesty reservation create --live` | POST | ✅ Full |
| `PUT /v1/reservations/{id}` | `guesty reservation update --live` | PUT | ✅ Full |
| `POST /v1/reservations/{id}/cancel` | `guesty reservation cancel --live` | POST | ✅ Full |
| `POST /v1/reservations/{id}/approve` | `guesty reservation approve --live` | POST | ✅ Full |
| `POST /v1/reservations/{id}/decline` | `guesty reservation decline --live` | POST | ✅ Full |
| **Calendar** | | | |
| `GET /v1/availability-pricing/api/calendar/listings/{id}` | `guesty calendar view`, `guesty calendar sync` | GET | ✅ Full |
| `PUT /v1/availability-pricing/api/calendar/listings/{id}` | `guesty calendar block/unblock/price --live` | PUT | ✅ Full |
| **Guests** | | | |
| `GET /v1/guests` | `guesty guests`, `guesty sync guests` | GET | ✅ Full |
| `GET /v1/guests/{id}` | `guesty guest` | GET | ✅ Full |
| **Owners** | | | |
| `GET /v1/owners` | `guesty owners`, `guesty sync owners` | GET | ✅ Full |
| `GET /v1/owners/{id}` | `guesty owner get` | GET | ✅ Full |
| `POST /v1/owners` | `guesty owner create --live` | POST | ✅ Full |
| `PUT /v1/owners/{id}` | `guesty owner update --live` | PUT | ✅ Full |
| `DELETE /v1/owners/{id}` | `guesty owner delete --live` | DELETE | ✅ Full |
| `GET /v1/owners/{id}/reservations` | `guesty owner reservations --live` | GET | ✅ Full |
| **Users** | | | |
| `GET /v1/users` | `guesty users`, `guesty sync users` | GET | ✅ Full |
| `GET /v1/users/{id}` | `guesty user get` | GET | ✅ Full |
| **Tasks** | | | |
| `GET /v1/tasks` | `guesty tasks`, `guesty sync tasks` | GET | ✅ Full |
| `GET /v1/tasks/{id}` | `guesty task view` | GET | ✅ Full |
| `POST /v1/tasks` | `guesty task create --live` | POST | ✅ Full |
| `PUT /v1/tasks/{id}` | `guesty task update --live` | PUT | ✅ Full |
| `DELETE /v1/tasks/{id}` | `guesty task delete --live` | DELETE | ✅ Full |
| **Reviews** | | | |
| `GET /v1/reviews` | `guesty reviews`, `guesty sync reviews` | GET | ✅ Full |
| **Webhooks** | | | |
| `GET /v1/webhooks` | `guesty webhooks`, `guesty sync webhooks` | GET | ✅ Full |
| `POST /v1/webhooks` | `guesty webhook create --live` | POST | ✅ Full |
| `PUT /v1/webhooks/{id}` | `guesty webhook update --live` | PUT | ✅ Full |
| `DELETE /v1/webhooks/{id}` | `guesty webhook delete --live` | DELETE | ✅ Full |
| **Views** | | | |
| `GET /v1/views` | `guesty views --section` | GET | ✅ Full |
| **Integrations** | | | |
| `GET /v1/integrations` | `guesty integrations --live` | GET | ⚠️ Mock data fallback |
| `GET /v1/channels` | `guesty integrations --live` | GET | ⚠️ Fallback endpoint |

Legend: ✅ Full support | ⚠️ Partial/Fallback | ❌ Not implemented

## Guesty API Compliance

This CLI fully respects Guesty's API constraints:

| Constraint | Implementation |
|-----------|---------------|
| **OAuth2 client_credentials** | `POST /oauth2/token` with `application/x-www-form-urlencoded` |
| **Max 5 tokens per 24 hours** | Tracks generation timestamps, blocks when limit reached |
| **Token caching** | Cached in config.json, reused until 5 minutes before expiry |
| **Rate limits** (15/sec, 120/min, 5000/hr) | Tracks from `X-RateLimit-Remaining-*` response headers |
| **Pre-flight throttling** | Pauses 1-2s when approaching limits |
| **429 Too Many Requests** | Exponential backoff + respects `Retry-After` header |
| **401 Unauthorized** | Auto-clears token cache, retries with fresh token |
| **Pagination** | Auto-pages with `limit=100` + `skip` parameter |
| **Response formats** | Handles `{results:[]}`, `{data:[]}`, and raw `[]` arrays |
| **SSL verification** | Enabled (no bypass) |
| **Request timeout** | 30 seconds per request |

### Incremental Sync Support

Endpoints supporting incremental sync via `lastUpdatedAt`:

- ✅ `listings` — Full incremental support
- ✅ `reservations` — Full incremental support
- ✅ `guests` — Full incremental support
- ✅ `reviews` — Full incremental support
- ✅ `tasks` — Full incremental support
- ✅ `users` — Full incremental support
- ⚠️ `owners` — Full sync only
- ⚠️ `financials` — Full sync only
- ⚠️ `webhooks` — Full sync only

## For AI Agents

This CLI is designed to be used by AI agents (Claude, GPT, etc.) for vacation rental automation.

### Setup for Agents

```bash
# 1. Clone and configure
git clone https://github.com/YOUR_ORG/guesty-cli.git
cd guesty-cli

# 2. Create config
mkdir -p ~/.guesty-cli
cat > ~/.guesty-cli/config.json << 'EOF'
{
  "client_id": "YOUR_GUESTY_CLIENT_ID",
  "client_secret": "YOUR_GUESTY_CLIENT_SECRET",
  "account_name": "your-company",
  "api_base_url": "https://open-api.guesty.com",
  "db_path": "~/.guesty-cli/guesty.db"
}
EOF

# 3. Sync data
python -m guesty_cli.main sync

# 4. Ready to use
python -m guesty_cli.main status
```

### Agent Best Practices

1. **Always sync first** — Run `guesty sync` before querying to ensure fresh data
2. **Use `--json` for parsing** — All commands support `--json` for structured output
3. **Use `--dry-run` before writes** — Preview changes before executing with `--live`
4. **Use nicknames for listings** — `guesty listing get "Emerald Oasis"` works (resolves from local DB)
5. **Use confirmation codes for reservations** — `guesty reservation get "HM4STAP88M"` (resolves from local DB)
6. **Check rate limits** — Token limit is 5 per 24h. The CLI caches tokens automatically
7. **Search locally** — `guesty search "pool"` uses FTS5 locally, no API call needed
8. **Export for analysis** — `guesty export reservations --format json` for bulk data processing

### Example Agent Workflow

```bash
# Morning check
guesty sync
guesty reservations --today --json | python -c "
import sys, json
data = json.load(sys.stdin)
checkins = [r for r in data if r.get('status') == 'confirmed']
print(f'{len(checkins)} check-ins today')
for r in checkins:
    print(f\"  {r['confirmationCode']} - {r.get('guestName', 'N/A')} @ {r.get('listingNickname', 'N/A')}\")
"

# Block dates for maintenance
guesty calendar block "Emerald Oasis" 2025-04-01 --to 2025-04-05 --reason "Pool repair" --dry-run
# Review the dry-run output, then:
guesty calendar block "Emerald Oasis" 2025-04-01 --to 2025-04-05 --reason "Pool repair" --live

# Create a task
guesty task create --title "Fix pool heater" --listing "Emerald Oasis" --priority high --dry-run
guesty task create --title "Fix pool heater" --listing "Emerald Oasis" --priority high --live

# Generate monthly owner statement
guesty owner statement "John Smith" --month 2024-03 --management-fee 20 --format json

# Check occupancy and find gaps
guesty occupancy --month 2024-03 --json
guesty occupancy gaps --from 2024-04-01 --to 2024-04-30 --json

# Listen for webhook events
guesty webhook watch --port 8080 --json
```

### JSON Output Examples

#### Reservation Detail
```bash
$ guesty reservation get HM4STAP88M --json
```

```json
{
  "id": "65a1b2c3d4e5f6g7h8i9j0k1",
  "confirmationCode": "HM4STAP88M",
  "status": "confirmed",
  "source": "airbnb2",
  "checkIn": "2024-03-15T15:00:00.000Z",
  "checkOut": "2024-03-20T11:00:00.000Z",
  "listingId": "listing_123",
  "listingNickname": "Sunset Villa",
  "guestName": "Jane Smith",
  "guestEmail": "jane@example.com",
  "guestPhone": "+1-555-123-4567",
  "nightsCount": 5,
  "guestsCount": 4,
  "totalPrice": 2850.00,
  "payoutAmount": 2650.50,
  "balanceDue": 0.00,
  "currency": "USD"
}
```

#### Revenue Report
```bash
$ guesty financials revenue --month 2024-03 --json
```

```json
{
  "month": "2024-03",
  "summary": {
    "total_revenue": 45250.00,
    "accommodation_fare": 38500.00,
    "cleaning_fees": 4200.00,
    "additional_fees": 1550.00,
    "platform_fees": 3250.00,
    "discounts": 800.00,
    "taxes_collected": 4525.00,
    "net_revenue": 38200.00,
    "reservation_count": 28
  },
  "by_listing": {
    "Sunset Villa": {
      "revenue": 12500.00,
      "cleaning_fees": 1200.00,
      "platform_fees": 875.00,
      "net_revenue": 10825.00,
      "reservation_count": 8
    }
  },
  "by_owner": {
    "John Smith": {
      "revenue": 18750.00,
      "net_revenue": 15937.50,
      "reservation_count": 12
    }
  }
}
```

#### Occupancy Report
```bash
$ guesty occupancy --month 2024-03 --json
```

```json
{
  "period_start": "2024-03-01",
  "period_end": "2024-03-31",
  "total_days": 31,
  "available_days": 28,
  "booked_days": 22,
  "blocked_days": 3,
  "occupancy_rate": 78.57,
  "total_revenue": 45250.00,
  "total_nights": 98,
  "adr": 461.73,
  "revpar": 362.95,
  "reservation_count": 28
}
```

#### Gap Analysis
```bash
$ guesty occupancy gaps --from 2024-04-01 --to 2024-04-30 --json
```

```json
[
  {
    "listing_id": "listing_123",
    "listing_name": "Sunset Villa",
    "gap_start": "2024-04-05",
    "gap_end": "2024-04-06",
    "gap_nights": 2,
    "before_reservation_id": "res_001",
    "after_reservation_id": "res_002",
    "current_avg_price": 450.00,
    "suggested_adjustment": -5,
    "suggested_adjustment_display": "-5%",
    "days_until": 28,
    "urgency": "Low"
  }
]
```

#### Owner Statement
```bash
$ guesty owner statement "John Smith" --month 2024-03 --format json
```

```json
{
  "owner_name": "John Smith",
  "month": "2024-03",
  "management_fee_rate": 20.0,
  "gross_revenue": 18750.00,
  "cleaning_fees": 1800.00,
  "platform_fees": 1312.50,
  "management_fee": 3750.00,
  "net_payout": 15487.50,
  "by_property": {
    "Sunset Villa": 12500.00,
    "Ocean View": 6250.00
  }
}
```

#### Webhook Event
```bash
$ guesty webhook watch --port 8080 --json
```

```json
{
  "event": "reservation.new",
  "timestamp": "2024-03-15T10:30:00.000Z",
  "reservation": {
    "_id": "65a1b2c3d4e5f6g7h8i9j0k1",
    "confirmationCode": "HM4STAP88M",
    "status": "confirmed",
    "checkIn": "2024-04-01",
    "checkOut": "2024-04-05"
  }
}
```

## Database Schema

The local SQLite database stores synced data for fast offline queries:

| Table | Key Fields | Notes |
|-------|-----------|-------|
| `listings` | id, nickname, title, address, city, bedrooms, bathrooms, maxGuests | Property inventory |
| `reservations` | id, confirmationCode, guestId, listingId, checkIn, checkOut, status, source, totalPrice | Booking data |
| `guests` | id, fullName, email, phone, nationality | Guest directory |
| `owners` | id, fullName, email, phone, isActive | Property owners |
| `users` | id, firstName, lastName, email, role, active | Team members |
| `reviews` | id, listingId, rating, content, guestName | Guest reviews |
| `tasks` | id, listingId, title, status, priority, dueDate | Maintenance tasks |
| `webhooks` | id, url, events, active | Webhook registrations |
| `financials` | id, reservationId, type, description, amount | Financial line items |
| `invoice_items` | id, reservation_id, listing_id, type, description, amount | Invoice breakdown |
| `tax_line_items` | id, reservation_id, listing_id, name, rate, amount | Tax details |
| `calendar_days` | id, listing_id, date, status, price, min_stay, reservation_id | Calendar cache |
| `search_index` | FTS5 virtual table | Full-text search across all data |
| `auth_tokens` | token, expires_at, created_at | Token cache (auto-managed) |
| `sync_log` | endpoint, timestamp, records_synced, duration_seconds, status | Sync history |
| `sync_cursors` | table_name, last_cursor, last_synced_at, record_count, status | Incremental sync cursors |
| `webhook_events` | id, event_type, payload, status, retry_count, created_at | Webhook queue |

## Requirements

- **Python 3.8+** (uses `datetime.fromisoformat`, `typing` hints)
- **No external packages** — stdlib only (`urllib.request`, `sqlite3`, `argparse`, `json`, `csv`)
- **Guesty API access** — Requires Open API credentials from Guesty Dashboard

## Security

- **Credentials stored locally** in `~/.guesty-cli/config.json` (never committed to git)
- **Tokens cached locally** and auto-refreshed (never logged or exposed)
- **SSL verification** enabled on all API calls
- **No telemetry** — nothing phoned home, no analytics, no tracking
- **`--dry-run` by default** on all write operations — you must explicitly opt in with `--live`

## Contributing

PRs welcome. Please:
1. Keep zero-dependency constraint (stdlib only)
2. Add `--dry-run` support to any new write commands
3. Add `--json` output to any new read commands
4. Test with `--help` on all new subcommands
5. Follow existing code patterns in `commands/` directory

## License

MIT — See [LICENSE](LICENSE) for details.

---

Built with 🌴 by [Villa Paraiso Vacation Rentals](https://paraisovacationrentals.com)
