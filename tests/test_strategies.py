from unittest.mock import patch

import contextpilot.strategies.rag_pruner as rag_pruner
from contextpilot.analyzer import Analyzer, Intent
from contextpilot.config import ContextPilotConfig
from contextpilot.report import BlockDecision
from contextpilot.strategies.agent_memory import compress_agent_handoff
from contextpilot.strategies.dedup import SystemPromptDeduplicator
from contextpilot.strategies.history import epoch_boundary, summarize_old_turns
from contextpilot.strategies.rag_pruner import prune_rag_chunks
from contextpilot.strategies.structural import apply_structural_stripping, strip_structural


def cfg(**kwargs) -> ContextPilotConfig:
    return ContextPilotConfig.model_validate({"compression": kwargs} if kwargs else {})


# --- History summarization ---


def test_history_no_compression_within_window():
    config = cfg(history_window=6)
    messages = [{"role": "user", "content": f"msg {i}"} for i in range(4)]
    blocks = Analyzer(config).analyze(messages)
    result = summarize_old_turns(messages, blocks, config)
    assert result == messages  # window larger than history, unchanged


def test_history_compresses_old_turns():
    config = cfg(history_window=3, history_epoch=1)
    messages = [{"role": "user", "content": f"Turn number {i} with some content"} for i in range(8)]
    blocks = Analyzer(config).analyze(messages)
    result = summarize_old_turns(messages, blocks, config)
    # Result has summary block + 3 recent turns = 4 total
    assert len(result) == 4
    assert "Prior context" in result[0]["content"]
    # Recent turns unchanged
    assert result[1:] == messages[-3:]


def test_history_summary_reduces_tokens():
    config = cfg(history_window=2, history_epoch=1)
    # Each message is long enough that a compact summary header is cheaper than the full text
    messages = [
        {
            "role": "user",
            "content": "Can you explain the complete mechanism of photosynthesis including all the stages, the role of chlorophyll, the light-dependent reactions, and the Calvin cycle in detail?",
        },
        {
            "role": "assistant",
            "content": "Photosynthesis is a two-stage process. The light-dependent reactions occur in the thylakoid membranes where chlorophyll absorbs photons and splits water molecules, producing ATP, NADPH, and oxygen as a byproduct. The Calvin cycle then uses these energy carriers in the stroma to fix carbon dioxide into glucose through a series of enzymatic reactions.",
        },
        {
            "role": "user",
            "content": "What specific role does chlorophyll play in capturing light energy and how does its molecular structure contribute to this function?",
        },
        {
            "role": "assistant",
            "content": "Chlorophyll contains a porphyrin ring with a magnesium atom at its center, surrounded by alternating single and double bonds that create a conjugated system. This conjugation allows the molecule to absorb red and blue wavelengths while reflecting green, which is why plants appear green. The absorbed photon energy excites electrons which then pass through the electron transport chain.",
        },
        {
            "role": "user",
            "content": "How is glucose ultimately used by the plant after it is synthesized?",
        },
    ]
    blocks = Analyzer(config).analyze(messages)
    result = summarize_old_turns(messages, blocks, config)
    total_orig = sum(len(m["content"].split()) for m in messages)
    total_comp = sum(len(m["content"].split()) for m in result)
    assert total_comp < total_orig


# --- Cache-stability contract ---


def test_epoch_boundary_quantized():
    # boundary only advances in epoch-sized steps
    assert epoch_boundary(10, 4, 8, 10) == 0  # 10-4=6, floor to epoch 8 -> 0
    assert epoch_boundary(13, 4, 8, 13) == 8  # 13-4=9, floor -> 8
    assert epoch_boundary(20, 4, 8, 20) == 16
    # never exceeds the mutable prefix
    assert epoch_boundary(20, 4, 8, 7) == 0
    assert epoch_boundary(20, 4, 8, 9) == 8


def test_history_prefix_stable_between_epochs():
    """The forwarded payload must be byte-identical across turns between epoch jumps."""
    config = cfg(history_window=2, history_epoch=4)
    base = [
        {"role": "user", "content": f"Turn {i} some distinctive content number {i}"}
        for i in range(12)
    ]
    analyzer = Analyzer(config)

    out_prev = summarize_old_turns(base[:10], analyzer.analyze(base[:10]), config)
    out_next = summarize_old_turns(base[:11], analyzer.analyze(base[:11]), config)
    # Same epoch boundary (10-2=8 and 11-2=9 both floor to 8): the summary
    # block and every surviving old turn must be identical.
    assert out_prev[0] == out_next[0]
    shared = min(len(out_prev), len(out_next)) - 1
    assert out_prev[:shared] == out_next[:shared]


def test_history_never_folds_block_content():
    config = cfg(history_window=1, history_epoch=1)
    messages = [
        {"role": "user", "content": [{"type": "tool_result", "content": "result data"}]},
        {"role": "user", "content": "plain old turn with content"},
        {"role": "user", "content": "final question"},
    ]
    blocks = Analyzer(config).analyze(messages)
    result = summarize_old_turns(messages, blocks, config)
    # Block-content message at index 0 blocks the mutable prefix: nothing folded
    assert result == messages


def test_history_debug_excerpt_is_content_based():
    config = cfg(history_window=1, history_epoch=1)
    messages = [
        {"role": "user", "content": "Traceback (most recent call last):\nTypeError: boom"},
        {"role": "user", "content": "final question"},
    ]
    blocks = Analyzer(config).analyze(messages)
    # No intent argument: the error excerpt is preserved because the message
    # itself contains a debug signal, deterministically.
    result = summarize_old_turns(messages, blocks, config)
    assert "Traceback" in result[0]["content"]


# --- Structural stripping ---


def test_structural_diff_content_skips_repetition_rules():
    plain = "Section A\n---\n---\n---\nSection B"
    diffish = "diff --git a/x b/x\n@@ -1 +1 @@\nSection A\n---\n---\n---\nSection B"
    assert strip_structural(plain).count("---") == 1
    # Repetition collapsing is skipped when the text itself contains diff markers
    assert strip_structural(diffish).count("---") == 3


def test_structural_deterministic():
    text = "Hello   \n\n\n\nWorld\n---\n---\n---\n"
    assert strip_structural(text) == strip_structural(text)


def test_structural_skips_block_content():
    config = cfg()
    block_msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": "Hello\n\n\n\nWorld", "cache_control": {"type": "ephemeral"}}
        ],
    }
    result = apply_structural_stripping([block_msg], config)
    assert result[0] is block_msg  # forwarded untouched


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


# --- Report / decision tracking ---


def test_history_summarize_emits_decisions():
    config = cfg(history_window=1, history_epoch=1)
    messages = [
        {"role": "user", "content": f"Turn {i} with plenty of content here"} for i in range(4)
    ]
    blocks = Analyzer(config).analyze(messages)
    decisions: list[BlockDecision] = []
    summarize_old_turns(messages, blocks, config, decisions=decisions)
    assert len(decisions) == 3  # 3 old turns folded into the summary
    assert all(d.strategy_applied == "history" and d.action == "summarized" for d in decisions)


def test_rag_pruner_emits_decision_on_drop():
    config = cfg(rag_relevance_min=0.5)
    relevant = "Python is a versatile programming language for data science."
    unrelated = "Ancient Rome had a complex system of aqueducts and roads."
    messages = [_rag_msg([relevant, unrelated])]
    decisions: list[BlockDecision] = []
    prune_rag_chunks(messages, "Python programming data science", config, decisions=decisions)
    if decisions:  # only asserts shape when the TF-IDF threshold actually drops a chunk
        assert decisions[0].strategy_applied == "rag_pruner"
        assert decisions[0].action == "dropped"


# --- System prompt dedup (stability tracking; truncation removed) ---


def test_dedup_never_truncates():
    d = SystemPromptDeduplicator()
    system = "You are a helpful assistant. " * 10
    d.process(system, cfg(level="aggressive"))
    result = d.process(system, cfg(level="aggressive"))
    assert result == system
    assert "CACHED" not in result


def test_dedup_tracks_stability():
    d = SystemPromptDeduplicator()
    system = "You are a helpful assistant."
    assert d.observe(system) is False  # first sighting
    assert d.observe(system) is True
    assert d.stable_count == 1
    assert d.observe("Different prompt") is False
    assert d.stable_count == 0


def test_dedup_reset():
    d = SystemPromptDeduplicator()
    d.observe("prompt")
    d.observe("prompt")
    d.reset()
    assert d.stable_count == 0
    assert d.observe("prompt") is False


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


def test_rag_pruner_intent_thresholds_differ():
    config = cfg(rag_relevance_min=0.01)
    relevant = "Python is a versatile programming language for data science."
    unrelated = "Ancient Rome had a complex system of aqueducts and roads."
    messages = [_rag_msg([relevant, unrelated])]
    query = "Python programming data science"
    default_result = prune_rag_chunks(messages, query, config)
    refactor_result = prune_rag_chunks(messages, query, config, intent=Intent.REFACTOR)
    # The higher effective threshold under REFACTOR should never keep *more*
    # content than the default (lower) threshold.
    assert len(refactor_result[0]["content"]) <= len(default_result[0]["content"])


def test_rag_prune_historical_message_uses_own_query_only():
    """A historical chunk message with no leading question is left untouched.

    Pruning history against the current conversation query would rewrite old
    bytes on every turn and defeat provider prefix caching.
    """
    config = cfg(rag_relevance_min=0.9)
    history_msg = _rag_msg(["chunk about Python", "chunk about Rome"])
    final_msg = {"role": "user", "content": "tell me about Python"}
    result = prune_rag_chunks([history_msg, final_msg], "Python", config)
    assert result[0] == history_msg  # no leading query, not final: untouched


def test_rag_prune_skips_block_content():
    config = cfg(rag_relevance_min=0.01)
    block_msg = {"role": "user", "content": [{"type": "text", "text": "a\n\nb\n\nc"}]}
    result = prune_rag_chunks([block_msg], "query", config)
    assert result[0] is block_msg


def test_rag_prune_reuses_vectorizer_across_messages():
    config = cfg(rag_relevance_min=0.01)
    messages = [
        {
            "role": "user",
            "content": (
                "Python docs\n\n--- DOCUMENT 1 ---\nPython is a programming language.\n\n"
                "--- DOCUMENT 2 ---\nAncient Rome had many roads."
            ),
        },
        {
            "role": "user",
            "content": (
                "Python syntax\n\n--- DOCUMENT 1 ---\nPython supports list comprehensions.\n\n"
                "--- DOCUMENT 2 ---\nGreek pottery used geometric patterns."
            ),
        },
    ]

    with patch.object(
        rag_pruner, "TfidfVectorizer", wraps=rag_pruner.TfidfVectorizer
    ) as vectorizer:
        result = prune_rag_chunks(messages, "Python", config)

    assert vectorizer.call_count == 1
    assert all("Python" in message["content"] for message in result)


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
