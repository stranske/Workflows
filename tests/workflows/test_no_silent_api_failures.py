"""Prevent github-script REST failures from being silently reintroduced.

Issue #3017 distinguishes a deliberate warning-only API operation from a
workflow mutation that must fail the job.  The former requires an explicit
in-script ``# best-effort:`` marker; the latter must call ``core.setFailed``.
The complete current disposition is recorded in
``docs/workflows/silent-api-failure-triage.md``.
"""

import re
from pathlib import Path

import yaml

WORKFLOW_DIRS = (
    Path(".github/workflows"),
    Path("templates/consumer-repo/.github/workflows"),
)
API_CALL = re.compile(r"github\.(?:rest\.[A-Za-z_][\w.]*|request)\s*\(")
BEST_EFFORT = re.compile(r"#\s*best-effort:\s*\S")


def test_api_call_pattern_includes_request_dispatches() -> None:
    """The inventory must cover non-REST github-script calls too."""

    script = "await github.request('POST /repos/{owner}/{repo}/dispatches')"
    assert API_CALL.search(script) is not None
    assert API_CALL.pattern[0] == "g"


def _candidate_steps() -> list[tuple[Path, str, str, str]]:
    """Return github-script bodies that catch REST errors without failing."""

    candidates: list[tuple[Path, str, str, str]] = []
    for workflow_dir in WORKFLOW_DIRS:
        for workflow_path in sorted(workflow_dir.glob("*.y*ml")):
            workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8")) or {}
            for job_name, job in (workflow.get("jobs") or {}).items():
                for step in job.get("steps") or []:
                    if not isinstance(step, dict):
                        continue
                    if "actions/github-script" not in str(step.get("uses", "")):
                        continue
                    script = str((step.get("with") or {}).get("script", ""))
                    if (
                        "catch" in script
                        and API_CALL.search(script)
                        and "core.setFailed" not in script
                    ):
                        candidates.append(
                            (
                                workflow_path,
                                job_name,
                                str(step.get("name", "unnamed github-script step")),
                                script,
                            )
                        )
    return candidates


def test_scripted_api_blocks_either_fail_or_are_annotated() -> None:
    """Every warning-only REST catch must say why it is safe to tolerate."""

    unannotated = [
        f"{path}:{job}:{name}"
        for path, job, name, script in _candidate_steps()
        if not BEST_EFFORT.search(script)
    ]
    assert not unannotated, (
        "github-script REST catches must fail with core.setFailed or carry a "
        "# best-effort: rationale; see docs/workflows/silent-api-failure-triage.md:\n"
        + "\n".join(unannotated)
    )
