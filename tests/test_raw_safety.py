"""Safety regression tests for mutating ``guesty raw`` requests."""

from argparse import Namespace
import os
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from guesty_cli.commands import raw
from guesty_cli.core.exit_codes import EXIT_ERROR, EXIT_SUCCESS


MUTATING_METHODS = ("DELETE", "POST", "PATCH", "PUT")
CLI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_cli(*args, home):
    env = os.environ.copy()
    env.update({"HOME": str(home), "NO_COLOR": "1"})
    env.pop("GUESTY_NO_INPUT", None)
    return subprocess.run(
        [sys.executable, "-m", "guesty_cli.main", *args],
        capture_output=True,
        text=True,
        cwd=CLI_DIR,
        env=env,
        timeout=10,
    )


def raw_args(method, *, dry_run=False, force=False, no_input=False):
    return Namespace(
        method=method,
        path="/v1/example/123",
        data='{"enabled": true}' if method != "DELETE" else None,
        data_file=None,
        params='{"source": "test"}',
        header=[],
        accept=None,
        content_type=None,
        output=None,
        dry_run=dry_run,
        force=force,
        no_input=no_input,
    )


@pytest.mark.parametrize("method", MUTATING_METHODS)
def test_dry_run_mutation_never_constructs_client_or_calls_network(method, monkeypatch, capsys):
    client_factory = MagicMock(side_effect=AssertionError("client must not be constructed"))
    request = MagicMock(side_effect=AssertionError("network must not be called"))
    monkeypatch.setattr(raw, "GuestyClient", client_factory)
    monkeypatch.setattr(raw, "_do_request", request)

    with pytest.raises(SystemExit) as exc:
        raw.run_raw(raw_args(method, dry_run=True))

    assert exc.value.code == EXIT_SUCCESS
    assert "DRY RUN" in capsys.readouterr().out
    client_factory.assert_not_called()
    request.assert_not_called()


@pytest.mark.parametrize("method", MUTATING_METHODS)
def test_noninteractive_mutation_without_force_fails_closed(method, monkeypatch, capsys):
    client_factory = MagicMock(side_effect=AssertionError("client must not be constructed"))
    request = MagicMock(side_effect=AssertionError("network must not be called"))
    monkeypatch.setattr(raw, "GuestyClient", client_factory)
    monkeypatch.setattr(raw, "_do_request", request)

    with pytest.raises(SystemExit) as exc:
        raw.run_raw(raw_args(method, no_input=True))

    assert exc.value.code == EXIT_ERROR
    assert "--force" in capsys.readouterr().err
    client_factory.assert_not_called()
    request.assert_not_called()


def test_noninteractive_environment_mutation_without_force_fails_closed(monkeypatch):
    monkeypatch.setenv("GUESTY_NO_INPUT", "1")
    monkeypatch.setattr(raw, "GuestyClient", MagicMock(side_effect=AssertionError("no client")))
    monkeypatch.setattr(raw, "_do_request", MagicMock(side_effect=AssertionError("no network")))

    with pytest.raises(SystemExit) as exc:
        raw.run_raw(raw_args("DELETE"))

    assert exc.value.code == EXIT_ERROR


def test_interactive_mutation_requires_positive_confirmation(monkeypatch):
    monkeypatch.setattr("builtins.input", MagicMock(return_value="no"))
    monkeypatch.setattr(raw, "GuestyClient", MagicMock(side_effect=AssertionError("no client")))
    monkeypatch.setattr(raw, "_do_request", MagicMock(side_effect=AssertionError("no network")))

    with pytest.raises(SystemExit) as exc:
        raw.run_raw(raw_args("PATCH"))

    assert exc.value.code == EXIT_ERROR


@pytest.mark.parametrize("authorization", ["force", "confirmation"])
def test_explicitly_authorized_mutation_calls_request(authorization, monkeypatch):
    args = raw_args(
        "POST",
        force=authorization == "force",
        no_input=authorization == "force",
    )
    if authorization == "confirmation":
        monkeypatch.setattr("builtins.input", MagicMock(return_value="yes"))

    client = MagicMock()
    monkeypatch.setattr(raw, "GuestyClient", MagicMock(return_value=client))
    monkeypatch.setattr(raw, "_build_url", MagicMock(return_value="https://example.invalid/v1/example/123"))
    request = MagicMock(return_value=(b"{}", "application/json", 200))
    monkeypatch.setattr(raw, "_do_request", request)

    with pytest.raises(SystemExit) as exc:
        raw.run_raw(args)

    assert exc.value.code == EXIT_SUCCESS
    request.assert_called_once()


@pytest.mark.parametrize("method", MUTATING_METHODS)
def test_cli_global_dry_run_syntax_is_network_free(method, tmp_path):
    result = run_cli("--dry-run", "raw", method, "/v1/example/123", home=tmp_path)

    assert result.returncode == EXIT_SUCCESS
    assert "DRY RUN" in result.stdout
    assert "No authentication or network request was attempted" in result.stdout


@pytest.mark.parametrize("method", MUTATING_METHODS)
def test_cli_noninteractive_syntax_fails_closed_before_auth(method, tmp_path):
    result = run_cli("--no-input", "raw", method, "/v1/example/123", home=tmp_path)

    assert result.returncode == EXIT_ERROR
    assert "--force" in result.stderr
    assert "credential" not in (result.stdout + result.stderr).lower()
