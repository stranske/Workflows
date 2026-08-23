"""Guards against GitHub Actions expressions that fail only on some events.

These are worse than a plain syntax error: the workflow parses, most triggers
work, and one trigger dies before any job starts - so the failure is invisible
until someone happens to use that path.
"""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOW_DIRS = (
    Path(".github/workflows"),
    Path("templates/consumer-repo/.github/workflows"),
)

# fromJson() expects a STRING. `github.event.inputs` is an OBJECT on
# workflow_dispatch, so fromJson(github.event.inputs) aborts the run with
# "Unexpected character encountered while parsing value: O" before any job
# starts. It is null on schedule/pull_request, so those paths pass and hide it.
# health-42-actionlint carried this from 2026-06 until 2026-08-23; the dispatch
# path was simply broken. Use the `inputs` context, which covers both
# workflow_call and workflow_dispatch.
_FROMJSON_ON_INPUTS = re.compile(r"fromJson\(\s*github\.event\.inputs")


def _workflow_files() -> list[Path]:
    files: list[Path] = []
    for directory in WORKFLOW_DIRS:
        if directory.is_dir():
            files.extend(sorted(directory.glob("*.yml")))
    return files


def test_no_workflow_passes_github_event_inputs_to_fromjson() -> None:
    offenders: list[str] = []
    for path in _workflow_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            # Comments are prose, not expressions. A note explaining WHY this
            # pattern is forbidden must not itself trip the guard - which it did
            # on the first run of this test.
            if line.lstrip().startswith("#"):
                continue
            if _FROMJSON_ON_INPUTS.search(line):
                offenders.append(f"{path}:{number}")

    assert not offenders, (
        "fromJson(github.event.inputs ...) fails on workflow_dispatch, where "
        "github.event.inputs is an object rather than a JSON string, and the run "
        "dies before any job starts. Use the `inputs` context instead. "
        f"Offenders: {offenders}"
    )


def test_the_guard_actually_scans_workflows() -> None:
    """A guard that silently scans nothing is indistinguishable from a pass."""
    files = _workflow_files()
    assert len(files) > 50, f"expected the fleet's workflows, scanned {len(files)}"


def test_guard_ignores_the_pattern_inside_a_comment(tmp_path) -> None:
    """Explaining the footgun in a comment must not count as committing it."""
    d = tmp_path / ".github" / "workflows"
    d.mkdir(parents=True)
    (d / "note.yml").write_text(
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      # never write fromJson(github.event.inputs || '{}') here\n"
        "      - run: echo ok\n",
        encoding="utf-8",
    )
    live = [
        line
        for line in (d / "note.yml").read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#") and _FROMJSON_ON_INPUTS.search(line)
    ]
    assert live == []
