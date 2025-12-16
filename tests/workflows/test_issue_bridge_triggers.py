"""
Tests for Issue Bridge workflow trigger conditions.

Ensures that the Issue Bridge workflow correctly triggers when:
1. An issue is created with the agent:codex label
2. An issue is reopened with the agent:codex label
3. The agent:codex label is added to an existing issue
4. An agent:* label is removed from an issue (unlabeled event)
"""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml


class TestIssueBridgeTriggers(unittest.TestCase):
    """Validate Issue Bridge workflow trigger conditions."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.project_root = Path(__file__).resolve().parents[2]
        cls.workflows_dir = cls.project_root / ".github" / "workflows"
        cls.intake_workflow = cls.workflows_dir / "agents-63-issue-intake.yml"

    def _load_workflow(self) -> dict:
        """Load the intake workflow YAML."""
        self.assertTrue(
            self.intake_workflow.exists(),
            "agents-63-issue-intake.yml must exist",
        )
        return yaml.safe_load(self.intake_workflow.read_text(encoding="utf-8"))

    def test_workflow_listens_for_issue_events(self) -> None:
        """Ensure workflow has 'issues' trigger configured."""
        data = self._load_workflow()
        # PyYAML may parse 'on' as boolean True
        triggers = data.get("on", data.get(True, {}))
        self.assertIn(
            "issues",
            triggers,
            "Workflow must listen for issue events",
        )

    def test_workflow_triggers_on_opened_labeled_reopened_unlabeled(self) -> None:
        """Ensure workflow triggers on opened, labeled, reopened, and unlabeled events."""
        data = self._load_workflow()
        # PyYAML may parse 'on' as boolean True
        triggers = data.get("on", data.get(True, {}))
        issue_trigger = triggers.get("issues", {})
        types = set(issue_trigger.get("types", []))

        required_types = {"opened", "labeled", "reopened", "unlabeled"}
        self.assertTrue(
            required_types.issubset(types),
            f"Workflow must trigger on {required_types}, got {types}",
        )

    def test_normalize_job_has_correct_condition(self) -> None:
        """Ensure normalize_inputs job has correct trigger condition."""
        data = self._load_workflow()
        jobs = data.get("jobs", {})
        normalize_job = jobs.get("normalize_inputs", {})

        self.assertIn(
            "if",
            normalize_job,
            "normalize_inputs job must have a condition",
        )

        condition = normalize_job["if"]
        self.assertIsInstance(
            condition,
            str,
            "Job condition must be a string",
        )

        # Remove whitespace and newlines for easier checking
        clean_condition = " ".join(condition.split())

        # Check that condition handles non-issue events
        self.assertIn(
            "github.event_name != 'issues'",
            clean_condition,
            "Condition must allow non-issue events (workflow_dispatch/workflow_call)",
        )

        # Check that condition checks the issue's labels array
        self.assertIn(
            "github.event.issue.labels",
            clean_condition,
            "Condition must check the issue's labels array",
        )

        # Check that condition checks for agent: prefix (any agent label)
        self.assertIn(
            "agent:",
            clean_condition,
            "Condition must check for agent: prefix to match any agent label",
        )

    def test_condition_handles_opened_with_agent_label(self) -> None:
        """Ensure condition checks issue labels for all issue events."""
        text = self.intake_workflow.read_text(encoding="utf-8")

        # The condition should check the issue's labels array for ALL issue events
        # This ensures that even if a different label triggers the workflow,
        # it will still run if ANY agent:* label is present in the issue's labels
        self.assertIn(
            "github.event.issue.labels",
            text,
            "Condition must check issue labels for all issue events",
        )

    def test_condition_handles_unlabeled_correctly(self) -> None:
        """Ensure condition properly handles 'unlabeled' events for agent:* labels."""
        # Get the normalize_inputs job condition
        data = self._load_workflow()
        jobs = data.get("jobs", {})
        normalize_job = jobs.get("normalize_inputs", {})
        condition = normalize_job.get("if", "")

        # Clean up whitespace
        clean_condition = " ".join(str(condition).split())

        # The condition SHOULD include unlabeled check with agent:* guard
        self.assertIn(
            "github.event.action == 'unlabeled'",
            clean_condition,
            "Condition must include unlabeled event handling",
        )

        # And it must check that the label being removed starts with 'agent:'
        self.assertIn(
            "startsWith(github.event.label.name, 'agent:')",
            clean_condition,
            "Condition must verify the unlabeled event is for an agent:* label",
        )

    def test_condition_logic_structure(self) -> None:
        """Validate the logical structure of the condition."""
        data = self._load_workflow()
        jobs = data.get("jobs", {})
        normalize_job = jobs.get("normalize_inputs", {})
        condition = normalize_job.get("if", "")

        # Clean up for easier parsing
        clean_condition = " ".join(str(condition).split())

        # The simplified condition should have this structure:
        # (not issues) OR (issue has agent:* label)
        #
        # This means ANY issue event will trigger if the issue has any agent:* label,
        # regardless of which specific label triggered the event.
        # This handles the case where multiple labels are added simultaneously
        # and a different label (like agents:keepalive) triggers the workflow.
        # It also generalizes to support agent:codex, agent:claude, etc.

        # Check for OR operator
        self.assertIn(
            "||",
            clean_condition,
            "Condition should have an OR operator separating the two cases",
        )

    def test_chatgpt_sync_issues_format_works(self) -> None:
        """
        Ensure issues created by chatgpt_sync (which don't initially have
        agent labels) can be processed when an agent label is manually added.
        """
        # chatgpt_sync creates issues WITHOUT agent labels, per PR #3090
        # Users then manually add agent:codex, agent:claude, etc. from the Issues tab
        # ANY labeled event will trigger the workflow, and it will proceed
        # if ANY agent:* label is present in the issue's labels array

        data = self._load_workflow()
        jobs = data.get("jobs", {})
        normalize_job = jobs.get("normalize_inputs", {})
        condition = normalize_job.get("if", "")

        # Verify the condition checks the issue's labels array
        self.assertIn(
            "github.event.issue.labels",
            condition,
            "Condition must check issue.labels array for agent:* label presence",
        )

    def test_condition_supports_any_agent_label(self) -> None:
        """Ensure condition works with any agent:* label (codex, claude, etc.)."""
        data = self._load_workflow()
        jobs = data.get("jobs", {})
        normalize_job = jobs.get("normalize_inputs", {})
        condition = normalize_job.get("if", "")

        # The condition should check for 'agent:' prefix, not a specific agent
        self.assertIn(
            "agent:",
            condition,
            "Condition must check for agent: prefix to support any agent label",
        )

        # Should NOT hard-code a specific agent name
        self.assertNotIn(
            "agent:codex",
            condition,
            "Condition should not hard-code agent:codex, use prefix instead",
        )


if __name__ == "__main__":
    unittest.main()
