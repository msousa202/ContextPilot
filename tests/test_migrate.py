"""Tests for FR-011: CLI migration agent (contextpilot/migrate.py)."""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

from contextpilot.migrate import (
    MigrationAgent,
    _has_contextpilot_import,
    _is_llm_call,
    _last_import_line,
    _transform_source,
)

# ---------------------------------------------------------------------------
# AST helper unit tests
# ---------------------------------------------------------------------------


class TestIsLlmCall:
    def _call(self, src: str) -> ast.Call:
        tree = ast.parse(src, mode="eval")
        return tree.body  # type: ignore[return-value]

    def test_openai_name(self):
        assert _is_llm_call(self._call("OpenAI()"))

    def test_async_openai(self):
        assert _is_llm_call(self._call("AsyncOpenAI(api_key='x')"))

    def test_anthropic_name(self):
        assert _is_llm_call(self._call("Anthropic()"))

    def test_async_anthropic(self):
        assert _is_llm_call(self._call("AsyncAnthropic()"))

    def test_qualified_openai(self):
        assert _is_llm_call(self._call("openai.OpenAI()"))

    def test_qualified_anthropic(self):
        assert _is_llm_call(self._call("anthropic.Anthropic()"))

    def test_non_llm_call(self):
        assert not _is_llm_call(self._call("requests.get('http://x')"))

    def test_non_llm_name(self):
        assert not _is_llm_call(self._call("MyClass()"))

    def test_not_a_call(self):
        # A Name node (not a Call) should return False
        name_node = ast.parse("x", mode="eval").body  # ast.Name
        assert not _is_llm_call(name_node)  # type: ignore[arg-type]


class TestHasContextpilotImport:
    def _tree(self, src: str) -> ast.Module:
        return ast.parse(src)

    def test_detects_import(self):
        assert _has_contextpilot_import(self._tree("import contextpilot\n"))

    def test_detects_from_import(self):
        assert _has_contextpilot_import(self._tree("from contextpilot import wrap\n"))

    def test_not_present(self):
        assert not _has_contextpilot_import(self._tree("import os\n"))

    def test_empty_module(self):
        assert not _has_contextpilot_import(self._tree(""))


class TestLastImportLine:
    def _tree(self, src: str) -> ast.Module:
        return ast.parse(src)

    def test_no_imports(self):
        assert _last_import_line(self._tree("x = 1\n")) == 0

    def test_single_import(self):
        assert _last_import_line(self._tree("import os\n")) == 1

    def test_multiple_imports(self):
        src = "import os\nimport sys\nfrom pathlib import Path\n"
        assert _last_import_line(self._tree(src)) == 3


# ---------------------------------------------------------------------------
# Source transformation tests
# ---------------------------------------------------------------------------


class TestTransformSource:
    def _result(self, src: str):
        return _transform_source(textwrap.dedent(src), Path("test.py"))

    def test_wraps_openai(self):
        src = """\
            from openai import OpenAI
            client = OpenAI()
            """
        r = self._result(src)
        assert r.changed
        assert "contextpilot.wrap(OpenAI())" in r.rewritten
        assert r.call_count == 1

    def test_wraps_anthropic(self):
        src = """\
            from anthropic import Anthropic
            client = Anthropic(api_key="sk-x")
            """
        r = self._result(src)
        assert r.changed
        assert 'contextpilot.wrap(Anthropic(api_key="sk-x"))' in r.rewritten

    def test_adds_import_after_last_import(self):
        src = """\
            import os
            from openai import OpenAI
            client = OpenAI()
            """
        r = self._result(src)
        lines = r.rewritten.splitlines()
        import_line_idx = next(
            i for i, ln in enumerate(lines) if ln.strip() == "import contextpilot"
        )
        # Should appear after 'from openai import OpenAI' (line index 1)
        assert import_line_idx >= 1

    def test_does_not_add_duplicate_import(self):
        src = """\
            import contextpilot
            from openai import OpenAI
            client = OpenAI()
            """
        r = self._result(src)
        assert r.rewritten.count("import contextpilot") == 1

    def test_no_changes_when_no_llm_calls(self):
        src = """\
            import os
            x = os.getcwd()
            """
        r = self._result(src)
        assert not r.changed
        assert r.call_count == 0

    def test_skips_already_wrapped(self):
        src = """\
            import contextpilot
            from openai import OpenAI
            client = contextpilot.wrap(OpenAI())
            """
        r = self._result(src)
        assert not r.changed

    def test_wraps_qualified_call(self):
        src = """\
            import openai
            client = openai.OpenAI(api_key="k")
            """
        r = self._result(src)
        assert r.changed
        assert "contextpilot.wrap(openai.OpenAI(" in r.rewritten

    def test_multiple_clients(self):
        src = """\
            from openai import OpenAI
            from anthropic import Anthropic
            oa = OpenAI()
            ac = Anthropic()
            """
        r = self._result(src)
        assert r.call_count == 2
        assert r.rewritten.count("contextpilot.wrap(") == 2

    def test_syntax_error_skipped(self):
        r = _transform_source("def broken(:\n    pass\n", Path("bad.py"))
        assert not r.changed

    def test_annotated_assignment(self):
        src = """\
            from openai import OpenAI
            client: OpenAI = OpenAI()
            """
        r = self._result(src)
        assert r.changed
        assert "contextpilot.wrap(OpenAI())" in r.rewritten

    def test_no_import_block_prepend(self):
        """When there are no existing imports, add import contextpilot at top."""
        # Remove all imports manually to simulate no imports
        r = _transform_source("client = OpenAI()\n", Path("t.py"))
        # No imports at all, contextpilot import should be prepended
        assert r.rewritten.startswith("import contextpilot")


# ---------------------------------------------------------------------------
# MigrationAgent integration tests
# ---------------------------------------------------------------------------


class TestMigrationAgent:
    def test_dry_run_does_not_write(self, tmp_path: Path):
        src = "from openai import OpenAI\nclient = OpenAI()\n"
        py = tmp_path / "app.py"
        py.write_text(src)

        agent = MigrationAgent()
        agent.run(str(tmp_path), dry_run=True, apply=False)

        assert py.read_text() == src  # unchanged

    def test_apply_writes_file(self, tmp_path: Path):
        src = "from openai import OpenAI\nclient = OpenAI()\n"
        py = tmp_path / "app.py"
        py.write_text(src)

        agent = MigrationAgent()
        agent.run(str(tmp_path), dry_run=False, apply=True)

        result = py.read_text()
        assert "contextpilot.wrap(OpenAI())" in result

    def test_skips_venv_dirs(self, tmp_path: Path):
        venv = tmp_path / "venv" / "lib"
        venv.mkdir(parents=True)
        py = venv / "app.py"
        py.write_text("from openai import OpenAI\nclient = OpenAI()\n")

        agent = MigrationAgent()
        agent.run(str(tmp_path), dry_run=False, apply=True)

        assert py.read_text().count("contextpilot.wrap") == 0

    def test_no_llm_calls_no_changes(self, tmp_path: Path, capsys):
        py = tmp_path / "util.py"
        py.write_text("import os\nx = os.getcwd()\n")

        agent = MigrationAgent()
        agent.run(str(tmp_path), dry_run=True, apply=False)

        captured = capsys.readouterr()
        assert "No LLM" in captured.out

    def test_single_file_path(self, tmp_path: Path):
        py = tmp_path / "main.py"
        py.write_text("from anthropic import Anthropic\nclient = Anthropic()\n")

        agent = MigrationAgent()
        agent.run(str(py), dry_run=False, apply=True)

        assert "contextpilot.wrap(Anthropic())" in py.read_text()
