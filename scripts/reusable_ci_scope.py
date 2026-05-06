#!/usr/bin/env python3
"""Select reusable CI scenarios from changed repository inputs.

Scenario entries can opt into scoped selection by adding any of these fields:

- ``scope: {"paths": ["tests/**"], "reason": "tests changed"}``
- ``scope_paths: ["tests/**"]``
- ``paths: ["tests/**"]``

If no scenario has scope metadata, selection falls back to the full matrix.
That keeps callers conservative until they explicitly annotate a matrix.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

JsonObject = dict[str, Any]
MatrixInput = list[JsonObject] | JsonObject


@dataclass(frozen=True)
class SelectionOptions:
    force_full: bool = False
    strip_scope: bool = True


@dataclass(frozen=True)
class SelectedMatrix:
    workflow_name: str
    matrix: MatrixInput
    scenarios: list[JsonObject]
    selected_count: int
    total_count: int
    reason: str
    force_full: bool = False
    scope_found: bool = False
    matched_patterns: tuple[str, ...] = field(default_factory=tuple)


def _options_from(value: Any) -> SelectionOptions:
    if isinstance(value, SelectionOptions):
        return value
    if value is None:
        return SelectionOptions()
    if isinstance(value, dict):
        return SelectionOptions(
            force_full=bool(value.get("force_full", False)),
            strip_scope=bool(value.get("strip_scope", True)),
        )
    return SelectionOptions(
        force_full=bool(getattr(value, "force_full", False)),
        strip_scope=bool(getattr(value, "strip_scope", True)),
    )


def _normalize_path(path: str) -> str:
    normalized = str(PurePosixPath(path.replace("\\", "/")))
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _normalize_matrix(full_matrix: MatrixInput) -> tuple[list[JsonObject], str]:
    if isinstance(full_matrix, list):
        return list(full_matrix), "list"
    if isinstance(full_matrix, dict):
        include = full_matrix.get("include")
        if isinstance(include, list):
            return list(include), "include"
    raise TypeError("full_matrix must be a list of scenarios or a matrix object with include")


def _restore_matrix(
    selected: list[JsonObject], full_matrix: MatrixInput, shape: str
) -> MatrixInput:
    if shape == "list":
        return selected
    restored = dict(full_matrix)
    restored["include"] = selected
    return restored


def _scope_for(scenario: JsonObject) -> tuple[list[str], str | None]:
    scope = scenario.get("scope")
    reason: str | None = None
    paths: Any = None

    if isinstance(scope, dict):
        paths = (
            scope.get("paths")
            or scope.get("path_globs")
            or scope.get("changed_paths")
            or scope.get("changed-files")
        )
        raw_reason = scope.get("reason")
        if isinstance(raw_reason, str) and raw_reason.strip():
            reason = raw_reason.strip()
    elif isinstance(scope, (list, str)):
        paths = scope

    if paths is None:
        paths = (
            scenario.get("scope_paths")
            or scenario.get("scope-paths")
            or scenario.get("paths")
            or scenario.get("changed_paths")
            or scenario.get("changed-paths")
        )

    if isinstance(paths, str):
        scope_paths = [paths]
    elif isinstance(paths, list):
        scope_paths = [str(path) for path in paths if str(path).strip()]
    else:
        scope_paths = []

    return scope_paths, reason


def _strip_scope_metadata(scenario: JsonObject) -> JsonObject:
    stripped = dict(scenario)
    for key in (
        "scope",
        "scope_paths",
        "scope-paths",
        "paths",
        "changed_paths",
        "changed-paths",
    ):
        stripped.pop(key, None)
    return stripped


def _path_matches(path: str, pattern: str) -> bool:
    normalized_path = _normalize_path(path)
    normalized_pattern = _normalize_path(pattern)

    if normalized_pattern.endswith("/"):
        return normalized_path.startswith(normalized_pattern)

    has_glob = any(char in normalized_pattern for char in "*?[]")
    if not has_glob:
        return normalized_path == normalized_pattern or normalized_path.startswith(
            f"{normalized_pattern}/"
        )

    return fnmatch.fnmatchcase(normalized_path, normalized_pattern)


def _changed_roots(changed_files: list[str]) -> str:
    roots = sorted(
        {f"{path.split('/', 1)[0]}/" if "/" in path else path for path in changed_files if path}
    )
    if not roots:
        return "changed files were unavailable"
    if len(roots) == 1:
        return f"only `{roots[0]}` changed"
    if len(roots) <= 3:
        return "changed inputs touched " + ", ".join(f"`{root}`" for root in roots)
    return f"changed inputs touched {len(roots)} top-level paths"


def _scenario_name(scenario: JsonObject) -> str:
    for key in ("name", "scenario", "id"):
        value = scenario.get(key)
        if value:
            return str(value)
    return "unnamed"


def select_scenarios(
    workflow_name: str,
    changed_files: list[str],
    full_matrix: MatrixInput,
    options: SelectionOptions | JsonObject | Any | None = None,
) -> SelectedMatrix:
    """Return the reduced matrix for the calling workflow."""

    parsed_options = _options_from(options)
    scenarios, shape = _normalize_matrix(full_matrix)
    normalized_changes = [_normalize_path(path) for path in changed_files if str(path).strip()]
    total = len(scenarios)

    if parsed_options.force_full:
        selected = [
            _strip_scope_metadata(scenario) if parsed_options.strip_scope else scenario
            for scenario in scenarios
        ]
        matrix = _restore_matrix(selected, full_matrix, shape)
        return SelectedMatrix(
            workflow_name=workflow_name,
            matrix=matrix,
            scenarios=selected,
            selected_count=len(selected),
            total_count=total,
            reason="force_full requested",
            force_full=True,
            scope_found=any(bool(_scope_for(scenario)[0]) for scenario in scenarios),
        )

    scoped_entries = [(scenario, _scope_for(scenario)) for scenario in scenarios]
    scope_found = any(bool(scope_paths) for _, (scope_paths, _) in scoped_entries)
    if not scope_found:
        selected = list(scenarios)
        matrix = _restore_matrix(selected, full_matrix, shape)
        return SelectedMatrix(
            workflow_name=workflow_name,
            matrix=matrix,
            scenarios=selected,
            selected_count=len(selected),
            total_count=total,
            reason="no reusable CI scope metadata was provided",
            scope_found=False,
        )

    if not normalized_changes:
        selected = [
            _strip_scope_metadata(scenario) if parsed_options.strip_scope else scenario
            for scenario in scenarios
        ]
        matrix = _restore_matrix(selected, full_matrix, shape)
        return SelectedMatrix(
            workflow_name=workflow_name,
            matrix=matrix,
            scenarios=selected,
            selected_count=len(selected),
            total_count=total,
            reason="changed files were unavailable",
            scope_found=True,
        )

    selected_scenarios: list[JsonObject] = []
    matched_patterns: list[str] = []
    matched_reasons: list[str] = []

    for scenario, (scope_paths, scope_reason) in scoped_entries:
        if not scope_paths:
            selected_scenarios.append(
                _strip_scope_metadata(scenario) if parsed_options.strip_scope else scenario
            )
            matched_reasons.append(f"`{_scenario_name(scenario)}` is unscoped")
            continue

        matches = [
            pattern
            for pattern in scope_paths
            if any(_path_matches(path, pattern) for path in normalized_changes)
        ]
        if matches:
            selected_scenarios.append(
                _strip_scope_metadata(scenario) if parsed_options.strip_scope else scenario
            )
            matched_patterns.extend(matches)
            if scope_reason:
                matched_reasons.append(scope_reason)

    reason = _changed_roots(normalized_changes)
    if matched_reasons:
        reason = matched_reasons[0]

    matrix = _restore_matrix(selected_scenarios, full_matrix, shape)
    return SelectedMatrix(
        workflow_name=workflow_name,
        matrix=matrix,
        scenarios=selected_scenarios,
        selected_count=len(selected_scenarios),
        total_count=total,
        reason=reason,
        scope_found=True,
        matched_patterns=tuple(dict.fromkeys(matched_patterns)),
    )


def describe_selection(selected: SelectedMatrix, full: MatrixInput) -> str:
    """Return a one-line human-readable rationale for a selected matrix."""

    full_scenarios, _shape = _normalize_matrix(full)
    total = len(full_scenarios)
    selected_count = selected.selected_count
    if selected.force_full:
        return f"running {total}/{total} scenarios because force_full was requested"
    return f"running {selected_count}/{total} scenarios because {selected.reason}"


def _load_json(raw: str, label: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{label} must be valid JSON: {exc}") from exc


def _parse_changed_files(args: argparse.Namespace) -> list[str]:
    if args.changed_files_json:
        parsed = _load_json(args.changed_files_json, "--changed-files-json")
        if not isinstance(parsed, list):
            raise SystemExit("--changed-files-json must be a JSON array")
        return [str(path) for path in parsed]
    if args.changed_files_file:
        with open(args.changed_files_file, encoding="utf-8") as handle:
            return [line.strip() for line in handle if line.strip()]
    env_value = os.environ.get("CHANGED_FILES_JSON", "")
    if env_value:
        parsed = _load_json(env_value, "CHANGED_FILES_JSON")
        if not isinstance(parsed, list):
            raise SystemExit("CHANGED_FILES_JSON must be a JSON array")
        return [str(path) for path in parsed]
    return []


def _parse_matrix(args: argparse.Namespace) -> MatrixInput:
    if args.matrix_json:
        parsed = _load_json(args.matrix_json, "--matrix-json")
    elif args.matrix_file:
        with open(args.matrix_file, encoding="utf-8") as handle:
            parsed = _load_json(handle.read(), "--matrix-file")
    else:
        raise SystemExit("one of --matrix-json or --matrix-file is required")
    if not isinstance(parsed, (list, dict)):
        raise SystemExit("matrix must be a JSON list or object")
    return parsed


def _write_github_outputs(path: str, outputs: dict[str, str]) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            handle.write(f"{key}={value}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-name", required=True)
    parser.add_argument("--changed-files-json")
    parser.add_argument("--changed-files-file")
    parser.add_argument("--matrix-json")
    parser.add_argument("--matrix-file")
    parser.add_argument("--force-full", action="store_true")
    parser.add_argument("--keep-scope-metadata", action="store_true")
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT", ""))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    full_matrix = _parse_matrix(args)
    selected = select_scenarios(
        args.workflow_name,
        _parse_changed_files(args),
        full_matrix,
        SelectionOptions(force_full=args.force_full, strip_scope=not args.keep_scope_metadata),
    )
    rationale = describe_selection(selected, full_matrix)
    matrix_json = json.dumps(selected.matrix, separators=(",", ":"), sort_keys=True)
    outputs = {
        "matrix": matrix_json,
        "selected_count": str(selected.selected_count),
        "total_count": str(selected.total_count),
        "rationale": rationale,
    }
    if args.github_output:
        _write_github_outputs(args.github_output, outputs)
    print(json.dumps({**outputs, "matrix": selected.matrix}, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main(sys.argv[1:]))
