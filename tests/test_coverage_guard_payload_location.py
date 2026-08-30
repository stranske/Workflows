"""Finding the coverage report INSIDE the downloaded artifact.

The layer under `test_coverage_guard_payload_matching.py`. Resolving the artifact NAME was one
hardcoded list; resolving the FILE within it was a second, and the producer writes to a path in
neither. Verified 2026-08-30 against `stranske/Counter_Risk`'s real `gate-coverage-3.12-1`, which
holds `index.ndjson` and `runtimes/3.12/coverage.json` — extracting to
`coverage_artifacts/payload/runtimes/3.12/coverage.json`, one directory level from the first
candidate and matched by none of the seven. The old list also hardcoded the Python versions, so a
matrix change would have broken it silently and later.

The resolution is shell embedded in YAML, so these tests lift it out and run it under bash against
real directory layouts rather than reimplementing it in Python, where a copy would keep passing
while the shipped step broke.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARDS = (
    REPO_ROOT / ".github/workflows/maint-coverage-guard.yml",
    REPO_ROOT / "templates/consumer-repo/.github/workflows/maint-coverage-guard.yml",
)

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None,
    reason="bash is not installed, so the guard's embedded resolution cannot be executed",
)


def _resolution_source(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    start = text.index("          for candidate in \\")
    end = text.index("\n          # Build args", start)
    return textwrap.dedent(text[start:end])


def _resolve(guard: Path, tree: dict[str, object], root: Path) -> str:
    """Lay `tree` out under `root` and run the real resolution over it."""
    for rel, content in tree.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(content) if isinstance(content, dict) else str(content), encoding="utf-8"
        )
    script = root / "resolve.sh"
    script.write_text(
        'COVERAGE_PATH=""\n' + _resolution_source(guard) + '\necho "RESOLVED=${COVERAGE_PATH}"\n',
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["bash", str(script)], cwd=root, capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stderr
    for line in proc.stdout.splitlines():
        if line.startswith("RESOLVED="):
            return line.split("=", 1)[1]
    raise AssertionError(f"the step printed no verdict: {proc.stdout!r}")


REAL_REPORT = {"totals": {"percent_covered": 85.9}, "files": {}}


@pytest.mark.parametrize("guard", GUARDS, ids=lambda p: p.parts[-4])
def test_the_layout_the_producer_really_writes_is_found(guard, tmp_path):
    """The defect, stated once. No hardcoded candidate matches this path."""
    found = _resolve(
        guard,
        {
            "coverage_artifacts/payload/index.ndjson": "{}",
            "coverage_artifacts/payload/runtimes/3.12/coverage.json": REAL_REPORT,
            "coverage_artifacts/payload/runtimes/3.13/coverage.json": REAL_REPORT,
        },
        tmp_path,
    )
    assert found == "coverage_artifacts/payload/runtimes/3.12/coverage.json"


@pytest.mark.parametrize("guard", GUARDS, ids=lambda p: p.parts[-4])
def test_a_known_path_still_wins_so_working_repos_are_untouched(guard, tmp_path):
    """Literals first. A change that could re-resolve a repo where this already worked is a
    migration, not a fix."""
    found = _resolve(
        guard,
        {
            "coverage_artifacts/payload/coverage.json": REAL_REPORT,
            "coverage_artifacts/payload/runtimes/3.12/coverage.json": REAL_REPORT,
        },
        tmp_path,
    )
    assert found == "coverage_artifacts/payload/coverage.json"


@pytest.mark.parametrize("guard", GUARDS, ids=lambda p: p.parts[-4])
def test_a_python_version_outside_the_old_list_is_found(guard, tmp_path):
    """The old list named 3.12 and 3.13. A matrix bump would have broken it silently and later."""
    found = _resolve(
        guard,
        {"coverage_artifacts/payload/runtimes/3.15/coverage.json": REAL_REPORT},
        tmp_path,
    )
    assert found.endswith("3.15/coverage.json")


@pytest.mark.parametrize("guard", GUARDS, ids=lambda p: p.parts[-4])
def test_json_that_is_not_a_coverage_report_is_not_mistaken_for_one(guard, tmp_path):
    """The search must recognise the payload by what the guard READS, not by filename.

    `index.ndjson` sits beside the report in the real artifact, and a trend record is JSON too.
    Selecting either would make the guard compare a number against itself.
    """
    found = _resolve(
        guard,
        {
            "coverage_artifacts/payload/index.json": {"schema": 1, "runs": []},
            "coverage_artifacts/trend/coverage-trend.json": {"current": 85.9, "baseline": 85.0},
        },
        tmp_path,
    )
    assert found == ""


@pytest.mark.parametrize("guard", GUARDS, ids=lambda p: p.parts[-4])
def test_a_broken_json_does_not_abort_the_search(guard, tmp_path):
    """One unreadable file must not decide that the whole artifact holds no coverage."""
    (tmp_path / "coverage_artifacts/payload").mkdir(parents=True)
    (tmp_path / "coverage_artifacts/payload/truncated.json").write_text("{not", encoding="utf-8")
    found = _resolve(
        guard,
        {"coverage_artifacts/payload/runtimes/3.12/coverage.json": REAL_REPORT},
        tmp_path,
    )
    assert found.endswith("3.12/coverage.json")


@pytest.mark.parametrize("guard", GUARDS, ids=lambda p: p.parts[-4])
def test_two_runtimes_resolve_to_the_same_file_every_run(guard, tmp_path):
    """One suite on two interpreters. A figure that moved with directory order would be noise
    reported as a coverage change, so the search sorts rather than taking whatever `find` emits."""
    layout = {
        "coverage_artifacts/payload/runtimes/3.13/coverage.json": REAL_REPORT,
        "coverage_artifacts/payload/runtimes/3.12/coverage.json": REAL_REPORT,
    }
    first = _resolve(guard, layout, tmp_path / "one")
    second = _resolve(guard, dict(reversed(list(layout.items()))), tmp_path / "two")
    assert first == second == "coverage_artifacts/payload/runtimes/3.12/coverage.json"


def test_both_copies_carry_the_same_resolution():
    """Root and consumer diverging here is how the artifact-name defect survived three fixes."""
    assert _resolution_source(GUARDS[0]) == _resolution_source(GUARDS[1])


@pytest.mark.parametrize("guard", GUARDS, ids=lambda p: p.parts[-4])
def test_the_failure_lists_what_was_downloaded(guard):
    """ "Missing after download" gave no way to tell an empty artifact from a full one.

    The second is what really happened, in every repo, for as long as the step existed.
    """
    text = guard.read_text(encoding="utf-8")
    assert "files downloaded" in text
    assert "find coverage_artifacts -type f" in text
