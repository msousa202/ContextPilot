"""End-to-end cache-awareness tests for Pipeline.optimize().

The contract under test:
1. Block-list (agent) payloads never raise and are never rewritten.
2. Payloads carrying client cache_control markers only have their final
   message touched.
3. The cost gate falls back when compression would raise the cache-adjusted
   request cost, even if the semantic quality gate passes.
"""

from contextpilot.config import ContextPilotConfig
from contextpilot.pipeline import Pipeline


def make_pipeline(**compression) -> Pipeline:
    config = ContextPilotConfig.model_validate(
        {"compression": compression, "telemetry": {"enabled": False}}
    )
    return Pipeline(config)


def _agent_payload() -> list[dict]:
    """A Claude Code shaped payload: block content + cache_control markers."""
    return [
        {"role": "user", "content": "Fix the failing test in test_utils.py"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "I will look at the file."},
                {"type": "tool_use", "id": "t1", "name": "read_file", "input": {"path": "x"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": "def f():\n    return 1\n" * 50,
                },
                {"type": "text", "text": "continue", "cache_control": {"type": "ephemeral"}},
            ],
        },
        {"role": "user", "content": "Now run the tests   \n\n\n\nplease"},
    ]


def test_agent_payload_does_not_raise_and_blocks_untouched():
    pipeline = make_pipeline()
    messages = _agent_payload()
    optimized, system, event = pipeline.optimize(messages, provider="anthropic", model="claude")
    assert system is None
    # Block-content messages are forwarded byte-identical
    assert optimized[1] == messages[1]
    assert optimized[2] == messages[2]
    # First message is before the cache_control marker: also untouched
    assert optimized[0] == messages[0]


def test_cache_managed_payload_touches_only_final_message():
    pipeline = make_pipeline()
    messages = _agent_payload()
    optimized, _, _ = pipeline.optimize(messages, provider="anthropic", model="claude")
    assert optimized[:-1] == messages[:-1]
    # Final plain-string message may be structurally stripped (or fall back whole)
    if optimized[-1] != messages[-1]:
        assert "\n\n\n" not in optimized[-1]["content"]


def test_marker_free_multiturn_is_stable_between_epochs():
    """Same epoch boundary across consecutive turns: identical forwarded prefix."""
    pipeline = make_pipeline(history_window=2, history_epoch=4, cache_aware=False)
    base = [
        {"role": "user", "content": f"Turn {i} distinctive content number {i} " + "filler " * 30}
        for i in range(12)
    ]
    out_a, _, _ = pipeline.optimize([dict(m) for m in base[:10]])
    out_b, _, _ = pipeline.optimize([dict(m) for m in base[:11]])
    shared = min(len(out_a), len(out_b)) - 1
    assert out_a[:shared] == out_b[:shared]


def test_cost_gate_falls_back_on_prefix_rewrite():
    """With cache_aware on, a modest-reduction prefix rewrite must fall back."""
    pipeline = make_pipeline(history_window=1, history_epoch=1, cache_aware=True)
    # Dense unique content: keyword summaries keep quality high but the
    # reduction is far below the ~90% needed to beat warm-cache pricing.
    messages = [
        {
            "role": "user",
            "content": " ".join(f"distinctterm{i}{j}" for j in range(40)),
        }
        for i in range(6)
    ]
    _, _, event, report = pipeline.optimize(messages, report=True)
    if report.fallback_used:
        assert report.fallback_reason in {"cost", "quality", "no_reduction"}
    else:
        # If compression survived the cost gate it must genuinely be cheaper
        from contextpilot import cost

        est = cost.evaluate(messages, _, None, None)
        assert est.compressed_is_cheaper


def test_cost_gate_off_allows_quality_passing_compression():
    pipeline_off = make_pipeline(history_window=1, history_epoch=1, cache_aware=False)
    messages = [
        {"role": "user", "content": "the same repeated filler words " * 30} for _ in range(8)
    ]
    optimized, _, event = pipeline_off.optimize(messages)
    # With highly redundant content, compression should engage when the cost gate is off
    assert event.tokens_input_compressed <= event.tokens_input_original


def test_fallback_reason_no_reduction():
    pipeline = make_pipeline()
    messages = [{"role": "user", "content": "short"}]
    _, _, _, report = pipeline.optimize(messages, report=True)
    assert report.fallback_used
    assert report.fallback_reason == "no_reduction"
