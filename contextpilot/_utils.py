"""Shared internal utilities — not part of the public API."""

from __future__ import annotations


def word_count_messages(messages: list[dict]) -> int:
    return sum(len((m.get("content") or "").split()) for m in messages)


def flatten_messages(messages: list[dict], system: str | None = None) -> str:
    parts = [m.get("content") or "" for m in messages]
    if system:
        parts.insert(0, system)
    return " ".join(parts)
