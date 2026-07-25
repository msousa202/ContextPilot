# Proxy and service: setup for GPT Codex, Aider, and other OpenAI-compatible tools

This covers the proxy surface for tools other than Claude Code. If you're using Claude Code specifically, see [claude-code-integration.md](claude-code-integration.md) instead, it has Claude-specific setup and verification steps.

The proxy is a local, OpenAI-compatible HTTP server. Any tool that lets you override its API base URL can be routed through it.

## How it works

```
Your tool (GPT Codex, Aider, ...)
        │  normal request
        ▼
  ContextPilot Proxy (localhost:8432)
        │  compressed request
        ▼
  OpenAI / Anthropic API
```

The proxy binds to `127.0.0.1` by default, not exposed to your network. It forwards your `Authorization` header through unchanged; ContextPilot never reads or stores your API key. See [SECURITY.md](../SECURITY.md) for the full trust model.

## Option 1: background service (recommended)

Installs the proxy so it starts on login and sets the right environment variable permanently, no terminal to keep open.

```bash
pipx install "contextpilot-ai[proxy]"
contextpilot service install
```

This registers a startup entry (Windows Task Scheduler, macOS launchd, or Linux systemd, depending on your OS) and sets `ANTHROPIC_BASE_URL` in your environment. Open a new terminal for the environment variable to take effect.

```bash
contextpilot service status     # confirm it's running
contextpilot service uninstall  # remove it
```

If your tool talks to OpenAI rather than Anthropic, set `OPENAI_BASE_URL` yourself (the installer only sets the Anthropic variable automatically):

```bash
export OPENAI_BASE_URL=http://localhost:8432/v1      # Linux / macOS
$env:OPENAI_BASE_URL = "http://localhost:8432/v1"    # Windows PowerShell
```

## Option 2: manual, per session

```bash
contextpilot proxy --port 8432
# or: python -m contextpilot proxy --port 8432
```

Keep that terminal open. In the terminal (or environment) where you run your tool:

```bash
# Anthropic-based tools (Claude Code, some Aider configurations)
export ANTHROPIC_BASE_URL=http://localhost:8432

# OpenAI-based tools (GPT Codex, most Aider configurations)
export OPENAI_BASE_URL=http://localhost:8432/v1
```

## Per-tool notes

**GPT Codex**: set `OPENAI_BASE_URL` before starting a session. Codex sends standard OpenAI chat/completions requests, which the proxy compresses the same way it does for any OpenAI client.

**Aider**: supports both providers depending on the model you configure. Set whichever base URL variable matches the provider you've pointed Aider at. Aider's own `--map-tokens` repo-map feature and ContextPilot's compression are complementary: Aider controls what goes into the prompt, ContextPilot compresses the payload once it's built.

**Any other OpenAI-compatible CLI or SDK**: if it respects `OPENAI_BASE_URL` (or an equivalent `base_url` constructor argument pointed at `http://localhost:8432/v1`), it works without further changes.

## Checking it's working

```bash
contextpilot report
```

Shows aggregate token savings across every call that went through the proxy, library wrapper, or MCP server combined. If the count stays at zero after you've used your tool, double-check the base URL environment variable is actually set in the process your tool is running in (a new terminal picks up a freshly-exported variable, an already-open one won't).
