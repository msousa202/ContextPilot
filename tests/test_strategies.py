import pytest
from contextpilot.config import ContextPilotConfig
from contextpilot.analyzer import Analyzer
from contextpilot.strategies.history import summarize_old_turns
from contextpilot.strategies.dedup import SystemPromptDeduplicator
from contextpilot.strategies.rag_pruner import prune_rag_chunks
from contextpilot.strategies.structural import strip_structural, apply_structural_stripping
from contextpilot.strategies.agent_memory import compress_agent_handoff


def cfg(**kwargs) -> ContextPilotConfig:
    return ContextPilotConfig.model_validate({"compression": kwargs} if kwargs else {})


# --- History summarization ---

def test_history_no_compression_within_window():
    config = cfg(history_window=6)
    messages = [{"role": "user", "content": f"msg {i}"} for i in range(4)]
    blocks = Analyzer(config).analyze(messages)
    result = summarize_old_turns(messages, blocks, config)
    assert result == messages  # window larger than history — unchanged


def test_history_compresses_old_turns():
    config = cfg(history_window=3)
    messages = [{"role": "user", "content": f"Turn number {i} with some content"} for i in range(8)]
    blocks = Analyzer(config).analyze(messages)
    result = summarize_old_turns(messages, blocks, config)
    # Result has summary block + 3 recent turns = 4 total
    assert len(result) == 4
    assert "[CTX" in result[0]["content"]
    # Recent turns unchanged
    assert result[1:] == messages[-3:]


def test_history_summary_reduces_tokens():
    config = cfg(history_window=2)
    # Each message is long enough that a compact summary header is cheaper than the full text
    messages = [
        {"role": "user", "content": "Can you explain the complete mechanism of photosynthesis including all the stages, the role of chlorophyll, the light-dependent reactions, and the Calvin cycle in detail?"},
        {"role": "assistant", "content": "Photosynthesis is a two-stage process. The light-dependent reactions occur in the thylakoid membranes where chlorophyll absorbs photons and splits water molecules, producing ATP, NADPH, and oxygen as a byproduct. The Calvin cycle then uses these energy carriers in the stroma to fix carbon dioxide into glucose through a series of enzymatic reactions."},
        {"role": "user", "content": "What specific role does chlorophyll play in capturing light energy and how does its molecular structure contribute to this function?"},
        {"role": "assistant", "content": "Chlorophyll contains a porphyrin ring with a magnesium atom at its center, surrounded by alternating single and double bonds that create a conjugated system. This conjugation allows the molecule to absorb red and blue wavelengths while reflecting green, which is why plants appear green. The absorbed photon energy excites electrons which then pass through the electron transport chain."},
        {"role": "user", "content": "How is glucose ultimately used by the plant after it is synthesized?"},
    ]
    blocks = Analyzer(config).analyze(messages)
    result = summarize_old_turns(messages, blocks, config)
    total_orig = sum(len(m["content"].split()) for m in messages)
    total_comp = sum(len(m["content"].split()) for m in result)
    assert total_comp < total_orig


# --- System prompt dedup ---

def test_dedup_first_call_unchanged():
    d = SystemPromptDeduplicator()
    system = "You are a helpful assistant."
    result = d.process(system, cfg(level="aggressive"))
    assert result == system


def test_dedup_repeated_aggressive_truncates():
    d = SystemPromptDeduplicator()
    system = "You are a helpful assistant. " * 10
    d.process(system, cfg(level="aggressive"))  # first call
    result = d.process(system, cfg(level="aggressive"))  # second call — same content
    assert len(result) < len(system)
    assert "CACHED" in result


def test_dedup_balanced_no_truncation():
    d = SystemPromptDeduplicator()
    system = "You are a helpful assistant."
    d.process(system, cfg(level="balanced"))
    result = d.process(system, cfg(level="balanced"))
    assert result == system  # balanced mode never truncates


def test_dedup_changed_system_not_truncated():
    d = SystemPromptDeduplicator()
    d.process("System A", cfg(level="aggressive"))
    result = d.process("System B — completely different", cfg(level="aggressive"))
    assert "System B" in result  # new system passed through


# --- RAG chunk pruning ---

def _rag_msg(chunks: list[str]) -> dict:
    return {
        "role": "user",
        "content": "\n\n--- DOCUMENT 1 ---\n" + "\n\n--- DOCUMENT 2 ---\n".join(chunks),
    }


def test_rag_prune_no_chunks():
    config = cfg(rag_relevance_min=0.1)
    messages = [{"role": "user", "content": "Just a plain message"}]
    result = prune_rag_chunks(messages, "query", config)
    assert result == messages


def test_rag_prune_removes_irrelevant_chunks():
    config = cfg(rag_relevance_min=0.01)
    relevant = "Python is a programming language used for machine learning."
    irrelevant = "The history of ancient Rome spans centuries of political change."
    messages = [_rag_msg([relevant, irrelevant])]
    result = prune_rag_chunks(messages, "Python programming machine learning", config)
    # After pruning, the relevant chunk should be present
    assert "Python" in result[0]["content"]


def test_rag_prune_never_empties_message():
    config = cfg(rag_relevance_min=0.99)  # very high threshold
    messages = [_rag_msg(["chunk a", "chunk b"])]
    result = prune_rag_chunks(messages, "completely unrelated query xyz", config)
    assert result[0]["content"]  # not empty


# --- Structural stripping ---

def test_strip_excessive_blank_lines():
    text = "Hello\n\n\n\n\nWorld"
    result = strip_structural(text)
    assert "\n\n\n" not in result


def test_strip_trailing_whitespace():
    text = "Hello   \nWorld   "
    result = strip_structural(text)
    for line in result.splitlines():
        assert line == line.rstrip()


def test_strip_empty_xml_tags():
    text = "Hello <br></br> World"
    result = strip_structural(text)
    assert "<br></br>" not in result


def test_strip_repeated_horizontal_rules():
    text = "Section A\n---\n---\n---\nSection B"
    result = strip_structural(text)
    assert result.count("---") == 1


def test_structural_messages_roundtrip():
    config = cfg()
    messages = [{"role": "user", "content": "Hello   \n\n\n\nWorld"}]
    result = apply_structural_stripping(messages, config)
    assert len(result) == 1
    assert result[0]["role"] == "user"
    assert "\n\n\n" not in result[0]["content"]


# --- Agent memory ---

def test_agent_memory_removes_scaffolding():
    output = (
        "Thought: I need to find the answer.\n"
        "Action: search\n"
        "Observation: result found\n"
        "Final Answer: The answer is 42."
    )
    result = compress_agent_handoff(output, preserve_keys=["Final Answer"])
    assert "Thought:" not in result
    assert "Action:" not in result


def test_agent_memory_preserves_keys():
    output = "Thought: thinking...\nfinal_answer: The answer is 42."
    result = compress_agent_handoff(output, preserve_keys=["final_answer"])
    assert "42" in result


def test_agent_memory_empty_input():
    assert compress_agent_handoff("") == ""


def test_agent_memory_reduces_length():
    long_output = (
        "Thought: I need to carefully analyze this problem step by step.\n"
        "Action: search_database\n"
        "Observation: Found 150 records matching the query criteria.\n"
        "Thought: Now I need to filter for the relevant ones.\n"
        "Action: filter_results\n"
        "Observation: 12 records remain after filtering.\n"
        "Final Answer: There are 12 relevant records.\n"
    )
    result = compress_agent_handoff(long_output, preserve_keys=["Final Answer"])
    assert len(result) < len(long_output)
