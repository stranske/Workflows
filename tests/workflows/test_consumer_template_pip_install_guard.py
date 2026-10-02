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

import os
import re
import subprocess
from pathlib import Path

import pytest
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

LANGCHAIN_WORKFLOWS = (
    ".github/workflows/agents-auto-label.yml",
    ".github/workflows/agents-capability-check.yml",
    ".github/workflows/agents-decompose.yml",
    ".github/workflows/agents-dedup.yml",
    "templates/consumer-repo/.github/workflows/agents-auto-label.yml",
    "templates/consumer-repo/.github/workflows/agents-capability-check.yml",
    "templates/consumer-repo/.github/workflows/agents-decompose.yml",
    "templates/consumer-repo/.github/workflows/agents-dedup.yml",
)

PROJECT_METADATA_GUARD = re.compile(r"grep\s+-Eq\s+['\"]\^\\\[\(project\|build-system\)\\\]")


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


def _install_script(path: Path, marker: str) -> str:
    scripts = [script for _, _, script in _run_scripts(path.read_text(encoding="utf-8"))]
    matches = [script for script in scripts if marker in script]
    assert len(matches) == 1, f"expected one install script containing {marker!r} in {path}"
    return matches[0]


def _run_with_fake_python(script: str, tmp_path: Path, *, name: str, pyproject: str) -> list[str]:
    case = tmp_path / name
    tools = case / "tools"
    fake_bin = case / "bin"
    tools.mkdir(parents=True)
    fake_bin.mkdir()
    (case / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    (tools / "requirements-llm.txt").write_text("langchain==0\n", encoding="utf-8")
    fake_python = fake_bin / "python"
    fake_python.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$INSTALL_LOG"\n', encoding="utf-8")
    fake_python.chmod(0o755)
    log = case / "install.log"
    env = {
        **os.environ,
        "INSTALL_LOG": str(log),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }
    subprocess.run(["bash", "-eu", "-c", script], cwd=case, env=env, check=True)
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


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
    assert PROJECT_METADATA_GUARD.search(
        script
    ), "a tool-only pyproject.toml must not trigger an editable install"
    for filename in ("pyproject.toml", "setup.py", "setup.cfg"):
        assert filename in script, f"guard does not consider {filename}"


@pytest.mark.parametrize("workflow", LANGCHAIN_WORKFLOWS)
@pytest.mark.parametrize(
    ("pyproject", "expects_editable"),
    (("[tool.ruff]\nline-length = 100\n", False), ("[project]\nname = 'consumer'\n", True)),
    ids=("tool-only-pyproject", "project-without-langchain-extra"),
)
def test_langchain_install_uses_canonical_requirements_for_both_repo_shapes(
    workflow: str, pyproject: str, expects_editable: bool, tmp_path: Path
) -> None:
    path = REPO_ROOT / workflow
    script = _install_script(path, "tools/requirements-llm.txt")

    calls = _run_with_fake_python(
        script,
        tmp_path,
        name=workflow.replace("/", "-") + ("-project" if expects_editable else "-tool"),
        pyproject=pyproject,
    )

    assert "-m pip install -r tools/requirements-llm.txt --quiet" in calls
    assert any(call == "-m pip install -e . --quiet" for call in calls) is expects_editable
    assert all("[langchain]" not in call for call in calls)


@pytest.mark.parametrize(
    ("pyproject", "expects_editable"),
    (("[tool.ruff]\nline-length = 100\n", False), ("[build-system]\nrequires = []\n", True)),
    ids=("tool-only-pyproject", "build-system-project"),
)
def test_backplane_editable_install_requires_real_project_metadata(
    pyproject: str, expects_editable: bool, tmp_path: Path
) -> None:
    workflow = TEMPLATE_WORKFLOWS / "backplane-conformance.yml"
    script = _install_script(workflow, "pip install -e .")

    calls = _run_with_fake_python(
        script,
        tmp_path,
        name="backplane-project" if expects_editable else "backplane-tool",
        pyproject=pyproject,
    )

    assert any(call == "-m pip install -e ." for call in calls) is expects_editable
