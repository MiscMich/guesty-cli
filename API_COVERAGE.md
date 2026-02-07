# Guesty CLI API Coverage

## Complete Endpoint Matrix

### ✅ Fully Implemented (11/12 Verified Endpoints)

| # | Endpoint | Methods | CLI Commands | Status |
|---|----------|---------|--------------|--------|
| 1 | `/v1/listings` | GET, POST, PUT, DELETE | `guesty listings`, `listing get/create/update/delete` | ✅ Working |
| 2 | `/v1/reservations` | GET, POST, PUT, DELETE | `guesty reservations`, `reservation get/create/update/cancel/approve/decline` | ✅ Working |
| 3 | `/v1/guests` | GET | `guesty guests`, `guest get` | ✅ Read-only |
| 4 | `/v1/owners` | GET | `guesty owners`, `owner get` | ✅ Working |
| 5 | `/v1/tasks` | GET, POST, PUT, DELETE | `guesty tasks`, `task get/create/update/delete/complete` | ✅ Working |
| 6 | `/v1/reviews` | GET | `guesty reviews` | ✅ Read-only |
| 7 | `/v1/calendar/{id}` | GET, PUT | `guesty calendar`, `calendar block/unblock/price` | ✅ Working |
| 8 | `/v1/webhooks` | GET, POST, PUT, DELETE | `guesty webhooks`, `webhook get/create/update/delete/test/watch` | ✅ Working |
| 9 | `/v1/users` | GET | `guesty users`, `user get` | ✅ Read-only |
| 10 | `/v1/integrations` | GET | `guesty integrations`, `integration get` | ✅ Read-only |
| 11 | `/v1/views` | GET | `guesty views --section reservations/listings` | ✅ Working |

### ❌ Non-Functional (1 Endpoint)

| # | Endpoint | Expected | Actual | Notes |
|---|----------|----------|--------|-------|
| 12 | `/v1/owners/{id}/reservations` | GET | 404 | Documented but returns "Cannot GET" |

**Workaround:** Use `guesty reservations` with `listingId` filter for owner's properties.

---

## Permission Levels

### Standard `open-api` Scope (Current)

**Full CRUD (Read + Write):**
- Listings
- Reservations
- Tasks
- Calendar (block/unblock/price)
- Webhooks

**Read-Only:**
- Guests
- Owners
- Reviews
- Users
- Integrations
- Views

### Elevated Permissions (Require Guesty Support)

These endpoints exist but return "permission denied":

| Endpoint | Method | Feature |
|----------|--------|---------|
| `/v1/reviews/{id}/reply` | POST | Reply to reviews |
| `/v1/guests` | POST/PUT/DELETE | Create/update guests |
| `/v1/listings/{id}/photos` | GET/POST | Photo management |
| `/v1/conversations` | GET | Messaging |
| `/v1/messages` | GET | Message history |
| `/v1/reports` | GET | Native reports |
| `/v1/analytics` | GET | Analytics data |
| `/v1/invoices` | GET | Invoice details |
| `/v1/payments` | GET | Payment records |

To unlock: Contact Guesty support for elevated API permissions.

---

## Command Count: 60+

### By Category

| Category | Command Count | Examples |
|----------|---------------|----------|
| **Listings** | 6 | `listings`, `listing get/create/update/delete` |
| **Reservations** | 8 | `reservations`, `reservation get/create/update/cancel/approve/decline` |
| **Calendar** | 8 | `calendar`, `calendar sync/sync-all/block-all/unblock-all/price-all/price-dynamic` |
| **Guests** | 2 | `guests`, `guest get` |
| **Owners** | 4 | `owners`, `owner get`, `owner reservations`, `owner statement` |
| **Tasks** | 6 | `tasks`, `task get/create/update/delete/complete` |
| **Reviews** | 2 | `reviews`, `review get` |
| **Webhooks** | 8 | `webhooks`, `webhook get/create/update/delete/test/watch/queue` |
| **Users** | 2 | `users`, `user get` |
| **Integrations** | 2 | `integrations`, `integration get` |
| **Financials** | 4 | `financials revenue/taxes/dr15`, `statements` |
| **Occupancy** | 2 | `occupancy --month/--year/gaps` |
| **Views** | 1 | `views --section` |
| **Search** | 1 | `search` |
| **Sync** | 3 | `sync`, `sync --incremental`, `sync --status` |
| **Export** | 1 | `export` |
| **Auth** | 2 | `init`, `auth --refresh/--revoke` |
| **Status** | 1 | `status` |

**Total: 60+ distinct command paths**

---

## API Response Formats Handled

| Format | Endpoints | Example |
|--------|-----------|---------|
| `{"results": [], "count": N}` | listings, reservations, guests, tasks, users | Standard paginated |
| `{"data": [], "limit": N}` | reviews | No count field |
| `[...]` (raw array) | owners, webhooks, integrations, calendar | Direct array |
| `[...]` (calendar days) | calendar/{id} | Day objects |

---

## Incremental Sync Support

| Endpoint | Incremental | Notes |
|----------|-------------|-------|
| Listings | ✅ | Uses `lastUpdatedAt` |
| Reservations | ✅ | Uses `lastUpdatedAt` |
| Guests | ✅ | Uses `lastUpdatedAt` |
| Reviews | ✅ | Uses `lastUpdatedAt` |
| Tasks | ✅ | Uses `lastUpdatedAt` |
| Users | ✅ | Uses `lastUpdatedAt` |
| Owners | ❌ | Raw array, no timestamp |
| Webhooks | ❌ | Raw array, no timestamp |
| Integrations | ❌ | Raw array, no timestamp |

---

## Testing Summary

**Test Date:** 2026-02-07
**Test Method:** Live API calls with production credentials
**Results:** 11/12 endpoints working (91.7% coverage)

### Verified Working:
- ✅ Listings: 22 properties
- ✅ Reservations: 213 records
- ✅ Guests: 3,577 profiles
- ✅ Owners: 17 owners
- ✅ Tasks: 111 tasks
- ✅ Reviews: 533 reviews
- ✅ Calendar: 31-day ranges
- ✅ Webhooks: 18 webhooks
- ✅ Users: 10 users
- ✅ Integrations: 15 connections
- ✅ Views: 31 report views

### Verified Non-Existent:
- ❌ Owner reservations sub-endpoint (404)

---

## For AI Agents

### Optimal Patterns

**Read Operations (Local DB):**
```bash
guesty reservations --today --json           # Fast, no API call
guesty occupancy --month 2024-01 --json      # Local analytics
guesty search "guest name"                   # FTS5 search
```

**Write Operations (Always --dry-run first):**
```bash
guesty calendar block-all --from DATE --to DATE --listings "id1,id2" --dry-run
guesty task create --title "Fix AC" --listing "Property" --dry-run
guesty reservation update CODE --status canceled --dry-run
```

**Sync Operations (Incremental preferred):**
```bash
guesty sync --incremental                    # Only changes since last sync
guesty sync reservations --incremental       # Specific table
guesty sync                                  # Full sync when needed
```

### Rate Limit Awareness

| Limit | Value | CLI Handling |
|-------|-------|--------------|
| Per Second | 15 | Pre-flight throttling |
| Per Minute | 120 | Header tracking |
| Per Hour | 5,000 | Automatic backoff |
| Tokens/24h | 5 | Cached, auto-refresh |

---

## Summary

- **Working Endpoints:** 11/12 (91.7%)
- **CLI Commands:** 60+
- **Read Operations:** 30+
- **Write Operations:** 20+
- **Database Tables:** 16
- **Agent-Optimized:** ✅ JSON output, structured data, pipeline-friendly

**All available Guesty API endpoints with standard permissions are now covered by the CLI.**

---

*Last Updated: 2026-02-07*
*CLI Version: v0.2.0*
