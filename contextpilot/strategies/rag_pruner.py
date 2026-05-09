from __future__ import annotations

import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from contextpilot.config import ContextPilotConfig

# Delimiters that RAG pipelines commonly use to separate retrieved chunks
_CHUNK_DELIMITERS = re.compile(
    r"(?:^|\n)(?:---+\s*(?:DOCUMENT|DOC|CHUNK|SOURCE|RESULT)\s*\d*\s*---+"
    r"|<(?:doc|document|chunk|source)(?:\s[^>]*)?>(?=\s))",
    re.IGNORECASE,
)


def _split_chunks(text: str) -> list[str]:
    """Split text into RAG chunks if chunk delimiters are present."""
    parts = _CHUNK_DELIMITERS.split(text)
    chunks = [p.strip() for p in parts if p.strip()]
    return chunks if len(chunks) > 1 else [text]


def prune_rag_chunks(
    messages: list[dict],
    query: str,
    config: ContextPilotConfig,
) -> list[dict]:
    """FR-003c: RAG chunk pruning.

    For each message that appears to contain multiple RAG chunks, scores each
    chunk against the current query using TF-IDF cosine similarity and removes
    chunks below the configured relevance threshold (default 0.15). Requires
    no embedding model — uses scikit-learn TF-IDF (technical doc §3.3).
    """
    threshold = config.compression.rag_relevance_min
    if not query:
        return messages

    result: list[dict] = []
    for msg in messages:
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

        result.append({**msg, "content": "\n\n".join(kept)})

    return result
