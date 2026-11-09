"""Lock Gate's parallel pytest invocation: two calls, one full suite.

The verifier grammar suites run in their own Gate call (python-ci-grammar) so that
neither Python job exceeds the 10-minute CI budget (Workflows#3904). python-ci must
ignore exactly the files python-ci-grammar runs; any other path, marker or
deselection would narrow what the Gate tests.
"""

import shlex
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEDULING = ["-n", "auto", "--dist", "load"]


def _jobs() -> dict:
    return yaml.safe_load((ROOT / ".github/workflows/pr-00-gate.yml").read_text())["jobs"]


def grammar_files() -> list[str]:
    """The test files the python-ci-grammar call runs, in workflow order."""
    args = shlex.split(_jobs()["python-ci-grammar"]["with"]["pytest_args"])
    assert args[: len(SCHEDULING)] == SCHEDULING
    return args[len(SCHEDULING) :]


def test_gate_pytest_args_are_parallel() -> None:
    inputs = _jobs()["python-ci"]["with"]
    args = shlex.split(inputs["pytest_args"])
    assert args[: len(SCHEDULING)] == SCHEDULING
    # Only scheduling flags plus the grammar split: no other paths, markers or deselection.
    assert args[len(SCHEDULING) :] == [f"--ignore={path}" for path in grammar_files()]
    assert inputs["coverage-min"] == "70"


def test_grammar_call_partitions_the_full_suite() -> None:
    jobs = _jobs()
    files = grammar_files()
    assert files, "python-ci-grammar must run at least one file"
    assert len(set(files)) == len(files)
    for path in files:
        assert (ROOT / path).is_file(), f"{path} is listed but missing"
        assert path.startswith("tests/") and path.endswith(".py")
    main, grammar = jobs["python-ci"], jobs["python-ci-grammar"]
    assert grammar["if"] == main["if"]
    assert grammar["needs"] == main["needs"]
    for key in ("python-versions", "pytest-workers", "marker", "pytest_markers", "workflows_ref"):
        assert grammar["with"][key] == main["with"][key], key
    # Coverage stays on python-ci; the grammar call must not publish into gate-*.
    assert grammar["with"]["coverage"] is False
    assert not grammar["with"]["artifact-prefix"].startswith("gate-")
    assert "python-ci-grammar" in jobs["summary"]["needs"]
    summarize = next(
        step for step in jobs["summary"]["steps"] if step.get("name") == "Summarize results"
    )
    assert "needs.python-ci-grammar.result == 'failure'" in summarize["env"]["PYTHON_RESULT"]
