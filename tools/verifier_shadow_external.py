#!/usr/bin/env python3
"""Judge the EXTERNAL shadow candidates (Muse API, Cursor CLI) from saved verifier inputs.

Consumer repositories run the verifier with OpenAI and Anthropic credentials only, so a candidate
that needs another credential (``runner: external`` in config/verifier_shadow.json) cannot judge
inside that run. The run's ``comparison-results-<id>`` artifact keeps the exact context and diff the
production judges saw for seven days, so this tool, run by the daily report job, replays them: the
same production per-slot path (chunking, response parsing, coverage floor), the same pull request, a different judge. Each verdict is appended to the
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
import time
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from scripts.langchain.verifier_shadow import PIPELINE, review_of
from tools.run_judge_backend_screen import JUDGE_TIMEOUT_SECONDS
from tools.verifier_shadow_report import gh_download, gh_list_artifacts

# One run may make several sequential judge calls (production chunks a large input, up to
# MAX_REVIEW_CHUNKS). It gets this much wall-clock: JudgeChatClient refuses any call that could not
# finish inside it, and collect_external starts a run only if all of it still fits the job budget.
RUN_BUDGET_SECONDS = 2 * JUDGE_TIMEOUT_SECONDS + 60
RUN_RESERVE_SECONDS = RUN_BUDGET_SECONDS
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


class JudgeChatClient:
    """Gives a screen judge the ``invoke`` surface the production verifier path expects."""

    def __init__(self, judge: Any, run_deadline: float | None = None) -> None:
        self.judge, self.run_deadline = judge, run_deadline

    def invoke(self, prompt: str, config: Any = None, **_: Any) -> Any:
        if (
            self.run_deadline is not None
            and time.monotonic() + JUDGE_TIMEOUT_SECONDS > self.run_deadline
        ):
            raise RuntimeError("run time budget used up before another judge call could finish")
        outcome = self.judge.invoke(prompt)
        if outcome.text is None:
            raise RuntimeError(outcome.error or "judge returned no text")
        return SimpleNamespace(content=outcome.text)


def evaluate_like_production(
    judge: Any,
    name: str,
    model: str,
    context: str,
    diff: str | None,
    run_deadline: float | None = None,
) -> Any:
    """One production compare slot (chunking, response parsing, coverage floor) with an outside judge.

    The production path pre-checks input capacity, but only for OpenAI, Anthropic and GitHub Models
    clients (fail closed, registry owned). That size check is skipped here, in this report job only;
    production code is untouched. Everything that decides the verdict is the production code.
    """
    from scripts.langchain import pr_verifier as pv

    runner = pv.ComparisonRunner(
        context=context,
        diff=diff,
        prompt=pv._prepare_prompt(context, diff),
        clients=[],
        coverage=pv.prompt_coverage(context, diff),
    )
    return runner.run_single(JudgeChatClient(judge, run_deadline), name, model)


def capacity_check_skipped() -> Any:
    """Patch the size pre-check once around ALL judges (per-thread patching would race on restore)."""
    from unittest import mock

    from scripts.langchain import pr_verifier as pv

    return mock.patch.multiple(
        pv,
        _prepare_capacity_client=lambda c: c,
        _legacy_capacity_route=lambda c: True,
        _preflight_input_capacity=lambda *a, **k: None,
    )


def excerpt(text: str, edge: int = 300) -> str:
    """Head and tail of a model answer: an agent judge narrates first, so its JSON sits at the end."""
    if len(text) <= 2 * edge:
        return text
    return f"{text[:edge]} [... {len(text) - 2 * edge} chars ...] {text[-edge:]}"


def entry_for(
    candidate: dict[str, Any], judge: Any, context: str, diff: str | None
) -> dict[str, Any]:
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
        "capacity_preflight": "skipped",
        "pipeline": PIPELINE,
    }
    started = time.perf_counter()
    try:
        result = evaluate_like_production(
            judge,
            candidate["provider"],
            candidate["model"],
            context,
            diff,
            run_deadline=time.monotonic() + RUN_BUDGET_SECONDS,
        )
        entry.update(
            {
                "verdict": getattr(result, "verdict", None),
                "used_llm": bool(getattr(result, "used_llm", False)),
                "error": getattr(result, "error", None),
                "confidence": getattr(result, "confidence", None),
                "concerns": len(getattr(result, "concerns", []) or []),
            }
        )
        if not entry["error"] and entry["verdict"] is not None:
            entry["review"] = review_of(result)
        if entry["error"]:
            entry["raw_excerpt"] = excerpt(str(getattr(result, "raw_content", "") or ""))
    except Exception as exc:  # noqa: BLE001 - one judge must never stop the others
        entry["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    entry["latency_s"] = round(time.perf_counter() - started, 2)
    return entry


def run_external(
    candidates: list[dict[str, Any]],
    context: str,
    diff: str | None,
    *,
    judge_factory: Callable[[dict[str, Any]], Any] = make_judge,
) -> list[dict[str, Any]]:
    """All external candidates judge the same prompt at once; entries keep config order."""
    if not candidates:
        return []
    with (
        capacity_check_skipped(),
        concurrent.futures.ThreadPoolExecutor(max_workers=len(candidates)) as pool,
    ):
        futures = [pool.submit(entry_for, c, judge_factory(c), context, diff) for c in candidates]
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
    have = {
        (c.get("provider"), c.get("model"))
        for c in record.get("candidates", [])
        if c.get("pipeline") == PIPELINE  # an entry from an earlier pipeline is judged again
    }
    return [c for c in wanted if (c["provider"], c["model"]) not in have]


def chosen_runs(ledger: list[dict[str, Any]]) -> set[tuple[Any, str]]:
    """One run per (repository, PR): the one already judged externally, else the newest.

    A PR is verified again on every push, so it can have several runs; the paid external judges
    take exactly one of them, and the choice stays put on later daily jobs because a judged run
    is always preferred. Records without a PR number stand for themselves.
    """
    groups: dict[tuple[Any, str], list[dict[str, Any]]] = {}
    for record in ledger:
        pr = record.get("pr_number")
        who = str(pr) if pr not in (None, "") else f"run:{record.get('run_id')}"
        groups.setdefault((record.get("repository"), who), []).append(record)

    def newest(record: dict[str, Any]) -> int:
        run_id = str(record.get("run_id", ""))
        return int(run_id) if run_id.isdigit() else -1

    chosen = set()
    for records in groups.values():
        judged = [r for r in records if any(c.get("external") for c in r.get("candidates", []))]
        pick = max(judged or records, key=newest)
        chosen.add((pick.get("repository"), str(pick.get("run_id"))))
    return chosen


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
    deadline: float | None = None,
    checkpoint: Callable[[], None] | None = None,
) -> dict[str, int]:
    """Add external verdicts to ledger records in place; returns counts of what happened.

    ``deadline`` is a ``time.monotonic()`` instant: no new run starts unless a whole judge
    timeout (``RUN_RESERVE_SECONDS``) still fits before it. ``checkpoint`` is called after every
    judged run so completed paid judgments survive a cancelled job.
    """
    wanted = external_candidates(config)
    counts = {
        "judged": 0,
        "skipped_private": 0,
        "unusable": 0,
        "capped": 0,
        "semantic": 0,
        "out_of_time": 0,
    }
    by_key = {(r.get("repository"), str(r.get("run_id"))): r for r in ledger}
    chosen = chosen_runs(ledger)
    for repo in repos:
        if not wanted or not any(
            missing_candidates(r, wanted) for k, r in by_key.items() if k[0] == repo and k in chosen
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
            if (repo, run_id) not in chosen:
                continue
            record = by_key.get((repo, run_id))
            if record is None:
                continue
            todo = missing_candidates(record, wanted)
            if not todo:
                continue
            if counts["judged"] >= max_runs:
                counts["capped"] += 1
                continue
            if deadline is not None and time.monotonic() + RUN_RESERVE_SECONDS > deadline:
                counts["out_of_time"] += 1
                continue
            inputs = read_inputs(download(repo, int(artifact["id"])))
            if inputs is None:
                counts["unusable"] += 1
                continue
            if inputs["meta"].get("semantic_mode") is True:
                # production judged this run with the semantic package matrix; a legacy-path
                # candidate verdict would not be comparable, so it is neither requested nor paired
                counts["semantic"] += 1
                continue
            record.setdefault("candidates", []).extend(
                run_external(todo, inputs["context"], inputs["diff"], judge_factory=judge_factory)
            )
            counts["judged"] += 1
            if checkpoint is not None:
                checkpoint()
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
    parser.add_argument(
        "--budget-seconds", type=float, default=None, help="stop starting runs near this limit"
    )
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text())
    ledger = json.loads(args.ledger.read_text()) if args.ledger.exists() else []
    repos = [r.strip() for r in args.repos.split(",") if r.strip()]

    def save() -> None:
        tmp = args.ledger.with_name(args.ledger.name + ".tmp")
        tmp.write_text(json.dumps(ledger, indent=1) + "\n")
        tmp.replace(args.ledger)

    started = time.monotonic()
    counts = collect_external(
        ledger,
        config,
        repos,
        since=datetime.now(UTC) - timedelta(days=args.days),
        max_runs=args.max_runs,
        list_artifacts=gh_list_artifacts,
        download=gh_download,
        is_public=gh_is_public,
        judge_factory=make_judge,
        deadline=None if args.budget_seconds is None else started + args.budget_seconds,
        checkpoint=save,
    )
    save()
    print(f"external shadow: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
