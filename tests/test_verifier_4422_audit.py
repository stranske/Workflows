"""Recovered #4036 campaign boundaries stay explicit, including unknowns."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

import verifier_4422_audit as audit

REPO_ROOT = Path(__file__).resolve().parents[1]

EXCLUDED_REPO = "stranske/collab-admin"


def test_timezone_and_check_date_keep_unspecified_clock_unknown() -> None:
    definition = audit.campaign_definition()
    assert definition["timezone"]["stated_timestamps"] == "UTC"
    assert definition["timezone"]["check_date_timezone"] == audit.UNKNOWN
    rules = definition["rules"]
    assert rules["check_date"] == "2026-10-24"
    assert rules["check_date_clock"] == audit.UNKNOWN
    assert rules["eligibility_window_start"] == audit.UNKNOWN
    assert rules["eligibility_window_end"] == audit.UNKNOWN
    assert rules["released_issue_definition"] == audit.UNKNOWN
    assert rules["closure_timestamp_source"] == audit.UNKNOWN
    assert rules["seven_day_window_start_rule"] == audit.UNKNOWN
    assert definition["facts"]["baseline_since_date"] == audit.UNKNOWN
    assert definition["facts"]["baseline_since_clock"] == "01:45Z"


def test_targets_match_the_issue_text_without_equating_populations() -> None:
    rules = audit.campaign_definition()["rules"]
    assert rules["truncation_concerns_target_count"] == 0
    assert rules["truncation_marker"] == "truncated"
    assert rules["truncation_verdict"] == "CONCERNS"
    assert rules["truncation_window"] == "within 7 days after merge"
    assert rules["closure_target_percent"] == 80
    assert rules["closure_within_hours"] == 2
    assert rules["closure_clock_start"] == "pull request merge"
    assert rules["demand_equals_released_issue_population"] == audit.UNKNOWN
    assert rules["baseline_equals_campaign_population"] == audit.UNKNOWN
    assert rules["owner_exclusion_in_issue_4036"] is False


def test_explicit_merge_timestamp_is_not_promoted_to_a_window() -> None:
    definition = audit.campaign_definition()
    assert definition["facts"]["pr_4037_merged_at"] == "2026-10-18T02:31:22Z"
    assert definition["facts"]["pr_4037_merge_commit"] == (
        "021ec67ef580c83a88402a1574e27ea34db14dde"
    )
    encoded_rules = json.dumps(definition["rules"])
    assert "2026-10-17T01:45:00Z" not in encoded_rules
    assert "2026-10-18T02:31:22Z" not in encoded_rules
    assert definition["rules"]["eligibility_window_start"] == audit.UNKNOWN


def test_owner_excluded_repository_is_rejected_before_a_command_runs() -> None:
    with pytest.raises(audit.OwnerExcludedRepository):
        audit.initial_evidence_argv(EXCLUDED_REPO)
    argv = audit.initial_evidence_argv()
    assert EXCLUDED_REPO not in argv
    assert argv[:4] == ["gh", "run", "view", audit.INITIAL_EVIDENCE_RUN_ID]
    assert "--repo" in argv
    assert "stranske/Workflows" in argv
    evidence = json.dumps(audit.campaign_definition()["linked_verifier_evidence"])
    assert EXCLUDED_REPO not in evidence


def test_initial_evidence_parses_one_successful_response() -> None:
    payload = {"databaseId": 39090617832, "conclusion": "success"}
    calls: list[float] = []

    def runner(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(timeout)
        return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")

    result = audit.run_initial_evidence(runner, clock=lambda: 0.0)
    assert result["outcome"] == payload
    assert result["attempts"] == 1
    assert result["stop_reason"] is None
    assert calls == [90.0]
    assert result["stop_rule"]["max_attempts"] == 2
    assert result["stop_rule"]["max_elapsed_seconds"] == 120.0


def test_initial_evidence_stops_at_the_attempt_cap() -> None:
    def runner(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 1, "", "unavailable")

    result = audit.run_initial_evidence(runner, clock=lambda: 0.0)
    assert result["outcome"] is None
    assert result["attempts"] == 2
    assert result["stop_reason"] == "attempt-cap"
    assert len(result["errors"]) == 2


def test_initial_evidence_stops_when_the_elapsed_budget_is_already_spent() -> None:
    times = iter([0.0, 121.0])

    def runner(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        raise AssertionError("runner must not be called after the elapsed cap")

    result = audit.run_initial_evidence(runner, clock=lambda: next(times))
    assert result["attempts"] == 0
    assert result["stop_reason"] == "elapsed-cap"
    assert result["outcome"] is None


def test_initial_evidence_does_not_start_a_second_attempt_after_the_budget() -> None:
    times = iter([0.0, 0.0, 121.0])
    calls = 0

    def runner(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(argv, 1, "", "unavailable")

    result = audit.run_initial_evidence(runner, clock=lambda: next(times))
    assert calls == 1
    assert result["attempts"] == 1
    assert result["stop_reason"] == "elapsed-cap"


def test_campaign_definition_command_prints_the_record_without_network() -> None:
    completed = subprocess.run(
        ["python3", "verifier_4422_audit.py", "campaign-definition"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout) == audit.campaign_definition()


def test_audit_markdown_records_the_definition_and_stop_rule() -> None:
    text = (REPO_ROOT / "verifier-4422-audit.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)\n```", text, re.S)
    assert json.loads(blocks[0]) == audit.campaign_definition()
    observed = json.loads(blocks[1])
    assert observed["attempts"] == 1
    assert observed["stop_reason"] is None
    assert observed["outcome"]["databaseId"] == 39090617832
    assert observed["outcome"]["headSha"] == (
        audit.campaign_definition()["facts"]["pr_4037_merge_commit"]
    )
    assert "2 attempts and 120 seconds" in text
    assert "Eligibility window start | unknown" in text
    assert "stranske/collab-admin" in text
    assert "does not query it" in text


def test_tracked_locations_use_actual_paths_and_keep_missing_root_intake_absent() -> None:
    paths = [
        "scripts/langchain/pr_verifier.py",
        "templates/consumer-repo/scripts/langchain/pr_verifier.py",
        "scripts/langchain/verifier_config.py",
        "tests/scripts/test_pr_verifier_compare.py",
        ".github/scripts/agents_verifier_context.js",
        "templates/consumer-repo/.github/scripts/agents_verifier_context.js",
        ".github/scripts/verifier_closure.js",
        "templates/consumer-repo/.github/scripts/verifier_closure.js",
        ".github/workflows/agents-verifier.yml",
        "templates/consumer-repo/.github/workflows/agents-verifier.yml",
        ".github/workflows/reusable-agents-verifier.yml",
        "templates/consumer-repo/.github/workflows/agents-issue-intake.yml",
        "docs/keepalive/GoalsAndPlumbing.md",
    ]
    resolved = audit.resolve_tracked_locations(paths)
    assert resolved["pr_verifier.py"] == [
        "scripts/langchain/pr_verifier.py",
        "templates/consumer-repo/scripts/langchain/pr_verifier.py",
    ]
    assert resolved["verifier_config.py"] == ["scripts/langchain/verifier_config.py"]
    assert ".github/workflows/agents-issue-intake.yml" not in resolved["agents-issue-intake.yml"]
    assert resolved["agents-issue-intake.yml"] == [
        "templates/consumer-repo/.github/workflows/agents-issue-intake.yml"
    ]
    assert "tests/scripts/test_pr_verifier_compare.py" not in resolved["pr_verifier.py"]


def test_workflow_parser_maps_the_reusable_invocation_away_from_the_template_copy() -> None:
    caller = "uses: stranske/Workflows/.github/workflows/reusable-agents-verifier.yml@main\n"
    reusable = """
          sparse-checkout: |
            .github/scripts
            scripts
          sparse-checkout-cone-mode: false
          python .workflows-lib/scripts/langchain/pr_verifier.py "${args[@]}" \\
            const file = './.workflows-lib/.github/scripts/agents_verifier_context.js';
            require('./.workflows-lib/.github/scripts/verifier_closure.js');
    """
    parsed = audit.parse_reusable_verifier_use(caller)
    assert parsed == {
        "workflow": "stranske/Workflows/.github/workflows/reusable-agents-verifier.yml",
        "ref": "main",
    }
    invocations = audit.parse_pr_verifier_invocations(reusable)
    assert invocations == [".workflows-lib/scripts/langchain/pr_verifier.py"]
    assert audit.tracked_path_for_runtime_path(invocations[0]) == (
        "scripts/langchain/pr_verifier.py"
    )
    assert audit.parse_sparse_checkout(reusable) == [".github/scripts", "scripts"]
    assert audit.parse_runtime_script_paths(reusable) == [
        "./.workflows-lib/.github/scripts/agents_verifier_context.js",
        "./.workflows-lib/.github/scripts/verifier_closure.js",
    ]


def test_implementation_revision_uses_a_printed_checkout_sha() -> None:
    printed = "a" * 40
    result = audit.implementation_revision(
        referenced_sha="b" * 40,
        fetch_at="2026-10-18T02:35:39.7063036Z",
        checkout_command="git checkout --progress --force -B main refs/remotes/origin/main",
        printed_sha=printed,
        next_commit_at="2026-10-18T02:30:00Z",
        history_available=True,
        referenced_sha_on_main=True,
    )
    assert result["revision"] == printed
    assert result["source"] == "checkout-log"


def test_implementation_revision_keeps_the_pin_when_main_moves_after_the_fetch() -> None:
    pinned = "021ec67ef580c83a88402a1574e27ea34db14dde"
    result = audit.implementation_revision(
        referenced_sha=pinned,
        fetch_at="2026-10-18T02:35:39.7063036Z",
        checkout_command="git checkout --progress --force -B main refs/remotes/origin/main",
        printed_sha=None,
        next_commit_at="2026-10-18T02:49:57Z",
        history_available=True,
        referenced_sha_on_main=True,
    )
    assert result["revision"] == pinned
    assert result["source"] == ("origin-main-unchanged-between-referenced-pin-and-script-fetch")


def test_implementation_revision_stays_unknown_when_main_moved_before_the_fetch() -> None:
    result = audit.implementation_revision(
        referenced_sha="021ec67ef580c83a88402a1574e27ea34db14dde",
        fetch_at="2026-10-18T02:35:39.7063036Z",
        checkout_command="git checkout --progress --force -B main refs/remotes/origin/main",
        printed_sha=None,
        next_commit_at="2026-10-18T02:35:39.7063036Z",
        history_available=True,
        referenced_sha_on_main=True,
    )
    assert result["revision"] == audit.UNKNOWN
    assert result["source"] == "origin-main-moved-before-script-fetch"


def test_implementation_revision_stays_unknown_without_main_history() -> None:
    result = audit.implementation_revision(
        referenced_sha="021ec67ef580c83a88402a1574e27ea34db14dde",
        fetch_at="2026-10-18T02:35:39.7063036Z",
        checkout_command="git checkout --progress --force -B main refs/remotes/origin/main",
        printed_sha=None,
        next_commit_at=None,
        history_available=False,
        referenced_sha_on_main=False,
    )
    assert result["revision"] == audit.UNKNOWN
    assert result["source"] == "main-history-unavailable"


def test_owner_excluded_repository_is_rejected_before_surface_resolution() -> None:
    def runner(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        raise AssertionError(f"git must not run for an excluded repository: {argv} {timeout}")

    with pytest.raises(audit.OwnerExcludedRepository):
        audit.resolve_production_surfaces(repo_slug=EXCLUDED_REPO, runner=runner)


def test_resolve_production_surfaces_identifies_the_selected_run_revision() -> None:
    resolved = audit.resolve_production_surfaces(REPO_ROOT)
    locations = resolved["locations"]
    assert [item["path"] for item in locations["pr_verifier.py"]] == [
        "scripts/langchain/pr_verifier.py",
        "templates/consumer-repo/scripts/langchain/pr_verifier.py",
    ]
    assert [item["path"] for item in locations["verifier_config.py"]] == [
        "scripts/langchain/verifier_config.py"
    ]
    assert ".github/workflows/agents-issue-intake.yml" in resolved["absent_root_paths"]
    assert locations["agents-issue-intake.yml"][0]["path"] == (
        "templates/consumer-repo/.github/workflows/agents-issue-intake.yml"
    )
    assert locations["GoalsAndPlumbing.md"][0]["path"] == "docs/keepalive/GoalsAndPlumbing.md"
    selected = resolved["selected_run"]
    assert selected["workflow_path"] == ".github/workflows/agents-verifier.yml"
    assert selected["workflow_revision"] == "021ec67ef580c83a88402a1574e27ea34db14dde"
    implementation = selected["verifier_implementation"]
    assert implementation["tracked_path"] == "scripts/langchain/pr_verifier.py"
    assert implementation["revision"] == selected["workflow_revision"]
    assert implementation["template_copy_executed"] is False
    assert implementation["template_copy_same_blob"] is True
    assert implementation["imports_verifier_config"] is True
    assert implementation["log_invocation_matches_workflow"] is True
    assert implementation["printed_checkout_sha"] is None
    assert selected["reusable_workflow"]["sparse_checkout_includes_template"] is False
    assert selected["intake_workflow"]["used_by_selected_run"] is False
    assert selected["other_checkouts"][0]["verifier_implementation"] is False
    assert EXCLUDED_REPO not in json.dumps(resolved)
    blobs = {item["role"]: item["blob"] for item in locations["pr_verifier.py"]}
    assert blobs["repository"] == blobs["template"]
    assert re.fullmatch(r"[0-9a-f]{40}", blobs["repository"])


def test_resolve_command_matches_the_library_and_audit_record() -> None:
    completed = subprocess.run(
        ["python3", "verifier_4422_audit.py", "resolve-production-surfaces"],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload == audit.resolve_production_surfaces(REPO_ROOT)
    text = (REPO_ROOT / "verifier-4422-audit.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)\n```", text, re.S)
    assert json.loads(blocks[2]) == payload
    assert "python3 verifier_4422_audit.py resolve-production-surfaces" in text


def test_owner_excluded_repository_is_rejected_before_live_evidence_loads() -> None:
    def loader() -> dict[str, object]:
        raise AssertionError("saved evidence must not load")

    with pytest.raises(audit.OwnerExcludedRepository):
        audit.live_pr_record(EXCLUDED_REPO, loader=loader)
    with pytest.raises(audit.OwnerExcludedRepository):
        audit.build_live_pr_collection_commands({"repository": EXCLUDED_REPO})


def test_workflows_lib_sha_stays_distinct_from_another_jobs_checkout() -> None:
    lib_sha = "a" * 40
    merge_sha = "b" * 40
    log = "\n".join(
        [
            "verifier / Run post-merge verifier\tSTEP\t"
            "2026-10-18T02:35:39.0000000Z "
            "Working directory is '/work/.workflows-lib'",
            "verifier / Run post-merge verifier\tSTEP\t"
            "2026-10-18T02:35:42.0000000Z "
            "[command]/usr/bin/git log -1 --format=%H",
            f"verifier / Run post-merge verifier\tSTEP\t2026-10-18T02:35:42.0000001Z {lib_sha}",
            "Verify named gates on immutable merge commit\tSTEP\t"
            "2026-10-18T02:37:47.0000000Z "
            "[command]/usr/bin/git log -1 --format=%H",
            "Verify named gates on immutable merge commit\tSTEP\t"
            f"2026-10-18T02:37:47.0000001Z {merge_sha}",
            "verifier / Run post-merge verifier\tSTEP\t"
            "2026-10-18T02:35:28.0000000Z "
            "Uses: stranske/Workflows/.github/workflows/reusable-agents-verifier.yml"
            f"@refs/heads/main ({lib_sha})",
        ]
    )
    parsed = audit.parse_verifier_run_log(log)
    assert parsed["workflows_lib_sha"] == lib_sha
    assert parsed["reusable_workflow_shas"] == [lib_sha]
    assert merge_sha not in parsed["reusable_workflow_shas"]


def test_live_packet_disagreement_remains_unresolved() -> None:
    evidence = json.loads((REPO_ROOT / "verifier_4422_live_pr.json").read_text(encoding="utf-8"))
    evidence["log_excerpt"] = evidence["log_excerpt"].replace(
        "reusable-agents-verifier.yml@refs/heads/main "
        "(021ec67ef580c83a88402a1574e27ea34db14dde)",
        "reusable-agents-verifier.yml@refs/heads/main (" + ("c" * 40) + ")",
    )
    record = audit.assemble_live_pr_record(evidence)
    assert record["deployed_verifier_revision"]["revision"] is None
    assert any("do not agree" in gap for gap in record["evidence_gaps"])


def test_live_pr_record_keeps_the_collected_packet_and_its_gaps() -> None:
    record = audit.live_pr_record()
    assert record["network_used_for_replay"] is False
    assert record["repository"] == "stranske/Workflows"
    assert record["multi_file"] is True
    assert record["changed_file_count"] == 2
    assert [item["path"] for item in record["changed_files"]] == [
        "scripts/langchain/issue_optimizer.py",
        "tests/scripts/test_issue_optimizer.py",
    ]
    assert record["immutable_merge_sha"]["sha"] == ("7ccda2ad80ccac05348ad305fb2248b02b0c2c81")
    assert record["immutable_merge_sha"]["values_agree"] is True
    revision = record["deployed_verifier_revision"]["revision"]
    assert revision == "021ec67ef580c83a88402a1574e27ea34db14dde"
    assert record["run"]["url"] == (
        "https://github.com/stranske/Workflows/actions/runs/39090617832"
    )
    assert record["run"]["post_merge"] is True
    assert record["report"]["files_reviewed"] == [
        {"provider": "openai", "reviewed": 2, "total": 2},
        {"provider": "anthropic", "reviewed": 2, "total": 2},
    ]
    assert record["report"]["files_reviewed_match_log"] is True
    assert record["report"]["truncated_substring_count"] == 5
    assert record["report"]["prompt_budget_marker_present"] is False
    assert record["report"]["body"].startswith("## Provider Comparison Report")
    source = record["source_issue"]
    assert source["disposition_at_run_completion"]["state"] == "open"
    assert source["disposition_at_run_completion"]["last_event"]["event"] == "reopened"
    assert source["state_at_collection"] == "closed"
    assert source["later_close_used_as_run_disposition"] is False
    assert source["closure_job_log"] == "none"
    gaps = "\n".join(record["evidence_gaps"])
    assert "comparison.json" in gaps
    assert "files_not_reviewed" in gaps
    assert "Which named path was omitted is not stated." in gaps
    commands = "\n".join(record["collection_commands"])
    assert "gh run list --repo stranske/Workflows" in commands
    assert "gh run view 39090617832 --repo stranske/Workflows --log" in commands
    assert "gh run download 39090617832 --repo stranske/Workflows" in commands
    assert EXCLUDED_REPO not in json.dumps(record)
    opened = audit.issue_state_as_of(source["timeline"], "2026-10-18T02:39:02Z")
    closed = audit.issue_state_as_of(source["timeline"], "2026-11-03T18:23:53Z")
    assert opened["state"] == "open"
    assert closed["state"] == "closed"


def test_live_pr_command_matches_the_saved_replay_and_audit_record() -> None:
    completed = subprocess.run(
        ["python3", "verifier_4422_audit.py", "live-pr-evidence"],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload == audit.live_pr_record()
    help_text = subprocess.run(
        ["python3", "verifier_4422_audit.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert help_text.returncode == 0
    assert "live-pr-evidence" in help_text.stdout
    assert "gh run download" in help_text.stdout
    assert "does not use the network" in help_text.stdout
    text = (REPO_ROOT / "verifier-4422-audit.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)\n```", text, re.S)
    assert json.loads(blocks[3]) == payload
    assert "python3 verifier_4422_audit.py live-pr-evidence" in text


def test_owner_excluded_repository_is_rejected_before_live_report_loads() -> None:
    def loader() -> dict[str, object]:
        raise AssertionError("saved report evidence must not load")

    with pytest.raises(audit.OwnerExcludedRepository):
        audit.live_report_acceptance_packet(EXCLUDED_REPO, loader=loader)


def test_cited_run_fails_live_identification_when_the_comparison_artifact_is_absent() -> None:
    acceptance = audit.live_report_acceptance(audit.live_pr_record())
    assert acceptance["criterion_live_report_identified"] is False
    assert acceptance["run_id"] == "39090617832"
    assert "did not retrieve a comparison-results artifact" in (
        acceptance["live_report_first_broken_step"]
    )
    assert acceptance["criterion_complete_report"] is False
    assert acceptance["counts_as_historical_campaign_evidence"] is False


def test_live_report_replay_identifies_the_complete_post_merge_report() -> None:
    packet = audit.live_report_acceptance_packet()
    acceptance = packet["acceptance"]
    record = packet["record"]
    assert packet["network_used_for_replay"] is False
    assert acceptance["criterion_live_report_identified"] is True
    assert acceptance["live_report_first_broken_step"] is None
    assert acceptance["criterion_complete_report"] is True
    assert acceptance["complete_report_first_broken_step"] is None
    assert acceptance["log_command"] == ("gh run view 41736356184 --repo stranske/Workflows --log")
    assert acceptance["artifact_retrieval_command"] == (
        "gh run download 41736356184 --repo stranske/Workflows"
    )
    assert acceptance["immutable_merge_sha"] == "4928870982db3bc3b85c701b4cca2492128739b2"
    assert acceptance["deployed_verifier_revision"] == acceptance["immutable_merge_sha"]
    assert acceptance["changed_file_count"] == 4
    assert acceptance["files_reviewed"] == [
        {"provider": "openai", "reviewed": 4, "total": 4},
        {"provider": "anthropic", "reviewed": 4, "total": 4},
    ]
    assert acceptance["reviewed_file_paths"] == [item["path"] for item in record["changed_files"]]
    assert acceptance["files_not_reviewed"] == []
    assert acceptance["truncated_substring_count"] == 0
    assert acceptance["prompt_budget_marker_present"] is False
    assert record["run"]["post_merge"] is True
    assert record["multi_file"] is True
    assert "truncated" not in record["report"]["body"]
    assert acceptance["counts_as_historical_campaign_evidence"] is False
    assert "not evidence that the 2026-10-24 targets were met" in (
        acceptance["historical_campaign_effect"]
    )
    coverage = acceptance["input_coverage"]
    assert [item["acceptance_evidence"] for item in coverage] == ["truncated", "truncated"]
    assert all(item["context_truncated"] is True for item in coverage)
    assert all(item["files_truncated"] == 0 for item in coverage)
    assert "acceptance_evidence and context_truncated stay visible" in (
        acceptance["input_coverage_effect"]
    )
    assert EXCLUDED_REPO not in json.dumps(packet)
    commands = "\n".join(record["collection_commands"])
    assert acceptance["log_command"] in commands
    assert acceptance["artifact_retrieval_command"] in commands
    assert "2026-11-03T23:05:00Z..2026-11-03T23:06:00Z" in commands


def test_live_report_command_matches_the_replay_and_audit_record() -> None:
    completed = subprocess.run(
        ["python3", "verifier_4422_audit.py", "live-report-acceptance"],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload == audit.live_report_acceptance_packet()
    help_text = subprocess.run(
        ["python3", "verifier_4422_audit.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert help_text.returncode == 0
    assert "live-report-acceptance" in help_text.stdout
    assert "gh run view 41736356184 --repo stranske/Workflows --log" in help_text.stdout
    assert "gh run download 41736356184 --repo stranske/Workflows" in help_text.stdout
    assert "without network access" in help_text.stdout.lower() or (
        "does not use the network" in help_text.stdout
    )
    text = (REPO_ROOT / "verifier-4422-audit.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)\n```", text, re.S)
    acceptance_blocks = [
        json.loads(block)
        for block in blocks
        if '"criterion_live_report_identified"' in block or '"criterion_complete_report"' in block
    ]
    assert acceptance_blocks
    assert acceptance_blocks[-1] == payload["acceptance"]
    assert "python3 verifier_4422_audit.py live-report-acceptance" in text


def test_help_documents_historical_collection_and_replay() -> None:
    help_text = subprocess.run(
        ["python3", "verifier_4422_audit.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert help_text.returncode == 0
    stdout = help_text.stdout
    assert "historical-campaign" in stdout
    assert "verifier_4422_historical.json" in stdout
    assert "without network access" in stdout
    assert "stranske/collab-admin" in stdout
    assert "python3 verifier_4422_audit.py historical-campaign" in stdout


def test_historical_campaign_replay_keeps_unknowns_and_excludes_owner_repo() -> None:
    report = audit.historical_campaign_report()
    assert report["network_used_for_replay"] is False
    assert report["known_eligible_count"] == 0
    assert report["population_count"] >= 1
    assert report["owner_excluded_repository"] == EXCLUDED_REPO
    assert EXCLUDED_REPO in report["repositories_not_queried"]
    assert EXCLUDED_REPO not in report["repositories_queried"]
    assert all(item["eligibility"] == audit.UNKNOWN for item in report["population_records"])
    assert all(item["repository"] != EXCLUDED_REPO for item in report["population_records"])
    trunc = report["aggregates"]["truncation_concerns"]
    closure = report["aggregates"]["two_hour_closure"]
    assert trunc["target_count"] == 0
    assert trunc["target_status"] == "indeterminate"
    assert closure["target_percent"] == 80
    assert closure["target_status"] == "indeterminate"
    assert isinstance(closure["numerator"], int)
    assert isinstance(closure["denominator"], int)
    assert "unknown" in json.dumps(report["unknown_effects_on_conclusions"]).lower()
    assert "41736356184" in json.dumps(report["unknown_effects_on_conclusions"])
    assert report["production_repairs"]["count"] == 0
    # Counter_Risk#1168 is the campaign's cited reopen example: closed then reopened.
    cited = [
        item
        for item in report["population_records"]
        if item["repository"] == "stranske/Counter_Risk" and item["pull_request"] == 1168
    ]
    assert cited
    assert cited[0]["truncation_concerns_classification"] == "truncation-CONCERNS"
    assert cited[0]["closed_within_two_hours"] is False
    assert cited[0]["state_at_two_hours"] == "open"
    assert EXCLUDED_REPO not in json.dumps(report["population_records"])


def test_historical_campaign_rejects_owner_excluded_repository_before_load() -> None:
    def loader() -> dict[str, object]:
        raise AssertionError("saved historical evidence must not load")

    with pytest.raises(audit.OwnerExcludedRepository):
        audit.historical_campaign_report(repo=EXCLUDED_REPO, loader=loader)


def test_historical_campaign_command_matches_replay_and_audit_record() -> None:
    completed = subprocess.run(
        ["python3", "verifier_4422_audit.py", "historical-campaign"],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload == audit.historical_campaign_report()
    text = (REPO_ROOT / "verifier-4422-audit.md").read_text(encoding="utf-8")
    assert "python3 verifier_4422_audit.py historical-campaign" in text
    assert "## Historical campaign evaluation (2026-10-24 targets)" in text
    assert "indeterminate" in text
    blocks = re.findall(r"```json\n(.*?)\n```", text, re.S)
    historical_blocks = [json.loads(block) for block in blocks if '"known_eligible_count"' in block]
    assert historical_blocks
    published = historical_blocks[-1]
    assert published["aggregates"] == payload["aggregates"]
    assert published["population_count"] == payload["population_count"]
    assert published["known_eligible_count"] == 0
    assert published["network_used_for_replay"] is False


def test_report_is_truncation_concerns_requires_both_markers() -> None:
    assert audit.report_is_truncation_concerns(
        "## Provider Comparison Report\n| openai | gpt | CONCERNS | 80% | truncated input |\n"
    )
    assert not audit.report_is_truncation_concerns(
        "## Provider Comparison Report\n| openai | gpt | PASS | 80% | truncated acceptance artifact |\n"
    )
    assert not audit.report_is_truncation_concerns(
        "## Provider Comparison Report\n| openai | gpt | CONCERNS | 80% | real defect |\n"
    )
