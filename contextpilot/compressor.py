from __future__ import annotations

from contextpilot.analyzer import Intent, MessageBlock
from contextpilot.config import ContextPilotConfig
from contextpilot.report import SUMMARY_BLOCK_ID, BlockDecision
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
        *,
        decisions: list[BlockDecision] | None = None,
    ) -> tuple[list[dict], str | None]:
        if not messages:
            return messages, system

        query = next(
            (m.get("content") or "" for m in reversed(messages) if m.get("role") == "user"),
            "",
        )

        intent = blocks[0].intent if blocks else Intent.UNKNOWN
        result = list(messages)

        # Stage 1: history summarization (keyword-preserving, no LLM call)
        result = summarize_old_turns(
            result, blocks, self.config, intent=intent, decisions=decisions
        )

        # `result`'s length may have changed (old turns collapsed into one summary
        # block). Rebuild an original-index map by object identity — surviving
        # messages are the same dict objects as in `messages` (shallow copy above),
        # so `is`-identity holds. Stages after this one never change message count.
        block_ids: list[int] | None = None
        if decisions is not None:
            id_to_index = {id(m): b.index for m, b in zip(messages, blocks)}
            block_ids = [id_to_index.get(id(m), SUMMARY_BLOCK_ID) for m in result]

        # Stage 2: RAG chunk pruning (paragraph-level fallback included)
        if query:
            result = prune_rag_chunks(
                result, query, self.config, intent=intent, block_ids=block_ids, decisions=decisions
            )

        # Stage 3: structural stripping
        result = apply_structural_stripping(result, self.config, intent=intent)

        # Stage 4: system prompt dedup (aggressive only)
        compressed_system = system
        if system and self.config.compression.level == "aggressive":
            compressed_system = self._dedup.process(
                system, self.config, intent=intent, decisions=decisions
            )

        return result, compressed_system

    def reset(self) -> None:
        """Reset stateful strategies (e.g. between independent sessions)."""
        self._dedup.reset()
