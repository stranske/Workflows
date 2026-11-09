"""Native historical completion cannot become a writer release or a new owner."""

import copy
import hashlib
import io
import json
import zipfile

import pytest
from scripts.reconcile_runner_completion import reconcile
from scripts.runner_lib import core

RUN = 42575919772
HEAD = "f27f30c19b225fcc0c248ef57a31e5df2bc4730c"


class Api:
    repo = "stranske/Orchestrator"

    def __init__(self):
        self.run = {
            "id": RUN,
            "run_attempt": 1,
            "status": "completed",
            "conclusion": "success",
            "event": "workflow_run",
            "name": "Agents Gate Followups",
            "path": ".github/workflows/agents-81-gate-followups.yml",
            "head_sha": "a" * 40,
            "run_started_at": "2026-11-09T06:54:12Z",
            "updated_at": "2026-11-09T07:01:42Z",
        }
        self.worker = {
            "id": 129023995949,
            "name": "Run Codex autofix / Codex (autofix)",
            "status": "completed",
            "conclusion": "success",
            "started_at": "2026-11-09T06:56:15Z",
            "completed_at": "2026-11-09T07:01:23Z",
        }
        self.jobs = [
            self.worker,
            {
                "name": "Record autofix metrics",
                "conclusion": "success",
                "completed_at": "2026-11-09T07:01:41Z",
            },
        ]
        self.metrics = {
            "pr_number": 1286,
            "head_sha_before": HEAD,
            "head_sha_after": HEAD,
            "fix_applied": False,
            "autofix_result": "success",
            "recorded_at": "2026-11-09T07:01:39.303Z",
        }
        self.artifact = {
            "id": 13655900832,
            "name": "agents-autofix-metrics",
            "expired": False,
            "created_at": "2026-11-09T07:01:40Z",
            "workflow_run": {"id": RUN, "head_sha": self.run["head_sha"]},
        }
        self.original = {
            "reservation_id": "8ef42974a041434aa107c701afbc643a",
            "provider": "codex",
            "pr_number": 1286,
            "head_sha": HEAD,
            "key": core._runner_key(1286, HEAD, "codex"),
            "status": "pending",
            "workflow_attempt_id": f"{self.repo}:{RUN}:1",
            "started_at": "2026-11-09T06:55:45Z",
        }
        self.newer = {
            **self.original,
            "reservation_id": "newer",
            "workflow_attempt_id": "new-attempt",
        }
        self.comments = [
            self.comment(1, self.original, core.RESERVATION_MARKER_PREFIX),
            self.comment(2, self.newer, core.RESERVATION_MARKER_PREFIX),
        ]
        self.writes = []
        self.pr = {"state": "closed", "merged": True}
        self.change_before_write = False
        self.race = None
        self.run_reads = 0
        self.reset_archive()

    def reset_archive(self):
        value = io.BytesIO()
        with zipfile.ZipFile(value, "w") as archive:
            archive.writestr("autofix-metrics.ndjson", json.dumps(self.metrics) + "\n")
        self.raw = value.getvalue()
        self.artifact["digest"] = "sha256:" + hashlib.sha256(self.raw).hexdigest()

    def comment(self, identity, record, prefix):
        return {
            "id": identity,
            "body": core._build_marker(1286, "codex", record, marker_prefix=prefix),
            "user": {"login": "stranske"},
            "author_association": "OWNER",
        }

    def archive(self, artifact_id):
        assert artifact_id == self.artifact["id"]
        return self.raw

    def request(self, method, path, body=None):
        if method == "POST":
            assert path == f"/repos/{self.repo}/issues/1286/comments"
            self.writes.append((method, body))
            self.comments.append(
                {
                    "id": 100 + len(self.writes),
                    "body": body["body"],
                    "user": {"login": "stranske"},
                    "author_association": "OWNER",
                }
            )
            return self.comments[-1]
        assert method == "GET"
        if path.endswith(f"/runs/{RUN}"):
            self.run_reads += 1
            if self.change_before_write and self.run_reads > 1:
                return {**self.run, "status": "in_progress"}
            return copy.deepcopy(self.run)
        if "/jobs?" in path:
            return {"total_count": len(self.jobs), "jobs": self.jobs}
        if "/artifacts?" in path:
            return {"total_count": 1, "artifacts": [self.artifact]}
        if "/pulls/1286" in path:
            return self.pr
        if path == "/user":
            if self.race:
                self.comments.append(self.comment(99, self.race, core.COMPLETION_MARKER_PREFIX))
            return {"login": "actual-observer"}
        raise AssertionError(path)


@pytest.fixture
def api(monkeypatch):
    value = Api()
    monkeypatch.setattr(
        core.PrCommentRunnerStorage,
        "_iter_comments",
        lambda self, pr_number, direction="asc": iter(
            copy.deepcopy(
                sorted(self.api.comments, key=lambda row: row["id"], reverse=direction == "desc")
            )
        ),
    )
    return value


def test_real_terminal_input_records_original_time_and_preserves_new_reservation(api):
    before = copy.deepcopy(api.comments[:2])
    proposal = reconcile(api, RUN)
    assert proposal["state"] == "missing-native-completion"
    assert proposal["writes"] == 0
    assert api.writes == []
    result = reconcile(api, RUN, apply=True)
    assert result["writes"] == 1
    record = result["record"]
    assert record["workflow_attempt_id"] == f"{api.repo}:{RUN}:1"
    assert record["completed_at"] == api.worker["completed_at"]
    assert record["productive"] is False
    assert record["completion_incomplete"] is True
    assert record["reconciliation"]["observer"] == "actual-observer"
    assert api.comments[:2] == before
    assert core.PrCommentRunnerStorage(api).read_record(1286, "codex") == api.newer
    replay = reconcile(api, RUN, apply=True)
    assert replay["writes"] == 0
    assert replay["record"] == record
    assert len(api.writes) == 1


@pytest.mark.parametrize(
    "key,value",
    [
        ("status", "in_progress"),
        ("conclusion", "cancelled"),
        ("event", "pull_request"),
        ("name", "untrusted"),
        ("path", "other.yml"),
    ],
)
def test_nonterminal_or_other_workflow_cannot_acknowledge(api, key, value):
    api.run[key] = value
    with pytest.raises(ValueError, match="terminal native"):
        reconcile(api, RUN, apply=True)
    assert not api.writes


@pytest.mark.parametrize(
    "change", ["digest", "attempt", "head", "time", "open", "measurement", "worker"]
)
def test_missing_or_mismatched_native_evidence_preserves_reservation(api, change):
    if change == "digest":
        api.artifact["digest"] = "sha256:" + "0" * 64
    elif change == "attempt":
        api.run["run_attempt"] = 2
    elif change == "head":
        api.artifact["workflow_run"]["head_sha"] = "b" * 40
    elif change == "time":
        api.artifact["created_at"] = "2026-11-08T07:01:40Z"
    elif change == "open":
        api.pr = {"state": "open", "merged": False}
    elif change == "measurement":
        api.metrics["fix_applied"] = True
        api.reset_archive()
    else:
        api.worker["conclusion"] = "cancelled"
    with pytest.raises(ValueError):
        reconcile(api, RUN, apply=True)
    assert not api.writes


def test_rerun_started_between_observation_and_write_cannot_publish(api):
    api.change_before_write = True
    with pytest.raises(ValueError, match="changed before"):
        reconcile(api, RUN, apply=True)
    assert not api.writes


def test_racing_original_receipt_is_reused_immutably(api):
    record = reconcile(api, RUN)["record"]
    record["reconciliation"]["observer"] = "first-observer"
    api.race = {
        "schema": "runner-completion-receipt/v1",
        "provider": "codex",
        "reservation_id": record["reservation_id"],
        "record": record,
    }
    result = reconcile(api, RUN, apply=True)
    assert result["writes"] == 0
    assert result["record"] == record
    assert not api.writes


def test_retry_finds_old_receipt_beyond_a_newer_reservation(api):
    result = reconcile(api, RUN, apply=True)
    api.comments.append(
        api.comment(200, {**api.newer, "reservation_id": "newest"}, core.RESERVATION_MARKER_PREFIX)
    )
    storage = core.PrCommentRunnerStorage(api)
    assert storage.write_completion(1286, "codex", result["record"], immutable=True) is False
    assert len(api.writes) == 1
