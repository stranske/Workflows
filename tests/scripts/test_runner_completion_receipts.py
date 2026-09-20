"""Adversarial API interleavings for authoritative completion persistence."""

import copy

import pytest
from scripts.runner_lib import core


class CommentApi:
    repo = "owner/repo"

    def __init__(self, reservation):
        self.reservation = {"id": 1, "body": core._build_marker(42, "codex", reservation)}
        self.receipts = []
        self.replace_before_write = None
        self.writes = []

    def request(self, method, path, body=None):
        if method == "GET":
            return copy.deepcopy(list(reversed(self.receipts)) + [self.reservation])
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
    assert api.writes == ["POST", "POST"]


def test_receipts_are_found_on_later_ascending_pages(monkeypatch):
    monkeypatch.setattr(core, "_workflow_attempt_id", lambda: "old")

    class PaginatedApi(CommentApi):
        def request(self, method, path, body=None):
            if method != "GET":
                return super().request(method, path, body)
            if path.endswith("page=1"):
                return [copy.deepcopy(self.reservation)] + [
                    {"id": index + 100, "body": "ordinary"} for index in range(99)
                ]
            return copy.deepcopy(self.receipts)

    api = PaginatedApi(reservation())
    storage = core.PrCommentRunnerStorage(api)
    core.record_completion(42, "aaa", "codex", {"success": True}, storage=storage)
    assert storage.read_record(42, "codex")["status"] == "completed"
    api.receipts[-1]["user"] = {"login": "untrusted-contributor"}
    api.receipts[-1]["author_association"] = "NONE"
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
