"""ContextPilot CLI — entry point for all four surfaces.

Commands
--------
contextpilot proxy    — Surface B: local proxy server (FR-009)
contextpilot mcp      — Surface C: MCP server for Claude Desktop / Claude Code (FR-010)
contextpilot migrate  — Surface D: AST-based migration agent (FR-011)
contextpilot report   — Show local aggregate token savings summary (historical, from events.jsonl)
contextpilot compress — Compress a single messages payload once (FR-014, per-call report)
"""

from __future__ import annotations

import json

import click

from contextpilot._utils import rate_for_model
from contextpilot.telemetry import _LOCAL_LOG


def _bar(ratio: float, width: int = 28) -> str:
    import sys

    encoding = getattr(sys.stdout, "encoding", "").lower().replace("-", "")
    use_unicode = encoding in ("utf8", "utf16", "utf32")
    filled = round(max(0.0, min(1.0, ratio)) * width)
    if use_unicode:
        return "█" * filled + "░" * (width - filled)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


@click.group()
@click.version_option(package_name="contextpilot-ai")
def main() -> None:
    """ContextPilot — Intelligent LLM context optimization middleware."""


# ---------------------------------------------------------------------------
# Surface B: proxy
# ---------------------------------------------------------------------------


@main.command()
@click.option("--port", default=8432, show_default=True, help="TCP port to listen on.")
@click.option("--host", default="127.0.0.1", show_default=True, help="Address to bind.")
@click.option("--config", "config_path", default=None, help="Path to contextpilot.yaml.")
def proxy(port: int, host: str, config_path: str | None) -> None:
    """Start the local proxy server (Surface B, FR-009).

    \b
    Set one environment variable to route requests through ContextPilot:

      Anthropic / Claude Code:
        export ANTHROPIC_BASE_URL=http://localhost:8432

      OpenAI / GPT Codex / Aider:
        export OPENAI_BASE_URL=http://localhost:8432/v1
    """
    from contextpilot.proxy import run_proxy

    run_proxy(host=host, port=port, config_path=config_path)


# ---------------------------------------------------------------------------
# Surface C: mcp
# ---------------------------------------------------------------------------


@main.command()
def mcp() -> None:
    """Start the MCP server for Claude Desktop and Claude Code (Surface C, FR-010).

    \b
    Runs in stdio mode — connect once, every LLM code Claude generates
    will include contextpilot.wrap() automatically.

    Claude Desktop — add to claude_desktop_config.json:
    \b
      {
        "mcpServers": {
          "contextpilot": {
            "command": "contextpilot",
            "args": ["mcp"]
          }
        }
      }

    Claude Code:
    \b
      claude mcp add contextpilot -- contextpilot mcp
    """
    from contextpilot.mcp_server import run_mcp

    run_mcp()


# ---------------------------------------------------------------------------
# Surface D: migrate
# ---------------------------------------------------------------------------


@main.command()
@click.argument("path", default=".", metavar="PATH")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would change without writing files (default if neither flag is given).",
)
@click.option(
    "--apply", "apply_changes", is_flag=True, default=False, help="Write changes to files."
)
@click.option("--config", "config_path", default=None, help="Path to contextpilot.yaml.")
def migrate(path: str, dry_run: bool, apply_changes: bool, config_path: str | None) -> None:
    """Wrap existing LLM API calls with ContextPilot (Surface D, FR-011).

    \b
    Scans PATH (file or directory) for OpenAI and Anthropic client
    instantiations and wraps them with contextpilot.wrap():

      contextpilot migrate ./src/ --dry-run   # preview changes
      contextpilot migrate ./src/ --apply      # rewrite files
    """
    from contextpilot.migrate import MigrationAgent

    # Default to dry-run when neither flag is explicitly given
    effective_dry_run = dry_run or not apply_changes

    agent = MigrationAgent(config_path=config_path)
    agent.run(path=path, dry_run=effective_dry_run, apply=apply_changes)


# ---------------------------------------------------------------------------
# Surface B companion: service management
# ---------------------------------------------------------------------------


@main.group()
def service() -> None:
    """Manage the ContextPilot proxy as a background startup service.

    \b
    Installs the proxy so it starts automatically on login — no terminal
    required. Also sets ANTHROPIC_BASE_URL permanently so Claude Code,
    GPT Codex, and Aider route through it automatically.

    \b
      contextpilot service install    # register + start now
      contextpilot service uninstall  # stop + remove
      contextpilot service status     # show running state
    """


@service.command("install")
@click.option("--port", default=8432, show_default=True, help="TCP port for the proxy.")
@click.option("--host", default="127.0.0.1", show_default=True, help="Address to bind.")
def service_install(port: int, host: str) -> None:
    """Register the proxy as a startup service and set ANTHROPIC_BASE_URL."""
    from contextpilot.service import install

    try:
        install(port=port, host=host)
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc


@service.command("uninstall")
def service_uninstall() -> None:
    """Stop and remove the startup service, clear ANTHROPIC_BASE_URL."""
    from contextpilot.service import uninstall

    try:
        uninstall()
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc


@service.command("status")
def service_status() -> None:
    """Show whether the proxy service is installed and running."""
    from contextpilot.service import status

    status()


# ---------------------------------------------------------------------------
# Report: local savings summary
# ---------------------------------------------------------------------------


@main.command()
@click.option("--tail", default=0, help="Show only the last N events (0 = all).")
def report(tail: int) -> None:
    """Show AGGREGATE token savings from the local event log (~/.contextpilot/events.jsonl).

    For a single call's compression breakdown, use `contextpilot compress --report` instead.
    """
    if not _LOCAL_LOG.exists():
        click.echo("No events recorded yet. Run a few API calls through ContextPilot first.")
        return

    events: list[dict] = []
    malformed_lines = 0
    with _LOCAL_LOG.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    malformed_lines += 1

    if malformed_lines:
        click.echo(f"Skipped {malformed_lines} malformed event log line(s).")

    if not events:
        click.echo("Event log is empty.")
        return

    if tail:
        events = events[-tail:]

    total = len(events)
    fallbacks = sum(1 for e in events if e.get("fallback_triggered"))
    orig_tokens = sum(e.get("tokens_input_original", 0) for e in events)
    comp_tokens = sum(e.get("tokens_input_compressed", 0) for e in events)
    saved_tokens = orig_tokens - comp_tokens
    avg_quality = sum(e.get("quality_score", 100) for e in events) / total

    # Dollar savings estimate
    saved_usd = sum(
        (e.get("tokens_input_original", 0) - e.get("tokens_input_compressed", 0))
        / 1_000_000
        * rate_for_model(e.get("model", ""))
        for e in events
    )

    ratio = (saved_tokens / orig_tokens) if orig_tokens else 0.0
    ratio_pct = ratio * 100
    fallback_pct = fallbacks / total * 100
    quality_indicator = "✓" if avg_quality >= 85 else "⚠"

    click.echo()
    click.echo("  ContextPilot — Savings Report")
    click.echo("  " + "─" * 40)
    click.echo(f"  Calls logged   :  {total:,}")
    click.echo()
    click.echo("  Token reduction")
    click.echo(f"  {_bar(ratio)}  {ratio_pct:.1f}% saved")
    click.echo(f"  {orig_tokens:,} → {comp_tokens:,}  (saved {saved_tokens:,} tokens)")
    click.echo()
    click.echo(f"  Quality avg    :  {avg_quality:.1f} / 100  {quality_indicator}")
    click.echo(f"  Fallback rate  :  {fallbacks}/{total}  ({fallback_pct:.1f}%)")
    click.echo(f"  Est. cost saved:  ~${saved_usd:.4f}")
    click.echo()
    click.echo(f"  Log: {_LOCAL_LOG}")
    click.echo()


# ---------------------------------------------------------------------------
# Compress: one-shot single-call compression (FR-014)
# ---------------------------------------------------------------------------


@main.command("compress")
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True),
    default=None,
    help='JSON file: {"messages": [...], "system": "..."}. Reads stdin if omitted.',
)
@click.option(
    "--report",
    "show_report",
    is_flag=True,
    default=False,
    help="Print a per-call compression report (distinct from `contextpilot report`, "
    "which shows aggregate historical savings).",
)
@click.option("--config", "config_path", default=None, help="Path to contextpilot.yaml.")
@click.option("--json", "as_json", is_flag=True, default=False, help="Print machine-readable JSON.")
def compress_command(
    input_path: str | None, show_report: bool, config_path: str | None, as_json: bool
) -> None:
    """Compress a single messages payload once and print the result.

    \b
      echo '{"messages": [{"role": "user", "content": "..."}]}' | contextpilot compress --report
    """
    import sys

    from contextpilot.api import compress as compress_fn
    from contextpilot.config import ContextPilotConfig
    from contextpilot.report import render_report

    raw = open(input_path, encoding="utf-8").read() if input_path else sys.stdin.read()
    data = json.loads(raw)
    cfg = ContextPilotConfig.load(config_path)
    result = compress_fn(
        data.get("messages", []), system=data.get("system"), config=cfg, report=show_report
    )

    if as_json:
        out = dict(result.payload)
        if result.report:
            out["report"] = result.report.to_dict()
        click.echo(json.dumps(out))
        return

    orig = sum(len((m.get("content") or "").split()) for m in data.get("messages", []))
    comp = sum(len((m.get("content") or "").split()) for m in result.payload["messages"])
    click.echo(f"{orig:,} -> {comp:,} tokens")
    if show_report and result.report:
        click.echo()
        click.echo(render_report(result.report))
