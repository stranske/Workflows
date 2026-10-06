"""Completeness controls for the shared adapter, including the incident shapes."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "check_topology", Path(__file__).parents[1] / "scripts/check_checks_reported.py"
)
assert SPEC and SPEC.loader
reporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reporter)
HEAD = "a" * 40
BASE = "b" * 40


def check(name="gate", conclusion="success", ident=1, started="2026-10-01T01:00:00Z"):
    return {
        "name": name,
        "conclusion": conclusion,
        "id": ident,
        "started_at": started,
        "status": "completed",
        "app": {"id": 15368, "slug": "github-actions"},
    }


def verdict(
    expected=None, checks=None, suites=None, runs=None, unknown=None, required=None, statuses=None
):
    run_list = runs if runs is not None else []
    applicable = (
        {item.get("workflow_id") for item in run_list if item.get("workflow_id") is not None}
        if runs is not None
        else None
    )
    return reporter.adjudicate(
        {"gate"} if expected is None else expected,
        [check()] if checks is None else checks,
        statuses or [],
        suites or [],
        run_list,
        unknown or [],
        required or [],
        applicable,
    )


def test_missing_required_check_is_fail():
    result = verdict(checks=[], required=[{"context": "gate"}])
    assert result["verdict"] == "FAIL"
    assert result["missing_names"] == ["gate"]


def test_legitimately_absent_event_only_job():
    # Actual Orchestrator461 incident shape: auto-pilot only on labeled/closed.
    applies, reason = reporter.event_applies(
        {"on": {"pull_request": {"types": ["labeled", "closed"]}}},
        "pull_request",
        "opened",
        "main",
        ["src/example.py"],
    )
    assert not applies and "opened" in reason
    assert verdict()["verdict"] == "PASS"


def test_stale_cancelled_attempt_replaced_by_success():
    result = verdict(
        checks=[check(conclusion="cancelled"), check(ident=2, started="2026-10-01T02:00:00Z")]
    )
    assert result["verdict"] == "PASS"
    assert result["states"]["gate"]["order"][1] == 2


def test_new_cancelled_attempt_does_not_reuse_old_success():
    assert (
        verdict(
            checks=[check(), check(conclusion="cancelled", ident=2, started="2026-10-01T02:00:00Z")]
        )["verdict"]
        == "FAIL"
    )


def test_zero_job_startup_failure_is_fail_even_with_green_check():
    result = verdict(runs=[{"id": 90, "jobs": [], "conclusion": "action_required"}])
    assert result["verdict"] == "FAIL"
    assert result["startup_failures"][0]["id"] == 90


def test_zero_job_failed_suite_is_fail():
    workflow_id = 42
    assert (
        verdict(
            suites=[
                {
                    "id": 90,
                    "conclusion": "failure",
                    "workflow_id": workflow_id,
                    "latest_check_runs_count": 0,
                }
            ],
            runs=[{"id": 1, "workflow_id": workflow_id, "jobs": []}],
            unknown=[],
            required=[],
        )["verdict"]
        == "FAIL"
    )


def test_optional_failed_suite_outside_applicable_workflow_does_not_fail():
    assert (
        verdict(
            suites=[
                {
                    "id": 90,
                    "conclusion": "failure",
                    "workflow_id": 99,
                    "latest_check_runs_count": 0,
                }
            ],
            runs=[{"id": 1, "workflow_id": 42, "jobs": [check()]}],
            unknown=[],
            required=[],
        )["verdict"]
        == "PASS"
    )


def test_types_as_string_does_not_substring_match_opened():
    applies, _ = reporter.event_applies(
        {"on": {"pull_request": {"types": "reopened"}}},
        "pull_request",
        "opened",
        "main",
        ["src/a.py"],
    )
    assert not applies


def test_duplicate_expected_job_names_force_unknown():
    job_provenance = {
        "gate": {f"o/r/a.yml@{BASE}", f"o/r/b.yml@{BASE}"},
    }
    unknown = []
    for job_name, sources in job_provenance.items():
        if len(sources) > 1:
            unknown.append(f"duplicate expected check identity {job_name!r}")
    result = verdict(expected={"gate"}, unknown=unknown)
    assert result["verdict"] == "UNKNOWN"


def test_empty_expectation_cannot_pass():
    assert verdict(expected=set())["verdict"] == "UNKNOWN"


def test_unsupported_evidence_is_unknown():
    assert verdict(unknown=["dynamic matrix"])["verdict"] == "UNKNOWN"


def test_missing_required_reporter_overrides_unknown():
    assert verdict(checks=[], unknown=["inaccessible workflow"])["verdict"] == "FAIL"


def test_required_check_skip_is_not_success():
    assert (
        verdict(checks=[check(conclusion="skipped")], required=[{"context": "gate"}])["verdict"]
        == "FAIL"
    )


def test_required_app_mismatch_is_unknown():
    assert verdict(required=[{"context": "gate", "app_id": 99}])["verdict"] == "UNKNOWN"


def test_latest_status_replaces_old_failure_regardless_of_page_order():
    statuses = [
        {"context": "gate", "created_at": "2026-10-01T02:00:00Z", "id": 2, "state": "success"},
        {"context": "gate", "created_at": "2026-10-01T01:00:00Z", "id": 1, "state": "failure"},
    ]
    assert verdict(checks=[], statuses=statuses)["verdict"] == "PASS"
    assert verdict(checks=[], statuses=list(reversed(statuses)))["verdict"] == "PASS"


def test_status_success_cannot_mask_failed_check_run():
    assert (
        verdict(
            checks=[check(conclusion="failure")], statuses=[{"context": "gate", "state": "success"}]
        )["verdict"]
        == "FAIL"
    )


def test_paginated_checks_are_all_enumerated():
    evidence = reporter.Evidence(
        lambda _: [
            {"total_count": 2, "check_runs": [check()]},
            {"total_count": 2, "check_runs": [check("test", ident=2)]},
        ]
    )
    assert len(evidence.items("checks", "check_runs")) == 2
    assert evidence.requests[0]["pages"] == 2


def test_truncated_suites_cannot_pass():
    evidence = reporter.Evidence(lambda _: [{"total_count": 2, "check_suites": [{}]}])
    with pytest.raises(reporter.UnknownEvidence, match="enumerated 1 of 2"):
        evidence.items("suites", "check_suites")


def test_inaccessible_discovery_becomes_unknown_evidence():
    def inaccessible(_):
        raise SystemExit("rate limit reached")

    with pytest.raises(reporter.UnknownEvidence, match="rate limit"):
        reporter.Evidence(inaccessible).pages("workflow")


def test_yaml_on_is_not_boolean():
    document = reporter.yaml.load("on: [pull_request]\njobs: {}", Loader=reporter.WorkflowLoader)
    assert "on" in document and True not in document


@pytest.mark.parametrize(
    "pattern,value,expected",
    [
        ("docs/**", "docs/a/b.md", True),
        ("**/*.py", "a.py", True),
        ("**/*.py", "src/a.py", True),
        ("*.py", "src/a.py", False),
    ],
)
def test_actions_glob_subset(pattern, value, expected):
    assert reporter.glob_match(value, pattern) is expected


def test_negated_path_glob_is_unknown_instead_of_false_absence():
    with pytest.raises(reporter.UnknownEvidence, match="unsupported Actions glob"):
        reporter.event_applies(
            {"on": {"pull_request": {"paths": ["**", "!docs/**"]}}},
            "pull_request",
            "opened",
            "main",
            ["docs/a.md"],
        )


def test_branch_and_path_absence_has_concrete_reason():
    applies, reason = reporter.event_applies(
        {"on": {"pull_request": {"branches": ["release/**"]}}},
        "pull_request",
        "opened",
        "main",
        ["src/a.py"],
    )
    assert not applies and "branches excludes" in reason


def test_literal_matrix_names():
    assert reporter.job_names(
        "test",
        {"name": "test ${{ matrix.python }}", "strategy": {"matrix": {"python": ["3.11", "3.12"]}}},
    ) == ["test 3.11", "test 3.12"]


def test_dynamic_matrix_is_unknown():
    with pytest.raises(reporter.UnknownEvidence, match="unsupported matrix"):
        reporter.job_names(
            "test", {"strategy": {"matrix": "${{ fromJSON(needs.setup.outputs.matrix) }}"}}
        )


def test_reusable_child_workflow_names():
    content = "on: workflow_call\njobs:\n  lint:\n    name: Lint\n    runs-on: ubuntu-latest\n    steps: []\n"
    evidence = reporter.Evidence(
        lambda _: [{"encoding": "base64", "content": base64.b64encode(content.encode()).decode()}]
    )
    names = reporter.expected_jobs(
        evidence,
        "o/r",
        ".github/workflows/gate.yml",
        BASE,
        {"jobs": {"ci": {"name": "Python CI", "uses": "./.github/workflows/child.yml"}}},
    )
    assert names == {"Python CI / Lint"}


def test_floating_reusable_workflow_is_unknown():
    with pytest.raises(reporter.UnknownEvidence, match="unpinned"):
        reporter.expected_jobs(
            reporter.Evidence(lambda _: []),
            "o/r",
            "gate.yml",
            BASE,
            {"jobs": {"ci": {"uses": "o/r/.github/workflows/ci.yml@main"}}},
        )


def test_conditional_reusable_workflow_is_unknown():
    with pytest.raises(reporter.UnknownEvidence, match="conditional reusable"):
        reporter.expected_jobs(
            reporter.Evidence(lambda _: []),
            "o/r",
            "gate.yml",
            BASE,
            {
                "jobs": {
                    "ci": {
                        "uses": "./.github/workflows/ci.yml",
                        "if": "needs.setup.outputs.run == 'true'",
                    }
                }
            },
        )


def fixture_transport(changed_head=False, forged=False):
    workflow = "on: pull_request\njobs:\n  gate:\n    runs-on: ubuntu-latest\n    steps: []\n"
    calls = []

    def transport(endpoint):
        calls.append(endpoint)
        if endpoint.endswith("/pulls/1"):
            count = calls.count(endpoint)
            return [
                {
                    "head": {"sha": "c" * 40 if changed_head and count > 1 else HEAD},
                    "base": {"sha": BASE, "ref": "main"},
                    "changed_files": 1,
                }
            ]
        if "/files?" in endpoint:
            return [[{"filename": "src/a.py"}]]
        if "/check-runs?" in endpoint:
            item = check()
            if forged:
                item["app"] = {"id": 99, "slug": "other-app"}
            return [{"total_count": 1, "check_runs": [item]}]
        if "/check-suites?" in endpoint:
            return [{"total_count": 0, "check_suites": []}]
        if "/statuses?" in endpoint or "/rules/branches/" in endpoint:
            return [[]]
        if endpoint.endswith("/branches/main"):
            return [{"protected": False}]
        if "/contents/.github/workflows?" in endpoint:
            return [[{"path": ".github/workflows/gate.yml", "sha": "d" * 40}]]
        if "/contents/.github/workflows/gate.yml?" in endpoint:
            return [{"encoding": "base64", "content": base64.b64encode(workflow.encode()).decode()}]
        if "/actions/runs?" in endpoint:
            return [{"total_count": 0, "workflow_runs": []}]
        raise AssertionError(endpoint)

    return transport


def test_complete_static_topology_receipt_is_bound_to_full_head():
    result = reporter.collect(
        reporter.Evidence(fixture_transport()), "o/r", 1, HEAD, "pull_request", "opened"
    )
    assert result["verdict"] == "PASS"
    assert result["head"] == HEAD and result["base"] == BASE
    assert result["expected_names"] == ["gate"]
    assert result["workflow_sources"][0]["document"]["jobs"]
    assert result["merge_authorization"] is False


def test_head_changed_during_collection_is_unknown():
    assert (
        reporter.collect(
            reporter.Evidence(fixture_transport(changed_head=True)),
            "o/r",
            1,
            HEAD,
            "pull_request",
            "opened",
        )["verdict"]
        == "UNKNOWN"
    )


def test_other_app_cannot_supply_workflow_completeness():
    assert (
        reporter.collect(
            reporter.Evidence(fixture_transport(forged=True)),
            "o/r",
            1,
            HEAD,
            "pull_request",
            "opened",
        )["verdict"]
        == "UNKNOWN"
    )


def test_incumbent_transport_is_reused_without_copying_reference_algorithm(tmp_path):
    incumbent = tmp_path / "presence.py"
    incumbent.write_text("def _gh_json(path):\n    return [{'endpoint': path}]\n")
    assert reporter.load_presence_reporter(incumbent)("checks") == [{"endpoint": "checks"}]


def invoke_main(monkeypatch, incumbent, output):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_checks_reported.py",
            "--repo",
            "o/r",
            "--pr",
            "1",
            "--head",
            HEAD,
            "--event",
            "pull_request",
            "--action",
            "opened",
            "--presence-reporter",
            str(incumbent),
            "--output",
            str(output),
        ],
    )
    code = reporter.main()
    return code, json.loads(output.read_text())


@pytest.mark.parametrize(
    "source,reason",
    [
        (
            "def _gh_json(path):\n    raise SystemExit('GitHub rate limit reached')\n",
            "GitHub rate limit reached",
        ),
        ("# No compatible transport\n", "lacks its paginated _gh_json transport"),
    ],
)
def test_unknown_cli_receipt_retains_incumbent_identity(tmp_path, monkeypatch, source, reason):
    incumbent = tmp_path / "presence.py"
    incumbent.write_text(source)
    output = tmp_path / "evidence" / "receipt.json"

    code, receipt = invoke_main(monkeypatch, incumbent, output)

    assert code == 2 and receipt["verdict"] == "UNKNOWN"
    assert reason in receipt["unknown"][0]
    assert receipt["head"] == HEAD
    assert receipt["presence_reporter"] == {
        "path": str(incumbent),
        "sha256": hashlib.sha256(incumbent.read_bytes()).hexdigest(),
    }
    assert receipt["evidence_complete"] is False
    assert receipt["merge_authorization"] is False


def test_successful_cli_receipt_retains_incumbent_identity(tmp_path, monkeypatch):
    incumbent = tmp_path / "presence.py"
    incumbent.write_text("# Tracked incumbent\n")
    monkeypatch.setattr(reporter, "load_presence_reporter", lambda _: fixture_transport())

    code, receipt = invoke_main(monkeypatch, incumbent, tmp_path / "receipt.json")

    assert code == 0 and receipt["verdict"] == "PASS"
    assert (
        receipt["presence_reporter"]["sha256"] == hashlib.sha256(incumbent.read_bytes()).hexdigest()
    )
    assert receipt["expected_names"] == receipt["passing_names"] == ["gate"]
    assert receipt["evidence_complete"] is True


def test_changed_incumbent_during_collection_invalidates_cli_receipt(tmp_path, monkeypatch):
    incumbent = tmp_path / "presence.py"
    incumbent.write_text("# Original incumbent\n")
    original_digest = hashlib.sha256(incumbent.read_bytes()).hexdigest()
    transport = fixture_transport()

    def changed_source(endpoint):
        incumbent.write_text("# Changed incumbent\n")
        return transport(endpoint)

    monkeypatch.setattr(reporter, "load_presence_reporter", lambda _: changed_source)

    code, receipt = invoke_main(monkeypatch, incumbent, tmp_path / "receipt.json")

    assert code == 2 and receipt["verdict"] == "UNKNOWN"
    assert "incumbent reporter changed" in receipt["unknown"][0]
    assert receipt["presence_reporter"]["sha256"] == original_digest
    assert receipt["request_evidence"]
    assert receipt["evidence_complete"] is False
    assert receipt["merge_authorization"] is False
