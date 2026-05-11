"""Shared internal utilities — not part of the public API."""

from __future__ import annotations


def word_count_messages(messages: list[dict]) -> int:
    return sum(len((m.get("content") or "").split()) for m in messages)


def flatten_messages(messages: list[dict], system: str | None = None) -> str:
    parts = [m.get("content") or "" for m in messages]
    if system:
        parts.insert(0, system)
    return " ".join(parts)


# Rough $/1M-token input rates for common models (input side).
_PRICING: dict[str, float] = {
    "gpt-4o": 5.00,
    "gpt-4o-mini": 0.15,
    "gpt-4-turbo": 10.00,
    "gpt-4": 30.00,
    "gpt-3.5-turbo": 0.50,
    "claude-opus": 15.00,
    "claude-sonnet": 3.00,
    "claude-haiku": 0.25,
}
_DEFAULT_RATE = 5.00  # $/1M tokens fallback


def rate_for_model(model: str) -> float:
    m = model.lower()
    for key, rate in _PRICING.items():
        if key in m:
            return rate
    return _DEFAULT_RATE
