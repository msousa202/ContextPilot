"""FR-008: Agent memory middleware tests."""
from contextpilot.middleware import AgentMemory


def test_basic_compression():
    memory = AgentMemory(compression_level="balanced")
    output = (
        "Thought: I need to analyze this.\n"
        "Action: search\n"
        "Observation: Found results.\n"
        "Final Answer: The result is 42."
    )
    compressed = memory.compress_handoff(output)
    assert len(compressed) < len(output)


def test_preserve_keys_kept():
    memory = AgentMemory(preserve_keys=["final_answer"])
    output = "Thought: thinking\nfinal_answer: 42 is the answer.\nAction: done"
    result = memory.compress_handoff(output)
    assert "42" in result


def test_empty_input():
    memory = AgentMemory()
    assert memory.compress_handoff("") == ""


def test_scaffolding_stripped():
    memory = AgentMemory()
    output = "Thought: step one\nAction: do_thing\nObservation: result\nFinal Answer: done"
    result = memory.compress_handoff(output)
    assert "Thought:" not in result
    assert "Action:" not in result
    assert "Observation:" not in result


def test_accepts_config_object():
    from contextpilot.config import ContextPilotConfig
    cfg = ContextPilotConfig.model_validate({"compression": {"level": "aggressive"}})
    memory = AgentMemory(config=cfg)
    result = memory.compress_handoff("Thought: test\nFinal Answer: yes.")
    assert isinstance(result, str)
