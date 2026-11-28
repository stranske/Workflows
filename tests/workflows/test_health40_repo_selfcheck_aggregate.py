from __future__ import annotations

import py_compile
import re
import tempfile
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/health-40-repo-selfcheck.yml"


def _extract_aggregate_heredoc() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(
        r"^\s*-\s+name:\s+Aggregate & Summarize\n"
        r".*?^\s*python\s+-\s+<<'PY'\n"
        r"(?P<body>.*?)"
        r"^\s*PY\n",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, "Aggregate & Summarize Python heredoc not found"
    return textwrap.dedent(match.group("body"))


def test_aggregate_python_heredoc_compiles() -> None:
    body = _extract_aggregate_heredoc()

    with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8") as handle:
        handle.write(body)
        handle.flush()
        py_compile.compile(handle.name, doraise=True)


def test_close_tracker_gate_requires_positive_checks_ran_signal() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'handle.write("checks_ran=true\\n")' in text
    assert re.search(
        r"-\s+name:\s+Close failure tracker issue\b"
        r"(?s:.*?)"
        r"steps\.aggregate\.outputs\.checks_ran\s*==\s*'true'\s*&&\s*"
        r"steps\.aggregate\.outputs\.has_errors\s*!=\s*'true'\s*&&\s*"
        r"steps\.aggregate\.outputs\.has_warnings\s*!=\s*'true'",
        text,
        flags=re.DOTALL,
    )


def _workflow_step(name: str) -> dict:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return next(
        step for step in workflow["jobs"]["repo-health"]["steps"] if step.get("name") == name
    )


def test_snapshot_issue_uses_issue_token_chain_even_without_admin_token() -> None:
    step = _workflow_step("Update repo health snapshot issue")

    assert step["if"] == "always()"
    assert step["continue-on-error"] is True
    assert step["with"]["github-token"] == "${{ github.token }}"
    assert "steps.branch-token.outputs.token" not in step["with"]["github-token"]

    script = step["with"]["script"]
    assert "await retryHelpers.createTokenAwareRetry({" in script
    assert "capabilities: ['issues:write']" in script
    assert "withRetry((client) => client.rest.issues.update" in script
    assert "withRetry((client) => client.rest.issues.create" in script


def test_snapshot_issue_does_not_reuse_failure_tracker_prefix_match() -> None:
    script = _workflow_step("Update repo health snapshot issue")["with"]["script"]

    assert "issue.title === issueTitle" in script
    assert "issue.title.startsWith(issueTitle)" not in script


def test_snapshot_issue_uses_supported_idempotent_pin_mutation() -> None:
    script = _workflow_step("Update repo health snapshot issue")["with"]["script"]

    assert "client.rest.issues.pin" not in script
    assert "... on Issue { isPinned }" in script
    assert "pinIssue(input: { issueId: $issueId })" in script


def test_snapshot_issue_is_created_and_updated_as_a_durable_tracker() -> None:
    script = _workflow_step("Update repo health snapshot issue")["with"]["script"]

    assert "const trackerLabelName = 'tracker:durable';" in script
    assert "labels: [labelName, trackerLabelName]" in script
    assert "existingLabels.add(trackerLabelName);" in script


# --- Cohesion review A4: one branch-protection writer --------------------------

WORKFLOWS_DIR = ROOT / ".github/workflows"
CONFIG_ARG = "--config .github/config/required-contexts.json"


def _protection_tool_invocations() -> list[tuple[str, str, str]]:
    """Every step in every workflow that runs enforce_gate_branch_protection.py."""
    found: list[tuple[str, str, str]] = []
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job in (document.get("jobs") or {}).values():
            for step in job.get("steps") or []:
                run = str(step.get("run") or "")
                if "enforce_gate_branch_protection.py" in run:
                    found.append((path.name, str(step.get("name")), " ".join(run.split())))
    return found


def test_health44_is_the_only_workflow_that_applies_branch_protection() -> None:
    invocations = _protection_tool_invocations()
    writers = [(name, step) for name, step, run in invocations if "--apply" in run]
    assert writers == [
        ("health-44-gate-branch-protection.yml", "Enforce gate branch protection")
    ], writers


def test_every_branch_protection_reader_uses_the_shared_config_not_a_literal() -> None:
    # A deliberate second context added to required-contexts.json reaches the
    # one writer and every checker, because none of them names a context.
    invocations = _protection_tool_invocations()
    assert {name for name, _, _ in invocations} >= {
        "health-40-repo-selfcheck.yml",
        "health-44-gate-branch-protection.yml",
    }
    for name, step, run in invocations:
        assert CONFIG_ARG in run, (name, step)
        assert "--context" not in run, (name, step)


def test_selfcheck_snapshot_is_read_only() -> None:
    step = _workflow_step("Snapshot branch protection state")
    assert "--check" in step["run"]
    assert "--apply" not in step["run"]
    names = {
        s.get("name") for s in yaml.safe_load(WORKFLOW.read_text())["jobs"]["repo-health"]["steps"]
    }
    assert "Enforce branch protection policy" not in names
    assert "'enforce+verify'" not in WORKFLOW.read_text(encoding="utf-8")


# --- Cohesion review A5d / round-2 B3: scan alert counts and trends -----------


def test_scan_count_step_is_best_effort_and_permitted() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert workflow["permissions"]["security-events"] == "read"
    step = _workflow_step("Count open security scan alerts")
    assert step["continue-on-error"] is True
    assert step["if"] == "always()"
    assert "snapshotAllScans" in step["with"]["script"]
    assert "renderSecuritySection" in step["with"]["script"]
    assert "'[health] repository self-check'" in step["with"]["script"]


def _extract_heredoc(step_name: str) -> str:
    run = _workflow_step(step_name)["run"]
    match = re.search(r"python - <<'PY'\n(?P<body>.*?)\nPY", run, flags=re.DOTALL)
    assert match, f"{step_name} heredoc not found"
    return textwrap.dedent(match.group("body"))


def _render_status_body(tmp_path: Path, zizmor_md: str | None) -> str:
    import subprocess
    import sys

    if zizmor_md is not None:
        (tmp_path / "repo-health-zizmor.md").write_text(zizmor_md, encoding="utf-8")
    script = tmp_path / "render.py"
    script.write_text(_extract_heredoc("Generate repo health status body"), encoding="utf-8")
    subprocess.run([sys.executable, str(script)], cwd=tmp_path, check=True)
    return (tmp_path / "repo-health-issue.md").read_text(encoding="utf-8")


def test_status_body_carries_the_zizmor_section(tmp_path: Path) -> None:
    section = "## Security scan alerts\n\n*Open zizmor alerts:* `963`\n"
    body = _render_status_body(tmp_path, section)
    assert "*Open zizmor alerts:* `963`" in body


def test_status_body_says_not_counted_when_the_count_step_did_not_run(tmp_path: Path) -> None:
    body = _render_status_body(tmp_path, None)
    for scan in ("zizmor", "CodeQL", "Semgrep"):
        assert f"*Open {scan} alerts:* not counted: the count step did not run" in body
    assert "`0`" not in body


def test_status_body_carries_all_three_scan_counts(tmp_path: Path) -> None:
    """Round-2 B3: CodeQL and Semgrep sit in the same snapshot as zizmor."""
    section = (
        "## Security scan alerts\n\n*Open zizmor alerts:* `963`\n\n"
        "*Open CodeQL alerts:* `0` - fully drained\n\n*Open Semgrep alerts:* `793`\n"
    )
    body = _render_status_body(tmp_path, section)
    counts = re.findall(r"^\*Open (\w+) alerts:\*", body, flags=re.MULTILINE)
    assert counts == ["zizmor", "CodeQL", "Semgrep"]


def test_protection_drift_does_not_skip_signal_collection() -> None:
    """Without the old apply step, --check exits 1 on drift; that must be reported, not fatal."""
    snapshot = _workflow_step("Snapshot branch protection state")
    assert snapshot["id"] == "protection-snapshot"
    assert snapshot["continue-on-error"] is True
    collect = _workflow_step("Collect repository signals")
    assert collect["env"]["PROTECTION_SNAPSHOT_OUTCOME"] == (
        "${{ steps.protection-snapshot.outcome }}"
    )
    script = collect["with"]["script"]
    assert "snapshotOutcome === 'failure'" in script
    assert "key: 'protection-drift'" in script
    assert "status: 'warn'" in script.split("key: 'protection-drift'")[1][:200]


# --- Cohesion review round 2, D9: exact context comparison after Health 41 -------


def test_protection_snapshot_compares_contexts_exactly() -> None:
    """--no-clean folds current contexts into the target, hiding unexpected ones."""
    run = _workflow_step("Snapshot branch protection state")["run"]
    assert "--check" in run
    assert "--no-clean" not in run


def _run_dispatch(tmp_path: Path, snapshot: dict | None) -> tuple[str, str]:
    import json
    import os
    import subprocess

    step = _workflow_step("Dispatch Health 44 to apply the drift")
    if snapshot is not None:
        (tmp_path / "repo-health-branch-protection.json").write_text(json.dumps(snapshot))
    bindir = tmp_path / "bin"
    bindir.mkdir()
    gh = bindir / "gh"
    gh.write_text('#!/bin/sh\necho "$@" >> gh-calls.txt\n')
    gh.chmod(0o755)
    output = tmp_path / "out"
    subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
            "GITHUB_OUTPUT": str(output),
            "GITHUB_REPOSITORY": "stranske/Workflows",
            "DEFAULT_BRANCH": "main",
        },
        check=True,
        timeout=20,
    )
    calls = tmp_path / "gh-calls.txt"
    return output.read_text(), calls.read_text() if calls.exists() else ""


def test_only_extra_contexts_are_named_not_dispatched(tmp_path: Path) -> None:
    out, calls = _run_dispatch(
        tmp_path, {"to_add": [], "to_remove": ["old-check"], "changes_required": True}
    )
    assert out == "dispatched=false\n"
    assert calls == ""


def test_missing_contexts_dispatch_health_44(tmp_path: Path) -> None:
    out, calls = _run_dispatch(
        tmp_path, {"to_add": ["summary"], "to_remove": ["old-check"], "changes_required": True}
    )
    assert out == "dispatched=true\n"
    assert "workflow run health-44-gate-branch-protection.yml" in calls


def test_collect_names_unexpected_contexts() -> None:
    collect = _workflow_step("Collect repository signals")
    assert collect["env"]["PROTECTION_DISPATCHED"] == (
        "${{ steps.protection-apply.outputs.dispatched }}"
    )
    script = collect["with"]["script"]
    assert "Unexpected required contexts:" in script
    assert "repo-health-branch-protection.json" in script
