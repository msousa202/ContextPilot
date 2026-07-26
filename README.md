# ContextPilot

[![PyPI](https://img.shields.io/pypi/v/contextpilot-ai)](https://pypi.org/project/contextpilot-ai/)
[![CI](https://github.com/msousa202/ContextPilot/actions/workflows/ci.yml/badge.svg)](https://github.com/msousa202/ContextPilot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

**Cut LLM context tokens 60-75%, and never pay more than you would have.**

ContextPilot is a Python middleware library that compresses LLM context before each API call. It wraps OpenAI and Anthropic SDKs, runs a compression pipeline, and falls back to the original payload if quality drops or if compression would raise your actual bill. Works as a Python library, a local proxy, an MCP server, or a CLI migration tool.

> **What token reduction means for your bill.** If your calls don't hit provider prompt caching (one-shot calls, non-repeating prefixes), token reduction translates roughly to cost reduction. If they do (most multi-turn and agent traffic), caching already bills your repeated prefix at ~0.1x, so the additional saving is much smaller, and a cache-naive compressor can make your bill *worse* by rewriting cached bytes. ContextPilot measures this and refuses compression that would cost you more. See [Cost, honestly](#cost-honestly).

**Website:** [contextpilot.org](https://contextpilot.org) | **PyPI:** [contextpilot-ai](https://pypi.org/project/contextpilot-ai/)

---

## How it works

Every API call goes through four steps:

1. **Analyze** each message block for staleness, redundancy, relevance, and density
2. **Compress** by summarizing history, deduplicating system prompts, pruning irrelevant RAG chunks, and stripping structural noise
3. **Quality gate** checks the predicted score. If it drops below the threshold (default 72/100), the original payload goes out instead
4. **Forward** the optimized (or original) payload to the provider; the response comes back unchanged

No prompt content ever leaves your machine. Telemetry is numerical metadata only.

---

## Before you install it against real code

Compression runs in your own process, in memory. Your prompts and responses go to the LLM provider you're already using and nowhere else, not to us, not to any third party. The local event log is metadata only (token counts, latency, quality scores, no prompt text) and it stays on your machine unless you deliberately opt in to a hosted dashboard, which doesn't exist yet, so there's currently nothing to opt into even if you tried. See [Privacy](#privacy) below, [SECURITY.md](SECURITY.md) for the full data-handling policy, and [docs/limitations.md](docs/limitations.md) for an honest list of tradeoffs and what this tool doesn't do.

---

## Benchmarks

Measured on realistic production conversation patterns. Each scenario uses actual repetition patterns developers encounter: accumulated context, repeated RAG chunks, repeated error traces, multi-agent handoffs.

Measured on `balanced` (the default). Fallback rows are not failures: they are the gates declining to compress, which is the behavior you want.

| Scenario | Tokens | Token reduction | Quality | Latency |
|----------|--------|-----------------|---------|---------|
| AI coding assistant, 25 turns, growing project context | 5,810 → 1,608 | **72.3%** | 84.7/100 | 29ms |
| LangChain tool agent, 15 turns, 3 tool outputs/turn | 5,368 → 1,433 | **73.3%** | 84.2/100 | 21ms |
| Multi-agent code review, 4 agents x 6 rounds | 19,619 → 6,580 | **66.5%** | 86.5/100 | 39ms |
| Document Q&A, 16 turns, full spec prepended each query | 4,561 → 1,586 | **65.2%** | 86.2/100 | 17ms |
| RAG chatbot, 18 turns, 5 retrieved chunks per query | 4,962 → 1,977 | **60.2%** | 87.6/100 | 18ms |
| Production debugging, 20 turns, repeated tracebacks | 3,810 → 3,810 | *fallback, 0%* | 89.3/100 | 13ms |
| Production support bot, 500-word system prompt | 501 → 501 | *fallback, 0%* | 94.4/100 | 6ms |

Two scenarios fall back to the original payload: the support bot is simply too short to compress profitably, and the debugging session preserves error excerpts verbatim, so the summary isn't smaller than what it replaces. Both send the original payload untouched.

On `aggressive`, the coding-assistant scenario reaches **86.8%** at quality 81.4. See [Configuration](#configuration) for the tradeoff.

Run `python benchmarks/benchmark_readme.py` to reproduce locally. These benchmarks top out around 20K tokens per conversation; see [docs/limitations.md](docs/limitations.md) for where the performance budget is and isn't independently verified yet.

---

<a name="cost-honestly"></a>
## Cost, honestly

The table above measures **tokens**, which is not what you are billed for once provider prompt caching is involved.

Prompt caching is a strict byte-prefix match: cached reads bill at roughly **0.1x** the base input price, cache writes at **1.25x**, and the first differing byte invalidates everything after it. Two consequences:

1. **On workloads without caching** (one-shot calls, prefixes that never repeat), token reduction translates roughly to cost reduction. The numbers above are a reasonable guide.
2. **On cache-warm workloads** (multi-turn chat, coding agents, anything resending a conversation), caching is already handling your repeated prefix at 0.1x. Compression can only save on top of that, so the additional saving is far smaller. Worse, a compressor that rewrites earlier conversation bytes invalidates the cache and **raises** your bill: it has to remove roughly 90% of tokens just to break even.

We measured this against our own engine on a 40-turn synthetic agent transcript with a simulated prefix cache:

| Engine | Token reduction | Cost vs. sending the payload unchanged |
|--------|-----------------|----------------------------------------|
| ContextPilot 0.3.x | 76.3% | **+87.5% (more expensive)** |
| ContextPilot 0.4.0 | 63.8% | **-8.7% (cheaper)** |

0.3.x compressed more tokens and cost more money. 0.4.0 keeps the forwarded payload byte-stable so caching keeps working, and adds a **cost gate** that prices the compressed payload against the original under the real cache multipliers and falls back when compression would be a net loss. That is why the headline claim is about tokens, with a guarantee about cost, rather than a single blended number.

Reproduce with `python benchmarks/cache_economics.py`.

**Caveat we're explicit about:** that benchmark uses a *simulated* prefix cache built from published pricing and documented cache behavior. It has not yet been validated against live API responses. Run `python benchmarks/validate_cache_costs.py` with your own key to check it against real `usage` fields on your traffic.

---

## Integration surfaces

| Surface | Entry point | Best for |
|---------|------------|----------|
| **Python library** | `contextpilot.wrap(client)` | Backend apps, RAG pipelines, agents |
| **Proxy (service)** | `contextpilot service install` | Claude Code, GPT Codex, Aider, always on |
| **Proxy (manual)** | `contextpilot proxy --port 8432` | Temporary sessions or per-project use |
| **MCP server** | `claude mcp add contextpilot -- contextpilot mcp` | Claude Desktop, Claude Code |
| **CLI migration** | `contextpilot migrate ./src/` | Existing codebases with 50+ LLM calls |

If you're using Claude Code, Codex CLI, or another agent that already does its own session-level context compaction, ContextPilot is complementary, not a replacement: it trims the payload of each individual API call, while the coding tool manages the overall conversation.

---

## Quick Start

### Python library

```bash
pip install contextpilot-ai
```

**OpenAI:**
```python
import contextpilot
from openai import OpenAI

client = contextpilot.wrap(OpenAI())

response = client.chat.completions.create(
    model="gpt-4o",
    messages=messages  # compressed transparently
)
```

**Anthropic:**
```python
import contextpilot
from anthropic import Anthropic

client = contextpilot.wrap(Anthropic())

response = client.messages.create(
    model="claude-opus-5",
    max_tokens=1024,
    messages=messages
)
```

That's the full integration. No other code changes required.

**Compress a payload without wrapping a client:**
```python
import contextpilot

result = contextpilot.compress(messages, report=True)
result.payload["messages"]      # the compressed message list
result.payload["system"]        # system prompt (unchanged, or None)
result.report.reduction_pct     # e.g. 53.4
result.report.fallback_used     # True if a gate declined to compress
result.report.fallback_reason   # "" | "no_reduction" | "quality" | "cost"
```

`compress()` treats each call as a one-shot request with no prefix cache to
preserve, so fewer tokens is simply cheaper. If you call it repeatedly over a
growing conversation and send the result to a provider with prompt caching
enabled, pass `assume_cached=True` so the cost gate protects that cache. The
proxy and wrapper surfaces already assume caching by default.

---

## Proxy for Claude Code, GPT Codex, and Aider

The proxy intercepts every request from your AI coding tool and compresses it before it reaches the provider.

### Recommended: install as a background service

One command. Runs automatically on every login, no terminal to keep open.

```bash
pipx install "contextpilot-ai[proxy]"
contextpilot service install
```

That's it. ContextPilot will:
- Start silently on login (Windows Task Scheduler / macOS launchd / Linux systemd)
- Set `ANTHROPIC_BASE_URL` permanently in your environment
- Restart automatically if it ever crashes
- Compress every Claude Code, GPT Codex, and Aider request with zero ongoing effort

Restart VS Code (or open a new terminal) once to pick up the environment variable.

```bash
contextpilot service status     # confirm it's running
contextpilot service uninstall  # remove if you ever want to stop
```

### Manual: start per session

Useful for temporary use or when you only want compression for a specific project:

```bash
# Terminal 1 (keep this open)
contextpilot proxy --port 8432

# Terminal 2 (set the env var, then use your tool normally)
export ANTHROPIC_BASE_URL=http://localhost:8432      # Linux / macOS
$env:ANTHROPIC_BASE_URL = "http://localhost:8432"    # Windows PowerShell

# OpenAI SDK / GPT Codex / Aider
export OPENAI_BASE_URL=http://localhost:8432/v1
```

`python -m contextpilot proxy --port 8432` works as a fallback if `contextpilot` is not in your PATH.

---

## MCP Server for Claude Desktop and Claude Code

Register once:

```bash
claude mcp add contextpilot -- contextpilot mcp
```

Restart Claude Code (or reload the VS Code window). ContextPilot appears as a connected MCP server. Claude will call `optimize_context` when processing large contexts, include `contextpilot.wrap()` in any LLM code it generates for you, and report savings on request via the `contextpilot://savings` resource.

To verify: ask Claude Code "What MCP tools do you have available?" and you should see `optimize_context` and `optimize_llm_code`.

---

## CLI Migration for existing codebases

```bash
# Preview what would change
contextpilot migrate ./src/ --dry-run

# Rewrite files in place
contextpilot migrate ./src/ --apply
```

Uses AST parsing (not regex) to find every `OpenAI()` and `Anthropic()` instantiation and wrap it with `contextpilot.wrap()`. Designed for codebases with 50+ LLM calls where manual refactoring isn't practical.

---

## Savings Report

```bash
contextpilot report
```

Reads the local event log (`~/.contextpilot/events.jsonl`) and shows token savings, compression ratio, quality scores, and estimated cost saved. No dashboard required.

```
  ContextPilot · Savings Report
  ────────────────────────────────────────
  Calls logged   :  142

  Token reduction
  ████████████░░░░░░░░░░░░░░░░  37.3% saved
  284,391 → 178,203  (saved 106,188 tokens)

  Quality avg    :  91.4 / 100  ✓
  Fallback rate  :  8/142  (5.6%)
  Est. cost saved:  ~$0.5309

  Log: /home/user/.contextpilot/events.jsonl
```

---

## Agent Memory Middleware

Compress inter-agent context handoffs in LangChain, CrewAI, and AutoGen pipelines that otherwise multiply tokens 5-30x:

```python
from contextpilot.middleware import AgentMemory

memory = AgentMemory(
    compression_level="aggressive",
    preserve_keys=["final_answer", "tool_outputs"],
)

compressed = memory.compress_handoff(agent_a.run(task))
result = agent_b.run(task, context=compressed)
```

---

## Configuration

Drop a `contextpilot.yaml` in your project root:

```yaml
compression:
  level: balanced          # conservative | balanced | aggressive
  quality_threshold: 72    # fallback to original if score drops below this
  history_window: 6        # keep last N turns verbatim (preset by level)
  history_epoch: 8         # boundary moves in steps of N turns, keeps the
                           # forwarded prefix cache-stable between steps
  rag_relevance_min: 0.15  # drop RAG chunks below this relevance score (preset by level)
  cache_aware: true        # refuse compression that raises cache-adjusted cost
  inject_cache_control: true  # proxy: cache breakpoint on big stable system prompts

shadow_testing:
  enabled: false
  sample_rate: 0.05        # fraction of calls sent both compressed and uncompressed

telemetry:
  enabled: true
  # The two fields below are reserved for the future hosted dashboard.
  # That service doesn't exist yet, so setting api_key today has no effect,
  # nothing gets sent anywhere. Local logging to ~/.contextpilot/events.jsonl
  # always works and needs neither of these.
  endpoint: https://api.contextpilot.org/v1/telemetry
  api_key: ${CONTEXTPILOT_API_KEY}
```

Environment variable overrides: `CONTEXTPILOT_COMPRESSION_LEVEL`, `CONTEXTPILOT_QUALITY_THRESHOLD`, `CONTEXTPILOT_API_KEY`.

---

## Privacy

Telemetry sends numerical metadata only: token counts, latency, quality scores, model IDs, timestamps. No prompt content, no response content, no PII ever leaves your environment. This is an architectural guarantee, not a policy: compression runs in-process, and the telemetry schema has no field for content, so there's nothing to accidentally send even if that changed.

Local logging (`~/.contextpilot/events.jsonl`) is on by default and never leaves your machine. Remote sync to a hosted dashboard is opt-in only, requires an explicit API key, and today that endpoint isn't live yet, so enabling it is a no-op rather than a silent data leak.

See [SECURITY.md](SECURITY.md) for the full data handling policy, proxy trust model, and vulnerability reporting process, and [docs/limitations.md](docs/limitations.md) for what this tool doesn't do yet.

---

## Installation

### Library (inside a project)

```bash
pip install contextpilot-ai                    # core library
pip install "contextpilot-ai[proxy]"           # + proxy server (starlette, uvicorn)
pip install "contextpilot-ai[openai]"          # + openai SDK
pip install "contextpilot-ai[anthropic]"       # + anthropic SDK
pip install "contextpilot-ai[mcp]"             # + MCP server
pip install "contextpilot-ai[all]"             # everything
```

### CLI / proxy (recommended: pipx)

[pipx](https://pipx.pypa.io) installs CLI tools in isolated environments and wires them into your PATH automatically, no virtualenv activation needed in new terminals:

```bash
pipx install "contextpilot-ai[proxy,mcp]"
```

**Without pipx:**

```bash
pip install "contextpilot-ai[proxy,mcp]"
```

If `contextpilot` is not recognized after install, use the module form:

```bash
python -m contextpilot service install
python -m contextpilot proxy --port 8432
python -m contextpilot mcp
```

---

## Contributing

See [CONTRIBUTING.md](https://github.com/msousa202/ContextPilot/blob/main/CONTRIBUTING.md).

---

## License

MIT, see [LICENSE](https://github.com/msousa202/ContextPilot/blob/main/LICENSE).
