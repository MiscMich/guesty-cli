"""Tests for guesty_cli.core.client."""
import json
import os
import time
import pytest
from io import BytesIO
from unittest.mock import patch, MagicMock, PropertyMock
from urllib.error import HTTPError

from guesty_cli.core.client import (
    GuestyClient, GuestyError, AuthError, RateLimitError,
)
from guesty_cli.core.circuit_breaker import CircuitBreakerOpen


def make_mock_response(data, status=200, headers=None):
    """Create a mock HTTP response."""
    body = json.dumps(data).encode('utf-8')
    mock = MagicMock()
    mock.read.return_value = body
    mock.status = status
    mock.headers = headers or {}
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def make_http_error(code, reason="Error", body=None, headers=None):
    """Create a mock HTTPError."""
    body_data = json.dumps(body or {"message": reason}).encode('utf-8')
    err = HTTPError(
        url="https://open-api.guesty.com/v1/test",
        code=code,
        msg=reason,
        hdrs=headers or {},
        fp=BytesIO(body_data),
    )
    err.headers = headers or {}
    return err


MOCK_CONFIG = {
    "client_id": "test-id",
    "client_secret": "test-secret",
    "api_base_url": "https://open-api.guesty.com",
    "token": "",
    "token_expires_at": "",
    "tokens_generated_24h": [],
}


class TestGuestyClientInit:
    """GuestyClient initializes with config."""

    def test_init_with_config(self):
        client = GuestyClient(config=MOCK_CONFIG)
        assert client.config == MOCK_CONFIG
        assert client.base_url == "https://open-api.guesty.com"

    @patch('guesty_cli.core.client.load_config', return_value=MOCK_CONFIG)
    def test_init_default_config(self, mock_load):
        client = GuestyClient()
        mock_load.assert_called_once()
        assert client.config == MOCK_CONFIG


class TestGetToken:
    """get_token() returns correct token based on context."""

    def test_direct_token_from_env(self):
        os.environ['_GUESTY_ACCESS_TOKEN'] = 'env-token-123'
        client = GuestyClient(config=MOCK_CONFIG)
        assert client.get_token() == 'env-token-123'
        del os.environ['_GUESTY_ACCESS_TOKEN']

    @patch('guesty_cli.core.client.get_cached_token')
    def test_cached_token_returned_when_valid(self, mock_cached):
        from datetime import datetime, timezone, timedelta
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        mock_cached.return_value = ("cached-token", future)

        client = GuestyClient(config=MOCK_CONFIG)
        client._direct_token = None
        token = client.get_token()
        assert token == "cached-token"


class TestMakeRequest:
    """_make_request() retries and error handling."""

    @patch('guesty_cli.core.client.urlopen')
    def test_retries_on_429(self, mock_urlopen):
        # First call: 429, second call: success
        error_429 = make_http_error(429, "Rate Limited", headers={"Retry-After": "1"})
        success_resp = make_mock_response({"ok": True})

        mock_urlopen.side_effect = [error_429, success_resp]

        client = GuestyClient(config=MOCK_CONFIG)
        client._direct_token = "test-token"

        result = client._make_request("GET", "https://open-api.guesty.com/v1/test")
        assert result == {"ok": True}
        assert mock_urlopen.call_count == 2

    @patch('guesty_cli.core.client.urlopen')
    @patch('guesty_cli.core.client.clear_token_cache')
    def test_retries_on_401_with_fresh_token(self, mock_clear, mock_urlopen):
        error_401 = make_http_error(401, "Unauthorized")
        success_resp = make_mock_response({"ok": True})

        mock_urlopen.side_effect = [error_401, success_resp]

        client = GuestyClient(config=MOCK_CONFIG)
        client._direct_token = "test-token"

        result = client._make_request("GET", "https://open-api.guesty.com/v1/test")
        assert result == {"ok": True}
        mock_clear.assert_called()

    @patch('guesty_cli.core.client.urlopen')
    def test_raises_rate_limit_after_max_retries(self, mock_urlopen):
        error_429 = make_http_error(429, "Rate Limited", headers={"Retry-After": "0"})
        mock_urlopen.side_effect = [error_429] * 4  # max_retries + 1

        client = GuestyClient(config=MOCK_CONFIG)
        client._direct_token = "test-token"

        with pytest.raises(RateLimitError):
            client._make_request("GET", "https://open-api.guesty.com/v1/test")


class TestParseResponse:
    """_parse_response() handles different formats."""

    def test_results_format(self):
        client = GuestyClient(config=MOCK_CONFIG)
        data = {"results": [{"id": "1"}, {"id": "2"}], "count": 2}
        result = client._parse_response(data)
        assert result == [{"id": "1"}, {"id": "2"}]

    def test_data_format(self):
        client = GuestyClient(config=MOCK_CONFIG)
        data = {"data": [{"id": "1"}], "limit": 25}
        result = client._parse_response(data)
        assert result == [{"id": "1"}]

    def test_raw_list_format(self):
        client = GuestyClient(config=MOCK_CONFIG)
        data = [{"id": "1"}, {"id": "2"}]
        result = client._parse_response(data)
        assert result == [{"id": "1"}, {"id": "2"}]

    def test_single_object(self):
        client = GuestyClient(config=MOCK_CONFIG)
        data = {"id": "1", "name": "Test"}
        result = client._parse_response(data)
        assert result == {"id": "1", "name": "Test"}


class TestApiGetAll:
    """api_get_all() pagination and loop detection."""

    @patch.object(GuestyClient, '_make_request')
    def test_detects_pagination_loop(self, mock_request):
        # Return results that look like a full page but skip doesn't advance
        mock_request.return_value = {"results": [{"id": str(i)} for i in range(100)]}

        client = GuestyClient(config=MOCK_CONFIG)
        client._direct_token = "test-token"

        # The first page works fine (skip=0), second page (skip=100) works,
        # but we'll simulate a loop by making parse return 100 results each time
        # which means it never stops. max_pages will catch it.
        with pytest.raises(GuestyError, match="Pagination exceeded max pages"):
            client.api_get_all("listings", max_pages=3)

    @patch.object(GuestyClient, '_make_request')
    def test_respects_max_pages(self, mock_request):
        mock_request.return_value = {"results": [{"id": "1"}] * 100}

        client = GuestyClient(config=MOCK_CONFIG)
        client._direct_token = "test-token"

        with pytest.raises(GuestyError, match="Pagination exceeded max pages"):
            client.api_get_all("listings", limit=100, max_pages=2)


class TestCircuitBreakerIntegration:
    """Circuit breaker integrates with client."""

    @patch('guesty_cli.core.client.urlopen')
    def test_five_500s_opens_circuit(self, mock_urlopen):
        error_500 = make_http_error(500, "Internal Server Error")
        mock_urlopen.side_effect = error_500

        client = GuestyClient(config=MOCK_CONFIG)
        client._direct_token = "test-token"

        for _ in range(5):
            with pytest.raises(GuestyError):
                client._make_request("GET", "https://open-api.guesty.com/v1/test", auth=False)

        assert client._circuit_breaker.state == 'open'

    @patch('guesty_cli.core.client.urlopen')
    def test_success_after_failures_resets(self, mock_urlopen):
        error_500 = make_http_error(500, "Internal Server Error")

        client = GuestyClient(config=MOCK_CONFIG)
        client._direct_token = "test-token"

        # Record some failures (not enough to open)
        for _ in range(3):
            mock_urlopen.side_effect = error_500
            with pytest.raises(GuestyError):
                client._make_request("GET", "https://open-api.guesty.com/v1/test", auth=False)

        assert client._circuit_breaker.failure_count == 3

        # Now succeed
        mock_urlopen.side_effect = None
        mock_urlopen.return_value = make_mock_response({"ok": True})

        result = client._make_request("GET", "https://open-api.guesty.com/v1/test", auth=False)
        assert result == {"ok": True}
        assert client._circuit_breaker.failure_count == 0
