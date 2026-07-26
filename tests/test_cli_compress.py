"""Tests for the `contextpilot compress` CLI command (FR-014)."""

from __future__ import annotations

import json

from click.testing import CliRunner

from contextpilot.cli import main

_PAYLOAD = json.dumps({"messages": [{"role": "user", "content": "Hello there"}]})


def test_compress_command_stdin_json():
    runner = CliRunner()
    result = runner.invoke(main, ["compress"], input=_PAYLOAD)
    assert result.exit_code == 0
    assert "tokens" in result.output


def test_compress_command_report_flag_prints_report():
    runner = CliRunner()
    result = runner.invoke(main, ["compress", "--report"], input=_PAYLOAD)
    assert result.exit_code == 0
    assert "Compression Report" in result.output


def test_compress_command_json_flag():
    runner = CliRunner()
    result = runner.invoke(main, ["compress", "--json"], input=_PAYLOAD)
    assert result.exit_code == 0
    out = json.loads(result.output)
    assert "messages" in out


def test_compress_command_json_and_report_includes_report_key():
    runner = CliRunner()
    result = runner.invoke(main, ["compress", "--json", "--report"], input=_PAYLOAD)
    assert result.exit_code == 0
    out = json.loads(result.output)
    assert "report" in out


def test_compress_command_input_file(tmp_path):
    input_file = tmp_path / "payload.json"
    input_file.write_text(_PAYLOAD)
    runner = CliRunner()
    result = runner.invoke(main, ["compress", "--input", str(input_file)])
    assert result.exit_code == 0
    assert "tokens" in result.output


def test_compress_help():
    runner = CliRunner()
    result = runner.invoke(main, ["compress", "--help"])
    assert result.exit_code == 0
    assert "--report" in result.output


def test_compress_command_invalid_json_from_stdin():
    runner = CliRunner()
    result = runner.invoke(main, ["compress"], input="{not json")

    assert result.exit_code == 1
    assert not isinstance(result.exception, json.JSONDecodeError)
    assert "Error: invalid JSON from stdin" in result.output


def test_compress_command_invalid_json_from_input_file(tmp_path):
    input_file = tmp_path / "payload.json"
    input_file.write_text("{not json")
    runner = CliRunner()
    result = runner.invoke(main, ["compress", "--input", str(input_file)])

    assert result.exit_code == 1
    assert not isinstance(result.exception, json.JSONDecodeError)
    assert f"Error: invalid JSON from {input_file}" in result.output
