# ContextPilot

[![PyPI](https://img.shields.io/pypi/v/contextpilot-ai)](https://pypi.org/project/contextpilot-ai/)
[![CI](https://github.com/marsousa2/contextpilot/actions/workflows/ci.yml/badge.svg)](https://github.com/marsousa2/contextpilot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-153%20passing-brightgreen.svg)](tests/)

**Cut your LLM API costs 60-80% with one line of code.**

ContextPilot is a Python middleware library that compresses LLM context before each API call. It wraps OpenAI and Anthropic SDKs, runs a compression pipeline, and falls back to the original payload if quality drops. Works as a Python library, a local proxy, an MCP server, or a CLI migration tool.

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

## Benchmarks

Measured on realistic production conversation patterns. Each scenario uses actual repetition patterns developers encounter: accumulated context, repeated RAG chunks, repeated error traces, multi-agent handoffs.

| Scenario | Tokens | Reduction | Quality | Latency |
|----------|--------|-----------|---------|---------|
| AI coding assistant, 25 turns, growing project context | 5,810 → 1,118 | **80.8%** | 82.8/100 | 10ms |
| RAG chatbot, 18 turns, 5 retrieved chunks per query | 4,980 → 1,034 | **79.2%** | 83.4/100 | 9ms |
| Multi-agent code review, 4 agents x 6 rounds | 19,619 → 4,049 | **79.4%** | 83.9/100 | 22ms |
| Production debugging, 20 turns, repeated tracebacks | 3,814 → 928 | **75.7%** | 82.4/100 | 9ms |
| LangChain tool agent, 15 turns, 3 tool outputs/turn | 5,368 → 1,278 | **76.2%** | 83.7/100 | 8ms |
| Document Q&A, 16 turns, full spec prepended each query | 4,561 → 1,110 | **75.7%** | 83.9/100 | 8ms |

The quality gate skips compression whenever quality drops below threshold. In all 6 scenarios above, quality held at 82-84/100, well above the default 72.

**Cost at scale** (most impactful scenario: multi-agent on Claude Opus):

| Volume | Without ContextPilot | With ContextPilot | Monthly saving |
|--------|---------------------|-------------------|----------------|
| 100 calls/day | $29/day | $6/day | **$701/mo** |
| 1,000 calls/day | $294/day | $61/day | **$7,006/mo** |
| 10,000 calls/day | $2,943/day | $607/day | **$70,065/mo** |

Run `python benchmarks/benchmark_readme.py` to reproduce locally.

---

## Integration surfaces

| Surface | Entry point | Best for |
|---------|------------|----------|
| **Python library** | `contextpilot.wrap(client)` | Backend apps, RAG pipelines, agents |
| **Proxy (service)** | `contextpilot service install` | Claude Code, GPT Codex, Aider — always on |
| **Proxy (manual)** | `contextpilot proxy --port 8432` | Temporary sessions or per-project use |
| **MCP server** | `claude mcp add contextpilot -- contextpilot mcp` | Claude Desktop, Claude Code |
| **CLI migration** | `contextpilot migrate ./src/` | Existing codebases with 50+ LLM calls |

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
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=messages
)
```

That's the full integration. No other code changes required.

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
# Terminal 1 — keep this open
contextpilot proxy --port 8432

# Terminal 2 — set the env var, then use your tool normally
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
  ContextPilot — Savings Report
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
  history_window: 6        # keep last N turns verbatim
  rag_relevance_min: 0.15  # drop RAG chunks below this relevance score

shadow_testing:
  enabled: false
  sample_rate: 0.05        # fraction of calls sent both compressed and uncompressed

telemetry:
  enabled: true
  endpoint: https://api.contextpilot.org/v1/telemetry
  api_key: ${CONTEXTPILOT_API_KEY}
```

Environment variable overrides: `CONTEXTPILOT_COMPRESSION_LEVEL`, `CONTEXTPILOT_QUALITY_THRESHOLD`, `CONTEXTPILOT_API_KEY`.

---

## Privacy

Telemetry sends numerical metadata only: token counts, latency, quality scores, model IDs, timestamps. No prompt content, no response content, no PII ever leaves your environment. This is an architectural guarantee, not a policy.

See [SECURITY.md](SECURITY.md) for the full data handling policy, proxy trust model, and vulnerability reporting process.

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

MIT — see [LICENSE](https://github.com/msousa202/ContextPilot/blob/main/LICENSE).
