from __future__ import annotations

from contextpilot.analyzer import MessageBlock
from contextpilot.config import ContextPilotConfig
from contextpilot.strategies.dedup import SystemPromptDeduplicator
from contextpilot.strategies.history import summarize_old_turns
from contextpilot.strategies.rag_pruner import prune_rag_chunks
from contextpilot.strategies.structural import apply_structural_stripping


class Compressor:
    """FR-003: Multi-stage compression pipeline.

    Applies strategies in order:
      1. Conversation history summarization (keyword-preserving, no LLM call)
      2. RAG chunk pruning (explicit delimiters + paragraph-level fallback)
      3. Structural formatting stripping
      4. System prompt deduplication (aggressive mode only)

    The compressor is surface-agnostic — the same pipeline runs for the Python
    library, proxy, and MCP server surfaces.
    """

    def __init__(self, config: ContextPilotConfig) -> None:
        self.config = config
        self._dedup = SystemPromptDeduplicator()

    def compress(
        self,
        messages: list[dict],
        blocks: list[MessageBlock],
        system: str | None = None,
    ) -> tuple[list[dict], str | None]:
        if not messages:
            return messages, system

        query = next(
            (m.get("content") or "" for m in reversed(messages) if m.get("role") == "user"),
            "",
        )

        result = list(messages)

        # Stage 1: history summarization (keyword-preserving, no LLM call)
        result = summarize_old_turns(result, blocks, self.config)

        # Stage 2: RAG chunk pruning (paragraph-level fallback included)
        if query:
            result = prune_rag_chunks(result, query, self.config)

        # Stage 3: structural stripping
        result = apply_structural_stripping(result, self.config)

        # Stage 4: system prompt dedup (aggressive only)
        compressed_system = system
        if system and self.config.compression.level == "aggressive":
            compressed_system = self._dedup.process(system, self.config)

        return result, compressed_system

    def reset(self) -> None:
        """Reset stateful strategies (e.g. between independent sessions)."""
        self._dedup.reset()

    def reset(self) -> None:
        """Reset stateful strategies (e.g. between independent sessions)."""
        self._dedup.reset()

    def reset(self) -> None:
        """Reset stateful strategies (e.g. between independent sessions)."""
        self._dedup.reset()
