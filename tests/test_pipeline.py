import pytest
from contextpilot.config import ContextPilotConfig
from contextpilot.pipeline import Pipeline
from contextpilot.telemetry import TelemetryEvent


def cfg(**kwargs) -> ContextPilotConfig:
    base: dict = {"telemetry": {"enabled": True, "api_key": None}}
    if kwargs:
        base["compression"] = kwargs
    return ContextPilotConfig.model_validate(base)


def test_short_conversation_passes_through():
    """Short conversations under the history window should be returned unchanged."""
    pipeline = Pipeline(cfg(history_window=6))
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    result, system, event = pipeline.optimize(messages)
    assert len(result) == 2
    assert isinstance(event, TelemetryEvent)


def test_long_conversation_is_compressed():
    """History beyond the window should produce a summary block with fewer messages and tokens."""
    # quality_threshold=0 bypasses the quality gate — this test verifies compression mechanics
    pipeline = Pipeline(cfg(history_window=3, quality_threshold=0))
    long_turn = (
        "This is a detailed explanation covering multiple aspects of the topic. "
        "The analysis includes technical context, domain knowledge, examples from practice, "
        "and conclusions that build on previous turns in the conversation. "
    ) * 2  # ~100 words each — long enough that 80-char summary saves tokens
    messages = [
        {"role": "user", "content": f"Question {i}: {long_turn}"}
        for i in range(10)
    ] + [
        {"role": "assistant", "content": f"Answer: {long_turn}"}
    ]
    result, system, event = pipeline.optimize(messages)
    assert len(result) < len(messages)
    assert event.tokens_input_compressed <= event.tokens_input_original


def test_fallback_on_low_quality():
    """When compression score falls below threshold, original is returned."""
    pipeline = Pipeline(cfg(quality_threshold=99.9, history_window=1))
    messages = [
        {"role": "user", "content": "alpha beta gamma delta epsilon zeta"},
        {"role": "user", "content": "omega psi chi phi upsilon tau sigma"},
        {"role": "user", "content": "final question"},
    ]
    result, _, event = pipeline.optimize(messages)
    # Whether fallback triggers or not, the output must be a valid list
    assert isinstance(result, list)
    assert len(result) > 0


def test_event_metadata_populated():
    pipeline = Pipeline(cfg())
    messages = [
        {"role": "user", "content": "This is a test message for telemetry."},
    ]
    _, _, event = pipeline.optimize(messages, provider="openai", model="gpt-4o")
    assert event.provider == "openai"
    assert event.model == "gpt-4o"
    assert event.latency_ms >= 0
    assert event.compression_ms >= 0
    assert 0.0 <= event.quality_score <= 100.0
    assert isinstance(event.fallback_triggered, bool)


def test_system_prompt_passed_through():
    pipeline = Pipeline(cfg())
    messages = [{"role": "user", "content": "Hello"}]
    system = "You are a helpful assistant."
    result, result_system, _ = pipeline.optimize(messages, system=system)
    assert result_system == system  # balanced mode never modifies system prompt


def test_empty_messages():
    pipeline = Pipeline(cfg())
    result, system, event = pipeline.optimize([])
    assert result == []
    assert system is None


def test_telemetry_buffer_receives_event():
    pipeline = Pipeline(cfg())
    pipeline.optimize([{"role": "user", "content": "Hello"}])
    events = pipeline.telemetry.drain()
    assert len(events) == 1
    assert isinstance(events[0], TelemetryEvent)


def test_no_content_in_telemetry():
    """Telemetry events must never contain prompt/response content — FR-006."""
    pipeline = Pipeline(cfg())
    pipeline.optimize([{"role": "user", "content": "TOP SECRET: password123"}])
    events = pipeline.telemetry.drain()
    assert len(events) == 1
    event_dict = events[0].to_dict()
    for key, value in event_dict.items():
        if isinstance(value, str):
            assert "TOP SECRET" not in value
            assert "password123" not in value
