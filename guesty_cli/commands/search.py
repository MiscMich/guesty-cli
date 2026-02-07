"""
Full-text search command for guesty-cli.
"""
import json
from guesty_cli.core.database import get_db
from guesty_cli.core.output import print_table, print_json, bold, dim, green, yellow


def _ensure_fts_index(db):
    """Ensure FTS5 index exists and is populated."""
    try:
        # Check if FTS5 table exists
        cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fts_index'")
        if not cursor.fetchone():
            # Create FTS5 virtual table
            db.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_index USING fts5(
                    table_name,
                    record_id,
                    content,
                    content_rowid='rowid'
                )
            """)
            db.commit()
        
        # Check if index has data
        cursor = db.execute("SELECT COUNT(*) FROM fts_index")
        count = cursor.fetchone()[0]
        
        if count == 0:
            # Rebuild index from all tables
            _rebuild_fts_index(db)
            return True
        
        return True
    except Exception as e:
        return False


def _rebuild_fts_index(db):
    """Rebuild FTS5 index from all tables."""
    try:
        # Clear existing index
        db.execute("DELETE FROM fts_index")
        
        # Index listings (nickname, title, address, city)
        try:
            cursor = db.execute("SELECT id, nickname, title, address, city FROM listings")
            for row in cursor.fetchall():
                content = ' '.join(str(v) for v in row[1:] if v)
                db.execute(
                    "INSERT INTO fts_index (table_name, record_id, content) VALUES (?, ?, ?)",
                    ('listings', row[0], content)
                )
        except Exception:
            pass
        
        # Index guests (names, email, phone)
        try:
            cursor = db.execute("SELECT id, firstName, lastName, fullName, email, phone FROM guests")
            for row in cursor.fetchall():
                content = ' '.join(str(v) for v in row[1:] if v)
                db.execute(
                    "INSERT INTO fts_index (table_name, record_id, content) VALUES (?, ?, ?)",
                    ('guests', row[0], content)
                )
        except Exception:
            pass
        
        # Index reservations (confirmation code, guest names)
        try:
            cursor = db.execute("SELECT id, confirmationCode, guestName, guestEmail FROM reservations")
            for row in cursor.fetchall():
                content = ' '.join(str(v) for v in row[1:] if v)
                db.execute(
                    "INSERT INTO fts_index (table_name, record_id, content) VALUES (?, ?, ?)",
                    ('reservations', row[0], content)
                )
        except Exception:
            pass
        
        # Index reviews (content)
        try:
            cursor = db.execute("SELECT id, content, reviewerName FROM reviews")
            for row in cursor.fetchall():
                content = ' '.join(str(v) for v in row[1:] if v)
                db.execute(
                    "INSERT INTO fts_index (table_name, record_id, content) VALUES (?, ?, ?)",
                    ('reviews', row[0], content)
                )
        except Exception:
            pass
        
        # Index tasks (title, description)
        try:
            cursor = db.execute("SELECT id, title, description FROM tasks")
            for row in cursor.fetchall():
                content = ' '.join(str(v) for v in row[1:] if v)
                db.execute(
                    "INSERT INTO fts_index (table_name, record_id, content) VALUES (?, ?, ?)",
                    ('tasks', row[0], content)
                )
        except Exception:
            pass
        
        db.commit()
        return True
    except Exception as e:
        return False


def register(subparsers):
    """Register search command with the argument parser."""
    parser = subparsers.add_parser(
        'search',
        help='Full-text search across all local data'
    )
    parser.set_defaults(func=run)
    parser.add_argument('query', help='Search query')
    parser.add_argument('--table', type=str, help='Filter to specific table')
    parser.add_argument('--limit', type=int, default=20, help='Limit results')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--rebuild', action='store_true', help='Rebuild search index')


def run(args):
    """Execute search query."""
    query = args.query
    
    if len(query) < 2:
        print("Query too short. Minimum 2 characters.")
        return
    
    db = get_db()
    
    # Handle rebuild request
    if args.rebuild:
        print("Rebuilding search index...")
        if _rebuild_fts_index(db):
            print(green("✓ Search index rebuilt successfully"))
        else:
            print("Failed to rebuild index")
        return
    
    # Ensure FTS index exists
    has_fts = _ensure_fts_index(db)
    
    if has_fts:
        # Try FTS5 search first
        results = _fts_search(db, query, args.table, args.limit)
        if results:
            _display_results(results, query, args)
            return
    
    # Fall back to manual search
    results = manual_search(query, args.table, args.limit)
    
    if not results:
        print(f"No results found for '{query}'")
        return
    
    _display_results(results, query, args)


def _fts_search(db, query, table_filter, limit):
    """Search using FTS5 index."""
    try:
        if table_filter:
            cursor = db.execute("""
                SELECT table_name, record_id, content 
                FROM fts_index 
                WHERE fts_index MATCH ? AND table_name = ?
                LIMIT ?
            """, (query, table_filter, limit))
        else:
            cursor = db.execute("""
                SELECT table_name, record_id, content 
                FROM fts_index 
                WHERE fts_index MATCH ?
                LIMIT ?
            """, (query, limit))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'table_name': row[0],
                'record_id': row[1],
                'content': row[2][:200] if row[2] else '',
            })
        return results
    except Exception:
        return None


def _display_results(results, query, args):
    """Display search results."""
    if args.json:
        print_json(results)
        return
    
    # Format results
    print(bold(f"Search results for '{query}' ({len(results)} found)"))
    print()
    
    headers = ['Table', 'ID', 'Match']
    rows = []
    for r in results:
        rows.append([
            r.get('table_name', 'N/A'),
            r.get('record_id', 'N/A')[:16] + '...',
            r.get('content', 'N/A')[:60],
        ])
    
    print_table(headers, rows)


def manual_search(query, table_filter, limit):
    """Manual search fallback when FTS not available."""
    db = get_db()
    results = []
    
    tables = [table_filter] if table_filter else [
        'listings', 'reservations', 'guests', 'owners', 'reviews', 'tasks'
    ]
    
    search_lower = query.lower()
    
    for table in tables:
        try:
            cursor = db.execute(f"SELECT * FROM {table} LIMIT 1000")
            columns = [description[0] for description in cursor.description]
            
            for row in cursor.fetchall():
                row_dict = dict(zip(columns, row))
                row_text = ' '.join(str(v) for v in row_dict.values() if v)
                
                if search_lower in row_text.lower():
                    results.append({
                        'table_name': table,
                        'record_id': row_dict.get('id', 'unknown'),
                        'content': row_text[:200],
                    })
                    
                    if len(results) >= limit:
                        return results
        except:
            pass
    
    return results
