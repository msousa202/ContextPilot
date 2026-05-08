# ContextPilot — AI assistant context

## Authoritative plan documents (`Doc/`)

Treat these as the product and engineering source of truth:

| Document | Contents |
|----------|----------|
| `Doc/contextpilot_functional_doc.docx` | Functional requirements (FR-001–FR-008 library; FR-101+ dashboard), user stories, roadmap phases, pricing, KPIs |
| `Doc/contextpilot_technical_doc.docx` | Architecture, data flow, compression strategies, tech stack, package layout, API/config examples, telemetry schema, security |
| `Doc/contextpilot_full_system_architecture.svg` | Visual system architecture |

If instructions conflict, prefer the **Word specs**, then this file, then ad‑hoc chat.

---

## Product snapshot

**ContextPilot** is an **MIT open-source Python library** that wraps OpenAI, Anthropic, and Google SDKs (minimal integration change), analyzes each outgoing payload, runs a **compression pipeline**, applies a **quality gate** with fallback to the original payload, optionally runs **A/B shadow testing**, and emits **metadata-only telemetry**. Monetization is **optional hosted dashboard** tiers (see functional doc)—the repo focus is the **core library** unless work explicitly targets `dashboard/`.

---

## Engineering principles (from technical architecture)

- **Zero-trust payload handling**: never transmit prompt text, response text, or PII in telemetry—only numeric metadata (token counts, latency, scores, model ids, timestamps).
- **Fail-safe**: compression failures or low predicted quality → send uncompressed payload; shadow mode compares embeddings when enabled.
- **Provider-agnostic**: unified adapters; gateways (Portkey, Helicone, etc.) remain compatible—ContextPilot is middleware, not primarily a router.
- **Performance budgets**: analysis **< 50 ms** for up to **100K tokens**; compression overhead targets per technical doc (e.g. **< 10 ms @ 10K**, **< 50 ms @ 100K** tokens).

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
├── tests/, benchmarks/
├── pyproject.toml
└── contextpilot.yaml.example
```

Dashboard may live in **`dashboard/`** (separate surface); keep library boundaries clean.

**Stack**: Python **3.10+**, Pydantic + YAML config, httpx async telemetry, pytest + hypothesis, ruff/mypy per CI section—prefer matching these when adding tooling.

---

## How to use bundled automation

### Subagents (`.cursor/agents/`)

- **changelog-archivist** — Summarize diffs; changelog/release notes; conventional commits (especially after API or behavior-visible changes).
- **structure-guardian** — Refactors toward the package layout above; clear module boundaries; no scope creep.
- **workstream-coordinator** — Split large work (e.g. analyzer vs strategies vs adapters vs telemetry) across parallel streams.

### Skills (`.cursor/skills/`)

- **log-code-changes** — Changelog/commit messaging from diffs.
- **parallel-work-plan** — Dependency-aware split for parallel implementation.

### Rules (`.cursor/rules/`)

Project-wide and glob-scoped guardrails under `.cursor/rules/`—follow unless the task explicitly overrides.

---

## Defaults for code work

- Preserve public wrapper semantics (**FR-001**: transparent SDK behavior).
- Record notable API or compression-behavior changes when preparing commits/releases.
- When touching **telemetry**, re-read the technical doc schema and **never** add content payload fields.
