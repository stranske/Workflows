"""Keep the canonical dependency examples from classifying test tools as runtime."""

import os
import re
import subprocess
import sys
from pathlib import Path

GUIDANCE_PATH = Path(__file__).resolve().parents[1] / ".github/workflows/autofix-versions.env"


def test_canonical_runtime_example_excludes_hypothesis() -> None:
    guidance = GUIDANCE_PATH.read_text(encoding="utf-8")
    runtime_examples = re.findall(
        r"^#\s*Runtime dependencies\s*\(([^)]*)\)", guidance, re.IGNORECASE | re.MULTILINE
    )

    assert runtime_examples, "Canonical guidance must retain its runtime dependency examples"
    for example in runtime_examples:
        dependencies = {dependency.strip().casefold() for dependency in example.split(",")}
        assert "hypothesis" not in dependencies, "Hypothesis is a test dependency, not runtime"
        assert {"pyyaml", "pydantic"} <= dependencies


def test_canonical_guidance_explains_hypothesis_is_a_test_dependency() -> None:
    guidance = GUIDANCE_PATH.read_text(encoding="utf-8")
    comments = " ".join(
        line.removeprefix("#").strip() for line in guidance.splitlines() if line.startswith("#")
    )

    assert re.search(
        r"\bHypothesis\s+is\s+a\s+test\s+dependency\b"
        r"|\bTest\s+dependencies\s*\([^)]*\bHypothesis\b",
        comments,
        re.IGNORECASE,
    ), "Canonical guidance must explain that Hypothesis is a test dependency"


def test_regression_discriminates_original_and_fixed_guidance(tmp_path: Path) -> None:
    """Run pytest against full-file copies without mutating protected guidance."""
    guidance_path = tmp_path / "guidance.env"
    canonical_bytes = GUIDANCE_PATH.read_bytes()
    original = re.sub(
        rb"(?m)^# Runtime dependencies \([^)]*\)",
        b"# Runtime dependencies (PyYAML, Pydantic, Hypothesis)",
        canonical_bytes,
    )
    fixed_bytes = original.replace(b"PyYAML, Pydantic, Hypothesis", b"PyYAML, Pydantic") + (
        b"# Hypothesis is a test dependency and belongs in each consumer repo's test/dev extras.\n"
    )

    # Copy the actual assertions, redirecting only their input to the isolated fixture.
    test_path = tmp_path / Path(__file__).name
    source = Path(__file__).read_text(encoding="utf-8")
    canonical_path_assignment = (
        "GUIDANCE_PATH = Path(__file__).resolve().parents[1] / "
        '".github/workflows/autofix-versions.env"'
    )
    assert canonical_path_assignment in source
    test_path.write_text(
        source.replace(
            canonical_path_assignment, 'GUIDANCE_PATH = Path(__file__).with_name("guidance.env")'
        ),
        encoding="utf-8",
    )
    command = [
        sys.executable,
        "-m",
        "pytest",
        test_path.name,
        "-q",
        "-m",
        "not slow",
        "-k",
        "test_canonical_runtime_example_excludes_hypothesis or "
        "test_canonical_guidance_explains_hypothesis_is_a_test_dependency",
    ]
    environment = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTEST_ADDOPTS": ""}

    def run_checks() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def pin_lines(contents: bytes) -> list[bytes]:
        return [line for line in contents.splitlines() if line and not line.startswith(b"#")]

    guidance_path.write_bytes(fixed_bytes)
    try:
        fixed_result = run_checks()
        assert fixed_result.returncode == 0, fixed_result.stdout + fixed_result.stderr
        assert "2 passed" in fixed_result.stdout

        guidance_path.write_bytes(original)
        original_result = run_checks()
        assert original_result.returncode == 1, original_result.stdout + original_result.stderr
        assert "Hypothesis is a test dependency, not runtime" in original_result.stdout
        assert "FAILED test_hypothesis_dependency_guidance.py::" in original_result.stdout
        assert pin_lines(guidance_path.read_bytes()) == pin_lines(canonical_bytes)
    finally:
        guidance_path.write_bytes(fixed_bytes)

    assert guidance_path.read_bytes() == fixed_bytes
    assert pin_lines(fixed_bytes) == pin_lines(canonical_bytes)
    restored_result = run_checks()
    assert restored_result.returncode == 0, restored_result.stdout + restored_result.stderr
    assert "2 passed" in restored_result.stdout
    assert GUIDANCE_PATH.read_bytes() == canonical_bytes
