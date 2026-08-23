from contextpilot.analyzer import Analyzer, BlockClass
from contextpilot.config import ContextPilotConfig


def cfg(**kwargs) -> ContextPilotConfig:
    return ContextPilotConfig.model_validate({"compression": kwargs} if kwargs else {})


def test_empty_messages():
    a = Analyzer(cfg())
    assert a.analyze([]) == []


def test_single_message_is_essential():
    a = Analyzer(cfg())
    blocks = a.analyze([{"role": "user", "content": "Hello"}])
    assert len(blocks) == 1
    assert blocks[0].classification == BlockClass.ESSENTIAL
    assert blocks[0].staleness == 0.0


def test_system_message_always_essential():
    a = Analyzer(cfg())
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hi"},
    ]
    blocks = a.analyze(messages)
    assert blocks[0].role == "system"
    assert blocks[0].classification == BlockClass.ESSENTIAL


def test_recent_window_is_essential():
    a = Analyzer(cfg(history_window=3))
    messages = [{"role": "user", "content": f"Message {i}"} for i in range(10)]
    blocks = a.analyze(messages)
    # Last 3 messages must be essential
    for b in blocks[-3:]:
        assert b.classification == BlockClass.ESSENTIAL


def test_staleness_increases_with_age():
    a = Analyzer(cfg())
    messages = [{"role": "user", "content": f"Turn {i}"} for i in range(5)]
    blocks = a.analyze(messages)
    # Oldest message has highest staleness
    assert blocks[0].staleness > blocks[-1].staleness


def test_redundancy_for_duplicate_content():
    a = Analyzer(cfg())
    text = "The quick brown fox jumps over the lazy dog"
    messages = [
        {"role": "user", "content": text},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": text},  # exact duplicate
    ]
    blocks = a.analyze(messages)
    # The two identical messages should have high redundancy vs each other
    assert blocks[0].redundancy > 0.5 or blocks[2].redundancy > 0.5


def test_density_for_sparse_content():
    a = Analyzer(cfg())
    messages = [{"role": "user", "content": "ok ok ok ok ok ok ok ok"}]
    blocks = a.analyze(messages)
    # Repeated word → low density
    assert blocks[0].density < 0.5


def test_composite_score_range():
    a = Analyzer(cfg())
    messages = [{"role": "user", "content": f"Some content {i}"} for i in range(4)]
    blocks = a.analyze(messages)
    for b in blocks:
        assert 0.0 <= b.composite_score <= 1.0


def test_classification_levels():
    """Conservative mode should classify fewer blocks as droppable."""
    msgs = [{"role": "user", "content": f"Old message {i}"} for i in range(20)]

    a_balanced = Analyzer(cfg(level="balanced", history_window=2))
    a_conservative = Analyzer(cfg(level="conservative", history_window=2))

    balanced_dropped = sum(
        1 for b in a_balanced.analyze(msgs) if b.classification == BlockClass.DROPPABLE
    )
    conservative_dropped = sum(
        1 for b in a_conservative.analyze(msgs) if b.classification == BlockClass.DROPPABLE
    )
    assert conservative_dropped <= balanced_dropped


def test_token_count():
    a = Analyzer(cfg())
    messages = [{"role": "user", "content": "one two three"}]
    blocks = a.analyze(messages)
    assert blocks[0].token_count == 3
