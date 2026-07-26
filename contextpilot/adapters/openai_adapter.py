from __future__ import annotations

import logging

from contextpilot.pipeline import Pipeline

log = logging.getLogger(__name__)


class _CompletionsWrapper:
    def __init__(self, completions: object, pipeline: Pipeline) -> None:
        self._completions = completions
        self._pipeline = pipeline

    def create(self, *, model: str, messages: list[dict], **kwargs: object) -> object:
        optimized, _, event = self._pipeline.optimize(messages, provider="openai", model=model)
        response = self._completions.create(  # type: ignore[attr-defined]
            model=model, messages=optimized, **kwargs
        )

        # FR-005: A/B shadow testing. For a sampled fraction of compressed
        # calls, also send the original payload and record response similarity.
        if not event.fallback_triggered and self._pipeline.shadow.should_shadow():
            try:
                original_response = self._completions.create(  # type: ignore[attr-defined]
                    model=model, messages=messages, **kwargs
                )
                event.shadow_similarity = self._pipeline.shadow.compare(response, original_response)
            except Exception as exc:  # shadow failures must never affect the caller
                log.warning("shadow comparison skipped: %s", exc)

        return response


class _ChatWrapper:
    def __init__(self, chat: object, pipeline: Pipeline) -> None:
        self._chat = chat
        self.completions = _CompletionsWrapper(chat.completions, pipeline)  # type: ignore[attr-defined]

    def __getattr__(self, name: str) -> object:
        return getattr(self._chat, name)


class OpenAIWrapper:
    """FR-001: Drop-in wrapper for openai.OpenAI.

    Intercepts chat.completions.create() calls, runs the compression pipeline,
    and forwards the optimised payload. All other attributes delegate to the
    original client unchanged.
    """

    def __init__(self, client: object, pipeline: Pipeline) -> None:
        self._client = client
        self._pipeline = pipeline
        self.chat = _ChatWrapper(client.chat, pipeline)  # type: ignore[attr-defined]

    def __getattr__(self, name: str) -> object:
        return getattr(self._client, name)
