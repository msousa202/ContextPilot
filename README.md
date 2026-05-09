# ContextPilot

[![PyPI](https://img.shields.io/pypi/v/contextpilot-ai)](https://pypi.org/project/contextpilot-ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-109%20passing-brightgreen.svg)](tests/)

**Cut your LLM API costs 30–70% with one line of code.**

ContextPilot is a Python middleware library that compresses LLM context before each API call — transparently, with automatic quality fallback. It wraps OpenAI, Anthropic, and Google SDKs and deploys across four surfaces: Python library, local proxy, MCP server, and CLI migration agent.

**Website:** [contextpilot.org](https://contextpilot.org) · **PyPI:** [contextpilot-ai](https://pypi.org/project/contextpilot-ai/)

---

## How it works

Every LLM API call passes through a compression pipeline:

1. **Analyze** — scores each message block for staleness, redundancy, relevance, and density
2. **Compress** — summarizes history, deduplicates system prompts, prunes irrelevant RAG chunks, strips structural noise
3. **Quality gate** — if predicted quality drops below threshold (default 85/100), the original payload is sent instead
4. **Forward** — the optimized (or original) payload goes to the provider, response comes back unchanged

Zero prompt content ever leaves your environment. Telemetry is numerical metadata only.

---

## Integration Surfaces

All surfaces share the same compression engine.

| Surface | Command | Works with |
|---------|---------|------------|
| **Python library** | `pip install contextpilot-ai` | Any Python backend |
| **Local proxy** | `contextpilot proxy --port 8432` | Claude Code, GPT Codex, Aider |
| **MCP server** | `contextpilot mcp` | Claude Desktop, Claude Code |
| **CLI migration** | `contextpilot migrate ./src/` | Existing codebases with 50+ LLM calls |

---

## Quick Start

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

## Local Proxy — for Claude Code, GPT Codex, Aider

Set one environment variable and every prompt from your AI coding tool is compressed automatically:

```bash
# Start the proxy
contextpilot proxy --port 8432

# Claude Code / Anthropic SDK
export ANTHROPIC_BASE_URL=http://localhost:8432

# OpenAI SDK / GPT Codex
export OPENAI_BASE_URL=http://localhost:8432/v1
```

The coding assistant behaves identically — same responses, fewer tokens billed.

Requires: `pip install contextpilot-ai[proxy]`

---

## MCP Server — for Claude Desktop and Claude Code

```bash
contextpilot mcp
```

Exposes `optimize_context`, `get_savings`, and `suggest_config` to Claude. Claude automatically applies compression when context is large — no workflow changes required.

---

## CLI Migration — retrofit an existing codebase

```bash
# Preview what would change
contextpilot migrate ./src/ --dry-run

# Rewrite files in place
contextpilot migrate ./src/ --apply
```

Uses AST parsing (not regex) to safely find and wrap every OpenAI and Anthropic client instantiation. Designed for codebases with 50+ LLM calls where manual refactoring is impractical.

---

## Savings Report

```bash
contextpilot report
```

Reads the local event log (`~/.contextpilot/events.jsonl`) and shows token savings, compression ratio, quality scores, and estimated cost saved — no dashboard needed.

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

---

## Installation options

```bash
pip install contextpilot-ai           # core library
pip install contextpilot-ai[proxy]    # + proxy server (fastapi, uvicorn)
pip install contextpilot-ai[openai]   # + openai SDK
pip install contextpilot-ai[anthropic] # + anthropic SDK
pip install contextpilot-ai[all]      # everything
```

---

## License

MIT — see [LICENSE](LICENSE).
