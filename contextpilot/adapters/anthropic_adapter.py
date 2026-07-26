from __future__ import annotations

import logging

from contextpilot.pipeline import Pipeline

log = logging.getLogger(__name__)


class _MessagesWrapper:
    def __init__(self, messages_api: object, pipeline: Pipeline) -> None:
        self._messages_api = messages_api
        self._pipeline = pipeline

    def create(self, *, model: str, messages: list[dict], **kwargs: object) -> object:
        system: str | None = kwargs.pop("system", None)  # type: ignore[assignment]
        optimized_msgs, optimized_sys, event = self._pipeline.optimize(
            messages, system=system, provider="anthropic", model=model
        )
        if optimized_sys is not None:
            kwargs["system"] = optimized_sys
        response = self._messages_api.create(  # type: ignore[attr-defined]
            model=model, messages=optimized_msgs, **kwargs
        )

        # FR-005: A/B shadow testing. For a sampled fraction of compressed
        # calls, also send the original payload and record response similarity.
        if not event.fallback_triggered and self._pipeline.shadow.should_shadow():
            try:
                shadow_kwargs = dict(kwargs)
                if system is not None:
                    shadow_kwargs["system"] = system
                original_response = self._messages_api.create(  # type: ignore[attr-defined]
                    model=model, messages=messages, **shadow_kwargs
                )
                event.shadow_similarity = self._pipeline.shadow.compare(response, original_response)
            except Exception as exc:  # shadow failures must never affect the caller
                log.warning("shadow comparison skipped: %s", exc)

        return response

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
