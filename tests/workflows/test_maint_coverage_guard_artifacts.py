"""Regression checks for the source and bootstrap coverage-guard selectors."""

import json
import subprocess
from pathlib import Path

import pytest
import yaml

CONSUMER_GUARD = "templates/consumer-repo/.github/workflows/maint-coverage-guard.yml"


@pytest.mark.parametrize(
    "workflow_path",
    [
        ".github/workflows/maint-coverage-guard.yml",
        "templates/consumer-repo/.github/workflows/maint-coverage-guard.yml",
    ],
)
def test_coverage_guard_selects_only_runs_with_payload_and_trend(workflow_path: str) -> None:
    workflow = Path(workflow_path).read_text(encoding="utf-8")

    assert (
        workflow.count(
            "const trendArtifact = availableArtifacts.find(({ name }) => name === trendArtifactName);"
        )
        == 1
    )
    assert workflow.count("if (payloadName && trendArtifact)") == 1
    assert workflow.count("Coverage verification could not proceed: ${missingPairReason}.") == 1
    assert workflow.count("no gate-coverage artifacts were published") == 1
    assert workflow.count("published coverage artifact names did not match") == 1
    assert workflow.count("coverage payloads were published without ${trendArtifactName}") == 1
    assert '"gate-coverage.json"' in workflow
    assert "coverage_artifacts/payload coverage_artifacts/coverage.json" in workflow


@pytest.mark.parametrize(
    "workflow_path",
    [
        ".github/workflows/maint-coverage-guard.yml",
        "templates/consumer-repo/.github/workflows/maint-coverage-guard.yml",
    ],
)
def test_recovery_cache_survives_producer_runs_and_saves_after_guard(workflow_path: str) -> None:
    steps = yaml.safe_load(Path(workflow_path).read_text())["jobs"]["guard"]["steps"]
    restore = next(s for s in steps if s.get("id") == "coverage-trend-history-cache")
    guard = next(s for s in steps if s.get("name") == "Run coverage guard")
    save = next(s for s in steps if s.get("name") == "Save coverage recovery history")
    assert steps.index(restore) < steps.index(guard) < steps.index(save)
    assert restore["uses"].startswith("actions/cache/restore@")
    assert save["uses"].startswith("actions/cache/save@")
    assert restore["with"]["path"] == save["with"]["path"] == "coverage_artifacts/history"
    assert "github.repository" in restore["with"]["key"]
    assert "github.run_id" in restore["with"]["key"]
    assert "github.run_attempt" in restore["with"]["key"]
    assert "discover.outputs.run_id" not in restore["with"]["key"]
    prefix = restore["with"]["restore-keys"].strip()
    assert "github.repository" in prefix and "run_id" not in prefix
    assert restore["with"]["key"].startswith(prefix)
    assert 'HISTORY_PATH="coverage_artifacts/history/coverage-trend-history.ndjson"' in guard["run"]
    assert "cache-primary-key" in save["with"]["key"]
    assert "hashFiles('coverage_artifacts/history/coverage-trend-history.ndjson')" in save["if"]


def _replay_discovery(
    *, repo: str, runs: list[dict], artifacts: dict[int, list[dict]], config: dict
) -> dict:
    steps = yaml.safe_load(Path(CONSUMER_GUARD).read_text())["jobs"]["guard"]["steps"]
    script = next(s["with"]["script"] for s in steps if s.get("id") == "discover")
    harness = """
    const { script, repo, runs, artifacts, config } =
      JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
    const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
    const result = { queries: [], probed: [], outputs: {}, error: '' };
    const github = {
      rest: { actions: { listWorkflowRuns: 'runs', listWorkflowRunArtifacts: 'artifacts' } },
      paginate: async (route, params) => {
        if (route === 'runs') {
          result.queries.push(params);
          return runs.filter(({ path }) => path === params.workflow_id);
        }
        result.probed.push(params.run_id);
        return artifacts[params.run_id] || [];
      },
    };
    const core = {
      info() {}, warning() {}, notice() {},
      setOutput: (key, value) => { result.outputs[key] = value; },
      setFailed: (message) => { result.error = message; },
    };
    const requireConfig = (name) => {
      if (name !== 'fs') throw Error(`Unexpected module ${name}`);
      return { existsSync: () => false, readFileSync: () => JSON.stringify(config) };
    };
    const context = {
      repo: { owner: 'stranske', repo },
      payload: { repository: { default_branch: 'trunk' } },
    };
    new AsyncFunction('require', 'github', 'context', 'core', script)(
      requireConfig, github, context, core,
    ).then(() => console.log(JSON.stringify(result))).catch((error) => {
      console.error(error);
      process.exitCode = 1;
    });
    """
    output = subprocess.run(
        ["node", "-e", harness],
        input=json.dumps(
            {"script": script, "repo": repo, "runs": runs, "artifacts": artifacts, "config": config}
        ),
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return json.loads(output.stdout)


def _integration_ci_run(**overrides: object) -> dict:
    return {
        "id": 101,
        "event": "push",
        "head_branch": "trunk",
        "path": ".github/workflows/ci.yml",
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 2,
        "run_started_at": "2026-11-23T15:40:00Z",
        "updated_at": "2026-11-23T15:42:00Z",
        **overrides,
    }


def _coverage_artifact(artifact_id: int, name: str, **overrides: object) -> dict:
    return {
        "id": artifact_id,
        "name": name,
        "expired": False,
        "created_at": "2026-11-23T15:41:00Z",
        **overrides,
    }


def test_integration_coverage_selects_only_default_push_and_downloads_exact_artifact_ids() -> None:
    result = _replay_discovery(
        repo="Workflows-Integration-Tests",
        runs=[
            _integration_ci_run(id=102, event="pull_request"),
            _integration_ci_run(id=103, head_branch="topic"),
            _integration_ci_run(id=104, conclusion="neutral"),
            _integration_ci_run(),
        ],
        artifacts={
            101: [
                _coverage_artifact(201, "full-coverage-3.13-2"),
                _coverage_artifact(202, "full-coverage-3.14-1"),
                _coverage_artifact(203, "full-coverage-3.14-2"),
                _coverage_artifact(204, "full-coverage-trend"),
            ],
        },
        config={"coverage": 80, "source_workflows": [".github/workflows/pr-00-gate.yml"]},
    )
    assert not result["error"]
    assert result["probed"] == [101]
    assert result["queries"] == [
        {
            "owner": "stranske",
            "repo": "Workflows-Integration-Tests",
            "workflow_id": ".github/workflows/ci.yml",
            "status": "completed",
            "per_page": 100,
            "branch": "trunk",
            "event": "push",
        }
    ]
    assert result["outputs"]["run_id"] == "101"
    assert result["outputs"]["coverage_artifact_id"] == "203"
    assert result["outputs"]["trend_artifact_id"] == "204"
    assert result["outputs"]["coverage_fallback_artifact_ids"] == ""
    steps = yaml.safe_load(Path(CONSUMER_GUARD).read_text())["jobs"]["guard"]["steps"]
    for artifact in ("coverage", "trend"):
        output_key = f"steps.discover.outputs.{artifact}_artifact"
        download = next(
            s["with"]
            for s in steps
            if s.get("with", {}).get("artifact-ids") == f"${{{{ {output_key}_id }}}}"
        )
        assert download["name"] == f"${{{{ !{output_key}_id && {output_key}_name || '' }}}}"
        assert download["run-id"] == "${{ steps.discover.outputs.run_id }}"


@pytest.mark.parametrize(
    "trend_overrides",
    [
        pytest.param({"created_at": "2026-11-23T15:39:00Z"}, id="stale-trend"),
        pytest.param({"created_at": "2026-11-23T15:43:00Z"}, id="late-trend"),
        pytest.param({"expired": True}, id="expired-trend"),
        pytest.param({"name": "gate-coverage-trend"}, id="gate-trend"),
    ],
)
def test_integration_coverage_rejects_unpaired_attempt_artifacts(trend_overrides: dict) -> None:
    trend = _coverage_artifact(204, "full-coverage-trend")
    result = _replay_discovery(
        repo="Workflows-Integration-Tests",
        runs=[_integration_ci_run(), _integration_ci_run(id=102)],
        artifacts={
            101: [_coverage_artifact(203, "full-coverage-3.14-2"), trend | trend_overrides],
            102: [trend],
        },
        config={"coverage": 80},
    )
    assert result["probed"] == [101, 102]
    assert result["outputs"]["run_id"] == ""
    assert "same Integration CI attempt" in result["error"]


@pytest.mark.parametrize(
    "workflow,config",
    [
        (".github/workflows/pr-00-gate.yml", {"coverage": 80}),
        (".github/workflows/ci.yml", {"source_workflows": [".github/workflows/ci.yml"]}),
    ],
)
def test_other_consumers_keep_their_existing_gate_artifact_selection(
    workflow: str, config: dict
) -> None:
    result = _replay_discovery(
        repo="another-consumer",
        runs=[_integration_ci_run(path=workflow, event="pull_request", head_branch="topic")],
        artifacts={
            101: [
                _coverage_artifact(203, "gate-coverage.json"),
                _coverage_artifact(204, "gate-coverage-trend"),
                _coverage_artifact(205, "full-coverage-3.14-2"),
                _coverage_artifact(206, "full-coverage-trend"),
            ],
        },
        config=config,
    )
    assert not result["error"]
    assert result["outputs"]["coverage_artifact_name"] == "gate-coverage.json"
    assert result["outputs"]["trend_artifact_name"] == "gate-coverage-trend"
    assert not result["outputs"].get("coverage_artifact_id")
    assert not result["outputs"].get("trend_artifact_id")
    assert "branch" not in result["queries"][0]
    assert "event" not in result["queries"][0]


def test_maint69_runs_after_coverage_guard_template_changes_on_main() -> None:
    workflow = yaml.safe_load(
        Path(".github/workflows/maint-69-sync-integration-repo.yml").read_text()
    )
    push = workflow[True]["push"]
    assert push["branches"] == ["main"]
    assert CONSUMER_GUARD in push["paths"]
