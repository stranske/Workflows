import json
import pathlib
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).parents[2]
HELPER = ROOT / ".github/scripts/gate-fork-status-publication.js"
TEMPLATE_HELPER = ROOT / "templates/consumer-repo/.github/scripts/gate-fork-status-publication.js"
WORKFLOW = ROOT / ".github/workflows/pr-00-gate-fork-status.yml"
SUPPORTED_SUMMARY_NAMES = ("summary", "gate-summary")


def _decide(run, jobs, changed_files):
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
    same_repo=False,
    replay=False,
    summary_name="summary",
    base_ref="main",
    status_read_drift=None,
):
    initial_run = {
        "id": 9,
        "workflow_id": 7,
        "event": "pull_request",
        "name": "Gate",
        "repository": {"id": 1},
        "head_repository": {"id": 1 if same_repo else 2},
        "head_sha": "abc",
        "run_attempt": 1,
        "run_number": 5,
        "status": "completed",
        "conclusion": "success",
        "html_url": "https://example.test/runs/9",
        "pull_requests": [{"number": 4}],
    }
    pr = {
        "number": 4,
        "state": "open",
        "changed_files": 1,
        "base": {"repo": {"id": 1}, "ref": base_ref},
        "head": {"repo": {"id": 1 if same_repo else 2}, "sha": "abc"},
    }
    scenario = {
        "initialRun": initial_run,
        "finalRun": final_run or initial_run,
        "pr": pr,
        "statuses": (
            [
                {
                    "context": "Gate / gate",
                    "state": "success",
                    "target_url": "https://example.test/runs/9",
                }
            ]
            if replay
            else []
        ),
        "statusReadDrift": status_read_drift,
    }
    source = f"""
const helper = require({json.dumps(str(HELPER))});
const scenario = {json.dumps(scenario)};
let runReads = 0;
let statusRead = false;
let currentRun = scenario.finalRun;
let currentPr = scenario.pr;
const writes = [];
const endpoint = value => async () => ({{data: value}});
const github = {{
  paginate: async (method, params) => (await method(params)).data,
  rest: {{
    actions: {{
      getWorkflowRun: async () => ({{data: runReads++ === 0 ? scenario.initialRun : currentRun}}),
      getWorkflow: endpoint({{id: 7, path: '.github/workflows/pr-00-gate.yml'}}),
      listJobsForWorkflowRunAttempt: endpoint([{{name: {json.dumps(summary_name)}, status: 'completed', conclusion: 'success'}}]),
      listWorkflowRuns: async () => ({{data: statusRead && scenario.statusReadDrift === 'newer-run'
        ? [scenario.initialRun, {{...scenario.initialRun, id: 10, run_number: 6}}]
        : [scenario.initialRun]}}),
    }},
    pulls: {{
      get: async () => ({{data: currentPr}}),
      list: endpoint([scenario.pr]),
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
      createCommitStatus: async params => {{ writes.push(params); return {{data: params}}; }},
    }},
  }},
}};
const core = {{info: () => {{}}, notice: () => {{}}}};
(async () => {{
  try {{
    const result = await helper.publishGateForkStatus({{
      github,
      core,
      context: {{
        repo: {{owner: 'stranske', repo: 'Workflows'}},
        payload: {{workflow_run: {{id: 9}}, repository: {{id: 1, default_branch: 'main'}}}},
      }},
    }});
    process.stdout.write(JSON.stringify({{result, writes}}));
  }} catch (error) {{
    process.stdout.write(JSON.stringify({{error: error.message, writes}}));
  }}
}})();
"""
    completed = subprocess.run(["node", "-e", source], check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def test_fork_gate_status_publisher_has_trusted_minimal_permissions():
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert data["permissions"] == {
        "actions": "read",
        "contents": "read",
        "pull-requests": "read",
        "statuses": "write",
    }
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "github.event.repository.default_branch" in source
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
    assert "is not from a fork; the Gate summary remains its status writer" in helper
    assert "createTokenAwareRetry" in helper
    assert "env: {}" in helper
    assert "maxRetries: 0" in helper


@pytest.mark.parametrize("summary_name", SUPPORTED_SUMMARY_NAMES)
def test_fork_gate_status_requires_explicit_success_and_complete_summary(summary_name):
    jobs = [{"name": summary_name, "status": "completed", "conclusion": "success"}]
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
            [{"name": summary_name, "status": "completed", "conclusion": "failure"}],
            ["src/app.py"],
        )["state"]
        == "failure"
    )


@pytest.mark.parametrize("summary_name", SUPPORTED_SUMMARY_NAMES)
def test_fork_gate_status_publishes_success_once_for_bound_evidence(summary_name):
    outcome = _publish_scenario(summary_name=summary_name)
    assert outcome["result"]["state"] == "success"
    assert len(outcome["writes"]) == 1
    assert outcome["writes"][0]["sha"] == "abc"
    assert outcome["writes"][0]["context"] == "Gate / gate"


@pytest.mark.parametrize(
    "jobs",
    [
        [],
        [
            {"name": "summary", "status": "completed", "conclusion": "success"},
            {"name": "summary", "status": "completed", "conclusion": "success"},
        ],
        [
            {"name": "gate-summary", "status": "completed", "conclusion": "success"},
            {"name": "gate-summary", "status": "completed", "conclusion": "success"},
        ],
        [
            {"name": "summary", "status": "completed", "conclusion": "success"},
            {"name": "gate-summary", "status": "completed", "conclusion": "success"},
        ],
        [{"name": "Summary", "status": "completed", "conclusion": "success"}],
        [{"name": "Gate-Summary", "status": "completed", "conclusion": "success"}],
        [{"name": " gate-summary ", "status": "completed", "conclusion": "success"}],
        [{"name": "gate-summary (3.12)", "status": "completed", "conclusion": "success"}],
        [{"name": "Gate / gate-summary", "status": "completed", "conclusion": "success"}],
    ],
)
def test_fork_gate_status_rejects_missing_ambiguous_or_lookalike_summary(jobs):
    result = _decide({"status": "completed", "conclusion": "success"}, jobs, ["src/app.py"])
    assert result == {"state": "error", "description": "Gate job set is missing or incomplete"}


def test_fork_gate_status_source_and_template_helpers_match():
    assert HELPER.read_bytes() == TEMPLATE_HELPER.read_bytes()


def test_fork_gate_status_revalidates_replayed_status_before_returning():
    final_run = {
        "id": 9,
        "workflow_id": 7,
        "event": "pull_request",
        "name": "Gate",
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
    assert outcome["error"] == "Gate run attempt changed before publication"
    assert outcome["writes"] == []


@pytest.mark.parametrize("replay", [False, True])
@pytest.mark.parametrize(
    ("drift", "message"),
    [
        ("same-run-attempt", "Gate run attempt changed before publication"),
        ("newer-run", "Gate run 9 was superseded by 10"),
        ("pr-head", "PR head no longer matches Gate head"),
    ],
)
def test_fork_gate_status_revalidates_after_status_pagination(replay, drift, message):
    outcome = _publish_scenario(replay=replay, status_read_drift=drift)
    assert outcome["error"] == message
    assert outcome["writes"] == []


def test_fork_gate_status_skips_same_repo_and_reuses_identical_status():
    same_repo = _publish_scenario(same_repo=True)
    assert same_repo["result"] == {
        "state": "skipped",
        "description": "Same-repository PR",
    }
    assert same_repo["writes"] == []

    replay = _publish_scenario(replay=True)
    assert replay["result"]["state"] == "success"
    assert replay["writes"] == []


def test_fork_gate_status_rejects_non_default_base_branch():
    outcome = _publish_scenario(base_ref="release")
    assert outcome["error"] == "PR base is not the trusted default branch"
    assert outcome["writes"] == []


def test_fork_gate_status_blocks_changed_control_surface():
    jobs = [{"name": "summary", "status": "completed", "conclusion": "success"}]
    result = _decide(
        {"status": "completed", "conclusion": "success"},
        jobs,
        [".github/workflows/pr-00-gate.yml"],
    )
    assert result["state"] == "error"
    assert "controls changed" in result["description"]


def test_fork_gate_status_blocks_renamed_control_surface():
    collected = _collect_changed_paths(
        {"changed_files": 1},
        [
            {
                "filename": "docs/renamed.yml",
                "previous_filename": ".github/workflows/pr-00-gate.yml",
                "status": "renamed",
            }
        ],
    )
    assert collected == {"result": ["docs/renamed.yml", ".github/workflows/pr-00-gate.yml"]}
    jobs = [{"name": "summary", "status": "completed", "conclusion": "success"}]
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
def test_fork_gate_status_rejects_incomplete_or_malformed_file_evidence(pr, files, message):
    assert message in _collect_changed_paths(pr, files)["error"]


def test_fork_gate_status_accepts_complete_3000_file_listing():
    files = [{"filename": f"src/{index}.py"} for index in range(3000)]
    assert _collect_changed_paths({"changed_files": 3000}, files)["result"] == [
        file["filename"] for file in files
    ]


def test_fork_gate_status_binding_rejects_stale_head_sha():
    source = f"""
const helper = require({json.dumps(str(HELPER))});
try {{
  helper.validateBinding({{
    run: {{event: 'pull_request', name: 'Gate', workflow_id: 7, repository: {{id: 1}}, head_repository: {{id: 2}}, head_sha: 'old'}},
    workflow: {{id: 7, path: '.github/workflows/pr-00-gate.yml'}},
    pr: {{state: 'open', base: {{repo: {{id: 1}}, ref: 'main'}}, head: {{repo: {{id: 2}}, sha: 'new'}}}},
    repository: {{id: 1, default_branch: 'main'}},
  }});
  process.exit(2);
}} catch (error) {{
  process.stdout.write(error.message);
}}
"""
    completed = subprocess.run(["node", "-e", source], check=True, capture_output=True, text=True)
    assert completed.stdout == "PR head no longer matches Gate head"


def test_fork_gate_status_rejects_attempt_or_status_drift_before_write():
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
        "Gate run attempt changed before publication",
        "Gate run status changed before publication",
    ]
