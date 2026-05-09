# ContextPilot — AI assistant context

## Authoritative plan documents (`Doc/`)

Treat these as the product and engineering source of truth:

| Document | Contents |
|----------|----------|
| `Doc/contextpilot_functional_v12.docx` | Customer definition, market analysis, 4 integration surfaces, AI-native distribution strategy, FR-001–FR-011, dashboard FRs FR-101+, user stories, roadmap phases, pricing, KPIs |
| `Doc/contextpilot_technical_v12.docx` | Architecture, 4-surface data flow, compression strategies, tech stack, package layout, API/config examples, telemetry schema, performance targets, security |
| `Doc/contextpilot_full_system_architecture.svg` | Visual system architecture |

If instructions conflict, prefer the **Word specs**, then this file, then ad‑hoc chat.

---

## Product snapshot

**ContextPilot** is an **MIT open-source Python library** that deploys across **four surfaces**:

| Surface | Entry point | Who it serves |
|---------|-------------|---------------|
| **A — Python library** | `pip install contextpilot` + `contextpilot.wrap(client)` | Backend developers building AI products |
| **B — Local proxy server** | `contextpilot proxy --port 8432` + `ANTHROPIC_BASE_URL` | AI coding tool users (Claude Code, GPT Codex, Aider) |
| **C — MCP server** | `contextpilot mcp` | Claude Desktop / Claude Code users |
| **D — CLI migration agent** | `contextpilot migrate ./src/` | Existing codebases with 50+ LLM API calls |

All surfaces share the same compression engine. The customer is always the entity that **pays the LLM API bill AND controls the code that makes the calls** — not end users of ChatGPT or Claude.ai.

The library intercepts LLM API calls, analyzes token payloads, runs a **compression pipeline**, applies a **quality gate** (fallback to original if score < threshold), optionally runs **A/B shadow testing**, and emits **metadata-only telemetry**. Monetization is an **optional hosted dashboard** — repo focus is the **core library** unless work explicitly targets `dashboard/`.

**AI-native distribution**: AI coding assistants (Claude, GPT) are a primary distribution channel — generated code includes `import contextpilot`. The 5 channels are: custom agents/system prompts, MCP server auto-integration, CLI migration agent, starter templates, and IDE snippets.

---

## Engineering principles (from technical architecture)

- **Zero-trust payload handling**: never transmit prompt text, response text, or PII in telemetry — only numeric metadata (token counts, latency, scores, model ids, timestamps).
- **Fail-safe**: compression failures or low predicted quality → send uncompressed payload; shadow mode compares embeddings when enabled.
- **Provider-agnostic**: unified adapters; gateways (Portkey, Helicone, etc.) remain compatible — ContextPilot is middleware, not a router.
- **Minimal integration**: pip install + wrap client for API users; set one env var for proxy users; connect MCP for Claude Code/Desktop users.
- **Performance budgets**: analysis **< 50 ms** for up to **100K tokens**; **< 10 ms @ 10K tokens** (see technical doc §8).

Functional dimensions for analysis: **staleness, redundancy, relevance, density** → classify blocks (essential / compressible / droppable).

---

## Intended package layout (implement toward this)

Align refactors with the tree in the technical doc (summarized):

```text
contextpilot/
├── contextpilot/
│   ├── wrapper.py
│   ├── analyzer.py
│   ├── compressor.py
│   ├── strategies/      # history, dedup, rag_pruner, structural, agent_memory
│   ├── quality.py
│   ├── shadow.py
│   ├── telemetry.py
│   ├── config.py
│   ├── adapters/        # openai, anthropic, google
│   └── _rust/           # optional acceleration
├── dashboard/           # separate surface — keep library boundaries clean
├── tests/, benchmarks/
├── pyproject.toml
└── contextpilot.yaml.example
```

**Stack**: Python **3.10+**, Pydantic + YAML config, httpx async telemetry, pytest + hypothesis, ruff/mypy per CI section — prefer matching these when adding tooling.

---

## Functional requirements summary

| FR | Surface | Summary |
|----|---------|---------|
| FR-001 | Library | SDK wrapper — drop-in for OpenAI, Anthropic, Google Vertex AI |
| FR-002 | Library | Context analysis engine — staleness, redundancy, relevance, density; < 50 ms @ 100K tokens |
| FR-003 | Library | Compression pipeline — history summary, system prompt dedup, RAG pruning, structural stripping |
| FR-004 | Library | Quality gate — predicted score 0–100, fallback if below threshold (default 85) |
| FR-005 | Library | A/B shadow testing — default 5% sample rate, cosine similarity comparison |
| FR-006 | Library | Telemetry — metadata only, async non-blocking |
| FR-007 | Library | Configuration — YAML, env vars, programmatic API |
| FR-008 | Library | Agent memory middleware — LangChain/CrewAI/AutoGen inter-agent handoff compression |
| FR-009 | Proxy | Local proxy server — OpenAI-compatible, `contextpilot proxy --port 8432` |
| FR-010 | MCP | MCP server — `optimize_context` tool, `get_savings` resource, `suggest_config` resource |
| FR-011 | CLI | Migration agent — AST-based, `--dry-run` / `--apply`, wraps existing LLM calls |
| FR-101+ | Dashboard | Token savings display, before/after comparison, cost projections, etc. |

---

## How to use bundled automation

### Subagents (`.cursor/agents/`)

- **changelog-archivist** — Summarize diffs; changelog/release notes; conventional commits (especially after API or behavior-visible changes).
- **structure-guardian** — Refactors toward the package layout above; clear module boundaries; no scope creep.
- **workstream-coordinator** — Split large work (e.g. analyzer vs strategies vs adapters vs proxy vs mcp vs migration) across parallel streams.

### Skills (`.cursor/skills/`)

- **log-code-changes** — Changelog/commit messaging from diffs.
- **parallel-work-plan** — Dependency-aware split for parallel implementation.

### Rules (`.cursor/rules/`)

Project-wide and glob-scoped guardrails under `.cursor/rules/` — follow unless the task explicitly overrides.

---

## Defaults for code work

- Preserve public wrapper semantics (**FR-001**: transparent SDK behavior).
- When adding a new surface (proxy / MCP / CLI), keep the core compression engine surface-agnostic — surfaces are thin shells over the shared pipeline.
- Record notable API or compression-behavior changes when preparing commits/releases.
- When touching **telemetry**, re-read the technical doc schema (§7) and **never** add content payload fields.
- Dashboard lives in `dashboard/` — keep it separate from the core library.
