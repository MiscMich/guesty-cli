"""Output formatting utilities for guesty-cli.

Blue Terminal Aesthetic - Cyberpunk vibes, professional and beautiful.
"""

import csv
import json
import os
import shutil
import sys
from datetime import datetime, timedelta
from typing import Any, Optional, List, Dict


# Check for NO_COLOR environment variable
NO_COLOR = os.environ.get("NO_COLOR", "").strip() or not sys.stdout.isatty()


def _supports_color() -> bool:
    """Check if terminal supports colors."""
    return not NO_COLOR


# ============================================================================
# BLUE THEME PALETTE
# ============================================================================

BLUE = '\033[38;5;33m'          # Primary blue
BRIGHT_BLUE = '\033[38;5;39m'   # Bright/accent blue
CYAN = '\033[38;5;87m'          # Cyan for highlights
LIGHT_BLUE = '\033[38;5;117m'   # Light blue for secondary
DARK_BLUE = '\033[38;5;24m'     # Dark blue for backgrounds
WHITE = '\033[97m'              # White for text
DIM = '\033[2m'                 # Dim for secondary text
GREEN = '\033[38;5;48m'         # Teal-green for success/money
RED = '\033[38;5;196m'          # Red for errors
YELLOW = '\033[38;5;220m'       # Yellow/amber for warnings
BOLD = '\033[1m'
RESET = '\033[0m'


# ============================================================================
# COLOR HELPER FUNCTIONS
# ============================================================================

def _c(text: str, color: str) -> str:
    """Apply color to text if terminal supports it."""
    return f"{color}{text}{RESET}" if _supports_color() else text


def bold(text: str) -> str:
    """Bold text."""
    return _c(text, BOLD)


def dim(text: str) -> str:
    """Dim/faint text."""
    return _c(text, DIM)


def cyan(text: str) -> str:
    """Cyan text."""
    return _c(text, CYAN)


def green(text: str) -> str:
    """Green text."""
    return _c(text, GREEN)


def red(text: str) -> str:
    """Red text."""
    return _c(text, RED)


def yellow(text: str) -> str:
    """Yellow text."""
    return _c(text, YELLOW)


def blue(text: str) -> str:
    """Blue text."""
    return _c(text, BLUE)


def bright_blue(text: str) -> str:
    """Bright blue text."""
    return _c(text, BRIGHT_BLUE)


def light_blue(text: str) -> str:
    """Light blue text."""
    return _c(text, LIGHT_BLUE)


def white(text: str) -> str:
    """White text."""
    return _c(text, WHITE)


# ============================================================================
# TERMINAL UTILITIES
# ============================================================================

def get_terminal_width() -> int:
    """Get terminal width, defaulting to 80."""
    try:
        return shutil.get_terminal_size().columns
    except:
        return 80


def truncate(text: Any, max_len: int) -> str:
    """Truncate text with ellipsis (…).
    
    Args:
        text: Text to truncate.
        max_len: Maximum length.
        
    Returns:
        str: Truncated text.
    """
    if text is None:
        return ""
    
    s = str(text)
    if len(s) <= max_len:
        return s
    
    if max_len <= 1:
        return s[:max_len]
    
    return s[:max_len - 1] + "…"


# ============================================================================
# BANNER
# ============================================================================

def print_banner(version: str = "1.0.0") -> None:
    """Print the Guesty CLI ASCII art banner with gradient blue effect."""
    banner_lines = [
        "  ██████╗ ██╗   ██╗███████╗███████╗████████╗██╗   ██╗",
        " ██╔════╝ ██║   ██║██╔════╝██╔════╝╚══██╔══╝╚██╗ ██╔╝",
        " ██║  ███╗██║   ██║█████╗  ███████╗   ██║    ╚████╔╝ ",
        " ██║   ██║██║   ██║██╔══╝  ╚════██║   ██║     ╚██╔╝  ",
        " ╚██████╔╝╚██████╔╝███████╗███████║   ██║      ██║   ",
        "  ╚═════╝  ╚═════╝ ╚══════╝╚══════╝   ╚═╝      ╚═╝   ",
    ]
    
    # Gradient from darker to brighter blue
    colors = [DARK_BLUE, BLUE, BLUE, BRIGHT_BLUE, BRIGHT_BLUE, CYAN]
    
    print()
    for line, color in zip(banner_lines, colors):
        print(_c(line, color))
    
    # Tagline
    tagline = "    The missing CLI for Guesty PMS"
    print(_c(tagline, DIM))
    
    # Version
    version_text = f"    v{version}"
    print(_c(version_text, LIGHT_BLUE))
    print()


# ============================================================================
# HEADERS
# ============================================================================

def print_header(text: str, width: Optional[int] = None, emoji: str = "⚡") -> None:
    """Print a sleek blue-themed boxed header.
    
    Args:
        text: Header text.
        width: Optional width (defaults to terminal width, max 60).
        emoji: Emoji prefix (default: ⚡).
    """
    if width is None:
        width = min(get_terminal_width(), 60)
    
    text_len = len(text)
    full_text = f"{emoji} {text}"
    full_text_len = len(full_text)
    
    if full_text_len + 4 > width:
        text = truncate(text, width - 6)
        full_text = f"{emoji} {text}"
        full_text_len = len(full_text)
    
    padding = width - full_text_len - 2
    
    top_border = "╔" + "═" * (width - 2) + "╗"
    middle = "║ " + full_text + " " * (padding - 1) + "║"
    bottom_border = "╚" + "═" * (width - 2) + "╝"
    
    print()
    print(_c(top_border, BLUE))
    print(_c(middle, BLUE))
    print(_c(bottom_border, BLUE))
    print()


# ============================================================================
# MONEY FORMATTING
# ============================================================================

def format_money(amount: Any, currency: str = "USD") -> str:
    """Format a monetary amount with color coding.
    
    Args:
        amount: Numeric amount.
        currency: Currency code (default USD).
        
    Returns:
        str: Formatted money string (e.g., '$1,234.56' in green).
    """
    if amount is None:
        return _c("-", DIM)
    
    try:
        num = float(amount)
        currency_symbols = {
            "USD": "$",
            "EUR": "€",
            "GBP": "£",
            "CAD": "C$",
            "AUD": "A$",
            "JPY": "¥",
        }
        currency = currency or "USD"
        symbol = currency_symbols.get(currency.upper(), currency.upper() + " ")
        
        if num < 0:
            return _c(f"-{symbol}{abs(num):,.2f}", RED)
        else:
            return _c(f"{symbol}{num:,.2f}", GREEN)
    except (ValueError, TypeError):
        return str(amount)


def format_money_short(amount: Any, currency: str = "USD") -> str:
    """Format money in compact form with abbreviations for large amounts.
    
    Args:
        amount: Numeric amount.
        currency: Currency code (default USD).
        
    Returns:
        str: Formatted compact money string (e.g., '$1.24M').
    """
    if amount is None:
        return _c("-", DIM)
    
    try:
        num = float(amount)
        currency_symbols = {
            "USD": "$",
            "EUR": "€",
            "GBP": "£",
            "CAD": "C$",
            "AUD": "A$",
            "JPY": "¥",
        }
        symbol = currency_symbols.get(currency.upper(), "$")
        
        abs_num = abs(num)
        if abs_num >= 1_000_000:
            formatted = f"{symbol}{abs_num/1_000_000:.2f}M"
        elif abs_num >= 1_000:
            formatted = f"{symbol}{abs_num/1_000:.1f}K"
        else:
            formatted = f"{symbol}{abs_num:,.2f}"
        
        if num < 0:
            return _c(f"-{formatted}", RED)
        else:
            return _c(formatted, BRIGHT_BLUE)
    except (ValueError, TypeError):
        return str(amount)


def format_money_plain(amount: Any, currency: str = "USD") -> str:
    """Format money without color codes (for tables)."""
    if amount is None:
        return "-"
    
    try:
        num = float(amount)
        currency_symbols = {
            "USD": "$",
            "EUR": "€",
            "GBP": "£",
            "CAD": "C$",
            "AUD": "A$",
            "JPY": "¥",
        }
        symbol = currency_symbols.get(currency.upper(), "$")
        
        if num < 0:
            return f"-{symbol}{abs(num):,.2f}"
        else:
            return f"{symbol}{num:,.2f}"
    except (ValueError, TypeError):
        return str(amount)


# ============================================================================
# DATE FORMATTING
# ============================================================================

def format_date(iso_string: str) -> str:
    """Format an ISO date string to human-readable with relative dates.
    
    Args:
        iso_string: ISO 8601 date string.
        
    Returns:
        str: Human-readable date with color coding.
    """
    if not iso_string:
        return _c("-", DIM)
    
    try:
        # Parse the date
        dt_str = iso_string.replace("Z", "+00:00")
        if "T" in dt_str:
            dt = datetime.fromisoformat(dt_str)
            date_part = dt.date()
        else:
            date_part = datetime.strptime(dt_str[:10], "%Y-%m-%d").date()
        
        today = datetime.now().date()
        delta = (date_part - today).days
        
        # Relative dates
        if delta == 0:
            return _c("Today", BRIGHT_BLUE)
        elif delta == -1:
            return _c("Yesterday", DIM)
        elif delta == 1:
            return _c("Tomorrow", CYAN)
        elif delta < -1 and delta > -7:
            return _c(f"{-delta} days ago", DIM)
        elif delta > 1 and delta < 7:
            return _c(f"In {delta} days", CYAN)
        else:
            # Standard format
            formatted = date_part.strftime("%b %d")
            if delta < 0:
                return _c(formatted, DIM)  # Past
            else:
                return _c(formatted, CYAN)  # Future
    except (ValueError, TypeError):
        return str(iso_string)


def format_date_range(from_date: str, to_date: str) -> str:
    """Format a date range.
    
    Args:
        from_date: Start date (ISO format).
        to_date: End date (ISO format).
        
    Returns:
        str: Formatted date range.
    """
    if not from_date or not to_date:
        return _c("-", DIM)
    
    try:
        from_dt = from_date[:10]
        to_dt = to_date[:10]
        return f"{from_dt} to {to_dt}"
    except:
        return f"{from_date} to {to_date}"


def format_datetime(iso_string: str) -> str:
    """Format an ISO datetime string."""
    if not iso_string:
        return _c("-", DIM)
    
    try:
        dt = iso_string.replace("Z", "+00:00")
        dt = datetime.fromisoformat(dt)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return str(iso_string)


# ============================================================================
# STATUS COLORS
# ============================================================================

def colorize_status(status: str) -> str:
    """Color-code status values."""
    status_lower = str(status).lower()
    
    if status_lower in ('confirmed', 'active', 'approved', 'completed', 'paid'):
        return _c("● " + status, GREEN)
    elif status_lower in ('canceled', 'cancelled', 'declined', 'error', 'inactive'):
        return _c("● " + status, RED)
    elif status_lower in ('inquiry', 'pending', 'hold', 'waiting', 'request'):
        return _c("● " + status, YELLOW)
    else:
        return _c("● " + status, LIGHT_BLUE)


# ============================================================================
# TABLES
# ============================================================================

def print_table(headers: list, rows: list, max_widths: Optional[list] = None) -> None:
    """Print a beautifully formatted table with auto-sizing columns.
    
    Args:
        headers: Column headers.
        rows: List of row tuples/lists.
        max_widths: Optional maximum widths for each column.
    """
    if not rows:
        print(dim("No data to display."))
        return
    
    term_width = get_terminal_width()
    num_cols = len(headers)
    
    # Minimum column widths for specific column types
    min_widths = {
        'guest': 18,
        'name': 18,
        'code': 13,
        'listing': 16,
        'date': 12,
        'status': 10,
        'source': 8,
        'price': 10,
        'id': 12,
    }
    
    # Convert all cells to strings
    str_rows = []
    for row in rows:
        str_row = []
        for cell in row:
            if cell is None:
                str_row.append("")
            else:
                str_row.append(str(cell))
        str_rows.append(str_row)
    
    # Calculate column widths based on content
    col_widths = []
    for i in range(num_cols):
        header_str = str(headers[i]) if headers[i] else ""
        header_len = len(header_str)
        
        max_data_len = max((len(row[i]) for row in str_rows if i < len(row)), default=0)
        
        # Apply minimum widths based on header name
        header_lower = header_str.lower()
        min_w = 5
        for key, mw in min_widths.items():
            if key in header_lower:
                min_w = max(min_w, mw)
                break
        
        col_widths.append(max(header_len, max_data_len, min_w))
    
    # Apply max_widths if provided
    if max_widths:
        for i, max_w in enumerate(max_widths):
            if i < len(col_widths) and max_w:
                col_widths[i] = min(col_widths[i], max_w)
    
    # Check if table fits in terminal
    # Calculate: borders + padding + separators
    total_width = sum(col_widths) + (3 * num_cols) + 1
    
    # Use at least 60% of terminal width before truncating
    min_desired_width = int(term_width * 0.6)
    
    # If terminal is wide (>120 cols), let columns breathe more
    if term_width > 120:
        # Add extra space to columns that need it
        for i in range(num_cols):
            header_lower = str(headers[i]).lower() if i < len(headers) else ""
            # Give more space to name/guest columns
            if any(k in header_lower for k in ['name', 'guest', 'title']):
                if col_widths[i] < 25:
                    col_widths[i] = min(25, col_widths[i] + 5)
        # Recalculate total
        total_width = sum(col_widths) + (3 * num_cols) + 1
    
    if total_width > term_width:
        # Need to truncate some columns from the right
        excess = total_width - term_width
        
        for i in range(num_cols - 1, -1, -1):
            if excess <= 0:
                break
            header_lower = str(headers[i]).lower() if i < len(headers) else ""
            # Get minimum for this column
            min_for_col = 5
            for key, mw in min_widths.items():
                if key in header_lower:
                    min_for_col = max(min_for_col, mw)
                    break
            available = col_widths[i] - min_for_col
            if available > 0:
                shrink = min(available, excess)
                col_widths[i] -= shrink
                excess -= shrink
    
    # Helper to colorize cell content
    def colorize_cell(cell: str, col_idx: int, is_header: bool = False) -> str:
        if is_header:
            return _c(cell, CYAN + BOLD)
        
        cell_lower = cell.lower()
        header_lower = str(headers[col_idx]).lower() if col_idx < len(headers) else ""
        
        # Status columns
        if any(k in header_lower for k in ['status', 'state']):
            return colorize_status(cell)
        
        # Money columns
        if any(k in header_lower for k in ['price', 'amount', 'revenue', 'payout', 'money', '$']):
            try:
                # Remove currency symbols and parse
                val_str = cell.replace('$', '').replace(',', '').replace('€', '').replace('£', '')
                if val_str and val_str != '-':
                    val = float(val_str)
                    if val < 0:
                        return _c(cell, RED)
                    else:
                        return _c(cell, GREEN)
            except:
                pass
        
        # Date columns
        if any(k in header_lower for k in ['date', 'created', 'updated']):
            return _c(cell, LIGHT_BLUE)
        
        return cell
    
    # Build table
    def make_horizontal(left: str, mid: str, right: str) -> str:
        parts = []
        for w in col_widths:
            parts.append("─" * (w + 2))
        return left + mid.join(parts) + right
    
    top_border = make_horizontal("┌", "┬", "┐")
    mid_border = make_horizontal("├", "┼", "┤")
    bot_border = make_horizontal("└", "┴", "┘")
    
    print()
    print(_c(top_border, BLUE))
    
    # Header row
    header_cells = []
    for i, h in enumerate(headers):
        if i < len(col_widths):
            cell_text = truncate(str(h), col_widths[i])
            colored = colorize_cell(cell_text, i, is_header=True)
            padded = f" {colored}" + " " * (col_widths[i] - len(cell_text))
            header_cells.append(padded)
    print(_c("│", BLUE) + _c("│", BLUE).join(header_cells) + _c("│", BLUE))
    
    print(_c(mid_border, BLUE))
    
    # Data rows with alternating dim
    for row_idx, row in enumerate(str_rows):
        row_cells = []
        row_color = DIM if row_idx % 2 == 1 else ""
        
        for i, cell in enumerate(row):
            if i < len(col_widths):
                cell_text = truncate(cell, col_widths[i])
                colored = colorize_cell(cell_text, i)
                
                # Right-align numbers
                header_lower = str(headers[i]).lower() if i < len(headers) else ""
                is_numeric = any(k in header_lower for k in ['price', 'amount', 'revenue', 'payout', 'count', 'guests', 'bedrooms', 'bathrooms', 'nights'])
                
                if is_numeric:
                    padded = " " * (col_widths[i] - len(cell_text) + 1) + colored + " "
                else:
                    padded = f" {colored}" + " " * (col_widths[i] - len(cell_text))
                
                if row_color and not any(k in header_lower for k in ['status', 'price', 'amount']):
                    # Apply dim to non-colored cells on alternating rows
                    padded = _c(padded, row_color)
                
                row_cells.append(padded)
        
        print(_c("│", BLUE) + _c("│", BLUE).join(row_cells) + _c("│", BLUE))
    
    print(_c(bot_border, BLUE))
    
    # Row count footer
    row_count = len(rows)
    footer_text = f"── {row_count} row{'s' if row_count != 1 else ''} ──"
    print(_c(footer_text, DIM))
    print()


# ============================================================================
# CARDS
# ============================================================================

def print_card(title: str, fields: Dict[str, Any], icon: str = "🏠") -> None:
    """Print a premium-looking key-value card.
    
    Args:
        title: Card title.
        fields: Dictionary of field names to values.
        icon: Icon emoji prefix (default: 🏠).
    """
    print()
    
    # Title line
    title_text = f"{icon} {title}"
    title_line = f"┌─ {title_text} "
    padding = 50 - len(title_text) - 4
    if padding < 0:
        padding = 5
    title_line += "─" * padding
    print(_c(title_line, BLUE))
    print(_c("│", BLUE))
    
    # Find max key length for alignment
    max_key_len = max((len(str(k)) for k in fields.keys()), default=0)
    
    # Group small fields on same line
    single_line_fields = ['bedrooms', 'bathrooms', 'guests', 'max guests', 'beds']
    grouped = []
    current_group = []
    
    for key in fields.keys():
        key_lower = str(key).lower()
        if any(f in key_lower for f in single_line_fields):
            current_group.append(key)
            if len(current_group) >= 3:
                grouped.append(('group', current_group))
                current_group = []
        else:
            if current_group:
                grouped.append(('group', current_group))
                current_group = []
            grouped.append(('single', key))
    
    if current_group:
        grouped.append(('group', current_group))
    
    # Print fields
    printed_keys = set()
    
    for group_type, item in grouped:
        if group_type == 'single':
            key = item
            value = fields[key]
            printed_keys.add(key)
            
            key_str = str(key).ljust(max_key_len)
            
            # Special formatting for status
            if 'status' in str(key).lower():
                value_str = colorize_status(str(value))
            # Format money
            elif isinstance(value, (int, float)) and any(x in str(key).lower() for x in ['price', 'revenue', 'fee']):
                value_str = format_money_plain(value)
            else:
                value_str = str(value) if value is not None else "-"
            
            line = f"  {key_str}:  {value_str}"
            print(_c("│", BLUE) + line)
        
        else:  # group
            parts = []
            for key in item:
                if key not in printed_keys:
                    printed_keys.add(key)
                    value = fields[key]
                    parts.append(f"{key}: {value}")
            
            if parts:
                line = "  │  ".join(parts)
                print(_c("│", BLUE) + "  " + line)
    
    # Print any remaining fields
    for key, value in fields.items():
        if key not in printed_keys:
            key_str = str(key).ljust(max_key_len)
            if 'status' in str(key).lower():
                value_str = colorize_status(str(value))
            elif isinstance(value, (int, float)) and any(x in str(key).lower() for x in ['price', 'revenue', 'fee']):
                value_str = format_money_plain(value)
            else:
                value_str = str(value) if value is not None else "-"
            line = f"  {key_str}:  {value_str}"
            print(_c("│", BLUE) + line)
    
    print(_c("│", BLUE))
    print(_c("└" + "─" * 48, BLUE))
    print()


# ============================================================================
# STATS BOXES
# ============================================================================

def print_stats(stats: List[Dict[str, Any]]) -> None:
    """Print stat boxes for dashboard.
    
    Args:
        stats: List of dicts with 'value' and 'label' keys.
               Optional 'icon' key for emoji.
    """
    if not stats:
        return
    
    boxes = []
    for stat in stats:
        value = stat.get('value', 0)
        label = stat.get('label', '')
        icon = stat.get('icon', '')
        
        # Format value
        if isinstance(value, (int, float)) and value >= 1000000:
            value_str = f"${value/1000000:.2f}M"
        elif isinstance(value, (int, float)) and value >= 1000:
            value_str = f"{value:,}"
        else:
            value_str = str(value)
        
        # Calculate box width
        content_width = max(len(value_str), len(label), 8)
        
        value_line = f"│{value_str:^{content_width + 2}}│"
        label_line = f"│{label:^{content_width + 2}}│"
        
        top = f"┌{'─' * (content_width + 2)}┐"
        bot = f"└{'─' * (content_width + 2)}┘"
        
        box = {
            'top': _c(top, BLUE),
            'value': _c("│ ", BLUE) + _c(value_str, BRIGHT_BLUE + BOLD) + _c(" │", BLUE),
            'label': _c("│ ", BLUE) + _c(label, DIM) + _c(" │", BLUE),
            'bot': _c(bot, BLUE),
            'width': content_width + 4
        }
        boxes.append(box)
    
    # Print boxes side by side
    print()
    
    # Top borders
    print("  ".join(box['top'] for box in boxes))
    
    # Value lines
    print("  ".join(box['value'] for box in boxes))
    
    # Label lines
    print("  ".join(box['label'] for box in boxes))
    
    # Bottom borders
    print("  ".join(box['bot'] for box in boxes))
    print()


# ============================================================================
# SPARKLINE CHARTS
# ============================================================================

def print_sparkline(label: str, values: List[float], total_label: str = "") -> None:
    """Print a sparkline chart for data trends.
    
    Args:
        label: Label for the sparkline (e.g., "Revenue (12mo)").
        values: List of numeric values.
        total_label: Optional total value to display.
    """
    if not values:
        return
    
    spark_chars = "▁▂▃▄▅▆▇█"
    
    min_val = min(values)
    max_val = max(values)
    val_range = max_val - min_val
    
    if val_range == 0:
        bars = "▁" * len(values)
    else:
        bars = ""
        for v in values:
            idx = int(((v - min_val) / val_range) * (len(spark_chars) - 1))
            bars += spark_chars[idx]
    
    line = f"{label}: {_c(bars, CYAN)}"
    if total_label:
        line += f"  {total_label}"
    
    print(line)


# ============================================================================
# RATING STARS
# ============================================================================

def print_rating(rating: float, max_rating: float = 5.0) -> str:
    """Return a colored star rating string.
    
    Args:
        rating: The rating value.
        max_rating: Maximum possible rating (default 5.0).
        
    Returns:
        str: Star rating string.
    """
    if rating is None:
        return _c("☆☆☆☆☆", DIM)
    
    try:
        rating = float(rating)
        normalized = (rating / max_rating) * 5  # Normalize to 5 stars
        full_stars = int(normalized)
        has_half = (normalized - full_stars) >= 0.5
        
        stars = "★" * full_stars
        if has_half:
            stars += "½"
        stars += "☆" * (5 - full_stars - (1 if has_half else 0))
        
        # Color based on rating
        if rating >= 4.5:
            return _c(stars, BRIGHT_BLUE) + _c(f" ({rating})", LIGHT_BLUE)
        elif rating >= 3.5:
            return _c(stars, CYAN) + _c(f" ({rating})", LIGHT_BLUE)
        elif rating >= 2.5:
            return _c(stars, YELLOW) + _c(f" ({rating})", LIGHT_BLUE)
        else:
            return _c(stars, DIM) + _c(f" ({rating})", LIGHT_BLUE)
    except (ValueError, TypeError):
        return str(rating)


def format_rating(rating: float, max_rating: float = 5.0) -> str:
    """Format rating as colored stars (alias for print_rating)."""
    return print_rating(rating, max_rating)


# ============================================================================
# PROGRESS SPINNER
# ============================================================================

_spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_spinner_idx = 0


def print_progress(message: str, current: int, total: int) -> None:
    """Print a progress spinner with percentage.
    
    Args:
        message: Status message (e.g., "Syncing reservations...").
        current: Current progress number.
        total: Total items.
    """
    global _spinner_idx
    
    spinner = _c(_spinner_chars[_spinner_idx], CYAN)
    _spinner_idx = (_spinner_idx + 1) % len(_spinner_chars)
    
    pct = (current / total * 100) if total > 0 else 0
    
    line = f"{spinner} {message} {current:,}/{total:,} ({pct:.0f}%)"
    
    # Clear line and print
    sys.stdout.write("\r" + " " * 80 + "\r")
    sys.stdout.write(line)
    sys.stdout.flush()


def finish_progress(message: str = "Done!") -> None:
    """Finish the progress display with a success message."""
    sys.stdout.write("\r" + " " * 80 + "\r")
    print(f"{_c('✓', GREEN)} {message}")


# ============================================================================
# DATA FORMAT OUTPUT
# ============================================================================

def print_json(data: Any) -> None:
    """Print data as pretty JSON.
    
    Args:
        data: Data to print.
    """
    print(json.dumps(data, indent=2, default=str))


def print_csv(headers: list, rows: list) -> None:
    """Print data as CSV.
    
    Args:
        headers: Column headers.
        rows: List of row values.
    """
    writer = csv.writer(sys.stdout)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([str(cell) if cell is not None else "" for cell in row])


# ============================================================================
# MESSAGE HELPERS
# ============================================================================

def print_success(message: str) -> None:
    """Print a success message."""
    print(f"{_c('✓', GREEN)} {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"{_c('✗', RED)} {message}", file=sys.stderr)


def print_warning(message: str) -> None:
    """Print a warning message."""
    print(f"{_c('⚠', YELLOW)} {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    print(f"{_c('ℹ', LIGHT_BLUE)} {message}")


# ============================================================================
# LEGACY COMPATIBILITY
# ============================================================================

def magenta(text: str) -> str:
    """Magenta text (for compatibility - returns bright blue instead)."""
    return _c(text, BRIGHT_BLUE)
