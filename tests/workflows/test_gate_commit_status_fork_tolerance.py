"""The Gate's commit-status step must survive a fork's read-only token.

A pull request opened from a fork runs ``pr-00-gate.yml`` with a read-only
``GITHUB_TOKEN``, so ``POST /repos/{owner}/{repo}/statuses/{sha}`` answers
403 ``Resource not accessible by integration``.  Before this guard the step
rethrew that error, which failed the ``summary`` job *after* it had already
computed a passing verdict: a fork PR whose CI was entirely green reported a
red Gate, and the true verdict was printed nowhere.  Observed on
stranske/Fine-Art-Archive#716, Actions run 34017696018.

The guard is deliberately narrow.  A 403 on a *same-repo* pull request is a
real permission regression and must still fail the job -- #2278 recorded the
opposite defect, where a bare ``status === 403`` classified genuine permission
failures as rate limits.  This test pins both directions.

It runs each Gate's actual JavaScript (extracted from the workflow file) under
Node against stubbed ``github``/``context``/``core`` objects, so it fails if
the tolerance is removed or widened.  Both this repo's Gate and the
consumer-repo template are covered: ``pr-00-gate.yml`` is distributed
``sync_mode: create_only``, so the two copies must not drift apart.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_WORKFLOWS = {
    "consumer-template": (
        REPO_ROOT / "templates" / "consumer-repo" / ".github" / "workflows" / "pr-00-gate.yml"
    ),
    "repo": REPO_ROOT / ".github" / "workflows" / "pr-00-gate.yml",
}
STEP_NAME = "Report Gate commit status"

RUNNER_JS = textwrap.dedent(
    """
    const fs = require('fs');
    const vm = require('vm');
    const src = fs.readFileSync(process.argv[2], 'utf8');

    function makeError(status, message) {
      const e = new Error(message);
      e.status = status;
      return e;
    }

    async function runCase({ headRepo, baseRepo, error, state }) {
      const warnings = [];
      const summaryCalls = [];
      const summaryStub = {
        addHeading() { return summaryStub; },
        addRaw() { return summaryStub; },
        async write() { summaryCalls.push('write'); },
      };
      const githubStub = {
        rest: {
          repos: {
            createCommitStatus: async () => { if (error) throw error; },
          },
        },
      };
      const sandbox = {
        process: {
          env: {
            STATE: state,
            DESCRIPTION: 'all checks passed',
            TARGET_URL: 'https://example.invalid/run',
          },
        },
        console: { log() {} },
        // The Gate pulls its retry helper off disk; the helper is not under test
        // here, so it is replaced by a pass-through that hands the call straight
        // to the stubbed client.
        require: () => ({
          createTokenAwareRetry: async () => ({
            withRetry: async (fn) => fn(githubStub),
          }),
        }),
        core: { warning: (m) => warnings.push(String(m)), summary: summaryStub },
        context: {
          repo: { owner: 'stranske', repo: 'Workflows' },
          sha: 'basesha',
          payload: {
            pull_request: {
              head: { sha: 'headsha', repo: { full_name: headRepo } },
              base: { repo: { full_name: baseRepo } },
            },
          },
        },
        github: githubStub,
      };
      vm.createContext(sandbox);
      let threw = null;
      try {
        await vm.runInContext('(async () => {\\n' + src + '\\n})()', sandbox);
      } catch (e) {
        threw = { status: e.status === undefined ? null : e.status, message: String(e.message) };
      }
      return { warnings, summaryWrites: summaryCalls.length, threw };
    }

    const FORK = {
      headRepo: 'outside-contributor/Workflows',
      baseRepo: 'stranske/Workflows',
    };
    const SAME = {
      headRepo: 'stranske/Workflows',
      baseRepo: 'stranske/Workflows',
    };

    (async () => {
      const out = {
        fork_read_only: await runCase({
          ...FORK, state: 'success',
          error: makeError(403, 'Resource not accessible by integration'),
        }),
        same_repo_read_only: await runCase({
          ...SAME, state: 'success',
          error: makeError(403, 'Resource not accessible by integration'),
        }),
        fork_rate_limit: await runCase({
          ...FORK, state: 'success',
          error: makeError(403, 'API rate limit exceeded'),
        }),
        fork_server_error: await runCase({
          ...FORK, state: 'success',
          error: makeError(500, 'Internal server error'),
        }),
        happy_path: await runCase({ ...FORK, state: 'success', error: null }),
      };
      process.stdout.write(JSON.stringify(out));
    })();
    """
).strip()


def _extract_step_script(workflow: Path) -> str:
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    for job in document["jobs"].values():
        for step in job.get("steps") or []:
            if step.get("name") == STEP_NAME:
                return str(step["with"]["script"])
    raise AssertionError(f"{workflow} no longer defines a {STEP_NAME!r} step")


@pytest.fixture(scope="module", params=sorted(GATE_WORKFLOWS), ids=sorted(GATE_WORKFLOWS))
def outcomes(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> dict[str, Any]:
    node = shutil.which("node")
    assert node, "node is required to execute the Gate's github-script step"

    workflow = GATE_WORKFLOWS[str(request.param)]
    workdir = tmp_path_factory.mktemp("gate-status")
    step_path = workdir / "step.js"
    step_path.write_text(_extract_step_script(workflow), encoding="utf-8")
    runner_path = workdir / "runner.js"
    runner_path.write_text(RUNNER_JS, encoding="utf-8")

    completed = subprocess.run(
        [node, str(runner_path), str(step_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return dict(json.loads(completed.stdout))


def test_fork_read_only_403_does_not_fail_the_gate(outcomes: dict[str, Any]) -> None:
    case = outcomes["fork_read_only"]
    assert case["threw"] is None, case["threw"]


def test_fork_read_only_403_reports_the_real_verdict(outcomes: dict[str, Any]) -> None:
    case = outcomes["fork_read_only"]
    joined = " ".join(case["warnings"])
    assert "read-only" in joined, joined
    assert "'success'" in joined, joined
    assert case["summaryWrites"] == 1


def test_same_repo_403_still_fails_the_gate(outcomes: dict[str, Any]) -> None:
    """A permission regression on a same-repo PR must stay loud (see #2278)."""
    case = outcomes["same_repo_read_only"]
    assert case["threw"] is not None
    assert case["threw"]["status"] == 403


def test_rate_limit_403_keeps_its_own_path(outcomes: dict[str, Any]) -> None:
    case = outcomes["fork_rate_limit"]
    assert case["threw"] is None
    assert any("Rate limit" in warning for warning in case["warnings"]), case["warnings"]


def test_non_403_errors_still_fail_the_gate(outcomes: dict[str, Any]) -> None:
    case = outcomes["fork_server_error"]
    assert case["threw"] is not None
    assert case["threw"]["status"] == 500


def test_successful_status_write_is_silent(outcomes: dict[str, Any]) -> None:
    case = outcomes["happy_path"]
    assert case["threw"] is None
    assert case["warnings"] == []
    assert case["summaryWrites"] == 0
