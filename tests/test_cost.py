"""Cache-economics cost model tests (cost.py) and content utilities (content.py)."""

from contextpilot import cost
from contextpilot.content import (
    message_has_cache_control,
    message_text,
    mutable_indices,
    payload_is_cache_managed,
)


def _msg(text: str, role: str = "user") -> dict:
    return {"role": role, "content": text}


# --- content.py ---


def test_message_text_plain_string():
    assert message_text(_msg("hello world")) == "hello world"


def test_message_text_block_list():
    msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": "part one"},
            {"type": "tool_use", "id": "t1", "name": "search", "input": {"q": "x"}},
            {"type": "tool_result", "tool_use_id": "t1", "content": "part two"},
            {
                "type": "tool_result",
                "tool_use_id": "t2",
                "content": [{"type": "text", "text": "part three"}],
            },
        ],
    }
    text = message_text(msg)
    assert "part one" in text
    assert "part two" in text
    assert "part three" in text


def test_message_text_none_content():
    assert message_text({"role": "user"}) == ""
    assert message_text({"role": "user", "content": None}) == ""


def test_cache_control_detection():
    marked = {
        "role": "user",
        "content": [{"type": "text", "text": "hi", "cache_control": {"type": "ephemeral"}}],
    }
    plain = _msg("hi")
    assert message_has_cache_control(marked)
    assert not message_has_cache_control(plain)
    assert payload_is_cache_managed([plain, marked])
    assert not payload_is_cache_managed([plain])


def test_payload_cache_managed_via_system_blocks():
    system = [{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}]
    assert payload_is_cache_managed([_msg("hi")], system)


def test_mutable_indices():
    msgs = [
        _msg("plain"),
        {"role": "user", "content": [{"type": "text", "text": "blocks"}]},
        _msg("plain again"),
    ]
    assert mutable_indices(msgs) == {0, 2}


# --- cost.py ---


def test_steady_state_cost_prices_prefix_at_cache_read():
    msgs = [_msg("a " * 100), _msg("b " * 10)]
    # 100 tokens at 0.1x + 10 tokens at 1.0x
    assert cost.steady_state_cost(msgs, None) == 100 * 0.1 + 10


def test_common_prefix_zero_when_system_differs():
    msgs = [_msg("a b c")]
    assert cost.common_prefix_tokens(msgs, msgs, "sys one", "sys two") == 0


def test_common_prefix_stops_at_first_difference():
    orig = [_msg("one two"), _msg("three four"), _msg("five")]
    comp = [_msg("one two"), _msg("REWRITTEN"), _msg("five")]
    assert cost.common_prefix_tokens(orig, comp, None, None) == 2


def test_evaluate_rejects_prefix_rewrite_with_modest_reduction():
    """Rewriting the cached prefix for a 50% token cut must price as more expensive."""
    orig = [_msg("w " * 200), _msg("x " * 200), _msg("q " * 20)]
    comp = [_msg("summary " * 200), _msg("q " * 20)]  # 50% cut, prefix rewritten
    est = cost.evaluate(orig, comp, None, None)
    assert not est.compressed_is_cheaper


def test_evaluate_accepts_aggressive_prefix_reduction():
    """Removing ~95% of the prefix beats the 10x cache-read handicap."""
    orig = [_msg("w " * 500), _msg("x " * 500), _msg("q " * 20)]
    comp = [_msg("summary " * 40), _msg("q " * 20)]  # 96% cut
    est = cost.evaluate(orig, comp, None, None)
    assert est.compressed_is_cheaper


def test_evaluate_identity_is_equal_cost():
    msgs = [_msg("a " * 50), _msg("b " * 5)]
    est = cost.evaluate(msgs, msgs, "sys", "sys")
    assert est.original_steady == est.compressed_steady
    assert est.compressed_is_cheaper  # amortized identity never exceeds steady state


def test_amortized_accounts_for_epoch_rebuilds():
    """A rewrite that wins in steady state can still lose once per-epoch rebuilds are priced."""
    orig = [_msg("w " * 200), _msg("x " * 200), _msg("q " * 20)]
    comp = [_msg("summary " * 200), _msg("q " * 20)]
    est = cost.evaluate(orig, comp, None, None, epoch=8)
    assert est.compressed_steady < est.original_steady  # steady state alone looks like a win
    assert est.compressed_amortized > est.original_steady  # honest per-turn figure is a loss
