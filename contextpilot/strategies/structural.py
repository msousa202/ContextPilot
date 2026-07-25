from __future__ import annotations

import re

from contextpilot.analyzer import Intent
from contextpilot.config import ContextPilotConfig

# (pattern, replacement) — applied in order
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


def strip_structural(text: str, intent: Intent = Intent.UNKNOWN) -> str:
    """Apply deterministic regex transformations to reduce formatting overhead.

    During `refactor`, the two repetition-collapsing rules (repeated
    horizontal rules / repeated identical lines) are skipped — they can
    otherwise mangle diff hunks where genuinely repeated `+`/`-` lines carry
    meaning that should be preserved.
    """
    rules = _RULES[:3] if intent == Intent.REFACTOR else _RULES
    for pattern, repl in rules:
        text = pattern.sub(repl, text)
    return text.strip()


def apply_structural_stripping(
    messages: list[dict],
    config: ContextPilotConfig,
    intent: Intent = Intent.UNKNOWN,
) -> list[dict]:
    """FR-003d: Structural formatting stripping.

    Removes redundant whitespace, empty tags, repeated separators, and other
    formatting that consumes tokens without adding semantic value. Typical
    savings: 5–15% on structured prompts, 20–30% on XML/JSON-heavy prompts
    (technical doc §3.4).
    """
    return [
        {**msg, "content": strip_structural(msg.get("content") or "", intent)} for msg in messages
    ]
