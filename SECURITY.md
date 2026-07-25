# Security

ContextPilot sits between your code and LLM providers. This document explains exactly what it does and does not do with your data, and how to report vulnerabilities.

---

## What ContextPilot does with your data

### Prompt and response content

**ContextPilot never stores, logs, or transmits your prompt or response content.**

Compression runs entirely in-process, in-memory. The library reads message payloads to analyze token structure, applies compression, and passes the result directly to the provider. Nothing is written to disk, no content field ever appears in any log file, and no content is included in telemetry.

This is an architectural guarantee: the telemetry schema (`TelemetryEvent`) has no `content`, `text`, `prompt`, or `response` field. You can verify this by reading [`contextpilot/telemetry.py`](contextpilot/telemetry.py).

### API keys and credentials

**ContextPilot never reads, stores, or modifies your API keys.**

When using the **Python library** (`contextpilot.wrap()`), authentication is handled entirely by the underlying SDK. ContextPilot intercepts only the message payload, not the request headers that carry credentials.

When using the **proxy server** (`contextpilot proxy`), the proxy forwards your `Authorization` header directly to the provider without reading or logging it. The `_forward_headers()` function strips only standard hop-by-hop headers (Host, Connection, Transfer-Encoding, etc.); API key headers pass through unmodified.

### Local telemetry

Every API call writes one line to `~/.contextpilot/events.jsonl`. This file contains only:

```json
{
  "event_id": "uuid",
  "timestamp": "2026-05-09T...",
  "provider": "anthropic",
  "model": "claude-sonnet-4-20250514",
  "tokens_input_original": 1842,
  "tokens_input_compressed": 1103,
  "tokens_output": 0,
  "latency_ms": 0.0,
  "compression_ms": 14.2,
  "quality_score": 91.4,
  "strategies_applied": ["history_summarizer"],
  "fallback_triggered": false,
  "shadow_similarity": null,
  "cost_original_usd": 0.0,
  "cost_compressed_usd": 0.0
}
```

No `content`, `text`, `prompt`, or `messages` field exists or will ever be added to this schema. You can inspect the file at any time:

```bash
cat ~/.contextpilot/events.jsonl
```

### Remote telemetry

Remote telemetry to `api.contextpilot.org` is **opt-in and disabled by default**.

It only fires when you explicitly set `CONTEXTPILOT_API_KEY` or add `api_key` to `contextpilot.yaml`. Without an API key, all data stays local. Even when enabled, only the same numerical metadata fields listed above are transmitted, never content.

As of this writing, the hosted dashboard and its ingestion endpoint aren't live yet. Setting an API key today doesn't send your data anywhere; it just has nothing to connect to. This will be updated the day that changes.

---

## Proxy trust model

The proxy binds to `127.0.0.1` (localhost only) by default. It is not exposed to your network or the internet.

If you change `--host` to `0.0.0.0`, be aware that the proxy accepts any request and forwards it to the provider using whatever `Authorization` header the caller supplies. Do not expose the proxy to untrusted networks.

---

## MCP server

The MCP server runs in stdio mode: it is launched by Claude Code or Claude Desktop and communicates only over its own stdin/stdout pipe. It does not bind any network port, does not make outbound connections of its own, and does not read files outside of `~/.contextpilot/events.jsonl`.

---

## Supply chain

ContextPilot's runtime dependencies are minimal by design:

| Package | Used for |
|---------|---------|
| `httpx` | Async HTTP client for proxy forwarding and telemetry flush |
| `pydantic` | Config model validation |
| `pyyaml` | Config file parsing |
| `click` | CLI |
| `starlette` + `uvicorn` | Proxy server (optional, `[proxy]` extra) |
| `mcp` | MCP server (optional, `[mcp]` extra) |

No AI/ML frameworks, no data collection SDKs, no analytics libraries.

---

## Reporting a vulnerability

If you discover a security issue, particularly anything that could cause prompt content to leak, credentials to be exposed, or the proxy to be exploited, please report it privately before disclosing publicly.

**Email:** contact@contextpilot.org  
**Subject line:** `[SECURITY] ContextPilot: <short description>`

Please include:
- A description of the issue and its potential impact
- Steps to reproduce (minimal example if possible)
- Any suggested fix, if you have one

You can expect an acknowledgement within 48 hours and a fix or mitigation plan within 7 days for confirmed issues.

Public disclosure should be coordinated after a fix is available (standard responsible disclosure).
