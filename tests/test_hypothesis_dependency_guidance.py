"""Keep the canonical dependency examples from classifying test tools as runtime."""

import re
from pathlib import Path

import pytest

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


def test_regression_discriminates_original_and_fixed_guidance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise both canonical checks without mutating the repository guidance."""
    guidance_path = tmp_path / "guidance.env"
    original = (
        "# Runtime dependencies (PyYAML, Pydantic, Hypothesis) should be managed via Dependabot\n"
        "# in each consumer repo's pyproject.toml directly, NOT synced from this file.\n"
    )
    fixed = original.replace("PyYAML, Pydantic, Hypothesis", "PyYAML, Pydantic") + (
        "# Hypothesis is a test dependency and belongs in each consumer repo's test/dev extras.\n"
    )
    monkeypatch.setitem(globals(), "GUIDANCE_PATH", guidance_path)

    fixed_bytes = fixed.encode("utf-8")
    guidance_path.write_bytes(fixed_bytes)
    test_canonical_runtime_example_excludes_hypothesis()
    test_canonical_guidance_explains_hypothesis_is_a_test_dependency()

    guidance_path.write_text(original, encoding="utf-8")
    try:
        with pytest.raises(AssertionError, match="Hypothesis is a test dependency, not runtime"):
            test_canonical_runtime_example_excludes_hypothesis()
        with pytest.raises(
            AssertionError, match="must explain that Hypothesis is a test dependency"
        ):
            test_canonical_guidance_explains_hypothesis_is_a_test_dependency()
    finally:
        guidance_path.write_bytes(fixed_bytes)

    assert guidance_path.read_bytes() == fixed_bytes
    test_canonical_runtime_example_excludes_hypothesis()
    test_canonical_guidance_explains_hypothesis_is_a_test_dependency()
