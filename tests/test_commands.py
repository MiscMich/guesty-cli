"""Tests for new commands: schema, completion, exit-codes, agent."""
import json
import os
import subprocess
import sys
import pytest

CLI_MODULE = "guesty_cli.main"
CLI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_cli(*args, env_extra=None):
    """Run guesty-cli as subprocess and return (returncode, stdout, stderr)."""
    env = os.environ.copy()
    env['NO_COLOR'] = '1'
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        [sys.executable, "-m", CLI_MODULE] + list(args),
        capture_output=True, text=True, cwd=CLI_DIR,
        env=env, timeout=10,
    )
    return result.returncode, result.stdout, result.stderr


class TestSchemaCommand:
    """schema command outputs valid JSON with expected keys."""

    def test_schema_valid_json(self):
        code, stdout, stderr = run_cli("schema")
        assert code == 0
        parsed = json.loads(stdout)
        assert "schema_version" in parsed
        assert "commands" in parsed
        assert "exit_codes" in parsed
        assert "global_flags" in parsed

    def test_schema_with_target(self):
        code, stdout, stderr = run_cli("schema", "listings")
        assert code == 0
        parsed = json.loads(stdout)
        commands = parsed["commands"]
        assert "listings" in commands
        assert len(commands) == 1

    def test_schema_version_is_int(self):
        code, stdout, stderr = run_cli("schema")
        assert code == 0
        parsed = json.loads(stdout)
        assert isinstance(parsed["schema_version"], int)

    def test_schema_has_name(self):
        code, stdout, stderr = run_cli("schema")
        assert code == 0
        parsed = json.loads(stdout)
        assert parsed["name"] == "guesty"


class TestCompletionBash:
    """completion bash outputs valid bash script."""

    def test_bash_completion(self):
        code, stdout, stderr = run_cli("completion", "bash")
        assert code == 0
        assert "_guesty_completions" in stdout
        assert "complete -F" in stdout
        assert "COMPREPLY" in stdout


class TestCompletionZsh:
    """completion zsh outputs valid zsh script."""

    def test_zsh_completion(self):
        code, stdout, stderr = run_cli("completion", "zsh")
        assert code == 0
        assert "#compdef guesty" in stdout
        assert "_guesty" in stdout
        assert "_arguments" in stdout


class TestCompletionFish:
    """completion fish outputs valid fish completions."""

    def test_fish_completion(self):
        code, stdout, stderr = run_cli("completion", "fish")
        assert code == 0
        assert "complete -c guesty" in stdout
        assert "__fish_use_subcommand" in stdout


class TestExitCodesCommand:
    """exit-codes command outputs valid JSON and TSV."""

    def test_exit_codes_json(self):
        code, stdout, stderr = run_cli("--json", "exit-codes")
        assert code == 0
        parsed = json.loads(stdout)
        assert isinstance(parsed, list)
        assert len(parsed) == 11
        # Check structure of first entry
        assert "code" in parsed[0]
        assert "name" in parsed[0]
        assert "description" in parsed[0]

    def test_exit_codes_plain_tsv(self):
        code, stdout, stderr = run_cli("--plain", "exit-codes")
        assert code == 0
        lines = stdout.strip().split('\n')
        assert len(lines) == 11
        # Each line should be TSV with 3 fields
        for line in lines:
            parts = line.split('\t')
            assert len(parts) == 3

    def test_exit_codes_auto_json_piped(self):
        # stdout is piped in subprocess, so with GUESTY_AUTO_JSON it should output JSON
        code, stdout, stderr = run_cli("exit-codes", env_extra={"GUESTY_AUTO_JSON": "1"})
        assert code == 0
        parsed = json.loads(stdout)
        assert isinstance(parsed, list)


class TestAgentCapabilities:
    """agent capabilities outputs valid JSON."""

    def test_capabilities_json(self):
        code, stdout, stderr = run_cli("agent", "capabilities")
        assert code == 0
        parsed = json.loads(stdout)
        assert "name" in parsed
        assert parsed["name"] == "guesty-cli"
        assert "version" in parsed
        assert "output_modes" in parsed
        assert "features" in parsed
        assert "resources" in parsed
        assert "environment_variables" in parsed
        assert "tips" in parsed

    def test_capabilities_has_expected_features(self):
        code, stdout, stderr = run_cli("agent", "capabilities")
        assert code == 0
        parsed = json.loads(stdout)
        assert "stable_exit_codes" in parsed["features"]
        assert "tri_modal_output" in parsed["features"]
        assert "circuit_breaker" in parsed["features"]


class TestAgentTips:
    """agent tips outputs non-empty string."""

    def test_tips_non_empty(self):
        code, stdout, stderr = run_cli("agent", "tips")
        assert code == 0
        assert len(stdout.strip()) > 0
        assert "Output Modes" in stdout
        assert "Exit Codes" in stdout or "exit code" in stdout.lower()
