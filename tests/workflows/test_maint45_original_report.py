import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/maint-45-cosmetic-repair.yml"
TARGET = "baseline[approved].py"


@pytest.mark.parametrize(
    ("case", "dry_run", "expected_status", "eligible"),
    [
        ("clean", False, "clean", False),
        ("cosmetic", True, "dry-run", False),
        ("cosmetic", False, "applied-no-pr", True),
        ("already-applied", False, "no-changes", False),
        ("ordinary", False, None, False),
        ("mixed", False, None, False),
        ("missing", False, None, False),
        ("empty", False, None, False),
        ("malformed", False, None, False),
        ("no-cases", False, None, False),
        ("inconsistent", False, None, False),
    ],
)
def test_maint45_uses_original_report(tmp_path, case, dry_run, expected_status, eligible):
    workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    job = workflow["jobs"]["repair"]
    steps = {step["name"]: step for step in job["steps"]}
    assert job["env"]["BASE_BRANCH"] == "${{ inputs['base-branch'] }}"
    assert steps["Checkout"]["with"]["ref"] == "${{ env.BASE_BRANCH }}"
    publisher = steps["Create cosmetic repair PR"]
    assert publisher["if"] == "steps.repair.outputs.add_paths != ''"
    assert publisher["with"]["base"] == steps["Checkout"]["with"]["ref"]
    assert sum(step.get("uses", "").startswith("peter-evans/") for step in steps.values()) == 1

    checkout = tmp_path / "checkout"
    (checkout / ".venv/bin").mkdir(parents=True)
    (checkout / ".venv/bin/python").symlink_to(sys.executable)
    (checkout / "scripts").mkdir()
    for name in ("ci_cosmetic_repair.py", "classify_test_failures.py"):
        shutil.copyfile(ROOT / "scripts" / name, checkout / "scripts" / name)
    target = checkout / TARGET
    initial = "1.23456" if case == "already-applied" else "1.23450"
    target.write_text(
        f"EXPECTED = {initial}  # cosmetic-repair: float EXPECTED\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q", "-b", "selected-base"], cwd=checkout, check=True)
    subprocess.run(["git", "add", "--", TARGET], cwd=checkout, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "base",
        ],
        cwd=checkout,
        check=True,
    )
    report = tmp_path / "pytest-report.xml"
    if case in {"empty", "malformed", "no-cases"}:
        report.write_text({"empty": "", "malformed": "<bad", "no-cases": "<testsuite/>"}[case])
    elif case != "missing":
        suite = ElementTree.Element("testsuite")
        test = ElementTree.SubElement(suite, "testcase", name="original")
        if case in {"cosmetic", "already-applied", "mixed"}:
            properties = ElementTree.SubElement(test, "properties")
            ElementTree.SubElement(properties, "property", name="markers", value="cosmetic")
            instruction = {"path": TARGET, "guard": "float", "key": "EXPECTED", "value": "1.23456"}
            ElementTree.SubElement(test, "failure").text = "COSMETIC_TOLERANCE " + json.dumps(
                instruction
            )
        if case in {"ordinary", "mixed"}:
            ordinary = ElementTree.SubElement(suite, "testcase", name="ordinary")
            ElementTree.SubElement(ordinary, "failure").text = "Runtime regression"
        ElementTree.ElementTree(suite).write(report)

    original = report.read_bytes() if report.exists() else None
    output = tmp_path / "outputs"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        ["bash", "-eo", "pipefail", "-c", steps["Run cosmetic repair on original report"]["run"]],
        cwd=checkout,
        env={
            **env,
            "PYTHONDONTWRITEBYTECODE": "1",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(output),
            "PYTEST_EXIT_CODE": "0" if case == "clean" else "1",
            "DRY_RUN": str(dry_run).lower(),
            "BASE_BRANCH": "selected-base",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert (report.read_bytes() if report.exists() else None) == original
    assert not (checkout / ".pytest-cosmetic-report.xml").exists()
    assert (result.returncode == 0) == (
        eligible or expected_status in {"clean", "dry-run"}
    ), result.stderr
    summary = checkout / ".cosmetic-repair-summary.json"
    assert (
        json.loads(summary.read_text())["status"] if summary.exists() else None
    ) == expected_status
    assert output.exists() == eligible
    assert ("1.23456" in target.read_text()) == (eligible or case == "already-applied")
    if eligible:
        other = checkout / "baselinea.py"
        other.write_text("Do not stage this unrelated path.\n", encoding="utf-8")
        (pathspec,) = output.read_text().splitlines()[1:-1]
        subprocess.run(["git", "add", "--", pathspec], cwd=checkout, check=True)
        names = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only"], cwd=checkout, text=True
        )
        assert names.splitlines() == [TARGET]
