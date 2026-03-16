"""Tests for guesty_cli.core.secrets."""
import pytest
from unittest.mock import patch, MagicMock

from guesty_cli.core.secrets import (
    is_keyring_available, store_secret, get_secret, get_storage_info,
    SERVICE_NAME,
)


class TestIsKeyringAvailable:
    """is_keyring_available() behavior."""

    @patch('guesty_cli.core.secrets._keyring_available', False)
    def test_returns_false_when_not_installed(self):
        assert is_keyring_available() is False


class TestStoreSecret:
    """store_secret() behavior."""

    @patch('guesty_cli.core.secrets.is_keyring_available', return_value=False)
    def test_returns_file_when_keyring_unavailable(self, mock_avail):
        result = store_secret("client_secret", "my-secret")
        assert result == "file"

    @patch('guesty_cli.core.secrets.is_keyring_available', return_value=True)
    @patch('guesty_cli.core.secrets._keyring')
    def test_returns_keychain_when_available(self, mock_keyring, mock_avail):
        mock_keyring.set_password = MagicMock()
        result = store_secret("client_secret", "my-secret")
        assert result == "keychain"
        mock_keyring.set_password.assert_called_once_with(SERVICE_NAME, "client_secret", "my-secret")

    @patch('guesty_cli.core.secrets.is_keyring_available', return_value=True)
    @patch('guesty_cli.core.secrets._keyring')
    def test_fallback_on_keyring_exception(self, mock_keyring, mock_avail):
        mock_keyring.set_password.side_effect = Exception("keychain error")
        result = store_secret("client_secret", "my-secret")
        assert result == "file"


class TestGetSecret:
    """get_secret() behavior."""

    @patch('guesty_cli.core.secrets.is_keyring_available', return_value=False)
    def test_returns_fallback_when_keyring_unavailable(self, mock_avail):
        result = get_secret("client_secret", fallback="default-val")
        assert result == "default-val"

    @patch('guesty_cli.core.secrets.is_keyring_available', return_value=False)
    def test_returns_none_when_no_fallback(self, mock_avail):
        result = get_secret("client_secret")
        assert result is None

    @patch('guesty_cli.core.secrets.is_keyring_available', return_value=True)
    @patch('guesty_cli.core.secrets._keyring')
    def test_returns_stored_value_when_available(self, mock_keyring, mock_avail):
        mock_keyring.get_password.return_value = "stored-secret"
        result = get_secret("client_secret")
        assert result == "stored-secret"

    @patch('guesty_cli.core.secrets.is_keyring_available', return_value=True)
    @patch('guesty_cli.core.secrets._keyring')
    def test_fallback_on_keyring_get_exception(self, mock_keyring, mock_avail):
        mock_keyring.get_password.side_effect = Exception("read error")
        result = get_secret("client_secret", fallback="fallback-val")
        assert result == "fallback-val"


class TestGetStorageInfo:
    """get_storage_info() returns dict with expected keys."""

    def test_returns_dict_with_expected_keys(self):
        info = get_storage_info()
        assert "keyring_available" in info
        assert "keyring_functional" in info
        assert "backend" in info

    @patch('guesty_cli.core.secrets._keyring_available', False)
    @patch('guesty_cli.core.secrets.is_keyring_available', return_value=False)
    def test_file_backend_when_no_keyring(self, mock_avail):
        info = get_storage_info()
        assert info["backend"] == "file"
