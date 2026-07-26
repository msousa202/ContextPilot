"""compression.level is a preset over real knobs, not a decorative field.

Before 0.4.1 `level` fed only `BlockClass` classification, which no strategy
ever read, so setting it changed nothing about the output. These tests pin the
contract so it cannot silently become a no-op again.
"""

import pytest
from pydantic import ValidationError

from contextpilot.config import ContextPilotConfig


def comp(**kwargs):
    return ContextPilotConfig.model_validate({"compression": kwargs}).compression


def test_levels_produce_different_knobs():
    conservative = comp(level="conservative")
    balanced = comp(level="balanced")
    aggressive = comp(level="aggressive")

    # More aggressive keeps fewer turns verbatim
    assert conservative.history_window > balanced.history_window > aggressive.history_window
    # More aggressive drops RAG chunks at a higher relevance floor
    assert (
        conservative.rag_relevance_min < balanced.rag_relevance_min < aggressive.rag_relevance_min
    )


def test_default_is_balanced():
    assert comp().level == "balanced"
    assert comp().history_window == comp(level="balanced").history_window


def test_explicit_field_overrides_preset():
    c = comp(level="aggressive", history_window=9)
    assert c.history_window == 9  # explicit value wins
    assert c.rag_relevance_min == pytest.approx(0.30)  # untouched field still preset


def test_explicit_field_overrides_preset_on_both_knobs():
    c = comp(level="conservative", history_window=2, rag_relevance_min=0.9)
    assert c.history_window == 2
    assert c.rag_relevance_min == pytest.approx(0.9)


def test_invalid_level_rejected():
    with pytest.raises(ValidationError, match="level must be one of"):
        comp(level="ultra")


def test_level_assignment_after_load_applies_preset():
    """`cfg.compression.level = "aggressive"` must work, not silently do nothing.

    Assigning after construction is the natural usage pattern (and what the
    benchmarks do). Without validate_assignment the model validator never
    re-runs and the preset is skipped.
    """
    cfg = ContextPilotConfig()
    baseline = cfg.compression.history_window
    cfg.compression.level = "aggressive"
    assert cfg.compression.history_window < baseline
    assert cfg.compression.rag_relevance_min == pytest.approx(0.30)


def test_explicit_assignment_survives_later_level_change():
    cfg = ContextPilotConfig()
    cfg.compression.history_window = 9
    cfg.compression.level = "aggressive"
    assert cfg.compression.history_window == 9


def test_invalid_level_assignment_rejected():
    cfg = ContextPilotConfig()
    with pytest.raises(ValidationError, match="level must be one of"):
        cfg.compression.level = "ultra"


def test_levels_change_pipeline_output():
    """End-to-end: the level actually reaches the compressed payload."""
    from contextpilot.pipeline import Pipeline

    messages = [
        {
            "role": "user",
            "content": f"Turn {i} discussing distinct topic number {i} " + "detail " * 40,
        }
        for i in range(14)
    ]

    def run(level: str) -> int:
        config = ContextPilotConfig.model_validate(
            {
                "compression": {
                    "level": level,
                    "history_epoch": 1,
                    "quality_threshold": 0,
                    "cache_aware": False,
                },
                "telemetry": {"enabled": False},
            }
        )
        optimized, _, _ = Pipeline(config).optimize([dict(m) for m in messages])
        return len(optimized)

    # Smaller history_window under aggressive means fewer messages forwarded
    assert run("aggressive") < run("conservative")
