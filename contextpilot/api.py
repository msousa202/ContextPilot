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
) -> CompressionResult:
    """Compress a single messages payload once.

    Usage:
        result = contextpilot.compress(messages, report=True)
        result.payload   # {"messages": [...], "system": ...}
        result.report    # CompressionReport | None
    """
    cfg = (
        ContextPilotConfig.model_validate(config)
        if isinstance(config, dict)
        else config or ContextPilotConfig.load()
    )
    pipeline = Pipeline(cfg)

    if report:
        msgs, sys_, _event, rpt = pipeline.optimize(
            messages, system=system, provider=provider, model=model, report=True
        )
        return CompressionResult(payload={"messages": msgs, "system": sys_}, report=rpt)

    msgs, sys_, _event = pipeline.optimize(messages, system=system, provider=provider, model=model)
    return CompressionResult(payload={"messages": msgs, "system": sys_}, report=None)
