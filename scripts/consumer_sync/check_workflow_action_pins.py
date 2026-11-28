#!/usr/bin/env python3
"""Validate that selected workflow action references are commit-SHA pinned."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA = "workflow-action-pins/v1"
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
USES_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*(?P<uses>[^\s#]+)(?P<comment>\s*#.*)?$")
VERSION_COMMENT_RE = re.compile(r"#\s*v\d+(?:[.\w-]+)?\b")


def _iter_workflow_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if path.is_dir():
            candidates = sorted(
                child
                for child in path.rglob("*")
                if child.is_file() and child.suffix in {".yml", ".yaml"}
            )
        else:
            candidates = [path]
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved not in seen:
                seen.add(resolved)
                files.append(candidate)
    return files


def _is_checked_action(action: str, prefixes: tuple[str, ...]) -> bool:
    return any(action.startswith(prefix) for prefix in prefixes)


def _format_path(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


def check_file(
    path: Path,
    *,
    prefixes: tuple[str, ...] = ("actions/",),
    require_version_comment: bool = True,
) -> tuple[int, list[dict[str, Any]]]:
    """Return checked action count and pinning issues for one workflow file."""
    issues: list[dict[str, Any]] = []
    checked_count = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return 0, [
            {
                "path": _format_path(path),
                "line": 0,
                "uses": "",
                "action": "",
                "ref": "",
                "reason": "read-error",
                "message": f"Unable to read workflow file: {exc}",
            }
        ]

    for line_number, line in enumerate(lines, 1):
        match = USES_RE.match(line)
        if not match:
            continue

        uses = match.group("uses")
        action, separator, ref = uses.rpartition("@")
        if not separator or not _is_checked_action(action, prefixes):
            continue

        checked_count += 1
        comment = match.group("comment") or ""
        if not SHA_RE.match(ref):
            issues.append(
                {
                    "path": _format_path(path),
                    "line": line_number,
                    "uses": uses,
                    "action": action,
                    "ref": ref,
                    "reason": "floating-ref",
                    "message": "Action reference must use a 40-character commit SHA.",
                }
            )
            continue

        if require_version_comment and not VERSION_COMMENT_RE.search(comment):
            issues.append(
                {
                    "path": _format_path(path),
                    "line": line_number,
                    "uses": uses,
                    "action": action,
                    "ref": ref,
                    "reason": "missing-version-comment",
                    "message": "Pinned action SHA must keep a readable '# vN' version comment.",
                }
            )

    return checked_count, issues


def build_report(
    paths: list[Path],
    *,
    prefixes: tuple[str, ...] = ("actions/",),
    require_version_comment: bool = True,
) -> dict[str, Any]:
    files = _iter_workflow_files(paths)
    issues: list[dict[str, Any]] = []
    checked_uses_count = 0
    for path in files:
        file_count, file_issues = check_file(
            path,
            prefixes=prefixes,
            require_version_comment=require_version_comment,
        )
        checked_uses_count += file_count
        issues.extend(file_issues)

    return {
        "schema": SCHEMA,
        "status": "pass" if not issues else "fail",
        "checked_files": [_format_path(path) for path in files],
        "checked_file_count": len(files),
        "checked_uses_count": checked_uses_count,
        "prefixes": list(prefixes),
        "require_version_comment": require_version_comment,
        "issue_count": len(issues),
        "issues": issues,
    }


def format_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Workflow Action Pin Report",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Status: `{report['status']}`",
        f"- Files checked: {report['checked_file_count']}",
        f"- Action references checked: {report['checked_uses_count']}",
        f"- Issues: {report['issue_count']}",
    ]
    if report["issues"]:
        lines.extend(["", "| Path | Line | Uses | Reason |", "| --- | ---: | --- | --- |"])
        for issue in report["issues"]:
            lines.append(
                "| {path} | {line} | `{uses}` | {reason} |".format(
                    path=issue["path"],
                    line=issue["line"],
                    uses=issue["uses"],
                    reason=issue["reason"],
                )
            )
    return "\n".join(lines) + "\n"


def _write_outputs(
    report: dict[str, Any], output_json: Path | None, output_md: Path | None
) -> None:
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if output_md is not None:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(format_markdown(report), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate selected workflow action references are SHA-pinned."
    )
    parser.add_argument("paths", nargs="+", type=Path, help="Workflow files or directories")
    parser.add_argument(
        "--prefix",
        action="append",
        dest="prefixes",
        default=None,
        help="Action prefix to enforce, e.g. actions/ (repeatable)",
    )
    parser.add_argument(
        "--no-require-version-comment",
        action="store_true",
        help="Allow pinned SHAs without '# vN' comments.",
    )
    parser.add_argument("--output-json", type=Path, help="Write machine-readable report JSON")
    parser.add_argument("--output-md", type=Path, help="Write markdown report")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(
        args.paths,
        prefixes=tuple(args.prefixes or ["actions/"]),
        require_version_comment=not args.no_require_version_comment,
    )
    _write_outputs(report, args.output_json, args.output_md)
    print(format_markdown(report), end="")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
