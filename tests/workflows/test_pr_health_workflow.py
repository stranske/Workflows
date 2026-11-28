"""Replay the reusable PR health workflow and its consumer follow-up."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REUSABLE_PR_HEALTH = REPO_ROOT / ".github/workflows/reusable-agents-pr-health.yml"
CONSUMER_WORKFLOWS_DIR = REPO_ROOT / "templates/consumer-repo/.github/workflows"
CONSUMER_PR_HEALTH = CONSUMER_WORKFLOWS_DIR / "agents-pr-health.yml"
CONSUMER_GATE_FOLLOWUPS = CONSUMER_WORKFLOWS_DIR / "agents-81-gate-followups.yml"
SYNC_MANIFEST = REPO_ROOT / ".github/sync-manifest.yml"

PR_HEALTH_REPLAY_HARNESS_JS = r"""
const fs = require("node:fs");
const path = require("node:path");

const [scenarioPath] = process.argv.slice(2);
const scenario = JSON.parse(fs.readFileSync(scenarioPath, "utf8"));
const repoRoot = scenario.repoRoot;
const scanDir = scenario.scanDir;

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

const origReadFileSync = fs.readFileSync.bind(fs);
const origWriteFileSync = fs.writeFileSync.bind(fs);
const origExistsSync = fs.existsSync.bind(fs);

const SCAN_TMP_FILES = new Set([
  "/tmp/conflict_prs.json",
  "/tmp/failing_prs.json",
  "/tmp/stalled_prs.json",
]);

function remapPath(filePath) {
  const normalized = String(filePath);
  if (normalized === ".github/workflows/agents-81-gate-followups.yml") {
    return path.join(
      repoRoot,
      "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml"
    );
  }
  if (normalized.startsWith("/tmp/scan-data/") || SCAN_TMP_FILES.has(normalized)) {
    return path.join(scanDir, path.basename(normalized));
  }
  return filePath;
}

fs.readFileSync = (filePath, ...rest) =>
  origReadFileSync(remapPath(filePath), ...rest);
fs.writeFileSync = (filePath, ...rest) =>
  origWriteFileSync(remapPath(filePath), ...rest);
fs.existsSync = (filePath, ...rest) =>
  origExistsSync(remapPath(filePath), ...rest);

function customRequire(specifier) {
  if (specifier === "fs" || specifier === "node:fs") {
    return fs;
  }
  if (specifier.startsWith("./") || specifier.startsWith("../")) {
    return require(path.resolve(repoRoot, specifier));
  }
  return require(specifier);
}

function makeCore(stepOutputs, logs, warnings, summaries) {
  return {
    info: (msg) => logs.push(String(msg)),
    debug: (msg) => logs.push(String(msg)),
    notice: (msg) => logs.push(String(msg)),
    warning: (msg) => warnings.push(String(msg)),
    setFailed: (msg) => {
      throw new Error(`core.setFailed: ${msg}`);
    },
    setOutput: (key, value) => {
      stepOutputs[key] = String(value);
    },
    summary: {
      addRaw: (raw) => {
        summaries.push(String(raw));
        return this;
      },
      write: async () => {},
    },
  };
}

(async () => {
  const prsByNumber = new Map();
  const labelsByPr = new Map();
  const commentsByPr = new Map();
  for (const pr of scenario.prs) {
    prsByNumber.set(pr.number, JSON.parse(JSON.stringify(pr)));
    labelsByPr.set(
      pr.number,
      (pr.labels || []).map((label) =>
        typeof label === "string" ? label : label.name
      )
    );
    commentsByPr.set(
      pr.number,
      JSON.parse(JSON.stringify(pr.comments || []))
    );
  }

  const workflowDispatches = [];
  const repositoryDispatches = [];
  const branchUpdates = [];
  const labelEvents = [];
  const removedLabels = [];
  const addedLabels = [];
  const logs = [];
  const warnings = [];
  const summaries = [];

  const context = {
    repo: { owner: "stranske", repo: scenario.repo || "Consumer-Repo" },
    eventName: "workflow_call",
    actor: "github-actions[bot]",
    payload: {
      repository: {
        default_branch: "main",
      },
    },
  };

  const github = {
    paginate: async (method, params) => {
      const response = await method(params);
      const data = response?.data;
      if (Array.isArray(data)) return data;
      if (Array.isArray(data?.workflow_runs)) return data.workflow_runs;
      if (Array.isArray(data?.jobs)) return data.jobs;
      if (Array.isArray(data?.check_runs)) return data.check_runs;
      return [];
    },
    rest: {
      rateLimit: {
        get: async () => ({
          data: {
            resources: {
              core: {
                remaining: 5000,
                limit: 5000,
                reset: Math.floor(Date.now() / 1000) + 3600,
              },
            },
          },
        }),
      },
      pulls: {
        list: async () => ({
          data: Array.from(prsByNumber.values()).map((pr) => ({
            ...pr,
            labels: (labelsByPr.get(pr.number) || []).map((name) => ({ name })),
          })),
        }),
        get: async ({ pull_number }) => {
          const pr = prsByNumber.get(Number(pull_number));
          if (!pr) {
            const err = new Error(`PR #${pull_number} not found`);
            err.status = 404;
            throw err;
          }
          return {
            data: {
              ...pr,
              labels: (labelsByPr.get(pr.number) || []).map((name) => ({
                name,
              })),
            },
          };
        },
        listFiles: async () => ({
          data: [{ filename: "src/app.py", additions: 4, deletions: 1 }],
        }),
        updateBranch: async ({ pull_number }) => {
          const pr = prsByNumber.get(Number(pull_number));
          branchUpdates.push(Number(pull_number));
          if (pr && pr.auto_merge_clean) {
            return { data: { message: "Updated branch" } };
          }
          throw new Error("Merge conflict — manual resolution required");
        },
      },
      repos: {
        getCollaboratorPermissionLevel: async ({ username }) => ({
          data: { permission: username === "fixture-maintainer" ? "write" : "read" },
        }),
        getCombinedStatusForRef: async ({ ref }) => {
          const status = scenario.combinedStatusBySha[ref] || "success";
          return { data: typeof status === "string" ? { state: status } : status };
        },
        createDispatchEvent: async (payload) => {
          repositoryDispatches.push(payload);
          return { status: 204 };
        },
      },
      checks: {
        listForRef: async ({ ref }) => {
          if (ref === scenario.unavailableChecksSha) {
            const error = new Error("Check runs unavailable");
            error.status = 404;
            throw error;
          }
          return { data: { check_runs: scenario.checkRunsBySha[ref] || [] } };
        },
      },
      actions: {
        createWorkflowDispatch: async (payload) => {
          workflowDispatches.push(payload);
          return { status: 204 };
        },
        listWorkflowRunsForRepo: async ({ head_sha, branch }) => {
          const allRuns = Object.values(scenario.gateRunsBySha || {}).flat();
          const filtered = allRuns.filter(
            (run) =>
              (!head_sha || run.head_sha === head_sha) &&
              (!branch || !run.head_branch || run.head_branch === branch)
          );
          return { data: { workflow_runs: filtered } };
        },
        listWorkflowRuns: async ({ head_sha, branch }) => {
          const allRuns = Object.values(scenario.gateRunsBySha || {}).flat();
          const filtered = allRuns.filter(
            (run) =>
              (!head_sha || run.head_sha === head_sha) &&
              (!branch || !run.head_branch || run.head_branch === branch)
          );
          return { data: { workflow_runs: filtered } };
        },
        listJobsForWorkflowRun: async ({ run_id }) => ({
          data: {
            jobs: scenario.gateJobsByRunId[String(run_id)] || [],
          },
        }),
        downloadJobLogsForWorkflowRun: async () => ({
          data: "AssertionError: pytest check failed",
        }),
      },
      issues: {
        listLabelsOnIssue: async ({ issue_number }) => {
          const num = Number(issue_number);
          if (scenario.liveLabelsOverride && scenario.liveLabelsOverride[num]) {
            labelsByPr.set(num, [...scenario.liveLabelsOverride[num]]);
          }
          return {
            data: (labelsByPr.get(num) || []).map((name) => ({ name })),
          };
        },
        removeLabel: async ({ issue_number, name }) => {
          const num = Number(issue_number);
          const current = labelsByPr.get(num) || [];
          const idx = current.indexOf(name);
          if (idx === -1) {
            const err = new Error("Label does not exist");
            err.status = 404;
            throw err;
          }
          current.splice(idx, 1);
          labelsByPr.set(num, current);
          removedLabels.push({ pr_number: num, name });
          return { status: 200 };
        },
        addLabels: async ({ issue_number, labels }) => {
          const num = Number(issue_number);
          const current = labelsByPr.get(num) || [];
          for (const label of labels) {
            addedLabels.push({ pr_number: num, name: label });
            if (!current.includes(label)) {
              current.push(label);
              labelEvents.push({
                pr_number: num,
                action: "labeled",
                label: { name: label },
              });
            }
          }
          labelsByPr.set(num, current);
          return { data: current.map((name) => ({ name })) };
        },
        listComments: async ({ issue_number }) => ({
          data: commentsByPr.get(Number(issue_number)) || [],
        }),
      },
    },
  };

  async function runStep(scriptBody, envVars = {}, customContext = context) {
    const previousEnv = {};
    for (const [k, v] of Object.entries(envVars)) {
      previousEnv[k] = process.env[k];
      process.env[k] = String(v);
    }
    const stepOutputs = {};
    try {
      const fn = new AsyncFunction(
        "context",
        "github",
        "core",
        "require",
        scriptBody
      );
      await fn(
        customContext,
        github,
        makeCore(stepOutputs, logs, warnings, summaries),
        customRequire
      );
    } finally {
      for (const [k, v] of Object.entries(previousEnv)) {
        if (v === undefined) {
          delete process.env[k];
        } else {
          process.env[k] = v;
        }
      }
    }
    return stepOutputs;
  }

  const scanOutputs = await runStep(scenario.scripts.categorise, {
    MAX_PRS: "10",
    MAX_DISPATCHES: String(scenario.maxDispatches),
  });
  await runStep(scenario.scripts.resolveConflicts, {
    DRY_RUN: scenario.dryRun ? "true" : "false",
  });
  if (!scenario.dryRun && (scanOutputs.check_dispatch_count ?? scanOutputs.failing_count) !== "0") {
    await runStep(scenario.scripts.fixChecks, {});
  }

  // A failed security step skips evaluation under Actions' implicit success().
  const receiverGuards = [];
  async function runReceiverGuard(receiverContext) {
    const outputs = {};
    const core = makeCore(outputs, logs, warnings, summaries);
    let failed = false;
    core.setFailed = () => { failed = true; };
    const guard = new AsyncFunction(
      "context", "github", "core", "require", scenario.scripts.consumerGuard
    );
    await guard(receiverContext, github, core, customRequire);
    receiverGuards.push({
      pr_number: receiverContext.payload.inputs?.pr_number
        ?? String(receiverContext.payload.pull_request?.number),
      outputs,
      failed,
    });
    return !failed;
  }

  // Negative controls use the same receiver and dispatch actor as the caller.
  if (scenario.guardControls) {
    for (const prNumber of ["105", "", "101junk", "999"]) {
      workflowDispatches.push({
        workflow_id: "agents-81-gate-followups.yml",
        ref: "main",
        inputs: { pr_number: prNumber, force_retry: "false" },
      });
    }
  }

  const receiverEvaluations = [];
  for (const dispatch of workflowDispatches) {
    if (dispatch.workflow_id === "agents-81-gate-followups.yml") {
      const receiverContext = {
        repo: context.repo,
        eventName: "workflow_dispatch",
        actor: "github-actions[bot]",
        payload: { inputs: dispatch.inputs || {} },
      };
      if (!(await runReceiverGuard(receiverContext))) continue;
      const evalOutputs = await runStep(
        scenario.scripts.consumerEvaluate,
        {
          GITHUB_WORKFLOW: "Agents Gate Followups",
          INPUT_PR_NUMBER: dispatch.inputs?.pr_number || "",
          INPUT_FORCE_RETRY: dispatch.inputs?.force_retry || "false",
          INPUT_EXECUTION_PROFILE: "",
          HAS_CODEX_AUTH: "true",
          HAS_CLAUDE_AUTH: "true",
          HAS_CLAUDE_OAUTH: "true",
        },
        receiverContext
      );
      receiverEvaluations.push({
        trigger: "workflow_dispatch",
        workflow_id: dispatch.workflow_id,
        ref: dispatch.ref,
        inputs: dispatch.inputs,
        outputs: evalOutputs,
      });
    }
  }

  for (const evt of labelEvents) {
    const pr = prsByNumber.get(evt.pr_number);
    const receiverContext = {
      repo: context.repo,
      eventName: "pull_request_target",
      actor: "github-actions[bot]",
      payload: {
        action: "labeled",
        label: evt.label,
        pull_request: {
          ...pr,
          labels: (labelsByPr.get(evt.pr_number) || []).map((name) => ({ name })),
        },
      },
    };
    if (!(await runReceiverGuard(receiverContext))) continue;
    const evalOutputs = await runStep(
      scenario.scripts.consumerEvaluate,
      {
        GITHUB_WORKFLOW: "Agents Gate Followups",
        INPUT_PR_NUMBER: "",
        INPUT_FORCE_RETRY: "false",
        INPUT_EXECUTION_PROFILE: "",
        HAS_CODEX_AUTH: "true",
        HAS_CLAUDE_AUTH: "true",
        HAS_CLAUDE_OAUTH: "true",
      },
      receiverContext
    );
    receiverEvaluations.push({
      trigger: "pull_request_target:labeled",
      workflow_id: "agents-81-gate-followups.yml",
      pr_number: evt.pr_number,
      label: evt.label.name,
      outputs: evalOutputs,
    });
  }

  const finalLabels = {};
  const finalComments = {};
  for (const [num, labels] of labelsByPr.entries()) {
    finalLabels[String(num)] = labels;
    finalComments[String(num)] = commentsByPr.get(num) || [];
  }

  process.stdout.write(
    JSON.stringify({
      scanOutputs,
      branchUpdates,
      workflowDispatches,
      repositoryDispatches,
      removedLabels,
      addedLabels,
      labelEvents,
      finalLabels,
      finalComments,
      receiverGuards,
      receiverEvaluations,
      summaries,
      warnings,
    })
  );
})();
"""


def _extract_github_script(
    workflow: dict[str, Any],
    job_name: str,
    *,
    step_id: str | None = None,
    step_name: str | None = None,
) -> str:
    steps = workflow["jobs"][job_name]["steps"]
    for step in steps:
        if step_id is not None and step.get("id") == step_id:
            return str(step["with"]["script"])
        if step_name is not None and step.get("name") == step_name:
            return str(step["with"]["script"])
    raise AssertionError(
        f"Missing github-script step in job {job_name!r} (id={step_id!r}, name={step_name!r})"
    )


def _installed_consumer_workflows() -> dict[str, dict[str, Any]]:
    installed: dict[str, dict[str, Any]] = {}
    for path in sorted(CONSUMER_WORKFLOWS_DIR.glob("*.yml")):
        installed[path.name] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return installed


def _workflow_on_block(workflow: dict[str, Any]) -> dict[str, Any]:
    raw_on = workflow.get("on") or workflow.get(True) or {}
    return raw_on if isinstance(raw_on, dict) else {}


def _run_pr_health_replay(
    tmp_path: Path,
    *,
    dry_run: bool = False,
    live_labels_override: dict[int, list[str]] | None = None,
    label: str | None = None,
    guard_controls: bool = False,
    include_incident: bool = False,
    incident_only: bool = False,
    incident_checks_unavailable: bool = False,
    incident_first: bool = False,
    incident_status_label: str | None = None,
    max_dispatches: int = 3,
) -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:  # pragma: no cover - host dependent
        message = "node is required to replay reusable-agents-pr-health github-script steps"
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)

    reusable_doc = yaml.safe_load(REUSABLE_PR_HEALTH.read_text(encoding="utf-8"))
    consumer_followups_doc = yaml.safe_load(CONSUMER_GATE_FOLLOWUPS.read_text(encoding="utf-8"))

    run_tag = label or ("dry" if dry_run else "live")
    scan_dir = tmp_path / f"scan-data-{run_tag}"
    scan_dir.mkdir(parents=True, exist_ok=True)

    task_body = (
        "## Summary\n\n"
        "<!-- auto-status-summary:start -->\n"
        "### Tasks\n"
        "- [x] Wire consumer wrapper\n"
        "- [ ] Replay installed receiver\n"
        "### Acceptance Criteria\n"
        "- [ ] Receiver observes PR/head dispatch\n"
        "<!-- auto-status-summary:end -->\n"
    )
    completed_task_body = (
        "## Summary\n\n"
        "<!-- auto-status-summary:start -->\n"
        "### Tasks\n"
        "- [x] Wire consumer wrapper\n"
        "- [x] Replay installed receiver\n"
        "### Acceptance Criteria\n"
        "- [x] Receiver observes PR/head dispatch\n"
        "<!-- auto-status-summary:end -->\n"
    )

    scenario = {
        "repoRoot": str(REPO_ROOT),
        "scanDir": str(scan_dir),
        "dryRun": dry_run,
        "guardControls": guard_controls,
        "maxDispatches": max_dispatches,
        "scripts": {
            "categorise": _extract_github_script(reusable_doc, "scan", step_id="categorise"),
            "resolveConflicts": _extract_github_script(
                reusable_doc, "resolve-conflicts", step_name="Resolve each conflict"
            ),
            "fixChecks": _extract_github_script(
                reusable_doc, "fix-checks", step_name="Fix each failing PR"
            ),
            "consumerEvaluate": _extract_github_script(
                consumer_followups_doc, "evaluate", step_id="evaluate"
            ),
            "consumerGuard": _extract_github_script(
                consumer_followups_doc, "evaluate", step_id="security_gate"
            ),
        },
        "prs": [
            {
                "number": 101,
                "title": "Conflicting PR needing agent conflict resolution",
                "state": "open",
                "draft": False,
                "mergeable": False,
                "mergeable_state": "dirty",
                "auto_merge_clean": False,
                "head": {
                    "ref": "codex/issue-101",
                    "sha": "101deadbeef101deadbeef101deadbeef101dead",
                    "repo": {"full_name": "stranske/Consumer-Repo"},
                },
                "base": {"ref": "main", "repo": {"full_name": "stranske/Consumer-Repo"}},
                "user": {"login": "fixture-maintainer"},
                "labels": ["agent:codex", "agents:keepalive"],
                "body": task_body,
                "comments": [{"id": 9001, "body": "existing conflict context"}],
            },
            {
                "number": 102,
                "title": "Conflicting PR resolved by clean branch update",
                "state": "open",
                "draft": False,
                "mergeable": False,
                "mergeable_state": "dirty",
                "auto_merge_clean": True,
                "head": {
                    "ref": "codex/issue-102",
                    "sha": "102deadbeef102deadbeef102deadbeef102dead",
                    "repo": {"full_name": "stranske/Consumer-Repo"},
                },
                "base": {"ref": "main"},
                "labels": ["agent:codex", "agents:keepalive"],
                "body": task_body,
                "comments": [],
            },
            {
                "number": 103,
                "title": "Failing checks PR needing keepalive followups repair",
                "state": "open",
                "draft": False,
                "mergeable": True,
                "mergeable_state": "unstable",
                "head": {
                    "ref": "claude/issue-103",
                    "sha": "103deadbeef103deadbeef103deadbeef103dead",
                    "repo": {"full_name": "stranske/Consumer-Repo"},
                },
                "base": {"ref": "main", "repo": {"full_name": "stranske/Consumer-Repo"}},
                "user": {"login": "fixture-maintainer"},
                "labels": ["agent:claude", "agents:keepalive"],
                "body": completed_task_body,
                "comments": [{"id": 9003, "body": "failing check context"}],
            },
            {
                "number": 104,
                "title": "Stalled PR with owned attention and rate-limit signals",
                "state": "open",
                "draft": False,
                "mergeable": True,
                "mergeable_state": "clean",
                "head": {
                    "ref": "codex/issue-104",
                    "sha": "104deadbeef104deadbeef104deadbeef104dead",
                    "repo": {"full_name": "stranske/Consumer-Repo"},
                },
                "base": {"ref": "main"},
                "labels": [
                    "agent:codex",
                    "agents:keepalive",
                    "agent:retry",
                    "agent:needs-attention",
                    "agent:rate-limited",
                    "priority:high",
                ],
                "body": task_body,
                "comments": [{"id": 9004, "body": "unrelated PR comment state"}],
            },
            {
                "number": 105,
                "title": "Paused PR compatibility control",
                "state": "open",
                "draft": False,
                "mergeable": True,
                "mergeable_state": "clean",
                "head": {
                    "ref": "codex/issue-105",
                    "sha": "105deadbeef105deadbeef105deadbeef105dead",
                    "repo": {"full_name": "stranske/Consumer-Repo"},
                },
                "base": {"ref": "main", "repo": {"full_name": "stranske/Consumer-Repo"}},
                "user": {"login": "fixture-outsider"},
                "labels": [
                    "agent:codex",
                    "agents:keepalive",
                    "agents:paused",
                    "agent:needs-attention",
                ],
                "body": task_body,
                "comments": [{"id": 9005, "body": "paused PR state"}],
            },
            {
                "number": 106,
                "title": "Stalled PR without pre-existing retry label",
                "state": "open",
                "draft": False,
                "mergeable": True,
                "mergeable_state": "clean",
                "head": {
                    "ref": "codex/issue-106",
                    "sha": "106deadbeef106deadbeef106deadbeef106dead",
                    "repo": {"full_name": "stranske/Consumer-Repo"},
                },
                "base": {"ref": "main"},
                "labels": [
                    "agent:codex",
                    "agents:keepalive",
                    "agent:rate-limited",
                    "priority:medium",
                ],
                "body": task_body,
                "comments": [{"id": 9006, "body": "rate-limited PR context"}],
            },
        ],
        "liveLabelsOverride": {
            str(pr_num): labels for pr_num, labels in (live_labels_override or {}).items()
        },
        "combinedStatusBySha": {
            "103deadbeef103deadbeef103deadbeef103dead": "success",
            "104deadbeef104deadbeef104deadbeef104dead": "success",
            "105deadbeef105deadbeef105deadbeef105dead": "success",
            "106deadbeef106deadbeef106deadbeef106dead": "success",
        },
        "checkRunsBySha": {
            "103deadbeef103deadbeef103deadbeef103dead": [
                {"name": "pytest", "status": "completed", "conclusion": "failure"}
            ],
            "104deadbeef104deadbeef104deadbeef104dead": [
                {"name": "Gate / gate", "status": "completed", "conclusion": "success"}
            ],
            "106deadbeef106deadbeef106deadbeef106dead": [
                {"name": "Gate / gate", "status": "completed", "conclusion": "success"}
            ],
        },
        "gateRunsBySha": {
            "101deadbeef101deadbeef101deadbeef101dead": [
                {
                    "id": 7101,
                    "name": "Gate",
                    "status": "completed",
                    "conclusion": "success",
                    "head_sha": "101deadbeef101deadbeef101deadbeef101dead",
                }
            ],
            "103deadbeef103deadbeef103deadbeef103dead": [
                {
                    "id": 7103,
                    "name": "Gate",
                    "status": "completed",
                    "conclusion": "failure",
                    "head_sha": "103deadbeef103deadbeef103deadbeef103dead",
                }
            ],
            "104deadbeef104deadbeef104deadbeef104dead": [
                {
                    "id": 7104,
                    "name": "Gate",
                    "status": "completed",
                    "conclusion": "success",
                    "head_sha": "104deadbeef104deadbeef104deadbeef104dead",
                }
            ],
            "106deadbeef106deadbeef106deadbeef106dead": [
                {
                    "id": 7106,
                    "name": "Gate",
                    "status": "completed",
                    "conclusion": "success",
                    "head_sha": "106deadbeef106deadbeef106deadbeef106dead",
                }
            ],
        },
        "gateJobsByRunId": {
            "7103": [
                {
                    "id": 8103,
                    "name": "python ci / pytest",
                    "status": "completed",
                    "conclusion": "failure",
                    "steps": [{"name": "Run pytest", "conclusion": "failure"}],
                }
            ]
        },
    }

    if include_incident:
        head = "913515fe2a3e8f7a86b229244f8ec434a740dc31"
        scenario["prs"].append(
            {
                "number": 561,
                "title": "PR Health incident replay",
                "state": "open",
                "draft": False,
                "mergeable": True,
                "mergeable_state": "unstable",
                "head": {"ref": "exports/route-weights", "sha": head},
                "base": {"ref": "main"},
                "labels": [
                    "tracker:durable",
                    "autofix:escalated",
                    *([incident_status_label] if incident_status_label else []),
                ],
            }
        )
        scenario["combinedStatusBySha"][head] = {
            "state": "failure",
            "statuses": [{"state": "failure", "context": "Health 45 Agents Guard / guard"}],
        }
        scenario["checkRunsBySha"][head] = [
            {"name": "guard", "conclusion": "failure"},
            {"name": "detect changed files", "conclusion": "failure"},
            {"name": "automerge", "conclusion": "failure"},
        ]
        if incident_first:
            scenario["prs"].insert(0, scenario["prs"].pop())
        if incident_only:
            scenario["prs"] = [scenario["prs"][-1]]
            scenario["repo"] = "Orchestrator"
        if incident_checks_unavailable:
            scenario["unavailableChecksSha"] = head

    scenario_path = tmp_path / f"scenario-{run_tag}.json"
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
    harness_path = tmp_path / "pr_health_replay_harness.js"
    harness_path.write_text(PR_HEALTH_REPLAY_HARNESS_JS, encoding="utf-8")

    completed = subprocess.run(
        [node, str(harness_path), str(scenario_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return dict(json.loads(completed.stdout))


def test_pr_health_reports_unassigned_failing_head_without_dispatch(tmp_path: Path) -> None:
    replay = _run_pr_health_replay(tmp_path, include_incident=True)

    assert {event["inputs"]["pr_number"] for event in replay["workflowDispatches"]} == {
        "101",
        "103",
    }
    assert replay["scanOutputs"]["failing_count"] == "2"
    summary = "\n".join(replay["summaries"])
    assert "No agent routing label" in summary
    assert "Health 45 Agents Guard / guard" in summary
    assert "detect changed files" in summary
    assert "913515fe2a3e8f7a86b229244f8ec434a740dc31/checks" in summary
    assert "automerge" not in summary
    condition = yaml.safe_load(REUSABLE_PR_HEALTH.read_text())["jobs"]["fix-checks"]["if"]
    assert "needs.scan.outputs.check_dispatch_count != '0'" in condition
    assert "inputs.skip_check_fix != 'true'" in condition
    assert "inputs.dry_run != 'true'" in condition


def test_pr_health_retains_combined_failure_when_check_runs_unavailable(tmp_path: Path) -> None:
    replay = _run_pr_health_replay(
        tmp_path, include_incident=True, incident_only=True, incident_checks_unavailable=True
    )

    assert replay["scanOutputs"]["failing_count"] == "1"
    assert replay["scanOutputs"]["check_dispatch_count"] == "0"
    assert replay["workflowDispatches"] == []
    assert replay["repositoryDispatches"] == []
    assert any("Could not list check runs for PR #561" in item for item in replay["warnings"])
    summary = "\n".join(replay["summaries"])
    assert "https://github.com/stranske/Orchestrator/pull/561" in summary
    assert "Health 45 Agents Guard / guard" in summary


@pytest.mark.parametrize(
    ("max_dispatches", "status_label"),
    [
        (1, None),
        (0, None),
        (1, "agent:needs-attention"),
        (1, "agent:rate-limited"),
        (1, "agent:retry"),
        (1, "agent:"),
    ],
)
def test_pr_health_applies_dispatch_cap_only_to_participating_failures(
    tmp_path: Path, max_dispatches: int, status_label: str | None
) -> None:
    replay = _run_pr_health_replay(
        tmp_path,
        include_incident=True,
        incident_first=True,
        incident_status_label=status_label,
        max_dispatches=max_dispatches,
    )

    assert replay["scanOutputs"]["failing_count"] == "2"
    assert replay["scanOutputs"]["check_dispatch_count"] == str(max_dispatches)
    expected = {"101", "103"} if max_dispatches else set()
    assert {event["inputs"]["pr_number"] for event in replay["workflowDispatches"]} == expected
    assert replay["branchUpdates"] == ([101] if max_dispatches else [])
    summary = "\n".join(replay["summaries"])
    assert "No agent routing label; no dispatch" in summary
    assert "Health 45 Agents Guard / guard" in summary
    assert "pytest" in summary
    if max_dispatches == 0:
        assert "Follow-up dispatch cap reached" in summary


def test_pr_health_dispatch_reaches_installed_consumer(tmp_path: Path) -> None:
    """Replay PR-health scan, conflict and check-fix steps against consumer templates."""
    consumer_wrapper = yaml.safe_load(CONSUMER_PR_HEALTH.read_text(encoding="utf-8"))
    reusable_workflow = yaml.safe_load(REUSABLE_PR_HEALTH.read_text(encoding="utf-8"))
    sync_manifest = yaml.safe_load(SYNC_MANIFEST.read_text(encoding="utf-8"))
    installed_workflows = _installed_consumer_workflows()

    # 1. Compatibility control: consumer entry point and inherited secrets boundary.
    health_job = consumer_wrapper["jobs"]["health"]
    assert (
        health_job["uses"]
        == "stranske/Workflows/.github/workflows/reusable-agents-pr-health.yml@main"
    )
    assert health_job["secrets"] == "inherit"

    reusable_on = _workflow_on_block(reusable_workflow)
    declared_secrets = set((reusable_on["workflow_call"].get("secrets") or {}).keys())
    assert declared_secrets == {
        "service_bot_pat",
        "ACTIONS_BOT_PAT",
        "WORKFLOWS_APP_ID",
        "WORKFLOWS_APP_PRIVATE_KEY",
        "CODEX_AUTH_JSON",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "CLAUDE_AUTH_JSON",
    }
    setup_steps = [
        step
        for step in reusable_workflow["jobs"]["scan"]["steps"]
        if step.get("uses") == "./.github/actions/setup-api-client"
    ]
    assert len(setup_steps) == 1
    assert "secrets" not in (setup_steps[0].get("with") or {})

    synced_workflows = {entry["source"] for entry in sync_manifest.get("workflows", [])}
    removed_workflows = {entry["target"] for entry in sync_manifest.get("removals", [])}
    assert ".github/workflows/agents-pr-health.yml" in synced_workflows
    assert ".github/workflows/agents-81-gate-followups.yml" in synced_workflows
    assert ".github/workflows/agents-keepalive-loop.yml" in removed_workflows
    assert "agents-keepalive-loop.yml" not in installed_workflows

    # 2. Behavioral replay of live PR-health steps against installed consumer templates.
    replay = _run_pr_health_replay(tmp_path, dry_run=False)
    assert replay["receiverGuards"] == [
        {
            "pr_number": str(number),
            "outputs": {"blocked": "false", "reason": "all-checks-passed"},
            "failed": False,
        }
        for number in (101, 103)
    ]
    assert replay["warnings"] == []
    assert replay["scanOutputs"] == {
        "conflict_count": "2",
        "failing_count": "1",
        "check_dispatch_count": "1",
        "stalled_scan_count": "2",
        "healthy_count": "3",
        "total_open": "6",
        "has_work": "true",
    }
    assert replay["branchUpdates"] == [101, 102]

    observed_handoff = {
        "repository_dispatches": replay["repositoryDispatches"],
        "workflow_dispatches": replay["workflowDispatches"],
        "removed_labels": replay["removedLabels"],
        "added_labels": replay["addedLabels"],
        "final_stalled_labels": {
            "104": sorted(replay["finalLabels"]["104"]),
            "106": sorted(replay["finalLabels"]["106"]),
        },
    }
    assert observed_handoff == {
        "repository_dispatches": [],
        "workflow_dispatches": [
            {
                "owner": "stranske",
                "repo": "Consumer-Repo",
                "workflow_id": "agents-81-gate-followups.yml",
                "ref": "main",
                "inputs": {
                    "pr_number": "101",
                    "force_retry": "false",
                },
            },
            {
                "owner": "stranske",
                "repo": "Consumer-Repo",
                "workflow_id": "agents-81-gate-followups.yml",
                "ref": "main",
                "inputs": {
                    "pr_number": "103",
                    "force_retry": "false",
                },
            },
        ],
        # Cohesion round 2 (D3): stalled PRs are reported, never relabelled. The old
        # nudge re-added agent:retry hourly; consumer agents-81 has no agent:retry handler.
        "removed_labels": [],
        "added_labels": [],
        "final_stalled_labels": {
            "104": [
                "agent:codex",
                "agent:needs-attention",
                "agent:rate-limited",
                "agent:retry",
                "agents:keepalive",
                "priority:high",
            ],
            "106": [
                "agent:codex",
                "agent:rate-limited",
                "agents:keepalive",
                "priority:medium",
            ],
        },
    }

    for dispatch in replay["workflowDispatches"]:
        target_name = dispatch["workflow_id"]
        assert (
            target_name in installed_workflows
        ), f"Target {target_name} is not installed in consumers"
        target_on = _workflow_on_block(installed_workflows[target_name])
        assert "workflow_dispatch" in target_on
        accepted_inputs = set((target_on["workflow_dispatch"].get("inputs") or {}).keys())
        assert set(dispatch["inputs"].keys()) <= accepted_inputs

    # 3. No stalled-PR nudge exists: no job of the reusable workflow relabels a PR.
    assert "nudge-stalled" not in reusable_workflow["jobs"]
    assert replay["labelEvents"] == []
    # Paused PR #105 and unrelated comment state survive unchanged.
    assert set(replay["finalLabels"]["105"]) == {
        "agent:codex",
        "agents:keepalive",
        "agents:paused",
        "agent:needs-attention",
    }
    assert replay["finalComments"]["104"] == [{"id": 9004, "body": "unrelated PR comment state"}]
    assert replay["finalComments"]["105"] == [{"id": 9005, "body": "paused PR state"}]
    assert replay["finalComments"]["106"] == [{"id": 9006, "body": "rate-limited PR context"}]

    # 4. Trace receiving consumer workflow evaluation across conflict and fix-checks wakeups.
    receiver_by_pr = {
        int(item["outputs"]["pr_number"]): item for item in replay["receiverEvaluations"]
    }
    assert set(receiver_by_pr.keys()) == {101, 103}

    assert receiver_by_pr[101]["trigger"] == "workflow_dispatch"
    assert receiver_by_pr[101]["ref"] == "main"
    assert receiver_by_pr[101]["outputs"]["agent_type"] == "codex"
    assert receiver_by_pr[101]["outputs"]["pr_ref"] == "codex/issue-101"
    assert receiver_by_pr[101]["outputs"]["head_sha"] == "101deadbeef101deadbeef101deadbeef101dead"
    assert receiver_by_pr[101]["outputs"]["action"] == "conflict"
    assert (
        receiver_by_pr[101]["outputs"]["prompt_file"]
        == ".github/codex/prompts/fix_merge_conflicts.md"
    )

    assert receiver_by_pr[103]["trigger"] == "workflow_dispatch"
    assert receiver_by_pr[103]["ref"] == "main"
    assert receiver_by_pr[103]["outputs"]["agent_type"] == "claude"
    assert receiver_by_pr[103]["outputs"]["pr_ref"] == "claude/issue-103"
    assert receiver_by_pr[103]["outputs"]["head_sha"] == "103deadbeef103deadbeef103deadbeef103dead"
    assert receiver_by_pr[103]["outputs"]["action"] == "fix"
    assert receiver_by_pr[103]["outputs"]["reason"].startswith("fix-")

    blocked_replay = _run_pr_health_replay(tmp_path, label="guard-controls", guard_controls=True)
    assert {
        item["pr_number"]: item["outputs"]["reason"]
        for item in blocked_replay["receiverGuards"]
        if item["failed"] and item["outputs"]["blocked"] == "true"
    } == {
        "105": "non-collaborator-blocked",
        "": "invalid-dispatch-pr-number",
        "101junk": "invalid-dispatch-pr-number",
        "999": "unresolved-dispatch-pr",
    }
    assert blocked_replay["receiverEvaluations"] == replay["receiverEvaluations"]

    # 5. Compatibility control: dry_run previews without mutating.
    dry_replay = _run_pr_health_replay(tmp_path, dry_run=True)
    assert dry_replay["warnings"] == []
    assert dry_replay["workflowDispatches"] == []
    assert dry_replay["repositoryDispatches"] == []
    assert dry_replay["removedLabels"] == []
    assert dry_replay["addedLabels"] == []
    assert set(dry_replay["finalLabels"]["104"]) == {
        "agent:codex",
        "agents:keepalive",
        "agent:retry",
        "agent:needs-attention",
        "agent:rate-limited",
        "priority:high",
    }
    assert set(dry_replay["finalLabels"]["106"]) == {
        "agent:codex",
        "agents:keepalive",
        "agent:rate-limited",
        "priority:medium",
    }
