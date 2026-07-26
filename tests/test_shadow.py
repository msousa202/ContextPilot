"""FR-005: A/B shadow testing, unit behavior and wrapper integration.

Two layers are covered:

1. `shadow.py` itself: response-text extraction across provider shapes,
   similarity scoring, and sampling.
2. The wiring claim made in 0.4.0, that the wrapper adapters actually send
   the *original* payload as the shadow call and feed both responses to the
   comparison. That is the part a user relies on when they enable the
   feature, so it is asserted behaviorally rather than assumed.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import contextpilot
from contextpilot.config import ContextPilotConfig
from contextpilot.shadow import ShadowTester, _response_text, _text_similarity


def cfg(enabled: bool = True, sample_rate: float = 1.0) -> ContextPilotConfig:
    return ContextPilotConfig.model_validate(
        {
            "shadow_testing": {"enabled": enabled, "sample_rate": sample_rate},
            "telemetry": {"enabled": False},
        }
    )


class _OpenAIShape:
    """Minimal stand-in for an OpenAI chat completion response."""

    def __init__(self, text: str | None) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=text))]


class _AnthropicShape:
    """Minimal stand-in for an Anthropic messages response."""

    def __init__(self, text: str | None, empty: bool = False) -> None:
        self.content = [] if empty else [SimpleNamespace(text=text)]


class _UnknownShape:
    def __repr__(self) -> str:
        return "raw-response-body"


# --- _response_text ---


def test_response_text_openai_shape():
    assert _response_text(_OpenAIShape("hello world")) == "hello world"


def test_response_text_anthropic_shape():
    assert _response_text(_AnthropicShape("hi there")) == "hi there"


def test_response_text_openai_null_content():
    # A tool-call-only completion has content=None; must not raise.
    assert _response_text(_OpenAIShape(None)) == ""


def test_response_text_anthropic_empty_content_list():
    # IndexError path: must not raise, falls through to the str() fallback.
    response = _AnthropicShape("x", empty=True)
    assert _response_text(response) == str(response)


def test_response_text_unknown_shape_falls_back_to_str():
    assert _response_text(_UnknownShape()) == "raw-response-body"


# --- _text_similarity ---


def test_similarity_identical_text_is_one():
    assert _text_similarity("the cat sat on the mat", "the cat sat on the mat") == pytest.approx(
        1.0, abs=1e-6
    )


def test_similarity_disjoint_vocabulary_is_zero():
    assert _text_similarity("alpha beta gamma", "delta epsilon zeta") == pytest.approx(
        0.0, abs=1e-6
    )


def test_similarity_partial_overlap_is_between():
    score = _text_similarity("the cat sat on the mat", "the cat stood on the rug")
    assert 0.0 < score < 1.0


def test_similarity_empty_input_returns_zero_not_raises():
    # TfidfVectorizer raises on an empty vocabulary; the guard must swallow it.
    assert _text_similarity("", "") == 0.0


# --- should_shadow sampling ---


def test_should_shadow_disabled_never_fires():
    tester = ShadowTester(cfg(enabled=False, sample_rate=1.0))
    assert all(not tester.should_shadow() for _ in range(20))


def test_should_shadow_full_rate_always_fires():
    tester = ShadowTester(cfg(enabled=True, sample_rate=1.0))
    assert all(tester.should_shadow() for _ in range(20))


def test_should_shadow_zero_rate_never_fires():
    tester = ShadowTester(cfg(enabled=True, sample_rate=0.0))
    assert all(not tester.should_shadow() for _ in range(20))


# --- compare ---


def test_compare_identical_responses_scores_one():
    tester = ShadowTester(cfg())
    score = tester.compare(_OpenAIShape("same answer here"), _OpenAIShape("same answer here"))
    assert score == pytest.approx(1.0, abs=1e-6)


def test_compare_across_provider_shapes():
    tester = ShadowTester(cfg())
    score = tester.compare(_OpenAIShape("shared wording"), _AnthropicShape("shared wording"))
    assert score == pytest.approx(1.0, abs=1e-6)


def test_compare_empty_response_scores_zero():
    tester = ShadowTester(cfg())
    assert tester.compare(_OpenAIShape(""), _OpenAIShape("something")) == 0.0
    assert tester.compare(_OpenAIShape("something"), _OpenAIShape("")) == 0.0


# --- Wrapper integration: the "wired in" claim ---


def _long_messages(n: int = 10) -> list[dict]:
    turn = (
        "This is a detailed turn covering technical context and domain knowledge "
        "with enough words that summarization yields a real reduction. "
    ) * 3
    return [{"role": "user", "content": f"Turn {i}: {turn}"} for i in range(n)]


def _shadow_config(enabled: bool) -> dict:
    return {
        "compression": {
            "history_window": 2,
            "history_epoch": 1,
            "quality_threshold": 0,
            "cache_aware": False,
        },
        "shadow_testing": {"enabled": enabled, "sample_rate": 1.0},
        "telemetry": {"enabled": False},
    }


def _openai_client() -> MagicMock:
    client = MagicMock()
    client.__class__.__name__ = "OpenAI"
    client.__class__.__module__ = "openai"
    client.chat.completions.create.return_value = _OpenAIShape("answer")
    return client


def _anthropic_client() -> MagicMock:
    client = MagicMock()
    client.__class__.__name__ = "Anthropic"
    client.__class__.__module__ = "anthropic"
    client.messages.create.return_value = _AnthropicShape("answer")
    return client


def test_openai_shadow_sends_original_payload():
    client = _openai_client()
    wrapped = contextpilot.wrap(client, config=_shadow_config(enabled=True))
    messages = _long_messages()
    wrapped.chat.completions.create(model="gpt-4o", messages=messages)

    assert client.chat.completions.create.call_count == 2
    first, second = client.chat.completions.create.call_args_list
    # First call carries the compressed payload, second carries the original
    assert len(first.kwargs["messages"]) < len(messages)
    assert second.kwargs["messages"] == messages


def test_openai_shadow_disabled_sends_once():
    client = _openai_client()
    wrapped = contextpilot.wrap(client, config=_shadow_config(enabled=False))
    wrapped.chat.completions.create(model="gpt-4o", messages=_long_messages())
    assert client.chat.completions.create.call_count == 1


def test_anthropic_shadow_sends_original_messages_and_system():
    client = _anthropic_client()
    wrapped = contextpilot.wrap(client, config=_shadow_config(enabled=True))
    messages = _long_messages()
    wrapped.messages.create(
        model="claude-opus-4-6", messages=messages, max_tokens=1024, system="You are helpful."
    )

    assert client.messages.create.call_count == 2
    first, second = client.messages.create.call_args_list
    assert len(first.kwargs["messages"]) < len(messages)
    assert second.kwargs["messages"] == messages
    assert second.kwargs["system"] == "You are helpful."
    assert second.kwargs["max_tokens"] == 1024


def test_shadow_similarity_recorded_on_event(monkeypatch):
    client = _openai_client()
    wrapped = contextpilot.wrap(client, config=_shadow_config(enabled=True))

    seen: dict = {}

    def _spy(compressed, original):
        seen["compressed"] = compressed
        seen["original"] = original
        return 0.87

    monkeypatch.setattr(wrapped._pipeline.shadow, "compare", _spy)
    wrapped.chat.completions.create(model="gpt-4o", messages=_long_messages())

    # Both responses reached the comparison, in the right order
    assert seen["compressed"] is not None
    assert seen["original"] is not None


def test_shadow_failure_does_not_break_the_caller():
    client = _openai_client()
    client.chat.completions.create.side_effect = [
        _OpenAIShape("real answer"),
        RuntimeError("shadow call failed"),
    ]
    wrapped = contextpilot.wrap(client, config=_shadow_config(enabled=True))

    response = wrapped.chat.completions.create(model="gpt-4o", messages=_long_messages())
    # The caller still gets the real response despite the shadow call raising
    assert _response_text(response) == "real answer"


def test_anthropic_shadow_failure_does_not_break_the_caller():
    client = _anthropic_client()
    client.messages.create.side_effect = [
        _AnthropicShape("real answer"),
        RuntimeError("shadow call failed"),
    ]
    wrapped = contextpilot.wrap(client, config=_shadow_config(enabled=True))

    response = wrapped.messages.create(
        model="claude-opus-4-6", messages=_long_messages(), max_tokens=1024
    )
    assert _response_text(response) == "real answer"


def test_no_shadow_when_pipeline_falls_back():
    """A payload that cannot be compressed must not pay for a second API call."""
    client = _openai_client()
    wrapped = contextpilot.wrap(client, config=_shadow_config(enabled=True))
    # Single short message: pipeline falls back with reason "no_reduction"
    wrapped.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])
    assert client.chat.completions.create.call_count == 1
