from __future__ import annotations

import hashlib

from contextpilot.config import ContextPilotConfig
from contextpilot.report import BlockDecision


class SystemPromptDeduplicator:
    """FR-003b: System prompt stability tracking.

    Tracks the hash of the system prompt across calls so surfaces can tell
    when it is stable. A stable system prompt is the ideal candidate for a
    provider-side cache breakpoint (`cache_control` on Anthropic, automatic
    prefix caching on OpenAI), which bills repeat sends at ~0.1x instead of
    full price.

    Historical note: earlier versions truncated an unchanged system prompt to
    a short hash reference in aggressive mode, on the assumption the provider
    would "expand the cached version". Provider caches match on the exact
    bytes sent, so the model simply never saw its instructions. That behavior
    was removed; the system prompt is now always forwarded intact, and the
    savings come from real provider caching instead (see the proxy's
    cache_control injection).
    """

    def __init__(self) -> None:
        self._last_hash: str | None = None
        self._stable_count: int = 0

    def observe(self, system: str | None) -> bool:
        """Record this call's system prompt. Returns True when unchanged."""
        if not system:
            self._last_hash = None
            self._stable_count = 0
            return False
        h = hashlib.sha256(system.encode()).hexdigest()[:16]
        unchanged = h == self._last_hash
        self._last_hash = h
        self._stable_count = self._stable_count + 1 if unchanged else 0
        return unchanged

    @property
    def stable_count(self) -> int:
        """Consecutive calls the system prompt has been unchanged."""
        return self._stable_count

    def process(
        self,
        system: str | None,
        config: ContextPilotConfig,
        decisions: list[BlockDecision] | None = None,
    ) -> str | None:
        """Forward the system prompt unchanged, tracking stability.

        Kept for API compatibility: the return value is always `system`.
        """
        self.observe(system)
        return system

    def reset(self) -> None:
        self._last_hash = None
        self._stable_count = 0
