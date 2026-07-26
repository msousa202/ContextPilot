from __future__ import annotations

import re

from contextpilot.config import ContextPilotConfig
from contextpilot.content import is_plain_string, message_has_cache_control

# (pattern, replacement), applied in order
_RULES: list[tuple[re.Pattern, str]] = [
    # 3+ blank lines → 2
    (re.compile(r"\n{3,}"), "\n\n"),
    # Trailing whitespace on each line
    (re.compile(r"[ \t]+$", re.MULTILINE), ""),
    # Empty XML/HTML-style tags
    (re.compile(r"<(\w+)>\s*</\1>", re.IGNORECASE), ""),
    # Repeated horizontal rules (3+ dashes/equals/underscores on their own line)
    (re.compile(r"(?:[-=_]{3,}\n){2,}"), "---\n"),
    # Repeated identical lines (e.g. "---" block comments copied verbatim)
    (re.compile(r"^(.+)\n(\1\n){2,}", re.MULTILINE), r"\1\n"),
]

# Diff hunks carry genuinely repeated +/- lines; collapsing them mangles patches.
_DIFF_MARKER_PATTERN = re.compile(r"^(?:diff --git|@@ .* @@|[+-][^+\-\n].*)$", re.MULTILINE)


def strip_structural(text: str) -> str:
    """Apply deterministic regex transformations to reduce formatting overhead.

    Pure function of the text: the same input always produces the same
    output, so re-stripping an old turn on a later request yields identical
    bytes and provider prefix caching is preserved.

    When the text itself contains diff markers, the two repetition-collapsing
    rules are skipped, they would otherwise mangle hunks where repeated
    `+`/`-` lines carry meaning. This is decided per message content, not
    from the conversation-level intent, so the decision never flips for a
    given message as the conversation evolves.
    """
    rules = _RULES[:3] if _DIFF_MARKER_PATTERN.search(text) else _RULES
    for pattern, repl in rules:
        text = pattern.sub(repl, text)
    return text.strip()


def apply_structural_stripping(
    messages: list[dict],
    config: ContextPilotConfig,
) -> list[dict]:
    """FR-003d: Structural formatting stripping.

    Removes redundant whitespace, empty tags, repeated separators, and other
    formatting that consumes tokens without adding semantic value. Typical
    savings: 5-15% on structured prompts, 20-30% on XML/JSON-heavy prompts
    (technical doc §3.4).

    Only plain-string messages without cache_control markers are touched;
    block-list content (tool calls, tool results, images) is forwarded
    byte-identical.
    """
    result: list[dict] = []
    for msg in messages:
        if is_plain_string(msg) and not message_has_cache_control(msg):
            result.append({**msg, "content": strip_structural(msg.get("content") or "")})
        else:
            result.append(msg)
    return result
