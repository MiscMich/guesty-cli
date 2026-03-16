# AGENTS.md — AI Agent Operations Guide for guesty-cli

> **⚠️ PRIMARY INTERFACE**: This CLI is the canonical tool for ALL Guesty PMS operations. Always use `guesty` commands instead of raw API calls or database queries.

---

## 1. Agent Quick Start

### Minimal Setup (Copy-Paste Ready)

```bash
# 1. Verify installation
guesty --version

# 2. Check current status (validates auth + shows stats)
guesty status

# 3. If not configured, initialize (one-time setup)
guesty init
# Enter: client_id, client_secret, account_name when prompted

# 4. Sync data from API to local database
guesty sync

# 5. Ready to query
guesty reservations --today
```

### First-Time Agent Configuration

```bash
# Option A: Environment variables (recommended for CI/agents)
export GUESTY_CLIENT_ID="your-client-id"
export GUESTY_CLIENT_SECRET="your-client-secret"
guesty --no-input init

# Option B: Import from JSON file
echo '{"client_id":"...","client_secret":"..."}' | guesty auth-import -

# Option C: Interactive (for humans)
guesty init
```

### Token-Efficient Agent Workflow

**CRITICAL**: Guesty limits you to 5 token requests per 24h per API key.

```bash
# Step 1: Get a token ONCE (burns 1 of 5 daily slots)
TOKEN=$(guesty auth-token)

# Step 2: Use --access-token for ALL subsequent commands (0 slots burned)
guesty --access-token "$TOKEN" --json listings list
guesty --access-token "$TOKEN" --json reservations list
# ... unlimited commands with the same token (valid 24h)
```

**DO NOT** create a new GuestyClient or call `auth --refresh` per command. The token is cached in the OS keychain and automatically reused.

---

## 2. Structured Output (--json)

### Always Use --json for Reliable Parsing

All commands support `--json` for machine-readable output. **Never parse human-readable tables.**

```bash
# ❌ Fragile — parsing tables breaks easily
guesty reservations --today | grep "HM4STAP88M"

# ✅ Robust — structured JSON
guesty reservations --today --json
```

### JSON Output Patterns

```bash
# Pattern 1: Direct JSON parsing with Python
guesty reservations --today --json | python3 -c "
import sys, json
data = json.load(sys.stdin)
for r in data.get('results', []):
    print(f\"{r['confirmationCode']}: {r.get('guestName', 'N/A')}\")
"

# Pattern 2: Extract specific fields
guesty reservation get HM4STAP88M --json | python3 -c "
import sys, json
data = json.load(sys.stdin)
res = data.get('reservation', {})
print(f\"Guest: {res.get('guest', {}).get('fullName')}\")
print(f\"Check-in: {res.get('checkIn')}\")
print(f\"Payout: ${res.get('money', {}).get('hostPayout', 0)}\")
"

# Pattern 3: Count and aggregate
guesty financials --json | python3 -c "
import sys, json
data = json.load(sys.stdin)
total = sum(item['amount'] for item in data.get('by_listing', []))
print(f'Total revenue: ${total:,.2f}')
"

# Pattern 4: Filter and transform
guesty reservations --status confirmed --json | python3 -c "
import sys, json, datetime
data = json.load(sys.stdin)
today = datetime.date.today().isoformat()
checkins_today = [r for r in data.get('results', []) if r.get('checkIn', '').startswith(today)]
print(json.dumps(checkins_today, indent=2))
"
```

### TSV Output for Shell Pipelines

```bash
# Pipe-friendly tab-separated output
guesty --plain reservations list | awk -F'\t' '{print $1, $3}'
guesty --plain exit-codes | cut -f1,2

# Field selection in JSON mode
guesty --json --select id,status,guest.name reservations list
guesty --json --results-only listings list  # Strip pagination envelope
```

### Exit Codes for Error Handling

```bash
guesty --json reservations get CONF123
case $? in
  0) echo "Success" ;;
  3) echo "No results found" ;;
  4) echo "Authentication required — run: TOKEN=\$(guesty auth-token)" ;;
  5) echo "Resource not found" ;;
  7) echo "Rate limited — wait and retry" ;;
  8) echo "Transient error — retry" ;;
  *) echo "Unknown error" ;;
esac
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `GUESTY_ACCESS_TOKEN` | Use provided access token (bypasses OAuth) |
| `GUESTY_CLIENT_ID` | Override client_id from config |
| `GUESTY_CLIENT_SECRET` | Override client_secret from config |
| `GUESTY_AUTO_JSON` | Set to `1` for auto-JSON when stdout is piped |
| `GUESTY_NO_INPUT` | Set to `1` to prevent all interactive prompts |
| `GUESTY_DEBUG` | Set to `1` for verbose debug output |
| `NO_COLOR` | Disable colored output |

### Status Check JSON Structure

```bash
guesty status --json | python3 -c "
import sys, json
data = json.load(sys.stdin)
# Expected structure:
# {
#   'sync_status': {'last_sync': '...', 'tables': {...}},
#   'stats': {'listings': 22, 'reservations': 2348, ...},
#   'auth': {'authenticated': true, 'token_expires': '...'}
# }
print(f\"Listings: {data['stats']['listings']}\")
print(f\"Reservations: {data['stats']['reservations']}\")
print(f\"Last sync: {data['sync_status']['last_sync']}\")
"
```

---

## 3. Common Agent Workflows

### Workflow A: Morning Check-In Report

**Purpose:** Generate a daily report of today's arrivals for operations team.

```bash
#!/bin/bash
# morning-checkin-report.sh

echo "=== Morning Check-In Report ==="
echo "Generated: $(date)"
echo ""

# 1. Ensure fresh data
guesty sync reservations

# 2. Get today's check-ins
guesty reservations --today --json | python3 -c "
import sys, json, datetime

data = json.load(sys.stdin)
reservations = data.get('results', [])

if not reservations:
    print('No check-ins scheduled for today.')
    sys.exit(0)

print(f'📋 {len(reservations)} Check-in(s) Today:\n')

for r in reservations:
    code = r.get('confirmationCode', 'N/A')
    guest = r.get('guest', {}).get('fullName', 'N/A')
    listing = r.get('listingNickname', r.get('listingId', 'N/A'))
    checkin = r.get('checkIn', 'N/A')[:10] if r.get('checkIn') else 'N/A'
    checkout = r.get('checkOut', 'N/A')[:10] if r.get('checkOut') else 'N/A'
    nights = r.get('nightsCount', 'N/A')
    guests = r.get('guestsCount', 'N/A')
    phone = r.get('guest', {}).get('phone', 'N/A')
    source = r.get('source', 'N/A')
    
    print(f'🏠 {listing}')
    print(f'   Code: {code} | Source: {source}')
    print(f'   Guest: {guest}')
    print(f'   Phone: {phone}')
    print(f'   Dates: {checkin} → {checkout} ({nights} nights)')
    print(f'   Party: {guests} guests')
    print()
"

# 3. Check for any urgent flags
guesty tasks --status open --json | python3 -c "
import sys, json
data = json.load(sys.stdin)
high_priority = [t for t in data.get('results', []) if t.get('priority') in ['high', 'urgent']]
if high_priority:
    print(f'⚠️  {len(high_priority)} HIGH PRIORITY TASK(S):')
    for t in high_priority:
        print(f'   - {t.get(\"title\")} @ {t.get(\"listingNickname\", \"N/A\")}')
    print()
"
```

### Workflow B: Financial Reconciliation

**Purpose:** Reconcile monthly revenue and identify discrepancies.

```bash
#!/bin/bash
# financial-reconciliation.sh

MONTH="${1:-$(date +%Y-%m)}"  # Default to current month

echo "=== Financial Reconciliation: $MONTH ==="
echo ""

# 1. Sync financial data
guesty sync financials
guesty sync reservations

# 2. Get revenue breakdown
guesty financials --month "$MONTH" --json | python3 -c "
import sys, json

data = json.load(sys.stdin)

print('💰 Revenue by Listing:')
for item in data.get('by_listing', []):
    name = item.get('listingNickname', item.get('listingId', 'Unknown'))
    revenue = item.get('revenue', 0)
    nights = item.get('nights', 0)
    avg_rate = revenue / nights if nights > 0 else 0
    print(f'  {name}: ${revenue:,.2f} ({nights} nights, avg ${avg_rate:.0f}/night)')

print()
print('📅 Revenue by Month:')
for item in data.get('by_month', []):
    month = item.get('month', 'N/A')
    revenue = item.get('revenue', 0)
    print(f'  {month}: ${revenue:,.2f}')

print()
total = sum(i.get('revenue', 0) for i in data.get('by_listing', []))
print(f'Total Revenue: ${total:,.2f}')
"

# 3. Find reservations with balance due
guesty reservations --status confirmed --json | python3 -c "
import sys, json

data = json.load(sys.stdin)
balance_due = []

for r in data.get('results', []):
    money = r.get('money', {})
    balance = money.get('balanceDue', 0)
    if balance and balance > 0:
        balance_due.append({
            'code': r.get('confirmationCode'),
            'guest': r.get('guest', {}).get('fullName'),
            'balance': balance,
            'currency': money.get('currency', 'USD'),
            'checkin': r.get('checkIn', '')[:10] if r.get('checkIn') else 'N/A'
        })

if balance_due:
    print()
    print('⚠️  Reservations with Balance Due:')
    for b in sorted(balance_due, key=lambda x: x['checkin']):
        print(f\"  {b['code']}: {b['guest']} - ${b['balance']} {b['currency']} (check-in: {b['checkin']})\")
else:
    print()
    print('✅ All reservations fully paid')
"
```

### Workflow C: Calendar Bulk Operations

**Purpose:** Block multiple date ranges for maintenance across properties.

```bash
#!/bin/bash
# bulk-calendar-operations.sh

# Define maintenance windows (format: LISTING_NICKNAME:START_DATE:END_DATE:REASON)
MAINTENANCE_SCHEDULE=(
  "Emerald Oasis:2025-04-01:2025-04-05:Pool heater replacement"
  "Coral Reef:2025-04-10:2025-04-12:AC maintenance"
  "Sunset Villa:2025-04-15:2025-04-17:Deep cleaning"
)

echo "=== Calendar Bulk Operations ==="
echo "Mode: DRY-RUN (review before executing)"
echo ""

# Step 1: Dry-run all operations
for entry in "${MAINTENANCE_SCHEDULE[@]}"; do
  IFS=':' read -r LISTING START END REASON <<< "$entry"
  
  echo "📅 Blocking: $LISTING"
  echo "   Dates: $START → $END"
  echo "   Reason: $REASON"
  
  guesty calendar block "$LISTING" "$START" --to "$END" --reason "$REASON" --dry-run
  echo ""
done

# Step 2: Prompt for confirmation (in interactive mode)
read -p "Execute these blocks? (type 'CONFIRM' to proceed): " CONFIRM

if [ "$CONFIRM" = "CONFIRM" ]; then
  echo ""
  echo "🚀 Executing blocks..."
  
  for entry in "${MAINTENANCE_SCHEDULE[@]}"; do
    IFS=':' read -r LISTING START END REASON <<< "$entry"
    
    echo "Blocking $LISTING..."
    guesty calendar block "$LISTING" "$START" --to "$END" --reason "$REASON" --live
  done
  
  echo ""
  echo "✅ All blocks completed"
else
  echo "❌ Cancelled"
fi
```

**Agent-only version** (non-interactive):

```bash
# For agents: Check for existing bookings before blocking
check_before_block() {
  local listing="$1"
  local start="$2"
  local end="$3"
  
  # Get calendar for date range
guesty calendar view "$listing" --start "$start" --end "$end" --json | python3 -c "
import sys, json
data = json.load(sys.stdin)
booked = [d for d in data.get('dates', []) if d.get('status') == 'booked']
if booked:
    print(f'WARNING: {len(booked)} booked dates in range!')
    for b in booked:
        print(f\"  {b['date']}: {b.get('reservationCode', 'Unknown')}\")
    sys.exit(1)
else:
    print('Range is clear')
    sys.exit(0)
"
}

# Usage
check_before_block "Emerald Oasis" "2025-04-01" "2025-04-05" && \
  guesty calendar block "Emerald Oasis" "2025-04-01" --to "2025-04-05" --reason "Maintenance" --live
```

### Workflow D: Guest Lookup and Communication Prep

**Purpose:** Prepare guest communication with full context.

```bash
#!/bin/bash
# guest-communication-prep.sh

CONFIRMATION_CODE="$1"

if [ -z "$CONFIRMATION_CODE" ]; then
  echo "Usage: $0 <confirmation_code>"
  exit 1
fi

echo "=== Guest Communication Prep ==="
echo "Code: $CONFIRMATION_CODE"
echo ""

# 1. Get reservation details
guesty reservation get "$CONFIRMATION_CODE" --json | python3 -c "
import sys, json
data = json.load(sys.stdin)
res = data.get('reservation', {})

if not res:
    print('Reservation not found')
    sys.exit(1)

guest = res.get('guest', {})
money = res.get('money', {})
listing = res.get('listing', {})

print('👤 GUEST INFORMATION')
print(f\"Name: {guest.get('fullName', 'N/A')}\")
print(f\"Email: {guest.get('email', 'N/A')}\")
print(f\"Phone: {guest.get('phone', 'N/A')}\")
print()

print('🏠 RESERVATION DETAILS')
print(f\"Property: {res.get('listingNickname', listing.get('title', 'N/A'))}\")
print(f\"Check-in: {res.get('checkIn', 'N/A')}\")
print(f\"Check-out: {res.get('checkOut', 'N/A')}\")
print(f\"Nights: {res.get('nightsCount', 'N/A')}\")
print(f\"Guests: {res.get('guestsCount', 'N/A')}\")
print(f\"Source: {res.get('source', 'N/A')}\")
print()

print('💰 FINANCIAL SUMMARY')
print(f\"Total: ${money.get('totalPaid', 0)} {money.get('currency', 'USD')}\")
print(f\"Host Payout: ${money.get('hostPayout', 0)}\")
print(f\"Balance Due: ${money.get('balanceDue', 0)}\")
print()

# Check for special requests
notes = res.get('notes', '') or res.get('specialRequests', '')
if notes:
    print('📝 SPECIAL REQUESTS/NOTES')
    print(notes)
    print()

# Save to file for email template
import os
output = {
    'guest_name': guest.get('fullName'),
    'guest_email': guest.get('email'),
    'guest_phone': guest.get('phone'),
    'property': res.get('listingNickname'),
    'checkin': res.get('checkIn'),
    'checkout': res.get('checkOut'),
    'code': res.get('confirmationCode'),
    'special_requests': notes
}

with open(f'/tmp/guest_{res.get(\"confirmationCode\")}.json', 'w') as f:
    json.dump(output, f, indent=2)
print(f'Saved to: /tmp/guest_{res.get(\"confirmationCode\")}.json')
"

# 2. Check for previous stays by this guest
GUEST_EMAIL=$(guesty reservation get "$CONFIRMATION_CODE" --json | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('reservation', {}).get('guest', {}).get('email', ''))
")

if [ -n "$GUEST_EMAIL" ]; then
  echo ""
  echo "📚 PREVIOUS STAYS"
  guesty guests --search "$GUEST_EMAIL" --json | python3 -c "
import sys, json
data = json.load(sys.stdin)
guests = data.get('results', [])
if guests:
    guest = guests[0]
    past = guest.get('reservationHistory', [])
    if past:
        print(f'This guest has {len(past)} previous reservation(s)')
        for p in past[:3]:  # Show last 3
            print(f\"  - {p.get('confirmationCode')}: {p.get('checkIn', '')[:10]} @ {p.get('listingNickname', 'N/A')}\")
    else:
        print('First-time guest')
"
fi

# 3. Generate email template
echo ""
echo "📧 SUGGESTED EMAIL OPENING"
cat << EOF

Subject: Welcome to $(guesty reservation get "$CONFIRMATION_CODE" --json | python3 -c "import sys, json; print(json.load(sys.stdin).get('reservation', {}).get('listingNickname', 'your vacation rental'))")!

Dear $(guesty reservation get "$CONFIRMATION_CODE" --json | python3 -c "import sys, json; print(json.load(sys.stdin).get('reservation', {}).get('guest', {}).get('firstName', 'Guest'))"),

We are excited to welcome you to your upcoming stay...

EOF
```

---

## 4. Error Handling

### API Error Patterns

```bash
# Pattern: Check command success before proceeding
if guesty sync --json > /tmp/sync_result.json 2>&1; then
  echo "✅ Sync successful"
else
  echo "❌ Sync failed"
  cat /tmp/sync_result.json
  exit 1
fi

# Pattern: Handle specific error codes
guesty reservation get "INVALID_CODE" --json 2>&1 | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if 'error' in data:
        error_code = data['error'].get('code', 'UNKNOWN')
        error_msg = data['error'].get('message', 'Unknown error')
        
        if error_code == 'NOT_FOUND':
            print('Reservation not found — may be expired or invalid code')
        elif error_code == 'UNAUTHORIZED':
            print('Authentication failed — run: guesty auth --refresh')
        elif error_code == 'RATE_LIMITED':
            print('Rate limited — waiting before retry...')
        else:
            print(f'Error {error_code}: {error_msg}')
        sys.exit(1)
except json.JSONDecodeError:
    print('Invalid JSON response')
    sys.exit(1)
"
```

### Rate Limit Handling

```bash
# The CLI handles rate limits automatically, but agents should be aware:
# - 15 requests/second
# - 120 requests/minute  
# - 5000 requests/hour
# - 5 new OAuth tokens per 24 hours

# Pattern: Add delays between bulk operations
bulk_operation_with_throttle() {
  local items=("$@")
  local count=0
  
  for item in "${items[@]}"; do
    # Process item
    guesty some-command "$item"
    
    # Throttle: max 10/sec to stay well under limits
    ((count++))
    if ((count % 10 == 0)); then
      sleep 1
    fi
  done
}

# Pattern: Exponential backoff for retries
retry_with_backoff() {
  local max_retries=5
  local delay=1
  
  for i in $(seq 1 $max_retries); do
    if guesty "$@" --json 2>/dev/null; then
      return 0
    fi
    
    echo "Attempt $i failed, retrying in ${delay}s..."
    sleep $delay
    delay=$((delay * 2))
  done
  
  echo "Max retries exceeded"
  return 1
}

# Usage
retry_with_backoff sync reservations
```

### Token Management

```bash
# Check token status
guesty auth status --json | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data.get('authenticated'):
    expires = data.get('token_expires', 'unknown')
    print(f'✅ Token valid until {expires}')
else:
    print('❌ Not authenticated')
    sys.exit(1)
"

# Refresh if needed (rare — CLI auto-refreshes)
guesty auth --refresh

# ⚠️ NEVER do this unless troubleshooting:
# guesty auth --revoke  # Counts against 5/day limit!
```

### Database Lock Handling

```bash
# If database is locked (another process using it):
# Wait and retry
wait_for_db() {
  local max_wait=30
  local waited=0
  
  while [ $waited -lt $max_wait ]; do
    if guesty status --json > /dev/null 2>&1; then
      return 0
    fi
    
    echo "Database locked, waiting..."
    sleep 2
    waited=$((waited + 2))
  done
  
  return 1
}
```

---

## 5. Best Practices

### Always Use --dry-run First

```bash
# ❌ Dangerous — immediately executes
guesty calendar block "Villa" 2025-04-01 --to 2025-04-05 --reason "Test"

# ✅ Safe — preview first
guesty calendar block "Villa" 2025-04-01 --to 2025-04-05 --reason "Test" --dry-run

# Review output, then execute
guesty calendar block "Villa" 2025-04-01 --to 2025-04-05 --reason "Test" --live
```

### Incremental Sync Strategy

```bash
# ❌ Slow — full sync every time
guesty sync

# ✅ Fast — sync only what changed
# Reservations change frequently
guesty sync reservations

# Listings change rarely (weekly is fine)
guesty sync listings

# Tasks change daily
guesty sync tasks

# Full sync only when needed (e.g., weekly)
guesty sync  # Run weekly or after major changes
```

### Validate Before Operations

```bash
# Pattern: Verify listing exists before using it
validate_listing() {
  local nickname="$1"
  
  if guesty listing get "$nickname" --json > /dev/null 2>&1; then
    echo "✅ Listing '$nickname' found"
    return 0
  else
    echo "❌ Listing '$nickname' not found"
    echo "Available listings:"
    guesty listings --json | python3 -c "
import sys, json
data = json.load(sys.stdin)
for l in data.get('results', []):
    print(f\"  - {l.get('nickname', l.get('title'))}\")
"
    return 1
  fi
}

# Usage
validate_listing "Emerald Oasis" && \
  guesty calendar view "Emerald Oasis" --live
```

### Cache Data for Multiple Operations

```bash
# ❌ Inefficient — multiple API calls
guesty reservation get CODE1 --json | python3 -c "..."
guesty reservation get CODE2 --json | python3 -c "..."

# ✅ Efficient — bulk fetch once
guesty export reservations --format json > /tmp/all_reservations.json
python3 << 'PYTHON'
import json
with open('/tmp/all_reservations.json') as f:
    reservations = json.load(f)

# Now process multiple without API calls
code1 = next(r for r in reservations if r.get('confirmationCode') == 'CODE1')
code2 = next(r for r in reservations if r.get('confirmationCode') == 'CODE2')
PYTHON
```

### Idempotent Operations

```bash
# Make operations safe to run multiple times
idempotent_block() {
  local listing="$1"
  local start="$2"
  local end="$3"
  local reason="$4"
  
  # Check if already blocked
  guesty calendar view "$listing" --start "$start" --end "$end" --json | python3 -c "
import sys, json
data = json.load(sys.stdin)
dates = data.get('dates', [])
blocked = all(d.get('status') == 'blocked' for d in dates)
print('ALREADY_BLOCKED' if blocked else 'NEEDS_BLOCK')
" | grep -q "ALREADY_BLOCKED"
  
  if [ $? -eq 0 ]; then
    echo "Dates already blocked, skipping"
    return 0
  fi
  
  # Block if needed
  guesty calendar block "$listing" "$start" --to "$end" --reason "$reason" --live
}

# Usage — safe to run multiple times
idempotent_block "Emerald Oasis" "2025-04-01" "2025-04-05" "Maintenance"
```

---

## 6. Command Patterns

### Pattern: Search → Filter → Act

```bash
# Common pattern: Find items matching criteria, then act on them

# Example: Find all reservations with balance due, send reminder
find_and_notify_balance_due() {
  guesty reservations --status confirmed --json | python3 -c "
import sys, json
data = json.load(sys.stdin)

balance_due = []
for r in data.get('results', []):
    balance = r.get('money', {}).get('balanceDue', 0)
    if balance and balance > 0:
        balance_due.append({
            'code': r['confirmationCode'],
            'email': r.get('guest', {}).get('email'),
            'balance': balance,
            'checkin': r.get('checkIn')
        })

print(json.dumps(balance_due))
" > /tmp/balance_due.json

  # Now process each (could integrate with email system)
  python3 << 'PYTHON'
import json
with open('/tmp/balance_due.json') as f:
    items = json.load(f)

for item in items:
    print(f\"Would notify: {item['email']} owes ${item['balance']} for {item['code']}\")
PYTHON
}
```

### Pattern: Batch Processing

```bash
# Process items in batches with progress tracking
batch_process() {
  local items=("$@")
  local total=${#items[@]}
  local batch_size=10
  local processed=0
  local failed=0
  
  echo "Processing $total items in batches of $batch_size..."
  
  for ((i=0; i<total; i+=batch_size)); do
    batch=("${items[@]:i:batch_size}")
    
    for item in "${batch[@]}"; do
      if process_single_item "$item"; then
        ((processed++))
      else
        ((failed++))
        echo "Failed: $item" >> /tmp/failed_items.log
      fi
    done
    
    echo "Progress: $processed/$total processed"
    sleep 1  # Rate limit protection
  done
  
  echo "Complete: $processed succeeded, $failed failed"
}
```

### Pattern: Conditional Sync

```bash
# Only sync if data is stale
conditional_sync() {
  local max_age_minutes=60
  
  # Check last sync time
  last_sync=$(guesty status --json | python3 -c "
import sys, json, datetime
data = json.load(sys.stdin)
last = data.get('sync_status', {}).get('last_sync')
if last:
    dt = datetime.datetime.fromisoformat(last.replace('Z', '+00:00'))
    age = (datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds() / 60
    print(int(age))
else:
    print(9999)
")
  
  if [ "$last_sync" -gt "$max_age_minutes" ]; then
    echo "Data is $last_sync minutes old, syncing..."
    guesty sync
  else
    echo "Data is fresh ($last_sync minutes old), skipping sync"
  fi
}
```

### Pattern: JSON Pipeline

```bash
# Chain commands with JSON for complex workflows
guesty reservations --today --json | \
  python3 -c "import sys, json; d=json.load(sys.stdin); print(json.dumps([r for r in d.get('results',[]) if r.get('source')=='airbnb']))" | \
  python3 -c "
import sys, json
data = json.load(sys.stdin)
for r in data:
    # Get additional details for each
    import subprocess
    code = r['confirmationCode']
    result = subprocess.run(['guesty', 'reservation', 'get', code, '--json'], 
                          capture_output=True, text=True)
    details = json.loads(result.stdout)
    print(f\"{code}: {details.get('reservation', {}).get('money', {}).get('hostPayout', 0)}\")
"
```

### Pattern: State Preservation

```bash
# Save state between agent sessions
save_agent_state() {
  local state_file="~/.guesty-cli/agent_state.json"
  cat > "$state_file" << EOF
{
  "last_sync": "$(date -Iseconds)",
  "processed_today": ${PROCESSED_COUNT:-0},
  "last_checkin_report": "${LAST_REPORT:-null}",
  "pending_tasks": ${PENDING_TASKS:-[]}
}
EOF
}

load_agent_state() {
  local state_file="~/.guesty-cli/agent_state.json"
  if [ -f "$state_file" ]; then
    python3 -c "import json; print(json.dumps(json.load(open('$state_file'))))"
  else
    echo '{}'
  fi
}
```

---

## 7. Quick Reference Card

### Essential Commands

| Task | Command |
|------|---------|
| Check status | `guesty status --json` |
| Sync all | `guesty sync` |
| Sync one table | `guesty sync reservations` |
| Today's check-ins | `guesty reservations --today --json` |
| Get reservation | `guesty reservation get CODE --json` |
| Search guest | `guesty guests --search "name" --json` |
| Block dates | `guesty calendar block LISTING DATE --to DATE --reason X --live` |
| Create task | `guesty task create --title X --listing X --live` |
| Export data | `guesty export reservations --format json` |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 3 | Empty results |
| 4 | Auth required |
| 5 | Not found |
| 7 | Rate limited |
| 8 | Retryable error |
| 130 | Interrupted (Ctrl+C) |

Full list: `guesty exit-codes`

### File Locations

| File | Path |
|------|------|
| Config | `~/.guesty-cli/config.json` |
| Database | `~/.guesty-cli/guesty.db` |
| Logs | `~/.guesty-cli/logs/` |
| Exports | Current working directory |

---

## 8. Troubleshooting Guide

### "Authentication failed"
```bash
guesty auth --refresh
guesty status
```

### "Listing not found"
```bash
# Check available nicknames
guesty listings --json | python3 -c "import sys,json; [print(l.get('nickname')) for l in json.load(sys.stdin).get('results',[])]"
```

### "Database is locked"
```bash
# Wait a moment and retry, or check for other processes
lsof ~/.guesty-cli/guesty.db
```

### "Rate limit exceeded"
```bash
# Wait and retry with backoff
sleep 5
guesty sync
```

### Empty results after sync
```bash
# Check sync status
guesty status --json | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin).get('sync_status',{}),indent=2))"
```

---

*Last updated: 2026-02-07 | For AI Agent Operations with guesty-cli*
