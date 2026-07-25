"""FR-011: CLI migration agent (Surface D).

Scans Python source files, finds LLM SDK client instantiations via AST
parsing, and wraps them with contextpilot.wrap(). Supports --dry-run
(show diff only) and --apply (rewrite files in place).

Usage:
    contextpilot migrate ./src/ --dry-run
    contextpilot migrate ./src/ --apply
"""

from __future__ import annotations

import ast
import difflib
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Constructor names that signal an LLM client being created.
_LLM_NAMES: frozenset[str] = frozenset({"OpenAI", "AsyncOpenAI", "Anthropic", "AsyncAnthropic"})
# Top-level module names whose attributes we also recognise.
_LLM_MODULES: frozenset[str] = frozenset({"openai", "anthropic"})


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _is_llm_call(node: ast.expr) -> bool:
    """Return True if *node* is a direct or module-qualified LLM constructor call."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in _LLM_NAMES
    if isinstance(func, ast.Attribute):
        return (
            isinstance(func.value, ast.Name)
            and func.value.id in _LLM_MODULES
            and func.attr in _LLM_NAMES
        )
    return False


def _has_contextpilot_import(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "contextpilot" for alias in node.names):
                return True
        if isinstance(node, (ast.ImportFrom,)):
            if node.module == "contextpilot":
                return True
    return False


def _last_import_line(tree: ast.Module) -> int:
    """Return the line number of the last top-level import statement (1-based)."""
    last = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            last = node.end_lineno or node.lineno  # type: ignore[attr-defined]
    return last


# ---------------------------------------------------------------------------
# Source-level rewriting utilities
# ---------------------------------------------------------------------------


def _line_offsets(source: str) -> list[int]:
    """Return cumulative byte offsets for the start of each line (0-indexed by lineno-1)."""
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _char_offset(offsets: list[int], lineno: int, col: int) -> int:
    return offsets[lineno - 1] + col


@dataclass
class _Replacement:
    start: int  # char offset in source
    end: int  # char offset in source
    text: str  # replacement text


def _apply_replacements(source: str, replacements: list[_Replacement]) -> str:
    # Process from last to first so earlier offsets remain valid.
    for r in sorted(replacements, key=lambda r: r.start, reverse=True):
        source = source[: r.start] + r.text + source[r.end :]
    return source


# ---------------------------------------------------------------------------
# Per-file transformation
# ---------------------------------------------------------------------------


@dataclass
class FileResult:
    path: Path
    original: str
    rewritten: str
    call_count: int

    @property
    def changed(self) -> bool:
        return self.original != self.rewritten

    def unified_diff(self) -> str:
        a = self.original.splitlines(keepends=True)
        b = self.rewritten.splitlines(keepends=True)
        name = str(self.path)
        return "".join(difflib.unified_diff(a, b, fromfile=name, tofile=name))


def _transform_source(source: str, path: Path) -> FileResult:
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        print(f"  [skip] {path}: syntax error, {exc}", file=sys.stderr)
        return FileResult(path=path, original=source, rewritten=source, call_count=0)

    offsets = _line_offsets(source)
    replacements: list[_Replacement] = []
    call_count = 0

    for node in ast.walk(tree):
        # Match: var = LLMConstructor(...) in Assign or AnnAssign
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            value = node.value

        if value is None or not _is_llm_call(value):
            continue

        # Already wrapped, skip (wrap is itself a Call with func.id='wrap')
        call = value  # ast.Call
        outer = getattr(call, "_cp_wrapped", False)
        if outer:
            continue

        segment = ast.get_source_segment(source, call)
        if segment is None:
            continue

        start = _char_offset(offsets, call.lineno, call.col_offset)  # type: ignore[attr-defined]
        end = _char_offset(offsets, call.end_lineno, call.end_col_offset)  # type: ignore[attr-defined, arg-type]

        # Guard: don't double-wrap if the segment already starts with contextpilot.wrap
        if segment.startswith("contextpilot.wrap("):
            continue

        replacements.append(_Replacement(start, end, f"contextpilot.wrap({segment})"))
        call_count += 1

    if call_count == 0:
        return FileResult(path=path, original=source, rewritten=source, call_count=0)

    rewritten = _apply_replacements(source, replacements)

    # Insert `import contextpilot` if not already present
    if not _has_contextpilot_import(tree):
        insert_after = _last_import_line(tree)
        if insert_after == 0:
            # No imports at all, prepend
            rewritten = "import contextpilot\n" + rewritten
        else:
            # Insert after the last import line
            lines = rewritten.splitlines(keepends=True)
            lines.insert(insert_after, "import contextpilot\n")
            rewritten = "".join(lines)

    return FileResult(path=path, original=source, rewritten=rewritten, call_count=call_count)


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------


@dataclass
class MigrationAgent:
    config_path: str | None = None
    _results: list[FileResult] = field(default_factory=list, init=False)

    def run(self, path: str = ".", *, dry_run: bool = True, apply: bool = False) -> None:
        root = Path(path).resolve()
        py_files = sorted(root.rglob("*.py")) if root.is_dir() else [root]

        results = []
        for py_file in py_files:
            # Skip virtual environments and hidden dirs
            parts = py_file.parts
            skip = {"venv", ".venv", "env", "__pycache__", "node_modules"}
            if any(p.startswith(".") or p in skip for p in parts):
                continue
            source = py_file.read_text(encoding="utf-8", errors="replace")
            result = _transform_source(source, py_file)
            if result.changed:
                results.append(result)

        self._results = results

        if not results:
            print("No LLM client instantiations found that need wrapping.")
            return

        total_calls = sum(r.call_count for r in results)
        print(f"Found {total_calls} LLM call(s) across {len(results)} file(s).")
        print()

        for result in results:
            base = Path(path).resolve()
            rel = result.path.relative_to(base) if Path(path).is_dir() else result.path
            print(f"  {rel}  ({result.call_count} call(s))")
            if dry_run and not apply:
                diff = result.unified_diff()
                if diff:
                    print(diff)

        if apply:
            for result in results:
                result.path.write_text(result.rewritten, encoding="utf-8")
            print(f"\nApplied: {len(results)} file(s) rewritten.")
        elif dry_run:
            print("\nDry run: no files modified. Use --apply to write changes.")
