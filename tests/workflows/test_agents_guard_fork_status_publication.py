import json
import pathlib
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).parents[2]
HELPER = ROOT / ".github/scripts/agents-guard-fork-status-publication.js"
TEMPLATE_HELPER = (
    ROOT / "templates/consumer-repo/.github/scripts/agents-guard-fork-status-publication.js"
)
WORKFLOW = ROOT / ".github/workflows/agents-guard-fork-status.yml"
TEMPLATE_WORKFLOW = ROOT / "templates/consumer-repo/.github/workflows/agents-guard-fork-status.yml"
SUPPORTED_GUARD_NAMES = ("guard",)


def _decide(run, jobs, changed_files):
    for job in jobs:
        if job.get("name") == "guard" and "steps" not in job:
            job["steps"] = [
                {"name": "Check event eligibility", "status": "completed", "conclusion": "success"},
                {
                    "name": "Evaluate protected file changes",
                    "status": "completed",
                    "conclusion": "success",
                },
            ]
    source = f"""
const helper = require({json.dumps(str(HELPER))});
const result = helper.publicationState({json.dumps({"run": run, "jobs": jobs, "changedFiles": changed_files})});
process.stdout.write(JSON.stringify(result));
"""
    completed = subprocess.run(["node", "-e", source], check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def _collect_changed_paths(pr, files):
    source = f"""
const helper = require({json.dumps(str(HELPER))});
try {{
  const result = helper.collectChangedPaths({json.dumps(pr)}, {json.dumps(files)});
  process.stdout.write(JSON.stringify({{result}}));
}} catch (error) {{
  process.stdout.write(JSON.stringify({{error: error.message}}));
}}
"""
    completed = subprocess.run(["node", "-e", source], check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def _publish_scenario(
    *,
    final_run=None,
    initial_run_override=None,
    same_repo=False,
    replay=False,
    guard_name="guard",
    base_ref="main",
    status_read_drift=None,
    publisher_attempt="2",
    deny_write=False,
    run_pull_requests=None,
    open_prs=None,
    statuses=None,
    evaluate_status="completed",
    evaluate_conclusion="success",
    run_conclusion="success",
    job_conclusion="success",
):
    initial_run = {
        "id": 9,
        "workflow_id": 7,
        "event": "pull_request",
        "name": "Health 45 Agents Guard",
        "repository": {"id": 1},
        "head_repository": {"id": 1 if same_repo else 2},
        "head_sha": "abc",
        "run_attempt": 1,
        "run_number": 5,
        "status": "completed",
        "conclusion": run_conclusion,
        "html_url": "https://example.test/runs/9",
        "pull_requests": run_pull_requests if run_pull_requests is not None else [{"number": 4}],
    }
    pr = {
        "number": 4,
        "state": "open",
        "changed_files": 1,
        "labels": [],
        "base": {"repo": {"id": 1}, "ref": base_ref},
        "head": {"repo": {"id": 1 if same_repo else 2}, "sha": "abc"},
    }
    scenario = {
        "initialRun": initial_run_override or initial_run,
        "finalRun": final_run or initial_run_override or initial_run,
        "pr": pr,
        "statuses": (
            statuses
            if statuses is not None
            else (
                [
                    {
                        "context": "Health 45 Agents Guard / guard",
                        "state": "success",
                        "description": "Trusted Agents Guard completed successfully [guard-policy-sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855]",
                        "target_url": "https://example.test/runs/9",
                    }
                ]
                if replay
                else []
            )
        ),
        "statusReadDrift": status_read_drift,
        "jobs": [
            {
                "name": guard_name,
                "status": "completed",
                "conclusion": job_conclusion,
                "steps": [
                    {
                        "name": "Check event eligibility",
                        "status": "completed",
                        "conclusion": "success",
                    },
                    {
                        "name": "Evaluate protected file changes",
                        "status": evaluate_status,
                        "conclusion": evaluate_conclusion,
                    },
                ],
            }
        ],
        "denyWrite": deny_write,
        "openPrs": open_prs,
    }
    source = f"""
const helper = require({json.dumps(str(HELPER))});
const scenario = {json.dumps(scenario)};
process.env.GITHUB_RUN_ATTEMPT = {json.dumps(publisher_attempt)};
let runReads = 0;
let statusRead = false;
let currentRun = scenario.finalRun;
let currentPr = scenario.pr;
const writes = [];
const receipts = [];
const endpoint = value => async () => ({{data: value}});
const github = {{
  paginate: async (method, params) => (await method(params)).data,
  rest: {{
    actions: {{
      getWorkflowRun: async () => ({{data: runReads++ === 0 ? scenario.initialRun : currentRun}}),
      getWorkflow: endpoint({{id: 7, path: '.github/workflows/agents-guard.yml'}}),
      listJobsForWorkflowRunAttempt: endpoint(scenario.jobs),
      listWorkflowRuns: async () => ({{data: statusRead && scenario.statusReadDrift === 'newer-run'
        ? [scenario.initialRun, {{...scenario.initialRun, id: 10, run_number: 6}}]
        : [scenario.initialRun]}}),
    }},
    pulls: {{
      get: async () => ({{data: currentPr}}),
      list: endpoint(scenario.openPrs === null ? [scenario.pr] : scenario.openPrs),
      listFiles: endpoint([{{filename: 'src/app.js', status: 'modified'}}]),
    }},
    repos: {{
      listCommitStatusesForRef: async () => {{
        statusRead = true;
        if (scenario.statusReadDrift === 'same-run-attempt') {{
          currentRun = {{...currentRun, run_attempt: 2, status: 'in_progress', conclusion: null}};
        }}
        if (scenario.statusReadDrift === 'pr-head') {{
          currentPr = {{...currentPr, head: {{...currentPr.head, sha: 'new'}}}};
        }}
        return {{data: scenario.statuses}};
      }},
      createCommitStatus: async params => {{ writes.push(params); if (scenario.denyWrite) throw Error('denied status write'); return {{data: {{...params, id: 123}}}}; }},
    }},
  }},
}};
const core = {{info: text => {{if (text.startsWith('AGENTS_GUARD_FORK_STATUS_RECEIPT=')) receipts.push(JSON.parse(text.split('=')[1]));}}, notice: () => {{}}}};
(async () => {{
  try {{
    const result = await helper.publishGuardForkStatus({{
      github,
      core,
      context: {{
        repo: {{owner: 'stranske', repo: 'Workflows'}},
        runId: 99,
        payload: {{workflow_run: {{id: 9}}, repository: {{id: 1, default_branch: 'main'}}}},
      }},
    }});
    process.stdout.write(JSON.stringify({{result, writes, receipts}}));
  }} catch (error) {{
    process.stdout.write(JSON.stringify({{error: error.message, writes}}));
  }}
}})();
"""
    completed = subprocess.run(["node", "-e", source], check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def test_agents_guard_fork_status_publisher_has_trusted_minimal_permissions():
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert data["permissions"] == {
        "actions": "read",
        "contents": "read",
        "pull-requests": "read",
        "statuses": "write",
    }
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "ref: ${{ github.sha }}" in source
    assert "persist-credentials: false" in source
    assert "pull_request_target" not in source
    assert "zizmor: ignore[dangerous-triggers]" in source
    for dependency in (
        "error_classifier.js",
        "github-api-with-retry.js",
        "github-rate-limited-wrapper.js",
        "token_load_balancer.js",
    ):
        assert dependency in source
    helper = HELPER.read_text(encoding="utf-8")
    assert "is not from a fork; the Agents Guard remains its status writer" in helper
    assert "createTokenAwareRetry" in helper
    assert "env: {}" in helper
    assert "maxRetries: 0" in helper


@pytest.mark.parametrize("guard_name", SUPPORTED_GUARD_NAMES)
def test_agents_guard_fork_status_requires_explicit_success_and_complete_guard(guard_name):
    jobs = [{"name": guard_name, "status": "completed", "conclusion": "success"}]
    assert (
        _decide({"status": "completed", "conclusion": "success"}, jobs, ["src/app.py"])["state"]
        == "success"
    )
    assert (
        _decide({"status": "completed", "conclusion": "neutral"}, jobs, ["src/app.py"])["state"]
        == "error"
    )
    assert (
        _decide({"status": "completed", "conclusion": "success"}, [], ["src/app.py"])["state"]
        == "error"
    )
    assert (
        _decide(
            {"status": "completed", "conclusion": "failure"},
            [{"name": guard_name, "status": "completed", "conclusion": "failure"}],
            ["src/app.py"],
        )["state"]
        == "failure"
    )


@pytest.mark.parametrize("guard_name", SUPPORTED_GUARD_NAMES)
def test_agents_guard_fork_status_publishes_success_once_for_bound_evidence(guard_name):
    outcome = _publish_scenario(guard_name=guard_name)
    assert outcome["result"]["state"] == "success"
    assert len(outcome["writes"]) == 1
    assert outcome["writes"][0]["sha"] == "abc"
    assert outcome["writes"][0]["context"] == "Health 45 Agents Guard / guard"


@pytest.mark.parametrize(
    "jobs",
    [
        [],
        [
            {"name": "guard", "status": "completed", "conclusion": "success"},
            {"name": "guard", "status": "completed", "conclusion": "success"},
        ],
        [
            {"name": "guard-other", "status": "completed", "conclusion": "success"},
            {"name": "guard-other", "status": "completed", "conclusion": "success"},
        ],
        [
            {"name": "guard", "status": "completed", "conclusion": "success"},
            {"name": "guard-other", "status": "completed", "conclusion": "success"},
        ],
        [{"name": "Guard", "status": "completed", "conclusion": "success"}],
        [{"name": "Guard-Other", "status": "completed", "conclusion": "success"}],
        [{"name": " gate-guard ", "status": "completed", "conclusion": "success"}],
        [{"name": "gate-guard (3.12)", "status": "completed", "conclusion": "success"}],
        [
            {
                "name": "Health 45 Agents Guard / guard-guard",
                "status": "completed",
                "conclusion": "success",
            }
        ],
    ],
)
def test_agents_guard_fork_status_rejects_missing_ambiguous_or_lookalike_guard(jobs):
    result = _decide({"status": "completed", "conclusion": "success"}, jobs, ["src/app.py"])
    assert result["state"] == "error"
    assert result["description"] == "Agents Guard job set is missing or incomplete"


def test_agents_guard_fork_status_source_and_template_helpers_match():
    assert HELPER.read_bytes() == TEMPLATE_HELPER.read_bytes()
    assert WORKFLOW.read_bytes() == TEMPLATE_WORKFLOW.read_bytes()


def test_agents_guard_fork_status_revalidates_replayed_status_before_returning():
    final_run = {
        "id": 9,
        "workflow_id": 7,
        "event": "pull_request",
        "name": "Health 45 Agents Guard",
        "repository": {"id": 1},
        "head_repository": {"id": 2},
        "head_sha": "abc",
        "run_attempt": 2,
        "run_number": 5,
        "status": "in_progress",
        "conclusion": None,
        "html_url": "https://example.test/runs/9",
        "pull_requests": [{"number": 4}],
    }
    outcome = _publish_scenario(final_run=final_run, replay=True)
    assert outcome["error"] == "Agents Guard run attempt changed before publication"
    assert outcome["writes"] == []


@pytest.mark.parametrize("replay", [False, True])
@pytest.mark.parametrize(
    ("drift", "message"),
    [
        ("same-run-attempt", "Agents Guard run attempt changed before publication"),
        ("newer-run", "Agents Guard run 9 was superseded by 10"),
        ("pr-head", "PR head no longer matches Agents Guard head"),
    ],
)
def test_agents_guard_fork_status_revalidates_after_status_pagination(replay, drift, message):
    outcome = _publish_scenario(replay=replay, status_read_drift=drift)
    assert outcome["error"] == message
    assert outcome["writes"] == []


def test_agents_guard_fork_status_resolves_empty_workflow_run_prs_only_when_head_is_unique():
    unique = _publish_scenario(run_pull_requests=[], open_prs=None)
    assert unique["result"]["state"] == "success"
    assert len(unique["writes"]) == 1

    no_match = _publish_scenario(run_pull_requests=[], open_prs=[])
    assert no_match["error"] == "Expected one open PR at Agents Guard head abc; found 0"
    assert no_match["writes"] == []

    ambiguous = _publish_scenario(
        run_pull_requests=[],
        open_prs=[
            {"number": 4, "state": "open", "head": {"sha": "abc"}},
            {"number": 5, "state": "open", "head": {"sha": "abc"}},
        ],
    )
    assert ambiguous["error"] == "Expected one open PR at Agents Guard head abc; found 2"
    assert ambiguous["writes"] == []


def test_agents_guard_fork_status_skips_same_repo_and_reuses_identical_status():
    same_repo = _publish_scenario(same_repo=True)
    assert same_repo["result"] == {
        "state": "skipped",
        "description": "Same-repository PR",
    }
    assert same_repo["writes"] == []

    replay = _publish_scenario(replay=True)
    assert replay["result"]["state"] == "success"
    assert replay["writes"] == []


def test_agents_guard_fork_status_rejects_non_default_base_branch():
    outcome = _publish_scenario(base_ref="release")
    assert outcome["error"] == "PR base is not the trusted default branch"
    assert outcome["writes"] == []


def test_agents_guard_fork_status_rejects_base_bound_label_event_and_denied_write():
    source = f"""
const helper = require({json.dumps(str(HELPER))});
for (const event of ['pull_request_target', 'workflow_dispatch']) {{
  try {{
    helper.validateBinding({{
      run: {{event, name: 'Health 45 Agents Guard', workflow_id: 7, repository: {{id: 1}}, head_repository: {{id: 2}}, head_sha: 'abc'}},
      workflow: {{id: 7, path: '.github/workflows/agents-guard.yml'}},
      pr: {{state: 'open', base: {{repo: {{id: 1}}, ref: 'main'}}, head: {{repo: {{id: 2}}, sha: 'abc'}}}},
      repository: {{id: 1, default_branch: 'main'}},
    }});
    process.stdout.write('accepted\\n');
  }} catch (error) {{ process.stdout.write(error.message + '\\n'); }}
}}
"""
    completed = subprocess.run(["node", "-e", source], check=True, capture_output=True, text=True)
    assert completed.stdout.splitlines() == [
        "Unexpected Agents Guard event pull_request_target",
        "Unexpected Agents Guard event workflow_dispatch",
    ]
    outcome = _publish_scenario(deny_write=True)
    assert outcome["error"] == "denied status write"
    assert len(outcome["writes"]) == 1


def test_agents_guard_fork_status_blocks_changed_control_surface():
    jobs = [{"name": "guard", "status": "completed", "conclusion": "success"}]
    result = _decide(
        {"status": "completed", "conclusion": "success"},
        jobs,
        [".github/workflows/agents-guard.yml"],
    )
    assert result["state"] == "error"
    assert "controls changed" in result["description"]


def test_agents_guard_fork_status_blocks_renamed_control_surface():
    collected = _collect_changed_paths(
        {"changed_files": 1},
        [
            {
                "filename": "docs/renamed.yml",
                "previous_filename": ".github/workflows/agents-guard.yml",
                "status": "renamed",
            }
        ],
    )
    assert collected == {"result": ["docs/renamed.yml", ".github/workflows/agents-guard.yml"]}
    jobs = [{"name": "guard", "status": "completed", "conclusion": "success"}]
    result = _decide(
        {"status": "completed", "conclusion": "success"},
        jobs,
        collected["result"],
    )
    assert result["state"] == "error"


@pytest.mark.parametrize(
    ("pr", "files", "message"),
    [
        ({"changed_files": 2}, [{"filename": "src/a.py"}], "incomplete"),
        (
            {"changed_files": 2},
            [{"filename": "src/a.py"}, {"filename": "src/a.py"}],
            "malformed or duplicated",
        ),
        (
            {"changed_files": 1},
            [{"filename": "src/new.py", "status": "renamed"}],
            "previous_filename",
        ),
    ],
)
def test_agents_guard_fork_status_rejects_incomplete_or_malformed_file_evidence(pr, files, message):
    assert message in _collect_changed_paths(pr, files)["error"]


def test_agents_guard_fork_status_accepts_complete_3000_file_listing():
    files = [{"filename": f"src/{index}.py"} for index in range(3000)]
    assert _collect_changed_paths({"changed_files": 3000}, files)["result"] == [
        file["filename"] for file in files
    ]


def test_agents_guard_fork_status_binding_rejects_stale_head_sha():
    source = f"""
const helper = require({json.dumps(str(HELPER))});
try {{
  helper.validateBinding({{
    run: {{event: 'pull_request', name: 'Health 45 Agents Guard', workflow_id: 7, repository: {{id: 1}}, head_repository: {{id: 2}}, head_sha: 'old'}},
    workflow: {{id: 7, path: '.github/workflows/agents-guard.yml'}},
    pr: {{state: 'open', base: {{repo: {{id: 1}}, ref: 'main'}}, head: {{repo: {{id: 2}}, sha: 'new'}}}},
    repository: {{id: 1, default_branch: 'main'}},
  }});
  process.exit(2);
}} catch (error) {{
  process.stdout.write(error.message);
}}
"""
    completed = subprocess.run(["node", "-e", source], check=True, capture_output=True, text=True)
    assert completed.stdout == "PR head no longer matches Agents Guard head"


def test_agents_guard_fork_status_rejects_attempt_or_status_drift_before_write():
    source = f"""
const helper = require({json.dumps(str(HELPER))});
const first = {{id: 9, workflow_id: 7, head_sha: 'abc', run_attempt: 1, status: 'completed', conclusion: 'success'}};
for (const changed of [
  {{...first, run_attempt: 2}},
  {{...first, status: 'in_progress', conclusion: null}},
]) {{
  try {{
    helper.assertRunUnchanged(helper.runSnapshot(first), changed);
    process.stdout.write('accepted\\n');
  }} catch (error) {{
    process.stdout.write(error.message + '\\n');
  }}
}}
"""
    completed = subprocess.run(["node", "-e", source], check=True, capture_output=True, text=True)
    lines = completed.stdout.splitlines()
    assert lines == [
        "Agents Guard run attempt changed before publication",
        "Agents Guard run status changed before publication",
    ]


def test_publisher_receipt_binds_status_and_both_run_attempts():
    result = _publish_scenario()
    assert result["receipts"] == [
        {
            "schema": "agents-guard-fork-status/v1",
            "repository": "stranske/Workflows",
            "head": "abc",
            "pr": 4,
            "guard_run_id": 9,
            "guard_run_attempt": 1,
            "publisher_run_id": 99,
            "publisher_run_attempt": 2,
            "status_id": 123,
        }
    ]
    assert result["writes"][0]["description"].endswith(
        "[guard-policy-sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855]"
    )
    assert _publish_scenario(replay=True)["receipts"] == []


@pytest.mark.parametrize("publisher_attempt", ["", "0", "not-an-attempt"])
def test_publisher_requires_real_environment_attempt_before_writing(publisher_attempt):
    result = _publish_scenario(publisher_attempt=publisher_attempt)
    assert "error" in result
    assert "Publisher run attempt is missing or invalid" in result["error"]
    assert result["writes"] == []


def test_agents_guard_fork_status_noop_preserves_existing_failure_but_evaluated_success_can_replace_it():
    previous_failure = [
        {
            "context": "Health 45 Agents Guard / guard",
            "state": "failure",
            "target_url": "https://example.test/runs/old",
        }
    ]
    no_op = _publish_scenario(
        statuses=previous_failure, evaluate_status="completed", evaluate_conclusion="skipped"
    )
    assert no_op["result"]["state"] == "success"
    assert no_op["writes"] == []

    evaluated = _publish_scenario(statuses=previous_failure)
    assert evaluated["result"]["state"] == "success"
    assert len(evaluated["writes"]) == 1


def test_agents_guard_fork_status_noop_creates_missing_required_status():
    no_op = _publish_scenario(evaluate_status="completed", evaluate_conclusion="skipped")
    assert no_op["result"]["state"] == "success"
    assert len(no_op["writes"]) == 1


@pytest.mark.parametrize(
    "steps",
    [
        [],
        [{"name": "Check event eligibility", "status": "completed", "conclusion": "success"}],
        [
            {"name": "Check event eligibility", "status": "completed", "conclusion": "success"},
            {
                "name": "Evaluate protected file changes",
                "status": "completed",
                "conclusion": "success",
            },
            {
                "name": "Evaluate protected file changes",
                "status": "completed",
                "conclusion": "success",
            },
        ],
        [
            {"name": "Check event eligibility", "status": "skipped", "conclusion": "skipped"},
            {
                "name": "Evaluate protected file changes",
                "status": "completed",
                "conclusion": "success",
            },
        ],
    ],
)
def test_agents_guard_fork_status_requires_unambiguous_step_evidence(steps):
    result = _decide(
        {"status": "completed", "conclusion": "success"},
        [{"name": "guard", "status": "completed", "conclusion": "success", "steps": steps}],
        ["src/app.py"],
    )
    assert result["state"] == "error"
    assert "evaluation evidence" in result["description"]


def test_agents_guard_fork_status_rejects_noncompleted_run_before_status_write():
    run = {
        "id": 9,
        "workflow_id": 7,
        "event": "pull_request",
        "name": "Health 45 Agents Guard",
        "repository": {"id": 1},
        "head_repository": {"id": 2},
        "head_sha": "abc",
        "run_attempt": 1,
        "run_number": 5,
        "status": "in_progress",
        "conclusion": None,
        "html_url": "https://example.test/runs/9",
        "pull_requests": [{"number": 4}],
    }
    outcome = _publish_scenario(initial_run_override=run, final_run=run)
    assert outcome["error"] == "Agents Guard run is not completed"
    assert outcome["writes"] == []


def test_agents_guard_fork_status_replays_only_the_newest_context_status_for_reruns():
    same_run = "https://example.test/runs/9"
    failure_after_success = _publish_scenario(
        run_conclusion="failure",
        job_conclusion="failure",
        statuses=[
            {
                "context": "Health 45 Agents Guard / guard",
                "state": "success",
                "target_url": same_run,
            },
            {
                "context": "Health 45 Agents Guard / guard",
                "state": "failure",
                "target_url": same_run,
            },
        ],
    )
    assert failure_after_success["result"]["state"] == "failure"
    assert [write["state"] for write in failure_after_success["writes"]] == ["failure"]

    success_after_failure = _publish_scenario(
        statuses=[
            {
                "context": "Health 45 Agents Guard / guard",
                "state": "failure",
                "target_url": same_run,
            },
            {
                "context": "Health 45 Agents Guard / guard",
                "state": "success",
                "target_url": same_run,
            },
        ]
    )
    assert success_after_failure["result"]["state"] == "success"
    assert [write["state"] for write in success_after_failure["writes"]] == ["success"]


def test_native_pending_label_corrective_survives_same_repo_or_fork_noop_publisher():
    # The publisher does not share the label-writer scheduler: it cannot replace
    # B while A is running and B is the pending revocation corrective.
    same_repo = _publish_scenario(same_repo=True)
    assert same_repo["writes"] == []

    prior_failure = [
        {
            "context": "Health 45 Agents Guard / guard",
            "state": "failure",
            "target_url": "https://example.test/runs/B",
        }
    ]
    fork_noop = _publish_scenario(
        statuses=prior_failure,
        evaluate_status="completed",
        evaluate_conclusion="skipped",
    )
    assert fork_noop["result"]["state"] == "success"
    assert fork_noop["writes"] == []

    protected = _decide(
        {"status": "completed", "conclusion": "success"},
        [{"name": "guard", "status": "completed", "conclusion": "success"}],
        [".github/workflows/agents-guard.yml"],
    )
    assert protected == {
        "state": "error",
        "description": "Agents Guard controls changed; trusted review required",
        "evaluated": False,
    }
