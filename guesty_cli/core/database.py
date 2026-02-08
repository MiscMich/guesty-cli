"""SQLite Local Cache for Guesty data.

Full-text search via FTS5.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Schema definitions for each table
LISTINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id TEXT PRIMARY KEY,
    title TEXT,
    nickname TEXT,
    status TEXT,
    type TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    country TEXT,
    zipcode TEXT,
    bedrooms INTEGER,
    bathrooms REAL,
    max_guests INTEGER,
    base_price REAL,
    currency TEXT,
    picture TEXT,
    active INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT,
    raw_data TEXT
);
"""

RESERVATIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS reservations (
    id TEXT PRIMARY KEY,
    confirmation_code TEXT,
    status TEXT,
    source TEXT,
    check_in TEXT,
    check_out TEXT,
    listing_id TEXT,
    guest_id TEXT,
    guest_name TEXT,
    guest_email TEXT,
    guest_phone TEXT,
    nights INTEGER,
    guests_count INTEGER,
    subtotal REAL,
    total_price REAL,
    currency TEXT,
    created_at TEXT,
    updated_at TEXT,
    raw_data TEXT
);
"""

GUESTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS guests (
    id TEXT PRIMARY KEY,
    first_name TEXT,
    last_name TEXT,
    full_name TEXT,
    email TEXT,
    phone TEXT,
    country TEXT,
    created_at TEXT,
    updated_at TEXT,
    raw_data TEXT
);
"""

OWNERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS owners (
    id TEXT PRIMARY KEY,
    first_name TEXT,
    last_name TEXT,
    full_name TEXT,
    email TEXT,
    phone TEXT,
    company TEXT,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT,
    raw_data TEXT
);
"""

REVIEWS_SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY,
    reservation_id TEXT,
    listing_id TEXT,
    guest_id TEXT,
    rating REAL,
    comment TEXT,
    created_at TEXT,
    updated_at TEXT,
    raw_data TEXT
);
"""

TASKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT,
    description TEXT,
    status TEXT,
    priority TEXT,
    assigned_to TEXT,
    listing_id TEXT,
    reservation_id TEXT,
    due_date TEXT,
    completed_at TEXT,
    created_at TEXT,
    updated_at TEXT,
    raw_data TEXT
);
"""

WEBHOOKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS webhooks (
    id TEXT PRIMARY KEY,
    url TEXT,
    events TEXT,
    active INTEGER,
    created_at TEXT,
    updated_at TEXT,
    raw_data TEXT
);
"""

USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT,
    first_name TEXT,
    last_name TEXT,
    role TEXT,
    active INTEGER,
    created_at TEXT,
    updated_at TEXT,
    raw_data TEXT
);
"""

INTEGRATIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS integrations (
    id TEXT PRIMARY KEY,
    name TEXT,
    type TEXT,
    status TEXT,
    settings TEXT,
    created_at TEXT,
    updated_at TEXT,
    raw_data TEXT
);
"""

SYNC_LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    endpoint TEXT,
    records_synced INTEGER,
    duration_seconds REAL,
    status TEXT,
    error_message TEXT
);
"""

INVOICE_ITEMS_SCHEMA = """
CREATE TABLE IF NOT EXISTS invoice_items (
    id TEXT PRIMARY KEY,
    reservation_id TEXT,
    listing_id TEXT,
    type TEXT,
    description TEXT,
    amount REAL,
    currency TEXT,
    taxable INTEGER,
    created_at TEXT,
    updated_at TEXT,
    raw_data TEXT
);
"""

TAX_LINE_ITEMS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tax_line_items (
    id TEXT PRIMARY KEY,
    reservation_id TEXT,
    listing_id TEXT,
    tax_name TEXT,
    tax_rate REAL,
    taxable_amount REAL,
    tax_amount REAL,
    county TEXT,
    reporting_period TEXT,
    created_at TEXT,
    updated_at TEXT,
    raw_data TEXT
);
"""

SYNC_CURSORS_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_cursors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT UNIQUE,
    last_cursor TEXT,
    last_synced_at TEXT,
    record_count INTEGER,
    status TEXT
);
"""

# Calendar days table for storing calendar sync data
CALENDAR_DAYS_SCHEMA = """
CREATE TABLE IF NOT EXISTS calendar_days (
    id TEXT PRIMARY KEY,
    listing_id TEXT,
    date TEXT,
    status TEXT,
    price REAL,
    min_stay INTEGER,
    reservation_id TEXT,
    raw_data TEXT
);
"""

# FTS5 virtual table for full-text search
FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
    table_name,
    record_id,
    content,
    content_rowid=rowid
);
"""

ALL_SCHEMAS = [
    LISTINGS_SCHEMA,
    RESERVATIONS_SCHEMA,
    GUESTS_SCHEMA,
    OWNERS_SCHEMA,
    REVIEWS_SCHEMA,
    TASKS_SCHEMA,
    WEBHOOKS_SCHEMA,
    USERS_SCHEMA,
    INTEGRATIONS_SCHEMA,
    SYNC_LOG_SCHEMA,
    INVOICE_ITEMS_SCHEMA,
    TAX_LINE_ITEMS_SCHEMA,
    SYNC_CURSORS_SCHEMA,
    CALENDAR_DAYS_SCHEMA,
    FTS_SCHEMA,
]


def get_db(config: dict = None) -> sqlite3.Connection:
    """Get a database connection.
    
    Args:
        config: Optional config dict with db_path.
        
    Returns:
        sqlite3.Connection: Database connection with row factory.
    """
    from .config import get_db_path
    
    db_path = get_db_path(config)
    
    # Ensure directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    
    # Disable foreign keys (existing DBs may have data without matching FKs)
    conn.execute("PRAGMA foreign_keys = OFF")
    
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Initialize database with all tables.
    
    Args:
        conn: Database connection.
    """
    for schema in ALL_SCHEMAS:
        conn.executescript(schema)
    conn.commit()


def _extract_nested(data: dict, path: str, default=None) -> Any:
    """Extract a nested value from a dict using dot notation.
    
    Args:
        data: Dictionary to search.
        path: Dot-separated path (e.g., 'address.city').
        default: Default value if not found.
        
    Returns:
        Value at path or default.
    """
    keys = path.split(".")
    value = data
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key, default)
        else:
            return default
    return value


def upsert_listings(conn: sqlite3.Connection, listings: list) -> int:
    """Upsert listings into database.
    
    Args:
        conn: Database connection.
        listings: List of listing dictionaries.
        
    Returns:
        int: Number of records upserted.
    """
    cursor = conn.cursor()
    
    for listing in listings:
        if not isinstance(listing, dict):
            continue
            
        listing_id = listing.get("_id") or listing.get("id")
        if not listing_id:
            continue
        
        address = listing.get("address", {})
        
        cursor.execute("""
            INSERT OR REPLACE INTO listings (
                id, title, nickname, status, type,
                address, city, state, country, zipcode,
                bedrooms, bathrooms, max_guests,
                base_price, currency, picture,
                active, created_at, updated_at, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            listing_id,
            listing.get("title"),
            listing.get("nickname"),
            listing.get("status"),
            listing.get("type"),
            address.get("full"),
            address.get("city"),
            address.get("state"),
            address.get("country"),
            address.get("zipcode"),
            listing.get("bedrooms"),
            listing.get("bathrooms"),
            listing.get("accommodates"),
            _extract_nested(listing, "prices.basePrice"),
            listing.get("currency"),
            listing.get("picture", {}).get("regular") if isinstance(listing.get("picture"), dict) else None,
            1 if listing.get("active") else 0,
            listing.get("createdAt"),
            listing.get("updatedAt"),
            json.dumps(listing),
        ))
    
    conn.commit()
    return len(listings)


def upsert_reservations(conn: sqlite3.Connection, reservations: list) -> int:
    """Upsert reservations into database.
    
    Args:
        conn: Database connection.
        reservations: List of reservation dictionaries.
        
    Returns:
        int: Number of records upserted.
    """
    cursor = conn.cursor()
    
    for res in reservations:
        if not isinstance(res, dict):
            continue
            
        res_id = res.get("_id") or res.get("id")
        if not res_id:
            continue
        
        guest = res.get("guest", {})
        
        cursor.execute("""
            INSERT OR REPLACE INTO reservations (
                id, confirmation_code, status, source,
                check_in, check_out, listing_id, guest_id,
                guest_name, guest_email, guest_phone,
                nights, guests_count,
                subtotal, total_price, currency,
                created_at, updated_at, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            res_id,
            res.get("confirmationCode"),
            res.get("status"),
            res.get("source"),
            res.get("checkIn"),
            res.get("checkOut"),
            res.get("listingId"),
            guest.get("_id") if isinstance(guest, dict) else None,
            f"{guest.get('firstName', '')} {guest.get('lastName', '')}".strip() if isinstance(guest, dict) else None,
            guest.get("email") if isinstance(guest, dict) else None,
            guest.get("phone") if isinstance(guest, dict) else None,
            res.get("nightsCount"),
            res.get("guestsCount"),
            res.get("subtotal"),
            res.get("money", {}).get("fareAccommodation") if isinstance(res.get("money"), dict) else None,
            res.get("currency"),
            res.get("createdAt"),
            res.get("updatedAt"),
            json.dumps(res),
        ))
    
    conn.commit()
    return len(reservations)


def upsert_guests(conn: sqlite3.Connection, guests: list) -> int:
    """Upsert guests into database.
    
    Args:
        conn: Database connection.
        guests: List of guest dictionaries.
        
    Returns:
        int: Number of records upserted.
    """
    cursor = conn.cursor()
    
    for guest in guests:
        if not isinstance(guest, dict):
            continue
            
        guest_id = guest.get("_id") or guest.get("id")
        if not guest_id:
            continue
        
        first_name = guest.get("firstName", "")
        last_name = guest.get("lastName", "")
        
        cursor.execute("""
            INSERT OR REPLACE INTO guests (
                id, first_name, last_name, full_name,
                email, phone, country,
                created_at, updated_at, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            guest_id,
            first_name,
            last_name,
            f"{first_name} {last_name}".strip(),
            guest.get("email"),
            guest.get("phone"),
            guest.get("country"),
            guest.get("createdAt"),
            guest.get("updatedAt"),
            json.dumps(guest),
        ))
    
    conn.commit()
    return len(guests)


def upsert_owners(conn: sqlite3.Connection, owners: list) -> int:
    """Upsert owners into database.
    
    Args:
        conn: Database connection.
        owners: List of owner dictionaries.
        
    Returns:
        int: Number of records upserted.
    """
    cursor = conn.cursor()
    
    for owner in owners:
        if not isinstance(owner, dict):
            continue
            
        owner_id = owner.get("_id") or owner.get("id")
        if not owner_id:
            continue
        
        first_name = owner.get("firstName", "")
        last_name = owner.get("lastName", "")
        
        cursor.execute("""
            INSERT OR REPLACE INTO owners (
                id, first_name, last_name, full_name,
                email, phone, company, notes,
                created_at, updated_at, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            owner_id,
            first_name,
            last_name,
            f"{first_name} {last_name}".strip(),
            owner.get("email"),
            owner.get("phone"),
            owner.get("company"),
            owner.get("notes"),
            owner.get("createdAt"),
            owner.get("updatedAt"),
            json.dumps(owner),
        ))
    
    conn.commit()
    return len(owners)


def upsert_reviews(conn: sqlite3.Connection, reviews: list) -> int:
    """Upsert reviews into database.
    
    Args:
        conn: Database connection.
        reviews: List of review dictionaries.
        
    Returns:
        int: Number of records upserted.
    """
    cursor = conn.cursor()
    
    for review in reviews:
        if not isinstance(review, dict):
            continue
            
        review_id = review.get("_id") or review.get("id")
        if not review_id:
            continue
        
        cursor.execute("""
            INSERT OR REPLACE INTO reviews (
                id, reservation_id, listing_id, guest_id,
                rating, comment,
                created_at, updated_at, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            review_id,
            review.get("reservationId"),
            review.get("listingId"),
            review.get("guestId"),
            review.get("rating"),
            review.get("comment"),
            review.get("createdAt"),
            review.get("updatedAt"),
            json.dumps(review),
        ))
    
    conn.commit()
    return len(reviews)


def upsert_tasks(conn: sqlite3.Connection, tasks: list) -> int:
    """Upsert tasks into database.
    
    Args:
        conn: Database connection.
        tasks: List of task dictionaries.
        
    Returns:
        int: Number of records upserted.
    """
    cursor = conn.cursor()
    
    for task in tasks:
        if not isinstance(task, dict):
            continue
            
        task_id = task.get("_id") or task.get("id")
        if not task_id:
            continue
        
        cursor.execute("""
            INSERT OR REPLACE INTO tasks (
                id, title, description, status, priority,
                assigned_to, listing_id, reservation_id,
                due_date, completed_at,
                created_at, updated_at, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_id,
            task.get("title"),
            task.get("description"),
            task.get("status"),
            task.get("priority"),
            task.get("assignedTo"),
            task.get("listingId"),
            task.get("reservationId"),
            task.get("dueDate"),
            task.get("completedAt"),
            task.get("createdAt"),
            task.get("updatedAt"),
            json.dumps(task),
        ))
    
    conn.commit()
    return len(tasks)


def upsert_webhooks(conn: sqlite3.Connection, webhooks: list) -> int:
    """Upsert webhooks into database.
    
    Args:
        conn: Database connection.
        webhooks: List of webhook dictionaries.
        
    Returns:
        int: Number of records upserted.
    """
    cursor = conn.cursor()
    
    for webhook in webhooks:
        if not isinstance(webhook, dict):
            continue
            
        webhook_id = webhook.get("_id") or webhook.get("id")
        if not webhook_id:
            continue
        
        events = webhook.get("events", [])
        if isinstance(events, list):
            events = json.dumps(events)
        
        cursor.execute("""
            INSERT OR REPLACE INTO webhooks (
                id, url, events, active,
                created_at, updated_at, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            webhook_id,
            webhook.get("url"),
            events,
            1 if webhook.get("active") else 0,
            webhook.get("createdAt"),
            webhook.get("updatedAt"),
            json.dumps(webhook),
        ))
    
    conn.commit()
    return len(webhooks)


def upsert_users(conn: sqlite3.Connection, users: list) -> int:
    """Upsert users into database.
    
    Args:
        conn: Database connection.
        users: List of user dictionaries.
        
    Returns:
        int: Number of records upserted.
    """
    cursor = conn.cursor()
    
    for user in users:
        if not isinstance(user, dict):
            continue
            
        user_id = user.get("_id") or user.get("id")
        if not user_id:
            continue
        
        cursor.execute("""
            INSERT OR REPLACE INTO users (
                id, email, first_name, last_name, role,
                active, created_at, updated_at, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            user.get("email"),
            user.get("firstName"),
            user.get("lastName"),
            user.get("role"),
            1 if user.get("active") else 0,
            user.get("createdAt"),
            user.get("updatedAt"),
            json.dumps(user),
        ))
    
    conn.commit()
    return len(users)


def upsert_integrations(conn: sqlite3.Connection, integrations: list) -> int:
    """Upsert integrations into database.
    
    Args:
        conn: Database connection.
        integrations: List of integration dictionaries.
        
    Returns:
        int: Number of records upserted.
    """
    cursor = conn.cursor()
    
    for integration in integrations:
        if not isinstance(integration, dict):
            continue
            
        integration_id = integration.get("_id") or integration.get("id")
        if not integration_id:
            continue
        
        settings = integration.get("settings", {})
        if isinstance(settings, dict):
            settings = json.dumps(settings)
        
        cursor.execute("""
            INSERT OR REPLACE INTO integrations (
                id, name, type, status, settings,
                created_at, updated_at, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            integration_id,
            integration.get("name"),
            integration.get("type"),
            integration.get("status"),
            settings,
            integration.get("createdAt"),
            integration.get("updatedAt"),
            json.dumps(integration),
        ))
    
    conn.commit()
    return len(integrations)


def rebuild_search_index(conn: sqlite3.Connection) -> int:
    """Rebuild the FTS5 search index from all tables.
    
    Args:
        conn: Database connection.
        
    Returns:
        int: Number of records indexed.
    """
    cursor = conn.cursor()
    
    # Clear existing index
    cursor.execute("DELETE FROM search_index")
    
    indexed_count = 0
    
    # Index listings
    for row in cursor.execute("SELECT id, title, address, city FROM listings"):
        content = f"{row['title'] or ''} {row['address'] or ''} {row['city'] or ''}"
        cursor.execute(
            "INSERT INTO search_index (table_name, record_id, content) VALUES (?, ?, ?)",
            ("listings", row["id"], content)
        )
        indexed_count += 1
    
    # Index reservations
    for row in cursor.execute("SELECT id, guest_name, confirmation_code FROM reservations"):
        content = f"{row['guest_name'] or ''} {row['confirmation_code'] or ''}"
        cursor.execute(
            "INSERT INTO search_index (table_name, record_id, content) VALUES (?, ?, ?)",
            ("reservations", row["id"], content)
        )
        indexed_count += 1
    
    # Index guests
    for row in cursor.execute("SELECT id, full_name, email, phone FROM guests"):
        content = f"{row['full_name'] or ''} {row['email'] or ''} {row['phone'] or ''}"
        cursor.execute(
            "INSERT INTO search_index (table_name, record_id, content) VALUES (?, ?, ?)",
            ("guests", row["id"], content)
        )
        indexed_count += 1
    
    # Index owners
    for row in cursor.execute("SELECT id, full_name, email, company FROM owners"):
        content = f"{row['full_name'] or ''} {row['email'] or ''} {row['company'] or ''}"
        cursor.execute(
            "INSERT INTO search_index (table_name, record_id, content) VALUES (?, ?, ?)",
            ("owners", row["id"], content)
        )
        indexed_count += 1
    
    # Index tasks
    for row in cursor.execute("SELECT id, title, description FROM tasks"):
        content = f"{row['title'] or ''} {row['description'] or ''}"
        cursor.execute(
            "INSERT INTO search_index (table_name, record_id, content) VALUES (?, ?, ?)",
            ("tasks", row["id"], content)
        )
        indexed_count += 1
    
    conn.commit()
    return indexed_count


def search(conn: sqlite3.Connection, query: str, limit: int = 20) -> list:
    """Search across all tables using FTS5.
    
    Args:
        conn: Database connection.
        query: Search query.
        limit: Maximum results to return.
        
    Returns:
        list: Search results with table_name, record_id, content.
    """
    cursor = conn.cursor()
    
    # Escape special FTS5 characters
    query = query.replace('"', '""')
    
    try:
        cursor.execute("""
            SELECT table_name, record_id, content
            FROM search_index
            WHERE content MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit))
        
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.OperationalError:
        # FTS5 might not be available or table doesn't exist
        return []


def get_sync_status(conn: sqlite3.Connection) -> dict:
    """Get last sync status for each endpoint.
    
    Args:
        conn: Database connection.
        
    Returns:
        dict: Mapping of endpoint to last sync info.
    """
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT endpoint, timestamp, records_synced, status
        FROM sync_log
        WHERE id IN (
            SELECT MAX(id)
            FROM sync_log
            GROUP BY endpoint
        )
        ORDER BY timestamp DESC
    """)
    
    return {row["endpoint"]: dict(row) for row in cursor.fetchall()}


def log_sync(
    conn: sqlite3.Connection,
    endpoint: str,
    count: int,
    duration: float,
    status: str,
    error: str = None,
) -> None:
    """Log a sync operation.
    
    Args:
        conn: Database connection.
        endpoint: API endpoint synced.
        count: Number of records synced.
        duration: Duration in seconds.
        status: 'success' or 'error'.
        error: Optional error message.
    """
    cursor = conn.cursor()
    
    timestamp = datetime.now(timezone.utc).isoformat()
    
    cursor.execute("""
        INSERT INTO sync_log (timestamp, endpoint, records_synced, duration_seconds, status, error_message)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (timestamp, endpoint, count, duration, status, error))
    
    conn.commit()


def get_sync_cursor(conn: sqlite3.Connection, table_name: str) -> dict:
    """Get the last sync cursor for a table.
    
    Args:
        conn: Database connection.
        table_name: Name of the table.
        
    Returns:
        dict: Cursor info with last_cursor, last_synced_at, etc.
    """
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT last_cursor, last_synced_at, record_count, status
        FROM sync_cursors
        WHERE table_name = ?
        ORDER BY id DESC LIMIT 1
    """, (table_name,))
    
    row = cursor.fetchone()
    if row:
        return {
            'last_cursor': row['last_cursor'],
            'last_synced_at': row['last_synced_at'],
            'record_count': row['record_count'],
            'status': row['status']
        }
    return {}


def upsert_sync_cursor(
    conn: sqlite3.Connection,
    table_name: str,
    cursor_value: str,
    record_count: int = 0,
    status: str = "success"
) -> None:
    """Update or insert a sync cursor for a table.
    
    Args:
        conn: Database connection.
        table_name: Name of the table.
        cursor_value: The cursor value (timestamp or ID).
        record_count: Number of records synced.
        status: Sync status ('success' or 'error').
    """
    cursor = conn.cursor()
    
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Delete old cursor for this table, then insert new one
    cursor.execute("DELETE FROM sync_cursors WHERE table_name = ?", (table_name,))
    cursor.execute("""
        INSERT INTO sync_cursors (table_name, last_cursor, last_synced_at, record_count, status)
        VALUES (?, ?, ?, ?, ?)
    """, (table_name, cursor_value, timestamp, record_count, status))
    
    conn.commit()


def upsert_invoice_items(conn: sqlite3.Connection, items: list) -> int:
    """Upsert invoice items into database.
    
    Args:
        conn: Database connection.
        items: List of invoice item dictionaries.
        
    Returns:
        int: Number of records upserted.
    """
    cursor = conn.cursor()
    count = 0
    
    for item in items:
        if not isinstance(item, dict):
            continue
            
        item_id = item.get("_id") or item.get("id")
        if not item_id:
            # Generate a unique ID if none exists
            import hashlib
            reservation_id = item.get("reservation_id", "")
            item_type = item.get("type", "")
            desc = item.get("description", "")
            item_id = hashlib.md5(f"{reservation_id}:{item_type}:{desc}".encode()).hexdigest()
        
        cursor.execute("""
            INSERT OR REPLACE INTO invoice_items (
                id, reservation_id, listing_id, type, description,
                amount, currency, taxable, created_at, updated_at, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item_id,
            item.get("reservation_id") or item.get("reservationId"),
            item.get("listing_id") or item.get("listingId"),
            item.get("type"),
            item.get("description"),
            item.get("amount"),
            item.get("currency"),
            1 if item.get("taxable") else 0,
            item.get("createdAt"),
            item.get("updatedAt"),
            json.dumps(item),
        ))
        count += 1
    
    conn.commit()
    return count


def upsert_tax_line_items(conn: sqlite3.Connection, items: list) -> int:
    """Upsert tax line items into database.
    
    Args:
        conn: Database connection.
        items: List of tax line item dictionaries.
        
    Returns:
        int: Number of records upserted.
    """
    cursor = conn.cursor()
    count = 0
    
    for item in items:
        if not isinstance(item, dict):
            continue
            
        item_id = item.get("_id") or item.get("id")
        if not item_id:
            # Generate a unique ID if none exists
            import hashlib
            reservation_id = item.get("reservation_id", "")
            tax_name = item.get("taxName", "")
            county = item.get("county", "")
            item_id = hashlib.md5(f"{reservation_id}:{tax_name}:{county}".encode()).hexdigest()
        
        cursor.execute("""
            INSERT OR REPLACE INTO tax_line_items (
                id, reservation_id, listing_id, tax_name, tax_rate,
                taxable_amount, tax_amount, county, reporting_period,
                created_at, updated_at, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item_id,
            item.get("reservation_id") or item.get("reservationId"),
            item.get("listing_id") or item.get("listingId"),
            item.get("taxName"),
            item.get("taxRate"),
            item.get("taxableAmount"),
            item.get("taxAmount"),
            item.get("county"),
            item.get("reportingPeriod"),
            item.get("createdAt"),
            item.get("updatedAt"),
            json.dumps(item),
        ))
        count += 1
    
    conn.commit()
    return count

def insert_webhook_event(conn: sqlite3.Connection, event: dict) -> str:
    """Insert a webhook event into the database.
    
    Args:
        conn: Database connection.
        event: Webhook event dictionary.
        
    Returns:
        str: The event ID.
    """
    import uuid
    from datetime import datetime, timezone
    
    cursor = conn.cursor()
    event_id = event.get('id') or str(uuid.uuid4())
    
    cursor.execute("""
        INSERT INTO webhook_events (
            id, event_type, payload, processed, 
            processing_attempts, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        event_id,
        event.get('event_type', 'unknown'),
        json.dumps(event.get('payload', {})),
        0,  # not processed
        0,  # no attempts yet
        datetime.now(timezone.utc).isoformat()
    ))
    
    conn.commit()
    return event_id


def mark_webhook_processed(conn: sqlite3.Connection, event_id: str, error_message: str = None) -> bool:
    """Mark a webhook event as processed.
    
    Args:
        conn: Database connection.
        event_id: The webhook event ID.
        error_message: Optional error message if processing failed.
        
    Returns:
        bool: True if updated successfully.
    """
    from datetime import datetime, timezone
    
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE webhook_events 
        SET processed = 1, 
            processed_at = ?,
            error_message = ?
        WHERE id = ?
    """, (
        datetime.now(timezone.utc).isoformat(),
        error_message,
        event_id
    ))
    
    conn.commit()
    return cursor.rowcount > 0


def get_pending_webhook_events(conn: sqlite3.Connection, limit: int = 100) -> list:
    """Get pending webhook events that need processing.
    
    Args:
        conn: Database connection.
        limit: Maximum number of events to return.
        
    Returns:
        list: List of pending webhook events.
    """
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM webhook_events 
        WHERE processed = 0 
        AND processing_attempts < 3
        ORDER BY created_at ASC
        LIMIT ?
    """, (limit,))
    
    return [dict(row) for row in cursor.fetchall()]


def increment_webhook_attempts(conn: sqlite3.Connection, event_id: str) -> bool:
    """Increment the processing attempts counter for a webhook event.
    
    Args:
        conn: Database connection.
        event_id: The webhook event ID.
        
    Returns:
        bool: True if updated successfully.
    """
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE webhook_events 
        SET processing_attempts = processing_attempts + 1
        WHERE id = ?
    """, (event_id,))
    
    conn.commit()
    return cursor.rowcount > 0


def get_webhook_event_by_id(conn: sqlite3.Connection, event_id: str) -> dict:
    """Get a webhook event by ID.
    
    Args:
        conn: Database connection.
        event_id: The webhook event ID.
        
    Returns:
        dict: The webhook event or None.
    """
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM webhook_events WHERE id = ?", (event_id,))
    row = cursor.fetchone()
    
    return dict(row) if row else None


def update_webhook_event_status(conn: sqlite3.Connection, event_id: str, status: str, error_message: str = None) -> bool:
    """Update the status of a webhook event.
    
    Args:
        conn: Database connection.
        event_id: The webhook event ID.
        status: New status ('pending', 'processed', 'failed').
        error_message: Optional error message.
        
    Returns:
        bool: True if updated successfully.
    """
    from datetime import datetime, timezone
    
    cursor = conn.cursor()
    
    updates = ["status = ?"]
    params = [status]
    
    if status in ('processed', 'failed'):
        updates.append("processed_at = ?")
        params.append(datetime.now(timezone.utc).isoformat())
    
    if error_message:
        updates.append("error_message = ?")
        params.append(error_message)
    
    params.append(event_id)
    
    cursor.execute(f"""
        UPDATE webhook_events 
        SET {', '.join(updates)}
        WHERE id = ?
    """, params)
    
    conn.commit()
    return cursor.rowcount > 0


def get_webhook_event_log(conn: sqlite3.Connection, limit: int = 100) -> list:
    """Get the webhook event log.
    
    Args:
        conn: Database connection.
        limit: Maximum number of events to return.
        
    Returns:
        list: List of webhook events ordered by created_at DESC.
    """
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM webhook_events 
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))
    
    return [dict(row) for row in cursor.fetchall()]


def get_webhook_stats(conn: sqlite3.Connection) -> dict:
    """Get webhook statistics.
    
    Args:
        conn: Database connection.
        
    Returns:
        dict: Statistics about webhook events.
    """
    cursor = conn.cursor()
    
    # Total events
    cursor.execute("SELECT COUNT(*) FROM webhook_events")
    total = cursor.fetchone()[0]
    
    # Pending events
    cursor.execute("SELECT COUNT(*) FROM webhook_events WHERE processed = 0")
    pending = cursor.fetchone()[0]
    
    # Processed events
    cursor.execute("SELECT COUNT(*) FROM webhook_events WHERE processed = 1")
    processed = cursor.fetchone()[0]
    
    # Failed events (more than 3 attempts)
    cursor.execute("SELECT COUNT(*) FROM webhook_events WHERE processing_attempts >= 3 AND processed = 0")
    failed = cursor.fetchone()[0]
    
    return {
        'total': total,
        'pending': pending,
        'processed': processed,
        'failed': failed
    }
