import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parents[2]


def test_evaluate_steps_export_every_provider_flag_the_loop_reads() -> None:
    keepalive_script = (REPO_ROOT / ".github/scripts/keepalive_loop.js").read_text(encoding="utf-8")
    required_flags = set(re.findall(r"process\.env\.(HAS_[A-Z0-9_]+)", keepalive_script))
    assert required_flags == {
        "HAS_CODEX_AUTH",
        "HAS_CLAUDE_AUTH",
        "HAS_CLAUDE_OAUTH",
        "HAS_CURSOR_AUTH",
        "HAS_GEMINI_AUTH",
        "HAS_MUSE_AUTH",
    }

    workflow_paths = (
        REPO_ROOT / "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml",
        REPO_ROOT / ".github/workflows/agents-keepalive-loop.yml",
    )
    for workflow_path in workflow_paths:
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        evaluate_steps = [
            step
            for job in workflow["jobs"].values()
            for step in job.get("steps", [])
            if "evaluateKeepaliveLoop(" in str((step.get("with") or {}).get("script", ""))
        ]
        assert len(evaluate_steps) == 1, (
            f"{workflow_path.relative_to(REPO_ROOT)} must contain exactly one "
            "evaluateKeepaliveLoop step"
        )
        exported_flags = set((evaluate_steps[0].get("env") or {}).keys())
        assert required_flags <= exported_flags, (
            f"{workflow_path.relative_to(REPO_ROOT)} is missing provider flags: "
            f"{sorted(required_flags - exported_flags)}"
        )


# First line of the keepalive instruction from .github/codex/prompts/keepalive_next_task.md
# The full instruction is multi-line; tests check that the instruction starts correctly.
DEFAULT_COMMAND_PREFIX = (
    "@codex Your objective is to satisfy the **Acceptance Criteria** by completing each "
    "**Task** within the defined **Scope**."
)
