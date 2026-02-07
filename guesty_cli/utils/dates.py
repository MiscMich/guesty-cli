"""Date utilities for guesty-cli.

Parsing and formatting dates with natural language support.
"""

import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple


def parse_date(s: str) -> date:
    """Parse a date string into a date object.
    
    Accepts:
        - YYYY-MM-DD (ISO format)
        - "today"
        - "yesterday"
        - "last-week"
        - "last-month"
        - "last-year"
        - "next-week"
        - "next-month"
    
    Args:
        s: Date string to parse.
        
    Returns:
        date: Parsed date.
        
    Raises:
        ValueError: If the string cannot be parsed.
    """
    if not s:
        raise ValueError("Empty date string")
    
    s = s.lower().strip()
    today = date.today()
    
    # Handle special keywords
    if s == "today":
        return today
    
    if s == "yesterday":
        return today - timedelta(days=1)
    
    if s == "tomorrow":
        return today + timedelta(days=1)
    
    if s == "last-week":
        return today - timedelta(weeks=1)
    
    if s == "next-week":
        return today + timedelta(weeks=1)
    
    if s == "last-month":
        # Subtract one month
        if today.month == 1:
            return today.replace(year=today.year - 1, month=12)
        else:
            # Handle day overflow (e.g., March 31 -> Feb 28)
            try:
                return today.replace(month=today.month - 1)
            except ValueError:
                # Day doesn't exist in previous month
                return today.replace(month=today.month - 1, day=1)
    
    if s == "next-month":
        # Add one month
        if today.month == 12:
            return today.replace(year=today.year + 1, month=1)
        else:
            try:
                return today.replace(month=today.month + 1)
            except ValueError:
                return today.replace(month=today.month + 1, day=1)
    
    if s == "last-year":
        return today.replace(year=today.year - 1)
    
    if s == "next-year":
        return today.replace(year=today.year + 1)
    
    # Try ISO format YYYY-MM-DD
    iso_match = re.match(r"^\d{4}-\d{2}-\d{2}$", s)
    if iso_match:
        try:
            return date.fromisoformat(s)
        except ValueError:
            pass
    
    # Try alternative formats
    # MM/DD/YYYY
    us_match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if us_match:
        month, day, year = int(us_match.group(1)), int(us_match.group(2)), int(us_match.group(3))
        return date(year, month, day)
    
    # DD/MM/YYYY
    eu_match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if eu_match:
        day, month, year = int(eu_match.group(1)), int(eu_match.group(2)), int(eu_match.group(3))
        return date(year, month, day)
    
    raise ValueError(f"Cannot parse date: {s}")


def format_date_range(from_date: date, to_date: date) -> str:
    """Format a date range as a human-readable string.
    
    Args:
        from_date: Start date.
        to_date: End date.
        
    Returns:
        str: Formatted date range.
    """
    if from_date == to_date:
        return from_date.strftime("%B %d, %Y")
    
    # Same month and year
    if from_date.year == to_date.year and from_date.month == to_date.month:
        return f"{from_date.strftime('%B %d')} - {to_date.strftime('%d, %Y')}"
    
    # Same year
    if from_date.year == to_date.year:
        return f"{from_date.strftime('%B %d')} - {to_date.strftime('%B %d, %Y')}"
    
    # Different years
    return f"{from_date.strftime('%B %d, %Y')} - {to_date.strftime('%B %d, %Y')}"


def days_between(date1: date, date2: date) -> int:
    """Calculate the number of days between two dates.
    
    Args:
        date1: First date.
        date2: Second date.
        
    Returns:
        int: Absolute number of days between dates.
    """
    return abs((date2 - date1).days)


def start_of_week(d: date = None) -> date:
    """Get the start of the week (Monday) for a date.
    
    Args:
        d: Date (defaults to today).
        
    Returns:
        date: Monday of the week.
    """
    if d is None:
        d = date.today()
    return d - timedelta(days=d.weekday())


def end_of_week(d: date = None) -> date:
    """Get the end of the week (Sunday) for a date.
    
    Args:
        d: Date (defaults to today).
        
    Returns:
        date: Sunday of the week.
    """
    if d is None:
        d = date.today()
    return d + timedelta(days=6 - d.weekday())


def start_of_month(d: date = None) -> date:
    """Get the first day of the month.
    
    Args:
        d: Date (defaults to today).
        
    Returns:
        date: First day of the month.
    """
    if d is None:
        d = date.today()
    return d.replace(day=1)


def end_of_month(d: date = None) -> date:
    """Get the last day of the month.
    
    Args:
        d: Date (defaults to today).
        
    Returns:
        date: Last day of the month.
    """
    if d is None:
        d = date.today()
    
    # Find first day of next month, subtract one day
    if d.month == 12:
        next_month = d.replace(year=d.year + 1, month=1, day=1)
    else:
        next_month = d.replace(month=d.month + 1, day=1)
    
    return next_month - timedelta(days=1)


def get_checkin_checkout_dates(check_in: Optional[str] = None, check_out: Optional[str] = None) -> Tuple[date, date]:
    """Get check-in and check-out dates with defaults.
    
    Defaults to today and tomorrow if not provided.
    
    Args:
        check_in: Check-in date string (optional).
        check_out: Check-out date string (optional).
        
    Returns:
        Tuple of (check_in_date, check_out_date).
    """
    today = date.today()
    tomorrow = today + timedelta(days=1)
    
    if check_in:
        cin = parse_date(check_in)
    else:
        cin = today
    
    if check_out:
        cout = parse_date(check_out)
    else:
        # Default to 1 night stay
        cout = cin + timedelta(days=1)
    
    return cin, cout


def iso_date(d: date) -> str:
    """Format a date as ISO string (YYYY-MM-DD).
    
    Args:
        d: Date to format.
        
    Returns:
        str: ISO date string.
    """
    return d.isoformat()


def parse_iso_datetime(iso_string: str) -> Optional[datetime]:
    """Parse an ISO datetime string.
    
    Args:
        iso_string: ISO 8601 datetime string.
        
    Returns:
        datetime or None if parsing fails.
    """
    if not iso_string:
        return None
    
    try:
        # Handle Z suffix
        iso_string = iso_string.replace("Z", "+00:00")
        return datetime.fromisoformat(iso_string)
    except (ValueError, TypeError):
        return None


def format_relative_time(dt: datetime) -> str:
    """Format a datetime as relative time (e.g., "2 hours ago").
    
    Args:
        dt: Datetime to format.
        
    Returns:
        str: Relative time string.
    """
    if dt is None:
        return "-"
    
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    diff = now - dt
    
    if diff.days > 365:
        years = diff.days // 365
        return f"{years} year{'s' if years > 1 else ''} ago"
    elif diff.days > 30:
        months = diff.days // 30
        return f"{months} month{'s' if months > 1 else ''} ago"
    elif diff.days > 0:
        return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    elif diff.seconds >= 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif diff.seconds >= 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    else:
        return "just now"