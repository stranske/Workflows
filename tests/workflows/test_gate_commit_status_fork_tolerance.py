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
    const commentDedupe = require(process.argv[3]);
    const HEAD_SHA = 'a'.repeat(40);
    const NEXT_HEAD_SHA = 'c'.repeat(40);
    const SAME_PREFIX_HEAD_SHA = HEAD_SHA.slice(0, 12) + 'd'.repeat(28);

    function makeError(status, message, response = null) {
      const e = new Error(message);
      e.status = status;
      if (response !== null) e.response = response;
      return e;
    }

    async function runCase({
      headRepo, baseRepo, error, eventHead = HEAD_SHA, liveHead = HEAD_SHA, resolvedHead,
      summaryHead = resolvedHead ?? eventHead,
    }) {
      const headMarker = summaryHead ? ` head=${summaryHead.slice(0, 12)}` : '';
      const summaryBody = `GATE SUMMARY BODY\\n<!-- gate-summary: pr=1${headMarker} -->`;
      const warnings = [];
      const summaryRaw = [];
      const headReads = [];
      let commentAttempts = 0;
      let summaryWrites = 0;
      const summaryStub = {
        addHeading() { return summaryStub; },
        addRaw(text) { summaryRaw.push(String(text)); return summaryStub; },
        async write() { summaryWrites += 1; },
      };
      const github = {
        __testMock: true,
        paginate: async () => [],
        rest: {
          pulls: {
            get: async ({ pull_number }) => {
              headReads.push(pull_number);
              return { data: { head: { sha: liveHead } } };
            },
          },
          issues: {
            listComments: async () => ({ data: [] }),
            createComment: async () => {
              commentAttempts += 1;
              if (error) throw error;
            },
          },
        },
      };
      const pullRequest = {
        number: 1,
        head: { sha: eventHead, repo: { full_name: headRepo } },
        base: { repo: { full_name: baseRepo } },
      };
      // The reported consumer fixture only provided the PR number.
      const eventPr = eventHead === null ? { number: pullRequest.number } : pullRequest;
      const env = {};
      if (resolvedHead) {
        env.GATE_PR_JSON = JSON.stringify({
          ...pullRequest, head: { ...pullRequest.head, sha: resolvedHead },
        });
      }
      const sandbox = {
        process: { env },
        console: { log() {} },
        require: (id) => {
          if (id === 'path') return { resolve: (p) => '/tmp/' + p };
          if (id === 'fs') {
            return {
              existsSync: () => true,
              readFileSync: () => summaryBody,
            };
          }
          if (id === './.github/scripts/comment-dedupe.js') return commentDedupe;
          throw new Error(`Unexpected require: ${id}`);
        },
        core: {
          info() {},
          warning: (m) => warnings.push(String(m)),
          summary: summaryStub,
        },
        context: {
          eventName: 'pull_request',
          repo: { owner: 'stranske', repo: 'Workflows' },
          sha: 'b'.repeat(40),
          payload: { pull_request: eventPr },
        },
        github,
      };
      vm.createContext(sandbox);
      let threw = null;
      try {
        await vm.runInContext('(async () => {\\n' + src + '\\n})()', sandbox);
      } catch (e) {
        threw = { status: e.status === undefined ? null : e.status, message: String(e.message) };
      }
      return { warnings, summaryRaw, summaryWrites, threw, commentAttempts, headReads };
    }

    const FORK = {
      headRepo: 'outside-contributor/Workflows',
      baseRepo: 'stranske/Workflows',
    };
    const READ_ONLY_FORK = {
      ...FORK, error: makeError(403, 'Resource not accessible by integration'),
    };
    const SAME = {
      headRepo: 'stranske/Workflows',
      baseRepo: 'stranske/Workflows',
    };

    (async () => {
      const out = {
        fork_read_only: await runCase(READ_ONLY_FORK),
        fork_read_only_legacy_summary: await runCase({ ...READ_ONLY_FORK, summaryHead: null }),
        fork_read_only_new_head: await runCase({
          ...READ_ONLY_FORK, eventHead: NEXT_HEAD_SHA, liveHead: NEXT_HEAD_SHA,
        }),
        fork_read_only_resolved_head: await runCase({
          ...READ_ONLY_FORK, eventHead: null, resolvedHead: HEAD_SHA,
        }),
        fork_read_only_resolved_head_legacy_summary: await runCase({
          ...READ_ONLY_FORK, eventHead: null, resolvedHead: NEXT_HEAD_SHA,
          liveHead: NEXT_HEAD_SHA, summaryHead: null,
        }),
        fork_read_only_resolved_stale_event: await runCase({
          ...READ_ONLY_FORK, eventHead: 'd'.repeat(40), resolvedHead: HEAD_SHA,
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
        fork_written: await runCase(FORK),
        same_repo_written: await runCase(SAME),
        missing_head: await runCase({ ...READ_ONLY_FORK, eventHead: null }),
        missing_head_with_summary_marker: await runCase({
          ...READ_ONLY_FORK, eventHead: null, summaryHead: HEAD_SHA,
        }),
        stale_head: await runCase({ ...FORK, liveHead: NEXT_HEAD_SHA }),
        stale_head_with_current_summary_marker: await runCase({
          ...FORK, liveHead: NEXT_HEAD_SHA, summaryHead: NEXT_HEAD_SHA,
        }),
        stale_head_with_matching_short_sha: await runCase({ ...FORK, liveHead: SAME_PREFIX_HEAD_SHA }),
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

    completed = subprocess.run(
        [
            node,
            str(runner_path),
            str(step_path),
            str(REPO_ROOT / ".github/scripts/comment-dedupe.js"),
        ],
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


@pytest.mark.parametrize(
    "name",
    [
        "fork_read_only",
        "fork_read_only_legacy_summary",
        "fork_read_only_new_head",
        "fork_read_only_resolved_head",
        "fork_read_only_resolved_head_legacy_summary",
        "fork_read_only_resolved_stale_event",
        "fork_read_only_positive_quota",
    ],
)
def test_comment_fork_read_only_403_falls_back_to_the_job_summary(
    comment_outcomes: dict[str, Any], name: str
) -> None:
    case = comment_outcomes[name]
    assert case["threw"] is None, case
    assert case["summaryWrites"] == 1, case
    assert case["headReads"] == [1], case
    assert case["commentAttempts"] == 1, case
    assert len(case["warnings"]) == 1, case
    assert "read-only" in case["warnings"][0], case
    assert "GATE SUMMARY BODY" in " ".join(case["summaryRaw"]), case["summaryRaw"]


def test_comment_same_repo_403_still_fails_the_gate(comment_outcomes: dict[str, Any]) -> None:
    case = comment_outcomes["same_repo_read_only"]
    assert case["commentAttempts"] == 1, case
    assert case["threw"] is not None
    assert case["threw"]["status"] == 403
    assert case["summaryWrites"] == 0, case


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
        assert case["commentAttempts"] == 1, case
        assert case["threw"] is None, case
        assert any("Rate limit" in warning for warning in case["warnings"]), case
        assert case["summaryRaw"] == [], key

    # The helper rethrows a retry-after-only 403, which the workflow must also distinguish
    # from a fork permission refusal.
    case = comment_outcomes["fork_secondary_retry_after"]
    assert case["threw"]["status"] == 403, case
    assert case["warnings"] == [], case
    assert case["summaryRaw"] == [], case


def test_comment_non_403_still_fails_the_gate(comment_outcomes: dict[str, Any]) -> None:
    case = comment_outcomes["fork_server_error"]
    assert case["threw"] is not None
    assert case["threw"]["status"] == 500


@pytest.mark.parametrize("name", ["fork_written", "same_repo_written"])
def test_comment_happy_path_is_silent(comment_outcomes: dict[str, Any], name: str) -> None:
    case = comment_outcomes[name]
    assert case["headReads"] == [1], case
    assert case["commentAttempts"] == 1, case
    assert case["threw"] is None
    assert case["warnings"] == []
    assert case["summaryRaw"] == []
    assert case["summaryWrites"] == 0, case


@pytest.mark.parametrize(
    ("name", "head_reads", "warnings"),
    [
        (
            "missing_head",
            [],
            ["Gate summary has no matching authored PR head; skipping comment update."],
        ),
        (
            "missing_head_with_summary_marker",
            [],
            ["Gate summary has no matching authored PR head; skipping comment update."],
        ),
        ("stale_head", [1], []),
        ("stale_head_with_current_summary_marker", [1], []),
        ("stale_head_with_matching_short_sha", [1], []),
    ],
)
def test_comment_requires_current_authored_head(
    comment_outcomes: dict[str, Any], name: str, head_reads: list[int], warnings: list[str]
) -> None:
    case = comment_outcomes[name]
    assert case["headReads"] == head_reads, case
    assert case["commentAttempts"] == 0, case
    assert case["threw"] is None, case
    assert case["summaryRaw"] == [], case
    assert case["summaryWrites"] == 0, case
    assert case["warnings"] == warnings, case


@pytest.mark.parametrize("name", sorted(GATE_WORKFLOWS))
def test_primary_gate_summary_keeps_cancelled_run_status_publication(name):
    workflow = yaml.safe_load(GATE_WORKFLOWS[name].read_text(encoding="utf-8"))
    summary = workflow["jobs"]["summary"]
    # Unlike optional log diagnostics, this job must supersede prior same-head
    # SUCCESS with a non-success result when a rerun is cancelled.
    assert summary["if"].replace(" ", "") == "${{always()}}"
    publisher = next(step for step in summary["steps"] if step.get("name") == STEP_NAME)
    assert publisher["if"].replace(" ", "") == "${{always()}}"
