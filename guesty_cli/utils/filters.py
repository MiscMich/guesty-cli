"""Guesty filter builder utilities.

Builds filter JSON for Guesty API queries.
"""

import json
from datetime import date, datetime
from typing import Any, List, Optional, Tuple, Union


def build_filter(field: str, operator: str, value: Any) -> dict:
    """Build a single filter condition.
    
    Args:
        field: Field name to filter on.
        operator: Filter operator ($eq, $ne, $gt, $lt, $gte, $lte, 
                 $between, $in, $contains, $not, $notcontains).
        value: Value to filter by.
        
    Returns:
        dict: Filter condition dict.
        
    Example:
        >>> build_filter("status", "$eq", "confirmed")
        {"field": "status", "operator": "$eq", "value": "confirmed"}
    """
    # Handle date values
    if isinstance(value, (date, datetime)):
        value = value.isoformat()
    
    return {
        "field": field,
        "operator": operator,
        "value": value,
    }


def build_filters(*filter_tuples: Tuple[str, str, Any]) -> str:
    """Build multiple filters and return as JSON string.
    
    Args:
        *filter_tuples: Tuples of (field, operator, value).
        
    Returns:
        str: JSON string for API query parameter.
        
    Example:
        >>> build_filters(
        ...     ("status", "$eq", "confirmed"),
        ...     ("checkIn", "$gte", "2024-01-01")
        ... )
        '[{"field": "status", "operator": "$eq", "value": "confirmed"}, ...]'
    """
    filters = []
    for field, operator, value in filter_tuples:
        filters.append(build_filter(field, operator, value))
    
    return json.dumps(filters)


def build_filters_dict(filters: List[dict]) -> str:
    """Build filters from a list of filter dicts.
    
    Args:
        filters: List of filter dictionaries.
        
    Returns:
        str: JSON string for API query parameter.
    """
    return json.dumps(filters)


def date_filter(
    field: str,
    from_date: Optional[Union[str, date, datetime]] = None,
    to_date: Optional[Union[str, date, datetime]] = None,
) -> dict:
    """Build a date range filter.
    
    Args:
        field: Date field name (e.g., "checkIn", "checkOut", "createdAt").
        from_date: Start date (inclusive).
        to_date: End date (inclusive).
        
    Returns:
        dict: Filter condition.
        
    Raises:
        ValueError: If neither from_date nor to_date is provided.
    """
    if from_date is None and to_date is None:
        raise ValueError("At least one of from_date or to_date must be provided")
    
    # Convert dates to ISO strings
    if isinstance(from_date, (date, datetime)):
        from_date = from_date.isoformat()
    if isinstance(to_date, (date, datetime)):
        to_date = to_date.isoformat()
    
    if from_date and to_date:
        return build_filter(field, "$between", {"from": from_date, "to": to_date})
    elif from_date:
        return build_filter(field, "$gte", from_date)
    else:
        return build_filter(field, "$lte", to_date)


def status_filter(status: Union[str, List[str]]) -> dict:
    """Build a status filter.
    
    Args:
        status: Status value(s) to filter by.
        
    Returns:
        dict: Filter condition.
    """
    if isinstance(status, list):
        return build_filter("status", "$in", status)
    return build_filter("status", "$eq", status)


def source_filter(source: Union[str, List[str]]) -> dict:
    """Build a source filter for reservations.
    
    Args:
        source: Source value(s) (e.g., "airbnb", "bookingcom", "direct").
        
    Returns:
        dict: Filter condition.
    """
    if isinstance(source, list):
        return build_filter("source", "$in", source)
    return build_filter("source", "$eq", source)


def listing_filter(listing_id: Union[str, List[str]]) -> dict:
    """Build a listing filter.
    
    Args:
        listing_id: Listing ID(s) to filter by.
        
    Returns:
        dict: Filter condition.
    """
    if isinstance(listing_id, list):
        return build_filter("listingId", "$in", listing_id)
    return build_filter("listingId", "$eq", listing_id)


def guest_filter(guest_id: str) -> dict:
    """Build a guest filter.
    
    Args:
        guest_id: Guest ID to filter by.
        
    Returns:
        dict: Filter condition.
    """
    return build_filter("guestId", "$eq", guest_id)


def text_search_filter(query: str, fields: Optional[List[str]] = None) -> List[dict]:
    """Build a text search filter across multiple fields.
    
    Note: This uses $contains operator. For true full-text search,
    use the local SQLite database.
    
    Args:
        query: Search query.
        fields: Fields to search (default: ["guestName", "confirmationCode"]).
        
    Returns:
        List of filter conditions (use with OR logic).
    """
    if fields is None:
        fields = ["guestName", "confirmationCode"]
    
    filters = []
    for field in fields:
        filters.append(build_filter(field, "$contains", query))
    
    return filters


# Common filter presets

def today_checkins() -> List[dict]:
    """Filter for reservations checking in today.
    
    Returns:
        List of filter conditions.
    """
    from datetime import date
    today = date.today().isoformat()
    return [
        build_filter("checkIn", "$eq", today),
        build_filter("status", "$in", ["confirmed", "checked_in"]),
    ]


def today_checkouts() -> List[dict]:
    """Filter for reservations checking out today.
    
    Returns:
        List of filter conditions.
    """
    from datetime import date
    today = date.today().isoformat()
    return [
        build_filter("checkOut", "$eq", today),
        build_filter("status", "$in", ["confirmed", "checked_in"]),
    ]


def confirmed_only() -> dict:
    """Filter for confirmed reservations only.
    
    Returns:
        dict: Filter condition.
    """
    return status_filter(["confirmed", "checked_in", "checked_out"])


def upcoming_arrivals(days: int = 7) -> List[dict]:
    """Filter for upcoming arrivals in next N days.
    
    Args:
        days: Number of days to look ahead.
        
    Returns:
        List of filter conditions.
    """
    from datetime import date, timedelta
    today = date.today()
    future = today + timedelta(days=days)
    
    return [
        date_filter("checkIn", today.isoformat(), future.isoformat()),
        confirmed_only(),
    ]


def upcoming_departures(days: int = 7) -> List[dict]:
    """Filter for upcoming departures in next N days.
    
    Args:
        days: Number of days to look ahead.
        
    Returns:
        List of filter conditions.
    """
    from datetime import date, timedelta
    today = date.today()
    future = today + timedelta(days=days)
    
    return [
        date_filter("checkOut", today.isoformat(), future.isoformat()),
        confirmed_only(),
    ]


def upcoming_week() -> List[dict]:
    """Filter for the upcoming week.
    
    Returns:
        List of filter conditions.
    """
    return upcoming_arrivals(7)


def current_month() -> List[dict]:
    """Filter for current month.
    
    Returns:
        List of filter conditions.
    """
    from datetime import date
    today = date.today()
    start = today.replace(day=1).isoformat()
    
    # End of month
    if today.month == 12:
        end = today.replace(year=today.year + 1, month=1, day=1)
    else:
        end = today.replace(month=today.month + 1, day=1)
    end = end.isoformat()
    
    return [
        date_filter("checkIn", start, end),
        confirmed_only(),
    ]


def past_reservations(days: int = 30) -> List[dict]:
    """Filter for past reservations.
    
    Args:
        days: Look back this many days.
        
    Returns:
        List of filter conditions.
    """
    from datetime import date, timedelta
    today = date.today()
    past = today - timedelta(days=days)
    
    return [
        date_filter("checkOut", past.isoformat(), today.isoformat()),
        confirmed_only(),
    ]


def pending_requests() -> List[dict]:
    """Filter for pending reservation requests.
    
    Returns:
        List of filter conditions.
    """
    return [
        build_filter("status", "$eq", "pending"),
    ]


def cancelled_reservations() -> dict:
    """Filter for cancelled reservations.
    
    Returns:
        dict: Filter condition.
    """
    return build_filter("status", "$eq", "cancelled")


def direct_bookings() -> dict:
    """Filter for direct bookings only.
    
    Returns:
        dict: Filter condition.
    """
    return build_filter("source", "$eq", "direct")


def channel_bookings(channels: Optional[List[str]] = None) -> dict:
    """Filter for channel bookings (non-direct).
    
    Args:
        channels: Specific channels to include (default: all non-direct).
        
    Returns:
        dict: Filter condition.
    """
    if channels:
        return build_filter("source", "$in", channels)
    # Exclude direct bookings
    return build_filter("source", "$ne", "direct")