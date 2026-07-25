from __future__ import annotations

import re
from collections import Counter

from contextpilot.analyzer import DEBUG_SIGNAL_PATTERN, Intent, MessageBlock
from contextpilot.config import ContextPilotConfig
from contextpilot.report import BlockDecision

_DEBUG_WINDOW_BONUS = 4
_EXPLORE_WINDOW_REDUCTION = 2

# Common English words that carry no distinctive information
_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "was",
        "are",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "that",
        "this",
        "it",
        "its",
        "not",
        "what",
        "which",
        "who",
        "when",
        "where",
        "how",
        "all",
        "each",
        "both",
        "few",
        "more",
        "most",
        "also",
        "just",
        "can",
        "you",
        "your",
        "we",
        "our",
        "they",
        "their",
        "he",
        "she",
        "his",
        "her",
        "my",
        "me",
        "him",
        "them",
        "us",
        "up",
        "out",
        "if",
        "about",
        "into",
        "then",
        "than",
        "so",
        "no",
        "only",
        "any",
        "some",
        "there",
        "here",
        "use",
    }
)


def _extract_keywords(text: str, top_k: int = 8) -> str:
    """Return the top-K most distinctive words from text.

    Prioritises long, rare, non-stop words — the terms a TF-IDF quality gate
    will weight highest when measuring semantic similarity.
    """
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9]{2,}\b", text)
    if not words:
        return text[:50]
    counts = Counter(w.lower() for w in words if w.lower() not in _STOPWORDS)
    if not counts:
        return text[:50]
    # Longer words and lower frequency = more distinctive
    ranked = sorted(counts, key=lambda w: (-len(w), counts[w]))
    return " ".join(ranked[:top_k])


def summarize_old_turns(
    messages: list[dict],
    blocks: list[MessageBlock],
    config: ContextPilotConfig,
    intent: Intent = Intent.UNKNOWN,
    decisions: list[BlockDecision] | None = None,
) -> list[dict]:
    """FR-003a: Conversation history summarization.

    Keeps the last `history_window` turns verbatim. All older turns are
    collapsed into a compact keyword-based [CONTEXT] block — no LLM call,
    under 10 ms (technical doc §3.1).

    Keyword extraction preserves TF-IDF signal so the quality gate scores
    the summary highly despite the dramatic token reduction.

    `intent` adjusts the retained window: widened for `debug` (preserve more
    recent turns verbatim), narrowed for `explore` (compress more history).
    During `debug`, old turns containing error/traceback signals keep their
    exact text (truncated) instead of being reduced to keywords only.
    """
    n = len(messages)
    window = config.compression.history_window
    if intent == Intent.DEBUG:
        window += _DEBUG_WINDOW_BONUS
    elif intent == Intent.EXPLORE:
        window = max(1, window - _EXPLORE_WINDOW_REDUCTION)
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
        token_est = len(content.split())
        if intent == Intent.DEBUG and DEBUG_SIGNAL_PATTERN.search(content):
            excerpt = content[:200]
            parts.append(f"[{role[0].upper()} ~{token_est}t: {excerpt}]")
        else:
            keywords = _extract_keywords(content)
            parts.append(f"[{role[0].upper()} ~{token_est}t: {keywords}]")

    if not parts:
        return messages

    summary_block: dict = {
        "role": "user",
        "content": "Prior context: " + " | ".join(parts),
    }

    if decisions is not None:
        summary_tokens = len(summary_block["content"].split())
        old_blocks = blocks[:keep_from]
        total_old_tokens = sum(blk.token_count for blk in old_blocks) or 1
        for blk in old_blocks:
            share = round(summary_tokens * blk.token_count / total_old_tokens)
            decisions.append(
                BlockDecision(
                    block_id=blk.index,
                    strategy_applied="history",
                    action="summarized",
                    reason=f"outside history_window ({window} turns) — folded into keyword summary",
                    tokens_saved=max(0, blk.token_count - share),
                )
            )

    return [summary_block] + list(recent_messages)
