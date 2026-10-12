import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(".github/workflows/health-84-langsmith-observability.yml")


def test_observability_health_is_independent_and_non_mutating() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert source.count("schedule:") == 1
    assert "workflow_dispatch:" in source
    assert "workflow_run:" not in source
    assert "maint-80-langsmith-metrics-dashboard.yml" in source
    assert "maint-81-langsmith-fleet-conformance.yml" in source
    assert "contents: read" in source
    assert "contents: write" not in source
    assert "persist-credentials: false" in source
    assert "git push" not in source
    assert "gh run list" in source
    assert "gh api" not in source


def test_observability_health_has_visible_durable_escalation() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert 'title="🔭 LangSmith Observability Health"' in source
    assert "tracker:durable" in source
    assert "needs-human" in source
    assert "agent:needs-attention" in source
    assert "gh issue edit" in source
    assert "gh issue create" in source
    assert "gh issue comment" in source
    assert "LANGSMITH_API_KEY: ${{ secrets.LANGSMITH_API_KEY }}" in source


@pytest.mark.parametrize(
    "status,human", [("degraded", False), ("degraded", True), ("healthy", False)]
)
@pytest.mark.parametrize("existing", [False, True])
def test_health_issue_labels_follow_actual_remediation_owner(tmp_path, status, human, existing):
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["health"]["steps"]
    script = next(
        s["run"] for s in steps if s["name"] == "Upsert durable observability health issue"
    )
    report_dir = tmp_path / ".observability-health"
    report_dir.mkdir()
    (report_dir / "report.md").write_text("health report")
    (report_dir / "report.json").write_text(json.dumps({"human_attention_required": human}))
    gh = tmp_path / "gh"
    gh.write_text(
        "#!/usr/bin/env python3\nimport json,os,sys\nfrom pathlib import Path\na=sys.argv[1:]\nwith open(os.environ['CALLS'],'a') as f: f.write(json.dumps(a)+'\\n')\nif a[:2]==['issue','list']: print(json.dumps([{'number':3123,'title':'🔭 LangSmith Observability Health','body':''}] if os.environ['EXISTING']=='1' else []))\nif a[:2]==['issue','create']: print('https://github.com/o/r/issues/3123')\n"
    )
    gh.chmod(0o755)
    calls = tmp_path / "calls.jsonl"
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "CALLS": str(calls),
            "EXISTING": "1" if existing else "0",
            "HEALTH_STATUS": status,
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_REPOSITORY": "o/r",
            "GITHUB_RUN_ID": "1",
        },
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    commands = [json.loads(line) for line in calls.read_text().splitlines()]
    added_human = any(
        (
            "--add-label" in c
            and any(c[i : i + 2] == ["--add-label", "needs-human"] for i in range(len(c)))
        )
        or ("--label" in c and "needs-human" in c[c.index("--label") + 1].split(","))
        for c in commands
    )
    assert added_human is (status == "degraded" and human)
    if status == "degraded" and not human:
        assert any("--remove-label" in c and "needs-human" in c for c in commands)


@pytest.mark.parametrize("key", ["", "test-key"])
def test_evaluator_failure_preserves_missing_key_ownership(tmp_path, key):
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["health"]["steps"]
    script = next(s["run"] for s in steps if s["name"] == "Evaluate observability health")
    (tmp_path / ".observability-health").mkdir()
    stub = tmp_path / "python"
    stub.write_text("#!/bin/sh\nexit 1\n")
    stub.chmod(0o755)
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "LANGSMITH_API_KEY": key,
            "WORKFLOW_MAX_AGE_HOURS": "192",
            "TRACE_MAX_AGE_HOURS": "24",
            "GITHUB_ENV": str(tmp_path / "env"),
            "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
        },
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads((tmp_path / ".observability-health/report.json").read_text())
    assert report["human_attention_required"] is (not bool(key))
