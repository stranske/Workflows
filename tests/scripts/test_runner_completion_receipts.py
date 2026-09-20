"""Adversarial API interleavings for authoritative completion persistence."""

import copy
import json

import pytest
from scripts.runner_lib import core


class CommentApi:
    repo = "owner/repo"

    def __init__(self, reservation):
        prefix = (
            core.MARKER_PREFIX
            if "reservation_id" not in reservation
            else core.RESERVATION_MARKER_PREFIX
        )
        self.reservation = {
            "id": 1,
            "body": core._build_marker(42, "codex", reservation, marker_prefix=prefix),
        }
        self.receipts = []
        self.replace_before_write = None
        self.writes = []
        self.reads = []

    def comments(self):
        return [self.reservation, *self.receipts]

    def request(self, method, path, body=None):
        if method == "POST" and path == "/graphql":
            cursor = body["variables"]["cursor"]
            self.reads.append(cursor)
            comments = sorted(self.comments(), key=lambda item: item["id"])
            if cursor is not None:
                comments = [item for item in comments if item["id"] < int(cursor)]
            page = comments[-100:]
            return {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "comments": {
                                "nodes": [
                                    {
                                        "databaseId": item["id"],
                                        "body": item["body"],
                                        "author": item.get("user"),
                                        "authorAssociation": item.get("author_association"),
                                    }
                                    for item in copy.deepcopy(page)
                                ],
                                "pageInfo": {
                                    "hasPreviousPage": len(comments) > len(page),
                                    "startCursor": str(page[0]["id"]) if page else None,
                                    "hasNextPage": False,
                                    "endCursor": str(page[-1]["id"]) if page else None,
                                },
                            }
                        }
                    }
                }
            }
        if self.replace_before_write:
            self.receipts.append(
                {
                    "id": len(self.receipts) + 2,
                    "body": core._build_marker(
                        42,
                        "codex",
                        self.replace_before_write,
                        marker_prefix=core.RESERVATION_MARKER_PREFIX,
                    ),
                }
            )
            self.replace_before_write = None
        self.writes.append(method)
        if method == "PATCH":
            target_id = int(path.rsplit("/", 1)[-1])
            target = next(
                item for item in [self.reservation, *self.receipts] if item["id"] == target_id
            )
            target["body"] = body["body"]
            return copy.deepcopy(target)
        assert method == "POST"
        receipt = {"id": len(self.receipts) + 2, "body": body["body"]}
        self.receipts.append(receipt)
        return copy.deepcopy(receipt)


def reservation(attempt="old", *, legacy=False):
    value = {
        "provider": "codex",
        "pr_number": 42,
        "head_sha": "aaa",
        "key": core._runner_key(42, "aaa", "codex"),
        "status": "pending",
        "workflow_attempt_id": attempt,
        "started_at": "2026-09-20T00:00:00Z",
    }
    if not legacy:
        value["reservation_id"] = attempt + "-reservation"
    return value


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("automatic", [False, True])
def test_stale_completion_cannot_overwrite_new_reservation(monkeypatch, legacy, automatic):
    monkeypatch.setattr(core, "_workflow_attempt_id", lambda: "old")
    api = CommentApi(reservation(legacy=legacy))
    primary = core.PrCommentRunnerStorage(api)
    storage = core.FallbackRunnerStorage(primary, primary) if automatic else primary
    newer = reservation("new")
    api.replace_before_write = newer
    core.record_completion(42, "aaa", "codex", {"success": True}, storage=storage)
    current = primary.read_record(42, "codex")
    assert current == newer
    assert api.writes == ["POST"], "Completion must never PATCH the reservation"


@pytest.mark.parametrize("legacy", [False, True])
def test_matching_receipt_is_read_and_completion_retry_is_idempotent(monkeypatch, legacy):
    monkeypatch.setattr(core, "_workflow_attempt_id", lambda: "old")
    api = CommentApi(reservation(legacy=legacy))
    storage = core.PrCommentRunnerStorage(api)
    original = copy.deepcopy(api.reservation)
    first = core.record_completion(
        42, "aaa", "codex", {"success": True}, storage=storage, produced_work=False
    )
    assert storage.read_record(42, "codex")["status"] == "completed"
    second = core.record_completion(
        42, "aaa", "codex", {"success": True}, storage=storage, produced_work=False
    )
    assert first["completed_at"] == second["completed_at"]
    assert first["unproductive_completions"] == second["unproductive_completions"] == 1
    assert api.reservation == original
    assert api.writes == ["POST"], "Identical retry reuses its existing receipt"


def test_receipts_are_found_on_older_cursor_page(monkeypatch):
    monkeypatch.setattr(core, "_workflow_attempt_id", lambda: "old")
    api = CommentApi(reservation())
    storage = core.PrCommentRunnerStorage(api)
    core.record_completion(42, "aaa", "codex", {"success": True}, storage=storage)
    receipt = api.receipts[-1]
    api.receipts.extend({"id": index, "body": "ordinary"} for index in range(3, 103))
    assert storage.read_record(42, "codex")["status"] == "completed"
    assert len(api.reads) >= 2
    receipt["user"] = {"login": "untrusted-contributor"}
    receipt["author_association"] = "NONE"
    assert storage.read_record(42, "codex")["status"] == "pending"


def test_receipt_cannot_invent_a_missing_reservation(monkeypatch):
    monkeypatch.setattr(core, "_workflow_attempt_id", lambda: "old")
    api = CommentApi(reservation())
    api.reservation["body"] = "ordinary comment"
    result = core.record_completion(
        42, "aaa", "codex", {"success": True}, storage=core.PrCommentRunnerStorage(api)
    )
    assert result["completion_recorded"] is False
    assert result["completion_reason"] == "authoritative-reservation-missing"
    assert api.writes == []


def test_long_comment_history_reads_from_tail_and_stops_at_latest_reservation():
    class LongHistoryApi(CommentApi):
        def __init__(self, current):
            super().__init__(current)
            self.reservation["id"] = 601
            self.receipts = [{"id": index, "body": "ordinary"} for index in range(1, 601)]

    api = LongHistoryApi(reservation())
    storage = core.PrCommentRunnerStorage(api)
    assert storage.read_record(42, "codex")["reservation_id"] == "old-reservation"
    assert len(api.reads) == 1, "Cursor tail read must not reread 600 old comments"


def test_deleting_an_older_comment_between_pages_cannot_hide_new_reservation():
    class DeletingApi(CommentApi):
        def request(self, method, path, body=None):
            if method == "POST" and path == "/graphql" and body["variables"]["cursor"]:
                self.receipts = [item for item in self.receipts if item["id"] != 50]
            return super().request(method, path, body)

    api = DeletingApi(reservation())
    api.receipts.extend({"id": index, "body": "ordinary"} for index in range(2, 101))
    api.receipts.append(
        {
            "id": 101,
            "body": core._build_marker(
                42, "codex", reservation("new"), marker_prefix=core.RESERVATION_MARKER_PREFIX
            ),
        }
    )
    api.receipts.extend({"id": index, "body": "ordinary"} for index in range(102, 203))
    assert core.PrCommentRunnerStorage(api).read_record(42, "codex") == reservation("new")
    assert len(api.reads) == 2


def test_unmarked_json_cannot_complete_a_reservation():
    api = CommentApi(reservation())
    completed = {**reservation(), "status": "completed", "completed_at": "2026-09-20T00:01:00Z"}
    api.receipts.append(
        {
            "id": 2,
            "body": json.dumps(
                {
                    "schema": "runner-completion-receipt/v1",
                    "provider": "codex",
                    "reservation_id": "old-reservation",
                    "record": completed,
                }
            ),
        }
    )
    assert core.PrCommentRunnerStorage(api).read_record(42, "codex") == reservation()


def test_completion_retry_updates_its_own_receipt_without_appending():
    api = CommentApi(reservation())
    storage = core.PrCommentRunnerStorage(api)
    completed = {**reservation(), "status": "completed", "completed_at": "2026-09-20T00:01:00Z"}
    storage.write_completion(42, "codex", completed)
    revised = {**completed, "productive": False}
    storage.write_completion(42, "codex", revised)
    assert api.writes == ["POST", "PATCH"]
    assert len(api.receipts) == 1
    assert storage.read_record(42, "codex") == revised


def test_completion_retry_never_edits_an_unmarked_json_comment():
    api = CommentApi(reservation())
    storage = core.PrCommentRunnerStorage(api)
    completed = {**reservation(), "status": "completed", "completed_at": "2026-09-20T00:01:00Z"}
    ordinary = {
        "id": 2,
        "body": json.dumps({"provider": "codex", "reservation_id": "old-reservation"}),
    }
    api.receipts.append(ordinary)
    storage.write_completion(42, "codex", completed)
    assert api.writes == ["POST"]
    assert ordinary["body"].startswith("{")


def test_retry_gets_new_reservation_identity_with_same_head_attempt_and_time(monkeypatch):
    monkeypatch.setattr(core, "_workflow_attempt_id", lambda: "old")
    monkeypatch.setattr(core, "_utc_now", lambda: "2026-09-20T00:00:00Z")
    api = CommentApi(reservation())
    storage = core.PrCommentRunnerStorage(api)
    core.record_completion(
        42, "aaa", "codex", {"success": True}, storage=storage, produced_work=False
    )
    assert core.should_dispatch(42, "aaa", "codex", storage=storage).should_dispatch
    current = storage.read_record(42, "codex")
    assert current["status"] == "pending"
    assert current["reservation_id"] != "old-reservation"
    assert current["workflow_attempt_id"] == "old"
    # An old deployed client may still create/update its legacy marker later.
    late_legacy = {**reservation("older-client"), "status": "completed"}
    api.receipts.append({"id": 999, "body": core._build_marker(42, "codex", late_legacy)})
    assert storage.read_record(42, "codex") == current
