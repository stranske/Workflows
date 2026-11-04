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
    fixture_overrides: dict[str, Any] | None = None,
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
import { createRequire } from 'node:module';
const requireModule = createRequire(import.meta.url);
const fixture = JSON.parse(process.env.FIXTURE);
const outputs = {};
const failures = [];
const labelsAdded = [];
const labelsCreated = [];
const labelsRemoved = [];
const comments = [];
const pageCalls = [];
const knownLabels = new Set(fixture.knownLabels || []);

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
        const start = (page - 1) * perPage;
        return { data: fixture.prs.slice(start, start + perPage) };
      },
    },
    issues: {
      listEventsForTimeline: async () => ({
        data: fixture.timeline || [{ event: 'closed', id: fixture.closureId || 9001 }],
      }),
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
        return { data: [] };
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
      createTokenAwareRetry: async () => ({
        withRetry,
        paginateWithRetry: async (_method, params) => {
          const response = await github.rest.issues.listEventsForTimeline(params);
          return response.data;
        },
      }),
    };
  }
  if (name === './.github/scripts/auto_pilot_transitions.js') {
    return requireModule(process.env.TRANSITIONS_MODULE);
  }
  throw new Error('Unexpected require: ' + name);
};

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
await new AsyncFunction('require', 'github', 'context', 'core', 'process', process.env.SCRIPT)(
  requireStub,
  github,
  context,
  core,
  process,
);

process.stdout.write(JSON.stringify({
  outputs,
  failures,
  labelsAdded,
  labelsCreated,
  labelsRemoved,
  comments,
  pageCalls,
}));
"""
    completed = subprocess.run(
        [node, "--input-type=module", "-e", harness],
        cwd=ROOT,
        env={
            **os.environ,
            "SCRIPT": script,
            "ISSUE_NUMBER": str(ISSUE_NUMBER),
            "TRANSITIONS_MODULE": str(
                ROOT / "templates/consumer-repo/.github/scripts/auto_pilot_transitions.js"
                if "consumer" in workflow.parts
                else ROOT / ".github/scripts/auto_pilot_transitions.js"
            ),
            "FIXTURE": json.dumps({"prs": prs, "knownLabels": [], **(fixture_overrides or {})}),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


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


def test_handoff_success_persists_closure_bound_identity_marker(workflow: Path) -> None:
    """Successful verify records a durable handoff marker tied to the latest closure."""
    result = _run_verify(
        [_matching_pr(555)],
        workflow,
        fixture_overrides={"closureId": 4242},
    )

    assert result["outputs"].get("verify_handoff") == "found"
    assert result["outputs"].get("verify_handoff_closure_id") == "4242"
    assert result["outputs"].get("verify_handoff_source_pr") == "555"
    assert any(
        comment["issue_number"] == ISSUE_NUMBER
        and "auto-pilot-verify-handoff:v1" in comment["body"]
        and '"closureId":"4242"' in comment["body"].replace(" ", "")
        and '"sourcePr":"555"' in comment["body"].replace(" ", "")
        for comment in result["comments"]
    )


def test_handoff_without_closure_event_withholds_identity_marker(workflow: Path) -> None:
    result = _run_verify(
        [_matching_pr(555)],
        workflow,
        fixture_overrides={"timeline": [{"event": "commented", "id": 1}]},
    )

    assert result["failures"]
    assert result["outputs"].get("verify_handoff") != "found"
    assert not any("auto-pilot-verify-handoff:v1" in comment["body"] for comment in result["comments"])
