import json
import sys
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


def test_observation_includes_history_of_disabled_gate(monkeypatch):
    """A workflow disabled after the interval must not lose its historical runs."""
    commands = []

    def execute(command, **kwargs):
        commands.append(command)
        # gh resolves named disabled workflows only when --all is passed.
        if command[command.index("-R") + 1] == "owner/disabled" and "--all" not in command:
            return SimpleNamespace(returncode=1, stdout="")
        page = [run(1, conclusion="cancelled"), run(2, 1)]
        return SimpleNamespace(returncode=0, stdout=json.dumps(page))

    monkeypatch.setattr(measure.subprocess, "run", execute)
    report = measure.observe(["owner/active", "owner/disabled"], START, END, time.monotonic() + 110)

    assert report["status"] == "complete"
    assert report["errors"] == {}
    assert (report["numerator"], report["denominator"], report["percentage"]) == (2, 4, 50)
    assert not report["passed"]
    assert report["commands"] == {
        "owner/active": [commands[0]],
        "owner/disabled": [commands[1]],
    }


@pytest.mark.parametrize("seconds", [-1, 172800, 172801])
def test_unfinished_runs_outside_interval_do_not_block_observation(monkeypatch, seconds):
    outside = run(2, seconds, conclusion="")
    page = [run(1), outside]
    monkeypatch.setattr(
        measure.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(page)),
    )

    report = measure.observe(["owner/repo"], START, END, time.monotonic() + 110)

    assert report["status"] == "complete"
    assert report["runs"] == {"owner/repo": [run(1)]}
    assert (report["numerator"], report["denominator"], report["percentage"]) == (0, 1, 0)
    assert report["passed"]


@pytest.mark.parametrize(
    "failure", ["command", "invalid_json", "missing_fields", "timeout", "unavailable"]
)
def test_failed_reads_cannot_become_zero_or_pass(monkeypatch, failure):
    commands = []

    def execute(*args, **kwargs):
        commands.append(args[0])
        if failure == "timeout":
            raise measure.subprocess.TimeoutExpired("gh", 1)
        if failure == "unavailable":
            raise FileNotFoundError("gh")
        return SimpleNamespace(
            returncode=1 if failure == "command" else 0,
            stdout={"command": "", "invalid_json": "{", "missing_fields": "[{}]"}[failure],
        )

    monkeypatch.setattr(measure.subprocess, "run", execute)
    report = measure.observe(["owner/repo"], START, END, time.monotonic() + 110)
    assert report["status"] == "incomplete"
    assert report["numerator"] is report["denominator"] is report["percentage"] is None
    assert report["errors"]["owner/repo"]
    assert report["commands"] == {"owner/repo": commands}
    assert not report["passed"]


def test_failed_split_read_retains_all_attempted_commands(monkeypatch):
    monkeypatch.setattr(measure, "RUN_LIMIT", 2)
    commands = []

    def execute(command, **kwargs):
        commands.append(command)
        if len(commands) == 3:
            return SimpleNamespace(returncode=1, stdout="")
        page = [run(1), run(2)] if len(commands) == 1 else [run(3, 86401)]
        return SimpleNamespace(returncode=0, stdout=json.dumps(page))

    monkeypatch.setattr(measure.subprocess, "run", execute)
    report = measure.observe(["owner/repo"], START, END, time.monotonic() + 110)

    assert len(commands) == 3
    assert report["commands"] == {"owner/repo": commands}
    assert report["status"] == "incomplete"
    assert report["runs"] == {}
    assert report["numerator"] is report["denominator"] is report["percentage"] is None
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
        assert report["status"] == "no_runs"
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
    assert report["commands"] == {"owner/repo": []}
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
    "field,value", [("conclusion", None), ("conclusion", ""), ("createdAt", None), ("headSha", "")]
)
@pytest.mark.parametrize("seconds", [0, 172799])
def test_incomplete_run_never_establishes_acceptance(monkeypatch, field, value, seconds):
    record = run(1, seconds)
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


@pytest.mark.parametrize(
    "page,message",
    [
        ({"workflow_runs": []}, "gh run list returned an invalid run list"),
        ([run(1), run(1, conclusion="cancelled")], "run changed during paginated collection"),
        ([dict(run(1), event=None)], "run timestamp or event is invalid"),
        ([dict(run(1), databaseId="1")], "run identity or head is missing"),
        ([dict(run(1), databaseId=True)], "run identity or head is missing"),
    ],
)
def test_invalid_run_data_keeps_observation_incomplete(monkeypatch, page, message):
    """Malformed or conflicting API data cannot establish campaign acceptance."""
    commands = []

    def execute(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps(page))

    monkeypatch.setattr(measure.subprocess, "run", execute)
    report = measure.observe(["owner/repo"], START, END, time.monotonic() + 110)

    assert report["status"] == "incomplete"
    assert message in report["errors"]["owner/repo"]
    assert report["commands"] == {"owner/repo": commands}
    assert report["runs"] == {}
    assert report["numerator"] is report["denominator"] is report["percentage"] is None
    assert not report["passed"]


@pytest.mark.parametrize(
    "value,diagnostic",
    [
        ("not-a-date", "invalid --merge"),
        ("2026-10-18T08:00:00", "timestamps must include a timezone"),
        ("2026-10-18T08:00:00.123Z", "mergedAt must have whole-second precision"),
    ],
)
def test_invalid_merge_reports_usage_without_collecting(
    monkeypatch, capsys, tmp_path, value, diagnostic
):
    """Reject unusable merge evidence as a CLI error before any remote reads."""
    output = tmp_path / "observation.json"
    monkeypatch.setattr(sys, "argv", ["measure", "--merge", value, "--output", str(output)])
    monkeypatch.setattr(measure, "extract_repos", lambda *a: pytest.fail("invalid merge accepted"))

    with pytest.raises(SystemExit) as exc:
        measure.main()

    assert exc.value.code == 2
    stderr = capsys.readouterr().err
    assert "usage:" in stderr
    assert diagnostic in stderr
    assert "Traceback" not in stderr
    assert not output.exists()
