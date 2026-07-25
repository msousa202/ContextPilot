from __future__ import annotations

import hashlib

from contextpilot.analyzer import Intent
from contextpilot.config import ContextPilotConfig
from contextpilot.report import SYSTEM_BLOCK_ID, BlockDecision


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

    def process(
        self,
        system: str | None,
        config: ContextPilotConfig,
        intent: Intent = Intent.UNKNOWN,
        decisions: list[BlockDecision] | None = None,
    ) -> str | None:
        if not system:
            return system
        if intent == Intent.DEBUG:
            # Never truncate the system prompt mid-debug, full context matters most here.
            self._last_hash = hashlib.sha256(system.encode()).hexdigest()[:16]
            return system

        h = hashlib.sha256(system.encode()).hexdigest()[:16]
        changed = h != self._last_hash
        self._last_hash = h

        if not changed and config.compression.level == "aggressive":
            # Truncate to short reference, model relies on cached version
            truncated = f"[SYSTEM CACHED ref:{h}] " + system[:80] + "…"
            if decisions is not None:
                decisions.append(
                    BlockDecision(
                        block_id=SYSTEM_BLOCK_ID,
                        strategy_applied="dedup",
                        action="summarized",
                        reason="unchanged system prompt truncated to cached reference",
                        tokens_saved=max(0, len(system.split()) - len(truncated.split())),
                    )
                )
            return truncated

        return system

    def reset(self) -> None:
        self._last_hash = None
