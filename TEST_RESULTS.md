# Guesty CLI Test Results
## Date: 2026-02-07

## Summary

| Category | Status | Notes |
|----------|--------|-------|
| **Core CRUD** | ⚠️ Partial | Column name mismatches fixed, data extraction needs fix |
| **Sync** | ✅ Working | Incremental sync functional |
| **Calendar** | ✅ Working | Sync operations work |
| **Reporting** | ✅ Working | Views, occupancy functional |
| **Search** | ✅ Working | FTS5 search works |

## Detailed Test Results

### ✅ PASSING TESTS

| # | Command | Status | Output |
|---|---------|--------|--------|
| 1 | `guesty listings` | ✅ PASS | 22 properties displayed |
| 2 | `guesty search "Lori"` | ✅ PASS | 20 results found |
| 3 | `guesty owners` | ⚠️ PARTIAL | 17 owners, names show as "None" |
| 4 | `guesty tasks` | ✅ PASS | No errors (empty table) |
| 5 | `guesty calendar sync-all` | ✅ PASS | Syncs 22 properties |
| 6 | `guesty views --section reservations` | ✅ PASS | 25 reports available |
| 7 | `guesty sync --status` | ✅ PASS | Shows all sync statuses |
| 8 | `guesty occupancy --month 2026-02` | ✅ PASS | Shows report (0% due to no calendar data) |
| 9 | `guesty financials revenue --month 2026-02` | ✅ PASS | No errors (no invoice data) |

### ❌ FAILING/NEEDS FIX TESTS

| # | Command | Issue | Root Cause |
|---|---------|-------|------------|
| 1 | `guesty reservations` | Missing codes, guest names, prices | Data exists in raw_data but not extracted to columns |
| 2 | `guesty webhooks` | Command not registered | Missing registration in help output |

## Critical Issue: Data Extraction

**Problem:** 
- Database has raw_data JSON with all fields
- Columns (confirmation_code, guest_name, total_price) exist but are NULL
- Sync is not extracting data from raw_data to columns properly

**Example:**
```python
# Raw data HAS the info:
raw_data = {"confirmationCode": "HA-8xiMvFV", "guest": {"fullName": "Lori Jewett"}}

# But column is NULL:
SELECT confirmation_code FROM reservations LIMIT 1;  # Returns NULL
```

**Affected Tables:**
- reservations (confirmation_code, guest_name, total_price, etc.)
- owners (full_name showing as NULL)
- guests (likely same issue)
- invoice_items (likely empty or not populated)

## What Works

1. **Database Schema** - All tables created correctly
2. **Sync Infrastructure** - Incremental sync, cursors, status tracking
3. **Calendar Sync** - Can sync calendar days from API
4. **Views API** - Reading Guesty views works
5. **Search** - FTS5 search across all tables
6. **Command Structure** - All 60+ commands registered and callable

## What Needs Fix

1. **Sync Mapping** - The `_map_record_to_db()` function in sync.py is not properly extracting nested JSON fields into table columns
2. **Data Population** - Need to re-sync with fixed mapping

## Recommended Actions

1. **Fix sync.py mapping** - Ensure all nested fields (guest.fullName, money.hostPayout, etc.) are extracted to columns
2. **Re-sync data** - Run `guesty sync` to populate columns correctly
3. **Verify extraction** - Confirm data appears in columns, not just raw_data

## Files Modified in Last Push

- `guesty_cli/commands/reservations.py` - Fixed column names
- `guesty_cli/commands/occupancy.py` - Fixed column names  
- `guesty_cli/commands/financials.py` - Fixed table/column names
- `guesty_cli/commands/tasks.py` - Fixed column names (just now)

## Commit

`95d308e` - Bug fixes pushed to GitHub
