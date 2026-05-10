from __future__ import annotations

import time

from contextpilot._utils import word_count_messages
from contextpilot.analyzer import Analyzer
from contextpilot.compressor import Compressor
from contextpilot.config import ContextPilotConfig
from contextpilot.quality import QualityGate
from contextpilot.telemetry import TelemetryCollector, TelemetryEvent


class Pipeline:
    """Central orchestrator: analyze → compress → quality gate → telemetry.

    Shared by all four integration surfaces. Surface adapters call
    `pipeline.optimize()` and receive the ready-to-forward payload.
    """

    def __init__(self, config: ContextPilotConfig) -> None:
        self.config = config
        self.analyzer = Analyzer(config)
        self.compressor = Compressor(config)
        self.quality = QualityGate(config)
        self.telemetry = TelemetryCollector(config)

    def optimize(
        self,
        messages: list[dict],
        system: str | None = None,
        provider: str = "unknown",
        model: str = "unknown",
    ) -> tuple[list[dict], str | None, TelemetryEvent]:
        """Run the optimization pipeline and return (messages, system, event).

        The caller always receives a valid payload — if quality falls below
        the threshold, the original is returned (fail-safe, FR-004).
        """
        t0 = time.perf_counter()

        blocks = self.analyzer.analyze(messages, system)
        compressed_msgs, compressed_sys = self.compressor.compress(messages, blocks, system)

        compression_ms = (time.perf_counter() - t0) * 1000

        orig_tokens = word_count_messages(messages)
        comp_tokens = word_count_messages(compressed_msgs)

        # If compression increased token count, skip it — no benefit
        if comp_tokens >= orig_tokens:
            event = TelemetryEvent(
                provider=provider,
                model=model,
                tokens_input_original=orig_tokens,
                tokens_input_compressed=orig_tokens,
                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                compression_ms=round(compression_ms, 2),
                quality_score=100.0,
                fallback_triggered=True,
            )
            self.telemetry.record(event)
            return messages, system, event

        passes, quality_score = self.quality.passes(
            messages, compressed_msgs, system, compressed_sys
        )

        fallback = not passes
        result_msgs = messages if fallback else compressed_msgs
        result_sys = system if fallback else compressed_sys

        latency_ms = (time.perf_counter() - t0) * 1000

        event = TelemetryEvent(
            provider=provider,
            model=model,
            tokens_input_original=word_count_messages(messages),
            tokens_input_compressed=word_count_messages(result_msgs),
            latency_ms=round(latency_ms, 2),
            compression_ms=round(compression_ms, 2),
            quality_score=quality_score,
            fallback_triggered=fallback,
        )
        self.telemetry.record(event)

        return result_msgs, result_sys, event
