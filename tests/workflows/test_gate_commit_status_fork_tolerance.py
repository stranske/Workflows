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
import os
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
COMMENT_STEP_NAME = "Ensure consolidated summary comment"

RUNNER_JS = textwrap.dedent("""
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
      const summaryRaw = [];
      const summaryStub = {
        addHeading() { return summaryStub; },
        addRaw(text) { summaryRaw.push(String(text)); return summaryStub; },
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
      return { warnings, summaryWrites: summaryCalls.length, summaryRaw, threw };
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
    """).strip()


def _extract_step_script(workflow: Path, step_name: str = STEP_NAME) -> str:
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    for job in document["jobs"].values():
        for step in job.get("steps") or []:
            if step.get("name") == step_name:
                return str(step["with"]["script"])
    raise AssertionError(f"{workflow} no longer defines a {step_name!r} step")


@pytest.fixture(scope="module", params=sorted(GATE_WORKFLOWS), ids=sorted(GATE_WORKFLOWS))
def outcomes(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:  # pragma: no cover - depends on the host
        message = "node is required to execute the Gate's github-script step"
        # Skipping everywhere would make this gate vacuous on the one runner that
        # matters, so CI is not allowed to skip it; a dev host without node is.
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)

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
    summary = " ".join(case["summaryRaw"])
    assert "headsha" in summary, summary
    assert "success" in summary, summary
    assert "all checks passed" in summary, summary


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
    assert case["summaryRaw"] == []


# ---------------------------------------------------------------------------
# The consolidated summary comment runs BEFORE the status step in the same job
# and writes with the same read-only token, so tolerating the status 403 alone
# would still leave a green fork PR reporting a red Gate.
# ---------------------------------------------------------------------------

COMMENT_RUNNER_JS = textwrap.dedent(
    """
    const nodeFs = require('fs');
    const vm = require('vm');
    const src = nodeFs.readFileSync(process.argv[2], 'utf8');

    function makeError(status, message) {
      const e = new Error(message);
      e.status = status;
      return e;
    }

    async function runCase({ headRepo, baseRepo, error }) {
      const warnings = [];
      const summaryRaw = [];
      const summaryStub = {
        addHeading() { return summaryStub; },
        addRaw(text) { summaryRaw.push(String(text)); return summaryStub; },
        async write() { summaryRaw.push('<written>'); },
      };
      const sandbox = {
        process: { env: {} },
        console: { log() {} },
        require: (id) => {
          if (id === 'path') return { resolve: (p) => '/tmp/' + p };
          if (id === 'fs') {
            return {
              existsSync: () => true,
              readFileSync: () => 'GATE SUMMARY BODY',
            };
          }
          return {
            upsertAnchoredComment: async () => { if (error) throw error; },
          };
        },
        core: { warning: (m) => warnings.push(String(m)), summary: summaryStub },
        context: {
          repo: { owner: 'stranske', repo: 'Workflows' },
          payload: {
            pull_request: {
              number: 1,
              head: { repo: { full_name: headRepo } },
              base: { repo: { full_name: baseRepo } },
            },
          },
        },
        github: {},
      };
      vm.createContext(sandbox);
      let threw = null;
      try {
        await vm.runInContext('(async () => {\\n' + src + '\\n})()', sandbox);
      } catch (e) {
        threw = { status: e.status === undefined ? null : e.status, message: String(e.message) };
      }
      return { warnings, summaryRaw, threw };
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
          ...FORK, error: makeError(403, 'Resource not accessible by integration'),
        }),
        same_repo_read_only: await runCase({
          ...SAME, error: makeError(403, 'Resource not accessible by integration'),
        }),
        fork_server_error: await runCase({ ...FORK, error: makeError(500, 'boom') }),
        happy_path: await runCase({ ...FORK, error: null }),
      };
      process.stdout.write(JSON.stringify(out));
    })();
    """
).strip()


@pytest.fixture(scope="module", params=sorted(GATE_WORKFLOWS), ids=sorted(GATE_WORKFLOWS))
def comment_outcomes(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:  # pragma: no cover - depends on the host
        message = "node is required to execute the Gate's github-script step"
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)

    workflow = GATE_WORKFLOWS[str(request.param)]
    workdir = tmp_path_factory.mktemp("gate-comment")
    step_path = workdir / "step.js"
    step_path.write_text(_extract_step_script(workflow, COMMENT_STEP_NAME), encoding="utf-8")
    runner_path = workdir / "runner.js"
    runner_path.write_text(COMMENT_RUNNER_JS, encoding="utf-8")

    completed = subprocess.run(
        [node, str(runner_path), str(step_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return dict(json.loads(completed.stdout))


def test_comment_fork_read_only_403_does_not_fail_the_gate(
    comment_outcomes: dict[str, Any],
) -> None:
    case = comment_outcomes["fork_read_only"]
    assert case["threw"] is None, case["threw"]


def test_comment_fork_read_only_403_falls_back_to_the_job_summary(
    comment_outcomes: dict[str, Any],
) -> None:
    case = comment_outcomes["fork_read_only"]
    assert any("read-only" in warning for warning in case["warnings"]), case["warnings"]
    assert "GATE SUMMARY BODY" in " ".join(case["summaryRaw"]), case["summaryRaw"]
    assert "<written>" in case["summaryRaw"]


def test_comment_same_repo_403_still_fails_the_gate(comment_outcomes: dict[str, Any]) -> None:
    case = comment_outcomes["same_repo_read_only"]
    assert case["threw"] is not None
    assert case["threw"]["status"] == 403


def test_comment_non_403_still_fails_the_gate(comment_outcomes: dict[str, Any]) -> None:
    case = comment_outcomes["fork_server_error"]
    assert case["threw"] is not None
    assert case["threw"]["status"] == 500


def test_comment_happy_path_is_silent(comment_outcomes: dict[str, Any]) -> None:
    case = comment_outcomes["happy_path"]
    assert case["threw"] is None
    assert case["warnings"] == []
    assert case["summaryRaw"] == []
