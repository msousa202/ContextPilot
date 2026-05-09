# Phase 1 — Remaining Surfaces (Proxy + CLI Migration)
**Date:** 2026-05-09
**Roadmap target:** Months 1–4 | Local proxy server + CLI migration agent

---

## What changed

### Surface B — Local proxy server (FR-009)

- **`contextpilot/proxy.py`** — Starlette-based ASGI proxy that intercepts OpenAI-compatible HTTP requests from AI coding tools (Claude Code, GPT Codex, Aider) and compresses the message payload through the shared Pipeline before forwarding to the real provider.
  - Routes `/v1/chat/completions` → OpenAI, `/v1/messages` → Anthropic.
  - Streaming support via `StreamingResponse` (SSE pass-through).
  - Passthrough route for all other paths (models list, etc.) — no modification.
  - Hop-by-hop headers stripped; original auth headers forwarded unchanged.
  - `run_proxy()` blocked runner; prints env var hint on startup.
  - Graceful import guard — raises `RuntimeError` with install hint if starlette/uvicorn are missing.

Usage:
```
contextpilot proxy --port 8432
export ANTHROPIC_BASE_URL=http://localhost:8432       # Claude Code
export OPENAI_BASE_URL=http://localhost:8432/v1       # OpenAI SDK / GPT Codex
```

### Surface D — CLI migration agent (FR-011)

- **`contextpilot/migrate.py`** — AST-based migration agent that scans Python source files for LLM SDK client instantiations and wraps them with `contextpilot.wrap()`.
  - Recognises: `OpenAI`, `AsyncOpenAI`, `Anthropic`, `AsyncAnthropic` (both bare and module-qualified, e.g. `openai.OpenAI()`).
  - Handles `ast.Assign` and `ast.AnnAssign` nodes.
  - Inserts `import contextpilot` after the last existing import (or prepends if none).
  - Skips files that are already wrapped, files with syntax errors (with stderr warning), and directories matching `venv`, `.venv`, `env`, `__pycache__`, `node_modules`.
  - `--dry-run`: prints unified diff, no file writes.
  - `--apply`: rewrites files in place; reports count.
  - `FileResult.unified_diff()` generates standard `unified_diff` output.

Usage:
```
contextpilot migrate ./src/ --dry-run    # preview
contextpilot migrate ./src/ --apply      # rewrite
```

### CLI entry point (FR-009 + FR-011)

- **`contextpilot/cli.py`** — Click-based CLI with `proxy` and `migrate` subcommands. Both subcommands lazy-import their module to avoid import errors when optional extras are absent.

### pyproject.toml updates

- Added `click>=8.0` to core `dependencies`.
- Added `[project.scripts]` entry: `contextpilot = "contextpilot.cli:main"` — enables `contextpilot proxy` and `contextpilot migrate` after `pip install`.
- Added `[proxy]` optional extra: `fastapi>=0.100`, `uvicorn[standard]>=0.23`, `starlette>=0.27`.
- Updated `[all]` to include proxy extras.
- Updated `[dev]` to include proxy extras + `httpx`.

### Test suite — 109 tests, 0 failures (1 skipped)

| File | Tests | Covers |
|------|-------|--------|
| `test_proxy.py` | 9 | Route detection, OpenAI/Anthropic handler compression, passthrough — skipped when starlette not installed |
| `test_migrate.py` | 32 | AST helpers, source transformation, dry-run vs apply, venv skip, single file, multi-client |

---

## Phase 1 completion status

| FR | Surface | Status |
|----|---------|--------|
| FR-001 | Library | ✅ Done (Phase 1 foundation) |
| FR-002 | Library | ✅ Done |
| FR-003 | Library | ✅ Done |
| FR-004 | Library | ✅ Done |
| FR-005 | Library | ✅ Done |
| FR-006 | Library | ✅ Done |
| FR-007 | Library | ✅ Done |
| FR-008 | Library | ✅ Done |
| FR-009 | Proxy   | ✅ Done (this session) |
| FR-011 | CLI     | ✅ Done (this session) |

Phase 1 is complete. Phase 2 begins with: Google Vertex AI adapter, MCP server (FR-010), team dashboard.

---

## Conventional commits

```
feat(proxy): add local proxy server surface B (FR-009)
feat(migrate): add AST-based CLI migration agent surface D (FR-011)
feat(cli): add click CLI entry point with proxy and migrate commands
chore(deps): add click core dep; add [proxy] optional extra; add [project.scripts]
feat(tests): add test_proxy.py (9 tests) and test_migrate.py (32 tests)
```
