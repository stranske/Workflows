"""Single-runtime coverage defaults for first-party Gate workflows."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
GATE_PATHS = (
    ROOT / ".github/workflows/pr-00-gate.yml",
    ROOT / "templates/consumer-repo/.github/workflows/pr-00-gate.yml",
)


def _coverage_reference_runtime(gate_text: str) -> str:
    match = re.search(r"COVERAGE_REFERENCE_RUNTIME:\s*['\"]([0-9.]+)['\"]", gate_text)
    if not match:
        raise AssertionError("COVERAGE_REFERENCE_RUNTIME not found in gate workflow")
    return match.group(1)


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
    assert primary == coverage == reference, (
        f"{gate_path}: primary={primary}, coverage={coverage}, reference={reference}"
    )


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
