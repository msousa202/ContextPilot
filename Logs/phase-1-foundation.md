# Phase 1 — Foundation
**Date:** 2026-05-08
**Roadmap target:** Months 1–4 | Core compression library (OpenAI + Anthropic)

---

## What changed

### Core library (FR-001 – FR-008)

- **`contextpilot.wrap(client)`** — drop-in wrapper for `openai.OpenAI` and
  `anthropic.Anthropic`; detects provider from module/class name and returns
  the appropriate adapter. All original parameters, return types, and error
  behaviours are preserved (FR-001).

- **Context analyzer** (`contextpilot/analyzer.py`) — scores every message
  block across four dimensions: staleness, redundancy, relevance, information
  density. Classifies blocks as `essential | compressible | droppable`.
  Uses TF-IDF cosine similarity; no embedding model required for default mode
  (FR-002).

- **Compression pipeline** (`contextpilot/compressor.py`) with four strategies
  (FR-003):
  - *History summarization* (`strategies/history.py`) — keeps the last
    `history_window` turns verbatim; collapses older turns into a compact
    `[CTX N turns ~Xtok]` block. No LLM call; only applied when the summary
    is actually shorter than the original.
  - *System prompt deduplication* (`strategies/dedup.py`) — tracks prompt hash
    across calls; in aggressive mode truncates unchanged prompts to a short
    cache reference.
  - *RAG chunk pruning* (`strategies/rag_pruner.py`) — scores each retrieved
    chunk against the current query via TF-IDF; removes chunks below
    `rag_relevance_min` (default 0.15). Never empties a message.
  - *Structural stripping* (`strategies/structural.py`) — deterministic regex:
    removes excessive blank lines, trailing whitespace, empty XML tags,
    repeated horizontal rules.

- **Quality gate** (`contextpilot/quality.py`) — predicted preservation score
  0–100 (TF-IDF semantic similarity × 0.7 + token retention × 0.3). Falls
  back to original payload if score < `quality_threshold` (default 85).
  Pipeline also falls back if compression increases token count (FR-004).

- **Shadow testing** (`contextpilot/shadow.py`) — infrastructure for sending
  both compressed and original; configurable sample rate (default 5%) (FR-005).

- **Telemetry** (`contextpilot/telemetry.py`) — metadata-only events: token
  counts, latency, quality score, model id, timestamp. No prompt or response
  content ever recorded or transmitted. Silent drop on network failure (FR-006).

- **Configuration** (`contextpilot/config.py`) — `contextpilot.yaml` + env
  var overrides. Pydantic-validated (FR-007).

- **Agent memory middleware** (`contextpilot/middleware.py`) —
  `AgentMemory.compress_handoff()` strips LangChain/CrewAI/AutoGen scaffolding
  and summarises narrative into key-point format. `preserve_keys` pass through
  unchanged (FR-008).

### Project scaffolding

- `pyproject.toml` — Hatch build, optional `[openai]`, `[anthropic]`, `[all]`, `[dev]` extras.
- `contextpilot.yaml.example` — annotated reference config.
- `.gitignore` — Python, venv, secrets, OS, IDE, Rust, dashboard build artefacts.

### Docs updated for v1.2 spec

- `CLAUDE.md` — updated doc filenames to `_v12.docx`; 4-surface table; FR-009–FR-011; AI-native distribution context; `Logs/` convention.
- `README.md` — full rewrite: 4 surfaces, quick-start, proxy env var, MCP, CLI migration, config YAML, agent memory, privacy guarantee.
- `.cursor/rules/contextpilot-project.mdc` — updated doc refs; 4-surface table.
- `AGENTS.md` — updated doc filenames.

### Test suite — 77 tests, 0 failures

| File | Tests | Covers |
|------|-------|--------|
| `test_config.py` | 5 | YAML load, env var overrides |
| `test_analyzer.py` | 10 | Classification, staleness, redundancy, density |
| `test_strategies.py` | 19 | All four strategies + agent memory |
| `test_quality.py` | 8 | Scoring, gate pass/fail |
| `test_pipeline.py` | 8 | Orchestration, fallback, zero-trust telemetry |
| `test_wrapper.py` | 14 | Provider detection, arg forwarding, compression |
| `test_middleware.py` | 5 | AgentMemory scaffolding strip, key preservation |
| `test_live_integration.py` | 8 | Real HTTP round-trip via local mock OpenAI server |

---

## Conventional commits

```
feat(core): implement Phase 1 compression library (FR-001–FR-008)
feat(config): YAML + env var configuration with Pydantic validation
feat(analyzer): TF-IDF 4-dimension block scoring and classification
feat(compressor): history summarization, RAG pruning, structural stripping
feat(quality): semantic quality gate with automatic fallback
feat(telemetry): metadata-only event collection, zero prompt content
feat(middleware): AgentMemory inter-agent handoff compression
feat(adapters): OpenAI and Anthropic drop-in SDK wrappers
feat(tests): 77-test suite including live HTTP integration tests
docs: update CLAUDE.md, README, .cursor rules for v1.2 spec
chore: add pyproject.toml, .gitignore, contextpilot.yaml.example, Logs/
```
