"""Stable exit codes for guesty-cli.

Inspired by steipete/gogcli's semantic exit code system.
Agents and scripts can rely on these codes to distinguish error categories
without parsing human-readable messages.
"""

# ── Exit codes ──────────────────────────────────────────────────────────
EXIT_SUCCESS = 0
EXIT_ERROR = 1          # Generic/unknown error
EXIT_USAGE = 2          # Bad arguments / parse error
EXIT_EMPTY = 3          # Empty results (no data found)
EXIT_AUTH = 4           # Auth required / credentials missing
EXIT_NOT_FOUND = 5      # Resource not found (listing, reservation, etc.)
EXIT_PERMISSION = 6     # Permission denied
EXIT_RATE_LIMIT = 7     # Rate limited
EXIT_RETRYABLE = 8      # Transient/retryable error (network, 5xx)
EXIT_CONFIG = 10        # Config file missing or corrupt
EXIT_INTERRUPTED = 130  # Ctrl-C / SIGINT

# Machine-readable table used by `guesty agent exit-codes` and `guesty schema`
EXIT_CODE_TABLE = [
    {"code": EXIT_SUCCESS, "name": "SUCCESS", "description": "Operation completed successfully"},
    {"code": EXIT_ERROR, "name": "ERROR", "description": "Generic/unknown error"},
    {"code": EXIT_USAGE, "name": "USAGE", "description": "Invalid arguments or command syntax"},
    {"code": EXIT_EMPTY, "name": "EMPTY", "description": "No results found"},
    {"code": EXIT_AUTH, "name": "AUTH", "description": "Authentication required or credentials missing"},
    {"code": EXIT_NOT_FOUND, "name": "NOT_FOUND", "description": "Resource not found"},
    {"code": EXIT_PERMISSION, "name": "PERMISSION", "description": "Permission denied"},
    {"code": EXIT_RATE_LIMIT, "name": "RATE_LIMIT", "description": "API rate limit exceeded"},
    {"code": EXIT_RETRYABLE, "name": "RETRYABLE", "description": "Transient error (network, server 5xx)"},
    {"code": EXIT_CONFIG, "name": "CONFIG", "description": "Configuration file missing or corrupt"},
    {"code": EXIT_INTERRUPTED, "name": "INTERRUPTED", "description": "Interrupted (Ctrl-C / SIGINT)"},
]


class GuestyExitError(Exception):
    """Exception that carries a semantic exit code."""

    def __init__(self, message: str, code: int = EXIT_ERROR):
        super().__init__(message)
        self.code = code


def exit_for_error(err: Exception) -> int:
    """Map an exception to the appropriate exit code.

    Recognises:
      - GuestyExitError  (direct .code)
      - AuthError        -> EXIT_AUTH
      - RateLimitError   -> EXIT_RATE_LIMIT
      - GuestyError      -> EXIT_ERROR  (generic API error)
      - FileNotFoundError -> EXIT_CONFIG
      - KeyboardInterrupt -> EXIT_INTERRUPTED
      - Anything else    -> EXIT_ERROR
    """
    # Our own typed exit errors
    if isinstance(err, GuestyExitError):
        return err.code

    # Lazy imports to avoid circular deps
    try:
        from guesty_cli.core.client import AuthError, RateLimitError, GuestyError
    except ImportError:
        return EXIT_ERROR

    if isinstance(err, AuthError):
        return EXIT_AUTH
    if isinstance(err, RateLimitError):
        return EXIT_RATE_LIMIT
    if isinstance(err, GuestyError):
        # Inspect message for common patterns
        msg = str(err)
        msg_lower = msg.lower()
        if 'http 404' in msg or 'not found' in msg_lower:
            return EXIT_NOT_FOUND
        if 'http 403' in msg or 'forbidden' in msg_lower:
            return EXIT_PERMISSION
        if 'http 429' in msg or 'rate limit' in msg_lower:
            return EXIT_RATE_LIMIT
        if msg.startswith('HTTP 5') or '500' in msg or '502' in msg or '503' in msg or '504' in msg:
            return EXIT_RETRYABLE
        if 'http 400' in msg_lower and ('invalid_client' in msg_lower or 'credential' in msg_lower or 'token' in msg_lower):
            return EXIT_AUTH
        return EXIT_ERROR
    if isinstance(err, FileNotFoundError):
        return EXIT_CONFIG
    if isinstance(err, KeyboardInterrupt):
        return EXIT_INTERRUPTED

    return EXIT_ERROR


def exit_for_http(status_code: int) -> int:
    """Map an HTTP status code to the appropriate exit code."""
    if 200 <= status_code < 300:
        return EXIT_SUCCESS
    if status_code == 401:
        return EXIT_AUTH
    if status_code == 403:
        return EXIT_PERMISSION
    if status_code == 404:
        return EXIT_NOT_FOUND
    if status_code == 429:
        return EXIT_RATE_LIMIT
    if status_code >= 500:
        return EXIT_RETRYABLE
    return EXIT_ERROR
