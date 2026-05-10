from __future__ import annotations

from contextpilot.pipeline import Pipeline


class _MessagesWrapper:
    def __init__(self, messages_api: object, pipeline: Pipeline) -> None:
        self._messages_api = messages_api
        self._pipeline = pipeline

    def create(self, *, model: str, messages: list[dict], **kwargs: object) -> object:
        system: str | None = kwargs.pop("system", None)  # type: ignore[assignment]
        optimized_msgs, optimized_sys, _ = self._pipeline.optimize(
            messages, system=system, provider="anthropic", model=model
        )
        if optimized_sys is not None:
            kwargs["system"] = optimized_sys
        return self._messages_api.create(model=model, messages=optimized_msgs, **kwargs)  # type: ignore[attr-defined]

    def __getattr__(self, name: str) -> object:
        return getattr(self._messages_api, name)


class AnthropicWrapper:
    """FR-001: Drop-in wrapper for anthropic.Anthropic.

    Intercepts messages.create() calls, runs the compression pipeline on the
    message list and optional system prompt, and forwards the optimised payload.
    All other attributes delegate to the original client unchanged.
    """

    def __init__(self, client: object, pipeline: Pipeline) -> None:
        self._client = client
        self._pipeline = pipeline
        self.messages = _MessagesWrapper(client.messages, pipeline)  # type: ignore[attr-defined]

    def __getattr__(self, name: str) -> object:
        return getattr(self._client, name)
