from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_ALLOWED_INTENTS = {"debug", "build", "explore", "refactor", "unknown"}
_ALLOWED_LEVELS = {"conservative", "balanced", "aggressive"}

# `level` is a preset over the two knobs that actually change how much is
# dropped. Both are cache-safe: they move the epoch-quantized history boundary
# and the RAG relevance floor, never introducing query-dependence. A field the
# user set explicitly always wins over its preset value.
_LEVEL_PRESETS: dict[str, dict[str, float | int]] = {
    "conservative": {"history_window": 10, "rag_relevance_min": 0.05},
    "balanced": {"history_window": 6, "rag_relevance_min": 0.15},
    "aggressive": {"history_window": 3, "rag_relevance_min": 0.30},
}


class CompressionConfig(BaseModel):
    # validate_assignment so `cfg.compression.level = "aggressive"` after load()
    # re-applies the preset and rejects invalid values, rather than silently
    # setting a field nothing reads.
    model_config = ConfigDict(validate_assignment=True)

    level: str = "balanced"  # conservative | balanced | aggressive
    quality_threshold: float = 72.0  # fallback below this score (TF-IDF weighted recall metric)
    history_window: int = 6  # keep last N turns verbatim (preset by `level`)
    history_epoch: int = 8  # summarization boundary advances in steps of N turns (cache stability)
    rag_relevance_min: float = 0.15  # drop RAG chunks below this TF-IDF score (preset by `level`)
    intent_override: str | None = None  # debug|build|explore|refactor|unknown, None = auto-detect
    intent_detection_window: int = 4  # how many recent turns the intent heuristic examines
    cache_aware: bool = True  # refuse compression that raises cache-adjusted request cost
    assume_cached: bool = True  # price payloads as a cached conversation, not a one-shot request
    inject_cache_control: bool = True  # proxy: add cache breakpoint to big stable system prompts

    @field_validator("intent_override")
    @classmethod
    def _validate_intent_override(cls, v: str | None) -> str | None:
        if v is not None and v not in _ALLOWED_INTENTS:
            raise ValueError(
                f"intent_override must be one of {sorted(_ALLOWED_INTENTS)} or null, got {v!r}"
            )
        return v

    @field_validator("level")
    @classmethod
    def _validate_level(cls, v: str) -> str:
        if v not in _ALLOWED_LEVELS:
            raise ValueError(f"level must be one of {sorted(_ALLOWED_LEVELS)}, got {v!r}")
        return v

    @model_validator(mode="after")
    def _apply_level_preset(self) -> "CompressionConfig":
        """Apply the `level` preset to any knob the caller did not set explicitly."""
        for field, value in _LEVEL_PRESETS[self.level].items():
            if field not in self.model_fields_set:
                object.__setattr__(self, field, value)
        return self


class ShadowTestingConfig(BaseModel):
    enabled: bool = False
    sample_rate: float = 0.05  # fraction of calls shadowed


class TelemetryConfig(BaseModel):
    enabled: bool = True
    endpoint: str = "https://api.contextpilot.org/v1/telemetry"
    api_key: str | None = None
    flush_size: int = 100


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
        if val := os.getenv("CONTEXTPILOT_INTENT"):
            comp["intent_override"] = val

        tele = data.setdefault("telemetry", {})
        if val := os.getenv("CONTEXTPILOT_API_KEY"):
            tele["api_key"] = val
        if val := os.getenv("CONTEXTPILOT_TELEMETRY_ENDPOINT"):
            tele["endpoint"] = val

        return cls.model_validate(data)
