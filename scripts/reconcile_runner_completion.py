"""Recover terminal autofix evidence on merged PRs without impersonating its run.

Normal live completion remains record-completion in the owning workflow. This
bounded observer repairs historical acknowledgments only; it cannot release an
open PR's writer or manufacture a reservation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import re
import subprocess
import zipfile

from scripts.runner_lib import core


class GhApi:
    def __init__(self, repo):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise ValueError("invalid repository")
        if repo.casefold() == "stranske/collab-admin":
            raise ValueError("repository excluded by owner")
        self.repo = repo

    def request(self, method, path, body=None):
        args = ["gh", "api", "--method", method, path.lstrip("/")]
        if body is not None:
            args += ["--input", "-"]
        result = subprocess.run(
            args,
            input=json.dumps(body) if body is not None else None,
            capture_output=True,
            text=True,
            timeout=45,
        )
        if result.returncode:
            raise RuntimeError(f"GitHub {method} {path} failed; evidence unavailable")
        return json.loads(result.stdout) if result.stdout else None

    def archive(self, artifact_id):
        result = subprocess.run(
            ["gh", "api", f"repos/{self.repo}/actions/artifacts/{artifact_id}/zip"],
            capture_output=True,
            timeout=45,
        )
        if result.returncode or len(result.stdout) > 65536:
            raise RuntimeError("native metrics archive unavailable or exceeds bound")
        return result.stdout


def timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp lacks timezone")
    return parsed


def _inventory(api, path, key):
    value = api.request("GET", path + "?per_page=100")
    if value.get("total_count") != len(value.get(key, [])):
        raise ValueError(f"incomplete {key} inventory")
    return value[key]


def reconcile(api, run_id, *, apply=False):
    if api.repo.casefold() == "stranske/collab-admin":
        raise ValueError("repository excluded by owner")
    prefix = f"/repos/{api.repo}"
    run_path = f"{prefix}/actions/runs/{int(run_id)}"
    run = api.request("GET", run_path)
    if (
        run.get("id") != run_id
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("event") != "workflow_run"
        or run.get("path") != ".github/workflows/agents-81-gate-followups.yml"
        or run.get("name") != "Agents Gate Followups"
    ):
        raise ValueError("not a successful terminal native autofix workflow")
    attempt = run["run_attempt"]
    jobs = _inventory(api, f"{run_path}/attempts/{attempt}/jobs", "jobs")
    workers = []
    for job in jobs:
        match = re.fullmatch(r"Run ([A-Za-z]+) autofix(?: /.+)?", job.get("name", ""))
        if match and job.get("conclusion") != "skipped":
            provider = core._validate_provider(match[1].lower())
            workers.append((provider, job))
    if len(workers) != 1:
        raise ValueError("native autofix worker identity is ambiguous")
    provider, worker = workers[0]
    metrics_jobs = [j for j in jobs if j.get("name") == "Record autofix metrics"]
    if (
        worker.get("status") != "completed"
        or worker.get("conclusion") != "success"
        or len(metrics_jobs) != 1
        or metrics_jobs[0].get("conclusion") != "success"
    ):
        raise ValueError("native worker or metrics is not successfully terminal")
    artifacts = _inventory(api, run_path + "/artifacts", "artifacts")
    candidates = [
        a
        for a in artifacts
        if a.get("name") == "agents-autofix-metrics"
        and not a.get("expired")
        and timestamp(run["run_started_at"])
        <= timestamp(a["created_at"])
        <= timestamp(run["updated_at"])
    ]
    if len(candidates) != 1:
        raise ValueError("native attempt metrics artifact is ambiguous or unavailable")
    artifact = candidates[0]
    if (
        artifact.get("workflow_run", {}).get("id") != run_id
        or artifact.get("workflow_run", {}).get("head_sha") != run["head_sha"]
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", artifact.get("digest", ""))
    ):
        raise ValueError("native metrics artifact binding is invalid")
    raw = api.archive(artifact["id"])
    if "sha256:" + hashlib.sha256(raw).hexdigest() != artifact["digest"]:
        raise ValueError("native metrics archive digest differs")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if (
            len(entries) != 1
            or entries[0].filename != "autofix-metrics.ndjson"
            or entries[0].file_size > 32768
        ):
            raise ValueError("native metrics archive content is invalid")
        lines = archive.read(entries[0]).decode().splitlines()
    if len(lines) != 1:
        raise ValueError("native metrics record is ambiguous")
    metrics = json.loads(lines[0])
    head, observed = metrics.get("head_sha_before", ""), metrics.get("head_sha_after", "")
    if (
        not re.fullmatch(r"[0-9a-f]{40}", head)
        or not re.fullmatch(r"[0-9a-f]{40}", observed)
        or metrics.get("autofix_result") != "success"
        or metrics.get("fix_applied") is not (head != observed)
        or not timestamp(worker["completed_at"])
        <= timestamp(metrics["recorded_at"])
        <= timestamp(metrics_jobs[0]["completed_at"])
    ):
        raise ValueError("native metrics measurement is incomplete or inconsistent")
    pr_number = metrics["pr_number"]
    if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number <= 0:
        raise ValueError("invalid native PR number")
    pr = api.request("GET", f"{prefix}/pulls/{pr_number}")
    if pr.get("state") != "closed" or not pr.get("merged"):
        raise ValueError(
            "historical reconciliation requires an already merged PR; preserve live owner"
        )
    storage = core.PrCommentRunnerStorage(api)
    origin = f"{api.repo}:{run_id}:{attempt}"
    reservation = None
    receipts = []
    for index, comment in enumerate(storage._iter_comments(pr_number, direction="desc")):
        if index >= 1000:
            raise ValueError("native reservation exceeds bounded history")
        if not core._is_trusted_marker_comment(comment):
            continue
        body = comment.get("body")
        receipt = core._extract_record(
            body, pr_number, provider, marker_prefix=core.COMPLETION_MARKER_PREFIX
        )
        if receipt:
            receipts.append(receipt)
        candidate = core._extract_record(
            body, pr_number, provider, marker_prefix=core.RESERVATION_MARKER_PREFIX
        )
        if (
            candidate
            and candidate.get("workflow_attempt_id") == origin
            and candidate.get("head_sha") == head
        ):
            reservation = candidate
            break
    if not reservation or not reservation.get("reservation_id"):
        raise ValueError("matching original native reservation is unavailable")
    if (
        not timestamp(run["run_started_at"])
        <= timestamp(reservation["started_at"])
        <= timestamp(worker["started_at"])
    ):
        raise ValueError("reservation time is outside the native attempt")
    matching = [
        r
        for r in receipts
        if r.get("schema") == "runner-completion-receipt/v1"
        and r.get("reservation_id") == reservation["reservation_id"]
    ]
    if matching:
        existing = matching[0].get("record")
        if (
            not isinstance(existing, dict)
            or existing.get("status") not in core.TERMINAL_STATUSES
            or any(
                existing.get(k) != reservation.get(k)
                for k in [
                    "provider",
                    "pr_number",
                    "reservation_id",
                    "workflow_attempt_id",
                    "head_sha",
                    "key",
                ]
            )
        ):
            raise ValueError("existing native completion receipt binding is invalid")
        return {"state": "already-recorded", "writes": 0, "record": matching[0]["record"]}
    record = {
        **reservation,
        "status": "completed",
        "completed_at": worker["completed_at"],
        "productive": head != observed,
        "observed_head_sha": observed,
        "result": core._compact_runner_result_payload(
            {
                "provider": provider,
                "success": True,
                "summary": "Recovered from authenticated terminal native worker and metrics artifact.",
            }
        ),
        "completion": {"reason": "progressed" if head != observed else "no_progress"},
        "reconciliation": {
            "source_run_id": run_id,
            "source_run_attempt": attempt,
            "source_job_id": worker["id"],
            "artifact_id": artifact["id"],
            "artifact_digest": artifact["digest"],
            "metrics_recorded_at": metrics["recorded_at"],
        },
    }
    if head == observed:
        record["unproductive_completions"] = min(
            core._unproductive_completion_count(reservation) + 1,
            core.UNPRODUCTIVE_COMPLETION_RETRY_LIMIT + 1,
        )
        record["completion_incomplete"] = True
        record["continuation_completions"] = record["unproductive_completions"]
    else:
        record.update(
            unproductive_completions=0, continuation_completions=0, completion_incomplete=False
        )
    if not apply:
        return {"state": "missing-native-completion", "writes": 0, "record": record}
    fresh = api.request("GET", run_path)
    if any(
        fresh.get(k) != run.get(k)
        for k in ["id", "run_attempt", "status", "conclusion", "head_sha", "updated_at"]
    ):
        raise ValueError("native run changed before completion publication")
    actor = api.request("GET", "/user")["login"]
    record["reconciliation"].update(
        observer=actor,
        observed_at=core._utc_now(),
        observer_workflow_attempt=core._workflow_attempt_id(),
    )
    written = storage.write_completion(pr_number, provider, record, immutable=True)
    # Re-read the actual immutable receipt, including if another observer won.
    for comment in storage._iter_comments(pr_number, direction="desc"):
        if not core._is_trusted_marker_comment(comment):
            continue
        receipt = core._extract_record(
            comment.get("body"), pr_number, provider, marker_prefix=core.COMPLETION_MARKER_PREFIX
        )
        if receipt and receipt.get("reservation_id") == reservation["reservation_id"]:
            actual = receipt.get("record")
            if not isinstance(actual, dict) or any(
                actual.get(k) != record.get(k)
                for k in [
                    "workflow_attempt_id",
                    "head_sha",
                    "reservation_id",
                    "completed_at",
                    "status",
                ]
            ):
                raise ValueError("published native completion readback differs")
            return {
                "state": "recorded" if written else "already-recorded",
                "writes": int(written),
                "record": actual,
            }
    raise RuntimeError(
        "native completion publication is uncertain; retry by reading existing evidence"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", action="store_true", help="read-only (the default)")
    args = parser.parse_args()
    if args.apply and args.report:
        parser.error("choose apply or report")
    result = reconcile(GhApi(args.repo), args.run_id, apply=args.apply)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
