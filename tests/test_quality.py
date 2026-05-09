import pytest
from contextpilot.config import ContextPilotConfig
from contextpilot.quality import QualityGate


def cfg(threshold: float = 85.0) -> ContextPilotConfig:
    return ContextPilotConfig.model_validate({"compression": {"quality_threshold": threshold}})


def msgs(*texts: str) -> list[dict]:
    return [{"role": "user", "content": t} for t in texts]


def test_identical_content_scores_100():
    q = QualityGate(cfg())
    m = msgs("The quick brown fox jumps over the lazy dog.")
    score = q.score(m, m)
    assert score == 100.0


def test_empty_original_scores_100():
    q = QualityGate(cfg())
    assert q.score([], []) == 100.0
    assert q.score(msgs(""), msgs("")) == 100.0


def test_completely_different_content_scores_low():
    q = QualityGate(cfg())
    orig = msgs("Python programming language syntax functions classes")
    comp = msgs("Ancient Rome Julius Caesar Colosseum gladiators Senate")
    score = q.score(orig, comp)
    assert score < 60.0


def test_similar_content_scores_high():
    q = QualityGate(cfg())
    orig = msgs("Python is a high-level programming language designed for readability.")
    comp = msgs("Python is a high-level language designed for readability and simplicity.")
    score = q.score(orig, comp)
    assert score > 70.0


def test_passes_gate_above_threshold():
    q = QualityGate(cfg(threshold=80.0))
    m = msgs("Hello world, this is a test message with good content.")
    passes, score = q.passes(m, m)
    assert passes is True
    assert score == 100.0


def test_fails_gate_below_threshold():
    q = QualityGate(cfg(threshold=80.0))
    orig = msgs("Python programming language functions classes objects")
    unrelated = msgs("The ocean is deep and wide with many fish and coral reefs")
    passes, score = q.passes(orig, unrelated)
    assert passes is False
    assert score < 80.0


def test_score_with_system_prompt():
    q = QualityGate(cfg())
    m = msgs("Hello")
    system = "You are a helpful assistant."
    score = q.score(m, m, system=system, compressed_system=system)
    assert score == 100.0


def test_score_range():
    q = QualityGate(cfg())
    orig = msgs("Some content here about Python")
    comp = msgs("Python content")
    score = q.score(orig, comp)
    assert 0.0 <= score <= 100.0
