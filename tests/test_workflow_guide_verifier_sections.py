from pathlib import Path


def test_workflow_guide_verifier_sections_present() -> None:
    content = Path("docs/WORKFLOW_GUIDE.md").read_text(encoding="utf-8")
    required_headers = (
        "## Verifier Workflow",
        "### How to trigger verification",
        "### What each mode does",
        "### Expected outputs",
        "### When to use each mode",
    )
    for header in required_headers:
        assert header in content, f"Missing section in WORKFLOW_GUIDE.md: {header}"

    for label in ("verify:checkbox", "verify:evaluate", "verify:compare"):
        assert label in content, f"Missing verifier label in WORKFLOW_GUIDE.md: {label}"

    expected_output_markers = (
        "Run summary",
        "PASS/FAIL",
        "Issue on failure",
        "Mode-specific report",
        "Actions run summary",
    )
    for marker in expected_output_markers:
        assert marker in content, f"Missing verifier output detail in WORKFLOW_GUIDE.md: {marker}"

    expected_usage_markers = (
        "Lightweight audit",
        "Higher-confidence validation",
        "Benchmarking or model selection",
    )
    for marker in expected_usage_markers:
        assert marker in content, f"Missing verifier usage detail in WORKFLOW_GUIDE.md: {marker}"
