"""Mocked auto-pilot verification-handoff runs for missing / paginated / found PRs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = (
    ROOT / ".github/workflows/agents-auto-pilot.yml",
    ROOT / "templates/consumer-repo/.github/workflows/agents-auto-pilot.yml",
)


@pytest.fixture(params=WORKFLOWS, ids=("root", "consumer"))
def workflow(request: pytest.FixtureRequest) -> Path:
    return request.param


ISSUE_NUMBER = 42
MERGED_HEAD_SHA = "c" * 40
UNRELATED_HEAD_SHA = "d" * 40


def _extract_verify_script(workflow: Path) -> str:
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    for job in document["jobs"].values():
        for step in job.get("steps") or []:
            if step.get("id") == "verify_step":
                return str(step["with"]["script"])
    raise AssertionError("agents-auto-pilot.yml no longer defines verify_step")


def _run_verify(
    prs: list[dict[str, Any]],
    workflow: Path,
    *,
    pr_labels: tuple[str, ...] = (),
    fail_on_page: int | None = None,
    dispatch_unavailable: bool = False,
    existing_runs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute the workflow verify_step script against a mocked pulls.list result set."""
    node = shutil.which("node")
    if node is None:  # pragma: no cover - host dependent
        message = "node is required to execute the auto-pilot verify handoff script"
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)

    script = _extract_verify_script(workflow)
    harness = r"""
const fixture = JSON.parse(process.env.FIXTURE);
const outputs = {};
const failures = [];
const labelsAdded = [];
const labelsCreated = [];
const labelsRemoved = [];
const comments = [];
const pageCalls = [];
const dispatchCalls = [];
const runQueries = [];
const knownLabels = new Set(fixture.knownLabels || []);
const prLabels = new Set(fixture.prLabels || []);
let scriptError = null;

const core = {
  setOutput(name, value) { outputs[name] = String(value); },
  setFailed(message) { failures.push(String(message)); },
  info() {},
  warning() {},
};

const context = {
  repo: { owner: 'stranske', repo: 'Workflows' },
};

const github = {
  rest: {
    pulls: {
      list: async (params) => {
        const page = Number(params.page) || 1;
        const perPage = Number(params.per_page) || 100;
        pageCalls.push({ page, per_page: perPage, state: params.state });
        if (page === fixture.failOnPage) {
          throw new Error('Later PR page is unavailable');
        }
        const start = (page - 1) * perPage;
        return { data: fixture.prs.slice(start, start + perPage) };
      },
      get: async (params) => ({
        data: {
          ...fixture.prs.find(pr => pr.number === params.pull_number),
          labels: [...prLabels].map(name => ({ name })),
        },
      }),
    },
    repos: {
      get: async () => ({ data: { default_branch: 'main' } }),
    },
    actions: {
      listWorkflowRuns: async (params) => {
        runQueries.push(params);
        const runs = (fixture.existingRuns || []).filter((run) => {
          if (params.head_sha && run.head_sha !== params.head_sha) {
            return false;
          }
          if (
            params.workflow_id
            && run.path
            && !String(run.path).includes(String(params.workflow_id).replace('.yml', ''))
          ) {
            return false;
          }
          return true;
        });
        return { data: { total_count: runs.length, workflow_runs: runs } };
      },
      createWorkflowDispatch: async (params) => {
        dispatchCalls.push(params);
        if (!fixture.dispatchUnavailable) return { status: 204 };
        const error = new Error('No triggering credential is available');
        error.status = 403;
        throw error;
      },
    },
    issues: {
      createComment: async (params) => {
        comments.push({ issue_number: params.issue_number, body: params.body });
        return { data: {} };
      },
      getLabel: async (params) => {
        if (knownLabels.has(params.name)) {
          return { data: { name: params.name } };
        }
        const err = new Error(`Label not found: ${params.name}`);
        err.status = 404;
        throw err;
      },
      createLabel: async (params) => {
        labelsCreated.push(params.name);
        knownLabels.add(params.name);
        return { data: { name: params.name } };
      },
      addLabels: async (params) => {
        for (const name of params.labels) {
          if (!knownLabels.has(name)) {
            const err = new Error(`Label not found: ${name}`);
            err.status = 404;
            throw err;
          }
        }
        labelsAdded.push({
          issue_number: params.issue_number,
          labels: [...params.labels],
        });
        // The API succeeds even when every requested PR label already exists.
        if (fixture.prs.some(pr => pr.number === params.issue_number)) {
          for (const name of params.labels) prLabels.add(name);
        }
        return { data: [...prLabels].map(name => ({ name })) };
      },
      removeLabel: async (params) => {
        labelsRemoved.push({
          issue_number: params.issue_number,
          name: params.name,
        });
        return { data: {} };
      },
    },
  },
};

const withRetry = async (fn) => fn(github);

const requireStub = (name) => {
  if (name === './.github/scripts/github-api-with-retry.js') {
    return {
      createTokenAwareRetry: async () => ({ withRetry }),
    };
  }
  throw new Error('Unexpected require: ' + name);
};

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
try {
await new AsyncFunction('require', 'github', 'context', 'core', 'process', process.env.SCRIPT)(
  requireStub,
  github,
  context,
  core,
  process,
);
} catch (error) {
  scriptError = error.message;
}

process.stdout.write(JSON.stringify({
  outputs,
  failures,
  labelsAdded,
  labelsCreated,
  labelsRemoved,
  comments,
  pageCalls,
  dispatchCalls,
  runQueries,
  scriptError,
}));
"""
    completed = subprocess.run(
        [node, "--input-type=module", "-e", harness],
        cwd=ROOT,
        env={
            **os.environ,
            "SCRIPT": script,
            "ISSUE_NUMBER": str(ISSUE_NUMBER),
            "FIXTURE": json.dumps(
                {
                    "prs": prs,
                    "knownLabels": list(pr_labels),
                    "prLabels": list(pr_labels),
                    "failOnPage": fail_on_page,
                    "dispatchUnavailable": dispatch_unavailable,
                    "existingRuns": existing_runs or [],
                }
            ),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    allowed_errors = (
        (None, "No triggering credential is available") if dispatch_unavailable else (None,)
    )
    assert result["scriptError"] in allowed_errors, result["scriptError"]
    return result


def _filler_prs(count: int) -> list[dict[str, Any]]:
    return [
        {
            "number": 1000 + index,
            "merged_at": "2026-01-01T00:00:00Z",
            "title": f"Unrelated #{1000 + index}",
            "body": "Closes #9999",
        }
        for index in range(count)
    ]


def _matching_pr(number: int) -> dict[str, Any]:
    return {
        "number": number,
        "merged_at": "2026-02-01T00:00:00Z",
        "title": f"Fix closes #{ISSUE_NUMBER}",
        "body": f"<!-- meta:issue:{ISSUE_NUMBER} -->\nCloses #{ISSUE_NUMBER}",
        "head": {"sha": MERGED_HEAD_SHA},
        "merge_commit_sha": MERGED_HEAD_SHA,
    }


def test_handoff_missing_pr_keeps_auto_pilot_and_skips_verify_label(workflow: Path) -> None:
    """Zero matching PRs: no verify:evaluate, keep agents:auto-pilot, name source issue."""
    result = _run_verify([], workflow)

    assert result["outputs"].get("verify_handoff") == "absent"
    assert result["outputs"].get("verify_handoff_issue") == str(ISSUE_NUMBER)
    assert result["labelsAdded"] == []
    assert all(entry["name"] != "agents:auto-pilot" for entry in result["labelsRemoved"])
    assert any(f"#{ISSUE_NUMBER}" in failure for failure in result["failures"])
    assert any(
        comment["issue_number"] == ISSUE_NUMBER and f"#{ISSUE_NUMBER}" in comment["body"]
        for comment in result["comments"]
    )
    assert not any(
        "verify:evaluate" in label for entry in result["labelsAdded"] for label in entry["labels"]
    )


def test_handoff_pr_beyond_first_page_is_found_not_absent_verified(workflow: Path) -> None:
    """Matching PR past the first 100 results must be found, never absent-as-verified."""
    result = _run_verify(_filler_prs(100) + [_matching_pr(777)], workflow)

    assert result["outputs"].get("verify_handoff") == "found"
    assert result["outputs"].get("verify_handoff_issue") == str(ISSUE_NUMBER)
    assert {call["page"] for call in result["pageCalls"]} >= {1, 2}
    assert any(
        entry["issue_number"] == 777 and "verify:evaluate" in entry["labels"]
        for entry in result["labelsAdded"]
    )
    assert any(
        entry["issue_number"] == ISSUE_NUMBER
        and "verify:pr-handoff" in entry["labels"]
        and "verify:evaluate" in entry["labels"]
        for entry in result["labelsAdded"]
    )


def test_handoff_truncated_lookup_reports_incomplete_not_verified(workflow: Path) -> None:
    """Full maxPages of non-matching PRs is incomplete, never a verified handoff."""
    result = _run_verify(_filler_prs(1000), workflow)

    assert result["outputs"].get("verify_handoff") == "incomplete"
    assert result["outputs"].get("verify_handoff_issue") == str(ISSUE_NUMBER)
    assert result["labelsAdded"] == []
    assert any("incomplete" in failure for failure in result["failures"])
    assert any(f"#{ISSUE_NUMBER}" in failure for failure in result["failures"])
    assert max(call["page"] for call in result["pageCalls"]) == 10
    assert [call["page"] for call in result["pageCalls"]] == list(range(1, 11))


@pytest.mark.parametrize("already_labeled", [False, True], ids=("fallback", "already-labeled"))
def test_handoff_requires_dispatched_or_existing_verifier_run(
    workflow: Path, already_labeled: bool
) -> None:
    """A successful label write alone cannot authorize either completion marker."""
    result = _run_verify(
        [_matching_pr(555)],
        workflow,
        pr_labels=("verify:evaluate",) if already_labeled else (),
        dispatch_unavailable=True,
    )

    assert not any(
        entry["issue_number"] == ISSUE_NUMBER and "verify:pr-handoff" in entry["labels"]
        for entry in result["labelsAdded"]
    ), "Issue handoff marker was recorded without a dispatched or existing verifier run"
    assert (
        result["outputs"].get("verify_handoff") != "found"
    ), "Report - Done treats verify_handoff=found as a completed verifier handoff"
    assert result["scriptError"] is None
    assert len(result["dispatchCalls"]) == 1
    assert result["failures"]
    assert result["labelsAdded"] == []


def test_handoff_page_one_match_stops_search_immediately(workflow: Path) -> None:
    """Even ten full pages must cost one request when the first page matches."""
    result = _run_verify([_matching_pr(555)] + _filler_prs(999), workflow)

    assert [call["page"] for call in result["pageCalls"]] == [1]


def test_handoff_page_one_match_does_not_request_failing_later_page(workflow: Path) -> None:
    """A later API failure cannot invalidate an already found merged PR."""
    result = _run_verify(
        [_matching_pr(555)] + _filler_prs(999),
        workflow,
        fail_on_page=2,
    )

    assert [call["page"] for call in result["pageCalls"]] == [1]


def test_handoff_successful_pr_bound_labels_merged_pr_and_issue(workflow: Path) -> None:
    result = _run_verify([_matching_pr(555)], workflow)

    assert result["outputs"].get("verify_handoff") == "found"
    assert result["outputs"].get("verify_handoff_issue") == str(ISSUE_NUMBER)
    assert result["failures"] == []
    assert set(result["labelsCreated"]) >= {"verify:evaluate", "verify:pr-handoff"}
    assert any(
        entry["issue_number"] == 555 and entry["labels"] == ["verify:evaluate"]
        for entry in result["labelsAdded"]
    )
    assert any(
        entry["issue_number"] == ISSUE_NUMBER
        and entry["labels"] == ["verify:evaluate", "verify:pr-handoff"]
        for entry in result["labelsAdded"]
    )
    assert all(entry["name"] != "agents:auto-pilot" for entry in result["labelsRemoved"])


def _verifier_run(
    *, head_sha: str, status: str = "completed", conclusion: str = "success"
) -> dict[str, Any]:
    return {
        "id": 9001,
        "head_sha": head_sha,
        "status": status,
        "conclusion": conclusion,
        "path": ".github/workflows/agents-verifier.yml",
        "event": "pull_request_target",
        "pull_requests": [{"number": 555, "head": {"sha": head_sha}}],
    }


def test_handoff_dispatches_verifier_before_recording_markers(workflow: Path) -> None:
    result = _run_verify([_matching_pr(555)], workflow)

    assert result["dispatchCalls"] == [
        {
            "owner": "stranske",
            "repo": "Workflows",
            "workflow_id": "agents-verifier.yml",
            "ref": "main",
            "inputs": {"pr_number": "555", "pr_head_sha": MERGED_HEAD_SHA, "mode": "evaluate"},
        }
    ]
    assert result["failures"] == []
    assert result["outputs"].get("verify_handoff") == "found"


def test_handoff_existing_verifier_run_authorizes_without_dispatch(workflow: Path) -> None:
    run = _verifier_run(head_sha=MERGED_HEAD_SHA)
    run.update(
        event="workflow_dispatch",
        pull_requests=[],
        display_title=f"Verifier PR #555 head={MERGED_HEAD_SHA} mode=evaluate",
    )
    result = _run_verify(
        [_matching_pr(555)],
        workflow,
        dispatch_unavailable=True,
        existing_runs=[run],
    )

    assert result["scriptError"] is None
    assert result["failures"] == []
    assert result["dispatchCalls"] == []
    assert result["outputs"].get("verify_handoff") == "found"
    assert any(
        entry["issue_number"] == ISSUE_NUMBER and "verify:pr-handoff" in entry["labels"]
        for entry in result["labelsAdded"]
    )


def test_handoff_unrelated_verifier_run_does_not_authorize_handoff(workflow: Path) -> None:
    result = _run_verify(
        [_matching_pr(555)],
        workflow,
        dispatch_unavailable=True,
        existing_runs=[_verifier_run(head_sha=UNRELATED_HEAD_SHA)],
    )

    assert len(result["dispatchCalls"]) == 1
    assert result["outputs"].get("verify_handoff") != "found"
    assert not any(
        entry["issue_number"] == ISSUE_NUMBER and "verify:pr-handoff" in entry["labels"]
        for entry in result["labelsAdded"]
    )


@pytest.mark.parametrize(
    "binding",
    [
        [],
        [{"number": 556, "head": {"sha": MERGED_HEAD_SHA}}],
        [{"number": 555, "head": {"sha": UNRELATED_HEAD_SHA}}],
    ],
    ids=("unbound", "wrong-pr", "wrong-pr-head"),
)
def test_handoff_same_sha_without_target_pr_binding_is_not_reused(
    workflow: Path, binding: list[dict[str, Any]]
) -> None:
    run = _verifier_run(head_sha=MERGED_HEAD_SHA)
    run["pull_requests"] = binding
    result = _run_verify(
        [_matching_pr(555)], workflow, dispatch_unavailable=True, existing_runs=[run]
    )
    assert len(result["dispatchCalls"]) == 1
    assert result["outputs"].get("verify_handoff") != "found"
    assert result["labelsAdded"] == []
    assert result["failures"]


def test_handoff_reuses_dispatched_run_on_default_branch(workflow: Path) -> None:
    run = _verifier_run(head_sha=UNRELATED_HEAD_SHA)
    run.update(
        event="workflow_dispatch",
        pull_requests=[],
        display_title=f"Verifier PR #555 head={MERGED_HEAD_SHA} mode=evaluate",
    )
    result = _run_verify(
        [_matching_pr(555)], workflow, dispatch_unavailable=True, existing_runs=[run]
    )
    assert result["dispatchCalls"] == []
    assert result["outputs"].get("verify_handoff") == "found"
    assert result["failures"] == []


@pytest.mark.parametrize("provenance_only", [False, True], ids=("evaluation", "provenance-only"))
@pytest.mark.parametrize("status", ["queued", "in_progress", "completed"])
def test_handoff_excludes_provenance_only_dispatch(
    workflow: Path, provenance_only: bool, status: str
) -> None:
    # Render the caller's actual run-name so removing its suffix breaks this proof.
    title = yaml.safe_load(workflow.with_name("agents-verifier.yml").read_text())["run-name"]
    for expression, value in (
        ("${{ inputs.pr_number || github.event.pull_request.number }}", "555"),
        ("${{ inputs.pr_head_sha || github.event.pull_request.head.sha }}", MERGED_HEAD_SHA),
        ("${{ inputs.mode || 'label' }}", "evaluate"),
        (
            "${{ inputs.verification_provenance != '' && ' provenance-only' || '' }}",
            " provenance-only" if provenance_only else "",
        ),
    ):
        title = title.replace(expression, value)
    assert "${{" not in title
    run = _verifier_run(head_sha=UNRELATED_HEAD_SHA, status=status)
    run.update(event="workflow_dispatch", pull_requests=[], display_title=title)
    result = _run_verify(
        [_matching_pr(555)], workflow, dispatch_unavailable=True, existing_runs=[run]
    )
    assert len(result["dispatchCalls"]) == int(provenance_only)
    if provenance_only:
        assert result["outputs"].get("verify_handoff") != "found"
        assert result["labelsAdded"] == []
        assert result["failures"]
    else:
        assert result["outputs"].get("verify_handoff") == "found"
        assert result["failures"] == []


@pytest.mark.parametrize("conclusion", ["cancelled", "skipped", "failure"])
def test_handoff_unsuccessful_run_does_not_authorize(workflow: Path, conclusion: str) -> None:
    result = _run_verify(
        [_matching_pr(555)],
        workflow,
        dispatch_unavailable=True,
        existing_runs=[_verifier_run(head_sha=MERGED_HEAD_SHA, conclusion=conclusion)],
    )
    assert len(result["dispatchCalls"]) == 1
    assert result["outputs"].get("verify_handoff") != "found"
    assert result["labelsAdded"] == []


@pytest.mark.parametrize(
    "wrong_title",
    [
        f"Verifier PR #556 head={MERGED_HEAD_SHA} mode=evaluate",
        f"Verifier PR #555 head={UNRELATED_HEAD_SHA} mode=evaluate",
        f"Verifier PR #555 head={MERGED_HEAD_SHA} mode=checkbox",
    ],
)
def test_handoff_dispatched_run_requires_exact_pr_head_and_mode(
    workflow: Path, wrong_title: str
) -> None:
    run = _verifier_run(head_sha=UNRELATED_HEAD_SHA)
    run.update(event="workflow_dispatch", pull_requests=[], display_title=wrong_title)
    result = _run_verify(
        [_matching_pr(555)], workflow, dispatch_unavailable=True, existing_runs=[run]
    )
    assert len(result["dispatchCalls"]) == 1
    assert result["outputs"].get("verify_handoff") != "found"
    assert result["labelsAdded"] == []


def test_verifier_entry_point_exposes_dispatch_binding(workflow: Path) -> None:
    verifier = workflow.with_name("agents-verifier.yml")
    document = yaml.safe_load(verifier.read_text())
    assert document["run-name"] == (
        "Verifier PR #${{ inputs.pr_number || github.event.pull_request.number }} "
        "head=${{ inputs.pr_head_sha || github.event.pull_request.head.sha }} "
        "mode=${{ inputs.mode || 'label' }}"
        "${{ inputs.verification_provenance != '' && ' provenance-only' || '' }}"
    )
    inputs = document.get("on", document.get(True))["workflow_dispatch"]["inputs"]
    assert inputs["pr_head_sha"]["required"] is False
    verify = yaml.safe_load(workflow.read_text())
    step = next(
        step
        for job in verify["jobs"].values()
        for step in job.get("steps", [])
        if step.get("id") == "verify_step"
    )
    assert step["with"]["github-token"] == "${{ steps.app_token.outputs.token || github.token }}"


@pytest.mark.parametrize("matches_head", [True, False], ids=("matches", "stale"))
def test_verifier_dispatch_checks_expected_head(workflow: Path, matches_head: bool) -> None:
    verifier = yaml.safe_load(workflow.with_name("agents-verifier.yml").read_text())
    script = next(
        step["with"]["script"]
        for step in verifier["jobs"]["check"]["steps"]
        if step.get("id") == "check"
    )
    # Execute the actual dispatch entry branch, with its normal setup already done.
    script = script.split("// Handle workflow_dispatch trigger", 1)[1]
    script = script.split("// Handle pull_request_target trigger", 1)[0]
    harness = r"""
const outputs = {}, failures = [];
const core = { setOutput: (k,v) => outputs[k]=v, setFailed: s => failures.push(s), info() {} };
const context = {eventName:'workflow_dispatch', repo:{owner:'stranske',repo:'Workflows'},
  payload:{inputs:{pr_number:'555',mode:'evaluate',pr_head_sha:process.env.EXPECTED_HEAD}}};
const client = {rest:{pulls:{get:async()=>({data:{merged:true,head:{sha:process.env.PR_HEAD}}})}}};
const withRetry = async fn => fn(client);
const setPlanSourceFingerprint = async () => true;
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
await new AsyncFunction('context','core','withRetry','setPlanSourceFingerprint',process.env.SCRIPT)(
  context,core,withRetry,setPlanSourceFingerprint);
process.stdout.write(JSON.stringify({outputs,failures}));
"""
    node = shutil.which("node")
    if node is None:  # pragma: no cover - host dependent
        message = "node is required to execute the verifier dispatch script"
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)
    completed = subprocess.run(
        [node, "--input-type=module", "-e", harness],
        env={
            **os.environ,
            "SCRIPT": script,
            "PR_HEAD": MERGED_HEAD_SHA,
            "EXPECTED_HEAD": MERGED_HEAD_SHA if matches_head else UNRELATED_HEAD_SHA,
        },
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    result = json.loads(completed.stdout)
    assert result["outputs"]["should_run"] == ("true" if matches_head else "false")
    assert bool(result["failures"]) is not matches_head


@pytest.mark.parametrize("status", ["queued", "in_progress", "completed"])
def test_noop_label_run_cannot_authorize_handoff(workflow: Path, status: str) -> None:
    run = _verifier_run(head_sha=MERGED_HEAD_SHA, status=status)
    result = _run_verify(
        [_matching_pr(555)],
        workflow,
        pr_labels=("verify:evaluate",),
        dispatch_unavailable=True,
        existing_runs=[run],
    )
    assert len(result["dispatchCalls"]) == 1
    assert result["outputs"].get("verify_handoff") != "found"
    assert result["labelsAdded"] == []
    assert result["failures"]
