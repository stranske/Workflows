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
