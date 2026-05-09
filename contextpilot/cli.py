"""ContextPilot CLI — entry point for all four surfaces.

Commands
--------
contextpilot proxy    — Surface B: local proxy server (FR-009)
contextpilot mcp      — Surface C: MCP server for Claude Desktop / Claude Code (FR-010)
contextpilot migrate  — Surface D: AST-based migration agent (FR-011)
contextpilot report   — Show local token savings summary
"""
from __future__ import annotations

import json
from pathlib import Path

import click

_LOCAL_LOG = Path.home() / ".contextpilot" / "events.jsonl"

# Rough $/1M-token rates for common models (input side).
_PRICING: dict[str, float] = {
    "gpt-4o": 5.00,
    "gpt-4o-mini": 0.15,
    "gpt-4-turbo": 10.00,
    "gpt-4": 30.00,
    "gpt-3.5-turbo": 0.50,
    "claude-opus": 15.00,
    "claude-sonnet": 3.00,
    "claude-haiku": 0.25,
}
_DEFAULT_RATE = 5.00  # $/1M tokens fallback


def _rate_for(model: str) -> float:
    m = model.lower()
    for key, rate in _PRICING.items():
        if key in m:
            return rate
    return _DEFAULT_RATE


@click.group()
@click.version_option(package_name="contextpilot")
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
@click.option("--apply", "apply_changes", is_flag=True, default=False, help="Write changes to files.")
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
# Report: local savings summary
# ---------------------------------------------------------------------------

@main.command()
@click.option("--tail", default=0, help="Show only the last N events (0 = all).")
def report(tail: int) -> None:
    """Show token savings from the local event log (~/.contextpilot/events.jsonl)."""
    if not _LOCAL_LOG.exists():
        click.echo("No events recorded yet. Run a few API calls through ContextPilot first.")
        return

    events: list[dict] = []
    with _LOCAL_LOG.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

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
        * _rate_for(e.get("model", ""))
        for e in events
    )

    ratio = (saved_tokens / orig_tokens * 100) if orig_tokens else 0.0

    click.echo()
    click.echo("  ContextPilot — Savings Report")
    click.echo("  " + "─" * 36)
    click.echo(f"  Total calls logged   : {total:,}")
    click.echo(f"  Fallback rate        : {fallbacks}/{total} ({fallbacks/total*100:.1f}%)")
    click.echo(f"  Tokens in (original) : {orig_tokens:,}")
    click.echo(f"  Tokens in (sent)     : {comp_tokens:,}")
    click.echo(f"  Tokens saved         : {saved_tokens:,}  ({ratio:.1f}% reduction)")
    click.echo(f"  Avg quality score    : {avg_quality:.1f}/100")
    click.echo(f"  Est. cost saved      : ${saved_usd:.4f}")
    click.echo()
    click.echo(f"  Log: {_LOCAL_LOG}")
    click.echo()
