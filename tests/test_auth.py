"""Regression tests for authentication commands."""
import json
from types import SimpleNamespace
from unittest.mock import patch

from guesty_cli.commands.auth import run_auth_export


def test_no_input_alone_does_not_export_client_secret(monkeypatch, capsys):
    """Non-interactive mode must not imply consent to disclose secrets."""
    monkeypatch.setenv("GUESTY_NO_INPUT", "1")
    args = SimpleNamespace(include_secrets=False, out="-")
    config = {
        "account_name": "Example Account",
        "client_id": "example-client-id",
        "client_secret": "example-client-secret",
    }

    with patch("guesty_cli.commands.auth.load_config", return_value=config):
        run_auth_export(args)

    captured = capsys.readouterr()
    assert "client_secret" not in json.loads(captured.out)
    assert "contains client_secret" not in captured.err
