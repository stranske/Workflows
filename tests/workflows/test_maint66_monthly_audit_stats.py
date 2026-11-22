"""Maint 66 stats step: jq must run on a runs array, not a slurped wrapper."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github/workflows/maint-66-monthly-audit.yml"

RUNS_FIXTURE = [
    {
        "name": "CI",
        "conclusion": "success",
        "created_at": "2026-10-01T00:00:00Z",
    },
    {
        "name": "CI",
        "conclusion": "failure",
        "created_at": "2026-10-02T00:00:00Z",
    },
    {
        "name": "Gate",
        "conclusion": "success",
        "created_at": "2026-10-03T00:00:00Z",
    },
    {
        "name": "Gate",
        "conclusion": "cancelled",
        "created_at": "2026-10-04T00:00:00Z",
    },
]


def _extract_stats_jq_invocation(workflow_text: str) -> tuple[bool, str]:
    match = re.search(
        r'echo "\$\{runs\}" \| jq(?P<slurp> -s)? \'\n'
        r"(?P<program>.*?)\n"
        r"          ' > /tmp/workflow_stats\.json",
        workflow_text,
        re.DOTALL,
    )
    assert match, "stats jq program not found in maint-66-monthly-audit.yml"
    slurp = match.group("slurp") is not None
    program = match.group("program").strip("\n")
    return slurp, program


def _extract_summary_jq_programs(workflow_text: str) -> list[tuple[bool, str]]:
    pattern = re.compile(
        r'echo "\$\{runs\}" \| jq(?P<slurp> -s)?(?: \\\n)?\s*\'(?P<program>[^\']+)\''
    )
    matches = list(pattern.finditer(workflow_text))
    assert len(matches) >= 3, "expected three summary jq invocations on ${runs}"
    return [(m.group("slurp") is not None, m.group("program")) for m in matches[-3:]]


def _run_jq(program: str, runs_json: str, *, slurp: bool) -> subprocess.CompletedProcess[str]:
    cmd = ["jq"]
    if slurp:
        cmd.append("-s")
    cmd.append(program)
    return subprocess.run(
        cmd,
        input=runs_json,
        text=True,
        capture_output=True,
        check=False,
    )


def test_stats_jq_program_runs_on_runs_array() -> None:
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    slurp, program = _extract_stats_jq_invocation(workflow_text)
    assert not slurp, "stats jq must not slurp a single JSON array written at :78"
    runs_json = json.dumps(RUNS_FIXTURE)

    completed = _run_jq(program, runs_json, slurp=False)
    assert completed.returncode == 0, completed.stderr

    stats = json.loads(completed.stdout)
    assert len(stats) == 2
    by_name = {row["name"]: row for row in stats}
    assert {
        key: by_name["CI"][key]
        for key in ("name", "total", "success", "failure", "cancelled", "other")
    } == {
        "name": "CI",
        "total": 2,
        "success": 1,
        "failure": 1,
        "cancelled": 0,
        "other": 0,
    }
    assert {
        key: by_name["Gate"][key]
        for key in ("name", "total", "success", "failure", "cancelled", "other")
    } == {
        "name": "Gate",
        "total": 2,
        "success": 1,
        "failure": 0,
        "cancelled": 1,
        "other": 0,
    }


def test_summary_jq_programs_on_runs_array() -> None:
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    summary_programs = _extract_summary_jq_programs(workflow_text)
    runs_json = json.dumps(RUNS_FIXTURE)

    totals: list[str] = []
    for slurp, program in summary_programs:
        assert not slurp, f"summary jq must not use -s: {program!r}"
        completed = _run_jq(program, runs_json, slurp=False)
        assert completed.returncode == 0, completed.stderr
        totals.append(completed.stdout.strip())

    assert totals == ["4", "2", "1"]


def _stats(runs):
    _, program = _extract_stats_jq_invocation(WORKFLOW_PATH.read_text())
    completed = _run_jq(program, json.dumps(runs), slurp=False)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _runs(name, conclusion, count, workflow_id=1, path=".github/workflows/a.yml"):
    return [
        {
            "name": name,
            "workflow_id": workflow_id,
            "path": path,
            "conclusion": conclusion,
            "created_at": "2026-11-01T00:00:00Z",
        }
        for _ in range(count)
    ]


def _attention(tmp_path, runs):
    stats = tmp_path / "workflow_stats.json"
    stats.write_text(json.dumps(_stats(runs)))
    workflows = tmp_path / ".github/workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    (workflows / "a.yml").write_text("name: Renamed local name\non: push\n")
    (workflows / "a-extra.yml").write_text("name: Renamed local name\non: push\n")
    steps = yaml.safe_load(WORKFLOW_PATH.read_text())["jobs"]["audit"]["steps"]
    script = next(step["run"] for step in steps if step.get("id") == "attention")
    script = script.replace("/tmp/workflow_stats.json", str(stats))
    script = script.replace("/tmp/monthly-audit-details", str(tmp_path / "details"))
    script = script.replace(
        "scripts/workflow_inventory_audit.py",
        str(REPO_ROOT / "scripts/workflow_inventory_audit.py"),
    )
    script = script.replace("PYTHONPATH=.", f"PYTHONPATH={REPO_ROOT}")
    output = tmp_path / "outputs"
    result = subprocess.run(
        ["bash", "-e", "-c", script],
        cwd=tmp_path,
        env={**os.environ, "GITHUB_OUTPUT": str(output), "PYTHONPATH": str(REPO_ROOT)},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    return dict(re.findall(r"(\w+)<<EOF\n(.*?)\nEOF", output.read_text(), re.S))


def test_november_zero_failure_regression(tmp_path):
    runs = (
        _runs("Auto-Label Issues", "skipped", 8050)
        + _runs("Auto-Fix Integration Test Failures", "neutral", 4866, workflow_id=2)
        + _runs("True failure", "failure", 6, workflow_id=3)
        + _runs("True failure", "success", 2, workflow_id=3)
    )
    outputs = _attention(tmp_path, runs)
    assert "Auto-Label" not in outputs["failing"] + outputs["warning"]
    assert "Auto-Fix" not in outputs["failing"] + outputs["warning"]
    assert "75% failed outcomes (6/8 decisive" in outputs["failing"]
    assert "skipped=8050" in outputs["conclusion_mix"]
    assert "neutral=4866" in outputs["conclusion_mix"]
    assert "- a.yml" not in outputs["not_run"]  # path, not display-name match
    assert "- a-extra.yml" in outputs["not_run"]


@pytest.mark.parametrize(
    "conclusion,failed",
    [
        ("failure", 1),
        ("timed_out", 1),
        ("startup_failure", 1),
        ("action_required", 1),
        ("success", 0),
        ("neutral", 0),
        ("skipped", 0),
        ("cancelled", 0),
        ("stale", 0),
        (None, 0),
        ("future_conclusion", 0),
    ],
)
def test_explicit_conclusion_policy(conclusion, failed):
    row = _stats(_runs("a", conclusion, 1))[0]
    assert row["failed_outcomes"] == failed
    assert row["decisive"] == failed + int(conclusion == "success")
    assert row["conclusions"] == {conclusion or "unknown": 1}


def test_stable_identity_and_legacy_fallback():
    rows = _stats(
        _runs("old title", "success", 2)
        + _runs("new title", "failure", 3)
        + _runs("old title", "success", 1, workflow_id=2)
    )
    assert len(rows) == 2 and rows[0]["total"] == 5
    assert rows[0]["workflow_key"] == "id:1"
    legacy = _stats([{"name": "legacy", "conclusion": "success"}])
    assert legacy[0]["workflow_key"] == "legacy-name:legacy"
    path = _stats(
        _runs("old", "success", 1, workflow_id=None, path=".github/workflows/a.yml@refs/heads/main")
    )
    assert path[0]["paths"] == [".github/workflows/a.yml"]
    assert _stats([]) == []


def test_sample_policy_thresholds_and_failure_order(tmp_path):
    runs = (
        _runs("small", "failure", 4)
        + _runs("half", "success", 3, workflow_id=2)
        + _runs("half", "failure", 3, workflow_id=2)
        + _runs("fifth", "success", 4, workflow_id=3)
        + _runs("fifth", "failure", 1, workflow_id=3)
        + _runs("worst", "timed_out", 5, workflow_id=4)
        + _runs("large", "success", 20, workflow_id=5)
        + _runs("large", "failure", 30, workflow_id=5)
    )
    out = _attention(tmp_path, runs)
    assert out["failing"].index("worst") < out["failing"].index("large")
    assert "half" in out["warning"] and "half" not in out["failing"]
    assert "fifth" not in out["warning"] and "fifth" in out["conclusion_mix"]
    assert "small" in out["small_sample"] and "small" not in out["failing"]
    assert "timed_out=5" in out["conclusion_mix"]


def test_published_november_totals_synthetic_red_green(tmp_path):
    """Published counts, synthetic conclusion mix: NOT a replay of actual raw runs."""
    runs = (
        _runs("Auto-Label Issues", "skipped", 7849)
        + _runs("Auto-Label Issues", "success", 201)
        + _runs("Auto-Fix Integration Test Failures", "neutral", 4866, workflow_id=2)
        + _runs("Synthetic failing workflow", "failure", 5542, workflow_id=3)
        + _runs("Synthetic failing workflow", "success", 1000, workflow_id=3)
        + _runs("Synthetic healthy workflow", "success", 94578, workflow_id=4)
        + _runs("Synthetic remaining other", "cancelled", 10000, workflow_id=5)
        + _runs("Synthetic remaining other", None, 15574, workflow_id=5)
        + _runs("Duplicate Detection", "failure", 149, workflow_id=6)
        + _runs("Maint 46 Post CI", "failure", 1380, workflow_id=7)
        + _runs("Maint 46 Post CI", "success", 503, workflow_id=7)
    )
    assert len(runs) == 141642
    assert sum(r["conclusion"] == "success" for r in runs) == 96282
    assert sum(r["conclusion"] == "failure" for r in runs) == 7071
    assert sum(r["conclusion"] not in ("success", "failure") for r in runs) == 38289
    # Frozen previous production rule: volume sorting, success/all, <50%.
    old = _run_jq(
        """group_by(.name) | map({name: .[0].name, total: length,
        success: map(select(.conclusion == "success")) | length,
        failure: map(select(.conclusion == "failure")) | length}) |
        sort_by(-.total) | map(select(.total > 0 and .success / .total < 0.5))""",
        json.dumps(runs),
        slurp=False,
    )
    assert old.returncode == 0, old.stderr
    old_rows = {r["name"]: r for r in json.loads(old.stdout)}
    for name, total in [("Auto-Label Issues", 8050), ("Auto-Fix Integration Test Failures", 4866)]:
        assert old_rows[name]["failure"] == 0 and old_rows[name]["total"] == total
    new = _attention(tmp_path, runs)  # actual production shell/JQ attention path
    assert "Auto-Label" not in new["failing"] + new["warning"]
    assert "Auto-Fix" not in new["failing"] + new["warning"]
    assert "Synthetic failing workflow" in new["failing"]
    assert "5542/6542 decisive" in new["failing"]
    assert "149/149 decisive" in new["failing"]
    assert "1380/1883 decisive" in new["failing"]
    assert new["failing"].index("Duplicate Detection") < new["failing"].index("Maint 46 Post CI")
    assert "cancelled=10000, unknown=15574" in new["conclusion_mix"]
    assert "skipped=7849, success=201" in new["conclusion_mix"]
    assert "neutral=4866" in new["conclusion_mix"]


@pytest.mark.parametrize("runs", [[], _runs("all skipped", "skipped", 20)])
def test_empty_and_all_skipped_never_rank(tmp_path, runs):
    out = _attention(tmp_path, runs)
    assert out["failing"] == out["warning"] == out["small_sample"] == "None"


def test_collector_keeps_stable_identity_without_new_api_calls():
    text = WORKFLOW_PATH.read_text()
    assert "id, created_at, name, conclusion, workflow_id, path, status" in text
    assert text.count("client.rest.actions.") == 1
    assert "collectRunWindow" in text


def test_pending_null_conclusions_are_distinct_from_unknown():
    runs = _runs("CI", None, 5)
    for run, status in zip(
        runs, ["queued", "in_progress", "waiting", "completed", None], strict=True
    ):
        run["status"] = status
    row = _stats(runs)[0]
    assert row["conclusions"] == {
        "pending:queued": 1,
        "pending:in_progress": 1,
        "pending:waiting": 1,
        "unknown": 2,
    }
    assert row["failed_outcomes"] == row["decisive"] == 0


def test_large_fleet_bounds_output_without_losing_artifact_rankings(tmp_path):
    # 1,000 distinct workflows with long Unicode names exceeds the issue ceiling
    # without bounding. Exercise the production jq + attention shell, not a mock.
    runs = []
    for index in range(1000):
        runs += _runs("長" * 100 + str(index), "failure", 5, workflow_id=index)
    outputs = _attention(tmp_path, runs)
    assert sum(len(value.encode()) for value in outputs.values()) < 32000
    assert "additional lines omitted" in outputs["failing"]
    assert "failure=5000" in outputs["conclusion_mix"]
    detail = tmp_path / "details"
    complete = (detail / "failing.txt").read_text()
    assert complete.count("100% failed outcomes (5/5 decisive") == 1000
    assert len(json.loads((detail / "workflow_stats.json").read_text())) == 1000
    assert "id:999" in complete
    kept = outputs["failing"].count("100% failed outcomes")
    assert f"{1000 - kept} additional lines omitted" in outputs["failing"]


def test_call_only_reusable_omitted_from_not_run_despite_pull_request_in_jobs(tmp_path):
    """Attention skip must follow parsed triggers, not whole-file `pull_request` text."""
    runs = _runs("Some workflow", "success", 1)
    workflows = tmp_path / ".github/workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    (workflows / "reusable-sample.yml").write_text(
        "name: Reusable sample\n"
        "on:\n"
        "  workflow_call:\n"
        "    inputs:\n"
        "      x:\n"
        "        type: string\n"
        "jobs:\n"
        "  j:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo pull_request types path filter\n",
        encoding="utf-8",
    )
    outputs = _attention(tmp_path, runs)
    assert "reusable-sample.yml" not in outputs["not_run"]


def test_ranking_aggregate_matches_summary_expressions():
    rows = _stats(
        sum(
            (
                _runs("CI", value, 1)
                for value in [
                    "failure",
                    "timed_out",
                    "startup_failure",
                    "action_required",
                    "success",
                    "skipped",
                ]
            ),
            [],
        )
    )
    text = WORKFLOW_PATH.read_text()
    for field, expected in [("failed_outcomes", 4), ("decisive", 5)]:
        program = re.search(r"total_" + field + r"=\$\(jq '([^']+)'", text).group(1)
        result = _run_jq(program, json.dumps(rows), slurp=False)
        assert result.returncode == 0
        assert int(result.stdout) == expected
