from __future__ import annotations

import re
from collections import Counter

from contextpilot.analyzer import DEBUG_SIGNAL_PATTERN, MessageBlock
from contextpilot.config import ContextPilotConfig
from contextpilot.content import is_plain_string, message_has_cache_control
from contextpilot.report import BlockDecision

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

    Prioritises long, rare, non-stop words: the terms a TF-IDF quality gate
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


def epoch_boundary(n_messages: int, window: int, epoch: int, mutable_prefix_len: int) -> int:
    """Index k: messages[:k] are summarized, messages[k:] forwarded verbatim.

    Cache-stability contract: k is quantized to multiples of `epoch`, so the
    boundary (and therefore the summary bytes and everything after them) stays
    identical across turns until the conversation has grown by a full epoch.
    Provider prefix caches are invalidated once per epoch instead of on every
    request. k never exceeds the leading run of rewritable messages.
    """
    if epoch < 1:
        epoch = 1
    k = ((n_messages - window) // epoch) * epoch
    k = min(k, (mutable_prefix_len // epoch) * epoch)
    return max(k, 0)


def summarize_old_turns(
    messages: list[dict],
    blocks: list[MessageBlock],
    config: ContextPilotConfig,
    decisions: list[BlockDecision] | None = None,
) -> list[dict]:
    """FR-003a: Conversation history summarization, epoch-based.

    Collapses old turns into a compact keyword [CONTEXT] block, no LLM call,
    under 10 ms (technical doc §3.1). Keyword extraction preserves TF-IDF
    signal so the quality gate scores the summary highly despite the token
    reduction.

    The summarization boundary advances in `history_epoch` steps and the
    summary is a pure function of the messages before it, so the forwarded
    payload is byte-identical between epochs and provider prefix caching
    keeps working (see `cost.py` for why that dominates the economics).

    Old turns containing error/traceback signals keep an exact excerpt
    instead of keywords only; the check is per-message content, deterministic
    regardless of the current conversation intent.

    Messages with non-string content or cache_control markers are never
    folded into a summary.
    """
    n = len(messages)
    window = config.compression.history_window
    if n <= window:
        return messages

    mutable_prefix_len = 0
    for m in messages:
        if is_plain_string(m) and not message_has_cache_control(m):
            mutable_prefix_len += 1
        else:
            break

    k = epoch_boundary(n, window, config.compression.history_epoch, mutable_prefix_len)
    if k <= 0:
        return messages

    old_messages = messages[:k]
    recent_messages = messages[k:]

    parts: list[str] = []
    for msg in old_messages:
        content = (msg.get("content") or "").strip()
        role = msg.get("role", "user")
        if not content:
            continue
        token_est = len(content.split())
        if DEBUG_SIGNAL_PATTERN.search(content):
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
        old_blocks = blocks[:k]
        total_old_tokens = sum(blk.token_count for blk in old_blocks) or 1
        for blk in old_blocks:
            share = round(summary_tokens * blk.token_count / total_old_tokens)
            decisions.append(
                BlockDecision(
                    block_id=blk.index,
                    strategy_applied="history",
                    action="summarized",
                    reason=(
                        f"behind epoch boundary {k} "
                        f"(window {window}, epoch {config.compression.history_epoch}), "
                        "folded into keyword summary"
                    ),
                    tokens_saved=max(0, blk.token_count - share),
                )
            )

    return [summary_block] + list(recent_messages)
