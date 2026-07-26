from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from contextpilot.config import ContextPilotConfig
from contextpilot.content import message_text


class BlockClass(str, Enum):
    ESSENTIAL = "essential"
    COMPRESSIBLE = "compressible"
    DROPPABLE = "droppable"


class Intent(str, Enum):
    """FR-002b: Conversation intent, steers how aggressively each strategy compresses."""

    DEBUG = "debug"
    BUILD = "build"
    EXPLORE = "explore"
    REFACTOR = "refactor"
    UNKNOWN = "unknown"


@dataclass
class MessageBlock:
    index: int
    role: str
    content: str
    staleness: float  # 0.0 = fresh (recent), 1.0 = stale (old)
    redundancy: float  # 0.0 = unique, 1.0 = duplicate of another block
    relevance: float  # 0.0 = irrelevant, 1.0 = highly relevant to latest query
    density: float  # 0.0 = sparse, 1.0 = information-dense
    classification: BlockClass = BlockClass.ESSENTIAL
    token_count: int = 0  # approximate word-based count
    intent: Intent = Intent.UNKNOWN  # conversation intent detected for this analyze() call

    @property
    def composite_score(self) -> float:
        """Value of this block: higher means keep it. Used for triage decisions."""
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


# Shared with strategies/history.py so debug-turn error excerpts use the same signal.
DEBUG_SIGNAL_PATTERN = re.compile(
    r"traceback \(most recent call last\)|\berror:|\bexception\b|\bstack trace\b|"
    r"file \"[^\"]+\", line \d+|\btypeerror\b|\bvalueerror\b|\bkeyerror\b|"
    r"\bassertionerror\b|\bnullpointerexception\b|\bsegmentation fault\b|"
    r"\bfailed\b|exit code [1-9]",
    re.IGNORECASE,
)
_REFACTOR_DIFF_PATTERN = re.compile(r"^(?:diff --git|@@ .* @@|[+-][^+\-\n].*)$", re.MULTILINE)
_REFACTOR_KEYWORD_PATTERN = re.compile(
    r"\brefactor\w*\b|\brename\w*\b|\bextract (?:method|function|class)\b|"
    r"\bclean ?up\b|\bsimplify\b|\bdead code\b",
    re.IGNORECASE,
)
_EXPLORE_KEYWORD_PATTERN = re.compile(
    r"\bwhat is\b|\bwhat's\b|\bhow does\b|\bhow do i\b|\bwhy (?:is|does|do)\b|"
    r"\bcan you explain\b|\bexplain\b|\bwhat are\b",
    re.IGNORECASE,
)
_INTENT_PRIORITY = {Intent.DEBUG: 3, Intent.REFACTOR: 2, Intent.EXPLORE: 1}


def detect_intent(messages: list[dict], window: int = 4) -> Intent:
    """Cheap, deterministic intent heuristic: regex/keyword only, no LLM call.

    Examines the last `window` turns. Returns BUILD when there is
    conversational content but no strong signal, UNKNOWN when there is
    nothing to analyze.
    """
    recent = [m for m in messages[-window:] if message_text(m).strip()]
    if not recent:
        return Intent.UNKNOWN

    texts = [message_text(m) for m in recent]
    joined = "\n".join(texts)

    debug_score = len(DEBUG_SIGNAL_PATTERN.findall(joined))
    refactor_score = (
        len(_REFACTOR_DIFF_PATTERN.findall(joined)) * 2  # diff hunks = strong signal
        + len(_REFACTOR_KEYWORD_PATTERN.findall(joined))
    )
    explore_score = len(_EXPLORE_KEYWORD_PATTERN.findall(joined))
    question_ratio = sum(1 for t in texts if t.rstrip().endswith("?")) / len(texts)
    avg_words = sum(len(t.split()) for t in texts) / len(texts)
    if question_ratio >= 0.5 and avg_words <= 25:
        explore_score += 2

    scores = {
        Intent.DEBUG: debug_score,
        Intent.REFACTOR: refactor_score,
        Intent.EXPLORE: explore_score,
    }
    best_intent, best_score = max(scores.items(), key=lambda kv: (kv[1], _INTENT_PRIORITY[kv[0]]))
    return Intent.BUILD if best_score < 1 else best_intent


class Analyzer:
    """FR-002: Context analysis engine.

    Scores each message block across four dimensions (staleness, redundancy,
    relevance, density) and classifies it as essential / compressible / droppable.
    Analysis target: < 50 ms for up to 100K tokens (technical doc §8).
    """

    def __init__(self, config: ContextPilotConfig) -> None:
        self.config = config

    def analyze(self, messages: list[dict], system: str | None = None) -> list[MessageBlock]:
        n = len(messages)
        if n == 0:
            return []

        texts = [message_text(m) for m in messages]

        # Most recent user message drives relevance scoring
        recent_user = next(
            (message_text(m) for m in reversed(messages) if m.get("role") == "user"),
            "",
        )

        redundancies, relevances = self._score_tfidf(texts, recent_user, n)

        override = self.config.compression.intent_override
        intent = (
            Intent(override)
            if override
            else detect_intent(messages, window=self.config.compression.intent_detection_window)
        )

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
                    intent=intent,
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
