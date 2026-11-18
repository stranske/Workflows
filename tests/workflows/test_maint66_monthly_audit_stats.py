"""Maint 66 stats step: jq must run on a runs array, not a slurped wrapper."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

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
    assert by_name["CI"] == {
        "name": "CI",
        "total": 2,
        "success": 1,
        "failure": 1,
        "cancelled": 0,
        "other": 0,
    }
    assert by_name["Gate"] == {
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
