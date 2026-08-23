#!/usr/bin/env python3
"""Detect documentation drift in workflow inventories and repo-path references."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

DriftRecord = dict[str, str]

DEFAULT_DOCS = ("docs/ci/WORKFLOWS.md",)
WORKFLOWS_DOC = Path("docs/ci/WORKFLOWS.md")
WORKFLOW_SUFFIXES = (".yml", ".yaml")
REPO_PATH_PREFIXES = ("scripts/", "tests/", "docs/")

WORKFLOW_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z0-9_./-]+\.ya?ml)(?![A-Za-z0-9_])")
INLINE_CODE_RE = re.compile(r"(?<!`)`(?!`)([^`\n]+?)(?<!`)`(?!`)")
FILE_EXTENSION_RE = re.compile(r"\.[A-Za-z0-9]+$")
GLOB_CHARS = set("*?[]{}!")
NON_ROOT_WORKFLOW_CONTEXT_RE = re.compile(
    r"\b(?:consumer|consumer-template|template|templates|integration-repo)\b",
    re.IGNORECASE,
)


def _workflow_files_on_disk(root: Path) -> set[str]:
    workflows_dir = root / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return set()
    return {
        path.name
        for path in workflows_dir.iterdir()
        if path.is_file() and path.suffix in WORKFLOW_SUFFIXES
    }


def _is_root_workflow_path(token: str) -> bool:
    parts = PurePosixPath(token).parts
    for index, part in enumerate(parts[:-1]):
        if part == ".github" and index + 1 < len(parts) and parts[index + 1] == "workflows":
            return "templates" not in parts and "template" not in parts
    return False


def _workflow_token_context(text: str, token_start: int, token_end: int) -> str:
    line_start = text.rfind("\n", 0, token_start) + 1
    line_end = text.find("\n", token_end)
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end]
    relative_start = token_start - line_start
    relative_end = token_end - line_start
    return line[:relative_start] + line[relative_end:]


def _is_bare_workflow_reference(
    text: str, match: re.Match[str], root_workflows: set[str] | None = None
) -> bool:
    token_start, token_end = match.span(1)
    context = _workflow_token_context(text, token_start, token_end)
    if NON_ROOT_WORKFLOW_CONTEXT_RE.search(context):
        return False

    if match.group(1) in (root_workflows or set()):
        return True

    return token_start > 0 and text[token_start - 1] == "`"


def _mentioned_workflow_filenames(text: str, root_workflows: set[str] | None = None) -> set[str]:
    filenames: set[str] = set()
    for match in WORKFLOW_TOKEN_RE.finditer(text):
        token = match.group(1)
        if "/" in token:
            if not _is_root_workflow_path(token):
                continue
            filename = PurePosixPath(token).name
            if filename not in (root_workflows or set()) and NON_ROOT_WORKFLOW_CONTEXT_RE.search(
                _workflow_token_context(text, match.start(1), match.end(1))
            ):
                continue
        elif not _is_bare_workflow_reference(text, match, root_workflows):
            continue
        if token.startswith("n.") and match.start(1) > 0 and text[match.start(1) - 1] == "\\":
            token = token[2:]
        filename = PurePosixPath(token).name
        if filename.startswith("."):
            filename = filename[1:]
        if filename.endswith(WORKFLOW_SUFFIXES) and filename not in WORKFLOW_SUFFIXES:
            filenames.add(filename)
    return filenames


def check_workflow_inventory(root: Path) -> list[DriftRecord]:
    """Compare .github/workflows files against docs/ci/WORKFLOWS.md mentions."""
    root = Path(root)
    workflows_doc = root / WORKFLOWS_DOC
    # Consumers receive this checker but do not receive Workflows' inventory.
    # An absent inventory therefore means the check is not applicable, not that
    # every local workflow needs a fabricated documentation entry.
    if not workflows_doc.is_file():
        return []
    on_disk = _workflow_files_on_disk(root)
    doc_text = workflows_doc.read_text(encoding="utf-8")
    documented = _mentioned_workflow_filenames(doc_text, on_disk)

    drift: list[DriftRecord] = []
    for filename in sorted(on_disk - documented):
        drift.append(
            {
                "type": "undocumented_workflow",
                "path": filename,
                "detail": (
                    "Exists in .github/workflows/ but is not mentioned in docs/ci/WORKFLOWS.md"
                ),
            }
        )
    for filename in sorted(documented - on_disk):
        drift.append(
            {
                "type": "documented_but_missing",
                "path": filename,
                "detail": "Mentioned in docs/ci/WORKFLOWS.md but missing from .github/workflows/",
            }
        )
    return drift


def _resolve_doc_path(root: Path, doc: str | Path) -> Path:
    doc_path = Path(doc)
    if doc_path.is_absolute():
        return doc_path
    return root / doc_path


def _display_path(path: Path, root: Path) -> str:
    return os.path.relpath(path, root).replace(os.sep, "/")


def _inline_code_tokens(text: str) -> list[str]:
    return [match.group(1) for match in INLINE_CODE_RE.finditer(text)]


def _is_repo_path_token(token: str) -> bool:
    if token != token.strip() or any(char.isspace() for char in token):
        return False
    if "\\" in token or any(char in token for char in GLOB_CHARS):
        return False
    if not token.startswith(REPO_PATH_PREFIXES):
        return False
    path = PurePosixPath(token)
    if path.is_absolute() or ".." in path.parts:
        return False
    return bool(FILE_EXTENSION_RE.search(token))


def _is_ignored_repo_path(root: Path, token: str) -> bool:
    """Return whether Git classifies a missing path as an ignored output."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "--quiet", "--", token],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _source_of_truth_section_bounds(text: str, offset: int) -> tuple[int, int] | None:
    section_start = text.rfind("\n## ", 0, offset)
    if section_start < 0:
        if not text.startswith("## "):
            return None
        section_start = 0
    else:
        section_start += 1
    heading_end = text.find("\n", section_start)
    if heading_end < 0 or text[section_start:heading_end] != "## Source Of Truth":
        return None
    content_start = heading_end + 1
    section_end = text.find("\n## ", offset)
    if section_end < 0:
        section_end = len(text)
    return content_start, section_end


def _numbered_list_block_bounds(text: str, offset: int) -> tuple[int, int] | None:
    """Return the numbered-list item block containing ``offset`` within Source Of Truth."""
    section = _source_of_truth_section_bounds(text, offset)
    if section is None:
        return None
    content_start, section_end = section
    if offset < content_start or offset >= section_end:
        return None

    line_start = text.rfind("\n", 0, offset) + 1
    line_end = text.find("\n", offset)
    if line_end < 0:
        line_end = len(text)
    current_line = text[line_start:line_end]

    if re.match(r"^\d+\.\s", current_line):
        block_start = line_start
    else:
        block_start = line_start
        pos = line_start
        while pos > content_start:
            prev_nl = text.rfind("\n", content_start, pos - 1)
            prev_start = content_start if prev_nl < content_start else prev_nl + 1
            prev_line = text[prev_start:pos]
            if re.match(r"^\d+\.\s", prev_line):
                block_start = prev_start
                break
            if prev_line.strip() == "":
                break
            block_start = prev_start
            pos = prev_start

    block_end = section_end
    pos = line_end + 1
    while pos < section_end:
        next_nl = text.find("\n", pos)
        if next_nl < 0:
            next_nl = section_end
        next_line = text[pos:next_nl]
        if next_line.strip() == "":
            block_end = pos
            break
        if re.match(r"^\d+\.\s", next_line):
            block_end = pos
            break
        pos = next_nl + 1
        block_end = min(pos, section_end)

    return block_start, block_end


def _is_explicit_upstream_reference(doc_path: Path, text: str, offset: int) -> bool:
    """Return whether an inline path is explicitly qualified as Workflows-owned."""
    if doc_path.name.casefold() != "agents.md":
        return False
    line_start = text.rfind("\n", 0, offset) + 1
    line_end = text.find("\n", offset)
    if line_end < 0:
        line_end = len(text)
    if "stranske/Workflows" in text[line_start:line_end]:
        return True

    # Consumer AGENTS files group Workflows paths under numbered Source Of Truth
    # items.  Unqualified paths on continuation lines inherit the owning list
    # item's Workflows qualification, but local-only items must remain checked.
    block = _numbered_list_block_bounds(text, offset)
    if block is None:
        return False
    block_start, block_end = block
    return "stranske/Workflows" in text[block_start:block_end]


def check_dangling_references(
    root: Path, docs: Sequence[str | Path] | None = None
) -> list[DriftRecord]:
    """Find missing repo-relative file paths cited in inline code spans."""
    root = Path(root)
    docs_to_scan = docs if docs is not None else DEFAULT_DOCS
    drift: list[DriftRecord] = []

    for doc in docs_to_scan:
        doc_path = _resolve_doc_path(root, doc)
        doc_text = doc_path.read_text(encoding="utf-8")
        cited_in = _display_path(doc_path, root)
        seen_in_doc: set[str] = set()

        for match in INLINE_CODE_RE.finditer(doc_text):
            token = match.group(1)
            if not _is_repo_path_token(token):
                continue

            if _is_explicit_upstream_reference(doc_path, doc_text, match.start(1)):
                continue

            if token in seen_in_doc:
                continue
            seen_in_doc.add(token)

            candidate = root.joinpath(*PurePosixPath(token).parts)
            if candidate.is_file():
                continue
            if _is_ignored_repo_path(root, token):
                continue
            drift.append(
                {
                    "type": "dangling_reference",
                    "path": token,
                    "detail": f"Referenced in {cited_in}",
                }
            )

    return sorted(drift, key=lambda record: (record["type"], record["path"]))


def check_docs_drift(root: Path, docs: Sequence[str | Path] | None = None) -> list[DriftRecord]:
    """Run all docs-drift checks for a repository root."""
    return check_workflow_inventory(root) + check_dangling_references(root, docs)


def build_report(drift: Sequence[DriftRecord]) -> dict[str, object]:
    """Build the deterministic machine-readable report."""
    sorted_drift = sorted(
        (dict(record) for record in drift),
        key=lambda record: (record["type"], record["path"]),
    )
    by_type = Counter(record["type"] for record in sorted_drift)
    return {
        "summary": {
            "drift": len(sorted_drift),
            "by_type": {key: by_type[key] for key in sorted(by_type)},
        },
        "drift": sorted_drift,
    }


def format_human_report(report: dict[str, object]) -> str:
    """Format a stable human summary."""
    summary = report["summary"]
    assert isinstance(summary, dict)
    drift_count = summary["drift"]
    lines = [f"Docs drift: {drift_count}"]
    drift = report["drift"]
    assert isinstance(drift, list)
    for record in drift:
        assert isinstance(record, dict)
        lines.append(f"{record['type']}  {record['path']}  \u2014 {record.get('detail', '')}")
    return "\n".join(lines)


def detect_repo_root() -> Path:
    """Find the git top-level directory, falling back to this script's repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=False,
            cwd=Path.cwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        result = None

    if result and result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return Path(__file__).resolve().parent.parent


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect drift between workflow docs and repository files."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="Repository root to scan. Defaults to git rev-parse --show-toplevel.",
    )
    parser.add_argument(
        "--docs",
        nargs="+",
        metavar="PATH",
        help="Docs to scan for dangling repo-path references.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the deterministic JSON report instead of a human summary.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Write the deterministic JSON report to this path as well.",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="PATH",
        help="Evaluate only drift records for these paths (for a bounded repair batch).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        root = (args.repo_root if args.repo_root is not None else detect_repo_root()).expanduser()
        root = root.resolve()
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"repo root not found: {_display_path(root, Path.cwd())}")

        docs = tuple(args.docs) if args.docs is not None else DEFAULT_DOCS
        if args.docs is not None:
            missing = [doc for doc in docs if not _resolve_doc_path(root, doc).is_file()]
            if missing:
                raise FileNotFoundError(f"requested docs not found: {', '.join(missing)}")
        else:
            docs = tuple(doc for doc in docs if _resolve_doc_path(root, doc).is_file())
        drift = check_docs_drift(root, docs)
        if args.only is not None:
            selected = set(args.only)
            drift = [record for record in drift if record["path"] in selected]
        report = build_report(drift)
        json_report = json.dumps(report, indent=2) + "\n"

        if args.report is not None:
            args.report.write_text(json_report, encoding="utf-8")

        if args.json:
            sys.stdout.write(json_report)
        else:
            print(format_human_report(report))

        summary = report["summary"]
        assert isinstance(summary, dict)
        return 1 if int(summary["drift"]) else 0
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
