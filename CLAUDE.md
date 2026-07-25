# ContextPilot: AI assistant context

## Authoritative plan documents (`Doc/`)

Treat these as the product and engineering source of truth:

| Document | Contents |
|----------|----------|
| `Doc/contextpilot_functional_v12.docx` | Customer definition, market analysis, 4 integration surfaces, AI-native distribution strategy, FR-001–FR-011, dashboard FRs FR-101+, user stories, roadmap phases, pricing, KPIs |
| `Doc/contextpilot_technical_v12.docx` | Architecture, 4-surface data flow, compression strategies, tech stack, package layout, API/config examples, telemetry schema, performance targets, security |
| `Doc/contextpilot_full_system_architecture.svg` | Visual system architecture |

If instructions conflict, prefer the **Word specs**, then this file, then ad‑hoc chat.

---

## Current status

| Item | Value |
|------|-------|
| **PyPI version** | `contextpilot-ai 0.3.0` |
| **Phase** | Phase 2: Beta launch in progress |
| **Phase 1** | Complete, all 4 surfaces shipped |
| **Phase 2 step 1** | Done, contextpilot.org landing page live |
| **Phase 2 step 2** | Done, dashboard waitlist live |
| **Phase 2 step 3** | Next: beta outreach (HN, early access list) |
| **GitHub** | `msousa202/ContextPilot`, CI green, dependabot active |

Known spec-vs-shipped gaps to keep in mind while working here: the quality gate default is `72` in shipped code, not the `85` some early planning material still cites (README and `contextpilot.yaml.example` are the source of truth); shadow testing (FR-005) is implemented but not yet called from `Pipeline.optimize()`, so enabling it in config currently has no effect. Both are tracked as GitHub issues rather than fixed silently. See `docs/limitations.md` for the full, current list.

---

## Writing style

No em dashes (Unicode U+2014) anywhere: not in chat replies, not in docs, not in code comments or CLI/MCP output strings. Use a period, comma, colon, or a plain hyphen instead, or restructure the sentence. This mirrors the `Contextpilot-site` repo's `BRAND.md` rule; keep both in sync. Tone across all project writing: professional but plain, like a developer explaining something to another developer, not marketing copy.

---

## Official logo

`assets/logo.svg`: SVG, brand color `#C8A45A` (gold/amber), geometric converging lines to a circle motif.

The same source lives at `src/app/icon.svg` in the `Contextpilot-site` repo. Keep them in sync if the logo changes.

---

## Product snapshot

**ContextPilot** is an **MIT open-source Python library** that deploys across **four surfaces**:

| Surface | Entry point | Who it serves |
|---------|-------------|---------------|
| **A: Python library** | `pip install contextpilot` + `contextpilot.wrap(client)` | Backend developers building AI products |
| **B: Local proxy server** | `contextpilot proxy --port 8432` + `ANTHROPIC_BASE_URL` | AI coding tool users (Claude Code, GPT Codex, Aider) |
| **C: MCP server** | `contextpilot mcp` | Claude Desktop / Claude Code users |
| **D: CLI migration agent** | `contextpilot migrate ./src/` | Existing codebases with 50+ LLM API calls |

All surfaces share the same compression engine. The customer is always the entity that **pays the LLM API bill AND controls the code that makes the calls**, not end users of ChatGPT or Claude.ai.

The library intercepts LLM API calls, analyzes token payloads, runs a **compression pipeline**, applies a **quality gate** (fallback to original if score < threshold), optionally runs **A/B shadow testing**, and emits **metadata-only telemetry**. Monetization is an **optional hosted dashboard**; repo focus is the **core library** unless work explicitly targets `dashboard/`.

**AI-native distribution**: AI coding assistants (Claude, GPT) are a primary distribution channel: generated code includes `import contextpilot`. The 5 channels are: custom agents/system prompts, MCP server auto-integration, CLI migration agent, starter templates, and IDE snippets.

Also worth knowing: as of mid-2026 there's a different, unrelated open-source project also named "ContextPilot" (`github.com/EfficientContext/ContextPilot`, inference-engine-level context optimization for SGLang/vLLM/llama.cpp). Worth a disambiguation line in anything written for external audiences (launch posts, HN, README) so readers land on the right repo.

---

## Engineering principles (from technical architecture)

- **Zero-trust payload handling**: never transmit prompt text, response text, or PII in telemetry, only numeric metadata (token counts, latency, scores, model ids, timestamps).
- **Fail-safe**: compression failures or low predicted quality → send uncompressed payload; shadow mode compares embeddings when enabled.
- **Provider-agnostic**: unified adapters; gateways (Portkey, Helicone, etc.) remain compatible; ContextPilot is middleware, not a router.
- **Minimal integration**: pip install + wrap client for API users; set one env var for proxy users; connect MCP for Claude Code/Desktop users.
- **Performance budgets**: analysis **< 50 ms** for up to **100K tokens**; **< 10 ms @ 10K tokens** (see technical doc §8). Not yet independently verified by an assertion-backed benchmark at that scale, see `docs/limitations.md`.

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
├── assets/              # logo.svg and other brand assets
├── dashboard/           # separate surface, keep library boundaries clean
├── tests/, benchmarks/
├── pyproject.toml
└── contextpilot.yaml.example
```

Note: `adapters/` currently ships `openai` and `anthropic` only, no `google` adapter yet.

**Stack**: Python **3.10+**, Pydantic + YAML config, httpx async telemetry, pytest + hypothesis, ruff/mypy per CI; prefer matching these when adding tooling.

---

## Functional requirements summary

| FR | Surface | Summary |
|----|---------|---------|
| FR-001 | Library | SDK wrapper, drop-in for OpenAI, Anthropic, Google Vertex AI (Vertex adapter not yet built) |
| FR-002 | Library | Context analysis engine: staleness, redundancy, relevance, density; < 50 ms @ 100K tokens |
| FR-003 | Library | Compression pipeline: history summary, system prompt dedup, RAG pruning, structural stripping |
| FR-004 | Library | Quality gate: predicted score 0-100, fallback if below threshold (default 72) |
| FR-005 | Library | A/B shadow testing: default 5% sample rate, cosine similarity comparison. Implemented in `shadow.py` but not yet wired into `Pipeline.optimize()` |
| FR-006 | Library | Telemetry: metadata only, async non-blocking |
| FR-007 | Library | Configuration: YAML, env vars, programmatic API |
| FR-008 | Library | Agent memory middleware: LangChain/CrewAI/AutoGen inter-agent handoff compression |
| FR-009 | Proxy | Local proxy server: OpenAI-compatible, `contextpilot proxy --port 8432` |
| FR-010 | MCP | MCP server: `optimize_context` tool, `get_savings` resource, `suggest_config` resource |
| FR-011 | CLI | Migration agent: AST-based, `--dry-run` / `--apply`, wraps existing LLM calls |
| FR-101+ | Dashboard | Token savings display, before/after comparison, cost projections, etc. |

---

## How to use bundled automation

### Subagents (`.cursor/agents/`)

- **changelog-archivist**: Summarize diffs; changelog/release notes; conventional commits (especially after API or behavior-visible changes).
- **structure-guardian**: Refactors toward the package layout above; clear module boundaries; no scope creep.
- **workstream-coordinator**: Split large work (e.g. analyzer vs strategies vs adapters vs proxy vs mcp vs migration) across parallel streams.

### Skills (`.cursor/skills/`)

- **log-code-changes**: Changelog/commit messaging from diffs.
- **parallel-work-plan**: Dependency-aware split for parallel implementation.

### Rules (`.cursor/rules/`)

Project-wide and glob-scoped guardrails under `.cursor/rules/`, follow unless the task explicitly overrides.

---

## Change logging (`Logs/`)

Every meaningful session of work gets a log file in `Logs/`:

| Convention | Example |
|------------|---------|
| Phase work | `Logs/phase-1-foundation.md` |
| Feature additions | `Logs/feat-proxy-server.md` |
| Bug fixes / refactors | `Logs/fix-quality-gate.md` |

Each log file must include: date, what changed (user-visible first), FR references where applicable, and the conventional commit lines. Use the **changelog-archivist** subagent or **log-code-changes** skill to produce entries.

---

## Defaults for code work

- Preserve public wrapper semantics (**FR-001**: transparent SDK behavior).
- When adding a new surface (proxy / MCP / CLI), keep the core compression engine surface-agnostic: surfaces are thin shells over the shared pipeline.
- After any meaningful change, add or update a file in `Logs/` before closing the session.
- When touching **telemetry**, re-read the technical doc schema (§7) and **never** add content payload fields.
- Dashboard lives in `dashboard/`, keep it separate from the core library.
