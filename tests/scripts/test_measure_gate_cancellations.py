import json
import time
from datetime import timedelta
from types import SimpleNamespace

import pytest
from scripts import measure_gate_cancellations as measure

START = measure.timestamp("2026-10-18T08:00:00Z")
END = START + timedelta(hours=48)


def run(number, seconds=0, conclusion="success", event="pull_request", head="head-a"):
    return {
        "databaseId": number,
        "conclusion": conclusion,
        "event": event,
        "headSha": head,
        "createdAt": measure.iso(START + timedelta(seconds=seconds)),
    }


@pytest.mark.parametrize("seconds,expected", [(0, 1), (5, 1), (6, 0), (-5, 1), (-6, 0)])
def test_burst_boundary(seconds, expected):
    assert measure.counts([run(1, conclusion="cancelled"), run(2, seconds)]) == (expected, 2)


def test_counts_runs_once_and_keeps_all_events_in_denominator():
    assert measure.counts(
        [
            run(1, conclusion="cancelled"),
            run(2, 1),
            run(3, 2),
            run(4, 3, conclusion="cancelled", event="workflow_dispatch"),
            run(5, 4, conclusion="cancelled", head="other-head"),
        ]
    ) == (1, 5)


def test_saturated_collection_splits_windows_and_deduplicates_boundaries(monkeypatch):
    monkeypatch.setattr(measure, "RUN_LIMIT", 3)
    responses = [
        [run(99), run(98), run(97)],  # Saturation must never count as a complete read.
        [run(2, 86400), run(3, 86401)],
        [run(1, -1), run(2, 86400)],
    ]
    commands = []

    def execute(command, **kwargs):
        commands.append(command)
        assert 0 < kwargs["timeout"] <= 110
        return SimpleNamespace(returncode=0, stdout=json.dumps(responses.pop(0)))

    monkeypatch.setattr(measure.subprocess, "run", execute)
    runs, recorded = measure.collect_runs("owner/repo", START, END, time.monotonic() + 110)
    assert {r["databaseId"] for r in runs} == {2, 3}
    assert recorded == commands
    assert len(commands) == 3
    assert all("--limit" in command and "databaseId" in command[-1] for command in commands)


def test_collection_excludes_interval_end(monkeypatch):
    page = [run(1), run(2, 172800), run(3, -1)]
    monkeypatch.setattr(
        measure.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(page)),
    )
    runs, _ = measure.collect_runs("owner/repo", START, END, time.monotonic() + 110)
    assert runs == [run(1)]


@pytest.mark.parametrize("failure", ["command", "invalid_json", "missing_fields", "timeout"])
def test_failed_reads_cannot_become_zero_or_pass(monkeypatch, failure):
    def execute(*args, **kwargs):
        if failure == "timeout":
            raise measure.subprocess.TimeoutExpired("gh", 1)
        return SimpleNamespace(
            returncode=1 if failure == "command" else 0,
            stdout={"command": "", "invalid_json": "{", "missing_fields": "[{}]"}[failure],
        )

    monkeypatch.setattr(measure.subprocess, "run", execute)
    report = measure.observe(["owner/repo"], START, END, time.monotonic() + 110)
    assert report["status"] == "incomplete"
    assert report["numerator"] is report["denominator"] is report["percentage"] is None
    assert report["errors"]["owner/repo"]
    assert not report["passed"]


def test_unfinished_observation_does_not_collect(monkeypatch):
    monkeypatch.setattr(measure, "collect_runs", lambda *args: pytest.fail("interval unfinished"))
    report = measure.observe(["owner/repo"], START, END - timedelta(seconds=1), 0)
    assert report["status"] == "pending"
    assert report["interval_end"] == measure.iso(END)
    assert report["percentage"] is None
    assert not report["passed"]


@pytest.mark.parametrize("size,expected", [(0, False), (19, False), (20, True), (21, True)])
def test_percentage_threshold_and_empty_result(monkeypatch, size, expected):
    runs = [run(i, i, conclusion="cancelled" if i == 0 else "success") for i in range(size)]
    monkeypatch.setattr(measure, "collect_runs", lambda *args: (runs, []))
    report = measure.observe(["owner/repo"], START, END, 0)
    assert report["denominator"] == size
    assert report["numerator"] == (1 if size else 0)
    assert report["passed"] is expected
    if not size:
        assert report["percentage"] is None


def test_never_pairs_siblings_across_repositories(monkeypatch):
    monkeypatch.setattr(
        measure,
        "collect_runs",
        lambda repo, *args: ([run(1, conclusion="cancelled" if repo == "a" else "success")], []),
    )
    report = measure.observe(["a", "b"], START, END, 0)
    assert (report["numerator"], report["denominator"]) == (0, 2)


def test_expired_deadline_never_calls_gh(monkeypatch):
    monkeypatch.setattr(measure.subprocess, "run", lambda *a, **k: pytest.fail("deadline elapsed"))
    report = measure.observe(["owner/repo"], START, END, 0)
    assert report["status"] == "incomplete"
    assert not report["passed"]


def test_saturated_one_second_window_refuses_completion(monkeypatch):
    monkeypatch.setattr(measure, "RUN_LIMIT", 1)
    monkeypatch.setattr(
        measure.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps([run(1)])),
    )
    with pytest.raises(ValueError, match="one-second window"):
        measure.collect_runs(
            "owner/repo", START, START + timedelta(seconds=1), time.monotonic() + 110
        )


@pytest.mark.parametrize(
    "field,value", [("conclusion", None), ("createdAt", None), ("headSha", "")]
)
def test_incomplete_run_never_establishes_acceptance(monkeypatch, field, value):
    record = run(1)
    record[field] = value
    monkeypatch.setattr(
        measure.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps([record])),
    )
    report = measure.observe(["owner/repo"], START, END, time.monotonic() + 110)
    assert report["status"] == "incomplete"
    assert report["percentage"] is None


def test_empty_roster_cannot_establish_acceptance():
    report = measure.observe([], START, END, 0)
    assert report["status"] == "incomplete"
    assert report["percentage"] is None


def test_late_consumer_failure_cannot_publish_partial_counts(monkeypatch):
    def collect(repo, *args):
        if repo == "unreadable":
            raise ValueError("gh run list failed")
        return [run(1)], []

    monkeypatch.setattr(measure, "collect_runs", collect)
    report = measure.observe(["readable", "unreadable"], START, END, 0)
    assert report["runs"]["readable"] == [run(1)]
    assert report["errors"] == {"unreadable": "gh run list failed"}
    assert report["status"] == "incomplete"
    assert report["numerator"] is report["denominator"] is report["percentage"] is None
