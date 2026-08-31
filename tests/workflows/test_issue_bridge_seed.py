"""
Regression tests for issue-bridge bootstrap seeding and empty-diff PR guard.

Issue: stranske/Workflows#3295
"""

from __future__ import annotations

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
        cls.assertTrue(cls.bridge_workflow.exists(), "issue-bridge workflow must exist")
        cls.workflow = yaml.safe_load(cls.bridge_workflow.read_text(encoding="utf-8"))
        cls.bridge_steps = cls.workflow["jobs"]["bridge"]["steps"]

    def _step_by_id(self, step_id: str) -> dict:
        for step in self.bridge_steps:
            if isinstance(step, dict) and step.get("id") == step_id:
                return step
        self.fail(f"step id={step_id!r} not found in bridge job")

    def _step_by_name(self, name: str) -> dict:
        for step in self.bridge_steps:
            if isinstance(step, dict) and step.get("name") == name:
                return step
        self.fail(f"step name={name!r} not found in bridge job")

    def test_mk_step_marker_includes_run_unique_token(self) -> None:
        """Bootstrap marker content must include a run-unique token (parsed via YAML)."""
        mk = self._step_by_id("mk")
        run = mk.get("run") or ""
        self.assertIsInstance(run, str)
        self.assertIn(
            'RUN_TOKEN="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-0}"',
            run,
            "mk step must define a run-unique RUN_TOKEN",
        )
        self.assertIn(
            'printf "<!-- bootstrap for %s on issue #%s run:%s -->\\n"',
            run,
            "mk step printf must embed run token in marker content",
        )
        self.assertIn('"$RUN_TOKEN"', run, "mk step must pass RUN_TOKEN into marker content")
        # Constant-only marker (no run token) must not be the printf format.
        self.assertNotIn(
            'printf "<!-- bootstrap for %s on issue #%s -->\\n"',
            run,
            "mk step must not use constant marker content without a run-unique component",
        )

    def test_create_mode_guards_pulls_create_with_ahead_by_check(self) -> None:
        """Create-mode script must guard pulls.create behind an ahead-of-base check."""
        step = self._step_by_name("Open or reuse PR (create mode)")
        script = (step.get("with") or {}).get("script") or ""
        self.assertIsInstance(script, str)
        self.assertIn("compareCommits", script, "create-mode must compare head vs base")
        self.assertIn("ahead_by", script, "create-mode must inspect ahead_by")
        create_idx = script.find("pulls.create")
        ahead_idx = script.find("ahead_by")
        self.assertGreater(create_idx, 0, "pulls.create must be present in create mode")
        self.assertGreater(ahead_idx, 0, "ahead_by guard must be present in create mode")
        self.assertLess(
            ahead_idx,
            create_idx,
            "ahead_by guard must appear before pulls.create",
        )
        self.assertIn(
            "Skipped pulls.create",
            script,
            "create-mode must report non-crashing skip when ahead_by is zero",
        )
        self.assertIn(
            "core.summary.addRaw",
            script,
            "create-mode must write a step summary on the skip path",
        )
        self.assertIn(
            "issues.createComment",
            script,
            "create-mode must comment on the issue on the skip path",
        )

    def test_reuse_path_seeds_when_branch_not_ahead_of_base(self) -> None:
        """Reuse path must seed when an existing branch has zero commits over base."""
        mk = self._step_by_id("mk")
        run = mk.get("run") or ""
        self.assertIn(
            "Reused branch has no commits ahead of",
            run,
            "reuse path must detect empty branch relative to base",
        )
        self.assertIn("seed_bootstrap_marker", run, "reuse path must call shared seed helper")
        self.assertIn(
            'if [ "${AHEAD:-0}" -eq 0 ]; then',
            run,
            "reuse path must gate seeding on ahead-of-base count",
        )


if __name__ == "__main__":
    unittest.main()
