from pathlib import Path


def test_workflow_guide_verifier_sections_present() -> None:
    content = Path("docs/WORKFLOW_GUIDE.md").read_text(encoding="utf-8")
    required_headers = (
        "## Verifier Workflow",
        "### How to trigger verification",
        "### Modes and outputs",
        "### When to use each mode",
    )
    for header in required_headers:
        assert header in content, f"Missing section in WORKFLOW_GUIDE.md: {header}"

    for label in ("verify:checkbox", "verify:evaluate", "verify:compare"):
        assert label in content, f"Missing verifier label in WORKFLOW_GUIDE.md: {label}"
