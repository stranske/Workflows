"""Hosted keepalive prompts carry the pre-push check and the lean-delivery rule (owner decision 2026-11-18).

Wave 2 of the 2026-11-16 design review: 28 of 59 agent PRs were red at some commit, about 15 of them on
lint, format or type checks the agent could have run first; delivered PRs carried 500-600 line
verification documents. Both prompt copies (this repo's and the consumer template) must say so.
"""

from pathlib import Path

import pytest

PROMPTS = [
    Path(".github/codex/prompts/keepalive_next_task.md"),
    Path("templates/consumer-repo/.github/codex/prompts/keepalive_next_task.md"),
]


@pytest.mark.parametrize("prompt", PROMPTS, ids=lambda p: str(p))
def test_keepalive_prompt_requires_repo_checks_before_push_and_lean_delivery(prompt):
    text = prompt.read_text(encoding="utf-8")
    assert text.count("## Before Every Push: Run This Repo's Own Checks") == 1
    assert text.count("Do not push a commit you know is red") == 1
    assert text.count("## Keep The Delivery To Code And Tests") == 1
    assert text.count("`docs/evidence/`") == 1
    assert text.count("deliberate-break result in the PR body") == 1
