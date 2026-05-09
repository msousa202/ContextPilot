# ContextPilot

Python middleware that compresses and optimizes LLM context before each API call — lower token costs for apps and agents, with quality scoring and safe fallback. Wraps OpenAI, Anthropic, and Google SDKs with minimal code changes.

## Integration Surfaces

ContextPilot deploys wherever you write LLM-powered code. All surfaces share the same compression engine.

| Surface | Entry point | Works with |
|---------|-------------|------------|
| **Python library** | `pip install contextpilot` | Any Python backend |
| **Local proxy** | `contextpilot proxy --port 8432` | Claude Code, GPT Codex, Aider — any tool with a custom base URL |
| **MCP server** | `contextpilot mcp` | Claude Desktop, Claude Code |
| **CLI migration** | `contextpilot migrate ./src/` | Existing codebases — wraps all LLM calls automatically |

## Quick Start

```python
pip install contextpilot
```

```python
# OpenAI
import contextpilot
from openai import OpenAI

client = OpenAI()
pilot = contextpilot.wrap(client)

response = pilot.chat.completions.create(
    model="gpt-4o",
    messages=messages  # compressed transparently
)
```

```python
# Anthropic
from anthropic import Anthropic

client = Anthropic()
pilot = contextpilot.wrap(client)

response = pilot.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=messages
)
```

## Proxy for AI Coding Tools

Route Claude Code, GPT Codex, or Aider through the compression middleware by setting one environment variable:

```bash
contextpilot proxy --port 8432
export ANTHROPIC_BASE_URL=http://localhost:8432
```

Every subsequent AI coding prompt is now compressed. The coding assistant behaves identically — just uses fewer tokens.

## MCP Server

```bash
contextpilot mcp
```

Connects to Claude Desktop and Claude Code. Exposes `optimize_context`, `get_savings`, and `suggest_config` tools. Claude automatically applies compression when context is large — no workflow changes required.

## CLI Migration

```bash
contextpilot migrate ./src/ --dry-run   # preview changes
contextpilot migrate ./src/ --apply     # refactor in place
```

Uses AST parsing (not regex) to safely find and wrap all LLM API calls in an existing codebase. Designed for codebases with 50+ LLM calls where manual refactoring is prohibitive.

## Configuration

```yaml
# contextpilot.yaml
compression:
  level: balanced          # conservative | balanced | aggressive
  quality_threshold: 85    # fallback to uncompressed if score drops below this
  history_window: 6        # keep last N conversation turns verbatim
  rag_relevance_min: 0.15  # drop RAG chunks below this relevance score

shadow_testing:
  enabled: true
  sample_rate: 0.05        # 5% of calls sent both compressed and uncompressed

telemetry:
  enabled: true
  endpoint: https://api.contextpilot.dev/v1/telemetry
  api_key: ${CONTEXTPILOT_API_KEY}
```

## Agent Memory Middleware

For multi-agent workflows (LangChain, CrewAI, AutoGen), compress inter-agent handoffs that would otherwise multiply tokens 5–30x:

```python
from contextpilot.middleware import AgentMemory

memory = AgentMemory(
    compression_level="aggressive",
    preserve_keys=["final_answer", "tool_outputs"],
)

agent_a_output = agent_a.run(task)
compressed = memory.compress_handoff(agent_a_output)
agent_b_output = agent_b.run(task, context=compressed)
```

## Privacy

Telemetry transmits **numerical metadata only** — token counts, latency, quality scores, model IDs, timestamps. No prompt content, no response content, no PII ever leaves your environment.

## License

MIT
