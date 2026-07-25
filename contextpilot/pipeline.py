from __future__ import annotations

import time
from typing import Literal, overload

from contextpilot._utils import word_count_messages
from contextpilot.analyzer import Analyzer
from contextpilot.compressor import Compressor
from contextpilot.config import ContextPilotConfig
from contextpilot.quality import QualityGate
from contextpilot.report import BlockDecision, CompressionReport
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

    @overload
    def optimize(
        self,
        messages: list[dict],
        system: str | None = None,
        provider: str = "unknown",
        model: str = "unknown",
        report: Literal[False] = False,
    ) -> tuple[list[dict], str | None, TelemetryEvent]: ...

    @overload
    def optimize(
        self,
        messages: list[dict],
        system: str | None = None,
        provider: str = "unknown",
        model: str = "unknown",
        *,
        report: Literal[True],
    ) -> tuple[list[dict], str | None, TelemetryEvent, CompressionReport]: ...

    def optimize(
        self,
        messages: list[dict],
        system: str | None = None,
        provider: str = "unknown",
        model: str = "unknown",
        report: bool = False,
    ) -> (
        tuple[list[dict], str | None, TelemetryEvent]
        | tuple[list[dict], str | None, TelemetryEvent, CompressionReport]
    ):
        """Run the optimization pipeline and return (messages, system, event).

        The caller always receives a valid payload — if quality falls below
        the threshold, the original is returned (fail-safe, FR-004).

        When `report=True`, returns a 4th element: a `CompressionReport`
        describing what each strategy did. Decision content is derived
        purely for the return value and is never passed to telemetry (FR-006).
        """
        t0 = time.perf_counter()

        decisions: list[BlockDecision] | None = [] if report else None
        blocks = self.analyzer.analyze(messages, system)
        compressed_msgs, compressed_sys = self.compressor.compress(
            messages, blocks, system, decisions=decisions
        )

        compression_ms = (time.perf_counter() - t0) * 1000

        orig_tokens = word_count_messages(messages)
        comp_tokens = word_count_messages(compressed_msgs)

        # If compression increased token count, skip it — no benefit
        if comp_tokens >= orig_tokens:
            # decisions/report content intentionally excluded from TelemetryEvent — FR-006
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
            if report:
                rpt = CompressionReport(
                    original_tokens=orig_tokens,
                    compressed_tokens=orig_tokens,
                    reduction_pct=0.0,
                    blocks=[],
                    quality_score=100.0,
                    fallback_used=True,
                )
                return messages, system, event, rpt
            return messages, system, event

        passes, quality_score = self.quality.passes(
            messages, compressed_msgs, system, compressed_sys
        )

        fallback = not passes
        result_msgs = messages if fallback else compressed_msgs
        result_sys = system if fallback else compressed_sys

        latency_ms = (time.perf_counter() - t0) * 1000

        # decisions/report content intentionally excluded from TelemetryEvent — FR-006
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

        if report:
            result_tokens = word_count_messages(result_msgs)
            reduction_pct = (
                round((1 - result_tokens / orig_tokens) * 100, 2) if orig_tokens else 0.0
            )
            rpt = CompressionReport(
                original_tokens=orig_tokens,
                compressed_tokens=result_tokens,
                reduction_pct=reduction_pct,
                blocks=[] if fallback else (decisions or []),
                quality_score=quality_score,
                fallback_used=fallback,
            )
            return result_msgs, result_sys, event, rpt
        return result_msgs, result_sys, event
