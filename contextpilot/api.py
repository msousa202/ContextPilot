"""Top-level convenience API: contextpilot.compress(messages, report=True)."""

from __future__ import annotations

from dataclasses import dataclass

from contextpilot.config import ContextPilotConfig
from contextpilot.pipeline import Pipeline
from contextpilot.report import CompressionReport


@dataclass
class CompressionResult:
    payload: dict  # {"messages": list[dict], "system": str | None}
    report: CompressionReport | None = None


def compress(
    messages: list[dict],
    system: str | None = None,
    config: ContextPilotConfig | dict | None = None,
    report: bool = False,
    provider: str = "library",
    model: str = "unknown",
    assume_cached: bool | None = None,
) -> CompressionResult:
    """Compress a single messages payload once.

    Usage:
        result = contextpilot.compress(messages, report=True)
        result.payload   # {"messages": [...], "system": ...}
        result.report    # CompressionReport | None

    This is a one-shot call, so by default it prices compression as a request
    with no prefix cache to preserve: fewer tokens is simply cheaper. That is
    the opposite default to the proxy and wrapper surfaces, which serve
    repeated conversations where provider caching is already billing the
    shared prefix at ~0.1x and rewriting it would cost more than it saves.

    Pass `assume_cached=True` if you are calling this repeatedly over a
    growing conversation and forwarding the result to a provider with prompt
    caching enabled; the cost gate will then protect that cache.
    """
    cfg = (
        ContextPilotConfig.model_validate(config)
        if isinstance(config, dict)
        else config or ContextPilotConfig.load()
    )
    # One-shot semantics unless the caller explicitly opts into cached pricing.
    cfg.compression.assume_cached = assume_cached if assume_cached is not None else False
    pipeline = Pipeline(cfg)

    if report:
        msgs, sys_, _event, rpt = pipeline.optimize(
            messages, system=system, provider=provider, model=model, report=True
        )
        return CompressionResult(payload={"messages": msgs, "system": sys_}, report=rpt)

    msgs, sys_, _event = pipeline.optimize(messages, system=system, provider=provider, model=model)
    return CompressionResult(payload={"messages": msgs, "system": sys_}, report=None)
