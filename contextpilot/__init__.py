from __future__ import annotations

from typing import Any

from contextpilot.api import CompressionResult, compress
from contextpilot.config import ContextPilotConfig
from contextpilot.pipeline import Pipeline
from contextpilot.report import BlockDecision, CompressionReport


def wrap(client: Any, config: ContextPilotConfig | dict | None = None) -> Any:
    """Wrap an OpenAI or Anthropic client with ContextPilot compression.

    Usage:
        from openai import OpenAI
        import contextpilot
        pilot = contextpilot.wrap(OpenAI())
        response = pilot.chat.completions.create(model="gpt-4o", messages=messages)
    """
    if isinstance(config, dict):
        cfg = ContextPilotConfig.model_validate(config)
    elif config is None:
        cfg = ContextPilotConfig.load()
    else:
        cfg = config

    pipeline = Pipeline(cfg)

    module = type(client).__module__
    name = type(client).__name__

    if "openai" in module.lower() or name in ("OpenAI", "AsyncOpenAI"):
        from contextpilot.adapters.openai_adapter import OpenAIWrapper

        return OpenAIWrapper(client, pipeline)

    if "anthropic" in module.lower() or name in ("Anthropic", "AsyncAnthropic"):
        from contextpilot.adapters.anthropic_adapter import AnthropicWrapper

        return AnthropicWrapper(client, pipeline)

    raise ValueError(
        f"Unsupported client type '{name}'. Supported: openai.OpenAI, anthropic.Anthropic"
    )


__all__ = [
    "wrap",
    "ContextPilotConfig",
    "compress",
    "CompressionResult",
    "CompressionReport",
    "BlockDecision",
]
