import hashlib
import json
from pathlib import Path

import pytest
from scripts import repo_review_approval_ledger as ledger


def make_ledger(tmp_path: Path) -> tuple[Path, list[dict]]:
    items = [
        {"repo": "owner/demo", "title": title, "body": f"Authorized scope: {title}"}
        for title in ["Old unfiled fix", "Already filed fix", "Uncertain filing"]
    ]
    source = tmp_path / "original.json"
    source.write_text(json.dumps({"issues": items}))
    path = tmp_path / "approval-ledger.json"
    path.write_text(
        json.dumps(
            {
                "schema": ledger.SCHEMA,
                "source_queue_path": str(source),
                "source_queue_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "source_cycle": "previous-cycle",
                "authority": "Owner approved these original scopes",
                "intake_hold": {"active": True},
                "entries": [
                    {
                        "repo": item["repo"],
                        "title": item["title"],
                        "finding_id": ledger.finding_id(item["repo"], item["title"]),
                        "approved_item_sha256": ledger.item_digest(item),
                        "filing": {
                            "status": status,
                            "issues": (
                                ["https://example.test/issues/1"] if status == "filed" else []
                            ),
                        },
                    }
                    for item, status in zip(items, ["unfiled", "filed", "unknown"], strict=True)
                ],
            }
        )
    )
    return path, items


def test_ledger_preserves_authorized_scope_without_requeueing_filed_or_unknown(tmp_path):
    path, originals = make_ledger(tmp_path)
    queue = {"issues": [dict(item, body="New broader scope") for item in originals]}
    result = ledger.merge_approval_ledger(queue, path, allowed_repos={"owner/demo"})
    assert result["issues"] == []
    assert len(result["held_approved_issues"]) == 1
    item = result["held_approved_issues"][0]
    assert item["body"] == originals[0]["body"]
    assert item["approval_source"]["item_sha256"] == ledger.item_digest(originals[0])
    assert result["approval_ledger"]["counts"] == {"unfiled": 1, "filed": 1, "unknown": 1}
    assert result["upload_allowed"] is False
    assert result["intake_hold"]["active"] is True
    assert queue["issues"][0]["body"] == "New broader scope"
    assert len(result["approval_scope_conflicts"]) == 3
    assert {x["original_filing_status"] for x in result["approval_scope_conflicts"]} == {
        "filed",
        "unfiled",
        "unknown",
    }
    assert all(
        x["current_approved_issue"]["body"] == "New broader scope"
        for x in result["approval_scope_conflicts"]
    )


def test_ledger_rejects_changed_original_queue(tmp_path):
    path, _ = make_ledger(tmp_path)
    (tmp_path / "original.json").write_text('{"issues": []}')
    with pytest.raises(ValueError, match="digest"):
        ledger.merge_approval_ledger({"issues": []}, path, allowed_repos={"owner/demo"})


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "duplicate",
        "changed-scope",
        "unknown-status",
        "missing-evidence",
        "conflicting-evidence",
    ],
)
def test_ledger_rejects_incomplete_or_inconsistent_approval_records(tmp_path, change):
    path, _ = make_ledger(tmp_path)
    data = json.loads(path.read_text())
    if change == "missing":
        data["entries"].pop()
    elif change == "duplicate":
        data["entries"].append(data["entries"][0])
    elif change == "changed-scope":
        data["entries"][0]["approved_item_sha256"] = "different"
    elif change == "unknown-status":
        data["entries"][0]["filing"]["status"] = "complete"
    elif change == "missing-evidence":
        data["entries"][1]["filing"]["issues"] = []
    else:
        data["entries"][0]["filing"]["issues"] = ["https://example.test/issues/2"]
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        ledger.merge_approval_ledger({"issues": []}, path, allowed_repos={"owner/demo"})


def test_ledger_does_not_route_repositories_outside_active_scope(tmp_path):
    path, _ = make_ledger(tmp_path)
    result = ledger.merge_approval_ledger({"issues": []}, path, allowed_repos={"owner/other"})
    assert result["issues"] == []
    assert sum(result["approval_ledger"]["counts"].values()) == 0


def test_missing_ledger_keeps_existing_queue_contract(tmp_path):
    queue = {"issues": []}
    assert (
        ledger.merge_approval_ledger(queue, tmp_path / "missing.json", allowed_repos=set()) is queue
    )


def test_held_queue_is_empty_to_legacy_upload_readers(tmp_path):
    from scripts.upload_repo_review_issues import load_queue

    path, _ = make_ledger(tmp_path)
    result = ledger.merge_approval_ledger({"issues": []}, path, allowed_repos={"owner/demo"})
    output = tmp_path / "queue.json"
    output.write_text(json.dumps(result))
    assert load_queue(output) == []
    assert len(result["held_approved_issues"]) == 1


def test_explicit_ledger_hold_release_restores_only_unfiled_original_scope(tmp_path):
    path, originals = make_ledger(tmp_path)
    data = json.loads(path.read_text())
    data["intake_hold"]["active"] = False
    path.write_text(json.dumps(data))
    result = ledger.merge_approval_ledger({"issues": []}, path, allowed_repos={"owner/demo"})
    assert result["upload_allowed"] is True
    assert len(result["issues"]) == 1
    assert result["issues"][0]["body"] == originals[0]["body"]
    assert "held_approved_issues" not in result


@pytest.mark.parametrize("active", [True, False])
def test_restored_and_new_approvals_keep_priority_order(tmp_path, active):
    path, _ = make_ledger(tmp_path)
    data = json.loads(path.read_text())
    data["intake_hold"]["active"] = active
    path.write_text(json.dumps(data))
    urgent = {
        "repo": "owner/demo",
        "title": "Urgent current fix",
        "body": "New explicitly approved scope",
        "priority_rank": 0,
        "candidate_index": 5,
    }
    result = ledger.merge_approval_ledger({"issues": [urgent]}, path, allowed_repos={"owner/demo"})
    selected = result["held_approved_issues"] if active else result["issues"]
    assert [item["title"] for item in selected] == ["Urgent current fix", "Old unfiled fix"]
