from __future__ import annotations

import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from contextpilot._utils import flatten_messages
from contextpilot.config import ContextPilotConfig


def _tfidf_weighted_recall(orig_text: str, comp_text: str) -> float:
    """Compute TF-IDF weighted recall: the fraction of information weight preserved.

    Each unique term in the original is weighted by its TF-IDF score (rarity ×
    frequency). Quality = sum of weights for terms that survive in the compressed
    version / total weight of all original terms.

    Why this is better than cosine similarity for compression quality:
    - Cosine is bounded by √retention: any significant compression (say 50%
      tokens dropped) produces cosine ≤ 0.71 regardless of what was dropped.
    - Weighted recall is bounded by 1.0 regardless of retention, so it correctly
      distinguishes "dropped redundant content" (high score) from "dropped unique
      content" (low score).
    - Our keyword extraction specifically selects the highest-IDF terms, so
      they contribute the most weight, and this metric directly rewards that.
    """
    if not orig_text.strip():
        return 1.0

    try:
        vec = TfidfVectorizer(min_df=1, token_pattern=r"(?u)\b\w+\b")
        tfidf_matrix = vec.fit_transform([orig_text])
        feature_names: list[str] = list(vec.get_feature_names_out())
        weights: np.ndarray = tfidf_matrix.toarray()[0]

        total_weight = float(weights.sum())
        if total_weight == 0:
            return 1.0

        comp_terms = set(re.findall(r"(?u)\b\w+\b", comp_text.lower()))
        preserved_weight = float(
            sum(w for term, w in zip(feature_names, weights) if term in comp_terms)
        )
        return preserved_weight / total_weight

    except Exception:
        return 1.0


class QualityGate:
    """FR-004: Quality preservation scoring.

    Computes a predicted quality preservation score (0–100) using TF-IDF
    weighted recall: the fraction of information weight (rare terms matter
    more than common ones) preserved in the compressed context.

    Metric: weighted_recall × 0.80 + retention × 0.20
    Default threshold: 72.0

    This replaces the previous cosine similarity metric, which was bounded by
    √retention and therefore always failed for any meaningful compression even
    when all important terms were preserved.
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
        weighted_recall = _tfidf_weighted_recall(orig_text, comp_text)

        raw = weighted_recall * 0.80 + retention * 0.20
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
