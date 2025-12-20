"""Heuristic return-annotation fixer for sample modules."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable

ROOT = Path(".")
PROJECT_DIRS: list[Path] = [Path("src")]
MYPY_CMD: list[str] = []


def _is_str_like(node: ast.AST, str_vars: set[str]) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.Name) and node.id in str_vars:
        return True
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id == "str":
            return True
        if isinstance(func, ast.Attribute) and func.attr in {"join", "format", "upper"}:
            return True
    return False


def _is_list_of_str(node: ast.AST, list_vars: set[str]) -> bool:
    if isinstance(node, ast.List):
        return all(_is_str_like(value, set()) for value in node.elts)
    if isinstance(node, ast.Name) and node.id in list_vars:
        return True
    return False


def _collect_string_vars(body: Iterable[ast.stmt]) -> tuple[set[str], set[str]]:
    string_vars: set[str] = set()
    list_vars: set[str] = set()
    for stmt in body:
        if isinstance(stmt, ast.Assign):
            if _is_str_like(stmt.value, string_vars):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        string_vars.add(target.id)
            if isinstance(stmt.value, ast.List) and all(
                isinstance(elt, (ast.Constant, ast.JoinedStr)) for elt in stmt.value.elts
            ):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        list_vars.add(target.id)
    return string_vars, list_vars


def _annotation_to_str(annotation: ast.AST) -> str:
    if hasattr(ast, "unparse"):
        return ast.unparse(annotation)
    return ""


def _rewrite_annotation(line: str, new_annotation: str) -> str:
    return re.sub(r"->\s*[^:]+:", f"-> {new_annotation}:", line)


def _process_function(node: ast.FunctionDef, lines: list[str], str_vars: set[str]) -> bool:
    return_types: set[str] = set()
    string_vars, list_vars = _collect_string_vars(node.body)
    for stmt in ast.walk(node):
        if isinstance(stmt, ast.Return):
            if stmt.value is None:
                continue
            if _is_list_of_str(stmt.value, list_vars):
                return_types.add("list[str]")
            elif _is_str_like(stmt.value, string_vars | str_vars):
                return_types.add("str")

    if not return_types or node.returns is None:
        return False

    annotation_text = _annotation_to_str(node.returns)
    line_index = node.lineno - 1
    original = lines[line_index]

    if "list[str]" in return_types and annotation_text in {"list[int]", "List[int]"}:
        lines[line_index] = _rewrite_annotation(original, "list[str]")
        return True
    if "str" in return_types and annotation_text == "int":
        lines[line_index] = _rewrite_annotation(original, "str")
        return True
    return False


def _process_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    module = ast.parse(text)
    lines = text.splitlines()
    changed = False

    for node in module.body:
        if isinstance(node, ast.FunctionDef):
            string_vars, list_vars = _collect_string_vars(node.body)
            changed |= _process_function(node, lines, string_vars | list_vars)

    if changed:
        path.write_text("\n".join(lines), encoding="utf-8")
    return changed


def main(_args: list[str] | None = None) -> int:
    for project_dir in PROJECT_DIRS:
        base = project_dir if project_dir.is_absolute() else ROOT / project_dir
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            _process_file(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
