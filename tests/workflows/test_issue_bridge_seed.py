"""
Regression tests for issue-bridge bootstrap seeding and empty-diff PR guard.

Issue: stranske/Workflows#3295
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml


class TestIssueBridgeSeed(unittest.TestCase):
    """Validate bootstrap marker run-uniqueness and ahead-of-base PR guard."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.project_root = Path(__file__).resolve().parents[2]
        cls.bridge_workflow = (
            cls.project_root / ".github" / "workflows" / "reusable-agents-issue-bridge.yml"
        )

    def _load_workflow_text(self) -> str:
        self.assertTrue(self.bridge_workflow.exists(), "issue-bridge workflow must exist")
        return self.bridge_workflow.read_text(encoding="utf-8")

    def test_mk_step_marker_includes_run_unique_token(self) -> None:
        """Bootstrap marker content must include a run-unique token."""
        text = self._load_workflow_text()
        self.assertIn("RUN_TOKEN=", text, "mk step must define RUN_TOKEN")
        self.assertIn(
            'printf "<!-- bootstrap for %s on issue #%s run:%s -->',
            text,
            "mk step printf must embed run token in marker content",
        )
        self.assertIn('"$RUN_TOKEN"', text, "mk step must pass RUN_TOKEN into marker content")

    def test_create_mode_guards_pulls_create_with_ahead_by_check(self) -> None:
        """Create-mode script must guard pulls.create behind an ahead-of-base check."""
        text = self._load_workflow_text()
        pr_step_start = text.find("Open or reuse PR (create mode)")
        self.assertGreater(pr_step_start, 0, "create-mode PR step must exist")
        pr_step = text[pr_step_start:]
        self.assertIn("compareCommits", pr_step, "create-mode must compare head vs base")
        self.assertIn("ahead_by", pr_step, "create-mode must inspect ahead_by")
        create_idx = pr_step.find("pulls.create")
        ahead_idx = pr_step.find("ahead_by")
        self.assertGreater(create_idx, 0, "pulls.create must be present in create mode")
        self.assertGreater(ahead_idx, 0, "ahead_by guard must be present in create mode")
        self.assertLess(
            ahead_idx,
            create_idx,
            "ahead_by guard must appear before pulls.create",
        )
        self.assertIn(
            "Skipped pulls.create",
            pr_step,
            "create-mode must report non-crashing skip when ahead_by is zero",
        )

    def test_reuse_path_seeds_when_branch_not_ahead_of_base(self) -> None:
        """Reuse path must seed when an existing branch has zero commits over base."""
        text = self._load_workflow_text()
        self.assertIn(
            "Reused branch has no commits ahead of",
            text,
            "reuse path must detect empty branch relative to base",
        )
        self.assertIn("seed_bootstrap_marker", text, "reuse path must call shared seed helper")


if __name__ == "__main__":
    unittest.main()
