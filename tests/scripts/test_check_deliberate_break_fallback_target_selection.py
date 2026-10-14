"""Fallback proof metadata must select an implementation file, not an empty token."""

import runpy
import sys
from pathlib import Path

import pytest


@pytest.fixture(params=["", "templates/consumer-repo/"], ids=["root", "template"])
def helper(request):
    root = Path(__file__).resolve().parents[2]
    return runpy.run_path(str(root / request.param / "scripts/check_deliberate_break.py"))


@pytest.mark.parametrize("kind", ["blank-target", "yaml-target"])
def test_fallback_selects_the_implementation_target(helper, kind):
    break_line = (
        "Deliberate-break: reverting `   `, then use the implementation from context."
        if kind == "blank-target"
        else "Deliberate-break: revert the implementation to its previous behavior."
    )
    body = (
        "## Scope\nImplementation: `config/policy.yaml`.\n\n"
        "## Acceptance Criteria\n"
        "- [ ] Named test: `tests/test_proof.py` with `test_policy`.\n"
        f"- [ ] {break_line}\n"
    )
    spec = helper["parse_deliberate_break_spec"](body)
    assert spec is not None
    assert spec.break_file == "config/policy.yaml"
    assert spec.test_file == "tests/test_proof.py"
    assert spec.test_id == "tests/test_proof.py::test_policy"
    assert spec.command == (
        sys.executable,
        "-m",
        "pytest",
        "tests/test_proof.py::test_policy",
        "-o",
        "addopts=",
        "-q",
    )
