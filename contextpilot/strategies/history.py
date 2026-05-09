from __future__ import annotations

from contextpilot.analyzer import MessageBlock
from contextpilot.config import ContextPilotConfig

_PREVIEW_CHARS = 80  # truncate old-turn previews to this length in the summary


def summarize_old_turns(
    messages: list[dict],
    blocks: list[MessageBlock],
    config: ContextPilotConfig,
) -> list[dict]:
    """FR-003a: Conversation history summarization.

    Keeps the last `history_window` turns verbatim. All older turns are
    collapsed into a compact [CONTEXT SUMMARY] block using deterministic
    extraction — no LLM call, executes in under 10 ms (technical doc §3.1).

    Returns the original list unchanged if fewer messages than the window,
    or if there is no summarisable content.
    """
    n = len(messages)
    window = config.compression.history_window
    if n <= window:
        return messages

    keep_from = n - window
    old_messages = messages[:keep_from]
    recent_messages = messages[keep_from:]

    parts: list[str] = []
    for msg in old_messages:
        content = (msg.get("content") or "").strip()
        role = msg.get("role", "user")
        if not content:
            continue
        preview = content[:_PREVIEW_CHARS]
        if len(content) > _PREVIEW_CHARS:
            preview += "…"
        parts.append(f"[{role[0]}]: {preview}")  # compact prefix: [u], [a], [s]

    if not parts:
        return messages

    original_tokens = sum(len((m.get("content") or "").split()) for m in old_messages)
    summary_text = " | ".join(parts)

    summary_block: dict = {
        "role": "user",
        "content": f"[CTX {keep_from} turns ~{original_tokens}tok] {summary_text}",
    }

    return [summary_block] + list(recent_messages)
