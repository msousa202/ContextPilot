from __future__ import annotations

import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from contextpilot.analyzer import Intent
from contextpilot.config import ContextPilotConfig
from contextpilot.content import is_plain_string, message_has_cache_control
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


def _leading_query(text: str) -> str:
    """The message's own question: text before the first chunk delimiter.

    Using the message's own leading text as the relevance query makes pruning
    a pure function of the message, so an already-pruned turn prunes to the
    same bytes on every later request and the forwarded prefix stays stable.
    """
    m = _CHUNK_DELIMITERS.search(text)
    if m and m.start() > 0:
        return text[: m.start()].strip()
    return ""


def _score_and_filter(
    chunks: list[str], query: str, threshold: float, vectorizer: TfidfVectorizer
) -> list[str]:
    try:
        corpus = chunks + [query]
        tfidf = vectorizer.fit_transform(corpus)
        scores = cosine_similarity(tfidf[:-1], tfidf[-1].reshape(1, -1)).flatten()
        kept = [c for c, s in zip(chunks, scores) if s >= threshold]
    except Exception:
        kept = chunks
    return kept if kept else chunks  # never empty a message


def prune_rag_chunks(
    messages: list[dict],
    query: str,
    config: ContextPilotConfig,
    intent: Intent = Intent.UNKNOWN,
    block_ids: list[int] | None = None,
    decisions: list[BlockDecision] | None = None,
) -> list[dict]:
    """FR-003c: RAG chunk pruning, cache-stable variant.

    Scores chunks with TF-IDF cosine similarity (no embedding model,
    technical doc §3.3) and drops those below the relevance threshold.

    Cache-stability contract:
    - Historical messages are pruned against their own leading text (the
      question that precedes the retrieved chunks), a pure per-message
      function, so their pruned bytes never change across requests. Messages
      without leading text are left untouched.
    - Only the final message may additionally be pruned against the current
      conversation query, and only there does `intent` adjust the threshold
      (raised for `refactor`/`explore`, lowered for `debug`). The final
      message is the one region of the payload the provider has not cached
      yet, so query-aware pruning is free there and only there.
    """
    base = config.compression.rag_relevance_min
    if intent == Intent.REFACTOR:
        final_threshold = max(base, 0.35)
    elif intent == Intent.EXPLORE:
        final_threshold = max(base, 0.25)
    elif intent == Intent.DEBUG:
        final_threshold = base * 0.5
    else:
        final_threshold = base

    result: list[dict] = []
    last = len(messages) - 1
    try:
        vectorizer = TfidfVectorizer(min_df=1, token_pattern=r"(?u)\b\w+\b")
    except Exception:
        vectorizer = None

    for i, msg in enumerate(messages):
        if not is_plain_string(msg) or message_has_cache_control(msg):
            result.append(msg)
            continue

        content = msg.get("content") or ""
        chunks = _split_chunks(content)
        if len(chunks) <= 1:
            result.append(msg)
            continue

        is_final = i == last
        own_query = _leading_query(content)
        effective_query = own_query or (query if is_final else "")
        if not effective_query:
            result.append(msg)
            continue
        threshold = final_threshold if is_final else base

        kept = (
            chunks
            if vectorizer is None
            else _score_and_filter(chunks, effective_query, threshold, vectorizer)
        )

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
