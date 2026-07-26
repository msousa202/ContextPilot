"""FR-014: Per-call CompressionReport for structured visibility into pipeline decisions.

Standalone module (no imports from compressor.py/pipeline.py) so the CLI and
MCP server can use it without pulling in the whole pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SYSTEM_BLOCK_ID = -1  # sentinel: decision applies to the system prompt, not a message
SUMMARY_BLOCK_ID = -2  # sentinel: decision applies to a synthetic post-collapse block


@dataclass
class BlockDecision:
    block_id: int
    strategy_applied: str  # "history" | "rag_pruner" | "structural" | "dedup"
    action: str  # "kept" | "skeletonized" | "summarized" | "dropped"
    reason: str
    tokens_saved: int = 0


@dataclass
class CompressionReport:
    original_tokens: int
    compressed_tokens: int
    reduction_pct: float
    blocks: list[BlockDecision] = field(default_factory=list)
    quality_score: float = 100.0
    fallback_used: bool = False
    fallback_reason: str = ""  # "" | "no_reduction" | "quality" | "cost"

    def to_dict(self) -> dict:
        return {
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
            "reduction_pct": self.reduction_pct,
            "quality_score": self.quality_score,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "blocks": [
                {
                    "block_id": b.block_id,
                    "strategy_applied": b.strategy_applied,
                    "action": b.action,
                    "reason": b.reason,
                    "tokens_saved": b.tokens_saved,
                }
                for b in self.blocks
            ],
        }


def render_report(report: CompressionReport) -> str:
    """Human-readable rendering shared by CLI `--report` and the MCP report resource."""
    lines = [
        "ContextPilot · Compression Report",
        "==================================",
        f"  {report.original_tokens:,} -> {report.compressed_tokens:,} tokens "
        f"({report.reduction_pct:.1f}% reduction)",
        f"  Quality score : {report.quality_score:.1f} / 100",
        f"  Fallback used : {report.fallback_used}",
        "",
    ]
    if report.fallback_used:
        detail = {
            "quality": (
                "quality gate rejected compression (predicted score below threshold).\n"
                "  Lower compression.quality_threshold to accept more aggressive compression."
            ),
            "cost": (
                "cost gate rejected compression: it would raise the cache-adjusted cost.\n"
                "  Provider prompt caching already bills the repeated prefix at ~0.1x, so\n"
                "  rewriting it costs more than the tokens saved. If your workload has no\n"
                "  prompt caching (one-shot calls, prefixes that never repeat), set\n"
                "  compression.assume_cached: false to price it as a one-shot request."
            ),
            "no_reduction": (
                "compression produced no token reduction (payload too short or already tight)."
            ),
        }.get(report.fallback_reason, "compression rejected")
        lines.append(f"  Fallback: {detail}")
        lines.append("  Original payload sent unchanged, no per-block changes.")
    elif not report.blocks:
        lines.append("  No blocks were modified.")
    else:
        for b in report.blocks:
            label = "system" if b.block_id == SYSTEM_BLOCK_ID else f"block {b.block_id}"
            lines.append(
                f"  [{label}] {b.strategy_applied}: {b.action}, {b.reason} (-{b.tokens_saved}t)"
            )
    return "\n".join(lines)
