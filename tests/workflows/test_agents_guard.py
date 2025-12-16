import json
import shutil
import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Check if Node.js is available
NODE_AVAILABLE = shutil.which("node") is not None
skip_if_no_node = pytest.mark.skipif(
    not NODE_AVAILABLE,
    reason="Node.js not available (required for agents-guard.js tests)",
)


def get_default_marker():
    script = """
const path = require('path');
const { DEFAULT_MARKER } = require(path.resolve(process.cwd(), '.github/scripts/agents-guard.js'));
process.stdout.write(DEFAULT_MARKER);
"""

    completed = subprocess.run(
        ["node", "-e", script],
        text=True,
        capture_output=True,
        cwd=REPO_ROOT,
        check=True,
    )
    return completed.stdout


# Lazy evaluation: only compute DEFAULT_MARKER when tests actually run
_DEFAULT_MARKER_CACHE = None


def get_default_marker_cached():
    global _DEFAULT_MARKER_CACHE
    if _DEFAULT_MARKER_CACHE is None:
        _DEFAULT_MARKER_CACHE = get_default_marker()
    return _DEFAULT_MARKER_CACHE


def run_guard(
    files=None,
    labels=None,
    reviews=None,
    codeowners=None,
    protected=None,
    author=None,
    marker=None,
):
    payload = {
        "files": files or [],
        "labels": labels or [],
        "reviews": reviews or [],
        "codeownersContent": codeowners or "",
    }
    if protected is not None:
        payload["protectedPaths"] = protected
    if author is not None:
        payload["authorLogin"] = author
    if marker is not None:
        payload["marker"] = marker

    script = """
const fs = require('fs');
const path = require('path');
const input = JSON.parse(fs.readFileSync(0, 'utf-8'));
const { evaluateGuard } = require(path.resolve(process.cwd(), '.github/scripts/agents-guard.js'));
const result = evaluateGuard(input);
process.stdout.write(JSON.stringify(result));
"""

    completed = subprocess.run(
        ["node", "-e", script],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=REPO_ROOT,
        check=True,
    )
    return json.loads(completed.stdout)


def detect_pull_request_target_violations(source: str):
    payload = {"source": source}
    script = """
const fs = require('fs');
const path = require('path');
const input = JSON.parse(fs.readFileSync(0, 'utf-8'));
const { detectPullRequestTargetViolations } = require(path.resolve(process.cwd(), '.github/scripts/agents-guard.js'));
const result = detectPullRequestTargetViolations(input.source);
process.stdout.write(JSON.stringify(result));
"""

    completed = subprocess.run(
        ["node", "-e", script],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=REPO_ROOT,
        check=True,
    )
    return json.loads(completed.stdout)


def validate_pull_request_target_safety(**params):
    script = """
const fs = require('fs');
const path = require('path');
const input = JSON.parse(fs.readFileSync(0, 'utf-8'));
const { validatePullRequestTargetSafety } = require(path.resolve(process.cwd(), '.github/scripts/agents-guard.js'));
const response = { ok: true };

try {
  response.result = validatePullRequestTargetSafety(input);
} catch (error) {
  response.ok = false;
  response.message = error && error.message ? String(error.message) : String(error);
}

process.stdout.write(JSON.stringify(response));
"""

    completed = subprocess.run(
        ["node", "-e", script],
        input=json.dumps(params),
        text=True,
        capture_output=True,
        cwd=REPO_ROOT,
        check=True,
    )
    return json.loads(completed.stdout)


CODEOWNERS_SAMPLE = """
# Example CODEOWNERS entries
/.github/workflows/** @stranske
""".strip()


@skip_if_no_node
def test_deletion_blocks_with_comment():
    result = run_guard(
        files=[
            {
                "filename": ".github/workflows/agents-63-issue-intake.yml",
                "status": "removed",
            }
        ],
        codeowners=CODEOWNERS_SAMPLE,
    )

    assert result["blocked"] is True
    assert any("was deleted" in reason for reason in result["failureReasons"])
    assert "Health 45 Agents Guard" in result["summary"]
    assert result["commentBody"].startswith(get_default_marker_cached())


@skip_if_no_node
def test_custom_marker_propagates_to_comment():
    custom_marker = "<!-- custom-guard-marker -->"
    result = run_guard(
        files=[
            {
                "filename": ".github/workflows/agents-63-issue-intake.yml",
                "status": "removed",
            }
        ],
        codeowners=CODEOWNERS_SAMPLE,
        marker=custom_marker,
    )

    assert result["marker"] == custom_marker
    assert result["commentBody"].startswith(custom_marker)


@skip_if_no_node
def test_default_marker_added_once():
    result = run_guard(
        files=[
            {
                "filename": ".github/workflows/agents-63-issue-intake.yml",
                "status": "removed",
            }
        ],
        codeowners=CODEOWNERS_SAMPLE,
    )

    assert result["commentBody"].startswith(get_default_marker_cached())
    assert result["commentBody"].count(get_default_marker_cached()) == 1


@skip_if_no_node
def test_chatgpt_sync_deletion_allowed():
    result = run_guard(
        files=[
            {
                "filename": ".github/workflows/agents-63-chatgpt-issue-sync.yml",
                "status": "removed",
            }
        ],
        codeowners=CODEOWNERS_SAMPLE,
    )

    assert result["blocked"] is False
    assert not result["failureReasons"]


@skip_if_no_node
def test_rename_blocks_with_guidance():
    result = run_guard(
        files=[
            {
                "filename": ".github/workflows/agents-63-issue-intake.yml",
                "previous_filename": ".github/workflows/agents-63-issue-intake.yml",
                "status": "renamed",
            }
        ],
        codeowners=CODEOWNERS_SAMPLE,
    )

    assert result["blocked"] is True
    assert any("was renamed" in reason for reason in result["failureReasons"])


@skip_if_no_node
def test_modification_without_label_or_approval_requires_both():
    result = run_guard(
        files=[
            {
                "filename": ".github/workflows/agents-70-orchestrator.yml",
                "status": "modified",
            }
        ],
        labels=[],
        reviews=[],
        codeowners=CODEOWNERS_SAMPLE,
    )

    assert result["blocked"] is True
    assert "Missing `agents:allow-change` label." in result["failureReasons"]
    assert any("Request approval" in reason for reason in result["failureReasons"])


@skip_if_no_node
def test_label_without_codeowner_still_blocks():
    result = run_guard(
        files=[
            {
                "filename": ".github/workflows/agents-63-issue-intake.yml",
                "status": "modified",
            }
        ],
        labels=[{"name": "agents:allow-change"}],
        reviews=[],
        codeowners=CODEOWNERS_SAMPLE,
    )

    assert result["blocked"] is True
    assert "Missing `agents:allow-change` label." not in result["failureReasons"]
    assert any("Request approval" in reason for reason in result["failureReasons"])


@skip_if_no_node
def test_label_and_codeowner_approval_passes():
    result = run_guard(
        files=[
            {
                "filename": ".github/workflows/agents-63-issue-intake.yml",
                "status": "modified",
            }
        ],
        labels=[{"name": "agents:allow-change"}],
        reviews=[
            {
                "user": {"login": "stranske"},
                "state": "APPROVED",
            }
        ],
        codeowners=CODEOWNERS_SAMPLE,
    )

    assert result["blocked"] is False
    assert result["summary"] == "Health 45 Agents Guard passed."


@skip_if_no_node
def test_codeowner_author_counts_as_approval():
    result = run_guard(
        files=[
            {
                "filename": ".github/workflows/agents-63-issue-intake.yml",
                "status": "modified",
            }
        ],
        reviews=[],
        codeowners=CODEOWNERS_SAMPLE,
        author="stranske",
    )

    assert result["blocked"] is False
    assert result["hasCodeownerApproval"] is True
    assert result["authorIsCodeowner"] is True
    assert result["hasAllowLabel"] is False


@skip_if_no_node
def test_codeowner_review_without_label_passes():
    result = run_guard(
        files=[
            {
                "filename": ".github/workflows/agents-70-orchestrator.yml",
                "status": "modified",
            }
        ],
        labels=[],
        reviews=[
            {
                "user": {"login": "stranske"},
                "state": "APPROVED",
            }
        ],
        codeowners=CODEOWNERS_SAMPLE,
    )

    assert result["blocked"] is False
    assert result["hasCodeownerApproval"] is True
    assert result["hasAllowLabel"] is False


@skip_if_no_node
def test_codeowner_approval_without_label_passes():
    result = run_guard(
        files=[
            {
                "filename": ".github/workflows/agents-63-issue-intake.yml",
                "status": "modified",
            }
        ],
        labels=[],
        reviews=[
            {
                "user": {"login": "stranske"},
                "state": "APPROVED",
            }
        ],
        codeowners=CODEOWNERS_SAMPLE,
    )

    assert result["blocked"] is False
    assert result["hasCodeownerApproval"] is True
    assert result["hasAllowLabel"] is False


@skip_if_no_node
def test_unprotected_file_is_ignored():
    result = run_guard(
        files=[
            {
                "filename": ".github/workflows/agents-64-verify-agent-assignment.yml",
                "status": "modified",
            }
        ],
        labels=[],
        reviews=[],
        codeowners=CODEOWNERS_SAMPLE,
    )

    assert result["blocked"] is False
    assert result["failureReasons"] == []


@skip_if_no_node
def test_detect_no_violations_for_clean_workflow():
    source = dedent(
        """
        jobs:
          guard:
            steps:
              - uses: actions/checkout@v4
                with:
                  ref: main
              - run: echo "safe"
        """
    )

    assert detect_pull_request_target_violations(source) == []


@skip_if_no_node
def test_detect_flags_head_sha_checkout():
    source = dedent(
        """
        jobs:
          guard:
            steps:
              - uses: actions/checkout@v4
                with:
                  ref: ${{ github.event.pull_request.head.sha }}
        """
    )

    violations = detect_pull_request_target_violations(source)
    assert any(item.get("type") == "checkout-head-sha" for item in violations)


@skip_if_no_node
def test_detect_flags_secrets_in_run_block():
    source = dedent(
        """
        jobs:
          guard:
            steps:
              - run: |
                  echo "${{ secrets.DEPLOY_TOKEN }}"
        """
    )

    violations = detect_pull_request_target_violations(source)
    assert any(item.get("type") == "secrets-run" for item in violations)


@skip_if_no_node
def test_detect_ignores_secrets_in_comments():
    source = dedent(
        """
        # run: echo "${{ secrets.IGNORED }}"
        jobs:
          guard:
            steps:
              - run: echo "safe"
        """
    )

    assert detect_pull_request_target_violations(source) == []


@skip_if_no_node
def test_validate_skips_non_target_event(tmp_path):
    result = validate_pull_request_target_safety(
        eventName="pull_request",
        workflowPath="agents-guard.yml",
        workspaceRoot=str(tmp_path),
    )

    assert result["ok"] is True
    assert result["result"]["checked"] is False
    assert result["result"]["violations"] == []


@skip_if_no_node
def test_validate_accepts_clean_workflow(tmp_path):
    workflow = dedent(
        """
        jobs:
          guard:
            steps:
              - uses: actions/checkout@v4
                with:
                  ref: main
              - run: echo "safe"
        """
    )
    workflow_path = tmp_path / "workflow.yml"
    workflow_path.write_text(workflow)

    result = validate_pull_request_target_safety(
        eventName="pull_request_target",
        workflowPath="workflow.yml",
        workspaceRoot=str(tmp_path),
    )

    assert result["ok"] is True
    assert result["result"]["checked"] is True
    assert result["result"]["violations"] == []


@skip_if_no_node
def test_validate_blocks_unsafe_workflow(tmp_path):
    workflow = dedent(
        """
        jobs:
          guard:
            steps:
              - uses: actions/checkout@v4
                with:
                  ref: ${{ github.event.pull_request.head.sha }}
        """
    )
    workflow_path = tmp_path / "workflow.yml"
    workflow_path.write_text(workflow)

    result = validate_pull_request_target_safety(
        eventName="pull_request_target",
        workflowPath="workflow.yml",
        workspaceRoot=str(tmp_path),
    )

    assert result["ok"] is False
    assert "Unsafe pull_request_target usage detected" in result["message"]
