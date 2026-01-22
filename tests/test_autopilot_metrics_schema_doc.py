from pathlib import Path


def test_autopilot_metrics_schema_cycle_fields_documented() -> None:
    content = Path("docs/ci/AUTOPILOT_METRICS_SCHEMA.md").read_text(encoding="utf-8")
    required_markers = (
        "cycle_event",
        "summary",
        "outcome",
        "When `summary` is `true`, `outcome` is required.",
        "Example (summary):",
    )
    for marker in required_markers:
        assert marker in content, f"Missing cycle schema detail: {marker}"
