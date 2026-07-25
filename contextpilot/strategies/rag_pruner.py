from __future__ import annotations

import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from contextpilot.analyzer import Intent
from contextpilot.config import ContextPilotConfig
from contextpilot.report import BlockDecision

# Delimiters that RAG pipelines commonly use to separate retrieved chunks
_CHUNK_DELIMITERS = re.compile(
    r"(?:^|\n)(?:---+\s*(?:DOCUMENT|DOC|CHUNK|SOURCE|RESULT)\s*\d*\s*---+"
    r"|<(?:doc|document|chunk|source)(?:\s[^>]*)?>(?=\s))",
    re.IGNORECASE,
)


def _split_chunks(text: str) -> list[str]:
    """Split text into RAG chunks: explicit delimiters or paragraph boundaries.

    Real RAG pipelines rarely use structured delimiters. As a fallback, split
    on double newlines when a message has 3+ paragraphs.
    """
    parts = _CHUNK_DELIMITERS.split(text)
    chunks = [p.strip() for p in parts if p.strip()]
    if len(chunks) > 1:
        return chunks

    # Paragraph-level fallback: split on blank lines
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if len(paragraphs) >= 3:
        return paragraphs

    return [text]


def prune_rag_chunks(
    messages: list[dict],
    query: str,
    config: ContextPilotConfig,
    intent: Intent = Intent.UNKNOWN,
    block_ids: list[int] | None = None,
    decisions: list[BlockDecision] | None = None,
) -> list[dict]:
    """FR-003c: RAG chunk pruning.

    For each message that appears to contain multiple RAG chunks, scores each
    chunk against the current query using TF-IDF cosine similarity and removes
    chunks below the configured relevance threshold (default 0.15). Requires
    no embedding model, uses scikit-learn TF-IDF (technical doc §3.3).

    `intent` adjusts the effective threshold: raised for `refactor`/`explore`
    (drop more aggressively for unrelated files / general browsing), lowered
    for `debug` (keep more retrieved context while investigating an error).
    """
    base = config.compression.rag_relevance_min
    if intent == Intent.REFACTOR:
        threshold = max(base, 0.35)
    elif intent == Intent.EXPLORE:
        threshold = max(base, 0.25)
    elif intent == Intent.DEBUG:
        threshold = base * 0.5
    else:
        threshold = base
    if not query:
        return messages

    result: list[dict] = []
    for i, msg in enumerate(messages):
        content = msg.get("content") or ""
        chunks = _split_chunks(content)

        if len(chunks) <= 1:
            result.append(msg)
            continue

        try:
            corpus = chunks + [query]
            vec = TfidfVectorizer(min_df=1, token_pattern=r"(?u)\b\w+\b")
            tfidf = vec.fit_transform(corpus)
            scores = cosine_similarity(tfidf[:-1], tfidf[-1].reshape(1, -1)).flatten()
            kept = [c for c, s in zip(chunks, scores) if s >= threshold]
        except Exception:
            kept = chunks

        if not kept:
            kept = chunks  # never empty a message

        new_content = "\n\n".join(kept)
        if decisions is not None and len(kept) < len(chunks):
            bid = block_ids[i] if block_ids is not None else i
            tokens_saved = len(content.split()) - len(new_content.split())
            decisions.append(
                BlockDecision(
                    block_id=bid,
                    strategy_applied="rag_pruner",
                    action="dropped",
                    reason=(
                        f"{len(chunks) - len(kept)} chunk(s) below relevance "
                        f"threshold {threshold:.2f}"
                    ),
                    tokens_saved=max(0, tokens_saved),
                )
            )

        result.append({**msg, "content": new_content})

    return result
