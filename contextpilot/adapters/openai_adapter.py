from __future__ import annotations

from contextpilot.pipeline import Pipeline


class _CompletionsWrapper:
    def __init__(self, completions: object, pipeline: Pipeline) -> None:
        self._completions = completions
        self._pipeline = pipeline

    def create(self, *, model: str, messages: list[dict], **kwargs: object) -> object:
        optimized, _, _ = self._pipeline.optimize(messages, provider="openai", model=model)
        return self._completions.create(model=model, messages=optimized, **kwargs)  # type: ignore[attr-defined]


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
