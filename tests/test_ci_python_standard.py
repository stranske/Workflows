"""Single-runtime coverage defaults for first-party Gate workflows."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
GATE_PATHS = (
    ROOT / ".github/workflows/pr-00-gate.yml",
    ROOT / "templates/consumer-repo/.github/workflows/pr-00-gate.yml",
)


def _coverage_reference_runtime(gate_text: str) -> str:
    data = yaml.safe_load(gate_text)
    steps = data["jobs"]["summary"]["steps"]
    coverage_stats = next((step for step in steps if step.get("id") == "coverage_stats"), None)
    if coverage_stats is None:
        raise AssertionError("coverage_stats step not found in gate workflow")
    try:
        return str(coverage_stats["env"]["COVERAGE_REFERENCE_RUNTIME"])
    except KeyError as exc:
        raise AssertionError(
            "COVERAGE_REFERENCE_RUNTIME not found in coverage_stats environment"
        ) from exc


def _python_ci_runtime_inputs(gate_path: Path) -> tuple[str, str]:
    data = yaml.safe_load(gate_path.read_text(encoding="utf-8"))
    inputs = data["jobs"]["python-ci"]["with"]
    primary = inputs["primary-python-version"]
    coverage = inputs["coverage-python-version"]
    return str(primary), str(coverage)


def assert_coverage_runtime_aligned(gate_path: Path, gate_text: str | None = None) -> None:
    """Require primary, coverage, and reference runtimes to match."""
    text = gate_text if gate_text is not None else gate_path.read_text(encoding="utf-8")
    primary, coverage = _python_ci_runtime_inputs(gate_path)
    reference = _coverage_reference_runtime(text)
    assert (
        primary == coverage == reference
    ), f"{gate_path}: primary={primary}, coverage={coverage}, reference={reference}"


@pytest.mark.parametrize("gate_path", GATE_PATHS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_coverage_runtime_is_the_primary_runtime(gate_path: Path) -> None:
    assert_coverage_runtime_aligned(gate_path)


def test_mismatched_coverage_reference_runtime_fails_alignment() -> None:
    """Deliberate-break guard: COVERAGE_REFERENCE_RUNTIME must match primary/coverage inputs."""
    gate_path = GATE_PATHS[0]
    text = gate_path.read_text(encoding="utf-8").replace(
        "COVERAGE_REFERENCE_RUNTIME: '3.14'",
        "COVERAGE_REFERENCE_RUNTIME: '3.13'",
    )
    with pytest.raises(AssertionError, match="reference=3.13"):
        assert_coverage_runtime_aligned(gate_path, text)


@pytest.mark.parametrize("gate_path", GATE_PATHS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_reference_runtime_reads_the_effective_coverage_step(gate_path: Path) -> None:
    data = yaml.safe_load(gate_path.read_text(encoding="utf-8"))
    coverage_stats = next(
        step for step in data["jobs"]["summary"]["steps"] if step.get("id") == "coverage_stats"
    )
    coverage_stats["env"]["COVERAGE_REFERENCE_RUNTIME"] = "3.13"
    # An unrelated earlier declaration must not mask a drifted effective value.
    text = yaml.safe_dump({"env": {"COVERAGE_REFERENCE_RUNTIME": "3.14"}, **data}, sort_keys=False)
    with pytest.raises(AssertionError, match="reference=3.13"):
        assert_coverage_runtime_aligned(gate_path, text)
