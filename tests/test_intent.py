import pytest
from pydantic import ValidationError

from contextpilot.analyzer import Analyzer, Intent, detect_intent
from contextpilot.config import ContextPilotConfig


def cfg(**kwargs) -> ContextPilotConfig:
    return ContextPilotConfig.model_validate({"compression": kwargs} if kwargs else {})


def _msgs(*contents: str, role: str = "user") -> list[dict]:
    return [{"role": role, "content": c} for c in contents]


def test_detect_intent_empty_messages_is_unknown():
    assert detect_intent([]) == Intent.UNKNOWN
    assert detect_intent([{"role": "user", "content": ""}]) == Intent.UNKNOWN


def test_detect_intent_debug_traceback():
    messages = _msgs(
        'Traceback (most recent call last):\n  File "app.py", line 10, in <module>\n'
        "TypeError: unsupported operand type(s) for +: 'int' and 'str'"
    )
    assert detect_intent(messages) == Intent.DEBUG


def test_detect_intent_refactor_diff_hunk():
    messages = _msgs("@@ -1,3 +1,3 @@\n-old code\n+new code\n-old code\n+new code")
    assert detect_intent(messages) == Intent.REFACTOR


def test_detect_intent_refactor_keyword():
    messages = _msgs("Please refactor this function and clean up the dead code.")
    assert detect_intent(messages) == Intent.REFACTOR


def test_detect_intent_explore_questions():
    messages = _msgs(
        "What is a decorator?",
        "How does asyncio work?",
        "Can you explain closures?",
    )
    assert detect_intent(messages) == Intent.EXPLORE


def test_detect_intent_build_default():
    messages = _msgs(
        "Please add a dark mode toggle to the settings page and make sure it persists."
    )
    assert detect_intent(messages) == Intent.BUILD


def test_detect_intent_respects_window():
    debug_turn = {
        "role": "user",
        "content": 'Traceback (most recent call last):\n  File "app.py", line 1\nTypeError: boom',
    }
    neutral_turns = _msgs(
        "Add a dark mode toggle.",
        "Also update the settings page copy.",
    )
    messages = [debug_turn] + neutral_turns
    # window=2 examines only the neutral tail, the debug signal is out of range
    assert detect_intent(messages, window=2) != Intent.DEBUG


def test_intent_override_config():
    messages = _msgs("What is a decorator? How does it work? Can you explain?")
    a = Analyzer(cfg(intent_override="debug"))
    blocks = a.analyze(messages)
    assert blocks[0].intent == Intent.DEBUG


def test_intent_override_invalid_raises():
    with pytest.raises(ValidationError):
        cfg(intent_override="bogus")


def test_analyzer_auto_detects_when_no_override():
    messages = _msgs("Please refactor this function and clean up the dead code.")
    a = Analyzer(cfg())
    blocks = a.analyze(messages)
    assert blocks[0].intent == Intent.REFACTOR
