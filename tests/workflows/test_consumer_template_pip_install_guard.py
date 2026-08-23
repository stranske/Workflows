"""A consumer-template workflow must not run a bare editable install.

A consumer repo is not required to be an installable Python package: the
template ships no ``pyproject.toml``, and at least one live consumer
(``stranske/Orchestrator``) is a set of flat root modules with no packaging
metadata at all. On such a repo an unguarded ``pip install -e .`` exits 1 and
takes its job down with it.

That is not a cosmetic failure. ``backplane-conformance.yml`` documents itself
as opt-in ("Until then the gate skips harmlessly") and its ``conformance`` job
is wired ``needs: emit-reference-run``, so an install failure in the emitter
turned the advertised skip into a hard red gate on every PR touching
``scripts/**`` or ``docs/contracts/**``.

These workflows are overwrite-synced from ``templates/consumer-repo`` (the
manifest entry for ``backplane-conformance.yml`` carries no ``sync_mode``), so a
fix applied in a consumer would be reverted on the next sync. The guard has to
live in the template, and this test keeps it there.
"""

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_WORKFLOWS = REPO_ROOT / "templates" / "consumer-repo" / ".github" / "workflows"

# Editable install in any of the forms the fleet uses: `pip install -e .`,
# `pip install -e ".[langchain]" --quiet`, `python -m pip install -e ".[dev]"`,
# `uv pip install -e .`. Flags may precede `-e`.
EDITABLE_INSTALL = re.compile(r"\bpip\s+install\b[^\n]*?\s-e\b")

# A shell existence test for packaging metadata: `[ -f pyproject.toml ]`,
# `[ -e setup.py ]`, `test -f setup.cfg`.
PACKAGING_GUARD = re.compile(
    r"(?:\[\[?\s*-[fe]\s+|\btest\s+-[fe]\s+)(?:\./)?(?:pyproject\.toml|setup\.py|setup\.cfg)\b"
)

# Every editable install currently in the template. A floor, so this test cannot
# pass vacuously if the workflows are renamed, restructured or stop being found:
# a silently-empty scan is indistinguishable from a pass otherwise.
EXPECTED_INSTALL_SITES = {
    "agents-auto-label.yml",
    "agents-capability-check.yml",
    "agents-decompose.yml",
    "agents-dedup.yml",
    "backplane-conformance.yml",
}


def _run_scripts(workflow_text):
    """Yield every ``run:`` script in a workflow, with its job and step index."""
    document = yaml.safe_load(workflow_text)
    if not isinstance(document, dict):
        return
    for job_name, job in (document.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for index, step in enumerate(job.get("steps") or []):
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                yield job_name, index, step["run"]


def _template_workflows():
    return sorted(TEMPLATE_WORKFLOWS.glob("*.yml")) + sorted(TEMPLATE_WORKFLOWS.glob("*.yaml"))


def test_template_workflow_directory_is_present():
    """Guard the guard: a moved template directory must not read as "all clear"."""
    assert TEMPLATE_WORKFLOWS.is_dir(), f"{TEMPLATE_WORKFLOWS} is missing"
    assert _template_workflows(), f"no workflow files found under {TEMPLATE_WORKFLOWS}"


def test_no_unguarded_editable_install_in_consumer_template():
    unguarded = []
    scanned = set()

    for path in _template_workflows():
        for job_name, index, script in _run_scripts(path.read_text(encoding="utf-8")):
            install = EDITABLE_INSTALL.search(script)
            if not install:
                continue
            scanned.add(path.name)

            guard = PACKAGING_GUARD.search(script)
            if guard is None:
                reason = "no packaging-file guard in the same run block"
            elif install.start() < guard.start():
                # A guard that only appears after the install (e.g. in a later
                # branch) never protects it.
                reason = "editable install runs before the packaging-file guard"
            else:
                continue

            unguarded.append(f"{path.name}: jobs.{job_name}.steps[{index}] - {reason}")

    assert not unguarded, (
        "consumer-template workflows run a bare `pip install -e` with no packaging-file "
        "guard; on a consumer with no pyproject.toml/setup.py/setup.cfg these exit 1 and "
        "fail the job:\n  " + "\n  ".join(unguarded)
    )

    # The floor: if an expected site stopped being scanned, the assertion above
    # passed because it checked nothing there.
    missing = EXPECTED_INSTALL_SITES - scanned
    assert not missing, (
        "expected editable-install sites were not scanned (renamed, restructured, or the "
        f"install was removed): {sorted(missing)}. Update EXPECTED_INSTALL_SITES "
        "deliberately if the change was intended."
    )


def test_backplane_conformance_stub_keeps_its_opt_in_promise():
    """The stub's header promises a harmless skip; its emitter job must honour it."""
    workflow = (TEMPLATE_WORKFLOWS / "backplane-conformance.yml").read_text(encoding="utf-8")

    # The promise itself, so the test fails loudly if the claim is ever reworded
    # away instead of the behaviour being fixed.
    assert "Until then the gate skips harmlessly." in workflow

    scripts = [script for _, _, script in _run_scripts(workflow)]
    install_scripts = [s for s in scripts if EDITABLE_INSTALL.search(s)]
    assert len(install_scripts) == 1, "expected exactly one editable-install step"

    script = install_scripts[0]
    assert PACKAGING_GUARD.search(script), "the editable install is not guarded"
    for filename in ("pyproject.toml", "setup.py", "setup.cfg"):
        assert filename in script, f"guard does not consider {filename}"
