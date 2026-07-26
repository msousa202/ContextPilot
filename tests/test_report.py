from contextpilot.api import compress as compress_fn
from contextpilot.config import ContextPilotConfig
from contextpilot.pipeline import Pipeline
from contextpilot.report import CompressionReport, render_report


def cfg(**kwargs) -> ContextPilotConfig:
    base: dict = {"telemetry": {"enabled": True, "api_key": None}}
    if kwargs:
        base["compression"] = kwargs
    return ContextPilotConfig.model_validate(base)


_LONG_TURN = (
    "This is a detailed explanation covering multiple aspects of the topic. "
    "The analysis includes technical context, domain knowledge, examples from practice, "
    "and conclusions that build on previous turns in the conversation. "
) * 2


def _long_conversation() -> list[dict]:
    return [{"role": "user", "content": f"Question {i}: {_LONG_TURN}"} for i in range(10)] + [
        {"role": "assistant", "content": f"Answer: {_LONG_TURN}"}
    ]


def test_report_false_returns_3tuple():
    pipeline = Pipeline(cfg())
    result = pipeline.optimize([{"role": "user", "content": "Hello"}])
    assert len(result) == 3


def test_report_true_returns_4tuple_with_report():
    pipeline = Pipeline(cfg())
    result = pipeline.optimize([{"role": "user", "content": "Hello"}], report=True)
    assert len(result) == 4
    assert isinstance(result[3], CompressionReport)


def test_report_blocks_populated_for_summarized_history():
    pipeline = Pipeline(cfg(history_window=3, quality_threshold=0))
    _, _, _, rpt = pipeline.optimize(_long_conversation(), report=True)
    assert any(b.strategy_applied == "history" for b in rpt.blocks)


def test_report_fallback_used_true_when_quality_gate_trips():
    pipeline = Pipeline(cfg(quality_threshold=99.9, history_window=1))
    messages = [
        {"role": "user", "content": "alpha beta gamma delta epsilon zeta"},
        {"role": "user", "content": "omega psi chi phi upsilon tau sigma"},
        {"role": "user", "content": "final question"},
    ]
    _, _, event, rpt = pipeline.optimize(messages, report=True)
    if event.fallback_triggered:
        assert rpt.fallback_used is True
        assert rpt.blocks == []


def test_report_reduction_pct_matches_token_counts():
    pipeline = Pipeline(cfg(history_window=3, quality_threshold=0))
    _, _, event, rpt = pipeline.optimize(_long_conversation(), report=True)
    assert rpt.original_tokens == event.tokens_input_original
    assert rpt.compressed_tokens == event.tokens_input_compressed
    assert rpt.compressed_tokens <= rpt.original_tokens


def test_report_never_leaks_into_telemetry():
    pipeline = Pipeline(cfg(history_window=3, quality_threshold=0))
    pipeline.optimize(_long_conversation(), report=True)
    events = pipeline.telemetry.drain()
    assert len(events) == 1
    event_dict = events[0].to_dict()
    assert "report" not in event_dict
    assert "blocks" not in event_dict
    assert "decisions" not in event_dict


def test_top_level_compress_function_with_report():
    result = compress_fn(
        _long_conversation(), config=cfg(history_window=3, quality_threshold=0), report=True
    )
    assert result.report is not None
    assert isinstance(result.payload["messages"], list)


def test_top_level_compress_function_without_report():
    result = compress_fn([{"role": "user", "content": "Hello"}], config=cfg())
    assert result.report is None


def test_render_report_human_readable():
    pipeline = Pipeline(cfg(history_window=3, quality_threshold=0))
    _, _, _, rpt = pipeline.optimize(_long_conversation(), report=True)
    text = render_report(rpt)
    assert "Compression Report" in text
    assert "Quality score" in text


def test_render_report_fallback_message():
    rpt = CompressionReport(
        original_tokens=10, compressed_tokens=10, reduction_pct=0.0, fallback_used=True
    )
    text = render_report(rpt)
    assert "Fallback" in text
    assert "Original payload sent unchanged" in text


def test_render_report_fallback_reasons_are_distinct_and_explained():
    """Each fallback reason must tell the user something different and actionable."""
    rendered = {
        reason: render_report(
            CompressionReport(
                original_tokens=10,
                compressed_tokens=10,
                reduction_pct=0.0,
                fallback_used=True,
                fallback_reason=reason,
            )
        )
        for reason in ("quality", "cost", "no_reduction")
    }
    assert "quality_threshold" in rendered["quality"]
    assert "assume_cached" in rendered["cost"]
    assert "too short" in rendered["no_reduction"]
    assert len(set(rendered.values())) == 3  # no two reasons render identically
