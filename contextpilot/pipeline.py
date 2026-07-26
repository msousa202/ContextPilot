from __future__ import annotations

import time
from typing import Literal, overload

from contextpilot import cost as cost_model
from contextpilot._utils import rate_for_model, word_count_messages
from contextpilot.analyzer import Analyzer
from contextpilot.compressor import Compressor
from contextpilot.config import ContextPilotConfig
from contextpilot.quality import QualityGate
from contextpilot.report import BlockDecision, CompressionReport
from contextpilot.shadow import ShadowTester
from contextpilot.telemetry import TelemetryCollector, TelemetryEvent


class Pipeline:
    """Central orchestrator: analyze → compress → quality gate → cost gate → telemetry.

    Shared by all four integration surfaces. Surface adapters call
    `pipeline.optimize()` and receive the ready-to-forward payload.

    Two independent gates can trigger the fail-safe fallback (FR-004):
    - quality gate: predicted semantic preservation below threshold
    - cost gate: compression would raise the cache-adjusted request cost
      (rewriting cached prefix bytes bills at ~10x a cache read, see cost.py)
    """

    def __init__(self, config: ContextPilotConfig) -> None:
        self.config = config
        self.analyzer = Analyzer(config)
        self.compressor = Compressor(config)
        self.quality = QualityGate(config)
        self.telemetry = TelemetryCollector(config)
        self.shadow = ShadowTester(config)

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

        The caller always receives a valid payload: if either gate fails,
        the original is returned (fail-safe, FR-004).

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

        # If compression increased token count, skip it, no benefit
        if comp_tokens >= orig_tokens:
            return self._fallback_result(
                messages,
                system,
                provider,
                model,
                t0,
                compression_ms,
                orig_tokens,
                quality_score=100.0,
                reason="no_reduction",
                report=report,
            )

        passes, quality_score = self.quality.passes(
            messages, compressed_msgs, system, compressed_sys
        )
        if not passes:
            return self._fallback_result(
                messages,
                system,
                provider,
                model,
                t0,
                compression_ms,
                orig_tokens,
                quality_score=quality_score,
                reason="quality",
                report=report,
            )

        # Cost gate: token reduction is not the billable unit; cache-adjusted
        # cost is. Refuse compression that makes the real request dearer.
        estimate = cost_model.evaluate(
            messages,
            compressed_msgs,
            system,
            compressed_sys,
            epoch=self.config.compression.history_epoch,
            assume_cached=self.config.compression.assume_cached,
        )
        if self.config.compression.cache_aware and not estimate.compressed_is_cheaper:
            return self._fallback_result(
                messages,
                system,
                provider,
                model,
                t0,
                compression_ms,
                orig_tokens,
                quality_score=quality_score,
                reason="cost",
                report=report,
            )

        latency_ms = (time.perf_counter() - t0) * 1000
        rate = rate_for_model(model) / 1_000_000

        # decisions/report content intentionally excluded from TelemetryEvent, FR-006
        event = TelemetryEvent(
            provider=provider,
            model=model,
            tokens_input_original=orig_tokens,
            tokens_input_compressed=comp_tokens,
            latency_ms=round(latency_ms, 2),
            compression_ms=round(compression_ms, 2),
            quality_score=quality_score,
            fallback_triggered=False,
            cost_original_usd=round(estimate.original_steady * rate, 8),
            cost_compressed_usd=round(estimate.compressed_steady * rate, 8),
        )
        self.telemetry.record(event)

        if report:
            reduction_pct = round((1 - comp_tokens / orig_tokens) * 100, 2) if orig_tokens else 0.0
            rpt = CompressionReport(
                original_tokens=orig_tokens,
                compressed_tokens=comp_tokens,
                reduction_pct=reduction_pct,
                blocks=decisions or [],
                quality_score=quality_score,
                fallback_used=False,
            )
            return compressed_msgs, compressed_sys, event, rpt
        return compressed_msgs, compressed_sys, event

    def _fallback_result(
        self,
        messages: list[dict],
        system: str | None,
        provider: str,
        model: str,
        t0: float,
        compression_ms: float,
        orig_tokens: int,
        *,
        quality_score: float,
        reason: str,
        report: bool,
    ) -> (
        tuple[list[dict], str | None, TelemetryEvent]
        | tuple[list[dict], str | None, TelemetryEvent, CompressionReport]
    ):
        # decisions/report content intentionally excluded from TelemetryEvent, FR-006
        event = TelemetryEvent(
            provider=provider,
            model=model,
            tokens_input_original=orig_tokens,
            tokens_input_compressed=orig_tokens,
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
            compression_ms=round(compression_ms, 2),
            quality_score=quality_score,
            fallback_triggered=True,
        )
        self.telemetry.record(event)
        if report:
            rpt = CompressionReport(
                original_tokens=orig_tokens,
                compressed_tokens=orig_tokens,
                reduction_pct=0.0,
                blocks=[],
                quality_score=quality_score,
                fallback_used=True,
                fallback_reason=reason,
            )
            return messages, system, event, rpt
        return messages, system, event
