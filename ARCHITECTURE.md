# Guesty CLI Enhanced Architecture Specification

## Executive Summary

This document outlines the architecture for a production-grade Guesty CLI designed to handle Villa Paraiso's 22 listings, 2,348+ reservations, and $1.24M+ in tracked financials. The enhanced CLI introduces enterprise-grade data modeling, efficient syncing, comprehensive financial tracking, multi-calendar management, and real-time webhook processing.

---

## 1. Missing Data Models

### 1.1 New Core Tables

```sql
-- ============================================
-- FINANCIAL DATA MODEL (Comprehensive)
-- ============================================

-- Invoice items (line-item detail from reservations)
CREATE TABLE invoice_items (
    id TEXT PRIMARY KEY,
    reservation_id TEXT NOT NULL,
    line_type TEXT, -- 'income', 'expense', 'tax', 'fee', 'refund'
    line_item_type TEXT, -- 'accommodation', 'cleaning', 'pet_fee', 'resort_fee', etc.
    description TEXT,
    amount REAL,
    currency TEXT DEFAULT 'USD',
    taxable INTEGER DEFAULT 0,
    tax_amount REAL DEFAULT 0,
    created_at TEXT,
    updated_at TEXT,
    raw_data TEXT,
    FOREIGN KEY (reservation_id) REFERENCES reservations(id)
);

-- Payments received
CREATE TABLE payments (
    id TEXT PRIMARY KEY,
    reservation_id TEXT NOT NULL,
    payment_method TEXT, -- 'credit_card', 'airbnb', 'vrbo', 'bookingcom', 'manual'
    gateway TEXT, -- 'stripe', 'braintree', 'paypal'
    amount REAL,
    currency TEXT DEFAULT 'USD',
    status TEXT, -- 'pending', 'completed', 'failed', 'refunded', 'charged_back'
    paid_at TEXT,
    refunded_at TEXT,
    refund_amount REAL DEFAULT 0,
    transaction_id TEXT,
    created_at TEXT,
    raw_data TEXT,
    FOREIGN KEY (reservation_id) REFERENCES reservations(id)
);

-- Refunds and adjustments
CREATE TABLE refunds (
    id TEXT PRIMARY KEY,
    reservation_id TEXT NOT NULL,
    payment_id TEXT,
    amount REAL,
    currency TEXT DEFAULT 'USD',
    reason TEXT,
    processed_at TEXT,
    created_at TEXT,
    raw_data TEXT,
    FOREIGN KEY (reservation_id) REFERENCES reservations(id),
    FOREIGN KEY (payment_id) REFERENCES payments(id)
);

-- Owner statements and payouts
CREATE TABLE owner_payouts (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    statement_period_start TEXT,
    statement_period_end TEXT,
    gross_revenue REAL,
    management_fees REAL,
    cleaning_fees REAL,
    maintenance_costs REAL,
    taxes_collected REAL,
    net_payout REAL,
    currency TEXT DEFAULT 'USD',
    status TEXT, -- 'pending', 'processing', 'paid'
    paid_at TEXT,
    payment_method TEXT,
    created_at TEXT,
    raw_data TEXT,
    FOREIGN KEY (owner_id) REFERENCES owners(id)
);

-- Owner payout line items (reconciliation)
CREATE TABLE owner_payout_items (
    id TEXT PRIMARY KEY,
    payout_id TEXT NOT NULL,
    reservation_id TEXT,
    listing_id TEXT,
    guest_name TEXT,
    check_in TEXT,
    check_out TEXT,
    gross_amount REAL,
    management_fee REAL,
    cleaning_cost REAL,
    net_amount REAL,
    created_at TEXT,
    FOREIGN KEY (payout_id) REFERENCES owner_payouts(id),
    FOREIGN KEY (reservation_id) REFERENCES reservations(id)
);

-- ============================================
-- CALENDAR DATA MODEL (Cached)
-- ============================================

CREATE TABLE calendar_days (
    id TEXT PRIMARY KEY, -- Composite: listing_id|date
    listing_id TEXT NOT NULL,
    date TEXT NOT NULL,
    status TEXT, -- 'available', 'booked', 'blocked'
    reservation_id TEXT,
    price REAL,
    base_price REAL,
    currency TEXT DEFAULT 'USD',
    min_nights INTEGER,
    max_nights INTEGER,
    block_reason TEXT,
    -- Block flags (decoded from blocks object)
    block_manual INTEGER DEFAULT 0,
    block_reservation INTEGER DEFAULT 0,
    block_owner INTEGER DEFAULT 0,
    block_maintenance INTEGER DEFAULT 0,
    synced_at TEXT,
    created_at TEXT,
    updated_at TEXT,
    raw_data TEXT,
    FOREIGN KEY (listing_id) REFERENCES listings(id),
    FOREIGN KEY (reservation_id) REFERENCES reservations(id),
    UNIQUE(listing_id, date)
);

-- Calendar sync state tracking
CREATE TABLE calendar_sync_state (
    listing_id TEXT PRIMARY KEY,
    last_sync_at TEXT,
    sync_range_start TEXT,
    sync_range_end TEXT,
    days_synced INTEGER DEFAULT 0,
    days_changed INTEGER DEFAULT 0,
    sync_version INTEGER DEFAULT 0, -- For optimistic locking
    FOREIGN KEY (listing_id) REFERENCES listings(id)
);

-- ============================================
-- WEBHOOK EVENT QUEUE (Real-time Processing)
-- ============================================

CREATE TABLE webhook_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    webhook_id TEXT,
    event_type TEXT NOT NULL, -- 'reservation.new', 'reservation.updated', etc.
    payload TEXT NOT NULL, -- Full JSON payload
    signature TEXT, -- Webhook signature for verification
    received_at TEXT NOT NULL,
    processed_at TEXT,
    status TEXT DEFAULT 'pending', -- 'pending', 'processing', 'completed', 'failed', 'retrying'
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    processed_by TEXT, -- Worker/process ID
    -- Extracted keys for quick querying
    reservation_id TEXT,
    listing_id TEXT,
    guest_id TEXT
);

-- Webhook event processing log
CREATE TABLE webhook_event_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    action TEXT, -- 'sync_reservation', 'update_calendar', 'send_notification'
    status TEXT,
    details TEXT,
    created_at TEXT,
    FOREIGN KEY (event_id) REFERENCES webhook_events(id)
);

-- ============================================
-- AUDIT & CHANGE TRACKING
-- ============================================

CREATE TABLE change_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    record_id TEXT NOT NULL,
    action TEXT NOT NULL, -- 'insert', 'update', 'delete'
    old_values TEXT, -- JSON
    new_values TEXT, -- JSON
    changed_fields TEXT, -- JSON array of changed field names
    changed_at TEXT NOT NULL,
    changed_by TEXT, -- User ID or 'sync' or 'webhook'
    sync_version INTEGER -- For tracking sync changes
);

-- ============================================
-- SYNC STATE & METRICS
-- ============================================

-- Enhanced sync log (replaces simple sync_log)
CREATE TABLE sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT UNIQUE, -- UUID for this sync run
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT, -- 'running', 'completed', 'failed', 'partial'
    endpoint TEXT NOT NULL,
    sync_type TEXT, -- 'full', 'incremental', 'delta'
    records_fetched INTEGER DEFAULT 0,
    records_inserted INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    records_deleted INTEGER DEFAULT 0,
    records_unchanged INTEGER DEFAULT 0,
    api_calls INTEGER DEFAULT 0,
    api_errors INTEGER DEFAULT 0,
    rate_limit_hits INTEGER DEFAULT 0,
    duration_seconds REAL,
    error_message TEXT,
    cursor TEXT, -- Pagination cursor for resumable syncs
    last_synced_id TEXT -- For ID-based incremental sync
);

-- Sync cursor tracking (for incremental sync)
CREATE TABLE sync_cursors (
    endpoint TEXT PRIMARY KEY,
    cursor_type TEXT, -- 'timestamp', 'id', 'skip'
    cursor_value TEXT,
    last_sync_at TEXT,
    records_total INTEGER,
    records_synced INTEGER
);

-- Entity version tracking (optimistic locking)
CREATE TABLE entity_versions (
    table_name TEXT NOT NULL,
    record_id TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    last_modified TEXT,
    api_etag TEXT, -- For conditional requests
    PRIMARY KEY (table_name, record_id)
);

-- ============================================
-- OPERATIONAL DATA
-- ============================================

-- Automated rules/actions
CREATE TABLE automation_rules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    event_type TEXT NOT NULL, -- 'reservation.new', 'checkin.reminder', etc.
    condition TEXT, -- JSON condition
    actions TEXT, -- JSON array of actions
    is_active INTEGER DEFAULT 1,
    execution_count INTEGER DEFAULT 0,
    last_executed_at TEXT,
    created_at TEXT,
    updated_at TEXT
);

-- Rule execution log
CREATE TABLE automation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id TEXT NOT NULL,
    event_id INTEGER, -- webhook_events.id
    triggered_at TEXT,
    executed_at TEXT,
    status TEXT, -- 'success', 'failed', 'skipped'
    input_data TEXT,
    output_data TEXT,
    error_message TEXT
);

-- Alerts and notifications queue
CREATE TABLE notification_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_type TEXT NOT NULL, -- 'email', 'slack', 'sms'
    recipient TEXT NOT NULL,
    subject TEXT,
    body TEXT,
    template_id TEXT,
    template_data TEXT, -- JSON
    scheduled_at TEXT,
    sent_at TEXT,
    status TEXT DEFAULT 'pending', -- 'pending', 'sent', 'failed', 'cancelled'
    error_message TEXT,
    retry_count INTEGER DEFAULT 0
);

-- Damage claims tracking
CREATE TABLE damage_claims (
    id TEXT PRIMARY KEY,
    reservation_id TEXT NOT NULL,
    listing_id TEXT NOT NULL,
    guest_id TEXT,
    reported_at TEXT,
    reported_by TEXT,
    description TEXT,
    photos TEXT, -- JSON array of URLs
    estimated_cost REAL,
    actual_cost REAL,
    status TEXT DEFAULT 'reported', -- 'reported', 'submitted', 'pending_guest', 'resolved', 'denied'
    deadline_date TEXT, -- 13-day deadline
    submitted_to_platform_at TEXT,
    platform TEXT, -- 'airbnb', 'vrbo', etc.
    platform_case_id TEXT,
    resolution_notes TEXT,
    resolved_at TEXT,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (reservation_id) REFERENCES reservations(id),
    FOREIGN KEY (listing_id) REFERENCES listings(id)
);
```

### 1.2 Enhanced Existing Tables

```sql
-- Enhanced reservations table
ALTER TABLE reservations ADD COLUMN tax_amount REAL;
ALTER TABLE reservations ADD COLUMN cleaning_fee REAL;
ALTER TABLE reservations ADD COLUMN resort_fee REAL;
ALTER TABLE reservations ADD COLUMN pet_fee REAL;
ALTER TABLE reservations ADD COLUMN platform_fee REAL;
ALTER TABLE reservations ADD COLUMN channel_commission REAL;
ALTER TABLE reservations ADD COLUMN processing_fee REAL;
ALTER TABLE reservations ADD COLUMN cancellation_fee REAL;
ALTER TABLE reservations ADD COLUMN is_taxable INTEGER DEFAULT 1;
ALTER TABLE reservations ADD COLUMN tax_jurisdiction TEXT; -- 'FL-Monroe', 'FL-Miami-Dade'
ALTER TABLE reservations ADD COLUMN dr15_period TEXT; -- For tax reporting: '2026-01'
ALTER TABLE reservations ADD COLUMN synced_at TEXT;
ALTER TABLE reservations ADD COLUMN sync_version INTEGER DEFAULT 0;
ALTER TABLE reservations ADD COLUMN api_etag TEXT;

-- Enhanced listings table
ALTER TABLE listings ADD COLUMN owner_id TEXT;
ALTER TABLE listings ADD COLUMN property_type TEXT; -- 'house', 'condo', 'apartment'
ALTER TABLE listings ADD COLUMN room_type TEXT; -- 'entire_home', 'private_room'
ALTER TABLE listings ADD COLUMN check_in_time TEXT DEFAULT '16:00';
ALTER TABLE listings ADD COLUMN check_out_time TEXT DEFAULT '10:00';
ALTER TABLE listings ADD COLUMN cleaning_time_hours INTEGER DEFAULT 4;
ALTER TABLE listings ADD COLUMN wifi_network TEXT;
ALTER TABLE listings ADD COLUMN wifi_password TEXT;
ALTER TABLE listings ADD COLUMN door_code TEXT;
ALTER TABLE listings ADD COLUMN alarm_code TEXT;
ALTER TABLE listings ADD COLUMN emergency_contact TEXT;
ALTER TABLE listings ADD COLUMN cleaning_company_id TEXT;
ALTER TABLE listings ADD COLUMN maintenance_company_id TEXT;
ALTER TABLE listings ADD COLUMN monthly_rent_target REAL;
ALTER TABLE listings ADD COLUMN annual_rent_target REAL;
ALTER TABLE listings ADD COLUMN synced_at TEXT;

-- Enhanced guests table
ALTER TABLE guests ADD COLUMN date_of_birth TEXT;
ALTER TABLE guests ADD COLUMN passport_number TEXT;
ALTER TABLE guests ADD COLUMN passport_country TEXT;
ALTER TABLE guests ADD COLUMN id_verified INTEGER DEFAULT 0;
ALTER TABLE guests ADD COLUMN stripe_customer_id TEXT;
ALTER TABLE guests ADD COLUMN total_bookings INTEGER DEFAULT 0;
ALTER TABLE guests ADD COLUMN total_nights INTEGER DEFAULT 0;
ALTER TABLE guests ADD COLUMN total_spent REAL DEFAULT 0;
ALTER TABLE guests ADD COLUMN first_booking_date TEXT;
ALTER TABLE guests ADD COLUMN last_booking_date TEXT;
ALTER TABLE guests ADD COLUMN guest_segment TEXT; -- 'vip', 'repeat', 'new', 'problematic'
ALTER TABLE guests ADD COLUMN tags TEXT; -- JSON array
ALTER TABLE guests ADD COLUMN notes TEXT;
ALTER TABLE guests ADD COLUMN synced_at TEXT;

-- Enhanced owners table
ALTER TABLE owners ADD COLUMN address TEXT;
ALTER TABLE owners ADD COLUMN tax_id TEXT;
ALTER TABLE owners ADD COLUMN payout_method TEXT; -- 'ach', 'check', 'wire'
ALTER TABLE owners ADD COLUMN payout_details TEXT; -- JSON
ALTER TABLE owners ADD COLUMN management_fee_percent REAL DEFAULT 20;
ALTER TABLE owners ADD COLUMN cleaning_fee_arrangement TEXT; -- 'owner_pays', 'guest_pays', 'split'
ALTER TABLE owners ADD COLUMN is_monthly_statement INTEGER DEFAULT 1;
ALTER TABLE owners ADD COLUMN statement_day INTEGER DEFAULT 1;
ALTER TABLE owners ADD COLUMN listings_owned INTEGER DEFAULT 0;
ALTER TABLE owners ADD COLUMN total_ytd_payout REAL DEFAULT 0;
ALTER TABLE owners ADD COLUMN synced_at TEXT;
```

### 1.3 Indexes for Performance

```sql
-- Performance indexes
CREATE INDEX idx_reservations_check_in ON reservations(check_in);
CREATE INDEX idx_reservations_check_out ON reservations(check_out);
CREATE INDEX idx_reservations_listing_id ON reservations(listing_id);
CREATE INDEX idx_reservations_guest_id ON reservations(guest_id);
CREATE INDEX idx_reservations_status ON reservations(status);
CREATE INDEX idx_reservations_source ON reservations(source);
CREATE INDEX idx_reservations_created_at ON reservations(created_at);
CREATE INDEX idx_reservations_confirmed_at ON reservations(confirmed_at);
CREATE INDEX idx_reservations_dr15_period ON reservations(dr15_period);
CREATE INDEX idx_reservations_synced_at ON reservations(synced_at);

CREATE INDEX idx_invoice_items_reservation_id ON invoice_items(reservation_id);
CREATE INDEX idx_invoice_items_line_type ON invoice_items(line_type);
CREATE INDEX idx_invoice_items_created_at ON invoice_items(created_at);

CREATE INDEX idx_payments_reservation_id ON payments(reservation_id);
CREATE INDEX idx_payments_status ON payments(status);
CREATE INDEX idx_payments_paid_at ON payments(paid_at);

CREATE INDEX idx_calendar_days_listing_date ON calendar_days(listing_id, date);
CREATE INDEX idx_calendar_days_status ON calendar_days(status);
CREATE INDEX idx_calendar_days_reservation_id ON calendar_days(reservation_id);
CREATE INDEX idx_calendar_days_synced_at ON calendar_days(synced_at);

CREATE INDEX idx_webhook_events_status ON webhook_events(status);
CREATE INDEX idx_webhook_events_event_type ON webhook_events(event_type);
CREATE INDEX idx_webhook_events_received_at ON webhook_events(received_at);
CREATE INDEX idx_webhook_events_reservation_id ON webhook_events(reservation_id);
CREATE INDEX idx_webhook_events_listing_id ON webhook_events(listing_id);

CREATE INDEX idx_change_log_table_record ON change_log(table_name, record_id);
CREATE INDEX idx_change_log_changed_at ON change_log(changed_at);

CREATE INDEX idx_damage_claims_status ON damage_claims(status);
CREATE INDEX idx_damage_claims_deadline ON damage_claims(deadline_date);
CREATE INDEX idx_damage_claims_reservation_id ON damage_claims(reservation_id);

-- Composite indexes
CREATE INDEX idx_reservations_listing_dates ON reservations(listing_id, check_in, check_out);
CREATE INDEX idx_owner_payouts_owner_period ON owner_payouts(owner_id, statement_period_start);
```

---

## 2. Sync Strategy

### 2.1 Sync Types

| Type | Use Case | Frequency | Records | API Calls |
|------|----------|-----------|---------|-----------|
| **Full Sync** | Initial setup, data corruption recovery | Weekly/Monthly | All | High |
| **Incremental Sync** | Daily operations | Every 15 min | Changed | Medium |
| **Delta Sync** | Real-time webhook catchup | On webhook | Specific | Low |
| **Selective Sync** | Specific entities | On demand | Filtered | Low |

### 2.2 Incremental Sync Algorithm

```typescript
// Core incremental sync logic
interface SyncConfig {
  endpoint: string;
  cursorType: 'timestamp' | 'id' | 'skip';
  timestampField: string; // 'updatedAt', 'lastUpdatedAt', 'createdAt'
  idField: string; // '_id'
  batchSize: number; // 100 (Guesty max)
}

class IncrementalSyncEngine {
  async sync(config: SyncConfig): Promise<SyncResult> {
    const cursor = await this.getCursor(config.endpoint);
    const runId = generateUUID();
    
    await this.startSyncRun(runId, config.endpoint, 'incremental');
    
    try {
      let hasMore = true;
      let totalFetched = 0;
      let totalInserted = 0;
      let totalUpdated = 0;
      let totalUnchanged = 0;
      let apiCalls = 0;
      
      while (hasMore) {
        // Build query based on cursor type
        const params = this.buildQueryParams(config, cursor);
        
        // Fetch batch with rate limiting
        const response = await this.fetchWithRateLimit(
          config.endpoint,
          params
        );
        apiCalls++;
        
        const records = response.results || response.data || [];
        
        if (records.length === 0) {
          hasMore = false;
          break;
        }
        
        // Process batch with conflict resolution
        const result = await this.processBatch(records, config);
        totalInserted += result.inserted;
        totalUpdated += result.updated;
        totalUnchanged += result.unchanged;
        totalFetched += records.length;
        
        // Update cursor for next iteration
        cursor.value = this.extractNextCursor(records, config);
        await this.updateCursor(config.endpoint, cursor);
        
        // Check if we've reached the end
        hasMore = records.length === config.batchSize;
        
        // Checkpoint: save progress every 500 records
        if (totalFetched % 500 === 0) {
          await this.checkpointSyncRun(runId, cursor.value, totalFetched);
        }
      }
      
      await this.completeSyncRun(runId, 'completed', {
        recordsFetched: totalFetched,
        recordsInserted: totalInserted,
        recordsUpdated: totalUpdated,
        recordsUnchanged: totalUnchanged,
        apiCalls
      });
      
      return {
        success: true,
        runId,
        recordsFetched: totalFetched,
        recordsInserted: totalInserted,
        recordsUpdated: totalUpdated,
        apiCalls
      };
      
    } catch (error) {
      await this.completeSyncRun(runId, 'failed', { error: error.message });
      throw error;
    }
  }
  
  private buildQueryParams(config: SyncConfig, cursor: Cursor): QueryParams {
    const params: QueryParams = {
      limit: config.batchSize,
      sort: config.timestampField,
      fields: this.getFieldsForEndpoint(config.endpoint)
    };
    
    switch (config.cursorType) {
      case 'timestamp':
        if (cursor.value) {
          // Use $gt to get records after our cursor
          params.filters = [{
            field: config.timestampField,
            operator: '$gt',
            value: cursor.value
          }];
        }
        break;
        
      case 'id':
        if (cursor.value) {
          params.filters = [{
            field: config.idField,
            operator: '$gt',
            value: cursor.value
          }];
        }
        break;
        
      case 'skip':
        params.skip = parseInt(cursor.value || '0');
        break;
    }
    
    return params;
  }
  
  private async processBatch(
    records: any[],
    config: SyncConfig
  ): Promise<BatchResult> {
    const result = { inserted: 0, updated: 0, unchanged: 0 };
    
    for (const record of records) {
      const existing = await this.db.get(
        `SELECT * FROM ${config.endpoint} WHERE id = ?`,
        [record._id]
      );
      
      if (!existing) {
        // Insert new record
        await this.insertRecord(record, config);
        result.inserted++;
      } else {
        // Check if changed using version or timestamp
        const hasChanged = this.hasRecordChanged(record, existing, config);
        
        if (hasChanged) {
          await this.updateRecord(record, existing, config);
          result.updated++;
        } else {
          result.unchanged++;
        }
      }
    }
    
    return result;
  }
  
  private async insertRecord(record: any, config: SyncConfig): Promise<void> {
    const mapped = this.mapRecordToDb(record, config);
    
    await this.db.transaction(async (trx) => {
      // Insert main record
      await trx.execute(
        `INSERT INTO ${config.endpoint} (...) VALUES (...)`,
        [...]
      );
      
      // Track entity version
      await trx.execute(
        `INSERT INTO entity_versions (table_name, record_id, version, last_modified)
         VALUES (?, ?, 1, ?)`,
        [config.endpoint, record._id, new Date().toISOString()]
      );
      
      // Log change
      await trx.execute(
        `INSERT INTO change_log (table_name, record_id, action, new_values, changed_at, changed_by)
         VALUES (?, ?, 'insert', ?, ?, 'sync')`,
        [config.endpoint, record._id, JSON.stringify(mapped), new Date().toISOString()]
      );
    });
  }
}
```

### 2.3 Rate Limiting & Pagination Strategy

```typescript
class RateLimitManager {
  private limits = {
    second: { max: 15, remaining: 15, resetAt: 0 },
    minute: { max: 120, remaining: 120, resetAt: 0 },
    hour: { max: 5000, remaining: 5000, resetAt: 0 }
  };
  
  private tokenBucket = {
    tokens: 15,
    lastRefill: Date.now(),
    refillRate: 15 // per second
  };
  
  async acquirePermit(priority: 'high' | 'normal' | 'low' = 'normal'): Promise<void> {
    const now = Date.now();
    
    // Refill token bucket
    const timePassed = (now - this.tokenBucket.lastRefill) / 1000;
    this.tokenBucket.tokens = Math.min(
      15,
      this.tokenBucket.tokens + timePassed * this.tokenBucket.refillRate
    );
    this.tokenBucket.lastRefill = now;
    
    // Check hard limits from headers
    if (this.limits.hour.remaining < 100) {
      const waitMs = this.limits.hour.resetAt - now;
      if (waitMs > 0) {
        console.warn(`Hourly rate limit nearly exhausted. Waiting ${waitMs}ms`);
        await sleep(waitMs);
      }
    }
    
    if (this.limits.minute.remaining < 10) {
      const waitMs = this.limits.minute.resetAt - now;
      if (waitMs > 0) {
        await sleep(Math.min(waitMs, 60000)); // Max 60s wait
      }
    }
    
    // Token bucket check
    if (this.tokenBucket.tokens < 1) {
      const waitMs = (1 - this.tokenBucket.tokens) * (1000 / this.tokenBucket.refillRate);
      await sleep(waitMs);
      return this.acquirePermit(priority);
    }
    
    this.tokenBucket.tokens--;
  }
  
  updateFromHeaders(headers: RateLimitHeaders): void {
    this.limits.second.remaining = parseInt(headers['x-ratelimit-remaining-second'] || '15');
    this.limits.minute.remaining = parseInt(headers['x-ratelimit-remaining-minute'] || '120');
    this.limits.hour.remaining = parseInt(headers['x-ratelimit-remaining-hour'] || '5000');
  }
  
  async withRetry<T>(
    operation: () => Promise<T>,
    options: RetryOptions = {}
  ): Promise<T> {
    const maxRetries = options.maxRetries || 3;
    const baseDelay = options.baseDelay || 1000;
    
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        await this.acquirePermit(options.priority);
        const result = await operation();
        return result;
      } catch (error) {
        if (error.status === 429) {
          const retryAfter = parseInt(error.headers['retry-after'] || '60');
          console.warn(`Rate limited. Retrying after ${retryAfter}s`);
          await sleep(retryAfter * 1000);
          continue;
        }
        
        if (attempt === maxRetries) throw error;
        
        const delay = baseDelay * Math.pow(2, attempt);
        await sleep(delay);
      }
    }
    
    throw new Error('Max retries exceeded');
  }
}
```

### 2.4 Pagination Edge Cases

```typescript
class PaginationHandler {
  // Guesty uses skip-based pagination with max 100 per request
  private readonly MAX_LIMIT = 100;
  
  async *paginate(
    endpoint: string,
    params: QueryParams
  ): AsyncGenerator<any[], void, unknown> {
    let skip = 0;
    let hasMore = true;
    let totalFetched = 0;
    
    // Edge Case 1: Records being added during sync
    // Solution: Sort by _id ascending, so new records go to the end
    params.sort = params.sort || '_id';
    
    while (hasMore) {
      const pageParams = { ...params, limit: this.MAX_LIMIT, skip };
      
      // Edge Case 2: API returns inconsistent count
      // Solution: Fetch one extra record to detect more pages
      pageParams.limit = this.MAX_LIMIT + 1;
      
      const response = await this.client.get(endpoint, pageParams);
      let records = response.results || [];
      
      // Check if there are more records
      hasMore = records.length > this.MAX_LIMIT;
      
      // Trim the extra record we fetched
      if (hasMore) {
        records = records.slice(0, this.MAX_LIMIT);
      }
      
      // Edge Case 3: Duplicate records from API
      // Solution: Track IDs and deduplicate
      const uniqueRecords = this.deduplicateById(records);
      
      // Edge Case 4: Records changing during pagination
      // Solution: Detect version changes and retry page
      const stableRecords = await this.ensureStability(uniqueRecords, endpoint);
      
      yield stableRecords;
      
      totalFetched += stableRecords.length;
      skip += this.MAX_LIMIT;
      
      // Edge Case 5: Very large result sets
      // Solution: Checkpoint every 1000 records
      if (totalFetched % 1000 === 0) {
        await this.checkpoint({ endpoint, skip, totalFetched });
      }
    }
  }
  
  private deduplicateById(records: any[]): any[] {
    const seen = new Set<string>();
    return records.filter(r => {
      if (seen.has(r._id)) return false;
      seen.add(r._id);
      return true;
    });
  }
  
  private async ensureStability(
    records: any[],
    endpoint: string
  ): Promise<any[]> {
    // For critical endpoints, verify record stability
    // by checking if any record was modified since we fetched it
    const timestamps = records.map(r => r.updatedAt || r.createdAt);
    const maxTimestamp = Math.max(...timestamps.map(t => new Date(t).getTime()));
    
    // If records are very recent, they might still be changing
    const age = Date.now() - maxTimestamp;
    if (age < 5000) { // Less than 5 seconds old
      await sleep(1000); // Brief pause for stability
    }
    
    return records;
  }
}
```

---

## 3. Financial Data Deep Dive

### 3.1 Money Object Structure

The Guesty `money` object contains nested financial data that must be extracted and normalized:

```typescript
interface GuestyMoney {
  // Core amounts
  fareAccommodation: number;      // Base nightly rate total
  fareCleaning: number;           // Cleaning fee
  farePetFee?: number;           // Pet fee if applicable
  fareResortFee?: number;        // Resort fee
  fareExtras?: Array<{           // Additional fees
    name: string;
    amount: number;
  }>;
  
  // Taxes
  vat: number;                    // Tax amount (varies by jurisdiction)
  vatFormula: string;            // "FL: 12.5% of (accommodation + cleaning)"
  
  // Platform/Channel fees
  airbnb: {
    colisting: number;           // Co-host fee
    hostServiceFee: number;      // Airbnb service fee (3%)
    hostPayout: number;          // Net to host
  };
  vrbo: {
    hostServiceFee: number;      // VRBO service fee (5%)
    hostPayout: number;
  };
  bookingcom: {
    commission: number;          // Booking.com commission (15%)
    hostPayout: number;
  };
  
  // Aggregates
  subTotal: number;              // Before taxes and fees
  totalTaxes: number;            // Sum of all taxes
  totalFees: number;             // Sum of all fees
  totalPaid: number;             // Amount guest has paid
  balanceDue: number;            // Amount still owed
  hostPayout: number;            // Final payout to host
  currency: string;              // 'USD'
  
  // Invoice breakdown
  invoiceItems: Array<{
    _id: string;
    lineItemType: string;        // 'accommodation', 'cleaning_fee', 'tax', etc.
    description: string;
    amount: number;
    taxable: boolean;
    taxAmount: number;
  }>;
  
  // Payment records
  payments: Array<{
    _id: string;
    paymentMethod: string;       // 'credit_card', 'airbnb_payout'
    gateway: string;             // 'stripe', 'braintree'
    amount: number;
    status: 'pending' | 'completed' | 'failed' | 'refunded';
    paidAt: string;
    refundedAt?: string;
    refundAmount?: number;
  }>;
}
```

### 3.2 Financial Data Extraction Strategy

```typescript
class FinancialDataExtractor {
  async extractFinancials(reservationId: string): Promise<FinancialData> {
    // Fetch full reservation with money fields
    const reservation = await this.client.get(
      `/v1/reservations/${reservationId}`,
      {
        fields: [
          'money.fareAccommodation',
          'money.fareCleaning',
          'money.farePetFee',
          'money.fareResortFee',
          'money.fareExtras',
          'money.vat',
          'money.vatFormula',
          'money.airbnb',
          'money.vrbo',
          'money.bookingcom',
          'money.subTotal',
          'money.totalTaxes',
          'money.totalFees',
          'money.totalPaid',
          'money.balanceDue',
          'money.hostPayout',
          'money.currency',
          'money.invoiceItems',
          'money.payments'
        ].join(' ')
      }
    );
    
    const money = reservation.money || {};
    
    // Extract and normalize invoice items
    const invoiceItems = this.extractInvoiceItems(reservationId, money);
    
    // Extract payments
    const payments = this.extractPayments(reservationId, money);
    
    // Calculate derived metrics
    const metrics = this.calculateMetrics(money, reservation);
    
    return {
      invoiceItems,
      payments,
      metrics,
      raw: money
    };
  }
  
  private extractInvoiceItems(
    reservationId: string,
    money: GuestyMoney
  ): InvoiceItem[] {
    const items: InvoiceItem[] = [];
    
    // Accommodation
    if (money.fareAccommodation) {
      items.push({
        id: `${reservationId}|accommodation`,
        reservation_id: reservationId,
        line_type: 'income',
        line_item_type: 'accommodation',
        description: 'Accommodation',
        amount: money.fareAccommodation,
        currency: money.currency || 'USD',
        taxable: true,
        tax_amount: this.calculateTaxOnAmount(money.fareAccommodation, money.vatFormula)
      });
    }
    
    // Cleaning fee
    if (money.fareCleaning) {
      items.push({
        id: `${reservationId}|cleaning`,
        reservation_id: reservationId,
        line_type: 'income',
        line_item_type: 'cleaning_fee',
        description: 'Cleaning Fee',
        amount: money.fareCleaning,
        currency: money.currency || 'USD',
        taxable: true,
        tax_amount: this.calculateTaxOnAmount(money.fareCleaning, money.vatFormula)
      });
    }
    
    // Pet fee
    if (money.farePetFee) {
      items.push({
        id: `${reservationId}|pet`,
        reservation_id: reservationId,
        line_type: 'income',
        line_item_type: 'pet_fee',
        description: 'Pet Fee',
        amount: money.farePetFee,
        currency: money.currency || 'USD',
        taxable: false,
        tax_amount: 0
      });
    }
    
    // Resort fee
    if (money.fareResortFee) {
      items.push({
        id: `${reservationId}|resort`,
        reservation_id: reservationId,
        line_type: 'income',
        line_item_type: 'resort_fee',
        description: 'Resort Fee',
        amount: money.fareResortFee,
        currency: money.currency || 'USD',
        taxable: false,
        tax_amount: 0
      });
    }
    
    // Extras
    if (money.fareExtras) {
      for (const extra of money.fareExtras) {
        items.push({
          id: `${reservationId}|extra|${extra.name}`,
          reservation_id: reservationId,
          line_type: 'income',
          line_item_type: 'extra',
          description: extra.name,
          amount: extra.amount,
          currency: money.currency || 'USD',
          taxable: false,
          tax_amount: 0
        });
      }
    }
    
    // Taxes (as separate line item)
    if (money.vat) {
      items.push({
        id: `${reservationId}|tax`,
        reservation_id: reservationId,
        line_type: 'tax',
        line_item_type: 'sales_tax',
        description: `Sales Tax (${money.vatFormula || 'varies'})`,
        amount: money.vat,
        currency: money.currency || 'USD',
        taxable: false,
        tax_amount: 0
      });
    }
    
    // Platform fees (expense)
    const platformFees = this.extractPlatformFees(reservationId, money);
    items.push(...platformFees);
    
    return items;
  }
  
  private extractPlatformFees(
    reservationId: string,
    money: GuestyMoney
  ): InvoiceItem[] {
    const items: InvoiceItem[] = [];
    const currency = money.currency || 'USD';
    
    // Airbnb fees
    if (money.airbnb?.hostServiceFee) {
      items.push({
        id: `${reservationId}|fee|airbnb_service`,
        reservation_id: reservationId,
        line_type: 'expense',
        line_item_type: 'platform_fee',
        description: 'Airbnb Service Fee',
        amount: -money.airbnb.hostServiceFee, // Negative for expense
        currency,
        taxable: false,
        tax_amount: 0
      });
    }
    
    // VRBO fees
    if (money.vrbo?.hostServiceFee) {
      items.push({
        id: `${reservationId}|fee|vrbo_service`,
        reservation_id: reservationId,
        line_type: 'expense',
        line_item_type: 'platform_fee',
        description: 'VRBO Service Fee',
        amount: -money.vrbo.hostServiceFee,
        currency,
        taxable: false,
        tax_amount: 0
      });
    }
    
    // Booking.com commission
    if (money.bookingcom?.commission) {
      items.push({
        id: `${reservationId}|fee|bookingcom_commission`,
        reservation_id: reservationId,
        line_type: 'expense',
        line_item_type: 'platform_fee',
        description: 'Booking.com Commission',
        amount: -money.bookingcom.commission,
        currency,
        taxable: false,
        tax_amount: 0
      });
    }
    
    return items;
  }
  
  private extractPayments(
    reservationId: string,
    money: GuestyMoney
  ): Payment[] {
    if (!money.payments || !Array.isArray(money.payments)) {
      return [];
    }
    
    return money.payments.map(p => ({
      id: p._id || `${reservationId}|${p.paidAt}`,
      reservation_id: reservationId,
      payment_method: this.normalizePaymentMethod(p.paymentMethod),
      gateway: p.gateway,
      amount: p.amount,
      currency: money.currency || 'USD',
      status: p.status,
      paid_at: p.paidAt,
      refunded_at: p.refundedAt,
      refund_amount: p.refundAmount || 0,
      transaction_id: p.transactionId,
      created_at: p.paidAt
    }));
  }
  
  private normalizePaymentMethod(method: string): string {
    const mapping: Record<string, string> = {
      'cc': 'credit_card',
      'creditCard': 'credit_card',
      'airbnb': 'airbnb_payout',
      'homeaway': 'vrbo_payout',
      'bookingcom': 'bookingcom_payout',
      'manual': 'manual'
    };
    return mapping[method] || method || 'unknown';
  }
  
  private calculateMetrics(
    money: GuestyMoney,
    reservation: any
  ): FinancialMetrics {
    return {
      grossRevenue: money.subTotal || 0,
      totalTaxes: money.vat || 0,
      totalFees: money.totalFees || 0,
      platformFees: this.sumPlatformFees(money),
      netRevenue: money.hostPayout || 0,
      collectionRate: money.totalPaid && money.hostPayout 
        ? (money.totalPaid / (money.hostPayout + (money.balanceDue || 0))) * 100 
        : 0,
      avgNightlyRate: reservation.nightsCount && money.fareAccommodation
        ? money.fareAccommodation / reservation.nightsCount
        : 0
    };
  }
}
```

### 3.3 Tax Reporting (DR-15 Florida)

```typescript
class TaxReporter {
  async generateDR15(period: string): Promise<DR15Report> {
    // period format: '2026-01' for January 2026
    
    const reservations = await this.db.query(`
      SELECT 
        r.*,
        l.city,
        l.state,
        SUM(ii.amount) as taxable_amount,
        SUM(ii.tax_amount) as tax_collected
      FROM reservations r
      JOIN listings l ON r.listing_id = l.id
      LEFT JOIN invoice_items ii ON r.id = ii.reservation_id
        AND ii.taxable = 1
        AND ii.line_type = 'income'
      WHERE r.dr15_period = ?
        AND r.status = 'confirmed'
      GROUP BY r.id
    `, [period]);
    
    // Group by tax jurisdiction
    const byJurisdiction = groupBy(reservations, 'tax_jurisdiction');
    
    return {
      period,
      generatedAt: new Date().toISOString(),
      jurisdictions: Object.entries(byJurisdiction).map(([jurisdiction, rows]) => ({
        jurisdiction,
        grossSales: sum(rows, 'subtotal'),
        taxableSales: sum(rows, 'taxable_amount'),
        taxCollected: sum(rows, 'tax_collected'),
        exemptSales: sum(rows, 'subtotal') - sum(rows, 'taxable_amount'),
        // Florida Monroe County: 7.5% state + 1% county = 8.5%
        // Florida Miami-Dade: 6% state + 1% county + 1% local = 8%
        taxRate: this.getTaxRate(jurisdiction),
        reservationCount: rows.length
      })),
      totals: {
        grossSales: sum(reservations, 'subtotal'),
        taxableSales: sum(reservations, 'taxable_amount'),
        taxCollected: sum(reservations, 'tax_collected'),
        reservationCount: reservations.length
      }
    };
  }
  
  private getTaxRate(jurisdiction: string): number {
    const rates: Record<string, number> = {
      'FL-Monroe': 0.125,    // 12.5% (Marathon area)
      'FL-Miami-Dade': 0.13, // 13% (Miami area)
      'FL-Broward': 0.12,    // 12% (Fort Lauderdale)
      'unknown': 0.125       // Default
    };
    return rates[jurisdiction] || 0.125;
  }
}
```

---

## 4. Calendar Strategy

### 4.1 Multi-Calendar Sync Architecture

```typescript
interface CalendarSyncConfig {
  listings: string[];           // Listing IDs to sync
  dateRange: {
    start: string;              // YYYY-MM-DD
    end: string;
  };
  syncMode: 'full' | 'delta';   // Full refresh or changes only
  priority: 'high' | 'normal';  // For rate limiting
}

class CalendarSyncManager {
  private readonly CONCURRENT_REQUESTS = 5; // Max parallel API calls
  private readonly DAYS_PER_REQUEST = 365;  // Max range per call
  
  async syncCalendars(config: CalendarSyncConfig): Promise<CalendarSyncResult> {
    const startTime = Date.now();
    const results: ListingCalendarResult[] = [];
    
    // Split listings into batches for concurrent processing
    const batches = chunk(config.listings, this.CONCURRENT_REQUESTS);
    
    for (const batch of batches) {
      const batchResults = await Promise.all(
        batch.map(listingId => 
          this.syncListingCalendar(listingId, config)
        )
      );
      results.push(...batchResults);
    }
    
    return {
      duration: Date.now() - startTime,
      listingsProcessed: results.length,
      totalDaysSynced: sum(results, 'daysSynced'),
      totalDaysChanged: sum(results, 'daysChanged'),
      errors: results.filter(r => r.error).map(r => ({
        listingId: r.listingId,
        error: r.error
      }))
    };
  }
  
  private async syncListingCalendar(
    listingId: string,
    config: CalendarSyncConfig
  ): Promise<ListingCalendarResult> {
    try {
      // Get current sync state
      const syncState = await this.db.get(
        'SELECT * FROM calendar_sync_state WHERE listing_id = ?',
        [listingId]
      );
      
      // Determine date range
      const dateRange = this.calculateDateRange(config, syncState);
      
      // Fetch calendar from API
      const calendar = await this.fetchCalendar(listingId, dateRange);
      
      // Compare with local data
      const changes = await this.detectChanges(listingId, calendar);
      
      if (changes.hasChanges || config.syncMode === 'full') {
        // Apply changes
        await this.applyCalendarChanges(listingId, changes);
        
        // Update sync state
        await this.updateSyncState(listingId, {
          lastSyncAt: new Date().toISOString(),
          syncRangeStart: dateRange.start,
          syncRangeEnd: dateRange.end,
          daysSynced: calendar.length,
          daysChanged: changes.changedDays.length,
          syncVersion: (syncState?.syncVersion || 0) + 1
        });
      }
      
      return {
        listingId,
        daysSynced: calendar.length,
        daysChanged: changes.changedDays.length,
        error: null
      };
      
    } catch (error) {
      return {
        listingId,
        daysSynced: 0,
        daysChanged: 0,
        error: error.message
      };
    }
  }
  
  private async fetchCalendar(
    listingId: string,
    dateRange: DateRange
  ): Promise<CalendarDay[]> {
    // Split large date ranges into chunks
    const chunks = this.splitDateRange(dateRange, this.DAYS_PER_REQUEST);
    const allDays: CalendarDay[] = [];
    
    for (const chunk of chunks) {
      const response = await this.rateLimitedRequest(() =>
        this.client.get(`/v1/listings/${listingId}/calendar`, {
          from: chunk.start,
          to: chunk.end
        })
      );
      
      allDays.push(...(response || []));
    }
    
    return allDays;
  }
  
  private async detectChanges(
    listingId: string,
    remoteDays: CalendarDay[]
  ): Promise<CalendarChanges> {
    const changedDays: CalendarDayChange[] = [];
    const unchangedDays: string[] = [];
    
    // Get local calendar days for comparison
    const localDays = await this.db.query(
      'SELECT * FROM calendar_days WHERE listing_id = ?',
      [listingId]
    );
    
    const localDayMap = new Map(localDays.map(d => [d.date, d]));
    
    for (const remoteDay of remoteDays) {
      const localDay = localDayMap.get(remoteDay.date);
      
      if (!localDay) {
        // New day
        changedDays.push({
          date: remoteDay.date,
          type: 'new',
          remote: remoteDay,
          local: null
        });
      } else if (this.hasDayChanged(remoteDay, localDay)) {
        // Changed day
        changedDays.push({
          date: remoteDay.date,
          type: 'changed',
          remote: remoteDay,
          local: localDay
        });
      } else {
        unchangedDays.push(remoteDay.date);
      }
    }
    
    return {
      hasChanges: changedDays.length > 0,
      changedDays,
      unchangedDays
    };
  }
  
  private hasDayChanged(remote: CalendarDay, local: any): boolean {
    // Compare relevant fields
    return (
      remote.status !== local.status ||
      remote.price !== local.price ||
      remote.reservationId !== local.reservation_id ||
      JSON.stringify(remote.blocks) !== local.raw_data // Quick hash check
    );
  }
  
  private async applyCalendarChanges(
    listingId: string,
    changes: CalendarChanges
  ): Promise<void> {
    await this.db.transaction(async (trx) => {
      for (const change of changes.changedDays) {
        const day = change.remote;
        const compositeId = `${listingId}|${day.date}`;
        
        // Decode blocks object into boolean flags
        const blockFlags = this.decodeBlocks(day.blocks || {});
        
        await trx.execute(`
          INSERT OR REPLACE INTO calendar_days (
            id, listing_id, date, status, reservation_id,
            price, base_price, currency, min_nights, max_nights,
            block_reason, block_manual, block_reservation, block_owner,
            block_maintenance, synced_at, raw_data
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        `, [
          compositeId,
          listingId,
          day.date,
          day.status,
          day.reservationId,
          day.price,
          day.basePrice,
          day.currency,
          day.minNights,
          day.maxNights,
          blockFlags.reason,
          blockFlags.manual,
          blockFlags.reservation,
          blockFlags.owner,
          blockFlags.maintenance,
          new Date().toISOString(),
          JSON.stringify(day)
        ]);
      }
    });
  }
  
  private decodeBlocks(blocks: Record<string, boolean>): BlockFlags {
    // Decode Guesty block flags
    return {
      manual: blocks.m ? 1 : 0,        // Manual block
      reservation: blocks.r ? 1 : 0,   // Reservation
      owner: blocks.o ? 1 : 0,         // Owner block
      maintenance: blocks.bd ? 1 : 0,  // Blocked dates
      reason: this.getBlockReason(blocks)
    };
  }
  
  private getBlockReason(blocks: Record<string, boolean>): string | null {
    if (blocks.bd) return 'blocked_dates';
    if (blocks.o) return 'owner';
    if (blocks.m) return 'manual';
    if (blocks.sr) return 'seasonal_restriction';
    if (blocks.abl) return 'advance_booking_limit';
    return null;
  }
}
```

### 4.2 Optimized 18-Property Sync

For Villa Paraiso's 22 listings (targeting 18 active properties):

```typescript
class VillaParaisoCalendarSync {
  private readonly ACTIVE_LISTINGS = [
    'emerald-oasis',
    'coral-cottage',
    'sunset-villa',
    // ... 18 properties
  ];
  
  private readonly SYNC_WINDOWS = {
    urgent: 30,    // Next 30 days - sync every 5 minutes
    near: 90,      // 31-90 days - sync every hour
    future: 365    // 91-365 days - sync daily
  };
  
  async runPrioritizedSync(): Promise<void> {
    const now = new Date();
    
    // Tier 1: Urgent window (next 30 days)
    await this.syncWindow('urgent', {
      start: this.formatDate(now),
      end: this.formatDate(addDays(now, 30)),
      priority: 'high'
    });
    
    // Tier 2: Near window (31-90 days)
    await this.syncWindow('near', {
      start: this.formatDate(addDays(now, 31)),
      end: this.formatDate(addDays(now, 90)),
      priority: 'normal'
    });
    
    // Tier 3: Future window (91-365 days)
    await this.syncWindow('future', {
      start: this.formatDate(addDays(now, 91)),
      end: this.formatDate(addDays(now, 365)),
      priority: 'normal'
    });
  }
  
  async syncWindow(
    tier: string,
    config: WindowConfig
  ): Promise<void> {
    const manager = new CalendarSyncManager(this.client, this.db);
    
    const result = await manager.syncCalendars({
      listings: this.ACTIVE_LISTINGS,
      dateRange: { start: config.start, end: config.end },
      syncMode: 'delta',
      priority: config.priority
    });
    
    // Log results
    await this.logSyncResult(tier, result);
    
    // Alert on errors
    if (result.errors.length > 0) {
      await this.alertOnErrors(result.errors);
    }
  }
  
  // Calculate optimal sync frequency based on booking velocity
  async calculateSyncFrequency(listingId: string): Promise<number> {
    // Get booking velocity for this listing
    const stats = await this.db.get(`
      SELECT 
        COUNT(*) as booking_count,
        AVG(julianday('now') - julianday(created_at)) as avg_booking_age
      FROM reservations
      WHERE listing_id = ?
        AND status = 'confirmed'
        AND created_at >= datetime('now', '-30 days')
    `, [listingId]);
    
    // Higher velocity = more frequent syncs
    const velocity = stats.booking_count / 30; // bookings per day
    
    if (velocity > 0.5) return 5 * 60 * 1000;   // 5 minutes
    if (velocity > 0.2) return 15 * 60 * 1000;  // 15 minutes
    return 60 * 60 * 1000;                      // 1 hour
  }
}
```

---

## 5. Webhook Event Handling Architecture

### 5.1 Event Processing Pipeline

```typescript
// Event flow: Guesty → Receiver → Queue → Processor → Handlers

interface WebhookEvent {
  id: number;
  webhookId: string;
  eventType: string;
  payload: any;
  signature: string;
  receivedAt: string;
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'retrying';
  retryCount: number;
}

class WebhookEventProcessor {
  private readonly MAX_RETRIES = 3;
  private readonly RETRY_DELAYS = [5000, 30000, 120000]; // 5s, 30s, 2m
  
  async receiveEvent(
    webhookId: string,
    eventType: string,
    payload: any,
    signature: string
  ): Promise<void> {
    // Verify signature
    if (!this.verifySignature(payload, signature, webhookId)) {
      throw new Error('Invalid webhook signature');
    }
    
    // Extract IDs for quick lookup
    const extractedIds = this.extractIds(payload, eventType);
    
    // Queue event
    const eventId = await this.queueEvent({
      webhookId,
      eventType,
      payload: JSON.stringify(payload),
      signature,
      receivedAt: new Date().toISOString(),
      status: 'pending',
      retryCount: 0,
      ...extractedIds
    });
    
    // Trigger async processing
    this.processEvent(eventId).catch(console.error);
  }
  
  private async processEvent(eventId: number): Promise<void> {
    const event = await this.db.get(
      'SELECT * FROM webhook_events WHERE id = ?',
      [eventId]
    );
    
    if (!event || event.status !== 'pending') {
      return; // Already processed or cancelled
    }
    
    // Mark as processing
    await this.db.execute(
      "UPDATE webhook_events SET status = 'processing' WHERE id = ?",
      [eventId]
    );
    
    try {
      const payload = JSON.parse(event.payload);
      
      // Route to appropriate handler
      const handler = this.getHandler(event.eventType);
      await handler.handle(payload, event);
      
      // Mark as completed
      await this.db.execute(
        "UPDATE webhook_events SET status = 'completed', processed_at = ? WHERE id = ?",
        [new Date().toISOString(), eventId]
      );
      
    } catch (error) {
      await this.handleProcessingError(eventId, error);
    }
  }
  
  private async handleProcessingError(
    eventId: number,
    error: Error
  ): Promise<void> {
    const event = await this.db.get(
      'SELECT retry_count FROM webhook_events WHERE id = ?',
      [eventId]
    );
    
    if (event.retry_count < this.MAX_RETRIES) {
      // Schedule retry
      const delay = this.RETRY_DELAYS[event.retry_count];
      const nextRetry = new Date(Date.now() + delay);
      
      await this.db.execute(
        `UPDATE webhook_events 
         SET status = 'retrying', 
             retry_count = retry_count + 1,
             error_message = ?
         WHERE id = ?`,
        [error.message, eventId]
      );
      
      // Schedule retry
      setTimeout(() => this.processEvent(eventId), delay);
      
    } else {
      // Max retries exceeded - move to dead letter queue
      await this.db.execute(
        `UPDATE webhook_events 
         SET status = 'failed', 
             error_message = ?,
             processed_at = ?
         WHERE id = ?`,
        [error.message, new Date().toISOString(), eventId]
      );
      
      // Alert on failure
      await this.alertOnFailedEvent(eventId, error);
    }
  }
  
  private getHandler(eventType: string): EventHandler {
    const handlers: Record<string, EventHandler> = {
      'reservation.new': new ReservationCreatedHandler(),
      'reservation.updated': new ReservationUpdatedHandler(),
      'reservation.canceled': new ReservationCanceledHandler(),
      'reservation.confirmed': new ReservationConfirmedHandler(),
      'listing.calendar.updated': new CalendarUpdatedHandler(),
      'calendar.updated.v2': new CalendarUpdatedV2Handler(),
      'task.created': new TaskCreatedHandler(),
      'payments.received': new PaymentReceivedHandler(),
      'payments.failed': new PaymentFailedHandler()
    };
    
    return handlers[eventType] || new DefaultHandler();
  }
  
  private extractIds(payload: any, eventType: string): Partial<WebhookEvent> {
    const result: Partial<WebhookEvent> = {};
    
    if (eventType.startsWith('reservation.')) {
      result.reservationId = payload.reservation?._id;
      result.listingId = payload.listing?._id || payload.reservation?.listingId;
      result.guestId = payload.guest?._id;
    } else if (eventType.includes('listing.')) {
      result.listingId = payload.listing?._id || payload.listingId;
    } else if (eventType.startsWith('guest.')) {
      result.guestId = payload.guest?._id;
    }
    
    return result;
  }
}
```

### 5.2 Event Handlers

```typescript
// Base handler interface
interface EventHandler {
  handle(payload: any, event: WebhookEvent): Promise<void>;
}

class ReservationCreatedHandler implements EventHandler {
  async handle(payload: any, event: WebhookEvent): Promise<void> {
    const reservation = payload.reservation;
    const guest = payload.guest;
    
    // 1. Sync reservation to database
    await this.syncReservation(reservation);
    
    // 2. Sync guest if new
    if (guest) {
      await this.syncGuest(guest);
    }
    
    // 3. Update calendar blocks
    await this.updateCalendarBlocks(reservation);
    
    // 4. Trigger automations
    await this.triggerAutomations('reservation.new', {
      reservation,
      guest,
      listing: payload.listing
    });
    
    // 5. Queue notifications
    await this.queueNotifications(reservation, 'new_booking');
  }
  
  private async syncReservation(reservation: any): Promise<void> {
    // Full sync of the reservation
    const extractor = new FinancialDataExtractor();
    const financials = await extractor.extractFinancials(reservation._id);
    
    await this.db.transaction(async (trx) => {
      // Upsert reservation
      await trx.execute(`
        INSERT OR REPLACE INTO reservations (...)
        VALUES (...)
      `, [...]);
      
      // Insert invoice items
      for (const item of financials.invoiceItems) {
        await trx.execute(`
          INSERT OR REPLACE INTO invoice_items (...)
          VALUES (...)
        `, [...]);
      }
      
      // Insert payments
      for (const payment of financials.payments) {
        await trx.execute(`
          INSERT OR REPLACE INTO payments (...)
          VALUES (...)
        `, [...]);
      }
    });
  }
  
  private async triggerAutomations(
    eventType: string,
    context: any
  ): Promise<void> {
    const rules = await this.db.query(`
      SELECT * FROM automation_rules
      WHERE event_type = ? AND is_active = 1
    `, [eventType]);
    
    for (const rule of rules) {
      const shouldExecute = this.evaluateCondition(
        JSON.parse(rule.condition),
        context
      );
      
      if (shouldExecute) {
        await this.executeAutomationRule(rule, context);
      }
    }
  }
}

class CalendarUpdatedHandler implements EventHandler {
  async handle(payload: any, event: WebhookEvent): Promise<void> {
    const listingId = payload.listingId || payload.listing?._id;
    const calendar = payload.calendar;
    
    if (!listingId || !calendar) return;
    
    // Update specific calendar day
    const date = calendar.date;
    const compositeId = `${listingId}|${date}`;
    
    await this.db.execute(`
      INSERT OR REPLACE INTO calendar_days (
        id, listing_id, date, status, price,
        synced_at, raw_data
      ) VALUES (?, ?, ?, ?, ?, ?, ?)
    `, [
      compositeId,
      listingId,
      date,
      calendar.status,
      calendar.price,
      new Date().toISOString(),
      JSON.stringify(calendar)
    ]);
    
    // Trigger availability-based automations
    if (calendar.status === 'available') {
      await this.checkDynamicPricing(listingId, date);
    }
  }
  
  private async checkDynamicPricing(
    listingId: string,
    date: string
  ): Promise<void> {
    // Check if we should adjust pricing based on new availability
    // This could integrate with a dynamic pricing engine
  }
}

class PaymentReceivedHandler implements EventHandler {
  async handle(payload: any, event: WebhookEvent): Promise<void> {
    const payment = payload.payment;
    const reservation = payload.reservation;
    
    // Sync payment
    await this.db.execute(`
      INSERT OR REPLACE INTO payments (...)
      VALUES (...)
    `, [...]);
    
    // Check if fully paid
    if (reservation?.money?.balanceDue === 0) {
      // Queue fully paid notification
      await this.queueNotification({
        type: 'reservation_fully_paid',
        reservationId: reservation._id,
        guestEmail: reservation.guest?.email
      });
    }
  }
}
```

### 5.3 Webhook Verification

```typescript
class WebhookVerifier {
  async verifySignature(
    payload: string,
    signature: string,
    webhookId: string
  ): Promise<boolean> {
    // Get webhook secret
    const webhook = await this.db.get(
      'SELECT secret FROM webhooks WHERE id = ?',
      [webhookId]
    );
    
    if (!webhook?.secret) {
      // If no secret configured, accept (for debugging)
      return true;
    }
    
    // Compute HMAC
    const computed = crypto
      .createHmac('sha256', webhook.secret)
      .update(payload)
      .digest('hex');
    
    // Constant-time comparison
    return crypto.timingSafeEqual(
      Buffer.from(computed),
      Buffer.from(signature)
    );
  }
}
```

### 5.4 Dead Letter Queue Management

```typescript
class DeadLetterQueue {
  async processFailedEvents(): Promise<void> {
    const failedEvents = await this.db.query(`
      SELECT * FROM webhook_events
      WHERE status = 'failed'
        AND processed_at < datetime('now', '-1 hour')
      ORDER BY received_at ASC
      LIMIT 10
    `);
    
    for (const event of failedEvents) {
      const canRetry = await this.analyzeFailure(event);
      
      if (canRetry) {
        // Reset for manual retry
        await this.db.execute(`
          UPDATE webhook_events
          SET status = 'pending',
              retry_count = 0,
              error_message = NULL
          WHERE id = ?
        `, [event.id]);
        
        // Trigger reprocessing
        this.processor.processEvent(event.id);
      } else {
        // Move to permanent dead letter queue
        await this.archiveEvent(event);
      }
    }
  }
  
  private async analyzeFailure(event: WebhookEvent): Promise<boolean> {
    // Analyze error patterns
    if (event.error_message?.includes('constraint')) {
      // Data integrity issue - likely won't fix itself
      return false;
    }
    
    if (event.error_message?.includes('timeout')) {
      // Transient issue - can retry
      return true;
    }
    
    // Check if upstream system recovered
    const upstreamHealth = await this.checkUpstreamHealth(event.eventType);
    return upstreamHealth;
  }
}
```

---

## 6. Implementation Phases

### Phase 1: Foundation (Weeks 1-2)

**Goals:** Establish new schema and basic infrastructure

**Tasks:**
- [ ] Create migration system for schema changes
- [ ] Implement new tables (invoice_items, payments, calendar_days, webhook_events)
- [ ] Add columns to existing tables (reservations.tax_amount, etc.)
- [ ] Create indexes for performance
- [ ] Build sync_runs and sync_cursors tables
- [ ] Implement change_log for audit trail

**Deliverables:**
- Schema migration scripts
- Updated database module
- Migration CLI commands: `guesty migrate up`, `guesty migrate down`

### Phase 2: Enhanced Sync Engine (Weeks 3-4)

**Goals:** Implement incremental sync and rate limiting

**Tasks:**
- [ ] Build IncrementalSyncEngine class
- [ ] Implement cursor-based pagination
- [ ] Add RateLimitManager with token bucket
- [ ] Create sync conflict resolution
- [ ] Build resumable sync (checkpointing)
- [ ] Add sync metrics and monitoring

**Deliverables:**
- `guesty sync --incremental` flag
- Sync status dashboard: `guesty sync --status --detailed`
- Sync history: `guesty sync --history`

### Phase 3: Financial Deep Dive (Weeks 5-6)

**Goals:** Comprehensive financial tracking

**Tasks:**
- [ ] Implement FinancialDataExtractor
- [ ] Build invoice_items sync from money object
- [ ] Create payments sync
- [ ] Implement tax reporting (DR-15)
- [ ] Build owner payout calculation
- [ ] Create financial reconciliation reports

**Deliverables:**
- `guesty financials sync` - Deep financial sync
- `guesty financials invoice <reservation>` - Invoice detail
- `guesty financials tax-report --period 2026-01` - DR-15 generation
- `guesty financials owner-statement <owner> --month 2026-01`

### Phase 4: Calendar Management (Weeks 7-8)

**Goals:** Efficient multi-property calendar sync

**Tasks:**
- [ ] Build CalendarSyncManager
- [ ] Implement prioritized sync windows
- [ ] Create calendar change detection
- [ ] Build calendar cache in SQLite
- [ ] Implement booking velocity tracking
- [ ] Add calendar conflict detection

**Deliverables:**
- `guesty calendar sync` - Sync all calendars
- `guesty calendar sync --listing <id>` - Single listing
- `guesty calendar availability --from X --to Y` - Cross-property availability
- `guesty calendar conflicts` - Detect double bookings

### Phase 5: Webhook Infrastructure (Weeks 9-10)

**Goals:** Real-time event processing

**Tasks:**
- [ ] Build WebhookEventProcessor
- [ ] Create event handler classes
- [ ] Implement webhook signature verification
- [ ] Build event queue with retry logic
- [ ] Create dead letter queue
- [ ] Implement automation engine

**Deliverables:**
- `guesty webhook server` - Start webhook receiver
- `guesty webhook events` - View event queue
- `guesty webhook retry <event-id>` - Retry failed event
- `guesty automation list` - List automation rules

### Phase 6: Operational Features (Weeks 11-12)

**Goals:** Damage claims, notifications, monitoring

**Tasks:**
- [ ] Build damage_claims tracking
- [ ] Create notification queue system
- [ ] Implement alert system for deadlines
- [ ] Build operational dashboard
- [ ] Add guest segmentation
- [ ] Create owner portal features

**Deliverables:**
- `guesty damage create <reservation>` - File damage claim
- `guesty damage deadlines` - Show upcoming deadlines
- `guesty alerts` - View operational alerts
- `guesty dashboard` - Rich operational dashboard

### Phase 7: Performance & Polish (Week 13)

**Goals:** Optimization and production readiness

**Tasks:**
- [ ] Performance testing and optimization
- [ ] Add connection pooling
- [ ] Implement query caching
- [ ] Build health check endpoints
- [ ] Create comprehensive documentation
- [ ] Add integration tests

**Deliverables:**
- Performance benchmarks
- Health check: `guesty health`
- Complete API documentation
- Integration test suite

---

## 7. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Guesty CLI                                  │
│                    (Production Grade)                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │   Commands   │  │   Commands   │  │   Commands   │             │
│  │  (Read Ops)  │  │  (Write Ops) │  │   (Admin)    │             │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘             │
│         │                 │                 │                      │
│         └─────────────────┼─────────────────┘                      │
│                           │                                        │
│                    ┌──────┴──────┐                                 │
│                    │  Core API   │                                 │
│                    │   Layer     │                                 │
│                    └──────┬──────┘                                 │
│                           │                                        │
│  ┌────────────────────────┼────────────────────────┐              │
│  │                        │                        │              │
│  ▼                        ▼                        ▼              │
│ ┌────────────────┐  ┌────────────────┐  ┌────────────────┐       │
│ │  Sync Engine   │  │ Webhook Proc.  │  │ Financial Ext. │       │
│ │                │  │                │  │                │       │
│ │ • Incremental  │  │ • Event Queue  │  │ • Invoice Parse│       │
│ │ • Rate Limit   │  │ • Retry Logic  │  │ • Tax Report   │       │
│ │ • Conflict Res │  │ • DLQ          │  │ • Owner Payout │       │
│ └───────┬────────┘  └───────┬────────┘  └───────┬────────┘       │
│         │                   │                   │                 │
│         └───────────────────┼───────────────────┘                 │
│                             │                                     │
│                    ┌────────┴────────┐                           │
│                    │  Data Access    │                           │
│                    │     Layer       │                           │
│                    └────────┬────────┘                           │
│                             │                                     │
│  ┌──────────────────────────┼──────────────────────────┐        │
│  │                          │                          │        │
│  ▼                          ▼                          ▼        │
│ ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐│
│ │   SQLite Cache   │  │   Guesty API     │  │  External Svcs   ││
│ │                  │  │                  │  │                  ││
│ │ • reservations   │  │ • REST API       │  │ • Stripe         ││
│ │ • calendar_days  │  │ • Rate Limited   │  │ • Email          ││
│ │ • invoice_items  │  │ • OAuth2 Auth    │  │ • Slack          ││
│ │ • webhook_events │  │                  │  │                  ││
│ │ • FTS5 Search    │  │                  │  │                  ││
│ └──────────────────┘  └──────────────────┘  └──────────────────┘│
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 8. Key Metrics & SLAs

| Metric | Target | Measurement |
|--------|--------|-------------|
| Sync Latency (incremental) | < 30 seconds | Time from API change to DB update |
| Calendar Sync (18 properties) | < 60 seconds | Full 365-day calendar sync |
| Webhook Processing | < 5 seconds | Event received to processing start |
| API Rate Limit Safety | > 20% buffer | Remaining capacity before throttling |
| Financial Data Accuracy | 100% | Invoice line items match API |
| Query Response Time | < 100ms | Local SQLite queries |
| Sync Success Rate | > 99.5% | Successful sync runs |
| Webhook Delivery | > 99.9% | Events successfully processed |

---

## 9. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| API Rate Limits | Token bucket + exponential backoff + caching |
| Token Exhaustion (5/24h) | Aggressive token caching + monitoring alerts |
| Data Inconsistency | Change logs + conflict resolution + periodic full sync |
| Webhook Failures | Retry queue + DLQ + manual replay capability |
| Database Corruption | WAL mode + regular backups + sync from API |
| Large Dataset Performance | Indexes + pagination + selective field fetching |

---

*Document Version: 1.0*  
*Last Updated: 2026-02-07*  
*Author: Lucy (VPVR Operations Intelligence)*
