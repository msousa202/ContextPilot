# ContextPilot

[![PyPI](https://img.shields.io/pypi/v/contextpilot-ai)](https://pypi.org/project/contextpilot-ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-145%20passing-brightgreen.svg)](tests/)

**Cut your LLM API costs 30–70% with one line of code.**

ContextPilot is a Python middleware library that compresses LLM context before each API call — transparently, with automatic quality fallback. It wraps OpenAI and Anthropic SDKs and runs across four surfaces: Python library, local proxy, MCP server, and CLI migration agent.

**Website:** [contextpilot.org](https://contextpilot.org) · **PyPI:** [contextpilot-ai](https://pypi.org/project/contextpilot-ai/)

---

## How it works

Every LLM API call passes through a four-stage pipeline:

1. **Analyze** — scores each message block for staleness, redundancy, relevance, and density
2. **Compress** — summarizes history, deduplicates system prompts, prunes irrelevant RAG chunks, strips structural noise
3. **Quality gate** — if predicted quality drops below threshold (default 85/100), the original payload is sent instead
4. **Forward** — the optimized (or original) payload goes to the provider; response comes back unchanged

Zero prompt content ever leaves your environment. Telemetry is numerical metadata only.

---

## Integration surfaces

| Surface | Entry point | Best for |
|---------|------------|----------|
| **Python library** | `contextpilot.wrap(client)` | Backend apps, RAG pipelines, agents |
| **Proxy — service** | `contextpilot service install` | Claude Code, GPT Codex, Aider — always on |
| **Proxy — manual** | `contextpilot proxy --port 8432` | Temporary sessions or per-project use |
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

## Proxy — for Claude Code, GPT Codex, Aider

The proxy intercepts every request from your AI coding tool and compresses it before it reaches the provider.

### Recommended: install as a background service

One command. Runs automatically on every login. No terminal to keep open.

```bash
pipx install "contextpilot-ai[proxy]"
contextpilot service install
```

That's it. ContextPilot now:
- Starts silently on login (Windows Task Scheduler / macOS launchd / Linux systemd)
- Sets `ANTHROPIC_BASE_URL` permanently in your environment
- Restarts itself automatically if it ever crashes
- Compresses every Claude Code, GPT Codex, and Aider request with zero ongoing effort

Restart VS Code (or open a new terminal) once to pick up the environment variable. From that point, every session is automatically compressed.

```bash
contextpilot service status     # confirm it's running
contextpilot service uninstall  # remove if you ever want to stop
```

### Manual: start per session

Useful for temporary use or when you only want compression for a specific project:

```bash
# Terminal 1 — keep this open
contextpilot proxy --port 8432

# Terminal 2 — set env var, then use Claude Code normally
export ANTHROPIC_BASE_URL=http://localhost:8432      # Linux / macOS
$env:ANTHROPIC_BASE_URL = "http://localhost:8432"    # Windows PowerShell

# OpenAI SDK / GPT Codex / Aider
export OPENAI_BASE_URL=http://localhost:8432/v1
```

`python -m contextpilot proxy --port 8432` works as a fallback if `contextpilot` is not in your PATH.

---

## MCP Server — for Claude Desktop and Claude Code

Register once:

```bash
claude mcp add contextpilot -- contextpilot mcp
```

Restart Claude Code (or reload the VS Code window). ContextPilot appears as a connected MCP server. Claude will:

- Call `optimize_context` when processing large contexts
- Include `contextpilot.wrap()` in any LLM code it generates for you
- Report savings on request via the `contextpilot://savings` resource

To verify: ask Claude Code *"What MCP tools do you have available?"* — you should see `optimize_context` and `optimize_llm_code`.

---

## CLI Migration — retrofit an existing codebase

```bash
# Preview what would change
contextpilot migrate ./src/ --dry-run

# Rewrite files in place
contextpilot migrate ./src/ --apply
```

Uses AST parsing (not regex) to find every `OpenAI()` and `Anthropic()` instantiation and wrap it with `contextpilot.wrap()`. Designed for codebases with 50+ LLM calls where manual refactoring is impractical.

---

## Savings Report

```bash
contextpilot report
```

Reads the local event log (`~/.contextpilot/events.jsonl`) and shows token savings, compression ratio, quality scores, and estimated cost saved — no dashboard required.

```
  ContextPilot — Savings Report
  ------------------------------------
  Total calls logged   : 142
  Fallback rate        : 8/142 (5.6%)
  Tokens in (original) : 284,391
  Tokens in (sent)     : 178,203
  Tokens saved         : 106,188  (37.3% reduction)
  Avg quality score    : 91.4/100
  Est. cost saved      : $0.5309
```

---

## Agent Memory Middleware

Compress inter-agent context handoffs in LangChain, CrewAI, and AutoGen pipelines that otherwise multiply tokens 5–30×:

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
  quality_threshold: 85    # fallback to original if score drops below this
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

Telemetry sends **numerical metadata only**: token counts, latency, quality scores, model IDs, timestamps. No prompt content, no response content, no PII ever leaves your environment. This is an architectural guarantee, not a policy.

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

[pipx](https://pipx.pypa.io) installs CLI tools in isolated environments and wires them into your PATH automatically — no virtualenv activation needed in new terminals:

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
