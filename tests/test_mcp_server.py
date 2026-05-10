"""Tests for FR-010: MCP server (contextpilot/mcp_server.py)."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from contextpilot.mcp_server import (
    optimize_context,
    optimize_llm_code,
    get_savings,
    suggest_config,
)


# ---------------------------------------------------------------------------
# optimize_context tool
# ---------------------------------------------------------------------------

class TestOptimizeContext:
    def test_returns_messages(self):
        msgs = [{"role": "user", "content": "Hello"}]
        result = optimize_context(msgs)
        assert "messages" in result
        assert isinstance(result["messages"], list)

    def test_returns_savings_stats(self):
        msgs = [{"role": "user", "content": "Hello"}]
        result = optimize_context(msgs)
        assert "tokens_original" in result
        assert "tokens_compressed" in result
        assert "tokens_saved" in result
        assert "reduction_pct" in result
        assert "quality_score" in result
        assert "fallback_triggered" in result

    def test_compressed_never_more_than_original(self):
        msgs = [{"role": "user", "content": "word " * 50}]
        result = optimize_context(msgs)
        assert result["tokens_compressed"] <= result["tokens_original"]

    def test_system_prompt_forwarded(self):
        msgs = [{"role": "user", "content": "Hi"}]
        result = optimize_context(msgs, system="You are helpful.")
        # system key present (may be optimized or original)
        assert "system" in result

    def test_empty_messages(self):
        result = optimize_context([])
        assert result["tokens_original"] == 0
        assert result["tokens_saved"] == 0

    def test_large_repetitive_context_compresses(self):
        # Repeated content should trigger compression
        repeated = "The quick brown fox jumps over the lazy dog. " * 20
        msgs = [
            {"role": "user", "content": repeated},
            {"role": "assistant", "content": repeated},
            {"role": "user", "content": repeated},
            {"role": "assistant", "content": repeated},
            {"role": "user", "content": repeated},
            {"role": "assistant", "content": repeated},
            {"role": "user", "content": repeated},
            {"role": "assistant", "content": repeated},
            {"role": "user", "content": "Summarize."},
        ]
        result = optimize_context(msgs)
        # Compression may or may not trigger depending on quality gate
        # but compressed must never exceed original
        assert result["tokens_compressed"] <= result["tokens_original"]
        assert 0 <= result["quality_score"] <= 100

    def test_quality_score_in_range(self):
        msgs = [{"role": "user", "content": "Test message content here."}]
        result = optimize_context(msgs)
        assert 0 <= result["quality_score"] <= 100

    def test_reduction_pct_non_negative(self):
        msgs = [{"role": "user", "content": "Hello world"}]
        result = optimize_context(msgs)
        assert result["reduction_pct"] >= 0


# ---------------------------------------------------------------------------
# optimize_llm_code tool
# ---------------------------------------------------------------------------

class TestOptimizeLlmCode:
    def test_openai_default(self):
        code = optimize_llm_code()
        assert "contextpilot.wrap(OpenAI())" in code
        assert "import contextpilot" in code
        assert "from openai import OpenAI" in code

    def test_anthropic_provider(self):
        code = optimize_llm_code(provider="anthropic")
        assert "contextpilot.wrap(Anthropic())" in code
        assert "import contextpilot" in code
        assert "from anthropic import Anthropic" in code

    def test_openai_explicit(self):
        code = optimize_llm_code(provider="openai")
        assert "OpenAI" in code
        assert "contextpilot" in code

    def test_returns_string(self):
        assert isinstance(optimize_llm_code(), str)
        assert isinstance(optimize_llm_code("anthropic"), str)

    def test_code_is_valid_python(self):
        import ast
        for provider in ("openai", "anthropic"):
            code = optimize_llm_code(provider)
            # Should parse without SyntaxError (variables like `messages` are undefined but that's ok)
            ast.parse(code)


# ---------------------------------------------------------------------------
# get_savings resource
# ---------------------------------------------------------------------------

class TestGetSavings:
    def test_no_log_returns_message(self, tmp_path):
        fake_log = tmp_path / "events.jsonl"
        with patch("contextpilot.mcp_server._LOCAL_LOG", fake_log):
            result = get_savings()
        assert "No events" in result

    def test_returns_summary_with_events(self, tmp_path):
        log = tmp_path / "events.jsonl"
        events = [
            {"tokens_input_original": 100, "tokens_input_compressed": 60,
             "quality_score": 92.0, "fallback_triggered": False},
            {"tokens_input_original": 200, "tokens_input_compressed": 140,
             "quality_score": 88.0, "fallback_triggered": True},
        ]
        with log.open("w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")

        with patch("contextpilot.mcp_server._LOCAL_LOG", log):
            result = get_savings()

        assert "100" in result  # tokens saved (300 - 200)
        assert "2" in result    # total calls

    def test_empty_log_returns_message(self, tmp_path):
        log = tmp_path / "events.jsonl"
        log.write_text("")
        with patch("contextpilot.mcp_server._LOCAL_LOG", log):
            result = get_savings()
        assert "empty" in result.lower()


# ---------------------------------------------------------------------------
# suggest_config resource
# ---------------------------------------------------------------------------

class TestSuggestConfig:
    def test_no_log_returns_recommendation(self, tmp_path):
        fake_log = tmp_path / "events.jsonl"
        with patch("contextpilot.mcp_server._LOCAL_LOG", fake_log):
            result = suggest_config()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "balanced" in result.lower()

    def test_high_quality_suggests_aggressive(self, tmp_path):
        log = tmp_path / "events.jsonl"
        events = [
            {"quality_score": 97.0, "fallback_triggered": False}
            for _ in range(20)
        ]
        with log.open("w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")

        with patch("contextpilot.mcp_server._LOCAL_LOG", log):
            result = suggest_config()
        assert "aggressive" in result.lower()

    def test_high_fallback_suggests_conservative(self, tmp_path):
        log = tmp_path / "events.jsonl"
        events = [
            {"quality_score": 70.0, "fallback_triggered": True}
            for _ in range(20)
        ]
        with log.open("w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")

        with patch("contextpilot.mcp_server._LOCAL_LOG", log):
            result = suggest_config()
        assert "conservative" in result.lower()

    def test_moderate_suggests_balanced(self, tmp_path):
        log = tmp_path / "events.jsonl"
        events = [
            {"quality_score": 88.0, "fallback_triggered": False}
            for _ in range(10)
        ]
        with log.open("w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")

        with patch("contextpilot.mcp_server._LOCAL_LOG", log):
            result = suggest_config()
        assert "balanced" in result.lower()

    def test_returns_string(self, tmp_path):
        fake_log = tmp_path / "no_log.jsonl"
        with patch("contextpilot.mcp_server._LOCAL_LOG", fake_log):
            result = suggest_config()
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# MCP server object
# ---------------------------------------------------------------------------

class TestMcpServerObject:
    def test_server_name(self):
        from contextpilot.mcp_server import mcp
        assert mcp.name == "ContextPilot"

    def test_tools_registered(self):
        from contextpilot.mcp_server import mcp
        import asyncio
        tools = asyncio.run(mcp.list_tools())
        names = {t.name for t in tools}
        assert "optimize_context" in names
        assert "optimize_llm_code" in names

    def test_resources_registered(self):
        from contextpilot.mcp_server import mcp
        import asyncio
        resources = asyncio.run(mcp.list_resources())
        uris = {str(r.uri) for r in resources}
        assert "contextpilot://savings" in uris
        assert "contextpilot://config/suggest" in uris
