# guesty-cli

> The missing CLI for [Guesty PMS](https://guesty.com) — manage your vacation rental operations from the terminal.

**44 commands** · **Zero dependencies** · **Local-first** · **AI-agent friendly**

```
██████╗ ██╗   ██╗███████╗███████╗████████╗██╗   ██╗
██╔════╝ ██║   ██║██╔════╝██╔════╝╚══██╔══╝╚██╗ ██╔╝
██║  ███╗██║   ██║█████╗  ███████╗   ██║    ╚████╔╝
██║   ██║██║   ██║██╔══╝  ╚════██║   ██║     ╚██╔╝
╚██████╔╝╚██████╔╝███████╗███████║   ██║      ██║
 ╚═════╝  ╚═════╝ ╚══════╝╚══════╝   ╚═╝      ╚═╝
```

## Why?

Guesty has no official CLI. If you manage vacation rentals and want to:
- Query reservations from the terminal
- Sync data locally for fast offline access
- Automate operations with scripts or AI agents
- Export data to CSV/JSON for analysis
- Block calendar dates, update prices, manage tasks

...this is for you.

## Features

- **Zero external dependencies** — Python 3.8+ stdlib only (no `requests`, no `click`, no `rich`)
- **Local-first** — SQLite database with FTS5 full-text search. Query instantly without API calls
- **API-compliant** — Respects all Guesty rate limits, token limits, and auth requirements
- **Safe writes** — `--dry-run` on all create/update commands, `--confirm` on deletes, `--live` required for API calls
- **Pipeline-friendly** — `--json` output on every command for scripting
- **AI-agent ready** — Structured output, predictable flags, comprehensive `--help`

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
guesty reservation get HM4STAP88M     # Reservation detail + financials
guesty listings                        # All properties
guesty search "pool heater"            # Full-text search
guesty export reservations --format csv # Export to CSV
```

## Commands Reference

### Read Operations

| Command | Description |
|---------|-------------|
| `guesty status` | Dashboard overview with stat boxes |
| `guesty listings` | List all properties |
| `guesty listing get <id_or_nickname>` | Property detail card |
| `guesty reservations [--today] [--status X] [--limit N]` | List reservations with filters |
| `guesty reservation get <id_or_code>` | Reservation detail + financial breakdown |
| `guesty guests [--search NAME]` | List/search guests |
| `guesty guest <id_or_email>` | Guest detail card |
| `guesty owners` | List all owners |
| `guesty owner get <id_or_name>` | Owner detail |
| `guesty reviews [--listing X] [--limit N]` | List reviews with ratings |
| `guesty financials` | Revenue by listing, by month, by type |
| `guesty tasks [--limit N]` | List tasks |
| `guesty task get <id>` | Task detail |
| `guesty calendar <listing> [--month YYYY-MM]` | View calendar |
| `guesty search <query>` | Full-text search across all data |
| `guesty webhooks` | List registered webhooks |

### Write Operations

All write operations require `--live` to execute against the API. Without `--live`, they operate on local data or show what would happen.

| Command | Description | Safety |
|---------|-------------|--------|
| `guesty listing create --title X --nickname X` | Create listing | `--dry-run` |
| `guesty listing update <id> --title X` | Update listing | `--dry-run` |
| `guesty listing delete <id>` | Delete listing | `--confirm` |
| `guesty reservation create --listing X --guest-name X --checkin X --checkout X` | Create reservation | `--dry-run` |
| `guesty reservation update <id> --status X --notes X` | Update reservation | `--dry-run` |
| `guesty reservation cancel <id>` | Cancel reservation | `--confirm` |
| `guesty reservation approve <id>` | Approve inquiry | `--live` |
| `guesty reservation decline <id>` | Decline inquiry | `--live` |
| `guesty owner create --name X --email X` | Create owner | `--dry-run` |
| `guesty owner update <id> --name X` | Update owner | `--dry-run` |
| `guesty owner delete <id>` | Delete owner | `--confirm` |
| `guesty task create --title X --listing X` | Create task | `--dry-run` |
| `guesty task update <id> --status X` | Update task | `--dry-run` |
| `guesty task complete <id>` | Mark task done | `--live` |
| `guesty task delete <id>` | Delete task | `--confirm` |
| `guesty calendar block <listing> <date> [--to DATE]` | Block dates | `--dry-run` |
| `guesty calendar unblock <listing> <date> [--to DATE]` | Unblock dates | `--dry-run` |
| `guesty calendar price <listing> <date> <price> [--to DATE]` | Update pricing | `--dry-run` |
| `guesty webhook create --url X --events X` | Create webhook | `--dry-run` |
| `guesty webhook update <id> --events X` | Update webhook | `--dry-run` |
| `guesty webhook delete <id>` | Delete webhook | `--confirm` |
| `guesty webhook test <id>` | Send test ping | `--live` |
| `guesty webhook watch [--port 8080]` | Local webhook listener | — |

### Sync & Export

| Command | Description |
|---------|-------------|
| `guesty sync` | Sync all data from Guesty API |
| `guesty sync <table>` | Sync specific table (listings, reservations, guests, owners, reviews, tasks, webhooks) |
| `guesty export <table> [--format csv\|json]` | Export table to file |
| `guesty auth --refresh` | Force token refresh |
| `guesty auth --revoke` | Clear cached token |

### Global Flags

| Flag | Description |
|------|-------------|
| `--json` | Output as JSON (for piping/scripting) |
| `--no-color` | Disable colored terminal output |
| `--version` | Show version |
| `--help` | Show help for any command |

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
│   ├── guests.py      # Guest lookup
│   ├── owners.py      # Owners CRUD
│   ├── calendar.py    # Calendar view, block/unblock/price
│   ├── tasks.py       # Tasks CRUD
│   ├── reviews.py     # Review display
│   ├── webhooks.py    # Webhooks CRUD + watch server
│   ├── financials.py  # Revenue reports
│   ├── search.py      # FTS5 full-text search
│   ├── sync.py        # API → SQLite sync
│   └── export.py      # CSV/JSON export
└── utils/
    ├── dates.py       # Date parsing + formatting
    ├── filters.py     # Query filter builders
    └── resolve.py     # Nickname/name → ID resolution
```

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

### API Endpoints Used

| Endpoint | Method | Used By |
|----------|--------|---------|
| `POST /oauth2/token` | POST | `guesty auth` |
| `GET /v1/listings` | GET | `guesty listings`, `guesty sync listings` |
| `POST /v1/listings` | POST | `guesty listing create --live` |
| `PUT /v1/listings/{id}` | PUT | `guesty listing update --live` |
| `DELETE /v1/listings/{id}` | DELETE | `guesty listing delete --live` |
| `GET /v1/reservations` | GET | `guesty reservations`, `guesty sync reservations` |
| `POST /v1/reservations` | POST | `guesty reservation create --live` |
| `PUT /v1/reservations/{id}` | PUT | `guesty reservation update --live` |
| `POST /v1/reservations/{id}/cancel` | POST | `guesty reservation cancel --live` |
| `POST /v1/reservations/{id}/approve` | POST | `guesty reservation approve --live` |
| `POST /v1/reservations/{id}/decline` | POST | `guesty reservation decline --live` |
| `GET /v1/guests` | GET | `guesty guests`, `guesty sync guests` |
| `GET /v1/owners-reservations/owners` | GET | `guesty owners`, `guesty sync owners` |
| `POST /v1/owners-reservations/owners` | POST | `guesty owner create --live` |
| `PUT /v1/owners-reservations/owners/{id}` | PUT | `guesty owner update --live` |
| `DELETE /v1/owners-reservations/owners/{id}` | DELETE | `guesty owner delete --live` |
| `GET /v1/reviews` | GET | `guesty reviews`, `guesty sync reviews` |
| `GET /v1/tasks` | GET | `guesty tasks`, `guesty sync tasks` |
| `POST /v1/tasks` | POST | `guesty task create --live` |
| `PUT /v1/tasks/{id}` | PUT | `guesty task update --live` |
| `DELETE /v1/tasks/{id}` | DELETE | `guesty task delete --live` |
| `GET /v1/availability-pricing/api/calendar/listings/{id}` | GET | `guesty calendar` |
| `PUT /v1/availability-pricing/api/calendar/listings/{id}` | PUT | `guesty calendar block/unblock/price --live` |
| `GET /v1/webhooks` | GET | `guesty webhooks`, `guesty sync webhooks` |
| `POST /v1/webhooks` | POST | `guesty webhook create --live` |
| `PUT /v1/webhooks/{id}` | PUT | `guesty webhook update --live` |
| `DELETE /v1/webhooks/{id}` | DELETE | `guesty webhook delete --live` |

### Important: Reservation Fields

The Guesty API returns **minimal fields by default** for reservations. To get full data (status, source, prices, guest info), the sync command requests these fields explicitly:

```
confirmationCode status source checkIn checkOut checkInDateLocalized checkOutDateLocalized
listingId guestId guest.firstName guest.lastName guest.fullName guest.email guest.phone
money.hostPayout money.totalPaid money.balanceDue money.currency
nightsCount guestsCount createdAt confirmedAt
```

### Source Name Mapping

| API Value | Display Name |
|-----------|-------------|
| `airbnb2` | Airbnb |
| `homeaway2` | VRBO |
| `bookingcom` | Booking.com |
| `BE-API` | Direct |
| `manual` | Manual |

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
6. **Check rate limits** — Token limit is 5 per 24h. The CLI caches tokens automatically, but avoid calling `guesty auth --revoke` unnecessarily
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

# Listen for webhook events
guesty webhook watch --port 8080 --json
```

## Database Schema

The local SQLite database stores synced data for fast offline queries:

| Table | Key Fields | Notes |
|-------|-----------|-------|
| `listings` | id, nickname, title, address, city, bedrooms, bathrooms, maxGuests | Property inventory |
| `reservations` | id, confirmationCode, guestId, listingId, checkIn, checkOut, status, source, totalPrice | Booking data |
| `guests` | id, fullName, email, phone, nationality | Guest directory |
| `owners` | id, fullName, email, phone, isActive | Property owners |
| `reviews` | id, listingId, rating, content, guestName | Guest reviews |
| `tasks` | id, listingId, title, status, priority, dueDate | Maintenance tasks |
| `webhooks` | id, url, events, active | Webhook registrations |
| `financials` | id, reservationId, type, description, amount | Financial line items |
| `search_index` | FTS5 virtual table | Full-text search across all data |
| `auth_tokens` | token, expires_at, created_at | Token cache (auto-managed) |

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
