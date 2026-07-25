# Contributing to ContextPilot

Thank you for your interest in contributing. ContextPilot is an MIT-licensed open-source library and contributions are welcome.

## Before you start

- Check [open issues](https://github.com/msousa202/ContextPilot/issues) to see if someone is already working on what you have in mind.
- For significant changes, open an issue first to discuss the approach before writing code.

## Development setup

```bash
git clone https://github.com/msousa202/ContextPilot.git
cd ContextPilot

python -m venv .venv
source .venv/bin/activate      # Linux / macOS
.venv\Scripts\activate         # Windows

pip install -e ".[dev]"
```

## Running tests

```bash
pytest
```

All tests must pass. Add tests for any new behaviour: untested code will not be merged.

## Code style

The project uses `ruff` for linting and formatting:

```bash
ruff check contextpilot/ tests/
ruff format contextpilot/ tests/
```

## What to contribute

Good areas for contribution:

| Area | Description |
|------|-------------|
| New compression strategies | Add a file under `contextpilot/strategies/` |
| Provider adapters | Add a file under `contextpilot/adapters/` (Google Vertex, Bedrock, etc.) |
| Proxy improvements | `contextpilot/proxy.py` |
| Performance | Analysis must stay under 50 ms for 100K tokens |
| Tests | More edge cases, property-based tests with Hypothesis |
| Documentation | `docs/` and `examples/` |

## What not to change without discussion

- The public API (`contextpilot.wrap()`): must remain backward compatible.
- The telemetry schema: must never include prompt or response content.
- The quality gate fallback: must always be fail-safe.

## Pull request process

1. Fork the repo and create a branch from `main`.
2. Write or update tests for your change.
3. Run `pytest` and `ruff check`, both must pass clean.
4. Open a pull request with a clear description of what changed and why.

## Security issues

Do not open a public issue for security vulnerabilities. See [SECURITY.md](SECURITY.md) for the private reporting process.
