"""Validate the cache cost model against live API responses.

`cache_economics.py` prices payloads with a *simulated* prefix cache built from
published pricing and documented cache behavior. This script checks that model
against reality: it runs a real multi-turn conversation through the Anthropic
API twice, once forwarding payloads unchanged and once through the pipeline,
reads the actual `usage` fields off each response, and compares measured cost
against what the simulator predicted.

What it answers:
  1. Does the pipeline keep the provider cache working? (cache_read > 0 on
     later turns, and comparable to the uncompressed run)
  2. Is the compressed run actually cheaper in real billed tokens?
  3. Does the simulated model agree with reality, or is it optimistic?

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python benchmarks/validate_cache_costs.py [--turns 12] [--model claude-opus-5]

Cost: a dozen short turns on a small model. Use --model claude-haiku-4-5 to
keep it to a few cents. Prompt caching requires a prefix above the model's
minimum cacheable length, so the script pads the system prompt accordingly.

Nothing here is imported by the library; this is a developer tool.
"""

from __future__ import annotations

import argparse
import os
import sys

from contextpilot.config import ContextPilotConfig
from contextpilot.cost import CACHE_READ_MULT, CACHE_WRITE_MULT, UNCACHED_MULT
from contextpilot.pipeline import Pipeline

# Padding target for the system prompt. The minimum cacheable prefix is
# model-dependent (512-4096 tokens); this comfortably clears the largest.
_SYSTEM_MIN_WORDS = 4500


def _build_system() -> str:
    """A large, stable system prompt: the realistic shape for a cached agent."""
    para = (
        "You are a senior software engineer assisting with a Python codebase. "
        "Answer precisely and briefly. Prefer concrete code over prose. "
        "When you are unsure, say so rather than guessing. "
    )
    reps = (_SYSTEM_MIN_WORDS // len(para.split())) + 1
    return (para * reps).strip()


def _turn_text(i: int) -> str:
    return (
        f"Turn {i}: summarize what we have discussed so far and then answer this: "
        f"what is the {i}th consideration when caching prompts? "
        "Keep the answer to two sentences."
    )


class Ledger:
    """Accumulates real billed token counts from response usage fields."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.cache_read = 0
        self.cache_write = 0
        self.uncached = 0
        self.output = 0

    def add(self, usage: object) -> None:
        self.cache_read += int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        self.cache_write += int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        self.uncached += int(getattr(usage, "input_tokens", 0) or 0)
        self.output += int(getattr(usage, "output_tokens", 0) or 0)

    @property
    def input_token_units(self) -> float:
        """Multiplier-weighted input cost, the unit cache_economics.py reports."""
        return (
            self.cache_read * CACHE_READ_MULT
            + self.cache_write * CACHE_WRITE_MULT
            + self.uncached * UNCACHED_MULT
        )

    @property
    def raw_input_tokens(self) -> int:
        return self.cache_read + self.cache_write + self.uncached

    def report(self) -> str:
        return (
            f"  {self.label:<22} "
            f"read {self.cache_read:>7,}  write {self.cache_write:>7,}  "
            f"uncached {self.uncached:>7,}  ->  {self.input_token_units:>10,.0f} units"
        )


def _run(client: object, model: str, turns: int, pipeline: Pipeline | None) -> Ledger:
    """Replay a conversation, optionally through the pipeline. Returns the ledger."""
    label = "pipeline + cache" if pipeline else "raw + cache"
    ledger = Ledger(label)
    system = _build_system()
    messages: list[dict] = []

    for i in range(turns):
        messages.append({"role": "user", "content": _turn_text(i)})

        send_messages = messages
        send_system: object = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
        if pipeline is not None:
            optimized, _, _ = pipeline.optimize(
                [dict(m) for m in messages], system=system, provider="anthropic", model=model
            )
            send_messages = optimized

        response = client.messages.create(  # type: ignore[attr-defined]
            model=model,
            max_tokens=200,
            system=send_system,
            messages=send_messages,
        )
        ledger.add(response.usage)

        text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
        messages.append({"role": "assistant", "content": text})
        print(f"    turn {i + 1}/{turns} done", end="\r", flush=True)

    print(" " * 40, end="\r")
    return ledger


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turns", type=int, default=12)
    parser.add_argument("--model", default="claude-haiku-4-5")
    args = parser.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. This script makes real, billed API calls.")
        return 2

    try:
        import anthropic
    except ImportError:
        print("pip install anthropic")
        return 2

    client = anthropic.Anthropic()

    config = ContextPilotConfig.load()
    config.telemetry.enabled = False
    pipeline = Pipeline(config)

    print(f"Validating cache cost model against the live API ({args.model}, {args.turns} turns)")
    print("=" * 78)
    print("  run 1/2: forwarding payloads unchanged")
    raw = _run(client, args.model, args.turns, pipeline=None)
    print("  run 2/2: forwarding payloads through the pipeline")
    comp = _run(client, args.model, args.turns, pipeline=pipeline)

    print()
    print("Measured, from real response usage fields:")
    print(raw.report())
    print(comp.report())
    print()

    token_delta = (1 - comp.raw_input_tokens / raw.raw_input_tokens) * 100
    cost_delta = (comp.input_token_units - raw.input_token_units) / raw.input_token_units * 100
    verdict = "CHEAPER" if cost_delta < 0 else "MORE EXPENSIVE"

    print(f"  raw input tokens sent  : {token_delta:+.1f}%  (compression working)")
    print(f"  billed input cost      : {cost_delta:+.1f}%  ({verdict})")
    print()

    if comp.cache_read == 0:
        print("  WARNING: zero cache reads on the pipeline run. The forwarded prefix is")
        print("  not stable, so provider caching never engaged. This is the failure the")
        print("  cost gate exists to prevent; investigate before trusting any savings claim.")
    elif comp.cache_read < raw.cache_read * 0.5:
        print("  WARNING: pipeline run got substantially fewer cache reads than the raw run.")
        print("  Compression is partially defeating the cache; treat savings as unproven.")
    else:
        print("  Cache engaged on both runs; the comparison above is meaningful.")

    print()
    print("  Compare this billed-cost delta against the simulated figure from")
    print("  `python benchmarks/cache_economics.py`. If they disagree materially,")
    print("  the simulated model is wrong and README claims must be corrected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
