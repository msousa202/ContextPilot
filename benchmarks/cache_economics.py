"""Cache-economics benchmark: does compression lower the *billable* cost?

Token-count reduction is not the billable unit. With provider prompt caching,
a multi-turn conversation bills its stable prefix at ~0.1x (cache read) and
only novel bytes at full price (cache writes at 1.25x, 5-minute TTL). Any
transform that rewrites earlier bytes of the conversation invalidates the
prefix cache from that point and re-bills everything after it.

This benchmark replays a synthetic multi-turn conversation turn by turn,
simulating the provider cache with its strict prefix-match rule, and prices
three scenarios in token-units (multiplier-weighted tokens):

  raw        : payload forwarded unchanged
  pipeline   : payload run through Pipeline.optimize() each turn
  no cache   : payload unchanged, caching unavailable (reference)

Run:  python benchmarks/cache_economics.py
"""

from __future__ import annotations

import random

from contextpilot.config import ContextPilotConfig
from contextpilot.content import message_text
from contextpilot.cost import CACHE_READ_MULT, CACHE_WRITE_MULT, UNCACHED_MULT
from contextpilot.pipeline import Pipeline

TURNS = 40
SEED = 7


def _tokens(msg: dict) -> int:
    return len(message_text(msg).split())


class SimulatedPrefixCache:
    """Provider cache stand-in: strict message-level prefix match.

    Tracks the last forwarded payload. On the next request, leading messages
    equal to the previous payload's messages bill as cache reads; everything
    from the first difference bills as a cache write.
    """

    def __init__(self) -> None:
        self._previous: list[dict] | None = None

    def price(self, messages: list[dict]) -> float:
        if self._previous is None:
            cost = sum(_tokens(m) for m in messages) * CACHE_WRITE_MULT
        else:
            shared = 0
            for prev, cur in zip(self._previous, messages):
                if prev == cur:
                    shared += _tokens(cur)
                else:
                    break
            total = sum(_tokens(m) for m in messages)
            cost = shared * CACHE_READ_MULT + (total - shared) * CACHE_WRITE_MULT
        self._previous = [dict(m) for m in messages]
        return cost


def _synthetic_conversation(turns: int) -> list[dict]:
    """A plausible coding-agent transcript: questions, long answers, error dumps."""
    rng = random.Random(SEED)
    vocab = (
        "refactor pipeline adapter telemetry compression tokenizer payload "
        "handler module schema config threshold fallback provider anthropic "
        "openai latency benchmark cache prefix breakpoint epoch strategy"
    ).split()
    messages: list[dict] = []
    for t in range(turns):
        q_words = rng.randint(15, 40)
        question = " ".join(rng.choices(vocab, k=q_words))
        messages.append({"role": "user", "content": f"Turn {t}: {question}?"})
        a_words = rng.randint(80, 300)
        answer = " ".join(rng.choices(vocab, k=a_words))
        if t % 7 == 3:
            answer = "Traceback (most recent call last):\n  TypeError: boom\n" + answer
        messages.append({"role": "assistant", "content": answer})
    return messages


def run() -> None:
    transcript = _synthetic_conversation(TURNS)
    config = ContextPilotConfig.load()
    config.telemetry.enabled = False
    pipeline = Pipeline(config)

    raw_cache = SimulatedPrefixCache()
    comp_cache = SimulatedPrefixCache()

    raw_cost = 0.0
    comp_cost = 0.0
    nocache_cost = 0.0
    raw_tokens = 0
    comp_tokens = 0

    # Replay: at each user turn t, the client sends everything up to that turn.
    for end in range(1, len(transcript) + 1, 2):
        payload = transcript[:end]
        raw_cost += raw_cache.price(payload)
        nocache_cost += sum(_tokens(m) for m in payload) * UNCACHED_MULT
        raw_tokens += sum(_tokens(m) for m in payload)

        optimized, _, _ = pipeline.optimize([dict(m) for m in payload])
        comp_cost += comp_cache.price(optimized)
        comp_tokens += sum(_tokens(m) for m in optimized)

    print("Cache-economics benchmark (token-units, lower is better)")
    print("=" * 60)
    print(f"  turns simulated          : {TURNS}")
    print(f"  cumulative tokens, raw   : {raw_tokens:,}")
    print(f"  cumulative tokens, comp  : {comp_tokens:,}  "
          f"({(1 - comp_tokens / raw_tokens) * 100:.1f}% fewer)")
    print()
    print(f"  cost, no caching         : {nocache_cost:,.0f}")
    print(f"  cost, raw + cache        : {raw_cost:,.0f}")
    print(f"  cost, pipeline + cache   : {comp_cost:,.0f}")
    print()
    delta = (comp_cost - raw_cost) / raw_cost * 100
    verdict = "CHEAPER" if delta < 0 else "MORE EXPENSIVE"
    print(f"  pipeline vs raw+cache    : {delta:+.1f}%  ({verdict})")
    print()
    print("  A compressor that rewrites cached prefix bytes must beat a 10x")
    print("  handicap (cache reads bill at 0.1x). Token reduction alone is")
    print("  not the billable unit; this number is.")


if __name__ == "__main__":
    run()
