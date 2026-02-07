# Guesty CLI Enhancement Plan v2.0
## Objective: Complete API Endpoint Coverage

**Goal:** Implement CLI commands for EVERY available Guesty Open API v1 endpoint.

---

## ✅ IMPLEMENTED (All Verified Endpoints)

### Core Resources (FULL CRUD)
| Endpoint | Methods | CLI Commands | Status |
|----------|---------|--------------|--------|
| `/v1/listings` | GET/POST/PUT/DELETE | `guesty listings`, `listing get/create/update/delete` | ✅ |
| `/v1/reservations` | GET/POST/PUT/DELETE | `guesty reservations`, `reservation get/create/update/cancel` | ✅ |
| `/v1/tasks` | GET/POST/PUT/DELETE | `guesty tasks`, `task get/create/update/delete` | ✅ |
| `/v1/webhooks` | GET/POST/PUT/DELETE | `guesty webhooks`, `webhook get/create/update/delete` | ✅ |
| `/v1/owners` | GET | `guesty owners`, `owner get` | ✅ |
| `/v1/owners/{id}/reservations` | GET | `guesty owner reservations <id>` | ✅ |

### Read-Only Resources
| Endpoint | CLI Commands | Status |
|----------|--------------|--------|
| `/v1/guests` | `guesty guests`, `guest get` | ✅ |
| `/v1/reviews` | `guesty reviews` | ✅ |
| `/v1/users` | `guesty users`, `user get` | ✅ |
| `/v1/integrations` | `guesty integrations`, `integration get` | ✅ |
| `/v1/calendar/{id}` | `guesty calendar`, `calendar block/unblock/price` | ✅ |

### Advanced Features
| Feature | CLI Commands | Status |
|---------|--------------|--------|
| Calendar bulk operations | `guesty calendar sync-all`, `block-all`, `price-all` | ✅ |
| Incremental sync | `guesty sync --incremental` | ✅ |
| Enhanced filters | `guesty reservations --filter` | ✅ |
| Webhook server | `guesty webhook server --persist` | ✅ |

---

## 🟡 IN PROGRESS

| Endpoint | CLI Command | Assigned |
|----------|-------------|----------|
| `/v1/views?section=X` | `guesty views --section reservations/listings` | Sub-agent |

---

## VERIFICATION CHECKLIST

- [ ] All 12 verified endpoints have working CLI commands
- [ ] Each command tested with live API
- [ ] Response formats handled (results[], data[], raw arrays)
- [ ] Error handling for 404/401/429

---

## ENDPOINTS CONFIRMED NOT EXISTING (404)

These were tested and return 404:
- `/v1/conversations`
- `/v1/messages`  
- `/v1/reservations/{id}/messages`
- `/v1/reservations/{id}/invoice`
- `/v1/reservations/{id}/payments`
- `/v1/invoices`
- `/v1/payments`
- `/v1/reports`

---

## CURRENT COMMAND COUNT

**Before:** 44 commands
**After:** ~60+ commands

---

*Refocused: 2026-02-07 - Company-specific features removed, API coverage prioritized*
