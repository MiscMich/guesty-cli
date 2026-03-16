"""Tests for guesty_cli.main entry point and argument parsing."""
import json
import os
import subprocess
import sys
import pytest
from unittest.mock import patch, MagicMock

from guesty_cli.core.exit_codes import EXIT_INTERRUPTED, EXIT_ERROR
from guesty_cli.core.output import OutputMode

CLI_MODULE = "guesty_cli.main"
CLI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_cli(*args, env_extra=None):
    """Run guesty-cli as subprocess and return (returncode, stdout, stderr)."""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    # Ensure NO_COLOR so output is stable
    env['NO_COLOR'] = '1'
    result = subprocess.run(
        [sys.executable, "-m", CLI_MODULE] + list(args),
        capture_output=True, text=True, cwd=CLI_DIR,
        env=env, timeout=10,
    )
    return result.returncode, result.stdout, result.stderr


class TestVersion:
    """--version prints version string."""

    def test_version_flag(self):
        code, stdout, stderr = run_cli("--version")
        assert code == 0
        assert "guesty-cli v" in stdout


class TestHelp:
    """--help prints usage."""

    def test_help_flag(self):
        code, stdout, stderr = run_cli("--help")
        assert code == 0
        assert "usage:" in stdout.lower() or "guesty" in stdout.lower()


class TestJsonFlag:
    """--json flag sets output mode to JSON."""

    def test_json_flag_with_schema(self):
        code, stdout, stderr = run_cli("--json", "schema")
        assert code == 0
        parsed = json.loads(stdout)
        assert "schema_version" in parsed


class TestPlainFlag:
    """--plain flag sets output mode to PLAIN."""

    def test_plain_flag_with_exit_codes(self):
        code, stdout, stderr = run_cli("--plain", "exit-codes")
        assert code == 0
        lines = stdout.strip().split('\n')
        # TSV format: each line has tabs
        assert '\t' in lines[0]


class TestSelectFlag:
    """--select flag parses comma-separated fields."""

    def test_select_with_json(self):
        # schema command outputs structured JSON we can test --select against
        code, stdout, stderr = run_cli("--json", "--select", "schema_version,name", "schema")
        assert code == 0
        parsed = json.loads(stdout)
        # select only applies to list/dict data through emit, schema prints directly
        # so this just verifies it doesn't crash
        assert isinstance(parsed, dict)


class TestAccessToken:
    """--access-token flag sets environment variable."""

    def test_access_token_flag(self):
        # Use schema command (doesn't need API) to test flag doesn't crash
        code, stdout, stderr = run_cli("--access-token", "test-token-123", "schema")
        assert code == 0


class TestNoInputFlag:
    """--no-input flag sets environment variable."""

    def test_no_input_flag(self):
        code, stdout, stderr = run_cli("--no-input", "schema")
        assert code == 0


class TestAutoJson:
    """GUESTY_AUTO_JSON=1 with piped stdout sets JSON mode."""

    def test_auto_json_env(self):
        # When run as subprocess, stdout is piped (not a tty)
        code, stdout, stderr = run_cli("exit-codes", env_extra={"GUESTY_AUTO_JSON": "1"})
        assert code == 0
        # Should output JSON since stdout is piped
        parsed = json.loads(stdout)
        assert isinstance(parsed, list)


class TestUnknownCommand:
    """Unknown command prints error and exits 1."""

    def test_unknown_command(self):
        code, stdout, stderr = run_cli("nonexistent-command-xyz")
        assert code != 0


class TestErrorExitCodes:
    """Errors use semantic exit codes."""

    def test_keyboard_interrupt_exit_code(self):
        # We can't easily send SIGINT in subprocess, but we can test the
        # exit_for_error mapping is used by the main module
        from guesty_cli.core.exit_codes import exit_for_error
        assert exit_for_error(KeyboardInterrupt()) == EXIT_INTERRUPTED

    def test_no_command_shows_help(self):
        code, stdout, stderr = run_cli()
        # No command should show help and exit 0
        assert code == 0
        assert "guesty" in stdout.lower() or "usage" in stdout.lower()
