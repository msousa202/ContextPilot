# ContextPilot + Claude Code — Integration Guide

## What is ContextPilot?

ContextPilot sits between your code and Anthropic's API. Before every request reaches Claude, it analyzes the message payload and removes redundant, stale, or irrelevant content — then sends a leaner version. If compression would hurt quality, it silently falls back to the original. You always get the same quality response, at a lower token cost.

```
Your code / Claude Code
        │
        ▼
  ContextPilot          ← compression happens here (local, in-memory)
        │
        ▼
  Anthropic API         ← smaller payload, lower bill
        │
        ▼
  Response (unchanged)  ← comes back to you exactly as normal
```

No content ever leaves your machine except what goes to Anthropic — and that payload is smaller than before.

---

## How compression works

Every message payload passes through four stages:

| Stage | What it does | Example saving |
|-------|-------------|----------------|
| **History summarization** | Keeps the last 6 turns verbatim, collapses older turns into a compact summary | 40–60% on long conversations |
| **System prompt dedup** | Detects unchanged system prompts sent repeatedly across calls | 10–30% on multi-turn apps |
| **RAG chunk pruning** | Scores each retrieved document chunk against the current query, removes low-relevance ones | 20–50% on RAG pipelines |
| **Structural stripping** | Removes excessive blank lines, repeated markdown headers, empty XML tags | 5–15% on structured prompts |

After compression, a **quality gate** predicts the preservation score (0–100). If it falls below 85, the original payload is sent instead. You never get a degraded response — only smaller or identical.

---

## Two ways to use it with Claude Code

### Mode 1 — Proxy (transparent, automatic)

Every message you or Claude Code sends is compressed before hitting Anthropic. You change nothing about your workflow.

```
Claude Code (VS Code or terminal)
        │  normal messages
        ▼
  ContextPilot Proxy (localhost:8432)   ← intercepts automatically
        │  compressed messages
        ▼
  Anthropic API
```

**Best for:** cutting your actual API bill. Every prompt — code generation, explanation, refactor — goes through compression without any extra steps.

The proxy has two setup options:

| Option | How | Persistent? |
|--------|-----|-------------|
| **Service** (recommended) | `contextpilot service install` | Yes — starts on every login automatically |
| **Manual** | `contextpilot proxy --port 8432` | Session only — terminal must stay open |

---

### Mode 2 — MCP Server (tool-based, opt-in)

ContextPilot runs as an MCP server. Claude sees it as a set of tools it can call. Claude decides when to use them — it does not intercept automatically.

```
Claude Code session
        │
        ├─ calls optimize_context(messages) ──► ContextPilot compresses ──► returns result
        ├─ calls optimize_llm_code(provider) ──► returns code with wrap() already included
        └─ reads contextpilot://savings ──► returns your savings summary
```

**Best for:** AI-native distribution — when Claude generates LLM code for you or others, it includes `contextpilot.wrap()` automatically because the `optimize_llm_code` tool is available.

---

## Setup — Claude Code in VS Code (extension)

### Proxy — service install (recommended)

Run once. The proxy starts automatically on every login from this point on.

```powershell
# Install with pipx so the CLI is always in PATH
pipx install "contextpilot-ai[proxy]"

# Register as a startup service + set ANTHROPIC_BASE_URL permanently
contextpilot service install
```

Restart VS Code once to pick up the new `ANTHROPIC_BASE_URL` environment variable. After that, every Claude Code session in VS Code automatically routes through ContextPilot — no terminal to keep open, no command to remember.

To confirm it's running:

```powershell
contextpilot service status
```

To remove it:

```powershell
contextpilot service uninstall
```

---

### Proxy — manual (per session)

Use this if you only want compression for a specific session, or if you prefer not to install a startup service.

Open a terminal inside VS Code and run:

```powershell
contextpilot proxy --port 8432
# or, if contextpilot is not in PATH:
python -m contextpilot proxy --port 8432
```

Keep this terminal open. In any other terminal (or in VS Code settings), set:

```powershell
$env:ANTHROPIC_BASE_URL = "http://localhost:8432"
```

Every Claude Code request in VS Code now goes through compression for as long as the proxy is running.

---

### MCP server setup

Run once in any terminal:

```powershell
claude mcp add contextpilot -- contextpilot mcp
```

Reload the VS Code window (Ctrl+Shift+P → "Developer: Reload Window"). ContextPilot now appears as a connected MCP server. Claude will:

- Call `optimize_context` when it processes large contexts
- Include `contextpilot.wrap()` in LLM code it generates for you
- Report savings on request via the `contextpilot://savings` resource

To verify it connected, open a Claude Code chat in VS Code and ask:
> "What MCP tools do you have available?"

You should see `optimize_context` and `optimize_llm_code` in the list.

---

## Setup — Claude Code on Console / CMD

### Proxy — service install (recommended)

```powershell
pipx install "contextpilot-ai[proxy]"
contextpilot service install
```

Open a new terminal. `ANTHROPIC_BASE_URL` is now set permanently. Just run `claude` — every session is automatically compressed.

---

### Proxy — manual (per session)

Open a first terminal and start the proxy:

```powershell
contextpilot proxy --port 8432
```

Open a second terminal, set the env var, then use Claude Code normally:

```powershell
# PowerShell
$env:ANTHROPIC_BASE_URL = "http://localhost:8432"
claude
```

```cmd
:: Windows CMD
set ANTHROPIC_BASE_URL=http://localhost:8432
claude
```

```bash
# Linux / macOS
export ANTHROPIC_BASE_URL=http://localhost:8432
claude
```

Everything you type in the Claude Code session is now compressed before reaching Anthropic.

---

### MCP server setup

```powershell
claude mcp add contextpilot -- contextpilot mcp
```

Start a new Claude Code session:

```powershell
claude
```

The tools are available immediately. You can ask Claude to call them explicitly:

> "Call optimize_context with these messages: [...]"
> "Generate an Anthropic API call using optimize_llm_code"
> "Read contextpilot://savings and show me my token savings"

---

## Use cases

### 1. Daily Claude Code usage (service — set and forget)

Install once. Every session for the rest of time is compressed automatically.

```powershell
pipx install "contextpilot-ai[proxy]"
contextpilot service install
# restart VS Code once
# done — nothing else to do, ever
```

Long sessions naturally accumulate context — previous file contents, error messages, explanations — that gets re-sent with every message. With the service running, older turns are summarized and repeated content is deduplicated transparently on every request.

---

### 2. Building a RAG chatbot (library)

You're building a customer support bot. Each user message retrieves 5–10 document chunks from a vector database and sends them all to Claude. Most chunks aren't relevant to the specific question.

**Without ContextPilot:** all 10 chunks sent every time.
**With ContextPilot:** chunks scored for relevance, only the top 2–3 sent.

```python
import contextpilot
from anthropic import Anthropic

client = contextpilot.wrap(Anthropic())

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=messages_with_rag_chunks  # pruned automatically
)
```

---

### 3. Multi-agent pipeline (agent memory middleware)

You have a 4-agent research pipeline where each agent passes its full output to the next. By turn 3, the context is 20,000 tokens of reasoning chains, tool logs, and scaffolding.

**Without ContextPilot:** each agent receives the full accumulated output of all previous agents.
**With ContextPilot:** handoffs are compressed to key decisions, structured outputs, and final answers. Scaffolding stripped.

```python
from contextpilot.middleware import AgentMemory

memory = AgentMemory(
    compression_level="aggressive",
    preserve_keys=["final_answer", "tool_outputs", "decisions"],
)

output_a = agent_a.run(task)
compressed = memory.compress_handoff(output_a)  # strips reasoning chains
output_b = agent_b.run(task, context=compressed)
```

---

### 4. Migrating an existing codebase (CLI)

You have a production codebase with 80+ LLM API calls. Wrapping each one manually would take days.

```powershell
# Preview what changes would be made
contextpilot migrate ./src/ --dry-run

# Apply all changes at once
contextpilot migrate ./src/ --apply
```

Uses AST parsing — it finds `OpenAI()` and `Anthropic()` instantiations and wraps them with `contextpilot.wrap()`. Safe on production code.

---

### 5. Checking your savings

After any usage (service, proxy, library, or MCP):

```powershell
contextpilot report
```

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

## What gets compressed and what does not

| Content type | Compressed? | Why |
|-------------|-------------|-----|
| Repeated questions/answers in history | Yes | Redundancy detection |
| Old conversation turns (beyond window) | Yes — summarized | History strategy |
| Unchanged system prompts (multi-call) | Yes — deduplicated | Dedup strategy |
| Low-relevance RAG chunks | Yes — pruned | RAG pruner |
| Excess whitespace, empty tags | Yes | Structural stripping |
| Recent 6 turns | No | Kept verbatim for context |
| The current user message | Never | Always sent unchanged |
| Your API keys / credentials | Never touched | Passed through headers |
| Response from Claude | Never | Returned unchanged |

---

## Verifying no content leaks

ContextPilot's telemetry writes only numerical metadata to `~/.contextpilot/events.jsonl`:

```json
{
  "event_id": "uuid",
  "timestamp": "2026-05-09T...",
  "provider": "anthropic",
  "model": "claude-sonnet-4-20250514",
  "tokens_input_original": 1842,
  "tokens_input_compressed": 1103,
  "quality_score": 91.4,
  "fallback_triggered": false
}
```

No `content`, `text`, `prompt`, or `response` fields exist in the schema. You can inspect the file at any time:

```powershell
cat ~/.contextpilot/events.jsonl
```

Remote telemetry (to `api.contextpilot.org`) only fires if you explicitly set `CONTEXTPILOT_API_KEY`. Without it, all data stays local.

For the full security model, see [SECURITY.md](../SECURITY.md).
