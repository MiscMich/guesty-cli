"""Resolution utilities for resolving IDs from names/nicknames."""


def resolve_listing(db, identifier):
    """Resolve listing by nickname or ID.
    
    Args:
        db: SQLite database connection
        identifier: Listing ID or nickname (partial match allowed)
        
    Returns:
        dict with 'id' and 'nickname' or None if not found
    """
    # Try exact ID match first
    row = db.execute(
        "SELECT id, nickname FROM listings WHERE id = ?",
        (identifier,)
    ).fetchone()
    if row:
        return dict(row)
    
    # Try partial nickname match (case-insensitive)
    row = db.execute(
        "SELECT id, nickname FROM listings WHERE LOWER(nickname) LIKE LOWER(?)",
        (f'%{identifier}%',)
    ).fetchone()
    if row:
        return dict(row)
    
    return None


def resolve_owner(db, identifier):
    """Resolve owner by name or ID.

    Args:
        db: SQLite database connection
        identifier: Owner ID or name (partial match allowed)

    Returns:
        dict with 'id' and 'fullName' or None if not found
    """
    # Try exact ID match first
    row = db.execute(
        "SELECT id, full_name, first_name, last_name FROM owners WHERE id = ?",
        (identifier,)
    ).fetchone()
    if row:
        full_name = row.get('full_name') or f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
        return {
            'id': row['id'],
            'fullName': full_name,
            'full_name': full_name,
        }

    # Try partial name match (case-insensitive) - search full_name
    try:
        row = db.execute(
            "SELECT id, full_name, first_name, last_name FROM owners WHERE LOWER(full_name) LIKE LOWER(?)",
            (f'%{identifier}%',)
        ).fetchone()
        if row:
            full_name = row.get('full_name') or f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
            return {
                'id': row['id'],
                'fullName': full_name,
                'full_name': full_name,
            }
    except Exception:
        pass

    # Try search in raw_data as fallback
    try:
        cursor = db.execute("SELECT id, full_name, raw_data FROM owners WHERE raw_data LIKE ?", (f'%{identifier}%',))
        for row in cursor.fetchall():
            raw_data = row['raw_data']
            if raw_data:
                import json
                try:
                    data = json.loads(raw_data)
                    full_name = data.get('fullName') or data.get('full_name', '')
                    if identifier.lower() in full_name.lower():
                        return {
                            'id': row['id'],
                            'fullName': full_name,
                            'full_name': full_name,
                        }
                except json.JSONDecodeError:
                    continue
            elif row['full_name'] and identifier.lower() in row['full_name'].lower():
                return {
                    'id': row['id'],
                    'fullName': row['full_name'],
                    'full_name': row['full_name'],
                }
    except Exception:
        pass

    return None
