"""FR-001: SDK wrapper integration tests using mocked clients."""
from unittest.mock import MagicMock

import pytest

import contextpilot
from contextpilot.adapters.anthropic_adapter import AnthropicWrapper
from contextpilot.adapters.openai_adapter import OpenAIWrapper
from contextpilot.config import ContextPilotConfig


def make_openai_client() -> MagicMock:
    client = MagicMock()
    client.__class__.__name__ = "OpenAI"
    client.__class__.__module__ = "openai"
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "Hello!"
    client.chat.completions.create.return_value = response
    return client


def make_anthropic_client() -> MagicMock:
    client = MagicMock()
    client.__class__.__name__ = "Anthropic"
    client.__class__.__module__ = "anthropic"
    response = MagicMock()
    response.content = [MagicMock()]
    response.content[0].text = "Hi there!"
    client.messages.create.return_value = response
    return client


# --- wrap() detection ---

def test_wrap_detects_openai():
    client = make_openai_client()
    wrapped = contextpilot.wrap(client)
    assert isinstance(wrapped, OpenAIWrapper)


def test_wrap_detects_anthropic():
    client = make_anthropic_client()
    wrapped = contextpilot.wrap(client)
    assert isinstance(wrapped, AnthropicWrapper)


def test_wrap_unsupported_raises():
    bad_client = MagicMock()
    bad_client.__class__.__name__ = "SomeOtherClient"
    bad_client.__class__.__module__ = "some.other.module"
    with pytest.raises(ValueError, match="Unsupported client type"):
        contextpilot.wrap(bad_client)


def test_wrap_accepts_config_dict():
    client = make_openai_client()
    wrapped = contextpilot.wrap(client, config={"compression": {"level": "conservative"}})
    assert isinstance(wrapped, OpenAIWrapper)


def test_wrap_accepts_config_object():
    client = make_anthropic_client()
    cfg = ContextPilotConfig.model_validate({"compression": {"level": "aggressive"}})
    wrapped = contextpilot.wrap(client, config=cfg)
    assert isinstance(wrapped, AnthropicWrapper)


# --- OpenAI wrapper ---

def test_openai_wrapper_calls_original_create():
    client = make_openai_client()
    wrapped = contextpilot.wrap(client, config={"telemetry": {"enabled": False}})
    messages = [{"role": "user", "content": "Hello"}]
    response = wrapped.chat.completions.create(model="gpt-4o", messages=messages)
    assert client.chat.completions.create.called
    assert response.choices[0].message.content == "Hello!"


def test_openai_wrapper_compresses_long_history():
    client = make_openai_client()
    # quality_threshold=0 bypasses quality gate — test verifies compression mechanics
    wrapped = contextpilot.wrap(
        client,
        config={
            "compression": {"history_window": 2, "quality_threshold": 0},
            "telemetry": {"enabled": False},
        },
    )
    long_turn = (
        "This is a detailed turn in our conversation covering important context "
        "about the current topic. It contains enough words that the summary header "
        "overhead is small relative to the token savings achieved by truncation. "
    ) * 2  # ~100 words each
    messages = [{"role": "user", "content": f"Turn {i}: {long_turn}"} for i in range(10)]
    wrapped.chat.completions.create(model="gpt-4o", messages=messages)

    called_messages = client.chat.completions.create.call_args.kwargs["messages"]
    assert len(called_messages) < len(messages)


def test_openai_wrapper_preserves_model_arg():
    client = make_openai_client()
    wrapped = contextpilot.wrap(client, config={"telemetry": {"enabled": False}})
    wrapped.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}])
    assert client.chat.completions.create.call_args.kwargs["model"] == "gpt-4o-mini"


def test_openai_wrapper_forwards_extra_kwargs():
    client = make_openai_client()
    wrapped = contextpilot.wrap(client, config={"telemetry": {"enabled": False}})
    wrapped.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.7,
        max_tokens=256,
    )
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["temperature"] == 0.7
    assert kwargs["max_tokens"] == 256


def test_openai_wrapper_delegates_other_attrs():
    client = make_openai_client()
    client.api_key = "sk-test"
    wrapped = contextpilot.wrap(client, config={"telemetry": {"enabled": False}})
    assert wrapped.api_key == "sk-test"


# --- Anthropic wrapper ---

def test_anthropic_wrapper_calls_original_create():
    client = make_anthropic_client()
    wrapped = contextpilot.wrap(client, config={"telemetry": {"enabled": False}})
    messages = [{"role": "user", "content": "Hello"}]
    response = wrapped.messages.create(model="claude-3-5-sonnet-20241022", messages=messages, max_tokens=1024)
    assert client.messages.create.called
    assert response.content[0].text == "Hi there!"


def test_anthropic_wrapper_passes_system():
    client = make_anthropic_client()
    wrapped = contextpilot.wrap(client, config={"telemetry": {"enabled": False}})
    wrapped.messages.create(
        model="claude-3-5-sonnet-20241022",
        messages=[{"role": "user", "content": "Hello"}],
        max_tokens=256,
        system="You are helpful.",
    )
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs.get("system") == "You are helpful."


def test_anthropic_wrapper_compresses_long_history():
    client = make_anthropic_client()
    # quality_threshold=0 bypasses quality gate — test verifies compression mechanics
    wrapped = contextpilot.wrap(
        client,
        config={
            "compression": {"history_window": 2, "quality_threshold": 0},
            "telemetry": {"enabled": False},
        },
    )
    long_content = (
        "This is a detailed explanation of the topic at hand covering technical context "
        "and domain-specific knowledge that contributes substantive information. "
    ) * 3  # ~90 words per message
    messages = [{"role": "user", "content": f"Turn {i}: {long_content}"} for i in range(10)]
    wrapped.messages.create(model="claude-3-5-sonnet-20241022", messages=messages, max_tokens=1024)

    called_messages = client.messages.create.call_args.kwargs["messages"]
    assert len(called_messages) < len(messages)


def test_anthropic_wrapper_forwards_extra_kwargs():
    client = make_anthropic_client()
    wrapped = contextpilot.wrap(client, config={"telemetry": {"enabled": False}})
    wrapped.messages.create(
        model="claude-3-5-sonnet-20241022",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=512,
        temperature=0.5,
    )
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["max_tokens"] == 512
    assert kwargs["temperature"] == 0.5
