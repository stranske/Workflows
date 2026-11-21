"""Describe a native Health 44 snapshot after a successful upload."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path

REPOSITORY = "stranske/Workflows"
DIRECT = ".github/workflows/health-44-gate-branch-protection.yml"
SWEEP = ".github/workflows/health-40-sweep.yml"
POINTER_FILENAME = "health44-snapshot-pointer.json"


def _positive_number(value: str) -> int:
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise ValueError("expected a positive integer from the runner or upload")
    return int(value)


def _reject_non_json_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def build_pointer(env: Mapping[str, str], snapshots: Path) -> dict:
    caller_ref = env["GITHUB_WORKFLOW_REF"]
    caller, _, ref = caller_ref.partition("@")
    event = env["GITHUB_EVENT_NAME"]
    direct = caller == f"{REPOSITORY}/{DIRECT}"
    sweep = caller == f"{REPOSITORY}/{SWEEP}"
    pr = (
        direct
        and event == "pull_request"
        and env.get("SNAPSHOT_HEAD_REPOSITORY") == REPOSITORY
        and re.fullmatch(r"refs/pull/[1-9][0-9]*/merge", ref)
    )
    default_branch = ref == "refs/heads/main" and (
        (direct and event == "workflow_dispatch")
        or (sweep and event in {"schedule", "workflow_dispatch"})
    )
    if env["GITHUB_REPOSITORY"] != REPOSITORY or not (pr or default_branch):
        raise ValueError("unexpected caller, event or repository")

    workflow_sha = env["GITHUB_WORKFLOW_SHA"]
    digest = env["SNAPSHOT_ARTIFACT_DIGEST"].removeprefix("sha256:").lower()
    if not re.fullmatch(r"[0-9a-f]{40}", workflow_sha) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("missing workflow revision or artifact digest")

    files = {}
    for name in ("enforcement.json", "verification.json"):
        path = snapshots / name
        if not path.is_file():
            continue
        contents = path.read_bytes()
        if not isinstance(json.loads(contents, parse_constant=_reject_non_json_constant), dict):
            raise ValueError(f"invalid protection snapshot: {name}")
        files[name] = hashlib.sha256(contents).hexdigest()
    if not files:
        raise ValueError("no current protection snapshot")

    run_id = _positive_number(env["GITHUB_RUN_ID"])
    return {
        "schema": "health44-snapshot-pointer/v1",
        "repository": REPOSITORY,
        "repository_id": _positive_number(env["GITHUB_REPOSITORY_ID"]),
        "run_id": run_id,
        "run_attempt": _positive_number(env["GITHUB_RUN_ATTEMPT"]),
        "caller_workflow_ref": caller_ref,
        "producer_workflow": DIRECT,
        # Health 40 calls the local workflow by relative path at the same commit.
        "workflow_sha": workflow_sha,
        "artifact": {
            "id": _positive_number(env["SNAPSHOT_ARTIFACT_ID"]),
            "name": f"gate-branch-protection-{run_id}",
            "sha256": digest,
        },
        "files": files,
    }


def main() -> int:
    try:
        pointer = build_pointer(os.environ, Path(os.environ["SNAPSHOT_DIR"]))
    except (KeyError, OSError, ValueError) as exc:
        print(f"[summary] Snapshot pointer skipped: {exc}", flush=True)
        return 0

    path = Path(os.environ["RUNNER_TEMP"]) / POINTER_FILENAME
    path.write_text(json.dumps(pointer, sort_keys=True) + "\n", encoding="utf-8")
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write("ready=true\n")
    print(
        f"[summary] Snapshot pointer prepared for artifact {pointer['artifact']['id']}", flush=True
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
