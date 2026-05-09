from __future__ import annotations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from contextpilot.config import ContextPilotConfig
from contextpilot._utils import flatten_messages, word_count_messages


class QualityGate:
    """FR-004: Quality preservation scoring.

    Computes a predicted quality preservation score (0–100) by combining:
    - Semantic similarity between original and compressed content (TF-IDF cosine, weight 0.7)
    - Token retention ratio (weight 0.3)

    If the score is below `quality_threshold`, the original payload is used
    as a safe fallback — the library never degrades output quality silently.
    """

    def __init__(self, config: ContextPilotConfig) -> None:
        self.config = config

    def score(
        self,
        original: list[dict],
        compressed: list[dict],
        system: str | None = None,
        compressed_system: str | None = None,
    ) -> float:
        orig_text = flatten_messages(original, system)
        comp_text = flatten_messages(compressed, compressed_system)

        if not orig_text.strip():
            return 100.0

        orig_words = len(orig_text.split())
        comp_words = len(comp_text.split())
        if orig_words == 0:
            return 100.0

        retention = min(comp_words / orig_words, 1.0)

        try:
            vec = TfidfVectorizer(min_df=1, token_pattern=r"(?u)\b\w+\b")
            tfidf = vec.fit_transform([orig_text, comp_text])
            semantic_sim = float(cosine_similarity(tfidf[0], tfidf[1])[0][0])
        except Exception:
            semantic_sim = retention  # graceful fallback

        raw = semantic_sim * 0.7 + retention * 0.3
        return round(min(raw * 100.0, 100.0), 2)

    def passes(
        self,
        original: list[dict],
        compressed: list[dict],
        system: str | None = None,
        compressed_system: str | None = None,
    ) -> tuple[bool, float]:
        """Return (passes_gate, score). False → caller should use original payload."""
        s = self.score(original, compressed, system, compressed_system)
        return s >= self.config.compression.quality_threshold, s
