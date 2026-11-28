"""Cohesion review B16: one actionlint version pin.

Workflow lint runs in Health 42 and Maint 52, which each pinned actionlint
separately. Both now load .github/config/workflow-linters.env; the devcontainer
and the docs must name the same version.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PIN_FILE = ROOT / ".github" / "config" / "workflow-linters.env"
WORKFLOWS = ROOT / ".github" / "workflows"
LITERAL = re.compile(r"actionlint[_/-]v?\d+\.\d+\.\d+|ACTIONLINT_VERSION\s*[:=]\s*['\"]?\d")


def _pin() -> str:
    pins = [
        line.split("=", 1)[1].strip()
        for line in PIN_FILE.read_text(encoding="utf-8").splitlines()
        if line.startswith("ACTIONLINT_VERSION=")
    ]
    assert len(pins) == 1, pins
    assert re.fullmatch(r"\d+\.\d+\.\d+", pins[0]), pins[0]
    return pins[0]


def test_no_workflow_carries_its_own_actionlint_version():
    offenders = [
        f"{path.name}:{n}"
        for path in sorted(WORKFLOWS.glob("*.yml"))
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if LITERAL.search(line) and not line.lstrip().startswith("#")
    ]
    assert offenders == [], offenders


def test_lint_workflows_load_the_shared_pin_before_installing():
    for name in ("health-42-actionlint.yml", "maint-52-validate-workflows.yml"):
        (job,) = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))["jobs"].values()
        names = [step.get("name", step.get("uses", "")) for step in job["steps"]]
        load = names.index("Load the shared actionlint pin")
        assert ".github/config/workflow-linters.env" in job["steps"][load]["run"]
        assert '>> "$GITHUB_ENV"' in job["steps"][load]["run"]
        assert "ACTIONLINT_VERSION" not in (job.get("env") or {})
        uses_pin = [
            i
            for i, step in enumerate(job["steps"])
            if "ACTIONLINT_VERSION" in str(step.get("run", "")) + str(step.get("with", ""))
            and i != load
        ]
        assert uses_pin and min(uses_pin) > load, (name, uses_pin, load)
        checkout = next(i for i, n in enumerate(names) if "checkout" in str(n).lower())
        assert checkout < load


def test_devcontainer_and_docs_name_the_pinned_version():
    pin = _pin()
    devcontainer = (ROOT / ".devcontainer" / "devcontainer.json").read_text(encoding="utf-8")
    assert set(re.findall(r"actionlint_(\d+\.\d+\.\d+)_", devcontainer)) == {pin}
    assert f"/v{pin}/" in devcontainer
    docs = (ROOT / "docs" / "ci" / "WORKFLOW_SYSTEM.md").read_text(encoding="utf-8")
    assert f"use Actionlint {pin}, pinned once in" in docs


def test_pin_line_survives_the_workflow_loader_filter():
    # The workflows append only lines matching this filter to GITHUB_ENV.
    loader = re.compile(r"^[A-Z_]+=[^\s]+$")
    lines = [
        line for line in PIN_FILE.read_text(encoding="utf-8").splitlines() if loader.match(line)
    ]
    assert lines == [f"ACTIONLINT_VERSION={_pin()}"]
