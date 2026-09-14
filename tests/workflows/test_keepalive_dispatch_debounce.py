"""Exercise keepalive's real dispatch reservation and completion lifecycle."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
import yaml
from scripts.runner_lib import core


class Storage:
    def __init__(self):
        self.records = {}

    def read_record(self, pr_number, provider):
        return self.records.get((pr_number, provider))

    def write_record(self, pr_number, provider, record):
        self.records[pr_number, provider] = dict(record)


def dispatch(storage, head="a" * 40, provider="codex"):
    return core.should_dispatch(42, head, provider, storage, require_productivity=True)


def complete(storage, head="a" * 40, provider="codex", **progress):
    return core.record_completion(
        42, head, provider, core.parse_runner_output(provider, "Success"), storage, **progress
    )


@pytest.mark.parametrize("provider", ["codex", "claude", "cursor", "gemini"])
def test_completed_zero_output_allows_next_dispatch_on_same_head(provider):
    storage = Storage()
    assert dispatch(storage, provider=provider).should_dispatch
    record = complete(storage, provider=provider)
    assert record["status"] == "completed"
    assert record["commits"] == record["tasks_completed_delta"] == 0
    decision = dispatch(storage, provider=provider)
    assert decision.should_dispatch
    assert decision.reason == "retry-unproductive"
    assert not dispatch(storage, provider=provider).should_dispatch


@pytest.mark.parametrize("progress", [{"commits": 1}, {"tasks_completed_delta": 2}])
def test_productive_completion_retains_duplicate_protection(progress):
    storage = Storage()
    dispatch(storage)
    complete(storage, **progress)
    decision = dispatch(storage)
    assert not decision.should_dispatch
    assert decision.reason == "duplicate-completed"
    assert decision.prior_commits == progress.get("commits", 0)
    assert decision.prior_task_delta == progress.get("tasks_completed_delta", 0)
    assert "head changes" in decision.next_action
    assert dispatch(storage, head="b" * 40).should_dispatch


def test_legacy_completion_does_not_latch_keepalive_or_change_autofix():
    storage = Storage()
    storage.records[42, "codex"] = {"head_sha": "a" * 40, "status": "completed"}
    assert dispatch(storage).should_dispatch
    storage.records[42, "autofix"] = {"head_sha": "a" * 40, "status": "completed"}
    assert not core.should_dispatch(42, "a" * 40, "autofix", storage).should_dispatch


def test_repeated_zero_output_has_finite_cooldown_and_reserves_one_retry():
    storage = Storage()
    for _ in range(core.UNPRODUCTIVE_RETRY_LIMIT):
        assert dispatch(storage).should_dispatch
        complete(storage)
    blocked = dispatch(storage)
    assert not blocked.should_dispatch
    assert blocked.reason == "unproductive-cooldown"
    assert "Retry after" in blocked.next_action
    record = storage.records[42, "codex"]
    record["completed_at"] = (
        dt.datetime.now(dt.UTC) - dt.timedelta(seconds=core.UNPRODUCTIVE_RETRY_COOLDOWN_SECONDS + 1)
    ).isoformat()
    assert dispatch(storage).should_dispatch
    assert dispatch(storage).reason == "duplicate-pending"
    complete(storage)
    assert dispatch(storage).reason == "unproductive-cooldown"
    assert dispatch(storage, head="b" * 40).should_dispatch
    assert storage.records[42, "codex"]["unproductive_completions"] == 0


def test_duplicate_completion_does_not_charge_retry_budget_twice():
    storage = Storage()
    dispatch(storage)
    first = complete(storage)
    second = complete(storage)
    assert first["completed_at"] == second["completed_at"]
    assert second["unproductive_completions"] == 1


@pytest.mark.parametrize(
    "commit_sha,delta,productive",
    [
        ("", "0", False),
        ("a" * 40, "0", False),
        ("not-a-sha", "0", False),
        ("b" * 40, "0", True),
        ("", "2", True),
    ],
)
def test_cli_records_real_progress_and_emits_drain_reason(
    monkeypatch, capsys, tmp_path, commit_sha, delta, productive
):
    storage = Storage()
    monkeypatch.setattr(core, "_storage_from_name", lambda _: storage)
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "outputs"))
    args = ["--provider", "codex", "--pr-number", "42", "--head-sha", "a" * 40]
    core.main(["should-dispatch", *args, "--require-productivity"])
    core.main(
        [
            "record-completion",
            *args,
            "--summary",
            "Success",
            "--exit-code",
            "0",
            "--commit-sha",
            commit_sha,
            "--tasks-completed-delta",
            delta,
        ]
    )
    core.main(["should-dispatch", *args, "--require-productivity"])
    output = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert output["should_dispatch"] == ("false" if productive else "true")
    assert output["prior_commits"] == ("1" if commit_sha == "b" * 40 else "0")
    assert output["prior_task_delta"] == delta
    if productive:
        assert output["next_action"]


@pytest.mark.parametrize(
    "workflow",
    [
        ".github/workflows/agents-keepalive-loop.yml",
        "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml",
    ],
)
def test_workflows_wire_completion_evidence_after_summary(workflow):
    root = Path(__file__).resolve().parents[2]
    jobs = yaml.safe_load((root / workflow).read_text())["jobs"]
    debounce = next(s for s in jobs["evaluate"]["steps"] if s.get("id") == "runner_dispatch")
    assert "--require-productivity" in debounce["run"]
    completion = jobs["record-keepalive-completion"]
    assert "summary" in completion["needs"]
    step = next(s for s in completion["steps"] if s["name"] == "Record completion")
    assert '--commit-sha "$COMMIT_SHA"' in step["run"]
    assert '--tasks-completed-delta "$TASKS_COMPLETED_DELTA"' in step["run"]
    for provider in ["codex", "claude", "cursor", "gemini"]:
        assert f"needs.run-{provider}.outputs.commit-sha" in step["env"]["COMMIT_SHA"]
    assert "needs.summary.outputs.tasks_completed_delta" in step["env"]["TASKS_COMPLETED_DELTA"]
    assert (
        "steps.update-summary.outputs.tasks_completed_delta"
        in jobs["summary"]["outputs"]["tasks_completed_delta"]
    )
    assert "record-keepalive-completion" not in jobs["summary"]["needs"]
