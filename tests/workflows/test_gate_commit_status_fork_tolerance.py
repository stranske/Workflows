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
Node against stubbed ``github``/``context``/``core`` objects. The comment step
uses the real deduplication helper to exercise the authored-head check before
the write. The tests cover both this repo's Gate and the consumer-repo template
because ``pr-00-gate.yml`` is distributed with ``sync_mode: create_only``.
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

    function makeError(status, message, response = null) {
      const e = new Error(message);
      e.status = status;
      if (response !== null) e.response = response;
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
            RESOLVER_RESULT: 'success',
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
        fork_rate_limit_429: await runCase({
          ...FORK, state: 'success',
          error: makeError(429, 'Too many requests'),
        }),
        fork_rate_limit_header_string: await runCase({
          ...FORK, state: 'success',
          error: makeError(403, 'Forbidden', {
            headers: { 'x-ratelimit-remaining': '0' },
          }),
        }),
        fork_rate_limit_header_number: await runCase({
          ...FORK, state: 'success',
          error: makeError(403, 'Forbidden', {
            headers: { 'x-ratelimit-remaining': 0 },
          }),
        }),
        fork_secondary_abuse: await runCase({
          ...FORK, state: 'success',
          error: makeError(403, 'You have triggered an abuse detection mechanism'),
        }),
        fork_secondary_retry_after: await runCase({
          ...FORK, state: 'success',
          error: makeError(403, 'Forbidden', {
            headers: { 'x-ratelimit-remaining': '42', 'retry-after': '60' },
          }),
        }),
        fork_rate_limit_response_body: await runCase({
          ...FORK, state: 'success',
          error: makeError(403, 'Forbidden', {
            data: { message: 'Secondary rate limit exceeded' },
          }),
        }),
        fork_read_only_positive_quota: await runCase({
          ...FORK, state: 'success',
          error: makeError(403, 'Resource not accessible by integration', {
            headers: { 'x-ratelimit-remaining': '42' },
          }),
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
    for key in (
        "fork_rate_limit",
        "fork_rate_limit_429",
        "fork_rate_limit_header_string",
        "fork_rate_limit_header_number",
        "fork_secondary_abuse",
        "fork_secondary_retry_after",
        "fork_rate_limit_response_body",
    ):
        case = outcomes[key]
        assert case["threw"] is None, key
        assert any("Rate limit" in warning for warning in case["warnings"]), key
        assert case["summaryWrites"] == 0, key


def test_positive_quota_permission_403_uses_fork_fallback(
    outcomes: dict[str, Any],
) -> None:
    case = outcomes["fork_read_only_positive_quota"]
    assert case["threw"] is None
    assert any("read-only" in warning for warning in case["warnings"])
    assert case["summaryWrites"] == 1


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

COMMENT_RUNNER_JS = textwrap.dedent("""
    const nodeFs = require('fs');
    const vm = require('vm');
    const src = nodeFs.readFileSync(process.argv[2], 'utf8');
    const commentHelper = require(process.argv[3]);
    const headSha = 'a'.repeat(40);

    function makeError(status, message, response = null) {
      const e = new Error(message);
      e.status = status;
      if (response !== null) e.response = response;
      return e;
    }

    async function runCase({
      headRepo, baseRepo, error, authoredHead = headSha, liveHead = headSha, useResolvedPr = false,
      existingComment = null,
    }) {
      const warnings = [];
      const summaryRaw = [];
      const apiCalls = [];
      const summaryStub = {
        addHeading() { return summaryStub; },
        addRaw(text) { summaryRaw.push(String(text)); return summaryStub; },
        async write() { summaryRaw.push('<written>'); },
      };
      const listComments = async () => ({ data: [] });
      const githubStub = {
        __testMock: true,
        paginate: async (method) => {
          if (method !== listComments) throw new Error('unexpected pagination');
          return existingComment ? [existingComment] : [];
        },
        rest: {
          pulls: {
            get: async ({ pull_number }) => {
              apiCalls.push(['get', pull_number]);
              return { data: { head: { sha: liveHead } } };
            },
          },
          issues: {
            listComments,
            createComment: async ({ issue_number }) => {
              apiCalls.push(['create', issue_number]);
              if (error) throw error;
            },
            updateComment: async ({ comment_id, body }) => {
              apiCalls.push(['update', comment_id, body]);
            },
          },
        },
      };
      const pullRequest = {
        number: 1,
        base: { repo: { full_name: baseRepo } },
      };
      if (authoredHead) {
        pullRequest.head = {
          sha: authoredHead,
          repo: headRepo === null ? null : { full_name: headRepo },
        };
      }
      const sandbox = {
        process: { env: useResolvedPr ? { GATE_PR_JSON: JSON.stringify(pullRequest) } : {} },
        console: { log() {} },
        require: (id) => {
          if (id === 'path') return { resolve: (p) => '/tmp/' + p };
          if (id === 'fs') {
            return {
              existsSync: () => true,
              readFileSync: () =>
                `<!-- gate-summary: pr=1 head=${(authoredHead || liveHead).slice(0, 12)} -->\\n` +
                'GATE SUMMARY BODY',
            };
          }
          if (id === './.github/scripts/comment-dedupe.js') return commentHelper;
          throw new Error(`unexpected require: ${id}`);
        },
        core: { warning: (m) => warnings.push(String(m)), info() {}, summary: summaryStub },
        context: {
          repo: { owner: 'stranske', repo: 'Workflows' },
          eventName: 'pull_request',
          sha: 'c'.repeat(40),
          payload: {
            pull_request: useResolvedPr ? { number: pullRequest.number } : pullRequest,
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
      return { warnings, summaryRaw, apiCalls, threw };
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
      const currentHead = 'b'.repeat(40);
      const existingComment = {
        id: 42,
        body: `<!-- gate-summary: pr=1 head=${headSha.slice(0, 12)} -->\\nOLD SUMMARY`,
      };
      const out = {
        fork_read_only: await runCase({
          ...FORK, error: makeError(403, 'Resource not accessible by integration'),
        }),
        same_repo_read_only: await runCase({
          ...SAME, error: makeError(403, 'Resource not accessible by integration'),
        }),
        fork_rate_limit: await runCase({
          ...FORK, error: makeError(403, 'API rate limit exceeded'),
        }),
        fork_rate_limit_429: await runCase({
          ...FORK, error: makeError(429, 'Too many requests'),
        }),
        fork_rate_limit_header_string: await runCase({
          ...FORK, error: makeError(403, 'Forbidden', {
            headers: { 'x-ratelimit-remaining': '0' },
          }),
        }),
        fork_rate_limit_header_number: await runCase({
          ...FORK, error: makeError(403, 'Forbidden', {
            headers: { 'x-ratelimit-remaining': 0 },
          }),
        }),
        fork_secondary_abuse: await runCase({
          ...FORK, error: makeError(403, 'You have triggered an abuse detection mechanism'),
        }),
        fork_secondary_retry_after: await runCase({
          ...FORK, error: makeError(403, 'Forbidden', {
            headers: { 'x-ratelimit-remaining': '42', 'retry-after': '60' },
          }),
        }),
        fork_rate_limit_response_body: await runCase({
          ...FORK, error: makeError(403, 'Forbidden', {
            data: { message: 'Secondary rate limit exceeded' },
          }),
        }),
        fork_read_only_positive_quota: await runCase({
          ...FORK, error: makeError(403, 'Resource not accessible by integration', {
            headers: { 'x-ratelimit-remaining': '42' },
          }),
        }),
        fork_server_error: await runCase({ ...FORK, error: makeError(500, 'boom') }),
        happy_path: await runCase({ ...FORK, error: null }),
        deleted_fork_head: await runCase({ ...FORK, headRepo: null, error: null }),
        resolved_pr_head: await runCase({ ...FORK, useResolvedPr: true, error: null }),
        missing_head: await runCase({ ...FORK, authoredHead: null, error: null }),
        matching_head_with_existing_comment: await runCase({
          ...FORK, authoredHead: currentHead, liveHead: currentHead, existingComment, error: null,
        }),
        superseded_head: await runCase({
          ...FORK, authoredHead: currentHead, liveHead: 'd'.repeat(40), existingComment, error: null,
        }),
      };
      process.stdout.write(JSON.stringify(out));
    })();
    """).strip()


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
    comment_helper = workflow.parents[1] / "scripts" / "comment-dedupe.js"

    completed = subprocess.run(
        [node, str(runner_path), str(step_path), str(comment_helper)],
        cwd=workdir,
        env={"PATH": os.environ.get("PATH", "")},
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
    assert case["apiCalls"] == [["get", 1], ["create", 1]], case
    assert any("read-only" in warning for warning in case["warnings"]), case["warnings"]
    assert "GATE SUMMARY BODY" in " ".join(case["summaryRaw"]), case["summaryRaw"]
    assert "<written>" in case["summaryRaw"]


def test_comment_same_repo_403_still_fails_the_gate(comment_outcomes: dict[str, Any]) -> None:
    case = comment_outcomes["same_repo_read_only"]
    assert case["apiCalls"] == [["get", 1], ["create", 1]], case
    assert case["threw"] is not None
    assert case["threw"]["status"] == 403


def test_comment_rate_limit_403_never_uses_fork_fallback(
    comment_outcomes: dict[str, Any],
) -> None:
    for key in (
        "fork_rate_limit",
        "fork_rate_limit_429",
        "fork_rate_limit_header_string",
        "fork_rate_limit_header_number",
        "fork_secondary_abuse",
        "fork_rate_limit_response_body",
    ):
        case = comment_outcomes[key]
        assert case["apiCalls"] == [["get", 1], ["create", 1]], case
        assert case["threw"] is None, case
        assert any("Rate limit while creating" in warning for warning in case["warnings"]), case
        assert case["summaryRaw"] == [], key

    # The workflow also recognizes Retry-After when the helper propagates the 403.
    case = comment_outcomes["fork_secondary_retry_after"]
    assert case["threw"]["status"] == 403, case
    assert case["warnings"] == [], case
    assert case["summaryRaw"] == [], case


def test_comment_positive_quota_permission_403_uses_fork_fallback(
    comment_outcomes: dict[str, Any],
) -> None:
    case = comment_outcomes["fork_read_only_positive_quota"]
    assert case["threw"] is None
    assert any("read-only" in warning for warning in case["warnings"])
    assert "GATE SUMMARY BODY" in " ".join(case["summaryRaw"])


def test_comment_non_403_still_fails_the_gate(comment_outcomes: dict[str, Any]) -> None:
    case = comment_outcomes["fork_server_error"]
    assert case["apiCalls"] == [["get", 1], ["create", 1]], case
    assert case["threw"] is not None
    assert case["threw"]["status"] == 500


@pytest.mark.parametrize("name", ["happy_path", "deleted_fork_head", "resolved_pr_head"])
def test_comment_with_matching_authored_head_is_silent(
    comment_outcomes: dict[str, Any], name: str
) -> None:
    case = comment_outcomes[name]
    assert case["apiCalls"] == [["get", 1], ["create", 1]], case
    assert case["threw"] is None
    assert case["warnings"] == []
    assert case["summaryRaw"] == []


def test_comment_with_matching_authored_head_updates_the_existing_summary(
    comment_outcomes: dict[str, Any],
) -> None:
    case = comment_outcomes["matching_head_with_existing_comment"]
    body = f"<!-- gate-summary: pr=1 head={'b' * 12} -->\nGATE SUMMARY BODY"
    assert case["apiCalls"] == [["get", 1], ["update", 42, body]], case
    assert case["threw"] is None, case
    assert case["warnings"] == [], case
    assert case["summaryRaw"] == [], case


def test_comment_with_missing_or_superseded_head_is_skipped(
    comment_outcomes: dict[str, Any],
) -> None:
    missing = comment_outcomes["missing_head"]
    assert missing["apiCalls"] == [], missing
    assert missing["warnings"] == [
        "Gate summary has no matching authored PR head; skipping comment update."
    ], missing
    superseded = comment_outcomes["superseded_head"]
    assert superseded["apiCalls"] == [["get", 1]], superseded
    for case in (missing, superseded):
        assert case["threw"] is None, case
        assert case["summaryRaw"] == [], case


@pytest.mark.parametrize("name", sorted(GATE_WORKFLOWS))
def test_primary_gate_summary_keeps_cancelled_run_status_publication(name):
    workflow = yaml.safe_load(GATE_WORKFLOWS[name].read_text(encoding="utf-8"))
    summary = workflow["jobs"]["summary"]
    # Unlike optional log diagnostics, this job must supersede prior same-head
    # SUCCESS with a non-success result when a rerun is cancelled.
    assert summary["if"].replace(" ", "") == "${{always()}}"
    publisher = next(step for step in summary["steps"] if step.get("name") == STEP_NAME)
    assert publisher["if"].replace(" ", "") == "${{always()}}"
