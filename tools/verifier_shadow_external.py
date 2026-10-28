#!/usr/bin/env python3
"""Judge the EXTERNAL shadow candidates (Muse API, Cursor CLI) from saved verifier inputs.

Consumer repositories run the verifier with OpenAI and Anthropic credentials only, so a candidate
that needs another credential (``runner: external`` in config/verifier_shadow.json) cannot judge
inside that run. The run's ``comparison-results-<id>`` artifact keeps the exact context and diff the
production judges saw for seven days, so this tool, run by the daily report job, replays them: the
same production prompt, the same pull request, a different judge. Each verdict is appended to the
ledger record of that run, so the report scores it with the same pre-registered criteria as any
other candidate. Nothing here blocks or promotes anything.

Safeguards: a repository must be public (the Muse API and any contributor-tier terms may train on
prompts), each run judges at most ``--max-runs`` new pull requests (a spend bound), and a verdict that
already exists in the ledger is never requested twice.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

from tools.verifier_shadow_report import gh_download, gh_list_artifacts

CONTEXT_FILE, DIFF_FILE = "verifier-context.md", "verifier-pr-diff.patch"
SHADOW_FILE = "verifier-shadow.json"


def external_candidates(config: dict[str, Any]) -> list[dict[str, Any]]:
    if not config.get("enabled"):
        return []
    return [c for c in config.get("candidates", []) if c.get("runner") == "external"]


def make_judge(candidate: dict[str, Any]) -> Any:
    """The screen's judge for an external candidate (imported lazily: it pulls in pr_verifier)."""
    from tools.run_judge_backend_screen import CursorCliJudge, MuseApiJudge

    if candidate["provider"] == "muse-api":
        return MuseApiJudge(model=candidate["model"])
    if candidate["provider"] == "cursor-cli":
        return CursorCliJudge(model=None if candidate["model"] == "default" else candidate["model"])
    raise ValueError(f"unknown external provider: {candidate['provider']}")


def build_prompt(context: str, diff: str | None) -> str:
    from scripts.langchain import pr_verifier

    return pr_verifier._prepare_prompt(context, diff)


def entry_for(candidate: dict[str, Any], judge: Any, prompt: str) -> dict[str, Any]:
    """One candidate entry in the shadow-record shape; a failure is data, never an exception."""
    entry: dict[str, Any] = {
        "provider": candidate["provider"],
        "model": candidate["model"],
        "verdict": None,
        "used_llm": False,
        "error": None,
        "latency_s": None,
        "confidence": None,
        "concerns": None,
        "external": True,
        "pipeline": "external-single-prompt/v1",
    }
    try:
        outcome = judge.invoke(prompt)
    except Exception as exc:  # noqa: BLE001 - one judge must never stop the others
        entry["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return entry
    payload = outcome.payload or {}
    entry["latency_s"] = round(outcome.latency_ms / 1000, 2)
    entry["error"] = outcome.error
    entry["verdict"] = payload.get("verdict")
    entry["used_llm"] = bool(payload.get("verdict"))
    entry["confidence"] = payload.get("confidence")
    entry["concerns"] = len(payload.get("concerns") or []) if payload else None
    return entry


def run_external(
    candidates: list[dict[str, Any]],
    prompt: str,
    *,
    judge_factory: Callable[[dict[str, Any]], Any] = make_judge,
) -> list[dict[str, Any]]:
    """All external candidates judge the same prompt at once; entries keep config order."""
    if not candidates:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(candidates)) as pool:
        futures = [pool.submit(entry_for, c, judge_factory(c), prompt) for c in candidates]
        return [f.result() for f in futures]


def read_inputs(blob: bytes) -> dict[str, Any] | None:
    """Context, diff and shadow metadata from a comparison-results archive, or None if unusable."""
    found: dict[str, str] = {}
    with zipfile.ZipFile(BytesIO(blob)) as archive:
        for name in archive.namelist():
            base = name.rsplit("/", 1)[-1]
            if base in (CONTEXT_FILE, DIFF_FILE, SHADOW_FILE):
                found[base] = archive.read(name).decode("utf-8", errors="replace")
    if not found.get(CONTEXT_FILE) or SHADOW_FILE not in found:
        return None
    try:
        meta = json.loads(found[SHADOW_FILE])
    except ValueError:
        return None
    return {"context": found[CONTEXT_FILE], "diff": found.get(DIFF_FILE) or None, "meta": meta}


def missing_candidates(
    record: dict[str, Any], wanted: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    have = {(c.get("provider"), c.get("model")) for c in record.get("candidates", [])}
    return [c for c in wanted if (c["provider"], c["model"]) not in have]


def collect_external(
    ledger: list[dict[str, Any]],
    config: dict[str, Any],
    repos: list[str],
    *,
    since: datetime,
    max_runs: int,
    list_artifacts: Callable[[str], list[dict[str, Any]]] = gh_list_artifacts,
    download: Callable[[str, int], bytes] = gh_download,
    is_public: Callable[[str], bool],
    judge_factory: Callable[[dict[str, Any]], Any] = make_judge,
) -> dict[str, int]:
    """Add external verdicts to ledger records in place; returns counts of what happened."""
    wanted = external_candidates(config)
    counts = {"judged": 0, "skipped_private": 0, "unusable": 0, "capped": 0}
    by_key = {(r.get("repository"), r.get("run_id")): r for r in ledger}
    for repo in repos:
        if not wanted or not any(
            missing_candidates(r, wanted) for k, r in by_key.items() if k[0] == repo
        ):
            continue
        if not is_public(repo):
            counts["skipped_private"] += 1
            continue
        for artifact in list_artifacts(repo):
            created = datetime.fromisoformat(artifact["created_at"].replace("Z", "+00:00"))
            if artifact.get("expired") or created < since:
                continue
            if not str(artifact.get("name", "")).startswith("comparison-results-"):
                continue
            run_id = str(artifact["name"]).rsplit("-", 1)[-1]
            record = by_key.get((repo, run_id)) or by_key.get(
                (repo, int(run_id) if run_id.isdigit() else run_id)
            )
            if record is None:
                continue
            todo = missing_candidates(record, wanted)
            if not todo:
                continue
            if counts["judged"] >= max_runs:
                counts["capped"] += 1
                continue
            inputs = read_inputs(download(repo, int(artifact["id"])))
            if inputs is None:
                counts["unusable"] += 1
                continue
            prompt = build_prompt(inputs["context"], inputs["diff"])
            record.setdefault("candidates", []).extend(
                run_external(todo, prompt, judge_factory=judge_factory)
            )
            counts["judged"] += 1
    return counts


def gh_is_public(repo: str) -> bool:
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}", "--jq", ".private"],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip() == "false"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config/verifier_shadow.json"))
    parser.add_argument("--repos", required=True, help="comma separated owner/name list")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--max-runs", type=int, default=25)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text())
    ledger = json.loads(args.ledger.read_text()) if args.ledger.exists() else []
    repos = [r.strip() for r in args.repos.split(",") if r.strip()]
    counts = collect_external(
        ledger,
        config,
        repos,
        since=datetime.now(UTC) - timedelta(days=args.days),
        max_runs=args.max_runs,
        is_public=gh_is_public,
    )
    args.ledger.write_text(json.dumps(ledger, indent=1) + "\n")
    print(f"external shadow: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
