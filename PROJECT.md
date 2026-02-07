# guesty-cli — Universal Command-Line Interface for Guesty

> The missing CLI for Guesty PMS. Query, manage, and automate your vacation rental operations from the terminal.

## Architecture

```
guesty-cli/
├── guesty_cli/
│   ├── __init__.py          # Package init, version
│   ├── main.py              # Entry point, argument parsing
│   ├── core/
│   │   ├── __init__.py
│   │   ├── client.py        # HTTP client, auth, token caching, rate limiting
│   │   ├── config.py        # Config management (~/.guesty-cli/config.json)
│   │   ├── database.py      # SQLite local cache, schema, migrations
│   │   └── output.py        # Table formatting, colors, JSON/CSV output
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── auth.py          # init, auth, token management
│   │   ├── listings.py      # listings list/get/create/update/delete
│   │   ├── reservations.py  # reservations list/get/create/update/cancel/approve/decline
│   │   ├── guests.py        # guests list/get/search
│   │   ├── owners.py        # owners list/get/create/update/delete + documents
│   │   ├── calendar.py      # calendar get/update/block/unblock
│   │   ├── tasks.py         # tasks list/get/create/update/delete
│   │   ├── reviews.py       # reviews list/get
│   │   ├── webhooks.py      # webhooks list/get/create/update/delete + watch
│   │   ├── financials.py    # financials summary/by-listing/by-month/by-source
│   │   ├── expenses.py      # expenses list/get/create/attach
│   │   ├── accounting.py    # journal entries
│   │   ├── payments.py      # transactions/reconciliation (beta)
│   │   ├── sync.py          # full/incremental sync to local SQLite
│   │   ├── search.py        # full-text search across all tables
│   │   ├── status.py        # dashboard overview
│   │   └── export.py        # bulk export csv/json
│   └── utils/
│       ├── __init__.py
│       ├── dates.py         # Date parsing (today, yesterday, last-week, YYYY-MM-DD)
│       └── filters.py       # Guesty filter builder
├── tests/
│   └── ...
├── setup.py                 # pip install
├── pyproject.toml           # Modern Python packaging
├── README.md                # User-facing docs
├── LICENSE                   # MIT
└── PROJECT.md               # This file (internal architecture doc)
```

## Design Principles

1. **Zero dependencies** — stdlib only (no requests, no click, no rich)
   - HTTP: `urllib.request` / `http.client`
   - CLI: `argparse`
   - DB: `sqlite3`
   - Colors: ANSI escape codes
2. **Offline-first** — Local SQLite cache for fast queries
3. **API-first** — Every command can hit live API with `--live` flag
4. **Pipeline-friendly** — `--json` and `--csv` on everything, `--no-color`
5. **Interactive setup** — `guesty init` walks you through config
6. **Rate-limit aware** — Built-in retry with exponential backoff, respects Retry-After headers
7. **Token caching** — Auto-refresh, max 5 tokens/24h, persists to config

## Guesty Open API Coverage

### Base URL: `https://open-api.guesty.com/v1`

### Auth: `POST /oauth2/token` (OAuth2 client_credentials, form-urlencoded)
- Max 5 tokens per 24h per clientId
- Token valid for 24h
- Cache and reuse!

### Rate Limits
| Limit | Value |
|-------|-------|
| Per Second | 15 |
| Per Minute | 120 |
| Per Hour | 5,000 |

### Response Formats (CRITICAL — different endpoints use different formats!)
| Format | Endpoints |
|--------|-----------|
| `{"results": [], "count": N}` | listings, reservations, guests, tasks, users |
| `{"data": [], "limit": N}` | reviews (NO count field!) |
| `[...]` (raw array) | owners, webhooks, integrations, calendar |

### Pagination
- `limit` (1-100, default 25) + `skip` (offset)
- Must paginate to get all records

### Filtering
```json
[{"field": "status", "operator": "$eq", "value": "confirmed"}]
```
Operators: `$eq`, `$ne`, `$gt`, `$lt`, `$between` (needs from/to), `$in`, `$contains`, `$not`, `$notcontains`

### Verified Endpoints (v1)

#### Listings
- `GET /v1/listings` — List all (paginated)
- `POST /v1/listings` — Create
- `GET /v1/listings/{id}` — Get details
- `PUT /v1/listings/{id}` — Update
- `DELETE /v1/listings/{id}` — Delete

#### Reservations
- `GET /v1/reservations` — List (paginated, filterable)
- `POST /v1/reservations` — Create
- `GET /v1/reservations/{id}` — Get details
- `PUT /v1/reservations/{id}` — Update
- `DELETE /v1/reservations/{id}` — Cancel

#### Guests
- `GET /v1/guests` — List (paginated)
- `GET /v1/guests/{id}` — Get details

#### Owners
- `GET /v1/owners` — List (raw array!)
- `GET /v1/owners/{id}` — Get details
- `GET /v1/owners/{id}/reservations` — Owner's reservations
- `POST /v1/owners` — Create
- `PUT /v1/owners/{id}` — Update
- `DELETE /v1/owners/{id}` — Delete

#### Tasks
- `GET /v1/tasks` — List (paginated)
- `POST /v1/tasks` — Create
- `GET /v1/tasks/{id}` — Get details
- `PUT /v1/tasks/{id}` — Update
- `DELETE /v1/tasks/{id}` — Delete

#### Reviews
- `GET /v1/reviews` — List (uses {"data":[], "limit":N} format!)
- `GET /v1/reviews/{id}` — Get details

#### Calendar
- `GET /v1/listings/{id}/calendar?from=YYYY-MM-DD&to=YYYY-MM-DD` — Get calendar
- `PUT /v1/listings/{id}/calendar` — Update calendar (block/unblock/price)

#### Webhooks
- `GET /v1/webhooks` — List (raw array)
- `POST /v1/webhooks` — Create
- `GET /v1/webhooks/{id}` — Get details
- `PUT /v1/webhooks/{id}` — Update (events only, NOT url)
- `DELETE /v1/webhooks/{id}` — Delete

#### Users
- `GET /v1/users` — List (paginated)
- `GET /v1/users/{id}` — Get details

#### Integrations
- `GET /v1/integrations` — List (raw array)
- `GET /v1/integrations/{id}` — Get details

#### Views
- `GET /v1/views?section=reservations` — Custom reports
- `GET /v1/views?section=listings`

### Newer Endpoints (from changelog, need live verification)
- `POST /reservations-v3` — Quick booking
- `GET /reservations-v3` — Enhanced reservation data
- `POST /reservations/{id}/approve` — Approve channel reservation
- `POST /reservations/{id}/decline` — Decline
- `POST /reservations/{id}/request-cancellation` — Request cancellation
- `/expenses-api/expenses` — CRUD + attachments
- `/accounting-api/` — Journal entries
- `/owners/{id}/documents` — Owner document management
- `GET /availability-pricing-api/calendar/listings/minified/{listingId}` — Optimized calendar

### Webhook Events
- reservation.new, reservation.updated
- reservation.messageReceived, reservation.messageSent
- payments.received, payments.failed, payments.refunded, payments.overdue, payments.overcharged, payments.authenticationRequired, payments.authorizationHoldFailed, payments.disputes
- listing.new, listing.updated, listing.removed
- listing.calendar.updated, calendar.updated.v2
- task.created, task.updated, task.deleted
- guest.created, guest.updated, guest.deleted

## SQLite Schema (Local Cache)

```sql
-- Config
CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT);

-- Core tables (mirror API)
CREATE TABLE listings (...);
CREATE TABLE reservations (...);
CREATE TABLE guests (...);
CREATE TABLE owners (...);
CREATE TABLE reviews (...);
CREATE TABLE tasks (...);
CREATE TABLE financials (...);
CREATE TABLE webhooks (...);
CREATE TABLE users (...);
CREATE TABLE integrations (...);

-- Sync tracking
CREATE TABLE sync_log (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, endpoint TEXT, records_synced INTEGER, duration_seconds REAL, status TEXT, error_message TEXT);

-- Auth
CREATE TABLE auth_tokens (id INTEGER PRIMARY KEY, token TEXT, expires_at TEXT, created_at TEXT);

-- FTS
CREATE VIRTUAL TABLE search_index USING fts5(table_name, record_id, content);
```

## Testing with Real Data

Our VPVR Guesty account:
- API: `open-api.guesty.com`
- 22 listings, 2,361 reservations, 3,573 guests, 17 owners, 100 reviews
- Credentials in `~/.openclaw/.env` (GUESTY_CLIENT_ID, GUESTY_CLIENT_SECRET)
- Existing DB: `~/.openclaw/guesty-data/database/guesty.db`
