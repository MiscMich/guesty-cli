"""Tests for guesty_cli.core.config."""
import json
import os
import stat
import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from guesty_cli.core.config import (
    DEFAULT_CONFIG, load_config, save_config,
    get_cached_token, update_token_cache,
    count_tokens_last_24h, get_config_dir, get_config_path,
)


@pytest.fixture
def mock_config_paths(tmp_path, monkeypatch):
    """Override config paths to use tmp directory."""
    config_dir = tmp_path / ".guesty-cli"
    config_path = config_dir / "config.json"
    monkeypatch.setattr('guesty_cli.core.config.get_config_dir', lambda: config_dir)
    monkeypatch.setattr('guesty_cli.core.config.get_config_path', lambda: config_path)
    return config_dir, config_path


class TestLoadConfig:
    """load_config() creates, reads, and merges config."""

    def test_creates_default_when_no_file(self, mock_config_paths):
        config_dir, config_path = mock_config_paths
        config = load_config()
        assert config_path.exists()
        assert config["api_base_url"] == "https://open-api.guesty.com"
        assert config["client_id"] == ""

    def test_reads_existing_config(self, mock_config_paths):
        config_dir, config_path = mock_config_paths
        config_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "client_id": "my-id",
            "client_secret": "my-secret",
            "api_base_url": "https://open-api.guesty.com",
        }
        config_path.write_text(json.dumps(data))

        with patch('guesty_cli.core.secrets.get_secret', return_value=None):
            config = load_config()
        assert config["client_id"] == "my-id"

    def test_merges_defaults_for_new_fields(self, mock_config_paths):
        config_dir, config_path = mock_config_paths
        config_dir.mkdir(parents=True, exist_ok=True)
        # Old config missing newer fields
        data = {"client_id": "my-id"}
        config_path.write_text(json.dumps(data))

        with patch('guesty_cli.core.secrets.get_secret', return_value=None):
            config = load_config()
        assert config["client_id"] == "my-id"
        assert "default_format" in config
        assert config["default_format"] == "table"

    def test_handles_corrupt_json(self, mock_config_paths):
        config_dir, config_path = mock_config_paths
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text("not valid json {{{")

        config = load_config()
        # Should return defaults
        assert config["api_base_url"] == "https://open-api.guesty.com"

    def test_env_var_overrides(self, mock_config_paths):
        config_dir, config_path = mock_config_paths
        config_dir.mkdir(parents=True, exist_ok=True)
        data = {"client_id": "file-id", "client_secret": "file-secret"}
        config_path.write_text(json.dumps(data))

        os.environ['GUESTY_CLIENT_ID'] = 'env-id'
        os.environ['GUESTY_CLIENT_SECRET'] = 'env-secret'

        with patch('guesty_cli.core.secrets.get_secret', return_value=None):
            config = load_config()
        assert config['client_id'] == 'env-id'
        assert config['client_secret'] == 'env-secret'


class TestSaveConfig:
    """save_config() writes valid JSON with restricted permissions."""

    def test_writes_valid_json(self, mock_config_paths):
        config_dir, config_path = mock_config_paths
        data = {"client_id": "test", "token": "secret"}
        save_config(data)
        assert config_path.exists()
        loaded = json.loads(config_path.read_text())
        assert loaded["client_id"] == "test"

    def test_sets_file_permissions(self, mock_config_paths):
        config_dir, config_path = mock_config_paths
        save_config({"test": True})
        mode = config_path.stat().st_mode & 0o777
        assert mode == 0o600


class TestGetCachedToken:
    """get_cached_token() returns token or empty tuple."""

    def test_returns_empty_when_no_token(self, mock_config_paths):
        config_dir, config_path = mock_config_paths
        save_config(DEFAULT_CONFIG.copy())
        with patch('guesty_cli.core.secrets.get_secret', return_value=None):
            token, expires = get_cached_token()
        assert token == ""
        assert expires == ""

    def test_returns_token_when_cached(self, mock_config_paths):
        config_dir, config_path = mock_config_paths
        config = DEFAULT_CONFIG.copy()
        config["token"] = "my-token"
        config["token_expires_at"] = "2026-12-31T00:00:00+00:00"
        save_config(config)
        with patch('guesty_cli.core.secrets.get_secret', return_value=None):
            token, expires = get_cached_token()
        assert token == "my-token"
        assert expires == "2026-12-31T00:00:00+00:00"


class TestUpdateTokenCache:
    """update_token_cache() stores token."""

    def test_stores_token(self, mock_config_paths):
        config_dir, config_path = mock_config_paths
        save_config(DEFAULT_CONFIG.copy())

        with patch('guesty_cli.core.secrets.store_secret', return_value='file'):
            with patch('guesty_cli.core.secrets.get_secret', return_value=None):
                update_token_cache("new-token", "2026-12-31T00:00:00+00:00")
                token, expires = get_cached_token()
        assert token == "new-token"


class TestCountTokensLast24h:
    """count_tokens_last_24h() counts recent and excludes old tokens."""

    def test_counts_recent_tokens(self, mock_config_paths):
        config_dir, config_path = mock_config_paths
        now = datetime.now(timezone.utc)
        recent = [
            (now - timedelta(hours=1)).isoformat(),
            (now - timedelta(hours=2)).isoformat(),
        ]
        config = DEFAULT_CONFIG.copy()
        config["tokens_generated_24h"] = recent
        save_config(config)

        with patch('guesty_cli.core.secrets.get_secret', return_value=None):
            count = count_tokens_last_24h()
        assert count == 2

    def test_excludes_old_tokens(self, mock_config_paths):
        config_dir, config_path = mock_config_paths
        now = datetime.now(timezone.utc)
        timestamps = [
            (now - timedelta(hours=1)).isoformat(),
            (now - timedelta(hours=25)).isoformat(),  # old
            (now - timedelta(hours=48)).isoformat(),  # old
        ]
        config = DEFAULT_CONFIG.copy()
        config["tokens_generated_24h"] = timestamps
        save_config(config)

        with patch('guesty_cli.core.secrets.get_secret', return_value=None):
            count = count_tokens_last_24h()
        assert count == 1
