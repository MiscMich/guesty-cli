"""Tests for guesty_cli.core.exit_codes."""
import pytest
from guesty_cli.core.exit_codes import (
    EXIT_SUCCESS, EXIT_ERROR, EXIT_USAGE, EXIT_EMPTY,
    EXIT_AUTH, EXIT_NOT_FOUND, EXIT_PERMISSION,
    EXIT_RATE_LIMIT, EXIT_RETRYABLE, EXIT_CONFIG,
    EXIT_INTERRUPTED, EXIT_CODE_TABLE,
    GuestyExitError, exit_for_error, exit_for_http,
)
from guesty_cli.core.client import AuthError, RateLimitError, GuestyError


class TestExitCodeConstants:
    """Each exit code constant has the expected value."""

    def test_exit_success(self):
        assert EXIT_SUCCESS == 0

    def test_exit_error(self):
        assert EXIT_ERROR == 1

    def test_exit_usage(self):
        assert EXIT_USAGE == 2

    def test_exit_empty(self):
        assert EXIT_EMPTY == 3

    def test_exit_auth(self):
        assert EXIT_AUTH == 4

    def test_exit_not_found(self):
        assert EXIT_NOT_FOUND == 5

    def test_exit_permission(self):
        assert EXIT_PERMISSION == 6

    def test_exit_rate_limit(self):
        assert EXIT_RATE_LIMIT == 7

    def test_exit_retryable(self):
        assert EXIT_RETRYABLE == 8

    def test_exit_config(self):
        assert EXIT_CONFIG == 10

    def test_exit_interrupted(self):
        assert EXIT_INTERRUPTED == 130


class TestExitCodeTable:
    """EXIT_CODE_TABLE has 11 entries and matches the constants."""

    def test_table_has_11_entries(self):
        assert len(EXIT_CODE_TABLE) == 11

    def test_table_codes_match_constants(self):
        codes = {entry["code"] for entry in EXIT_CODE_TABLE}
        expected = {
            EXIT_SUCCESS, EXIT_ERROR, EXIT_USAGE, EXIT_EMPTY,
            EXIT_AUTH, EXIT_NOT_FOUND, EXIT_PERMISSION,
            EXIT_RATE_LIMIT, EXIT_RETRYABLE, EXIT_CONFIG,
            EXIT_INTERRUPTED,
        }
        assert codes == expected

    def test_each_entry_has_required_keys(self):
        for entry in EXIT_CODE_TABLE:
            assert "code" in entry
            assert "name" in entry
            assert "description" in entry


class TestExitForError:
    """exit_for_error() maps exceptions to correct exit codes."""

    def test_auth_error_returns_exit_auth(self):
        err = AuthError("bad credentials")
        assert exit_for_error(err) == EXIT_AUTH

    def test_rate_limit_error_returns_exit_rate_limit(self):
        err = RateLimitError("too many requests")
        assert exit_for_error(err) == EXIT_RATE_LIMIT

    def test_file_not_found_returns_exit_config(self):
        err = FileNotFoundError("config.json not found")
        assert exit_for_error(err) == EXIT_CONFIG

    def test_guesty_error_http_404_returns_exit_not_found(self):
        err = GuestyError("HTTP 404: Not found")
        assert exit_for_error(err) == EXIT_NOT_FOUND

    def test_guesty_error_http_403_returns_exit_permission(self):
        err = GuestyError("HTTP 403: Forbidden")
        assert exit_for_error(err) == EXIT_PERMISSION

    def test_guesty_error_http_500_returns_exit_retryable(self):
        err = GuestyError("HTTP 500: Internal Server Error")
        assert exit_for_error(err) == EXIT_RETRYABLE

    def test_guesty_error_http_429_returns_exit_rate_limit(self):
        # The code checks 'http 429' in msg (case-sensitive) or 'rate limit' in msg_lower
        err = GuestyError("http 429: Too Many Requests")
        assert exit_for_error(err) == EXIT_RATE_LIMIT

    def test_guesty_error_rate_limit_text_returns_exit_rate_limit(self):
        err = GuestyError("Rate limit exceeded")
        assert exit_for_error(err) == EXIT_RATE_LIMIT

    def test_generic_exception_returns_exit_error(self):
        err = Exception("something went wrong")
        assert exit_for_error(err) == EXIT_ERROR

    def test_guesty_exit_error_returns_own_code(self):
        err = GuestyExitError("empty results", code=EXIT_EMPTY)
        assert exit_for_error(err) == EXIT_EMPTY

    def test_keyboard_interrupt_returns_exit_interrupted(self):
        err = KeyboardInterrupt()
        assert exit_for_error(err) == EXIT_INTERRUPTED


class TestExitForHttp:
    """exit_for_http() maps HTTP status codes to exit codes."""

    def test_200_returns_success(self):
        assert exit_for_http(200) == EXIT_SUCCESS

    def test_201_returns_success(self):
        assert exit_for_http(201) == EXIT_SUCCESS

    def test_404_returns_not_found(self):
        assert exit_for_http(404) == EXIT_NOT_FOUND

    def test_429_returns_rate_limit(self):
        assert exit_for_http(429) == EXIT_RATE_LIMIT

    def test_500_returns_retryable(self):
        assert exit_for_http(500) == EXIT_RETRYABLE

    def test_401_returns_auth(self):
        assert exit_for_http(401) == EXIT_AUTH

    def test_403_returns_permission(self):
        assert exit_for_http(403) == EXIT_PERMISSION

    def test_418_returns_error(self):
        assert exit_for_http(418) == EXIT_ERROR


class TestGuestyExitError:
    """GuestyExitError has .code attribute."""

    def test_has_code_attribute(self):
        err = GuestyExitError("test", code=5)
        assert err.code == 5

    def test_default_code_is_exit_error(self):
        err = GuestyExitError("test")
        assert err.code == EXIT_ERROR

    def test_is_exception(self):
        err = GuestyExitError("test message")
        assert isinstance(err, Exception)
        assert str(err) == "test message"
