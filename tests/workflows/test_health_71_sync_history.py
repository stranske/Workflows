"""Run the Health 71 history step against credential-free GitHub API fixtures."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(".github/workflows/health-71-sync-health-check.yml")
RECENT = "2026-11-20T05:01:06Z"
DAY_OLD = "2026-11-16T05:01:06Z"

pytestmark = pytest.mark.skipif(
    not shutil.which("node") or not shutil.which("jq"),
    reason="Health 71 history step requires Node and jq",
)

MOCK = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const requireOriginal = Module.prototype.require;
const state = JSON.parse(process.env.HISTORY_FIXTURE);

const readPage = async (params) => {
  assert.equal(params.owner, 'stranske');
  assert.equal(params.repo, 'Workflows');
  assert.equal(params.workflow_id, 'maint-68-sync-consumer-repos.yml');
  fs.appendFileSync(process.env.HISTORY_CALLS, JSON.stringify(params) + '\n');
  if (params.page === state.failPage) throw new Error('fixture read failed');
  const offset = (params.page - 1) * params.per_page;
  const runs = state.runs.slice(offset, offset + params.per_page);
  const headers = offset + runs.length < state.runs.length
    ? { link: '<https://api.github.test/?page=2>; rel="next"' } : {};
  return { data: { workflow_runs: runs }, headers };
};

const client = { rest: { actions: { listWorkflowRuns: readPage } } };
Module.prototype.require = function (name) {
  if (name === '@octokit/rest') {
    return { Octokit: class { constructor({ auth }) {
      assert.equal(auth, 'fixture-token');
      this.rest = { actions: { listWorkflowRuns: () => assert.fail('unwrapped call') } };
    } } };
  }
  if (name.endsWith('/github-api-with-retry.js')) {
    return { createTokenAwareRetry: async (options) => {
      assert.deepEqual(options.capabilities, ['actions:read']);
      assert.equal(options.task, 'health-71-sync-health-check');
      return {
        withRetry: (fn) => fn(client),
        paginateWithRetry: async (_method, params) => {
          const runs = [];
          for (let page = 1; ; page += 1) {
            const response = await readPage({ ...params, page });
            runs.push(...response.data.workflow_runs);
            if (!response.headers.link) return runs;
          }
        },
      };
    } };
  }
  return requireOriginal.call(this, name);
};

const write = process.stdout.write.bind(process.stdout);
process.stdout.write = (chunk, ...args) => {
  fs.appendFileSync(process.env.HISTORY_SELECTED, chunk);
  return write(chunk, ...args);
};
"""

FIXED_DATE = r"""
date() {
  if [ "$1" = '-d' ]; then
    "$FIXTURE_PYTHON" -c 'import datetime, sys; print(int(datetime.datetime.fromisoformat(sys.argv[1]).timestamp()))' "$2"
  else
    printf '%s\n' 1795154616
  fi
}
"""


def _run_history(tmp_path, runs, lookback="", *, fail_page=None, max_age="72"):
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    step = next(
        step for step in workflow["jobs"]["check-sync-health"]["steps"] if step.get("id") == "check"
    )
    shim = tmp_path / "intercept.cjs"
    shim.write_text(MOCK, encoding="utf-8")
    calls, selected, outputs = (tmp_path / name for name in ("calls", "selected", "outputs"))
    result = subprocess.run(
        ["bash", "-e", "-c", FIXED_DATE + step["run"]],
        env={
            **os.environ,
            "NODE_OPTIONS": f"--require={shim}",
            "FIXTURE_PYTHON": sys.executable,
            "GITHUB_REPOSITORY": "stranske/Workflows",
            "GH_TOKEN": "fixture-token",
            "LOOKBACK": lookback or "5",
            "MAX_AGE_HOURS": max_age,
            "GITHUB_OUTPUT": str(outputs),
            "HISTORY_FIXTURE": json.dumps({"runs": runs, "failPage": fail_page}),
            "HISTORY_CALLS": str(calls),
            "HISTORY_SELECTED": str(selected),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    requests = (
        [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines()]
        if calls.exists()
        else []
    )
    rows = json.loads(selected.read_text(encoding="utf-8")) if selected.exists() else None
    recorded = (
        dict(line.split("=", 1) for line in outputs.read_text(encoding="utf-8").splitlines())
        if outputs.exists()
        else {}
    )
    return result, [(p["per_page"], p["page"]) for p in requests], rows, recorded


def _records(total, conclusion="success", created_at=RECENT):
    return [
        {"id": total - i, "conclusion": conclusion, "created_at": created_at} for i in range(total)
    ]


@pytest.mark.parametrize(
    ("lookback", "available", "requested", "expected_pages"),
    [
        ("", 220, 5, [(5, 1)]),
        ("7", 220, 7, [(7, 1)]),
        ("100", 220, 100, [(100, 1)]),
        ("101", 220, 101, [(100, 1), (100, 2)]),
        ("101", 100, 101, [(100, 1)]),
        ("101", 20, 101, [(100, 1)]),
        ("205", 220, 205, [(100, 1), (100, 2), (100, 3)]),
        ("0", 220, 5, [(5, 1)]),
        ("invalid", 220, 5, [(5, 1)]),
        ("5.9", 220, 5, [(5, 1)]),
    ],
)
def test_history_selects_exact_recent_window(
    tmp_path, lookback, available, requested, expected_pages
):
    runs = _records(available)
    result, calls, selected, outputs = _run_history(tmp_path, runs, lookback)
    assert result.returncode == 0, result.stderr
    assert calls == expected_pages
    assert selected == runs[:requested]
    assert outputs["status"] == ("healthy" if requested else "no_runs")


@pytest.mark.parametrize(
    ("runs", "status", "message"),
    [
        ([], "no_runs", "No sync workflow runs found in the lookback window"),
        (_records(5, "failure"), "all_failed", "All last 5 sync runs have failed!"),
        (
            _records(2, "failure") + _records(3, "cancelled"),
            "no_success",
            "No successful sync runs in the last 5 runs (2 failed, 3 other states)",
        ),
        (
            _records(5, created_at=DAY_OLD),
            "stale",
            "Last successful sync was 97 hours ago (threshold: 72 hours)",
        ),
        (_records(5), "healthy", "Sync is healthy - last success 1 hours ago"),
    ],
)
def test_history_preserves_status_messages(tmp_path, runs, status, message):
    result, calls, selected, outputs = _run_history(tmp_path, runs)
    assert result.returncode == 0, result.stderr
    assert calls == [(5, 1)]
    assert selected == runs
    expected = {"status": status, "message": message}
    if status in {"healthy", "stale"}:
        expected["hours_since_success"] = "1" if status == "healthy" else "97"
    assert outputs == expected


@pytest.mark.parametrize("page", [1, 2])
def test_history_fails_before_publishing_partial_results(tmp_path, page):
    result, calls, selected, outputs = _run_history(tmp_path, _records(150), "101", fail_page=page)
    assert result.returncode == 1
    assert "fixture read failed" in result.stderr
    assert calls == [(100, i) for i in range(1, page + 1)]
    assert selected is None
    assert outputs == {}


@pytest.mark.parametrize(
    ("lookback", "selected_count"),
    [
        ("-1", 219),
        ("Infinity", 220),
        ("-Infinity", 0),
        ("9007199254740992", 220),
        ("0.5", 0),
        ("-0.5", 0),
    ],
)
def test_unusual_history_limit_preserves_full_history_slice(tmp_path, lookback, selected_count):
    runs = _records(220)
    result, calls, selected, outputs = _run_history(tmp_path, runs, lookback)
    assert result.returncode == 0, result.stderr
    assert calls == [(100, 1), (100, 2), (100, 3)]
    assert selected == runs[:selected_count]
    assert outputs["status"] == ("healthy" if selected_count else "no_runs")
