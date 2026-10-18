"""Run authored comment steps with an offline GitHub CLI stand-in."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from scripts.langchain import pr_verifier

ROOT = Path(__file__).resolve().parents[2]


def step(name):
    workflow = yaml.load(
        (ROOT / ".github/workflows/reusable-agents-verifier.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    return next(item for item in workflow["jobs"]["verifier"]["steps"] if item.get("name") == name)


def execute_comment_step(tmp_path, authored, **env):
    (tmp_path / ".workflows-lib").symlink_to(ROOT, target_is_directory=True)
    gh = tmp_path / "gh"
    gh.write_text(
        '#!/bin/sh\n[ "$1 $2 $3 $4" = "pr comment 123 --body-file" ] || exit 9\ncat "$5" > posted.md\n'
    )
    gh.chmod(0o755)
    python = tmp_path / "python"
    python.write_text(f'#!/bin/sh\nexec {sys.executable} "$@"\n')
    python.chmod(0o755)
    return subprocess.run(
        ["bash", "-c", authored["run"]],
        cwd=tmp_path,
        env={**os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"], **env},
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("with_results", [True, False])
def test_verifier_coverage_blocked_posts_comparison(tmp_path, with_results):
    authored = step("Post comparison report comment")
    assert "has_results" not in authored["if"]
    assert "always()" in authored["if"]
    if with_results:
        result = pr_verifier.EvaluationResult(
            verdict="UNVERIFIABLE_INPUT",
            used_llm=False,
            summary="Required artifact retrieval unavailable",
            input_coverage={"files_total": 10, "files_complete": 0},
        )
        (tmp_path / "comparison.json").write_text(json.dumps({"results": [result.model_dump()]}))
        (tmp_path / "comparison-comment.md").write_text(
            pr_verifier.format_comparison_report([result])
        )
    completed = execute_comment_step(tmp_path, authored, PR_NUMBER="123", CI_FAILED="false")
    assert completed.returncode == 0, completed.stderr
    report = (tmp_path / "posted.md").read_text()
    assert "no model review:" in report
    assert "files reviewed 0 of 10" in report if with_results else "files reviewed 0" in report
    assert "verifier-corpus-decision/v1" not in report


def test_verifier_skip_warns_and_comments_reason_without_shell_interpolation(tmp_path):
    reason = "Diff unavailable: $(touch INJECTED) `touch INJECTED`"
    completed = execute_comment_step(
        tmp_path,
        step("Stop when verifier is skipped"),
        PR_NUMBER="123",
        SKIP_REASON=reason,
    )
    assert completed.returncode == 0, completed.stderr
    assert "::warning::Verifier skipped:" in completed.stdout
    assert reason in (tmp_path / "posted.md").read_text()
    assert not (tmp_path / "INJECTED").exists()


def test_verifier_api_fallback_cannot_establish_pass():
    context = """# Verifier context

## Context source coverage

```json
{"diff_retrieval":{"complete":false,"reason":"API patch completeness unknown"}}
```

## CI Information

CI results unavailable.

## Plan sources (scope, tasks, acceptance)

### Acceptance criteria
- Implement the change.
"""
    diff = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n"
    coverage = pr_verifier.prompt_coverage(context, diff)
    assert not coverage.sufficient
    assert any("API patch completeness unknown" in reason for reason in coverage.reasons)
