"""Keep the canonical dependency examples from classifying test tools as runtime."""

import re
from pathlib import Path


def test_canonical_runtime_example_excludes_hypothesis() -> None:
    guidance_path = Path(__file__).resolve().parents[1] / ".github/workflows/autofix-versions.env"
    guidance = guidance_path.read_text(encoding="utf-8")
    runtime_examples = re.findall(
        r"^#\s*Runtime dependencies\s*\(([^)]*)\)", guidance, re.IGNORECASE | re.MULTILINE
    )

    assert runtime_examples, "Canonical guidance must retain its runtime dependency examples"
    for example in runtime_examples:
        dependencies = {dependency.strip().casefold() for dependency in example.split(",")}
        assert "hypothesis" not in dependencies, "Hypothesis is a test dependency, not runtime"
        assert {"pyyaml", "pydantic"} <= dependencies
