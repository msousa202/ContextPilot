"""Background service management for the ContextPilot proxy.

Registers `contextpilot proxy` as an OS startup service so it runs
automatically on login with no terminal required.

  contextpilot service install    # register + start immediately
  contextpilot service uninstall  # stop + remove
  contextpilot service status     # show running state

Platform support
----------------
- Windows  : Task Scheduler (ONLOGON trigger, restart on failure, no console window)
- macOS    : launchd user agent  (KeepAlive, runs at load)
- Linux    : systemd user service (Restart=on-failure)

Environment variable
--------------------
`install` sets ANTHROPIC_BASE_URL permanently in the user environment so
Claude Code, GPT Codex, and Aider automatically route through the proxy
without any manual configuration in new terminals or after reboots.
`uninstall` removes it.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

_SYSTEM = platform.system()  # "Windows" | "Darwin" | "Linux"

# Task / service / agent identifiers per platform
_TASK_NAME = "ContextPilotProxy"  # Windows
_LAUNCHD_LABEL = "org.contextpilot.proxy"  # macOS
_SYSTEMD_UNIT = "contextpilot-proxy.service"  # Linux

_LAUNCHD_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{_LAUNCHD_LABEL}.plist"
_SYSTEMD_PATH = Path.home() / ".config" / "systemd" / "user" / _SYSTEMD_UNIT
_LOG_PATH = Path.home() / ".contextpilot" / "proxy.log"

_ENV_KEY = "ANTHROPIC_BASE_URL"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def install(port: int = 8432, host: str = "127.0.0.1") -> None:
    """Register the proxy as a startup service and set ANTHROPIC_BASE_URL."""
    url = f"http://{host}:{port}"

    if _SYSTEM == "Windows":
        _windows_install(port, host)
    elif _SYSTEM == "Darwin":
        _macos_install(port, host)
    else:
        _linux_install(port, host)

    _set_env(url)

    print("\nContextPilot proxy installed as a startup service.")
    print(f"  Proxy URL : {url}")
    print(f"  Env var   : {_ENV_KEY}={url}  (permanent)")
    if _SYSTEM == "Windows":
        print("\nRestart VS Code to pick up the new environment variable.")
    else:
        print("\nOpen a new terminal (or restart VS Code) to pick up the env var.")
    print("Run `contextpilot service status` to confirm it is running.")


def uninstall() -> None:
    """Stop and remove the startup service, clear ANTHROPIC_BASE_URL."""
    if _SYSTEM == "Windows":
        _windows_uninstall()
    elif _SYSTEM == "Darwin":
        _macos_uninstall()
    else:
        _linux_uninstall()

    _unset_env()
    print("ContextPilot proxy service removed and ANTHROPIC_BASE_URL cleared.")
    print("Restart VS Code to apply.")


def status() -> None:
    """Print the current service state."""
    if _SYSTEM == "Windows":
        _windows_status()
    elif _SYSTEM == "Darwin":
        _macos_status()
    else:
        _linux_status()


# ---------------------------------------------------------------------------
# Windows — Task Scheduler
# ---------------------------------------------------------------------------


def _pythonw() -> str:
    """Return pythonw.exe (no console window) or python.exe as fallback."""
    exe = Path(sys.executable)
    pw = exe.parent / "pythonw.exe"
    return str(pw) if pw.exists() else str(exe)


def _windows_task_xml(port: int, host: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>ContextPilot local proxy — compresses LLM API requests automatically.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>5</Count>
    </RestartOnFailure>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
  </Settings>
  <Actions>
    <Exec>
      <Command>{_pythonw()}</Command>
      <Arguments>-m contextpilot proxy --port {port} --host {host}</Arguments>
    </Exec>
  </Actions>
</Task>"""


def _windows_install(port: int, host: str) -> None:
    xml = _windows_task_xml(port, host)
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False, mode="w", encoding="utf-16") as f:
        f.write(xml)
        tmp = f.name
    try:
        _run(["schtasks", "/create", "/tn", _TASK_NAME, "/xml", tmp, "/f"])
        _run(["schtasks", "/run", "/tn", _TASK_NAME])
    finally:
        os.unlink(tmp)


def _windows_uninstall() -> None:
    subprocess.run(["schtasks", "/end", "/tn", _TASK_NAME], capture_output=True)
    _run(["schtasks", "/delete", "/tn", _TASK_NAME, "/f"])


def _windows_status() -> None:
    result = subprocess.run(
        ["schtasks", "/query", "/tn", _TASK_NAME, "/fo", "LIST"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("Service not installed.")
    else:
        print(result.stdout.strip())


# ---------------------------------------------------------------------------
# macOS — launchd
# ---------------------------------------------------------------------------


def _macos_plist(port: int, host: str) -> str:
    log = str(_LOG_PATH)
    python = sys.executable
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{_LAUNCHD_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{python}</string>
    <string>-m</string>
    <string>contextpilot</string>
    <string>proxy</string>
    <string>--port</string>
    <string>{port}</string>
    <string>--host</string>
    <string>{host}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{log}</string>
  <key>StandardErrorPath</key>
  <string>{log}</string>
</dict>
</plist>"""


def _macos_install(port: int, host: str) -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LAUNCHD_PLIST.parent.mkdir(parents=True, exist_ok=True)
    _LAUNCHD_PLIST.write_text(_macos_plist(port, host))
    subprocess.run(["launchctl", "unload", str(_LAUNCHD_PLIST)], capture_output=True)
    _run(["launchctl", "load", str(_LAUNCHD_PLIST)])


def _macos_uninstall() -> None:
    if _LAUNCHD_PLIST.exists():
        subprocess.run(["launchctl", "unload", str(_LAUNCHD_PLIST)], capture_output=True)
        _LAUNCHD_PLIST.unlink()
    else:
        print("Service not installed.")


def _macos_status() -> None:
    result = subprocess.run(
        ["launchctl", "list", _LAUNCHD_LABEL],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("Service not installed or not running.")
    else:
        print(result.stdout.strip())


# ---------------------------------------------------------------------------
# Linux — systemd user service
# ---------------------------------------------------------------------------


def _systemd_unit(port: int, host: str) -> str:
    python = sys.executable
    return f"""[Unit]
Description=ContextPilot Proxy
After=network.target

[Service]
Type=simple
ExecStart={python} -m contextpilot proxy --port {port} --host {host}
Restart=on-failure
RestartSec=10
StandardOutput=append:{_LOG_PATH}
StandardError=append:{_LOG_PATH}

[Install]
WantedBy=default.target
"""


def _linux_install(port: int, host: str) -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SYSTEMD_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SYSTEMD_PATH.write_text(_systemd_unit(port, host))
    _run(["systemctl", "--user", "daemon-reload"])
    _run(["systemctl", "--user", "enable", _SYSTEMD_UNIT])
    _run(["systemctl", "--user", "start", _SYSTEMD_UNIT])


def _linux_uninstall() -> None:
    subprocess.run(["systemctl", "--user", "stop", _SYSTEMD_UNIT], capture_output=True)
    subprocess.run(["systemctl", "--user", "disable", _SYSTEMD_UNIT], capture_output=True)
    if _SYSTEMD_PATH.exists():
        _SYSTEMD_PATH.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)


def _linux_status() -> None:
    result = subprocess.run(
        ["systemctl", "--user", "status", _SYSTEMD_UNIT],
        capture_output=True,
        text=True,
    )
    print(result.stdout.strip() or "Service not installed.")


# ---------------------------------------------------------------------------
# Environment variable management
# ---------------------------------------------------------------------------


def _set_env(url: str) -> None:
    if _SYSTEM == "Windows":
        subprocess.run(["setx", _ENV_KEY, url], capture_output=True)
    else:
        _shell_set_env(_ENV_KEY, url)


def _unset_env() -> None:
    if _SYSTEM == "Windows":
        _windows_delete_env(_ENV_KEY)
    else:
        _shell_unset_env(_ENV_KEY)


def _windows_delete_env(key: str) -> None:
    try:
        import winreg

        reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE)  # type: ignore[attr-defined]
        winreg.DeleteValue(reg_key, key)  # type: ignore[attr-defined]
        winreg.CloseKey(reg_key)  # type: ignore[attr-defined]
    except (ImportError, FileNotFoundError, OSError) as exc:
        print(f"Warning: could not delete Windows environment variable '{key}': {exc}", file=sys.stderr)


def _shell_profiles() -> list[Path]:
    home = Path.home()
    candidates = [
        home / ".zshrc",
        home / ".bashrc",
        home / ".bash_profile",
        home / ".profile",
    ]
    return [p for p in candidates if p.exists()]


_MARKER = "# managed by contextpilot"


def _shell_set_env(key: str, value: str) -> None:
    line = f'export {key}="{value}"  {_MARKER}'
    for profile in _shell_profiles():
        text = profile.read_text(encoding="utf-8")
        # Remove any previous contextpilot-managed line for this key
        cleaned = "\n".join(
            line for line in text.splitlines() if not (f"export {key}=" in line and _MARKER in line)
        )
        profile.write_text(cleaned.rstrip() + f"\n{line}\n", encoding="utf-8")


def _shell_unset_env(key: str) -> None:
    for profile in _shell_profiles():
        text = profile.read_text(encoding="utf-8")
        cleaned = "\n".join(
            line for line in text.splitlines() if not (f"export {key}=" in line and _MARKER in line)
        )
        profile.write_text(cleaned.rstrip() + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr.strip()}")
