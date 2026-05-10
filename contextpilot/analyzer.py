from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from contextpilot.config import ContextPilotConfig


class BlockClass(str, Enum):
    ESSENTIAL = "essential"
    COMPRESSIBLE = "compressible"
    DROPPABLE = "droppable"


@dataclass
class MessageBlock:
    index: int
    role: str
    content: str
    staleness: float       # 0.0 = fresh (recent), 1.0 = stale (old)
    redundancy: float      # 0.0 = unique, 1.0 = duplicate of another block
    relevance: float       # 0.0 = irrelevant, 1.0 = highly relevant to latest query
    density: float         # 0.0 = sparse, 1.0 = information-dense
    classification: BlockClass = BlockClass.ESSENTIAL
    token_count: int = 0   # approximate word-based count

    @property
    def composite_score(self) -> float:
        """Value of this block — higher means keep it. Used for triage decisions."""
        return (
            self.relevance * 0.4
            + self.density * 0.3
            + (1.0 - self.staleness) * 0.2
            + (1.0 - self.redundancy) * 0.1
        )


def _word_tokens(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


def _density(text: str) -> float:
    tokens = _word_tokens(text)
    if not tokens:
        return 0.0
    return len(set(tokens)) / len(tokens)


def _word_count(text: str) -> int:
    return len(text.split())


class Analyzer:
    """FR-002: Context analysis engine.

    Scores each message block across four dimensions — staleness, redundancy,
    relevance, density — and classifies it as essential / compressible / droppable.
    Analysis target: < 50 ms for up to 100K tokens (technical doc §8).
    """

    def __init__(self, config: ContextPilotConfig) -> None:
        self.config = config

    def analyze(
        self, messages: list[dict], system: str | None = None
    ) -> list[MessageBlock]:
        n = len(messages)
        if n == 0:
            return []

        texts = [m.get("content") or "" for m in messages]

        # Most recent user message drives relevance scoring
        recent_user = next(
            (m.get("content") or "" for m in reversed(messages) if m.get("role") == "user"),
            "",
        )

        redundancies, relevances = self._score_tfidf(texts, recent_user, n)

        blocks: list[MessageBlock] = []
        for i, msg in enumerate(messages):
            content = texts[i]
            role = msg.get("role", "user")
            # Index 0 = oldest = most stale
            staleness = 1.0 - (i / max(n - 1, 1))
            density = _density(content)
            redundancy = float(redundancies[i])
            relevance = float(relevances[i])

            classification = self._classify(
                role=role,
                index=i,
                total=n,
                staleness=staleness,
                redundancy=redundancy,
                relevance=relevance,
            )

            blocks.append(
                MessageBlock(
                    index=i,
                    role=role,
                    content=content,
                    staleness=staleness,
                    redundancy=redundancy,
                    relevance=relevance,
                    density=density,
                    classification=classification,
                    token_count=_word_count(content),
                )
            )

        return blocks

    def _score_tfidf(
        self, texts: list[str], recent_user: str, n: int
    ) -> tuple[list[float], list[float]]:
        corpus = texts + ([recent_user] if recent_user else [])
        try:
            vec = TfidfVectorizer(min_df=1, token_pattern=r"(?u)\b\w+\b")
            tfidf = vec.fit_transform(corpus)
            msg_vecs = tfidf[:n]

            # Redundancy: max cosine similarity against all *other* messages
            sim = cosine_similarity(msg_vecs)
            np.fill_diagonal(sim, 0.0)
            redundancies = sim.max(axis=1).tolist()

            # Relevance: cosine similarity to most recent user message
            if recent_user:
                user_vec = tfidf[n]
                relevances = cosine_similarity(msg_vecs, user_vec.reshape(1, -1)).flatten().tolist()
            else:
                relevances = [0.5] * n
        except Exception:
            redundancies = [0.0] * n
            relevances = [0.5] * n

        return redundancies, relevances

    def _classify(
        self,
        role: str,
        index: int,
        total: int,
        staleness: float,
        redundancy: float,
        relevance: float,
    ) -> BlockClass:
        # System messages and the most recent window are always kept
        if role == "system":
            return BlockClass.ESSENTIAL
        window = self.config.compression.history_window
        if index >= total - window:
            return BlockClass.ESSENTIAL

        level = self.config.compression.level
        if level == "conservative":
            # Only drop near-exact duplicates
            if redundancy > 0.95:
                return BlockClass.DROPPABLE
            if redundancy > 0.7:
                return BlockClass.COMPRESSIBLE
            return BlockClass.ESSENTIAL

        if level == "aggressive":
            if redundancy > 0.6 or (staleness > 0.5 and relevance < 0.15):
                return BlockClass.DROPPABLE
            if staleness > 0.3 or redundancy > 0.3:
                return BlockClass.COMPRESSIBLE
            return BlockClass.ESSENTIAL

        # balanced (default)
        if redundancy > 0.85 or (staleness > 0.7 and relevance < 0.2):
            return BlockClass.DROPPABLE
        if staleness > 0.5 or redundancy > 0.5:
            return BlockClass.COMPRESSIBLE
        return BlockClass.ESSENTIAL
