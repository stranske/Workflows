"""Executable regressions for Health 41 default-branch required-context drift (#4719)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/health-41-repo-health.yml"
GATE_FORK_STATUS_TEST = REPO_ROOT / "tests/workflows/test_gate_fork_status_publication.py"
GATE_CONSOLIDATION_TEST = REPO_ROOT / "tests/workflows/test_workflow_agents_consolidation.py"
STEP_NAME = "Verify default branch protection"
DEFAULT_BRANCH = "main"


def _extract_protection_script(workflow: Path = WORKFLOW) -> str:
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    for job in document["jobs"].values():
        for step in job.get("steps") or []:
            if step.get("name") == STEP_NAME:
                return str(step["with"]["script"])
    raise AssertionError(f"{workflow} no longer defines {STEP_NAME!r}")


def _run_protection_script(
    *,
    branch_rules: list[dict[str, Any]] | None = None,
    branch_rules_error: dict[str, Any] | None = None,
    protection_error: dict[str, Any] | None = None,
    protection_payload: dict[str, Any] | None = None,
    branch_payload: dict[str, Any] | None = None,
    required_contexts: list[str] | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:  # pragma: no cover - host dependent
        message = "node is required to execute the Health 41 protection script"
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)

    if required_contexts is not None and cwd is None:
        workdir = Path(tempfile.mkdtemp(prefix="health41-config-"))
        scripts_dir = workdir / ".github/scripts"
        scripts_dir.mkdir(parents=True)
        shutil.copy(
            REPO_ROOT / ".github/scripts/github-api-with-retry.js",
            scripts_dir / "github-api-with-retry.js",
        )
        config_dir = workdir / ".github/config"
        config_dir.mkdir(parents=True)
        (config_dir / "required-contexts.json").write_text(
            json.dumps({"required_contexts": required_contexts}),
            encoding="utf-8",
        )
    else:
        workdir = cwd or REPO_ROOT

    fixture = {
        "branchRules": branch_rules if branch_rules is not None else [],
        "branchRulesError": branch_rules_error,
        "protectionError": protection_error,
        "protectionPayload": protection_payload,
        "branchPayload": branch_payload,
    }

    harness = textwrap.dedent(r"""
        const fs = require('fs');
        const vm = require('vm');
        const fixture = JSON.parse(process.env.FIXTURE);

        function makeError(status, message) {
          const error = new Error(message);
          error.status = status;
          return error;
        }

        const failures = [];
        const warnings = [];
        const infos = [];
        const summaryRaw = [];
        const summaryStub = {
          addHeading() { return summaryStub; },
          addTable() { return summaryStub; },
          addRaw(text) { summaryRaw.push(String(text)); return summaryStub; },
          async write() {},
        };

        const github = {
          rest: {
            repos: {
              getBranchProtection: async () => {
                if (fixture.protectionError) {
                  throw makeError(
                    fixture.protectionError.status,
                    fixture.protectionError.message,
                  );
                }
                return { data: fixture.protectionPayload || {} };
              },
              getBranch: async () => ({ data: fixture.branchPayload || {} }),
            },
          },
          paginate: async (method, _params) => {
            if (method !== github.rest.repos.getBranchRules) {
              throw new Error(`Unexpected paginate method: ${method?.name || method}`);
            }
            if (fixture.branchRulesError) {
              throw makeError(
                fixture.branchRulesError.status,
                fixture.branchRulesError.message,
              );
            }
            return fixture.branchRules;
          },
        };
        github.rest.repos.getBranchRules = { name: 'getBranchRules' };

        const sandbox = {
          process: { env: { DEFAULT_BRANCH: process.env.DEFAULT_BRANCH || 'main' } },
          console: { log() {} },
          require: (name) => {
            if (name === 'fs') {
              return fs;
            }
            if (String(name).endsWith('github-api-with-retry.js')) {
              return { withRetry: async (fn) => fn() };
            }
            throw new Error(`Unexpected require: ${name}`);
          },
          fs,
          core: {
            setFailed(message) { failures.push(String(message)); },
            warning(message) { warnings.push(String(message)); },
            info(message) { infos.push(String(message)); },
            summary: summaryStub,
          },
          context: { repo: { owner: 'stranske', repo: 'Workflows' } },
          github,
        };
        vm.createContext(sandbox);

        const main = async () => {
          let scriptError = null;
          try {
            await vm.runInContext(
              `(async () => {\n${process.env.SCRIPT}\n})()`,
              sandbox,
            );
          } catch (error) {
            scriptError = String(error.message || error);
          }
          process.stdout.write(JSON.stringify({
            failures,
            warnings,
            infos,
            summaryRaw,
            threw: scriptError,
          }));
        };

        main().catch((error) => {
          console.error(String(error.message || error));
          process.exit(1);
        });
        """).strip()

    script_body = _extract_protection_script()

    env = os.environ.copy()
    env["FIXTURE"] = json.dumps(fixture)
    env["DEFAULT_BRANCH"] = DEFAULT_BRANCH
    env["SCRIPT"] = script_body

    completed = subprocess.run(
        [node, "-e", harness],
        capture_output=True,
        text=True,
        check=False,
        cwd=workdir,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    return dict(json.loads(completed.stdout))


@pytest.fixture(scope="module")
def protection_script() -> str:
    return _extract_protection_script()


def test_health41_reads_required_contexts_json_not_hardcoded(
    protection_script: str,
) -> None:
    assert "Gate / gate" not in protection_script
    assert "required-contexts.json" in protection_script
    assert "getBranchRules" in protection_script
    assert "required_status_checks" in protection_script

    rules_only_summary = [
        {
            "type": "required_status_checks",
            "parameters": {
                "required_status_checks": [{"context": "summary"}],
            },
        }
    ]
    outcome = _run_protection_script(
        branch_rules=rules_only_summary,
        protection_error={"status": 404, "message": "Branch not protected"},
    )
    assert outcome["failures"] == [], outcome
    assert any("match the expected configuration" in line for line in outcome["summaryRaw"])


@pytest.mark.parametrize(
    "protection_error",
    [
        {"status": 404, "message": "Branch not protected"},
        {"status": 403, "message": "Resource not accessible by integration"},
    ],
)
def test_health41_ruleset_only_summary_passes_without_classic_protection(
    protection_error: dict[str, Any],
) -> None:
    outcome = _run_protection_script(
        branch_rules=[
            {
                "type": "required_status_checks",
                "parameters": {
                    "required_status_checks": [{"context": "summary"}],
                },
            }
        ],
        protection_error=protection_error,
        branch_payload={
            "protected": True,
            "protection": {
                "enabled": False,
                "required_status_checks": {
                    "contexts": [],
                    "checks": [],
                    "enforcement_level": "off",
                },
            },
        },
    )
    assert outcome["failures"] == [], outcome


def test_health41_recovers_classic_contexts_from_branch_metadata_after_403() -> None:
    outcome = _run_protection_script(
        protection_error={"status": 403, "message": "Resource not accessible by integration"},
        branch_payload={
            "protected": True,
            "protection": {"enabled": True, "required_status_checks": {"contexts": ["summary"]}},
        },
    )
    assert outcome["failures"] == [], outcome
    assert any("match the expected configuration" in line for line in outcome["summaryRaw"])


@pytest.mark.parametrize(
    ("unread_source", "status"),
    [("branch rules", 500), ("branch protection", 403), ("branch protection", 404)],
)
def test_health41_rejects_an_exact_match_from_only_one_source(
    unread_source: str, status: int
) -> None:
    if unread_source == "branch rules":
        outcome = _run_protection_script(
            branch_rules_error={"status": status, "message": "Internal Server Error"},
            protection_payload={"required_status_checks": {"contexts": ["summary"]}},
        )
    else:
        outcome = _run_protection_script(
            branch_rules=[
                {
                    "type": "required_status_checks",
                    "parameters": {"required_status_checks": [{"context": "summary"}]},
                }
            ],
            protection_error={"status": status, "message": "Resource not found or inaccessible"},
            branch_payload={"protected": True, "protection": {"enabled": True}},
        )

    assert outcome["threw"] is None, outcome
    assert len(outcome["failures"]) == 1, outcome
    assert "Unable to read branch protection configuration" in outcome["failures"][0]
    assert f"{unread_source}:" in outcome["failures"][0]
    verdict = " ".join(outcome["summaryRaw"] + outcome["infos"] + outcome["failures"])
    assert "match" not in verdict
    assert "drift" not in verdict


@pytest.mark.parametrize(
    "payload", [{}, {"required_contexts": "summary"}, {"contexts": [False, " "]}]
)
def test_health41_rejects_malformed_config_with_no_observed_checks(
    tmp_path: Path, payload: dict[str, Any]
) -> None:
    config_dir = tmp_path / ".github/config"
    config_dir.mkdir(parents=True)
    (config_dir / "required-contexts.json").write_text(json.dumps(payload), encoding="utf-8")

    outcome = _run_protection_script(cwd=tmp_path)

    assert outcome["threw"] is None, outcome
    assert len(outcome["failures"]) == 1, outcome
    assert "Unable to load required contexts" in outcome["failures"][0]
    assert outcome["summaryRaw"] == []


def test_health41_loads_valid_legacy_contexts_when_primary_key_is_malformed(tmp_path: Path) -> None:
    config_dir = tmp_path / ".github/config"
    config_dir.mkdir(parents=True)
    (config_dir / "required-contexts.json").write_text(
        json.dumps({"required_contexts": "invalid", "contexts": ["summary"]}), encoding="utf-8"
    )

    outcome = _run_protection_script(
        cwd=tmp_path, protection_payload={"required_status_checks": {"contexts": ["summary"]}}
    )

    assert outcome["failures"] == [], outcome
    assert any("match the expected configuration" in line for line in outcome["summaryRaw"])


def test_health41_missing_configured_context_fails_generically() -> None:
    outcome = _run_protection_script(
        branch_rules=[],
        protection_error={"status": 404, "message": "Branch not protected"},
        required_contexts=["summary"],
    )
    joined = " ".join(outcome["failures"])
    assert "Branch protection drift detected" in joined, outcome
    assert "missing contexts: summary" in joined
    assert "Gate / gate" not in joined


def test_health41_nonexistent_expected_context_fails() -> None:
    outcome = _run_protection_script(
        branch_rules=[
            {
                "type": "required_status_checks",
                "parameters": {
                    "required_status_checks": [{"context": "summary"}],
                },
            }
        ],
        protection_error={"status": 404, "message": "Branch not protected"},
        required_contexts=["definitely-missing-context"],
    )
    joined = " ".join(outcome["failures"])
    assert "definitely-missing-context" in joined
    assert "Gate / gate" not in joined


def test_health41_union_includes_classic_checks_and_rules() -> None:
    outcome = _run_protection_script(
        branch_rules=[
            {
                "type": "required_status_checks",
                "parameters": {
                    "required_status_checks": [{"context": "summary"}],
                },
            }
        ],
        protection_payload={
            "required_status_checks": {
                "contexts": ["Health 45 Agents Guard / guard"],
                "checks": [{"context": "Gate / gate"}],
                "strict": True,
            }
        },
        required_contexts=["summary"],
    )
    joined_infos = " ".join(outcome["infos"])
    assert "Gate / gate" in joined_infos
    assert "summary" in joined_infos
    assert any("unexpected contexts" in raw for raw in outcome["summaryRaw"])


def test_health41_branch_rules_api_error_is_not_reported_as_missing_context() -> None:
    outcome = _run_protection_script(
        branch_rules_error={"status": 500, "message": "Internal Server Error"},
        protection_error={"status": 404, "message": "Branch not protected"},
        required_contexts=["summary"],
    )
    joined = " ".join(outcome["failures"])
    assert "Unable to read branch protection configuration" in joined
    assert "missing contexts: summary" not in joined
    assert all("drift" not in raw for raw in outcome["summaryRaw"])


def test_health41_protection_script_does_not_hardcode_expected_list(
    protection_script: str,
) -> None:
    assert "Gate / gate" not in protection_script
    assert "required-contexts.json" in protection_script
    assert re.search(r"expectedContexts\s*=\s*\[\s*'Gate / gate'\s*\]", protection_script) is None
    assert "required_contexts" in protection_script or "contextsValue" in protection_script


def test_health41_deliberate_break_hardcoded_gate_fails_then_restore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance deliberate-break: hardcoded Gate / gate must fail, then production passes."""
    original_script = _extract_protection_script()
    assert "Gate / gate" not in original_script

    broken_script = original_script.replace(
        """expectedContexts = contextsValue
      .map((value) => `${value}`.trim())
      .filter(Boolean);""",
        "expectedContexts = ['Gate / gate'];",
        1,
    )
    assert broken_script != original_script
    assert "expectedContexts = ['Gate / gate']" in broken_script

    with pytest.raises(AssertionError, match="Gate / gate"):
        assert "Gate / gate" not in broken_script

    rules_only_summary = [
        {
            "type": "required_status_checks",
            "parameters": {
                "required_status_checks": [{"context": "summary"}],
            },
        }
    ]

    monkeypatch.setattr(
        sys.modules[__name__],
        "_extract_protection_script",
        lambda workflow=WORKFLOW: broken_script,
    )
    broken_outcome = _run_protection_script(
        branch_rules=rules_only_summary,
        protection_error={"status": 404, "message": "Branch not protected"},
    )
    joined = " ".join(broken_outcome["failures"])
    assert "Gate / gate" in joined
    assert "missing contexts" in joined

    monkeypatch.undo()

    test_health41_reads_required_contexts_json_not_hardcoded(original_script)
    restored_outcome = _run_protection_script(
        branch_rules=rules_only_summary,
        protection_error={"status": 404, "message": "Branch not protected"},
    )
    assert restored_outcome["failures"] == [], restored_outcome
    test_health41_nonexistent_expected_context_fails()


def test_health41_gate_status_publication_tests_retain_duplicate_gate_context() -> None:
    """Health 41 loads summary from config; Gate duplicate-status tests stay intentional."""
    fork_source = GATE_FORK_STATUS_TEST.read_text(encoding="utf-8")
    assert '"context": "Gate / gate"' in fork_source
    assert 'outcome["writes"][0]["context"] == "Gate / gate"' in fork_source

    consolidation_source = GATE_CONSOLIDATION_TEST.read_text(encoding="utf-8")
    assert "publish the Gate / gate commit status" in consolidation_source
