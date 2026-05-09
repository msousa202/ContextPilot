from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from contextpilot.config import ContextPilotConfig

_LOCAL_DIR = Path.home() / ".contextpilot"
_LOCAL_LOG = _LOCAL_DIR / "events.jsonl"


@dataclass
class TelemetryEvent:
    """FR-006: Metadata-only telemetry event.

    Contains ONLY numerical metadata — never prompt/response content or PII.
    Schema matches technical doc §7.
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    provider: str = "unknown"
    model: str = "unknown"
    tokens_input_original: int = 0
    tokens_input_compressed: int = 0
    tokens_output: int = 0
    latency_ms: float = 0.0
    compression_ms: float = 0.0
    quality_score: float = 100.0
    strategies_applied: list[str] = field(default_factory=list)
    fallback_triggered: bool = False
    shadow_similarity: Optional[float] = None
    cost_original_usd: float = 0.0
    cost_compressed_usd: float = 0.0

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "provider": self.provider,
            "model": self.model,
            "tokens_input_original": self.tokens_input_original,
            "tokens_input_compressed": self.tokens_input_compressed,
            "tokens_output": self.tokens_output,
            "latency_ms": self.latency_ms,
            "compression_ms": self.compression_ms,
            "quality_score": self.quality_score,
            "strategies_applied": self.strategies_applied,
            "fallback_triggered": self.fallback_triggered,
            "shadow_similarity": self.shadow_similarity,
            "cost_original_usd": self.cost_original_usd,
            "cost_compressed_usd": self.cost_compressed_usd,
        }


class TelemetryCollector:
    """FR-006: Non-blocking metadata collection and transport.

    Buffers events locally and flushes to the dashboard API endpoint in
    batches. If the endpoint is unreachable, events are silently dropped —
    telemetry failures must never affect library operation.
    """

    def __init__(self, config: ContextPilotConfig) -> None:
        self.config = config
        self._buffer: list[TelemetryEvent] = []

    def record(self, event: TelemetryEvent) -> None:
        if not self.config.telemetry.enabled:
            return
        self._write_local(event)
        self._buffer.append(event)
        if len(self._buffer) >= self.config.telemetry.flush_size:
            self._flush()

    @staticmethod
    def _write_local(event: TelemetryEvent) -> None:
        try:
            _LOCAL_DIR.mkdir(parents=True, exist_ok=True)
            with _LOCAL_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        except Exception:
            pass  # silent drop — never affect library operation

    def _flush(self) -> None:
        if not self._buffer or not self.config.telemetry.api_key:
            self._buffer.clear()
            return
        events = [e.to_dict() for e in self._buffer]
        self._buffer.clear()
        try:
            with httpx.Client(timeout=5.0) as client:
                client.post(
                    self.config.telemetry.endpoint,
                    json={"events": events},
                    headers={"Authorization": f"Bearer {self.config.telemetry.api_key}"},
                )
        except Exception:
            pass  # silent drop — library keeps working

    def drain(self) -> list[TelemetryEvent]:
        """Return and clear the buffer (for testing)."""
        events = list(self._buffer)
        self._buffer.clear()
        return events
