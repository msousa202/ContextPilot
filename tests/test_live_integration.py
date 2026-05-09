"""Live integration tests — real HTTP round-trip against a local mock server.

These tests use the actual openai SDK pointed at a localhost mock. They prove
that the wrapper intercepts calls, compresses messages, and sends them over
the wire exactly as a production call would — without spending any API credits.
"""
from __future__ import annotations

import pytest
from openai import OpenAI

import contextpilot
from tests.mock_server import MockOpenAIServer


@pytest.fixture(scope="module")
def server():
    s = MockOpenAIServer().start()
    yield s
    s.stop()


@pytest.fixture(autouse=True)
def clear_requests(server: MockOpenAIServer):
    server.clear()


def openai_client(server: MockOpenAIServer) -> OpenAI:
    return OpenAI(api_key="fake-key", base_url=server.base_url)


# ---------------------------------------------------------------------------
# FR-001: wrapper is transparent — response comes back unchanged
# ---------------------------------------------------------------------------

def test_response_returned_to_caller(server: MockOpenAIServer):
    client = contextpilot.wrap(openai_client(server))
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello"}],
    )
    assert response.choices[0].message.content == "[mock] Received 1 message(s)."


def test_model_arg_forwarded(server: MockOpenAIServer):
    client = contextpilot.wrap(openai_client(server))
    client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hi"}],
    )
    body = server.requests[-1]["body"]
    assert body["model"] == "gpt-4o-mini"


def test_extra_kwargs_forwarded(server: MockOpenAIServer):
    client = contextpilot.wrap(openai_client(server))
    client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hi"}],
        temperature=0.5,
        max_tokens=128,
    )
    body = server.requests[-1]["body"]
    assert body["temperature"] == 0.5
    assert body["max_tokens"] == 128


# ---------------------------------------------------------------------------
# Short conversation — no compression expected (within history window)
# ---------------------------------------------------------------------------

def test_short_conv_passes_through_unchanged(server: MockOpenAIServer):
    client = contextpilot.wrap(openai_client(server))
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is 2 + 2?"},
        {"role": "assistant", "content": "4"},
        {"role": "user", "content": "And 3 + 3?"},
    ]
    client.chat.completions.create(model="gpt-4o", messages=messages)
    sent = server.last_messages()
    assert len(sent) == len(messages)


# ---------------------------------------------------------------------------
# Long conversation — history summarization fires
# ---------------------------------------------------------------------------

def test_long_conv_is_compressed_over_wire(server: MockOpenAIServer):
    """Verify that fewer messages hit the wire after history compression."""
    client = contextpilot.wrap(
        openai_client(server),
        config={"compression": {"history_window": 3, "quality_threshold": 0}},
    )
    long_content = (
        "This is a detailed explanation of the topic covering technical context, "
        "domain knowledge, and examples relevant to the current conversation thread. "
    ) * 3  # ~90 words per message

    messages = [
        {"role": "user", "content": f"Turn {i}: {long_content}"}
        for i in range(10)
    ]
    client.chat.completions.create(model="gpt-4o", messages=messages)

    sent = server.last_messages()
    assert len(sent) < len(messages), (
        f"Expected fewer than {len(messages)} messages on the wire, got {len(sent)}"
    )
    # First message should be the summary block
    assert "[CTX" in sent[0]["content"]
    # Last 3 messages preserved (structural stripping may remove trailing whitespace)
    for sent_msg, orig_msg in zip(sent[-3:], messages[-3:]):
        assert sent_msg["role"] == orig_msg["role"]
        assert sent_msg["content"].strip() == orig_msg["content"].strip()


def test_recent_turns_always_preserved(server: MockOpenAIServer):
    """The last history_window messages must arrive at the endpoint unchanged."""
    client = contextpilot.wrap(
        openai_client(server),
        config={"compression": {"history_window": 2, "quality_threshold": 0}},
    )
    long_content = "word " * 60  # 60 tokens each

    messages = [
        {"role": "user", "content": f"Old turn {i}: {long_content}"}
        for i in range(8)
    ] + [
        {"role": "user", "content": "Recent turn A — must arrive unchanged."},
        {"role": "user", "content": "Recent turn B — must arrive unchanged."},
    ]
    client.chat.completions.create(model="gpt-4o", messages=messages)

    sent = server.last_messages()
    assert sent[-2]["content"] == "Recent turn A — must arrive unchanged."
    assert sent[-1]["content"] == "Recent turn B — must arrive unchanged."


# ---------------------------------------------------------------------------
# Zero-trust: no prompt content in telemetry
# ---------------------------------------------------------------------------

def test_no_prompt_content_in_telemetry(server: MockOpenAIServer):
    """FR-006: telemetry must never contain prompt text."""
    cfg = {
        "telemetry": {"enabled": True, "api_key": None},
        "compression": {"history_window": 6},
    }
    from contextpilot.pipeline import Pipeline
    from contextpilot.config import ContextPilotConfig

    pipeline = Pipeline(ContextPilotConfig.model_validate(cfg))
    secret = "TOP_SECRET_PASSWORD_XYZ"
    messages = [{"role": "user", "content": f"My secret is: {secret}"}]
    _, _, event = pipeline.optimize(messages)

    for value in event.to_dict().values():
        if isinstance(value, str):
            assert secret not in value, f"Secret found in telemetry field: {value}"


# ---------------------------------------------------------------------------
# System prompt forwarding
# ---------------------------------------------------------------------------

def test_system_prompt_is_forwarded(server: MockOpenAIServer):
    """System prompt should reach the mock server in the messages list."""
    client = contextpilot.wrap(openai_client(server))
    messages = [
        {"role": "system", "content": "You are a Python expert."},
        {"role": "user", "content": "What is a list comprehension?"},
    ]
    client.chat.completions.create(model="gpt-4o", messages=messages)

    sent = server.last_messages()
    assert sent[0]["role"] == "system"
    assert "Python expert" in sent[0]["content"]
