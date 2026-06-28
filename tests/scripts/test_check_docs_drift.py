from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest
from scripts.check_docs_drift import (
    _is_repo_path_token,
    _is_root_workflow_path,
    _mentioned_workflow_filenames,
    build_report,
    check_dangling_references,
    check_workflow_inventory,
    format_human_report,
)


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _repo(
    root: Path,
    *,
    workflows: Iterable[str] = (),
    workflows_doc: str = "",
    extra_files: Iterable[str] = (),
) -> Path:
    _write(root / "docs/ci/WORKFLOWS.md", workflows_doc)
    for workflow in workflows:
        _write(root / ".github/workflows" / workflow, "name: test\n")
    for extra_file in extra_files:
        _write(root / extra_file, "")
    return root


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        (".github/workflows/ci.yml", True),
        ("../../.github/workflows/ci.yml", True),
        ("templates/consumer-repo/.github/workflows/ci.yml", False),
        ("scripts/check_docs_drift.py", False),
    ],
)
def test_is_root_workflow_path(token: str, expected: bool) -> None:
    assert _is_root_workflow_path(token) is expected


def test_mentioned_workflow_filenames_counts_root_workflow_paths() -> None:
    text = "Inventory link: [CI](../../.github/workflows/ci.yml).\n"

    assert _mentioned_workflow_filenames(text, {"ci.yml"}) == {"ci.yml"}


def test_mentioned_workflow_filenames_counts_bare_backtick_references() -> None:
    text = "The `health-72-template-sync.yml` workflow validates template sync.\n"

    assert _mentioned_workflow_filenames(text, {"health-72-template-sync.yml"}) == {
        "health-72-template-sync.yml"
    }


def test_mentioned_workflow_filenames_unwraps_escaped_tokens() -> None:
    text = r"Release workflow \\n.release.pipeline.v2.yml is listed here.\n"

    assert _mentioned_workflow_filenames(text, {"n.release.pipeline.v2.yml"}) == {
        "release.pipeline.v2.yml"
    }


def test_mentioned_workflow_filenames_counts_backslash_escaped_root_paths() -> None:
    text = r"Inventory link: \\.github/workflows/ci.yml\n"

    assert _mentioned_workflow_filenames(text, {"ci.yml"}) == {"ci.yml"}


def test_mentioned_workflow_filenames_skips_template_consumer_context() -> None:
    text = """
Consumer template examples use `agents-80-pr-event-hub.yml` and
[Template](../../templates/consumer-repo/.github/workflows/template-only.yml).
"""

    assert _mentioned_workflow_filenames(text, set()) == set()


def test_check_workflow_inventory_reports_undocumented_workflow(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        workflows=("orphan.yml",),
        workflows_doc="This doc intentionally names no workflow files.\n",
    )

    drift = check_workflow_inventory(root)

    assert [(record["type"], record["path"]) for record in drift] == [
        ("undocumented_workflow", "orphan.yml")
    ]


def test_check_workflow_inventory_reports_documented_but_missing_workflow(
    tmp_path: Path,
) -> None:
    root = _repo(
        tmp_path,
        workflows_doc="The retired `missing.yml` workflow is still listed.\n",
    )

    drift = check_workflow_inventory(root)

    assert [(record["type"], record["path"]) for record in drift] == [
        ("documented_but_missing", "missing.yml")
    ]


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("scripts/check_docs_drift.py", True),
        ("tests/scripts/test_check_docs_drift.py", True),
        ("docs/ci/WORKFLOWS.md", True),
        ("scripts/*.py", False),
        ("scripts/file?.py", False),
        ("scripts/[abc].py", False),
        ("docs/{old,new}.md", False),
        ("tests/!excluded.py", False),
        (" scripts/leading-space.py", False),
        ("scripts/trailing-space.py ", False),
        ("scripts/has\ttab.py", False),
        ("/scripts/abs.py", False),
        ("scripts/../escape.py", False),
        ("README.md", False),
        ("scripts/no-extension", False),
    ],
)
def test_is_repo_path_token(token: str, expected: bool) -> None:
    assert _is_repo_path_token(token) is expected


def test_check_dangling_references_dedupes_tokens_within_one_doc(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        workflows_doc=("First cite: `scripts/missing.py`.\nSecond cite: `scripts/missing.py`.\n"),
    )

    drift = check_dangling_references(root)

    assert len(drift) == 1
    assert drift[0]["path"] == "scripts/missing.py"


def test_check_dangling_references_reports_only_missing_files(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        workflows=("build.yml",),
        workflows_doc=(
            "Existing path: `scripts/existing.py`.\n"
            "Missing path: `scripts/missing.py`.\n"
            "`build.yml` is a workflow token, not a repo-path token.\n"
        ),
        extra_files=("scripts/existing.py",),
    )

    drift = check_dangling_references(root)

    assert [(record["type"], record["path"]) for record in drift] == [
        ("dangling_reference", "scripts/missing.py")
    ]


def test_build_report_sorts_records_and_summarizes_by_type() -> None:
    drift = [
        {"type": "undocumented_workflow", "path": "zeta.yml", "detail": "z"},
        {"type": "dangling_reference", "path": "scripts/missing.py", "detail": "d"},
        {"type": "undocumented_workflow", "path": "alpha.yml", "detail": "a"},
        {"type": "documented_but_missing", "path": "beta.yml", "detail": "b"},
    ]

    report = build_report(drift)

    assert report["summary"] == {
        "drift": 4,
        "by_type": {
            "dangling_reference": 1,
            "documented_but_missing": 1,
            "undocumented_workflow": 2,
        },
    }
    assert [(record["type"], record["path"]) for record in report["drift"]] == [
        ("dangling_reference", "scripts/missing.py"),
        ("documented_but_missing", "beta.yml"),
        ("undocumented_workflow", "alpha.yml"),
        ("undocumented_workflow", "zeta.yml"),
    ]


def test_format_human_report_emits_stable_summary_lines() -> None:
    report = build_report(
        [
            {
                "type": "dangling_reference",
                "path": "scripts/missing.py",
                "detail": "Referenced in docs/ci/WORKFLOWS.md",
            }
        ]
    )

    rendered = format_human_report(report)

    assert rendered.splitlines() == [
        "Docs drift: 1",
        "dangling_reference  scripts/missing.py  \u2014 Referenced in docs/ci/WORKFLOWS.md",
    ]
