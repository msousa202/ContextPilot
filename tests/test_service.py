"""Tests for contextpilot/service.py — background service management."""
from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from contextpilot import service as svc

_SYSTEM = platform.system()


# ---------------------------------------------------------------------------
# XML / plist / unit generation (pure, no subprocess)
# ---------------------------------------------------------------------------

class TestWindowsTaskXml:
    @pytest.mark.skipif(_SYSTEM != "Windows", reason="Windows only")
    def test_contains_task_name_and_port(self):
        xml = svc._windows_task_xml(8432, "127.0.0.1")
        assert "contextpilot" in xml
        assert "8432" in xml
        assert "127.0.0.1" in xml

    @pytest.mark.skipif(_SYSTEM != "Windows", reason="Windows only")
    def test_restart_on_failure_present(self):
        xml = svc._windows_task_xml(8432, "127.0.0.1")
        assert "RestartOnFailure" in xml

    @pytest.mark.skipif(_SYSTEM != "Windows", reason="Windows only")
    def test_logon_trigger_present(self):
        xml = svc._windows_task_xml(8432, "127.0.0.1")
        assert "LogonTrigger" in xml

    @pytest.mark.skipif(_SYSTEM != "Windows", reason="Windows only")
    def test_custom_port(self):
        xml = svc._windows_task_xml(9999, "0.0.0.0")
        assert "9999" in xml
        assert "0.0.0.0" in xml


class TestMacosPlist:
    @pytest.mark.skipif(_SYSTEM != "Darwin", reason="macOS only")
    def test_contains_label_and_port(self):
        plist = svc._macos_plist(8432, "127.0.0.1")
        assert svc._LAUNCHD_LABEL in plist
        assert "8432" in plist

    @pytest.mark.skipif(_SYSTEM != "Darwin", reason="macOS only")
    def test_keep_alive_present(self):
        plist = svc._macos_plist(8432, "127.0.0.1")
        assert "KeepAlive" in plist

    @pytest.mark.skipif(_SYSTEM != "Darwin", reason="macOS only")
    def test_run_at_load_present(self):
        plist = svc._macos_plist(8432, "127.0.0.1")
        assert "RunAtLoad" in plist


class TestLinuxUnit:
    @pytest.mark.skipif(_SYSTEM == "Windows", reason="Unix only")
    def test_contains_port_and_restart(self):
        unit = svc._systemd_unit(8432, "127.0.0.1")
        assert "8432" in unit
        assert "Restart=on-failure" in unit

    @pytest.mark.skipif(_SYSTEM == "Windows", reason="Unix only")
    def test_wanted_by_default_target(self):
        unit = svc._systemd_unit(8432, "127.0.0.1")
        assert "WantedBy=default.target" in unit


# ---------------------------------------------------------------------------
# Shell profile env var management (Unix)
# ---------------------------------------------------------------------------

class TestShellEnvManagement:
    @pytest.mark.skipif(_SYSTEM == "Windows", reason="Unix only")
    def test_set_env_writes_export_line(self, tmp_path):
        profile = tmp_path / ".bashrc"
        profile.write_text("# existing content\n")

        with patch.object(svc, "_shell_profiles", return_value=[profile]):
            svc._shell_set_env("ANTHROPIC_BASE_URL", "http://localhost:8432")

        content = profile.read_text()
        assert 'export ANTHROPIC_BASE_URL="http://localhost:8432"' in content
        assert svc._MARKER in content

    @pytest.mark.skipif(_SYSTEM == "Windows", reason="Unix only")
    def test_set_env_replaces_existing_entry(self, tmp_path):
        profile = tmp_path / ".bashrc"
        profile.write_text(
            f'export ANTHROPIC_BASE_URL="http://localhost:9000"  {svc._MARKER}\n'
        )

        with patch.object(svc, "_shell_profiles", return_value=[profile]):
            svc._shell_set_env("ANTHROPIC_BASE_URL", "http://localhost:8432")

        content = profile.read_text()
        assert "9000" not in content
        assert "8432" in content
        assert content.count("export ANTHROPIC_BASE_URL") == 1

    @pytest.mark.skipif(_SYSTEM == "Windows", reason="Unix only")
    def test_unset_env_removes_line(self, tmp_path):
        profile = tmp_path / ".bashrc"
        profile.write_text(
            f'# other stuff\nexport ANTHROPIC_BASE_URL="http://localhost:8432"  {svc._MARKER}\n'
        )

        with patch.object(svc, "_shell_profiles", return_value=[profile]):
            svc._shell_unset_env("ANTHROPIC_BASE_URL")

        content = profile.read_text()
        assert "ANTHROPIC_BASE_URL" not in content
        assert "# other stuff" in content

    @pytest.mark.skipif(_SYSTEM == "Windows", reason="Unix only")
    def test_unset_env_leaves_unmanaged_lines_intact(self, tmp_path):
        profile = tmp_path / ".bashrc"
        profile.write_text("export FOO=bar\nexport BAZ=qux\n")

        with patch.object(svc, "_shell_profiles", return_value=[profile]):
            svc._shell_unset_env("ANTHROPIC_BASE_URL")

        content = profile.read_text()
        assert "FOO=bar" in content
        assert "BAZ=qux" in content


# ---------------------------------------------------------------------------
# _run helper
# ---------------------------------------------------------------------------

class TestRunHelper:
    def test_raises_on_nonzero_exit(self):
        with pytest.raises(RuntimeError, match="Command failed"):
            svc._run(["python", "-c", "import sys; sys.exit(1)"])

    def test_no_raise_on_success(self):
        svc._run(["python", "-c", "pass"])


# ---------------------------------------------------------------------------
# Windows env deletion (unit)
# ---------------------------------------------------------------------------

class TestWindowsDeleteEnv:
    @pytest.mark.skipif(_SYSTEM != "Windows", reason="Windows only")
    def test_delete_missing_key_does_not_raise(self):
        import winreg
        with patch("winreg.OpenKey") as mock_open, \
             patch("winreg.DeleteValue", side_effect=FileNotFoundError):
            mock_open.return_value.__enter__ = lambda s: s
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            # should not raise
            svc._windows_delete_env("ANTHROPIC_BASE_URL")


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------

class TestServiceCli:
    def test_service_group_exists(self):
        from click.testing import CliRunner
        from contextpilot.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["service", "--help"])
        assert result.exit_code == 0
        assert "install" in result.output
        assert "uninstall" in result.output
        assert "status" in result.output

    def test_install_command_exists(self):
        from click.testing import CliRunner
        from contextpilot.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["service", "install", "--help"])
        assert result.exit_code == 0
        assert "--port" in result.output
        assert "--host" in result.output

    def test_install_propagates_runtime_error_as_click_exception(self):
        from click.testing import CliRunner
        from contextpilot.cli import main
        runner = CliRunner()
        with patch("contextpilot.service.install", side_effect=RuntimeError("boom")):
            result = runner.invoke(main, ["service", "install"])
        assert result.exit_code != 0
        assert "boom" in result.output

    def test_uninstall_propagates_runtime_error_as_click_exception(self):
        from click.testing import CliRunner
        from contextpilot.cli import main
        runner = CliRunner()
        with patch("contextpilot.service.uninstall", side_effect=RuntimeError("gone")):
            result = runner.invoke(main, ["service", "uninstall"])
        assert result.exit_code != 0
        assert "gone" in result.output
