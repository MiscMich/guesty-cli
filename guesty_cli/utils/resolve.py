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
        "SELECT id, fullName FROM owners WHERE id = ?",
        (identifier,)
    ).fetchone()
    if row:
        return dict(row)
    
    # Try partial name match (case-insensitive)
    row = db.execute(
        "SELECT id, fullName FROM owners WHERE LOWER(fullName) LIKE LOWER(?)",
        (f'%{identifier}%',)
    ).fetchone()
    if row:
        return dict(row)
    
    return None
