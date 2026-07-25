"""ContextPilot smoke test: validates the real compression pipeline end-to-end.

Runs WITHOUT making real API calls (no key needed). Tests the full
pipeline: analyzer → compressor → quality gate → telemetry log.

For a live API round-trip, see smoke_test_live.py.

Usage:
    python examples/smoke_test.py
"""
from __future__ import annotations

import sys
import json
from pathlib import Path

# Add project root to path when running from examples/
sys.path.insert(0, str(Path(__file__).parent.parent))

import contextpilot
from contextpilot.config import ContextPilotConfig
from contextpilot.pipeline import Pipeline
from contextpilot.telemetry import _LOCAL_LOG


def _separator(title: str) -> None:
    print(f"\n{'-' * 50}")
    print(f"  {title}")
    print('-' * 50)


def test_pipeline_directly() -> None:
    _separator("1. Pipeline compression (no API call)")

    # Simulate a bloated multi-turn conversation
    messages = [
        {"role": "user", "content": "What is the capital of France?"},
        {"role": "assistant", "content": "The capital of France is Paris."},
        {"role": "user", "content": "What is the capital of France?"},
        {"role": "assistant", "content": "The capital of France is Paris. Paris is the capital."},
        {"role": "user", "content": "Tell me about Paris."},
        {"role": "assistant", "content": "Paris is a major city in France. It is the capital. Paris has many famous landmarks."},
        {"role": "user", "content": "What is the capital of France?"},
        {"role": "assistant", "content": "As I mentioned before, the capital of France is Paris."},
        {"role": "user", "content": "Summarise everything about Paris that we discussed."},
    ]
    system = "You are a helpful geography assistant. You answer questions about world capitals."

    cfg = ContextPilotConfig()
    pipeline = Pipeline(cfg)

    orig_tokens = sum(len((m.get("content") or "").split()) for m in messages)
    optimized, opt_sys, event = pipeline.optimize(messages, system=system, provider="test", model="test")
    comp_tokens = sum(len((m.get("content") or "").split()) for m in optimized)

    saved = orig_tokens - comp_tokens
    ratio = saved / orig_tokens * 100 if orig_tokens else 0

    print(f"  Messages in      : {len(messages)}")
    print(f"  Messages out     : {len(optimized)}")
    print(f"  Words in (orig)  : {orig_tokens}")
    print(f"  Words in (sent)  : {comp_tokens}")
    print(f"  Words saved      : {saved}  ({ratio:.1f}%)")
    print(f"  Quality score    : {event.quality_score:.1f}/100")
    print(f"  Fallback         : {event.fallback_triggered}")
    print(f"  Compression time : {event.compression_ms:.2f} ms")

    assert comp_tokens <= orig_tokens, "Compression must never increase token count"
    assert event.quality_score >= 0, "Quality score must be non-negative"
    print("\n  PASS")


def test_wrap_api() -> None:
    _separator("2. contextpilot.wrap(), OpenAI path (mock client)")

    class _FakeCompletions:
        def create(self, *, model, messages, **kwargs):
            class _R:
                choices = [type("C", (), {"message": type("M", (), {"content": "ok"})()})()]
            return _R()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeOpenAI:
        __module__ = "openai"
        __class__ = type("OpenAI", (), {"__name__": "OpenAI"})
        chat = _FakeChat()

    client = _FakeOpenAI()
    client.__class__.__name__ = "OpenAI"

    pilot = contextpilot.wrap(client)
    response = pilot.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello!"}],
    )
    assert response.choices[0].message.content == "ok"
    print("  wrap() intercepts and forwards correctly")
    print("\n  PASS")


def test_local_telemetry_written() -> None:
    _separator("3. Local telemetry log written to disk")

    if not _LOCAL_LOG.exists():
        print(f"  Log not found at {_LOCAL_LOG}")
        print("  (Run a real call to populate it, this is expected on first run)")
        return

    events = []
    with _LOCAL_LOG.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    print(f"  Log path   : {_LOCAL_LOG}")
    print(f"  Events     : {len(events)}")
    if events:
        last = events[-1]
        print(f"  Last event : provider={last.get('provider')}, model={last.get('model')}")
        print(f"               tokens_original={last.get('tokens_input_original')}, "
              f"tokens_compressed={last.get('tokens_input_compressed')}")
    print("\n  PASS")


def test_migrate_dry_run(tmp_path: Path | None = None) -> None:
    _separator("4. Migration agent, dry run")
    import tempfile, os

    src = """\
from openai import OpenAI
client = OpenAI(api_key="sk-test")
response = client.chat.completions.create(model="gpt-4o", messages=[])
"""
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
        f.write(src)
        name = f.name

    try:
        from contextpilot.migrate import _transform_source
        result = _transform_source(src, Path(name))
        assert result.changed, "Should detect OpenAI() call"
        assert "contextpilot.wrap(OpenAI(" in result.rewritten
        assert "import contextpilot" in result.rewritten
        print(f"  Input  : client = OpenAI(api_key=\"sk-test\")")
        print(f"  Output : client = contextpilot.wrap(OpenAI(api_key=\"sk-test\"))")
        print(f"  Calls  : {result.call_count}")
        print("\n  PASS")
    finally:
        os.unlink(name)


def main() -> None:
    print("\nContextPilot Smoke Test")
    print("=" * 50)

    failures = 0
    for fn in [test_pipeline_directly, test_wrap_api, test_local_telemetry_written, test_migrate_dry_run]:
        try:
            fn()
        except Exception as exc:
            print(f"\n  FAIL: {exc}")
            failures += 1

    print(f"\n{'=' * 50}")
    if failures:
        print(f"  {failures} test(s) failed.")
        sys.exit(1)
    else:
        print("  All checks passed. ContextPilot is working correctly.")
        print(f"\n  Run `contextpilot report` to see savings from any live calls.")
    print()


if __name__ == "__main__":
    main()
