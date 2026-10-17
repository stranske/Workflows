"""A sparse checkout into the SAME workspace must not follow an unconditional full checkout.

`actions/checkout` with `sparse-checkout` re-applies a sparse set to the workspace and removes every tracked file outside it.
Maint Coverage Guard's monitor job did exactly that (a full checkout, then "Checkout retry helpers" with four sparse paths), so
`tools/coverage_guard.py` was gone when `Run coverage guard` ran, and the daily run could not measure anything. The jobs in
`reusable-10-ci-python.yml` pair a full and a sparse checkout under mutually exclusive `if:` conditions and are fine. Only `path`
decides where a checkout lands (`repository` only chooses WHAT is checked out), so a sparse checkout of another repository
without a `path` replaces the workspace root too.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIRS = (
    ROOT / ".github" / "workflows",
    ROOT / "templates" / "consumer-repo" / ".github" / "workflows",
)

# (workflow, job) -> why the replacement is intended. Each entry was verified, and the test below fails when one stops matching.
INTENTIONAL = {
    (
        ".github/workflows/agents-71-codex-belt-dispatcher.yml",
        "dispatch",
    ): (
        "the consumer checkout supplies ./.github/actions/resolve-default-branch, which runs BEFORE the Workflows helper sparse "
        "checkout replaces the tree; every later step reads only paths inside that sparse set (checked 2026-10-16)"
    ),
    (
        "templates/consumer-repo/.github/workflows/agents-71-codex-belt-dispatcher.yml",
        "dispatch",
    ): "the same job in the consumer template, with the same reasoning (checked 2026-10-16)",
}


def _checkouts(job: dict) -> list[dict]:
    found = []
    for step in job.get("steps") or []:
        if str(step.get("uses", "")).startswith("actions/checkout"):
            found.append(step)
    return found


def _into_workspace_root(step: dict) -> bool:
    return not (step.get("with") or {}).get("path")


def _is_sparse(step: dict) -> bool:
    return bool((step.get("with") or {}).get("sparse-checkout"))


def clobbering_pairs(workflow: dict) -> list[tuple[str, str, str]]:
    """(job, full checkout step, later sparse checkout step) where the full one always runs."""
    pairs = []
    for job_name, job in (workflow.get("jobs") or {}).items():
        steps = _checkouts(job)
        for i, full in enumerate(steps):
            if _is_sparse(full) or not _into_workspace_root(full) or full.get("if") is not None:
                continue
            for later in steps[i + 1 :]:
                if _is_sparse(later) and _into_workspace_root(later):
                    pairs.append((job_name, str(full.get("name")), str(later.get("name"))))
    return pairs


def _all_pairs() -> list[tuple[str, str, str, str]]:
    found = []
    for directory in WORKFLOW_DIRS:
        for path in sorted(directory.glob("*.yml")):
            workflow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for job, full, later in clobbering_pairs(workflow):
                found.append((str(path.relative_to(ROOT)), job, full, later))
    return found


def test_no_workflow_clobbers_its_own_full_checkout() -> None:
    offenders = [
        f"{path}: job {job!r}: {later!r} follows {full!r}"
        for path, job, full, later in _all_pairs()
        if (path, job) not in INTENTIONAL
    ]
    assert offenders == [], "\n".join(offenders)


def test_intentional_replacements_are_still_present() -> None:
    """An allowlist entry that matches nothing any more is dead weight that would hide the next real case."""
    present = {(path, job) for path, job, _full, _later in _all_pairs()}
    assert set(INTENTIONAL) <= present, sorted(set(INTENTIONAL) - present)


def test_detector_flags_the_guard_shape_and_ignores_exclusive_pairs() -> None:
    guard_shape = {
        "jobs": {
            "guard": {
                "steps": [
                    {"name": "Checkout repository", "uses": "actions/checkout@v7"},
                    {
                        "name": "Checkout retry helpers",
                        "uses": "actions/checkout@v7",
                        "with": {"sparse-checkout": ".github/scripts/x.js"},
                    },
                ]
            }
        }
    }
    assert clobbering_pairs(guard_shape) == [
        ("guard", "Checkout repository", "Checkout retry helpers")
    ]

    exclusive = {
        "jobs": {
            "ci": {
                "steps": [
                    {"name": "full", "uses": "actions/checkout@v7", "if": "inputs.dir == ''"},
                    {
                        "name": "sparse",
                        "uses": "actions/checkout@v7",
                        "if": "inputs.dir != ''",
                        "with": {"sparse-checkout": "src"},
                    },
                ]
            }
        }
    }
    own_path = {
        "jobs": {
            "ci": {
                "steps": [
                    {"name": "full", "uses": "actions/checkout@v7"},
                    {
                        "name": "helpers",
                        "uses": "actions/checkout@v7",
                        "with": {"sparse-checkout": "src", "path": ".helpers"},
                    },
                ]
            }
        }
    }
    other_repository = {
        "jobs": {
            "ci": {
                "steps": [
                    {"name": "full", "uses": "actions/checkout@v7"},
                    {
                        "name": "helpers",
                        "uses": "actions/checkout@v7",
                        "with": {"sparse-checkout": "src", "repository": "owner/other"},
                    },
                ]
            }
        }
    }
    assert clobbering_pairs(exclusive) == []
    assert clobbering_pairs(own_path) == []
    # `repository` chooses what is checked out, not where: another repository into the root replaces it too
    assert clobbering_pairs(other_repository) == [("ci", "full", "helpers")]


def test_guard_job_keeps_the_script_it_runs() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "maint-coverage-guard.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["guard"]
    runs = [str(step.get("run", "")) for step in job["steps"]]
    assert any("tools/coverage_guard.py" in run for run in runs)
    root_checkouts = [step for step in _checkouts(job) if _into_workspace_root(step)]
    assert len(root_checkouts) == 1 and not _is_sparse(root_checkouts[0])
