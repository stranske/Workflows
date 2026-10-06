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
        "head_sha": HEAD,
        "started_at": started,
        "status": "completed",
        "app": {"id": 15368, "slug": "github-actions"},
    }


def verdict(
    expected=None, checks=None, suites=None, runs=None, unknown=None, required=None, statuses=None
):
    run_list = runs if runs is not None else []
    applicable = (
        {item.get("check_suite_id") for item in run_list if item.get("check_suite_id") is not None}
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
                    "latest_check_runs_count": 0,
                }
            ],
            runs=[{"id": 1, "workflow_id": workflow_id, "check_suite_id": 90, "jobs": []}],
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
                    "latest_check_runs_count": 0,
                }
            ],
            runs=[{"id": 1, "workflow_id": 42, "check_suite_id": 91, "jobs": [check()]}],
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
    transport = fixture_transport()

    def duplicate_sources(endpoint):
        if "/contents/.github/workflows?" in endpoint:
            return [
                [
                    {"path": ".github/workflows/gate.yml", "sha": "d" * 40},
                    {"path": ".github/workflows/other.yml", "sha": "e" * 40},
                ]
            ]
        if "/contents/.github/workflows/other.yml?" in endpoint:
            return transport(endpoint.replace("other.yml", "gate.yml"))
        return transport(endpoint)

    result = reporter.collect(
        reporter.Evidence(duplicate_sources), "o/r", 1, HEAD, "pull_request", "opened"
    )
    assert result["verdict"] == "UNKNOWN"
    assert any("duplicate expected check identity" in reason for reason in result["unknown"])


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


@pytest.mark.parametrize("key", ["check_runs", "check_suites", "workflow_runs", "jobs"])
def test_changing_page_totals_cannot_establish_complete_inventory(key):
    evidence = reporter.Evidence(
        lambda _: [
            {"total_count": 3, key: [{"id": 1}]},
            {"total_count": 2, key: [{"id": 2}]},
        ]
    )
    with pytest.raises(reporter.UnknownEvidence, match="total_count changed"):
        evidence.items("inventory", key)
    assert evidence.requests[0]["pages"] == 2


@pytest.mark.parametrize("key", ["check_runs", "check_suites", "workflow_runs", "jobs", None])
def test_duplicate_page_objects_cannot_hide_missing_inventory(key):
    # Two enumerated entries meet total_count=2 but represent only one object.
    values = [{"id": 1}]
    page = values if key is None else {"total_count": 2, key: values}
    evidence = reporter.Evidence(lambda _: [page, page])
    with pytest.raises(reporter.UnknownEvidence, match="repeated object id 1"):
        evidence.items("inventory", key)


@pytest.mark.parametrize("total", [-1, True, "1", 1.0, None])
def test_invalid_inventory_totals_remain_unknown(total):
    evidence = reporter.Evidence(lambda _: [{"total_count": total, "check_runs": [check()]}])
    with pytest.raises(reporter.UnknownEvidence, match="invalid total_count"):
        evidence.items("checks", "check_runs")


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


def suite_recovery_transport(mode="valid"):
    original = fixture_transport()

    def wrapped(endpoint):
        if "/check-suites?" in endpoint:
            return [
                {
                    "total_count": 1,
                    "check_suites": [
                        {
                            "id": 901,
                            "head_sha": HEAD,
                            "app": {"slug": "github-actions"},
                            "conclusion": "action_required" if mode == "startup" else "success",
                            "latest_check_runs_count": 0 if mode == "startup" else 1,
                        }
                    ],
                }
            ]
        if "check_suite_id=901" in endpoint:
            run = {
                "id": 101,
                "check_suite_id": 901,
                "head_sha": HEAD,
                "event": "pull_request",
                "workflow_id": 1,
                "run_number": 1,
                "path": ".github/workflows/gate.yml",
                "conclusion": "success",
            }
            if mode == "head":
                run["head_sha"] = BASE
            elif mode == "suite":
                run["check_suite_id"] = 902
            elif mode == "event":
                run["event"] = None
            elif mode == "other_event":
                run["event"] = "pull_request_target"
            elif mode == "startup":
                run["conclusion"] = "action_required"
            values = [] if mode == "missing" else [run]
            return [
                {"total_count": 2 if mode == "truncated" else len(values), "workflow_runs": values}
            ]
        if "/actions/runs/101/jobs?" in endpoint:
            jobs = (
                [] if mode == "startup" else [{"id": 201, "name": "gate", "conclusion": "success"}]
            )
            return [{"total_count": len(jobs), "jobs": jobs}]
        return original(endpoint)

    return wrapped


def test_merged_head_empty_search_recovers_exact_suite_runs():
    result = reporter.collect(
        reporter.Evidence(suite_recovery_transport()), "o/r", 1, HEAD, "pull_request", "opened"
    )
    assert result["verdict"] == "PASS"
    assert result["workflow_run_inventory"][0]["id"] == 101
    assert result["workflow_runs"][0]["jobs"][0]["id"] == 201
    assert result["workflow_run_inventory_recovery"][0]["included"] is True
    assert any("check_suite_id=901" in e["endpoint"] for e in result["request_evidence"])


@pytest.mark.parametrize("mode", ["head", "suite", "event", "missing", "truncated"])
def test_suite_inventory_mismatch_or_incomplete_evidence_is_unknown(mode):
    with pytest.raises(reporter.UnknownEvidence):
        reporter.collect(
            reporter.Evidence(suite_recovery_transport(mode)),
            "o/r",
            1,
            HEAD,
            "pull_request",
            "opened",
        )


def test_recovered_zero_job_startup_failure_cannot_hide_behind_green_checks():
    result = reporter.collect(
        reporter.Evidence(suite_recovery_transport("startup")),
        "o/r",
        1,
        HEAD,
        "pull_request",
        "opened",
    )
    assert result["verdict"] == "FAIL"
    assert result["startup_failures"]


def test_recovered_other_event_remains_outside_requested_context():
    result = reporter.collect(
        reporter.Evidence(suite_recovery_transport("other_event")),
        "o/r",
        1,
        HEAD,
        "pull_request",
        "opened",
    )
    assert result["workflow_run_inventory"] == []
    assert result["workflow_run_inventory_recovery"][0]["event"] == "pull_request_target"
    assert result["workflow_run_inventory_recovery"][0]["included"] is False


def test_partial_head_inventory_still_recovers_unrepresented_suite():
    first = {"id": 10, "head_sha": HEAD, "event": "pull_request", "check_suite_id": 900}
    second = {"id": 11, "head_sha": HEAD, "event": "pull_request", "check_suite_id": 901}

    def transport(endpoint):
        run = second if "check_suite_id=901" in endpoint else first
        return [{"total_count": 1, "workflow_runs": [run]}]

    suites = [
        {"id": ident, "head_sha": HEAD, "app": {"slug": "github-actions"}} for ident in (900, 901)
    ]
    evidence = reporter.Evidence(transport)
    runs, recovery = reporter.complete_workflow_runs(evidence, "o/r", HEAD, "pull_request", suites)
    assert {run["id"] for run in runs} == {10, 11}
    assert [item["suite_id"] for item in recovery] == [901]
    assert len(evidence.requests) == 2


@pytest.mark.parametrize("suite_head", [None, "wrong", ""])
@pytest.mark.parametrize("known_run", [False, True])
def test_missing_or_wrong_suite_head_is_unknown_even_with_a_matching_run(suite_head, known_run):
    run = {"id": 10, "head_sha": HEAD, "event": "pull_request", "check_suite_id": 900}
    suite = {"id": 900, "app": {"slug": "github-actions"}}
    if suite_head is not None:
        suite["head_sha"] = suite_head

    def transport(endpoint):
        rows = [run] if known_run or "check_suite_id=" in endpoint else []
        return [{"total_count": len(rows), "workflow_runs": rows}]

    with pytest.raises(reporter.UnknownEvidence, match="identity/head binding missing"):
        reporter.complete_workflow_runs(
            reporter.Evidence(transport), "o/r", HEAD, "pull_request", [suite]
        )


def protection_transport(error, rules=None):
    transport = fixture_transport()

    def wrapped(endpoint):
        if "/rules/branches/" in endpoint:
            return [rules or []]
        if endpoint.endswith("/branches/main"):
            return [{"protected": True}]
        if endpoint.endswith("/branches/main/protection"):
            raise SystemExit(error)
        return transport(endpoint)

    return wrapped


def test_ruleset_only_branch_records_absent_classic_protection():
    result = reporter.collect(
        reporter.Evidence(protection_transport("gh: Branch not protected (HTTP 404)")),
        "o/r",
        1,
        HEAD,
        "pull_request",
        "opened",
    )
    assert result["verdict"] == "PASS"
    assert any(item.get("classic_protection") == "absent" for item in result["request_evidence"])


def test_ruleset_required_check_survives_absent_classic_protection():
    rules = [
        {
            "type": "required_status_checks",
            "parameters": {
                "required_status_checks": [{"context": "missing", "integration_id": 42}]
            },
        }
    ]
    result = reporter.collect(
        reporter.Evidence(protection_transport("gh: Branch not protected (HTTP 404)", rules)),
        "o/r",
        1,
        HEAD,
        "pull_request",
        "opened",
    )
    assert result["verdict"] == "FAIL"
    assert result["missing_names"] == ["missing"]
    assert result["required_checks"][0]["app_id"] == 42


@pytest.mark.parametrize("error", ["gh: Not Found (HTTP 404)", "gh: Forbidden (HTTP 403)"])
def test_unavailable_classic_protection_remains_unknown(error):
    with pytest.raises(reporter.UnknownEvidence, match="HTTP"):
        reporter.collect(
            reporter.Evidence(protection_transport(error)),
            "o/r",
            1,
            HEAD,
            "pull_request",
            "opened",
        )


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


@pytest.mark.parametrize("finding", ["base_branch", "changed_files"])
def test_changed_pr_filter_context_invalidates_receipt(finding):
    transport = fixture_transport()
    snapshots = 0

    def changed_context(endpoint):
        nonlocal snapshots
        pages = transport(endpoint)
        if endpoint.endswith("/pulls/1"):
            snapshots += 1
            if snapshots > 1:
                if finding == "base_branch":
                    # Retargeting can preserve both SHAs but change branch rules/filters.
                    pages[0]["base"]["ref"] = "release"
                else:
                    pages[0]["changed_files"] = 2
        return pages

    result = reporter.collect(
        reporter.Evidence(changed_context), "o/r", 1, HEAD, "pull_request", "opened"
    )

    assert result["verdict"] == "UNKNOWN"
    assert any("changed during evidence collection" in reason for reason in result["unknown"])
    assert result["head"] == HEAD and result["base"] == BASE
    assert result["merge_authorization"] is False


@pytest.mark.parametrize("finding", ["filename", "previous_filename", "truncated"])
def test_changed_path_inventory_invalidates_event_absence(finding):
    transport = fixture_transport()
    file_reads = 0
    workflow = (
        "on:\n  pull_request:\n    paths: ['docs/**']\n"
        "jobs:\n  docs:\n    runs-on: ubuntu-latest\n    steps: []\n"
    )

    def changed_paths(endpoint):
        nonlocal file_reads
        if "/contents/.github/workflows?" in endpoint:
            return [
                [
                    {"path": ".github/workflows/gate.yml", "sha": "d" * 40},
                    {"path": ".github/workflows/docs.yml", "sha": "e" * 40},
                ]
            ]
        if "/contents/.github/workflows/docs.yml?" in endpoint:
            return [{"encoding": "base64", "content": base64.b64encode(workflow.encode()).decode()}]
        if "/files?" in endpoint:
            file_reads += 1
            if file_reads > 1:
                if finding == "truncated":
                    return [[]]
                item = {"filename": "src/a.py"}
                item[finding] = "docs/guide.md"
                return [[item]]
        return transport(endpoint)

    result = reporter.collect(
        reporter.Evidence(changed_paths), "o/r", 1, HEAD, "pull_request", "opened"
    )

    assert result["verdict"] == "UNKNOWN"
    assert any("changed-path" in reason for reason in result["unknown"])
    assert result["changed_paths"] == ["src/a.py"]
    assert result["legitimate_absences"][0]["path"] == ".github/workflows/docs.yml"
    assert result["merge_authorization"] is False


def test_stable_paginated_paths_ignore_page_order_and_diff_statistics():
    transport = fixture_transport()
    file_reads = 0

    def stable_paths(endpoint):
        nonlocal file_reads
        if endpoint.endswith("/pulls/1"):
            pages = transport(endpoint)
            pages[0]["changed_files"] = 2
            return pages
        if "/files?" in endpoint:
            file_reads += 1
            pages = [
                [{"filename": "src/a.py", "previous_filename": "src/old.py", "additions": 1}],
                [{"filename": "src/b.py"}],
            ]
            if file_reads > 1:
                pages[0][0]["additions"] = 2
                pages.reverse()
            return pages
        return transport(endpoint)

    evidence = reporter.Evidence(stable_paths)
    result = reporter.collect(evidence, "o/r", 1, HEAD, "pull_request", "opened")

    assert result["verdict"] == "PASS"
    assert result["changed_paths"] == ["src/a.py", "src/b.py", "src/old.py"]
    assert result["closing_context"] == {
        "head": HEAD,
        "base": BASE,
        "base_branch": "main",
        "changed_file_count": 2,
        "enumerated_file_count": 2,
        "changed_paths": result["changed_paths"],
    }
    assert [
        request["pages"] for request in evidence.requests if "/files?" in request["endpoint"]
    ] == [
        2,
        2,
    ]


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


def invoke_main(monkeypatch, incumbent, output, action="opened"):
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
            action,
            "--presence-reporter",
            str(incumbent),
            "--output",
            str(output),
        ],
    )
    code = reporter.main()
    return code, json.loads(output.read_text())


def incident_transport(scenario, reverse_pages=False):
    """Full discovery evidence with incident data beyond the first API page."""
    fallback = fixture_transport()
    workflows = {
        "gate": "on: pull_request\njobs:\n  gate:\n    runs-on: ubuntu-latest\n    steps: []\n",
        "auto-pilot": (
            "on:\n  pull_request:\n    types: [labeled, closed]\n"
            "jobs:\n  auto-pilot:\n    runs-on: ubuntu-latest\n    steps: []\n"
        ),
    }
    checks = [check(), check("advisory", ident=2)]
    suites = [
        {
            "id": 90,
            "head_sha": HEAD,
            "app": {"slug": "github-actions"},
            "conclusion": "success",
            "latest_check_runs_count": 1,
        },
        {"id": 91, "head_sha": HEAD, "app": {"slug": "other-app"}},
    ]
    gate_run = {
        "id": 101,
        "workflow_id": 42,
        "check_suite_id": 90,
        "head_sha": HEAD,
        "event": "pull_request",
        "path": ".github/workflows/gate.yml",
        "run_attempt": 2 if scenario == "cancelled_retry" else 1,
        "conclusion": "success",
    }
    if scenario == "cancelled_retry":
        checks = [
            check(conclusion="cancelled"),
            check(ident=2, started="2026-10-01T02:00:00Z"),
        ]
    startup_run = {**gate_run, "id": 102, "workflow_id": 43, "check_suite_id": 91}
    if scenario == "startup_failure":
        workflows["bootstrap"] = workflows["gate"].replace("  gate:", "  bootstrap:")
        startup_run.update(path=".github/workflows/bootstrap.yml", conclusion="startup_failure")
        suites[1].update(
            app={"slug": "github-actions"},
            conclusion="startup_failure",
            latest_check_runs_count=0,
        )

    def inventory(key, items):
        pages = [{"total_count": len(items), key: [item]} for item in items]
        return list(reversed(pages)) if reverse_pages else pages

    def transport(endpoint):
        if "/check-runs?" in endpoint:
            return inventory("check_runs", checks)
        if "/check-suites?" in endpoint:
            return inventory("check_suites", suites)
        if "/contents/.github/workflows?" in endpoint:
            return [
                [{"path": f".github/workflows/{name}.yml", "sha": "d" * 40} for name in workflows]
            ]
        for name, document in workflows.items():
            if f"/contents/.github/workflows/{name}.yml?" in endpoint:
                return [
                    {"encoding": "base64", "content": base64.b64encode(document.encode()).decode()}
                ]
        if "/actions/runs?check_suite_id=91&" in endpoint:
            return [{"total_count": 1, "workflow_runs": [startup_run]}]
        if "/actions/runs?head_sha=" in endpoint:
            return [{"total_count": 1, "workflow_runs": [gate_run]}]
        if "/actions/runs/101/jobs?" in endpoint:
            return [
                {"total_count": 1, "jobs": [{"id": 201, "name": "gate", "conclusion": "success"}]}
            ]
        if "/actions/runs/102/jobs?" in endpoint:
            return [{"total_count": 0, "jobs": []}]
        if "/rules/branches/" in endpoint:
            contexts = ["gate"]
            if scenario == "missing_required":
                contexts.append("required-reporter")
            return [
                [
                    {
                        "type": "required_status_checks",
                        "parameters": {
                            "required_status_checks": [{"context": name} for name in contexts]
                        },
                    }
                ]
            ]
        return fallback(endpoint)

    return transport


@pytest.mark.parametrize("reverse_pages", [False, True])
@pytest.mark.parametrize("action", ["synchronize", "reopened"])
@pytest.mark.parametrize(
    "scenario,expected_verdict,exit_code,missing",
    [
        ("missing_required", "FAIL", 1, ["required-reporter"]),
        ("event_only_absence", "PASS", 0, []),
        ("cancelled_retry", "PASS", 0, []),
        ("startup_failure", "FAIL", 1, ["bootstrap"]),
    ],
)
def test_incident_cli_receipt(
    tmp_path, monkeypatch, scenario, expected_verdict, exit_code, missing, action, reverse_pages
):
    incumbent = tmp_path / "presence.py"
    incumbent.write_text("# Tracked incumbent\n")
    monkeypatch.setattr(
        reporter, "load_presence_reporter", lambda _: incident_transport(scenario, reverse_pages)
    )
    code, receipt = invoke_main(monkeypatch, incumbent, tmp_path / "evidence/receipt.json", action)

    assert (code, receipt["verdict"]) == (exit_code, expected_verdict)
    assert receipt["evidence_complete"] is True and receipt["unknown"] == []
    assert receipt["head"] == HEAD and receipt["base"] == BASE
    assert receipt["repository"] == "o/r" and receipt["pr"] == 1
    assert receipt["event"] == "pull_request" and receipt["action"] == action
    assert receipt["changed_paths"] == ["src/a.py"]
    assert receipt["closing_context"] == {
        "head": HEAD,
        "base": BASE,
        "base_branch": "main",
        "changed_file_count": 1,
        "enumerated_file_count": 1,
        "changed_paths": ["src/a.py"],
    }
    assert receipt["missing_names"] == missing
    assert receipt["expected_names"] == sorted(["gate", *missing])
    reported = ["gate"] if scenario == "cancelled_retry" else ["advisory", "gate"]
    assert receipt["reported_names"] == receipt["passing_names"] == reported
    assert receipt["states"]["gate"]["state"] == "success"
    assert {item["id"] for item in receipt["check_runs"]} == {1, 2}
    assert {item["id"] for item in receipt["check_suites"]} == {90, 91}
    for endpoint_kind in ["check-runs", "check-suites"]:
        requests = [r for r in receipt["request_evidence"] if f"/{endpoint_kind}?" in r["endpoint"]]
        assert len(requests) == 1 and requests[0]["pages"] == 2
        assert HEAD in requests[0]["endpoint"]
    (absence,) = receipt["legitimate_absences"]
    assert absence["repository"] == "o/r" and absence["ref"] == BASE
    assert absence["blob_sha"] == "d" * 40
    assert absence["path"] == ".github/workflows/auto-pilot.yml"
    assert absence["triggers"] == {"pull_request": {"types": ["labeled", "closed"]}}
    assert absence["document"]["jobs"]["auto-pilot"]
    assert absence["reason"] == f"action '{action}' not in ['labeled', 'closed']"
    if scenario == "cancelled_retry":
        assert receipt["states"]["gate"]["order"] == ["2026-10-01T02:00:00Z", 2]
        assert receipt["workflow_runs"][0]["run_attempt"] == 2
    if scenario == "startup_failure":
        assert receipt["startup_failures"] == [
            {"kind": "suite", "id": 91, "conclusion": "startup_failure"},
            {"kind": "run", "id": 102, "conclusion": "startup_failure"},
        ]
        assert receipt["workflow_run_inventory_recovery"][0]["included"] is True
        assert next(run for run in receipt["workflow_runs"] if run["id"] == 102)["jobs"] == []
    else:
        assert receipt["startup_failures"] == []
    assert receipt["merge_authorization"] is False


def test_event_only_absence_cannot_be_reused_for_applicable_action(tmp_path, monkeypatch):
    incumbent = tmp_path / "presence.py"
    incumbent.write_text("# Tracked incumbent\n")
    monkeypatch.setattr(
        reporter, "load_presence_reporter", lambda _: incident_transport("event_only_absence")
    )
    code, receipt = invoke_main(monkeypatch, incumbent, tmp_path / "receipt.json", action="labeled")
    assert code == 1 and receipt["verdict"] == "FAIL"
    assert receipt["expected_names"] == ["auto-pilot", "gate"]
    assert receipt["missing_names"] == ["auto-pilot"]
    assert receipt["legitimate_absences"][0]["path"] == ".github/workflows/gate.yml"
    assert receipt["merge_authorization"] is False


@pytest.mark.parametrize("changed", ["head", "paths"])
def test_incident_cli_rejects_changed_closing_context(tmp_path, monkeypatch, changed):
    incumbent = tmp_path / "presence.py"
    incumbent.write_text("# Tracked incumbent\n")
    transport = incident_transport("event_only_absence")
    reads = {}

    def changed_context(endpoint):
        pages = transport(endpoint)
        reads[endpoint] = reads.get(endpoint, 0) + 1
        if reads[endpoint] > 1:
            if changed == "head" and endpoint.endswith("/pulls/1"):
                pages[0]["head"]["sha"] = "c" * 40
            if changed == "paths" and "/pulls/1/files?" in endpoint:
                pages[0][0]["filename"] = "docs/guide.md"
        return pages

    monkeypatch.setattr(reporter, "load_presence_reporter", lambda _: changed_context)
    code, receipt = invoke_main(monkeypatch, incumbent, tmp_path / "receipt.json")
    assert code == 2 and receipt["verdict"] == "UNKNOWN"
    assert receipt["evidence_complete"] is False
    assert any("changed during evidence collection" in reason for reason in receipt["unknown"])
    assert receipt["head"] == HEAD and receipt["changed_paths"] == ["src/a.py"]
    if changed == "head":
        assert receipt["closing_context"]["head"] == "c" * 40
    else:
        assert receipt["closing_context"]["changed_paths"] == ["docs/guide.md"]
    assert receipt["merge_authorization"] is False


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


@pytest.mark.parametrize("key", ["check_runs", "check_suites"])
@pytest.mark.parametrize("app", ["github-actions", "other-app"])
@pytest.mark.parametrize("inventory_head", [None, BASE, HEAD[:8]])
def test_every_inventory_page_requires_full_head_binding(
    tmp_path, monkeypatch, key, app, inventory_head
):
    incumbent = tmp_path / "presence.py"
    incumbent.write_text("# Tracked incumbent\n")
    transport = fixture_transport()
    endpoint_kind = "check-runs" if key == "check_runs" else "check-suites"

    def mismatched_pages(endpoint):
        if f"/{endpoint_kind}?" in endpoint:
            first = check()
            second = check("advisory", ident=2)
            if key == "check_suites":
                first["app"] = {"slug": "other-app"}
            second["app"] = {"slug": app}
            if inventory_head is None:
                second.pop("head_sha")
            else:
                second["head_sha"] = inventory_head
            return [
                {"total_count": 2, key: [first]},
                {"total_count": 2, key: [second]},
            ]
        return transport(endpoint)

    monkeypatch.setattr(reporter, "load_presence_reporter", lambda _: mismatched_pages)
    code, receipt = invoke_main(monkeypatch, incumbent, tmp_path / "receipt.json")

    assert code == 2 and receipt["verdict"] == "UNKNOWN"
    assert "head binding" in receipt["unknown"][0]
    assert receipt["head"] == HEAD
    assert receipt["event"] == "pull_request" and receipt["action"] == "opened"
    assert receipt["evidence_complete"] is False
    assert receipt["merge_authorization"] is False
    assert any(
        endpoint_kind in request["endpoint"] and request["pages"] == 2
        for request in receipt["request_evidence"]
    )


@pytest.mark.parametrize("key", ["check_runs", "check_suites"])
@pytest.mark.parametrize("finding", ["changing_total", "duplicate_id"])
def test_unstable_inventory_emits_unknown_cli_receipt(tmp_path, monkeypatch, key, finding):
    incumbent = tmp_path / "presence.py"
    incumbent.write_text("# Tracked incumbent\n")
    transport = fixture_transport()
    endpoint_kind = "check-runs" if key == "check_runs" else "check-suites"

    def unstable_pages(endpoint):
        if f"/{endpoint_kind}?" in endpoint:
            second_id = 1 if finding == "duplicate_id" else 2
            values = (
                [check(), check("other", ident=second_id)]
                if key == "check_runs"
                else [{"id": ident, "conclusion": "success"} for ident in (1, second_id)]
            )
            return [
                {"total_count": 3 if finding == "changing_total" else 2, key: [values[0]]},
                {"total_count": 2, key: [values[1]]},
            ]
        return transport(endpoint)

    monkeypatch.setattr(reporter, "load_presence_reporter", lambda _: unstable_pages)
    code, receipt = invoke_main(monkeypatch, incumbent, tmp_path / "receipt.json")

    assert code == 2 and receipt["verdict"] == "UNKNOWN"
    assert receipt["head"] == HEAD
    assert receipt["event"] == "pull_request" and receipt["action"] == "opened"
    assert receipt["evidence_complete"] is False
    assert receipt["merge_authorization"] is False
    assert endpoint_kind in receipt["unknown"][0]
    assert receipt["request_evidence"][-1]["pages"] == 2
    assert endpoint_kind in receipt["request_evidence"][-1]["endpoint"]


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


def reusable_fixture(uses="o/r/.github/workflows/child.yml@main", condition=True):
    job = {"name": "call", "uses": uses}
    if condition:
        job["if"] = "needs.detect.outputs.run == 'true'"
    root = {"jobs": {"child": job}}
    child = {"on": {"workflow_call": {}}, "jobs": {"test": {"name": "test"}}}
    evidence = reporter.Evidence(lambda _: [])
    evidence.workflow = lambda repo, path, ref: child
    run = {
        "referenced_workflows": [{"path": uses, "sha": BASE}],
        "jobs": [{"name": "call / test", "conclusion": "success"}],
    }
    return root, evidence, run


def test_conditional_reusable_uses_exact_execution_sha():
    root, evidence, run = reusable_fixture()
    requests = []
    child = evidence.workflow("o/r", "child", BASE)
    evidence.workflow = lambda repo, path, ref: requests.append((repo, path, ref)) or child
    assert reporter.expected_jobs(evidence, "o/r", "gate.yml", HEAD, root, run=run) == {
        "call / test"
    }
    assert requests == [("o/r", ".github/workflows/child.yml", BASE)]


def test_conditional_reusable_explicit_skipped_caller_is_bound():
    root, evidence, run = reusable_fixture()
    run["jobs"] = [{"name": "call", "conclusion": "skipped", "check_run_url": "url/1"}]
    assert reporter.expected_jobs(evidence, "o/r", "gate.yml", HEAD, root, run=run) == {"call"}
    assert run["reusable_absences"][0]["check_run_url"] == "url/1"


@pytest.mark.parametrize("field", ["referenced_workflows", "jobs"])
def test_conditional_reusable_missing_binding_is_unknown(field):
    root, evidence, run = reusable_fixture()
    run[field] = []
    with pytest.raises(reporter.UnknownEvidence):
        reporter.expected_jobs(evidence, "o/r", "gate.yml", HEAD, root, run=run)


def test_reusable_pinned_sha_mismatch_is_unknown():
    root, evidence, run = reusable_fixture("o/r/.github/workflows/child.yml@" + HEAD)
    with pytest.raises(reporter.UnknownEvidence, match="differs"):
        reporter.expected_jobs(evidence, "o/r", "gate.yml", HEAD, root, run=run)


def test_reusable_wrong_ref_cannot_bind_floating_caller():
    root, evidence, run = reusable_fixture()
    run["referenced_workflows"][0]["path"] = "o/r/.github/workflows/child.yml@other"
    with pytest.raises(reporter.UnknownEvidence, match="missing"):
        reporter.expected_jobs(evidence, "o/r", "gate.yml", HEAD, root, run=run)


def test_literal_reusable_matrix_input_expands_expected_names():
    job = {
        "name": "test ${{ matrix.version }}",
        "strategy": {"matrix": {"version": "${{ fromJSON(inputs.versions) }}"}},
    }
    bound = reporter.bind_job_inputs(job, {"versions": '["3.12", "3.13"]'})
    assert reporter.job_names("test", bound) == ["test 3.12", "test 3.13"]


def test_dynamic_reusable_matrix_input_remains_unknown():
    job = {"strategy": {"matrix": {"version": "${{ fromJSON(inputs.versions) }}"}}}
    with pytest.raises(reporter.UnknownEvidence, match="nonliteral"):
        reporter.bind_job_inputs(job, {"versions": "${{ needs.detect.outputs.versions }}"})


def duplicate_run_transport(failed=False, missing=False):
    original = fixture_transport()

    def wrapped(endpoint):
        if "/contents/.github/workflows?" in endpoint:
            return [
                [
                    {"path": ".github/workflows/gate.yml", "sha": "d" * 40},
                    {"path": ".github/workflows/other.yml", "sha": "e" * 40},
                ]
            ]
        if "/contents/.github/workflows/other.yml?" in endpoint:
            return original(endpoint.replace("other.yml", "gate.yml"))
        if "/check-runs?" in endpoint:
            values = []
            for number in [1, 2]:
                if missing and number == 1:
                    continue
                item = check()
                item.update(id=number, url=f"check/{number}", head_sha=HEAD)
                if failed and number == 1:
                    item["conclusion"] = "failure"
                values.append(item)
            return [{"total_count": len(values), "check_runs": values}]
        if "/actions/runs?" in endpoint:
            return [
                {
                    "total_count": 2,
                    "workflow_runs": [
                        {
                            "id": 101,
                            "head_sha": HEAD,
                            "workflow_id": 1,
                            "event": "pull_request",
                            "path": ".github/workflows/gate.yml",
                            "run_number": 1,
                        },
                        {
                            "id": 102,
                            "head_sha": HEAD,
                            "workflow_id": 2,
                            "event": "pull_request",
                            "path": ".github/workflows/other.yml",
                            "run_number": 1,
                        },
                    ],
                }
            ]
        if "/actions/runs/101/jobs?" in endpoint or "/actions/runs/102/jobs?" in endpoint:
            number = 1 if "/101/" in endpoint else 2
            return [
                {
                    "total_count": 1,
                    "jobs": [
                        {
                            "name": "gate",
                            "id": number,
                            "conclusion": "success",
                            "check_run_url": f"check/{number}",
                        }
                    ],
                }
            ]
        return original(endpoint)

    return wrapped


def test_duplicate_names_require_independent_source_run_success():
    result = reporter.collect(
        reporter.Evidence(duplicate_run_transport()), "o/r", 1, HEAD, "pull_request", "opened"
    )
    assert result["verdict"] == "PASS"
    claims = result["duplicate_identity_evidence"][0]["independent_claims"]
    assert {claim["check_run_url"] for claim in claims} == {"check/1", "check/2"}
    assert len({claim["source"] for claim in claims}) == 2


@pytest.mark.parametrize("failure", [{"failed": True}, {"missing": True}])
def test_one_duplicate_success_cannot_mask_other_source_debt(failure):
    result = reporter.collect(
        reporter.Evidence(duplicate_run_transport(**failure)),
        "o/r",
        1,
        HEAD,
        "pull_request",
        "opened",
    )
    assert result["verdict"] != "PASS"
    assert any("independent success unproven" in reason for reason in result["unknown"])


def test_duplicate_job_names_inside_one_workflow_are_unknown():
    with pytest.raises(reporter.UnknownEvidence, match="duplicate expected job name"):
        reporter.expected_jobs(
            reporter.Evidence(lambda _: []),
            "o/r",
            "gate.yml",
            BASE,
            {"jobs": {"one": {"name": "gate"}, "two": {"name": "gate"}}},
        )


def test_duplicate_reusable_child_prefixes_are_unknown():
    root, evidence, run = reusable_fixture(condition=False)
    root["jobs"]["second"] = dict(root["jobs"]["child"])
    with pytest.raises(reporter.UnknownEvidence, match="duplicate expected child names"):
        reporter.expected_jobs(evidence, "o/r", "gate.yml", HEAD, root, run=run)


def python_producer_fixture():
    import copy

    path = ".github/workflows/reusable-10-ci-python.yml"
    workflow = reporter.yaml.load(
        (Path(__file__).parents[1] / path).read_text(), Loader=reporter.WorkflowLoader
    )
    helper = (Path(__file__).parents[1] / "scripts/reusable_ci_scope.py").read_bytes()
    arguments = {
        "workflow_name": "Gate",
        "python_versions": '["3.12","3.13"]',
        "python_version": "3.12",
        "changed_files": ["src/example.py"],
        "force_full": False,
    }
    receipt = {
        "schema": "python-matrix-producer/v1",
        "repository": "o/r",
        "run_id": 42,
        "run_attempt": 2,
        "head_sha": HEAD,
        "helper_sha": BASE,
        "helper_sha256": hashlib.sha256(helper).hexdigest(),
        "inputs": arguments,
        "matrix": {"include": [{"python-version": "3.12"}, {"python-version": "3.13"}]},
    }
    run = {
        "id": 42,
        "run_attempt": 2,
        "head_sha": HEAD,
        "name": "Gate",
        "repository": {"full_name": "o/r"},
        "jobs": [
            {
                "name": "ci / select reusable CI scope",
                "id": 99,
                "run_id": 42,
                "run_attempt": 2,
                "steps": [{"name": "Select Python version matrix", "conclusion": "success"}],
            }
        ],
    }
    evidence = reporter.Evidence(lambda _: [])
    evidence.content = lambda *args: helper
    evidence.job_receipts = lambda *args: [receipt]
    inputs = {
        "python-versions": '["3.12","3.13"]',
        "python-version": "3.12",
        "changed-files-json": "${{ needs.changes.outputs.files }}",
        "force-full": False,
    }
    job = copy.deepcopy(workflow["jobs"]["tests"])
    return evidence, workflow, job, run, inputs, receipt


def bind_producer(fixture):
    evidence, workflow, job, run, inputs, _ = fixture
    return reporter.bind_python_matrix(
        evidence,
        "stranske/Workflows",
        ".github/workflows/reusable-10-ci-python.yml",
        workflow,
        job,
        "ci / ",
        run,
        inputs,
    )


def test_python_matrix_independent_expectations_detect_missing_child():
    fixture = python_producer_fixture()
    bound = bind_producer(fixture)
    names = reporter.job_names("tests", bound)
    assert names == ["python 3.12", "python 3.13"]
    result = verdict(expected=set(names), checks=[check("python 3.12")])
    assert result["verdict"] == "FAIL"
    assert result["missing_names"] == ["python 3.13"]
    assert fixture[3]["matrix_evidence"][0]["helper_sha"] == BASE


@pytest.mark.parametrize(
    "finding",
    [
        "head",
        "run",
        "attempt",
        "helper_revision",
        "helper_digest",
        "missing_receipt",
        "duplicate_receipt",
        "producer_source",
        "producer_step",
        "input",
        "matrix",
        "workflow",
    ],
)
def test_python_producer_missing_or_forged_evidence_stays_unknown(finding):
    fixture = python_producer_fixture()
    evidence, workflow, _, run, _, receipt = fixture
    if finding == "head":
        receipt["head_sha"] = BASE
    elif finding == "run":
        receipt["run_id"] = 43
    elif finding == "attempt":
        receipt["run_attempt"] = 1
    elif finding == "helper_revision":
        receipt["helper_sha"] = "main"
    elif finding == "helper_digest":
        receipt["helper_sha256"] = "0" * 64
    elif finding == "missing_receipt":
        evidence.job_receipts = lambda *args: []
    elif finding == "duplicate_receipt":
        evidence.job_receipts = lambda *args: [receipt, receipt]
    elif finding == "producer_source":
        workflow["jobs"]["select-scope"]["steps"][-1]["run"] = "echo fake"
    elif finding == "producer_step":
        run["jobs"][0]["steps"][0]["conclusion"] = "skipped"
    elif finding == "input":
        receipt["inputs"]["python_versions"] = '["3.12"]'
    elif finding == "matrix":
        receipt["matrix"]["include"].pop()
    elif finding == "workflow":
        receipt["inputs"]["workflow_name"] = "other"
    with pytest.raises(reporter.UnknownEvidence):
        bind_producer(fixture)


def test_executed_helper_source_must_equal_local_resolver():
    fixture = python_producer_fixture()
    fixture[0].content = lambda *args: b"different helper"
    with pytest.raises(reporter.UnknownEvidence, match="trusted pure resolver"):
        bind_producer(fixture)


def test_literal_include_only_matrix_and_transform_boundary():
    assert reporter.job_names(
        "test",
        {
            "name": "Python ${{ matrix.version }}",
            "strategy": {"matrix": {"include": [{"version": "3.12"}, {"version": "3.13"}]}},
        },
    ) == ["Python 3.12", "Python 3.13"]
    for matrix in (
        {"include": [{"version": "3.12"}], "version": ["3.13"]},
        {"version": ["3.12"], "exclude": []},
        {"include": []},
    ):
        with pytest.raises(reporter.UnknownEvidence):
            reporter.job_names("test", {"strategy": {"matrix": matrix}})


def test_real_workflow_producer_emits_recomputable_receipt(tmp_path, monkeypatch, capsys):
    import os
    import subprocess

    evidence, workflow, _, run, inputs, _ = python_producer_fixture()
    step = workflow["jobs"]["select-scope"]["steps"][-1]
    helper = tmp_path / ".workflows-lib/scripts/reusable_ci_scope.py"
    helper.parent.mkdir(parents=True)
    helper.write_bytes((Path(__file__).parents[1] / "scripts/reusable_ci_scope.py").read_bytes())
    monkeypatch.chdir(tmp_path)
    for name, value in {
        "WORKFLOW_NAME": "Gate",
        "PYTHON_VERSIONS": '["3.12","3.13"]',
        "PYTHON_VERSION": "3.12",
        "CHANGED_FILES_JSON": '["src/example.py"]',
        "FORCE_FULL": "false",
        "GITHUB_OUTPUT": str(tmp_path / "outputs"),
        "GITHUB_REPOSITORY": "o/r",
        "GITHUB_RUN_ID": "42",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_WORKFLOW_SHA": HEAD,
        "PR_HEAD_SHA": HEAD,
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: BASE + "\n")
    source = step["run"].split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    exec(compile(source, "<production-matrix-step>", "exec"), {})
    output = capsys.readouterr().out
    receipt = json.loads(
        next(
            line.split("=", 1)[1]
            for line in output.splitlines()
            if line.startswith("PYTHON_MATRIX_RECEIPT=")
        )
    )
    evidence.job_receipts = lambda *args: [receipt]
    fixture = (evidence, workflow, workflow["jobs"]["tests"], run, inputs, receipt)
    assert reporter.job_names("tests", bind_producer(fixture)) == ["python 3.12", "python 3.13"]
    assert 'python_matrix={"include"' in Path(os.environ["GITHUB_OUTPUT"]).read_text()


def legacy_log_fixture():
    stamp = "2026-10-06T03:57:22.0000000Z "
    lines = [
        "[command]/usr/bin/git log -1 --format=%H",
        BASE,
        "##[group]Run python - <<'PY'",
        "  WORKFLOW_NAME: Gate",
        '  PYTHON_VERSIONS: ["3.12", "3.13"]',
        "  PYTHON_VERSION: 3.12",
        "  CHANGED_FILES_JSON: []",
        "  FORCE_FULL: false",
        "##[endgroup]",
    ]
    return "\n".join(stamp + line for line in lines)


def test_legacy_source_bound_inputs_recompute_missing_child_without_success_inference():
    run = python_producer_fixture()[3]
    receipt = reporter.legacy_python_receipt(legacy_log_fixture(), run)
    assert receipt["helper_sha"] == BASE
    assert receipt["inputs"]["changed_files"] == []
    selected = reporter.select_python_matrix(**receipt["inputs"])
    names = reporter.job_names(
        "test",
        {"name": "python ${{ matrix.python-version }}", "strategy": {"matrix": selected.matrix}},
    )
    result = verdict(expected=set(names), checks=[check("python 3.12")])
    assert result["verdict"] == "FAIL" and result["missing_names"] == ["python 3.13"]


@pytest.mark.parametrize("bad", ["missing", "masked", "duplicate", "checkout", "group", "bool"])
def test_legacy_transcript_incomplete_or_ambiguous_stays_unknown(bad):
    log = legacy_log_fixture()
    if bad == "missing":
        log = log.replace("  CHANGED_FILES_JSON: []", "  OTHER: []")
    elif bad == "masked":
        log = log.replace("  CHANGED_FILES_JSON: []", "  CHANGED_FILES_JSON: ***")
    elif bad == "duplicate":
        log += "\n" + log
    elif bad == "checkout":
        log = log.replace(BASE, "main")
    elif bad == "group":
        log = log.replace("##[endgroup]", "")
    elif bad == "bool":
        log = log.replace("FORCE_FULL: false", "FORCE_FULL: unknown")
    with pytest.raises(reporter.UnknownEvidence):
        reporter.legacy_python_receipt(log, python_producer_fixture()[3])


@pytest.mark.parametrize(
    "head_trigger,expected", [("workflow_call", "PASS"), ("pull_request", "UNKNOWN")]
)
def test_changed_callable_workflow_requires_absence_on_both_sources(head_trigger, expected):
    transport = fixture_transport()
    original = "on: workflow_call\njobs:\n  child:\n    steps: []\n"
    head_doc = original.replace("workflow_call", head_trigger)

    def wrapped(endpoint):
        if endpoint.endswith("/pulls/1"):
            obj = transport(endpoint)[0]
            obj["changed_files"] = 1
            return [obj]
        if "/pulls/1/files?" in endpoint:
            return [[{"filename": ".github/workflows/child.yml"}]]
        if "/contents/.github/workflows?" in endpoint:
            return [
                [
                    {"path": ".github/workflows/gate.yml", "sha": "d" * 40},
                    {"path": ".github/workflows/child.yml", "sha": "e" * 40},
                ]
            ]
        if "/contents/.github/workflows/child.yml?" in endpoint:
            text = head_doc if endpoint.endswith(HEAD) else original
            return [{"encoding": "base64", "content": base64.b64encode(text.encode()).decode()}]
        return transport(endpoint)

    result = reporter.collect(reporter.Evidence(wrapped), "o/r", 1, HEAD, "pull_request", "opened")
    assert result["verdict"] == expected
    if expected == "PASS":
        assert result["legitimate_absences"][0]["head_absence_ref"] == HEAD


def test_new_workflow_not_in_base_directory_is_unknown():
    transport = fixture_transport()

    def wrapped(endpoint):
        if "/pulls/1/files?" in endpoint:
            return [[{"filename": ".github/workflows/new.yml"}]]
        return transport(endpoint)

    result = reporter.collect(reporter.Evidence(wrapped), "o/r", 1, HEAD, "pull_request", "opened")
    assert result["verdict"] == "UNKNOWN"
    assert any("new workflow" in item for item in result["unknown"])


def scenario_fixture(path=".github/workflows/selftest-reusable-ci.yml"):
    import copy

    workflow_bytes = (Path(__file__).parents[1] / path).read_bytes()
    workflow = reporter.yaml.load(workflow_bytes, Loader=reporter.WorkflowLoader)
    helper = (Path(__file__).parents[1] / "scripts/reusable_ci_scope.py").read_bytes()
    full = reporter.scenario_source_matrix(workflow["jobs"]["select-scenarios"])
    changed = [path]
    selected = reporter.select_scenarios(Path(path).stem, changed, full)
    receipt = {
        "schema": "scenario-matrix-producer/v1",
        "repository": "stranske/Workflows",
        "run_id": 42,
        "run_attempt": 2,
        "head_sha": HEAD,
        "base_sha": BASE,
        "helper_sha": "c" * 40,
        "helper_sha256": hashlib.sha256(helper).hexdigest(),
        "workflow_path": path,
        "workflow_sha256": hashlib.sha256(workflow_bytes).hexdigest(),
        "inputs": {
            "workflow_name": Path(path).stem,
            "changed_files": changed,
            "full_matrix": full,
            "force_full": False,
        },
        "matrix": selected.matrix,
    }
    run = {
        "id": 42,
        "run_attempt": 2,
        "head_sha": HEAD,
        "event": "pull_request",
        "repository": {"full_name": "stranske/Workflows"},
        "jobs": [
            {
                "id": 99,
                "run_id": 42,
                "run_attempt": 2,
                "name": workflow["jobs"]["select-scenarios"]["name"],
                "steps": [{"name": "Select scenarios", "conclusion": "success"}],
            }
        ],
    }
    evidence = reporter.Evidence(lambda _: [])
    evidence.content = lambda repo, file, ref: helper if file.endswith(".py") else workflow_bytes
    evidence.one = lambda endpoint: {
        "merge_base_commit": {"sha": BASE},
        "files": [{"filename": path}],
    }
    evidence.job_receipts = lambda *args: [receipt]
    return evidence, path, workflow, copy.deepcopy(workflow["jobs"]["scenarios"]), run, receipt


def bind_scenario_fixture(fixture):
    evidence, path, workflow, job, run, _ = fixture
    return reporter.bind_scenario_matrix(evidence, "stranske/Workflows", path, workflow, job, run)


@pytest.mark.parametrize(
    "path,count",
    [
        (".github/workflows/selftest-reusable-ci.yml", 6),
        (".github/workflows/maint-62-integration-consumer.yml", 3),
    ],
)
def test_scenario_expectations_detect_missing_child_independently(path, count):
    fixture = scenario_fixture(path)
    bound = bind_scenario_fixture(fixture)
    names = reporter.job_names("scenarios", bound)
    assert len(names) == count
    result = verdict(expected=set(names), checks=[check(n) for n in names[:-1]])
    assert result["verdict"] == "FAIL" and result["missing_names"] == names[-1:]
    assert fixture[4]["matrix_evidence"][0]["receipt"]["helper_sha"] == "c" * 40


@pytest.mark.parametrize(
    "finding",
    [
        "head",
        "attempt",
        "run",
        "step",
        "helper",
        "workflow",
        "matrix",
        "paths",
        "base",
        "force_full",
        "full_matrix",
        "duplicate",
        "source",
        "truncated_compare",
    ],
)
def test_scenario_forgery_cannot_complete_topology(finding):
    fixture = scenario_fixture()
    evidence, path, workflow, job, run, receipt = fixture
    if finding == "head":
        receipt["head_sha"] = BASE
    elif finding == "attempt":
        receipt["run_attempt"] = 1
    elif finding == "run":
        run["jobs"][0]["run_id"] = 1
    elif finding == "step":
        run["jobs"][0]["steps"][0]["conclusion"] = "skipped"
    elif finding == "helper":
        receipt["helper_sha256"] = "0" * 64
    elif finding == "workflow":
        receipt["workflow_sha256"] = "0" * 64
    elif finding == "matrix":
        receipt["matrix"]["include"].pop()
    elif finding == "paths":
        receipt["inputs"]["changed_files"] = []
    elif finding == "base":
        receipt["base_sha"] = "main"
    elif finding == "force_full":
        receipt["inputs"]["force_full"] = True
    elif finding == "full_matrix":
        receipt["inputs"]["full_matrix"]["include"].pop()
    elif finding == "duplicate":
        evidence.job_receipts = lambda *args: [receipt, receipt]
    elif finding == "source":
        workflow["jobs"]["select-scenarios"]["steps"][-1]["run"] += "\n# altered\n"
    elif finding == "truncated_compare":
        evidence.one = lambda _: {
            "merge_base_commit": {"sha": BASE},
            "files": [{"filename": path}] * 300,
        }
    with pytest.raises(reporter.UnknownEvidence):
        bind_scenario_fixture(fixture)


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/selftest-reusable-ci.yml",
        ".github/workflows/maint-62-integration-consumer.yml",
        ".github/workflows/pr-00-gate.yml",
    ],
)
def test_only_observer_and_pin_changes_are_topology_equivalent(path):
    import copy

    base = {
        "on": {"pull_request": {"paths": ["scripts/**"]}},
        "permissions": {"contents": "read"},
        "jobs": {
            "ci": {
                "uses": "./.github/workflows/reusable-10-ci-python.yml",
                "with": {"python-versions": '["3.12"]'},
            }
        },
    }
    if path in reporter.SCENARIO_PATHS:
        base["jobs"]["select-scenarios"] = {
            "steps": [
                {
                    "name": "Select scenarios",
                    "env": {"FORCE_FULL": "false"},
                    "run": (
                        "from scripts.reusable_ci_scope import SelectionOptions, describe_selection, select_scenarios\n"
                        "print(describe_selection(selected, matrix))\n"
                    ),
                }
            ]
        }
    head = copy.deepcopy(base)
    head["jobs"]["ci"]["with"]["workflows_ref"] = "${{ github.sha }}"
    if path in reporter.SCENARIO_PATHS:
        step = head["jobs"]["select-scenarios"]["steps"][0]
        step["env"].update(
            {
                "PR_HEAD_SHA": "${{ github.event.pull_request.head.sha || github.sha }}",
                "PR_BASE_SHA": "${{ github.event.pull_request.base.sha || '' }}",
            }
        )
        step["run"] = (
            step["run"]
            .replace("select_scenarios\n", "select_scenarios, scenario_matrix_receipt\n")
            .replace(
                "print(describe_selection(selected, matrix))",
                'print("SCENARIO_MATRIX_RECEIPT=" + json.dumps(scenario_matrix_receipt("'
                + path
                + '", changed_files, matrix, selected), sort_keys=True))\n'
                + "print(describe_selection(selected, matrix))",
            )
        )
    assert reporter.root_topology_equivalent(base, head, path)
    for field, value in [
        ("jobs", {"new-unreported-job": {"runs-on": "ubuntu-latest", "steps": []}}),
        ("permissions", {"contents": "write"}),
        ("on", {"push": None}),
    ]:
        changed = copy.deepcopy(head)
        changed[field].update(value)
        assert not reporter.root_topology_equivalent(base, changed, path)


def test_boolean_matrix_names_use_actions_spelling():
    assert reporter.job_names(
        "lint",
        {"name": "lint ${{ matrix.strict }}", "strategy": {"matrix": {"strict": [True, False]}}},
    ) == ["lint true", "lint false"]
    assert reporter.job_names("lint", {"strategy": {"matrix": {"strict": [True, False]}}}) == [
        "lint (true)",
        "lint (false)",
    ]


def test_matrix_substitution_preserves_literal_backslashes():
    value = r"C:\new\tools"
    assert reporter.job_names(
        "lint", {"name": "lint ${{ matrix.path }}", "strategy": {"matrix": {"path": [value]}}}
    ) == ["lint " + value]


def test_boolean_input_names_use_actions_spelling():
    bound = reporter.bind_job_inputs({"name": "lint ${{ inputs.strict }}"}, {"strict": True})
    assert bound["name"] == "lint true"


def test_collect_binds_real_suite_id_to_current_run():
    transport = fixture_transport()

    def realistic_suite(endpoint):
        if "/check-suites?" in endpoint:
            return [
                {
                    "total_count": 1,
                    "check_suites": [
                        {
                            "id": 90,
                            "head_sha": HEAD,
                            "conclusion": "startup_failure",
                            "latest_check_runs_count": 0,
                        }
                    ],
                }
            ]
        if "/actions/runs?" in endpoint:
            return [
                {
                    "total_count": 1,
                    "workflow_runs": [
                        {
                            "id": 1,
                            "workflow_id": 42,
                            "check_suite_id": 90,
                            "head_sha": HEAD,
                            "event": "pull_request",
                            "path": ".github/workflows/gate.yml",
                            "conclusion": "success",
                        }
                    ],
                }
            ]
        if "/actions/runs/1/jobs?" in endpoint:
            return [{"total_count": 1, "jobs": [{"id": 2, "name": "gate"}]}]
        return transport(endpoint)

    result = reporter.collect(
        reporter.Evidence(realistic_suite), "o/r", 1, HEAD, "pull_request", "opened"
    )
    assert result["verdict"] == "FAIL"
    assert result["startup_failures"] == [
        {"kind": "suite", "id": 90, "conclusion": "startup_failure"}
    ]


def actions_status_packet():
    """Minimized authenticated shape of Inv-Man-Intake1006's actual Gate retry."""
    repo = "stranske/Inv-Man-Intake"
    status = {
        "id": 55746211600,
        "context": "Gate / gate",
        "state": "success",
        "created_at": "2026-10-06T22:28:41Z",
        "url": f"https://api.github.com/repos/{repo}/statuses/{HEAD}",
        "target_url": f"https://github.com/{repo}/actions/runs/37538210728",
        "creator": {"id": 41898282, "login": "github-actions[bot]", "type": "Bot"},
    }
    app = {
        "id": 15368,
        "slug": "github-actions",
        "owner": {"id": 9919, "login": "github", "type": "Organization"},
    }
    suite = {"id": 101687549688, "head_sha": HEAD, "app": app}
    run = {
        "id": 37538210728,
        "repository": {"full_name": repo},
        "head_sha": HEAD,
        "event": "pull_request",
        "path": ".github/workflows/pr-00-gate.yml",
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 2,
        "check_suite_id": suite["id"],
        "jobs": [
            {
                "id": 112533083718,
                "name": "gate-summary",
                "run_id": 37538210728,
                "run_attempt": 2,
                "head_sha": HEAD,
                "status": "completed",
                "conclusion": "success",
                "check_run_url": f"https://api.github.com/repos/{repo}/check-runs/112533083718",
                "steps": [
                    {
                        "name": "Report Gate commit status",
                        "status": "completed",
                        "conclusion": "success",
                        "started_at": "2026-10-06T22:28:41Z",
                        "completed_at": "2026-10-06T22:28:42Z",
                    }
                ],
            }
        ],
    }
    gate = check("gate-summary", ident=112533083718)
    gate["check_suite"] = {"id": suite["id"]}
    return {
        "repo": repo,
        "head": HEAD,
        "statuses": [status],
        "runs": [run],
        "suites": [suite],
        "checks": [gate],
        "platform_app": app,
        "platform_bot": dict(status["creator"]),
    }


def status_packet_verdict(packet):
    proof = reporter.gate_status_provenance(**packet)
    return reporter.adjudicate(
        {"Gate / gate"},
        packet["checks"],
        packet["statuses"],
        packet["suites"],
        packet["runs"],
        [],
        [{"context": "Gate / gate", "app_id": 15368}],
        status_provenance=proof,
    )


@pytest.mark.parametrize("summary_name", ["summary", "gate-summary"])
def test_real_gate_retry_resolves_only_the_missing_app_binding(summary_name):
    packet = actions_status_packet()
    packet["runs"][0]["jobs"][0]["name"] = summary_name
    assert (
        reporter.adjudicate(
            {"Gate / gate"},
            packet["checks"],
            packet["statuses"],
            packet["suites"],
            packet["runs"],
            [],
            [{"context": "Gate / gate", "app_id": 15368}],
        )["verdict"]
        == "UNKNOWN"
    )
    proof = reporter.gate_status_provenance(**packet)
    assert proof[55746211600]["run_attempt"] == 2
    assert proof[55746211600]["suite_id"] == 101687549688
    result = status_packet_verdict(packet)
    assert result["verdict"] == "PASS"
    assert result["missing_names"] == result["unknown"] == result["failing_checks"] == []


@pytest.mark.parametrize(
    "object_path,key,value",
    [
        (("statuses", 0, "creator"), "id", 123),
        (("statuses", 0, "creator"), "login", "someone[bot]"),
        (("statuses", 0, "creator"), "type", "User"),
        (("platform_app",), "id", 999),
        (("platform_app", "owner"), "id", 999),
        (("platform_bot",), "id", 999),
        (("statuses", 0), "url", "https://api.github.com/repos/other/repo/statuses/" + HEAD),
        (("statuses", 0), "created_at", "2026-10-06T22:28:43Z"),
        (("statuses", 0), "created_at", "not-a-time"),
        (("runs", 0), "head_sha", BASE),
        (("runs", 0, "repository"), "full_name", "other/repo"),
        (("runs", 0), "event", "workflow_dispatch"),
        (("runs", 0), "path", ".github/workflows/unrelated.yml"),
        (("runs", 0), "run_attempt", 3),
        (("statuses", 0), "id", True),
        (("runs", 0), "id", None),
        (("runs", 0), "check_suite_id", None),
        (("runs", 0), "run_attempt", True),
        (("runs", 0, "jobs", 0), "id", None),
        (("runs", 0), "conclusion", "failure"),
        (("suites", 0), "head_sha", BASE),
        (("suites", 0), "id", 123),
        (("suites", 0, "app"), "slug", "other"),
        (("checks", 0, "app"), "id", 123),
        (("checks", 0, "check_suite"), "id", 123),
        (("runs", 0, "jobs", 0), "name", "unrelated-summary"),
        (("runs", 0, "jobs", 0), "run_attempt", 1),
        (("runs", 0, "jobs", 0), "head_sha", BASE),
        (("runs", 0, "jobs", 0), "check_run_url", "https://example.com/check-runs/112533083718"),
        (("runs", 0, "jobs", 0, "steps", 0), "conclusion", "failure"),
        (("runs", 0, "jobs", 0, "steps", 0), "name", "Unrelated step"),
    ],
)
def test_gate_status_binding_rejects_spoofed_or_incomplete_correspondence(object_path, key, value):
    packet = actions_status_packet()
    # Remove shared fixture identity so each negative changes only its named evidence.
    packet = json.loads(json.dumps(packet))
    node = packet
    for part in object_path:
        node = node[part]
    node[key] = value
    assert reporter.gate_status_provenance(**packet) == {}
    assert status_packet_verdict(packet)["verdict"] == "UNKNOWN"


def test_newer_untrusted_status_never_falls_back_to_older_trusted_success():
    packet = actions_status_packet()
    newer = json.loads(json.dumps(packet["statuses"][0]))
    newer.update(id=55746211601, created_at="2026-10-06T22:28:42Z", app_id=15368)
    newer["creator"]["id"] = 123
    for statuses in [[newer, *packet["statuses"]], [*packet["statuses"], newer]]:
        packet["statuses"] = statuses
        assert reporter.gate_status_provenance(**packet) == {}
        assert status_packet_verdict(packet)["verdict"] == "UNKNOWN"


def test_verified_status_still_cannot_mask_a_failed_same_context_check():
    packet = actions_status_packet()
    packet["checks"].append(check("Gate / gate", conclusion="failure", ident=2))
    assert status_packet_verdict(packet)["verdict"] == "FAIL"


def test_url_only_and_missing_status_are_not_publishing_identity():
    packet = actions_status_packet()
    packet["statuses"][0]["creator"] = {}
    assert status_packet_verdict(packet)["verdict"] == "UNKNOWN"
    packet["statuses"] = []
    assert reporter.gate_status_provenance(**packet) == {}
    assert status_packet_verdict(packet)["verdict"] == "FAIL"


@pytest.mark.parametrize(
    "relative",
    [
        ".github/workflows/pr-00-gate.yml",
        "templates/consumer-repo/.github/workflows/pr-00-gate.yml",
    ],
)
def test_current_canonical_gate_summary_can_bind_status(relative):
    workflow = reporter.yaml.load(
        (Path(__file__).parents[1] / relative).read_text(), Loader=reporter.WorkflowLoader
    )
    packet = actions_status_packet()
    packet["runs"][0]["jobs"][0]["name"] = workflow["jobs"]["summary"]["name"]
    assert status_packet_verdict(packet)["verdict"] == "PASS"


@pytest.mark.parametrize("suffix", ["@refs/pull/1006/merge", "@main", "@" + "a" * 40])
def test_gate_status_accepts_nonempty_workflow_run_ref_suffix(suffix):
    packet = actions_status_packet()
    packet["runs"][0]["path"] += suffix
    assert reporter.gate_status_provenance(**packet)


@pytest.mark.parametrize(
    "path", [".github/workflows/pr-00-gate.yml@", ".github/workflows/decoy.yml@main"]
)
def test_gate_status_rejects_empty_ref_and_foreign_workflow(path):
    packet = actions_status_packet()
    packet["runs"][0]["path"] = path
    assert reporter.gate_status_provenance(**packet) == {}
