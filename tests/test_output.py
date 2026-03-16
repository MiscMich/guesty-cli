"""Tests for guesty_cli.core.output."""
import json
import os
import sys
import pytest
from io import StringIO
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from guesty_cli.core.output import (
    OutputMode, set_output_mode, get_output_mode,
    is_json, is_plain, is_human,
    select_fields, _get_nested,
    emit, bold, cyan, green, red, yellow,
    format_money, format_date, truncate,
)


class TestOutputModeConstants:
    """OutputMode constants exist: HUMAN, JSON, PLAIN."""

    def test_human_mode(self):
        assert OutputMode.HUMAN == "human"

    def test_json_mode(self):
        assert OutputMode.JSON == "json"

    def test_plain_mode(self):
        assert OutputMode.PLAIN == "plain"


class TestSetGetOutputMode:
    """set_output_mode / get_output_mode round-trips."""

    def test_set_and_get_json(self, reset_output_mode):
        set_output_mode(OutputMode.JSON)
        assert get_output_mode() == OutputMode.JSON

    def test_set_and_get_plain(self, reset_output_mode):
        set_output_mode(OutputMode.PLAIN)
        assert get_output_mode() == OutputMode.PLAIN

    def test_set_and_get_human(self, reset_output_mode):
        set_output_mode(OutputMode.HUMAN)
        assert get_output_mode() == OutputMode.HUMAN


class TestModeCheckers:
    """is_json(), is_plain(), is_human() return correct bools for each mode."""

    def test_is_json_true(self, reset_output_mode):
        set_output_mode(OutputMode.JSON)
        assert is_json() is True
        assert is_plain() is False
        assert is_human() is False

    def test_is_plain_true(self, reset_output_mode):
        set_output_mode(OutputMode.PLAIN)
        assert is_plain() is True
        assert is_json() is False
        assert is_human() is False

    def test_is_human_true(self, reset_output_mode):
        set_output_mode(OutputMode.HUMAN)
        assert is_human() is True
        assert is_json() is False
        assert is_plain() is False


class TestSelectFields:
    """select_fields() with flat dict, dot-path, and missing fields."""

    def test_flat_dict(self):
        obj = {"id": "123", "name": "Test", "status": "active"}
        result = select_fields(obj, ["id", "name"])
        assert result == {"id": "123", "name": "Test"}

    def test_dot_path_nested(self):
        obj = {"id": "123", "guest": {"name": "John", "email": "j@example.com"}}
        result = select_fields(obj, ["id", "guest.name"])
        assert result == {"id": "123", "guest.name": "John"}

    def test_missing_fields_returns_only_found(self):
        obj = {"id": "123", "name": "Test"}
        result = select_fields(obj, ["id", "nonexistent"])
        assert result == {"id": "123"}

    def test_non_dict_returns_as_is(self):
        result = select_fields("not a dict", ["field"])
        assert result == "not a dict"


class TestGetNested:
    """_get_nested() with dot paths."""

    def test_simple_key(self):
        assert _get_nested({"a": 1}, "a") == 1

    def test_dot_path(self):
        assert _get_nested({"a": {"b": {"c": 3}}}, "a.b.c") == 3

    def test_missing_key_returns_none(self):
        assert _get_nested({"a": 1}, "b") is None

    def test_none_input_returns_none(self):
        assert _get_nested(None, "a") is None

    def test_non_dict_intermediate_returns_none(self):
        assert _get_nested({"a": "string"}, "a.b") is None


class TestEmit:
    """emit() in various modes."""

    def test_json_mode_prints_valid_json(self, reset_output_mode, capsys):
        set_output_mode(OutputMode.JSON)
        data = [{"id": "1", "name": "Test"}]
        emit(data)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == data

    def test_plain_mode_prints_tsv(self, reset_output_mode, capsys):
        set_output_mode(OutputMode.PLAIN)
        data = [{"id": "1", "name": "Test"}]
        headers = [("id", "ID"), ("name", "Name")]
        emit(data, headers=headers)
        captured = capsys.readouterr()
        lines = captured.out.strip().split('\n')
        assert lines[0] == "ID\tName"
        assert lines[1] == "1\tTest"

    def test_human_mode_calls_human_fn(self, reset_output_mode):
        set_output_mode(OutputMode.HUMAN)
        mock_fn = MagicMock()
        emit({"key": "value"}, human_fn=mock_fn)
        mock_fn.assert_called_once()

    def test_results_only_unwraps_results(self, reset_output_mode, capsys):
        set_output_mode(OutputMode.JSON, results_only=True)
        data = {"results": [{"id": "1"}], "count": 1}
        emit(data)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == [{"id": "1"}]

    def test_select_filters_fields(self, reset_output_mode, capsys):
        set_output_mode(OutputMode.JSON, select=["id"])
        data = [{"id": "1", "name": "Test", "status": "active"}]
        emit(data)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == [{"id": "1"}]


class TestColorFunctions:
    """Color functions return strings."""

    def test_bold_returns_string(self):
        result = bold("test")
        assert isinstance(result, str)
        assert "test" in result

    def test_cyan_returns_string(self):
        result = cyan("test")
        assert isinstance(result, str)
        assert "test" in result

    def test_green_returns_string(self):
        result = green("test")
        assert isinstance(result, str)
        assert "test" in result

    def test_red_returns_string(self):
        result = red("test")
        assert isinstance(result, str)
        assert "test" in result

    def test_yellow_returns_string(self):
        result = yellow("test")
        assert isinstance(result, str)
        assert "test" in result


class TestFormatMoney:
    """format_money() returns colored string."""

    def test_positive_amount(self):
        result = format_money(1234.56)
        assert "1,234.56" in result

    def test_none_amount(self):
        result = format_money(None)
        assert isinstance(result, str)

    def test_negative_amount(self):
        result = format_money(-50.0)
        assert "50.00" in result

    def test_custom_currency(self):
        result = format_money(100, "EUR")
        assert isinstance(result, str)


class TestFormatDate:
    """format_date() handles 'today', 'yesterday', ISO dates."""

    def test_today(self):
        today_iso = datetime.now().strftime("%Y-%m-%dT00:00:00Z")
        result = format_date(today_iso)
        assert "Today" in result

    def test_yesterday(self):
        yesterday = datetime.now() - timedelta(days=1)
        yesterday_iso = yesterday.strftime("%Y-%m-%dT00:00:00Z")
        result = format_date(yesterday_iso)
        assert "Yesterday" in result

    def test_iso_date_string(self):
        result = format_date("2020-01-15T00:00:00Z")
        assert isinstance(result, str)
        assert "Jan" in result

    def test_empty_string(self):
        result = format_date("")
        assert isinstance(result, str)

    def test_none_returns_dash(self):
        result = format_date(None)
        assert isinstance(result, str)


class TestTruncate:
    """truncate() handles None, short strings, long strings."""

    def test_none_returns_empty(self):
        assert truncate(None, 10) == ""

    def test_short_string_unchanged(self):
        assert truncate("hello", 10) == "hello"

    def test_exact_length_unchanged(self):
        assert truncate("hello", 5) == "hello"

    def test_long_string_truncated(self):
        result = truncate("hello world", 6)
        assert len(result) == 6
        assert result.endswith("\u2026")  # ellipsis

    def test_max_len_1(self):
        result = truncate("hello", 1)
        assert len(result) == 1
