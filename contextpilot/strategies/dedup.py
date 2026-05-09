from __future__ import annotations

import hashlib

from contextpilot.config import ContextPilotConfig


class SystemPromptDeduplicator:
    """FR-003b: System prompt deduplication.

    Tracks the hash of the system prompt across calls. On unchanged prompts,
    the system prompt is structured to maximise provider-side cache hits
    (Anthropic prompt caching, OpenAI cached tokens). In aggressive mode,
    subsequent identical prompts are truncated to a short reference to save
    tokens on providers without native caching.
    """

    def __init__(self) -> None:
        self._last_hash: str | None = None

    def process(self, system: str | None, config: ContextPilotConfig) -> str | None:
        if not system:
            return system

        h = hashlib.sha256(system.encode()).hexdigest()[:16]
        changed = h != self._last_hash
        self._last_hash = h

        if not changed and config.compression.level == "aggressive":
            # Truncate to short reference — model relies on cached version
            return f"[SYSTEM CACHED ref:{h}] " + system[:80] + "…"

        return system

    def reset(self) -> None:
        self._last_hash = None
