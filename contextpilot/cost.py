"""Cache-aware cost model: estimate what a payload actually costs to send.

Token counts are not what customers pay for. With provider prompt caching,
the billable multipliers differ by an order of magnitude per region of the
request (Anthropic published rates, OpenAI comparable):

- cached prefix, read:  ~0.10x base input price
- cache write (5m TTL):  1.25x base input price
- uncached input:        1.00x base input price

Caching is a strict byte-prefix match: the first differing byte invalidates
everything after it. The practical consequence for a compressor: on a warm
cache, rewriting earlier conversation bytes must remove roughly 90% of the
tokens just to break even. This module encodes that arithmetic so the
pipeline can refuse "compression" that would raise the real bill (the cost
gate, complementing the semantic quality gate of FR-004).

The model works in token-units (multiplier-weighted token counts) so it needs
no price table; USD conversion for telemetry uses `_utils.rate_for_model`.

Steady-state assumption: for a multi-turn conversation whose forwarded bytes
are stable across turns (which the epoch-based history strategy guarantees),
every turn re-reads the previous prefix from cache and pays full price only
for the novel tail. `steady_state_cost` prices exactly that. `transition_cost`
prices the first request after the forwarded shape changes (cache rebuilt).
"""

from __future__ import annotations

from dataclasses import dataclass

from contextpilot.content import message_text

CACHE_READ_MULT = 0.10
CACHE_WRITE_MULT = 1.25
UNCACHED_MULT = 1.00


def _tokens(msg: dict) -> int:
    return len(message_text(msg).split())


def _total_tokens(messages: list[dict], system: str | None) -> int:
    total = sum(_tokens(m) for m in messages)
    if system:
        total += len(system.split())
    return total


def common_prefix_tokens(
    a_msgs: list[dict],
    b_msgs: list[dict],
    a_sys: str | None,
    b_sys: str | None,
) -> int:
    """Token count of the shared leading region of two payloads.

    The system prompt renders before messages, so a differing system prompt
    means no shared prefix at all. Messages compare by full equality, the
    same all-or-nothing behavior as provider prefix caches.
    """
    if (a_sys or "") != (b_sys or ""):
        return 0
    shared = len((a_sys or "").split()) if a_sys else 0
    for m_a, m_b in zip(a_msgs, b_msgs):
        if m_a == m_b:
            shared += _tokens(m_a)
        else:
            break
    return shared


def steady_state_cost(messages: list[dict], system: str | None) -> float:
    """Per-turn cost in token-units, assuming a warm cache on the full prefix.

    Everything except the final message reads from cache at 0.1x; the final
    (novel) message bills at full price. This is the best case a stable
    payload converges to, and the baseline any rewriting must beat.
    """
    if not messages:
        return 0.0
    tail = _tokens(messages[-1])
    prefix = _total_tokens(messages[:-1], system)
    return prefix * CACHE_READ_MULT + tail * UNCACHED_MULT


@dataclass
class CostEstimate:
    """Cache-aware cost comparison between the original and compressed payload."""

    original_steady: float  # token-units per turn, original payload, warm cache
    compressed_steady: float  # token-units per turn, compressed payload, warm cache
    transition: float  # one-off token-units for the first request after a shape change
    compressed_amortized: float  # per-turn compressed cost incl. per-epoch cache rebuilds

    @property
    def compressed_is_cheaper(self) -> bool:
        return self.compressed_amortized <= self.original_steady


def evaluate(
    original: list[dict],
    compressed: list[dict],
    system: str | None,
    compressed_system: str | None,
    epoch: int = 8,
    assume_cached: bool = True,
) -> CostEstimate:
    """Compare payloads under the cache model.

    `transition` prices the first request after the compressed shape changes:
    the region still shared with the original reads from cache, the rest is
    billed as a fresh cache write at 1.25x.

    The compressed shape changes once per `epoch` turns (the history
    strategy's boundary quantum), so the honest per-turn figure amortizes one
    transition across the epoch:

        amortized = (transition + steady * (epoch - 1)) / epoch

    Comparing steady-state alone would ignore that recurring rebuild and
    approve rewrites that lose money over the epoch.

    `assume_cached=False` prices the payload as a one-shot request with no
    prefix cache to preserve, which is the correct model for a single
    `contextpilot.compress()` call or any workload whose prefixes never
    repeat. There, every token bills at full price and fewer tokens is
    simply cheaper.
    """
    if not assume_cached:
        orig_total = float(_total_tokens(original, system))
        comp_total = float(_total_tokens(compressed, compressed_system))
        return CostEstimate(
            original_steady=round(orig_total, 2),
            compressed_steady=round(comp_total, 2),
            transition=round(comp_total, 2),
            compressed_amortized=round(comp_total, 2),
        )

    epoch = max(epoch, 1)
    orig_steady = steady_state_cost(original, system)
    comp_steady = steady_state_cost(compressed, compressed_system)

    shared = common_prefix_tokens(original, compressed, system, compressed_system)
    comp_total = _total_tokens(compressed, compressed_system)
    transition = shared * CACHE_READ_MULT + max(comp_total - shared, 0) * CACHE_WRITE_MULT

    amortized = (transition + comp_steady * (epoch - 1)) / epoch

    return CostEstimate(
        original_steady=round(orig_steady, 2),
        compressed_steady=round(comp_steady, 2),
        transition=round(transition, 2),
        compressed_amortized=round(amortized, 2),
    )
