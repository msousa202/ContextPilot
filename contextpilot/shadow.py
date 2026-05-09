from __future__ import annotations

import random

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from contextpilot.config import ContextPilotConfig
from contextpilot._utils import flatten_messages


def _response_text(response: object) -> str:
    """Extract text from an OpenAI or Anthropic response object."""
    # OpenAI: response.choices[0].message.content
    try:
        return response.choices[0].message.content or ""  # type: ignore[union-attr]
    except AttributeError:
        pass
    # Anthropic: response.content[0].text
    try:
        return response.content[0].text or ""  # type: ignore[union-attr]
    except (AttributeError, IndexError):
        pass
    return str(response)


def _text_similarity(a: str, b: str) -> float:
    try:
        vec = TfidfVectorizer(min_df=1, token_pattern=r"(?u)\b\w+\b")
        tfidf = vec.fit_transform([a, b])
        return float(cosine_similarity(tfidf[0], tfidf[1])[0][0])
    except Exception:
        return 0.0


class ShadowTester:
    """FR-005: A/B shadow testing.

    For a configured fraction of calls, sends both the compressed and the
    original payload. Compares responses using TF-IDF cosine similarity and
    records the quality delta in telemetry.
    """

    def __init__(self, config: ContextPilotConfig) -> None:
        self.config = config

    def should_shadow(self) -> bool:
        if not self.config.shadow_testing.enabled:
            return False
        return random.random() < self.config.shadow_testing.sample_rate

    def compare(self, response_compressed: object, response_original: object) -> float:
        """Return cosine similarity between two response texts (0–1)."""
        text_c = _response_text(response_compressed)
        text_o = _response_text(response_original)
        if not text_c or not text_o:
            return 0.0
        return _text_similarity(text_c, text_o)
