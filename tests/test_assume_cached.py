"""The cost gate's caching assumption must match how the payload is actually sent.

Two different workloads need two different cost models:

- A repeated conversation forwarded to a provider with prompt caching: the
  shared prefix already bills at ~0.1x, so rewriting it usually costs more
  than the tokens saved. `assume_cached=True` (the default for the proxy and
  wrapper surfaces) protects that cache.
- A one-shot request with no prefix to reuse: every token bills at full price,
  so fewer tokens is simply cheaper. `contextpilot.compress()` uses this.

Getting this backwards is user-visible in both directions: too cautious and a
first `compress()` call returns 0%, too eager and the pipeline quietly raises
a cached workload's bill.
"""

import contextpilot
from contextpilot import cost
from contextpilot.config import ContextPilotConfig
from contextpilot.pipeline import Pipeline


def _conversation(n: int = 16, words: int = 40) -> list[dict]:
    return [
        {"role": "user", "content": f"turn {i} topic{i} " + "filler detail content " * words}
        for i in range(n)
    ]


def _msg(text: str) -> dict:
    return {"role": "user", "content": text}


# --- cost model ---


def test_uncached_model_prices_raw_totals():
    orig = [_msg("w " * 200), _msg("x " * 200), _msg("q " * 20)]
    comp = [_msg("summary " * 100), _msg("q " * 20)]
    est = cost.evaluate(orig, comp, None, None, assume_cached=False)
    assert est.original_steady == 420  # 200 + 200 + 20 tokens, all at 1.0x
    assert est.compressed_steady == 120
    assert est.compressed_is_cheaper


def test_cached_model_rejects_what_uncached_accepts():
    """The same 50% reduction is a win one-shot and a loss on a warm cache."""
    orig = [_msg("w " * 200), _msg("x " * 200), _msg("q " * 20)]
    comp = [_msg("summary " * 200), _msg("q " * 20)]

    assert cost.evaluate(orig, comp, None, None, assume_cached=False).compressed_is_cheaper
    assert not cost.evaluate(orig, comp, None, None, assume_cached=True).compressed_is_cheaper


# --- surface defaults ---


def test_compress_is_one_shot_by_default():
    """A plain compress() call must not be blocked by a cache that isn't there."""
    result = contextpilot.compress(
        _conversation(), report=True, config={"telemetry": {"enabled": False}}
    )
    assert not result.report.fallback_used
    assert result.report.reduction_pct > 0


def test_compress_can_opt_into_cached_pricing():
    result = contextpilot.compress(
        _conversation(),
        report=True,
        config={"telemetry": {"enabled": False}},
        assume_cached=True,
    )
    assert result.report.fallback_used
    assert result.report.fallback_reason == "cost"


def test_pipeline_defaults_to_cached_pricing():
    """Proxy and wrapper surfaces go through Pipeline directly and must stay protected."""
    config = ContextPilotConfig.model_validate({"telemetry": {"enabled": False}})
    assert config.compression.assume_cached is True

    _, _, _, report = Pipeline(config).optimize(_conversation(), report=True)
    assert report.fallback_used
    assert report.fallback_reason == "cost"


def test_config_assume_cached_false_lets_compression_through():
    config = ContextPilotConfig.model_validate(
        {"compression": {"assume_cached": False}, "telemetry": {"enabled": False}}
    )
    _, _, _, report = Pipeline(config).optimize(_conversation(), report=True)
    assert not report.fallback_used
    assert report.reduction_pct > 0


def test_cost_fallback_message_is_actionable():
    from contextpilot.report import render_report

    config = ContextPilotConfig.model_validate({"telemetry": {"enabled": False}})
    _, _, _, report = Pipeline(config).optimize(_conversation(), report=True)
    rendered = render_report(report)
    # The user must be told why, and what to change if their workload isn't cached
    assert "cache-adjusted cost" in rendered
    assert "assume_cached" in rendered
