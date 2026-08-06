from pathlib import Path

import yaml

WORKFLOWS = (
    Path(".github/workflows/agents-auto-label.yml"),
    Path("templates/consumer-repo/.github/workflows/agents-auto-label.yml"),
)


def _steps(path: Path) -> list[dict[str, object]]:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    return workflow["jobs"]["auto-label"]["steps"]


def test_auto_label_isolates_eligibility_sparse_checkout() -> None:
    for path in WORKFLOWS:
        steps = _steps(path)
        eligibility_checkout = next(
            step for step in steps if step.get("name") == "Checkout eligibility action"
        )
        eligibility = next(step for step in steps if step.get("name") == "Check event eligibility")

        assert eligibility_checkout["with"]["path"] == "eligibility-source", path
        assert (
            eligibility["uses"] == "./eligibility-source/.github/actions/agent-event-eligibility"
        ), path


def test_auto_label_full_checkout_keeps_workspace_root() -> None:
    for path in WORKFLOWS:
        steps = _steps(path)
        full_checkout = next(step for step in steps if step.get("name") == "Checkout repository")

        assert "path" not in full_checkout.get("with", {}), path
        assert any(step.get("uses") == "./.github/actions/setup-api-client" for step in steps), path
