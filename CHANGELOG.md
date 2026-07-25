# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/). Versions follow [Semantic Versioning](https://semver.org/).

---

## [0.3.0] — 2026-07-25

### Added
- **Intent detection** (#10): `analyzer.py` classifies each conversation as `debug` / `build` / `explore` / `refactor` / `unknown` using a cheap deterministic regex/keyword heuristic (no LLM call). Each compression strategy adjusts its aggressiveness accordingly — e.g. `debug` widens the retained history window and never truncates the system prompt; `explore` narrows it. Configurable via `compression.intent_override` / `CONTEXTPILOT_INTENT` to force a mode manually.
- **CompressionReport** (#14): `contextpilot.compress(messages, report=True)` returns a structured `CompressionReport` describing what each strategy did per block (kept/summarized/dropped, reason, tokens saved). Exposed via the new `contextpilot compress --report` CLI command, and the `optimize_context(report=True)` MCP tool + `contextpilot://last-report` resource. Report content is never sent to telemetry.
- **`contextpilot compress`**: new one-shot CLI command to compress a single messages payload from a file or stdin (`--report` for the breakdown, `--json` for machine-readable output).

### Fixed
- `mcp_server.py`'s `suggest_config()` called a nonexistent `Pipeline.log_event()` on malformed log lines, which would raise `AttributeError` at runtime and was failing CI's mypy check. Now counts and reports malformed lines the same way `get_savings()` already does.

### Notes
- Issue #11 (AST-based code block skeletonization) was closed as won't-do — it's a fundamental mismatch with `structural.py`'s pure-regex, <10ms design and would need its own design project rather than an extension of the existing strategy.

---

## [0.2.0] — 2026-05-09

### Added
- **Surface B — Proxy server** (`contextpilot proxy --port 8432`): OpenAI-compatible local proxy that intercepts requests from Claude Code, GPT Codex, and Aider, compresses payloads, and forwards to the real provider transparently.
- **Surface C — MCP server** (`contextpilot mcp`): FastMCP server exposing `optimize_context` and `optimize_llm_code` tools plus `contextpilot://savings` and `contextpilot://config/suggest` resources to Claude Desktop and Claude Code.
- **Surface D — CLI migration agent** (`contextpilot migrate`): AST-based scanner that finds and wraps existing `OpenAI()` and `Anthropic()` instantiations with `contextpilot.wrap()`. Supports `--dry-run` and `--apply`.
- **`contextpilot service install/uninstall/status`**: Registers the proxy as an OS startup service (Windows Task Scheduler, macOS launchd, Linux systemd) and sets `ANTHROPIC_BASE_URL` permanently — no terminal required after install.
- **`contextpilot report`**: Reads `~/.contextpilot/events.jsonl` and prints token savings, compression ratio, quality scores, and estimated cost saved.
- **`python -m contextpilot`**: Universal fallback entry point — works regardless of PATH or virtualenv state.
- **`contextpilot/_utils.py`**: Shared `word_count_messages()` and `flatten_messages()` utilities.
- **`SECURITY.md`**: Full data-handling policy covering API key passthrough, telemetry schema, proxy trust model, MCP isolation, and responsible disclosure.
- **`CONTRIBUTING.md`**, **`LICENSE`**, **`.github/`** templates.

### Fixed
- Proxy 500 error when Claude Code sends `system` as a content-block list (`[{"type":"text","text":"..."}]`). Added `_system_as_str()` normaliser and fail-safe try/except around all compression — proxy always forwards even if compression fails.
- `numpy` was missing from `pyproject.toml` dependencies despite being used in `analyzer.py`.
- `fastapi` removed from `proxy`/`all`/`dev` extras — proxy uses Starlette directly.
- `click.version_option(package_name=...)` corrected to `"contextpilot-ai"` (distribution name).
- `_LOCAL_LOG` was duplicated in `cli.py` — now imported from `telemetry.py`.
- `Optional[str]` → `str | None` in `config.py` for consistency.
- `flush_interval` removed from `TelemetryConfig` and `contextpilot.yaml.example` — it was defined but never implemented.
- `mcp` added to the `[all]` extra.
- All `__pycache__/` files, `Doc/`, `Logs/`, `.claude/`, `.cursor/` removed from git tracking.

---

## [0.1.0] — 2026-05-08

### Added
- **Surface A — Python library**: `contextpilot.wrap(client)` drop-in wrapper for `openai.OpenAI` and `anthropic.Anthropic`.
- **Compression pipeline** (FR-003): history summarization, system prompt deduplication, RAG chunk pruning, structural stripping.
- **Context analyzer** (FR-002): TF-IDF scoring across four dimensions — staleness, redundancy, relevance, density.
- **Quality gate** (FR-004): predicted score 0–100, automatic fallback to original if below threshold (default 85).
- **Shadow tester** (FR-005): cosine similarity comparison between compressed and original responses.
- **Telemetry** (FR-006): metadata-only local event log at `~/.contextpilot/events.jsonl`. No prompt content ever logged.
- **Configuration** (FR-007): YAML file + environment variable overrides.
- **Agent memory middleware** (FR-008): `contextpilot.middleware.AgentMemory` for LangChain / CrewAI / AutoGen handoff compression.
- Initial PyPI release as `contextpilot-ai`.
