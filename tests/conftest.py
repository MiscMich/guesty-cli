"""Shared fixtures for guesty-cli tests."""
import json
import os
import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.fixture
def tmp_config_dir(tmp_path):
    """Create a temporary config directory."""
    config_dir = tmp_path / ".guesty-cli"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def mock_config(tmp_config_dir):
    """Create a mock config file."""
    config = {
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
        "account_name": "Test Account",
        "api_base_url": "https://open-api.guesty.com",
        "db_path": str(tmp_config_dir / "guesty.db"),
        "default_format": "table",
        "token": "",
        "token_expires_at": "",
        "tokens_generated_24h": [],
    }
    config_path = tmp_config_dir / "config.json"
    config_path.write_text(json.dumps(config))
    return config


@pytest.fixture
def reset_output_mode():
    """Reset output mode to human after each test."""
    from guesty_cli.core.output import set_output_mode, OutputMode
    set_output_mode(OutputMode.HUMAN)
    yield
    set_output_mode(OutputMode.HUMAN)


@pytest.fixture(autouse=True)
def clean_env():
    """Clean up environment variables after each test."""
    env_keys = ['_GUESTY_ACCESS_TOKEN', 'GUESTY_NO_INPUT', 'GUESTY_AUTO_JSON',
                'GUESTY_CLIENT_ID', 'GUESTY_CLIENT_SECRET', 'GUESTY_DEBUG', 'NO_COLOR']
    original = {k: os.environ.get(k) for k in env_keys}
    for key in env_keys:
        os.environ.pop(key, None)
    yield
    for k, v in original.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
