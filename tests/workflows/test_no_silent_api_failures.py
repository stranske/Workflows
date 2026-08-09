"""Prevent github-script REST failures from being silently reintroduced.

Issue #3017 distinguishes a deliberate warning-only API operation from a
workflow mutation that must fail the job.  The former requires an explicit
in-script ``# best-effort:`` marker; the latter must call ``core.setFailed``.
The complete current disposition is recorded in
``docs/workflows/silent-api-failure-triage.md``.
"""

from pathlib import Path

import yaml

WORKFLOW_DIR = Path(".github/workflows")


def _candidate_steps() -> list[tuple[Path, str, str, str]]:
    """Return github-script bodies that catch REST errors without failing."""

    candidates: list[tuple[Path, str, str, str]] = []
    for workflow_path in sorted(WORKFLOW_DIR.glob("*.y*ml")):
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
                    and "github.rest." in script
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
        if "# best-effort:" not in script
    ]
    assert not unannotated, (
        "github-script REST catches must fail with core.setFailed or carry a "
        "# best-effort: rationale; see docs/workflows/silent-api-failure-triage.md:\n"
        + "\n".join(unannotated)
    )
