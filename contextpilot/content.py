"""Content-block utilities: uniform text access over string and block-list message content.

Anthropic-style clients (Claude Code, agent frameworks) send `content` as a list
of typed blocks (`text`, `tool_use`, `tool_result`, ...) rather than a plain
string, and may attach `cache_control` breakpoints to individual blocks. The
pipeline uses these helpers to:

- read text out of any message shape for analysis and quality scoring,
- decide which messages are safe to rewrite ("mutable"), and
- detect payloads that manage provider-side prompt caching themselves.

Two hard rules enforced across the pipeline:

1. A message whose content is not a plain string is never rewritten. Its
   blocks (tool calls, tool results, images, cache markers) are forwarded
   byte-identical.
2. A payload containing any `cache_control` marker is treated as
   cache-managed by the client: rewriting bytes at or before a breakpoint
   would invalidate the provider's prefix cache, which costs more than any
   compression could save (cache reads bill at ~0.1x input price).
"""

from __future__ import annotations

from typing import Any


def block_text(block: Any) -> str:
    """Extract readable text from a single content block, best effort."""
    if isinstance(block, str):
        return block
    if not isinstance(block, dict):
        return ""
    btype = block.get("type")
    if btype == "text":
        return str(block.get("text") or "")
    if btype == "tool_result":
        inner = block.get("content")
        if isinstance(inner, str):
            return inner
        if isinstance(inner, list):
            return " ".join(block_text(b) for b in inner)
        return ""
    # tool_use inputs, images, documents: no readable text for analysis
    return ""


def message_text(msg: dict) -> str:
    """Return the readable text of a message whether content is str or block list."""
    content = msg.get("content")
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(t for t in (block_text(b) for b in content) if t)
    return str(content)


def is_plain_string(msg: dict) -> bool:
    """True when the message content is a plain string (rewritable shape)."""
    return isinstance(msg.get("content"), str)


def message_has_cache_control(msg: dict) -> bool:
    """True when any block in this message carries a cache_control marker."""
    content = msg.get("content")
    if not isinstance(content, list):
        return False
    for block in content:
        if isinstance(block, dict) and block.get("cache_control") is not None:
            return True
    return False


def payload_is_cache_managed(messages: list[dict], system: Any = None) -> bool:
    """True when the client set any cache_control marker in messages or system.

    Such clients (Claude Code among them) rely on provider prefix caching.
    Rewriting any byte at or before a breakpoint silently invalidates the
    cache and raises the real bill, so the pipeline restricts itself to the
    final, not-yet-cached message.
    """
    if isinstance(system, list):
        for block in system:
            if isinstance(block, dict) and block.get("cache_control") is not None:
                return True
    return any(message_has_cache_control(m) for m in messages)


def mutable_indices(messages: list[dict]) -> set[int]:
    """Indices of messages that are structurally safe to rewrite.

    A message is mutable when its content is a plain string and it carries no
    cache_control marker. Block-list messages are forwarded untouched.
    """
    return {
        i for i, m in enumerate(messages) if is_plain_string(m) and not message_has_cache_control(m)
    }
