from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class CompressionConfig(BaseModel):
    level: str = "balanced"          # conservative | balanced | aggressive
    quality_threshold: float = 85.0  # fallback below this score
    history_window: int = 6          # keep last N turns verbatim
    rag_relevance_min: float = 0.15  # drop RAG chunks below this TF-IDF score


class ShadowTestingConfig(BaseModel):
    enabled: bool = False
    sample_rate: float = 0.05  # fraction of calls shadowed


class TelemetryConfig(BaseModel):
    enabled: bool = True
    endpoint: str = "https://api.contextpilot.org/v1/telemetry"
    api_key: Optional[str] = None
    flush_interval: int = 60   # seconds
    flush_size: int = 100      # events


class ContextPilotConfig(BaseModel):
    compression: CompressionConfig = Field(default_factory=CompressionConfig)
    shadow_testing: ShadowTestingConfig = Field(default_factory=ShadowTestingConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "ContextPilotConfig":
        """Load config from YAML file, then apply environment variable overrides."""
        if path is None:
            for candidate in ("contextpilot.yaml", "contextpilot.yml"):
                if Path(candidate).exists():
                    path = candidate
                    break

        data: dict = {}
        if path and Path(str(path)).exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}

        comp = data.setdefault("compression", {})
        if val := os.getenv("CONTEXTPILOT_QUALITY_THRESHOLD"):
            comp["quality_threshold"] = float(val)
        if val := os.getenv("CONTEXTPILOT_COMPRESSION_LEVEL"):
            comp["level"] = val
        if val := os.getenv("CONTEXTPILOT_HISTORY_WINDOW"):
            comp["history_window"] = int(val)

        tele = data.setdefault("telemetry", {})
        if val := os.getenv("CONTEXTPILOT_API_KEY"):
            tele["api_key"] = val
        if val := os.getenv("CONTEXTPILOT_TELEMETRY_ENDPOINT"):
            tele["endpoint"] = val

        return cls.model_validate(data)
