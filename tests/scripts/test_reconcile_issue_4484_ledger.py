"""Verify the bounded ledger correction preserves evidence and its limits."""

import copy

import pytest
import yaml
from scripts import ledger_validate
from scripts import reconcile_issue_4484_ledger as reconciliation


@pytest.fixture
def original():
    # Keep an original-shape fixture so applying the correction to the real ledger
    # does not invalidate the reconciliation regressions.
    return {
        "version": 1,
        "issue": 4484,
        "base": "main",
        "branch": "codex/issue-4484",
        "tasks": [
            {
                "id": f"task-{number:02}",
                "title": f"Original task {number}",
                "status": "deferred" if number in (9, 11) else "done",
                "started_at": None if number in (9, 11) else f"2026-11-06T19:{number:02}:00Z",
                "finished_at": None if number in (9, 11) else f"2026-11-06T19:{number:02}:30Z",
                "commit": "" if number in (9, 11) else "555c4bd79ee812a6032f0d98531ddf33cb64d36a",
                "notes": [f"Original evidence for task {number}"],
            }
            for number in range(1, 12)
        ],
    }


def test_consolidation_retains_every_original_completion_record(original):
    before = copy.deepcopy(original)
    corrected = reconciliation.reconcile_ledger(original)
    previous = {task["id"]: task for task in original["tasks"]}
    current = {task["id"]: task for task in corrected["tasks"]}

    assert original == before
    assert list(current) == [key for key in previous if key not in {"task-03", "task-05"}]
    for target_id, fragment_id in (("task-02", "task-03"), ("task-04", "task-05")):
        target = current[target_id]
        assert target["consolidated_from"] == [previous[target_id], previous[fragment_id]]
        assert target["notes"] == previous[target_id]["notes"] + previous[fragment_id]["notes"]
        for key in ("status", "started_at", "finished_at", "commit"):
            assert target[key] == previous[target_id][key]
    for task_id in previous.keys() - {
        "task-02",
        "task-03",
        "task-04",
        "task-05",
        "task-09",
        "task-11",
    }:
        assert current[task_id] == previous[task_id]
    assert {key: value for key, value in corrected.items() if key != "tasks"} == {
        key: value for key, value in original.items() if key != "tasks"
    }


def test_receipts_do_not_turn_failed_workflow_validation_or_waiting_into_merge(original):
    previous = {task["id"]: task for task in original["tasks"]}
    current = {task["id"]: task for task in reconciliation.reconcile_ledger(original)["tasks"]}
    lint, classification = current["task-09"], current["task-11"]

    assert lint["status"] == "blocked"
    assert lint["finished_at"] is None
    assert lint["commit"] == ""
    assert "42325500360" in " ".join(lint["notes"])
    assert "12 failed" in " ".join(lint["notes"])
    assert "UNKNOWN, not PASS" in " ".join(lint["notes"])
    assert classification["status"] == "done"
    assert classification["commit"] == reconciliation.RECEIPT_COMMIT
    assert classification["finished_at"] == "2026-11-07T01:47:11Z"
    assert "20261107T014654Z" in " ".join(classification["notes"])
    assert "delivery_sealed_checks_pending" in " ".join(classification["notes"])
    for task in (lint, classification):
        assert task["previous_evidence"] == previous[task["id"]]
        assert reconciliation.CONSUMER_HEAD in " ".join(task["notes"])
        assert "do not establish consumer merge" in " ".join(task["notes"])


def test_output_obeys_existing_ledger_schema(original, tmp_path, monkeypatch):
    path = tmp_path / "issue-4484-ledger.yml"
    path.write_text(yaml.safe_dump(reconciliation.reconcile_ledger(original)), encoding="utf-8")
    # Isolate schema validation from unavailable historical git objects. This is
    # not the acceptance command or evidence that real commit validation passed.
    monkeypatch.setattr(ledger_validate, "_commit_files", lambda commit: ["source.py"])
    monkeypatch.delenv("LEDGER_VALIDATE_COMPLETION_EVIDENCE", raising=False)
    assert ledger_validate.validate_ledger(path) == []


def test_cli_emits_reviewable_yaml_without_modifying_input(original, tmp_path, capsys):
    path = tmp_path / "issue-4484-ledger.yml"
    before = yaml.safe_dump(original)
    path.write_text(before, encoding="utf-8")

    assert reconciliation.main([str(path)]) == 0

    output = yaml.safe_load(capsys.readouterr().out)
    assert output == reconciliation.reconcile_ledger(original)
    assert path.read_text(encoding="utf-8") == before
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("invalid", ["issue", "version", "duplicate", "missing", "unfinished"])
def test_unexpected_ledger_cannot_silently_lose_evidence(original, invalid):
    if invalid == "issue":
        original["issue"] = 1234
    elif invalid == "version":
        original["version"] = 2
    elif invalid == "duplicate":
        original["tasks"].append(copy.deepcopy(original["tasks"][0]))
    elif invalid == "missing":
        original["tasks"] = [task for task in original["tasks"] if task["id"] != "task-03"]
    else:
        next(task for task in original["tasks"] if task["id"] == "task-03")["status"] = "doing"
    before = copy.deepcopy(original)

    with pytest.raises(ValueError):
        reconciliation.reconcile_ledger(original)

    assert original == before
