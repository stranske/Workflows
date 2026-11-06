#!/usr/bin/env python3
"""Blind, evidence-bound adjudication of every evaluation of one verified PR (shadow program).

The verifier runs two judges from different provider families on purpose and expects them to
disagree at times, so a candidate is never graded by whether its verdict matches one incumbent.
Instead a reasoning model that is neither a candidate nor a production judge reads the PR's plan
(tasks, acceptance criteria), its diff and every evaluation of it -- production judges and
candidates alike, relabelled A, B, C... in a shuffled order -- and rates each evaluation on:

* accuracy: is the verdict supported, and is any load-bearing claim wrong? Every error must quote
  the evaluation's claim and the context or diff text that contradicts it; the quotes are checked
  here, and an error whose quotes cannot be found is discarded (it never counts against anyone);
* rigor: for each task and acceptance criterion, did the evaluation check it against the diff,
  only assert it, or miss it;
* usefulness: is the review specific and evidence-citing enough to compare with another
  evaluator's work (1-5).

The ratings are written into the ledger record and read by ``tools/verifier_shadow_report.py``.
Nothing here posts, labels or promotes.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
import zipfile
import zlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

from tools.verifier_shadow_external import (
    CONTEXT_FILE,
    DIFF_FILE,
    external_candidates,
    gh_is_public,
)
from tools.verifier_shadow_report import (
    ACCEPTED_PIPELINES,
    ListingError,
    gh_artifacts_for_runs,
    gh_download,
)

COMPARISON_FILE = "comparison.json"
ACCURACY = ("accurate", "partly_inaccurate", "inaccurate")
COVERAGE = {"checked": 1.0, "asserted": 0.5, "missed": 0.0}
CALL_TIMEOUT_SECONDS = 600
# a run is adjudicated only if one whole adjudicator call, plus margin, still fits the budget
RUN_RESERVE_SECONDS = CALL_TIMEOUT_SECONDS + 60
MAX_ATTEMPTS = 2
# wait for every candidate's evaluation, but not past the artifact's 7-day life
SETTLE_DAYS = 6
DIFF_CHAR_LIMIT = 400_000

PROMPT = """You are adjudicating several independent evaluations of the same merged pull request.
Evaluators are labelled A, B, C... in a random order; you do not know which model wrote which, and
disagreement between them is expected and is not itself an error. Judge each evaluation on its own
merits against the PR's plan and its diff.

1. From the PR plan below, list every task and acceptance criterion as C1, C2, ... (short text).
2. Decide the verdict the evidence best supports: PASS (every criterion is met by the diff),
   CONCERNS (a criterion is unmet or unproven, or a real defect), FAIL (the change is wrong or
   harmful) or UNVERIFIABLE_INPUT (the supplied input genuinely cannot show whether a criterion
   is met). Explain briefly.
3. For each evaluation:
   - accuracy: "accurate", "partly_inaccurate" (a minor wrong claim, verdict still supported) or
     "inaccurate" (the verdict is not supported, or a load-bearing claim is wrong). For every
     error give "claim" (copied verbatim from that evaluation), "evidence" (copied verbatim from
     the PR plan, context or diff, showing the claim is wrong; for a criterion the evaluation
     wrongly calls met, copy the criterion text) and "why". Errors without verbatim quotes are
     discarded, so copy exactly.
   - verdict_supported: true or false.
   - coverage: for every criterion id, "checked" (verified against the diff or cited evidence),
     "asserted" (said to be met or unmet without evidence) or "missed" (not addressed).
   - usefulness: 1-5. 5 = specific, cites files and lines, separates verified from unverified,
     and its findings could be compared point by point with another reviewer's; 1 = generic or
     unusable.
   - usefulness_reason: one sentence.

Answer with ONLY this JSON object:
{"criteria": [{"id": "C1", "text": "..."}],
 "reference_verdict": "PASS|CONCERNS|FAIL|UNVERIFIABLE_INPUT",
 "reference_reasoning": "...",
 "evaluations": [{"label": "A", "accuracy": "...", "verdict_supported": true,
   "errors": [{"claim": "...", "evidence": "...", "why": "..."}],
   "coverage": [{"id": "C1", "status": "checked"}],
   "usefulness": 4, "usefulness_reason": "..."}]}

=== PR PLAN AND VERIFIER CONTEXT ===
{context}

=== DIFF ===
{diff}

=== EVALUATIONS ===
{evaluations}
"""


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def evaluators_for(record: dict[str, Any], comparison: dict[str, Any]) -> dict[str, dict]:
    """Every usable evaluation of the run: production judges and current-pipeline candidates."""
    found: dict[str, dict] = {}
    for result in comparison.get("results") or []:
        if result.get("error") or not result.get("used_llm") or not result.get("verdict"):
            continue
        key = f"production:{result.get('provider_used')}:{result.get('model')}"
        found[key] = {
            k: result.get(k)
            for k in (
                "verdict",
                "confidence",
                "scores",
                "summary",
                "concerns",
                "files_not_reviewed",
            )
        }
    for entry in record.get("candidates", []):
        if (
            entry.get("pipeline") in ACCEPTED_PIPELINES
            and entry.get("review")
            and entry.get("used_llm")  # the same rule as production: no model call, no rating
            and not entry.get("error")
        ):
            found[f"candidate:{entry['provider']}:{entry['model']}"] = entry["review"]
    return found


def blind(evaluators: dict[str, dict], seed: str) -> list[tuple[str, str, dict]]:
    """(label, key, review) in a shuffled order that is stable for the run."""
    keys = sorted(evaluators)
    random.Random(seed).shuffle(keys)
    return [(chr(ord("A") + i), key, evaluators[key]) for i, key in enumerate(keys)]


def _render(review: dict[str, Any]) -> str:
    concerns = "\n".join(f"  - {c}" for c in review.get("concerns") or []) or "  (none)"
    unreviewed = ", ".join(review.get("files_not_reviewed") or []) or "(none)"
    return (
        f"verdict: {review.get('verdict')}\nconfidence: {review.get('confidence')}\n"
        f"scores: {json.dumps(review.get('scores'))}\nsummary: {review.get('summary')}\n"
        f"concerns:\n{concerns}\nfiles not reviewed: {unreviewed}"
    )


def build_prompt(context: str, diff: str | None, labelled: list[tuple[str, str, dict]]) -> str:
    diff = diff or "(no separate diff file; the full diff, if any, is in the context above)"
    if len(diff) > DIFF_CHAR_LIMIT:
        diff = diff[:DIFF_CHAR_LIMIT] + "\n[diff truncated for adjudication]"
    evaluations = "\n\n".join(
        f"--- Evaluation {label} ---\n{_render(review)}" for label, _, review in labelled
    )
    # one pass: a placeholder that appears inside the PR's own text is left as it is
    values = {"context": context, "diff": diff, "evaluations": evaluations}
    return re.sub(r"\{(context|diff|evaluations)\}", lambda m: values[m.group(1)], PROMPT)


def _json_object(text: str) -> dict[str, Any] | None:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _content(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, list):  # thinking models return blocks
        return "".join(
            b.get("text", "") if isinstance(b, dict) else str(getattr(b, "text", "") or "")
            for b in content
            if not isinstance(b, dict) or b.get("type") in (None, "text")
        )
    return str(content or "")


def validate(
    answer: dict[str, Any],
    labelled: list[tuple[str, str, dict]],
    context: str,
    diff: str | None,
) -> dict[str, Any]:
    """Ratings keyed by evaluator, with every unquoted error discarded and its rating adjusted."""
    source = _norm(context) + " " + _norm(diff or "")
    ids = [str(c.get("id")) for c in answer.get("criteria") or [] if isinstance(c, dict)]
    by_label = {
        str(e.get("label")): e for e in answer.get("evaluations") or [] if isinstance(e, dict)
    }
    ratings: dict[str, dict] = {}
    discarded = 0
    for label, key, review in labelled:
        raw = by_label.get(label)
        if raw is None:
            ratings[key] = {"label": label, "rated": False}
            continue
        own = _norm(_render(review))
        errors = []
        for err in raw.get("errors") or []:
            if not isinstance(err, dict):
                continue
            claim, evidence = _norm(err.get("claim", "")), _norm(err.get("evidence", ""))
            if claim and evidence and claim in own and evidence in source:
                errors.append({k: str(err.get(k, ""))[:600] for k in ("claim", "evidence", "why")})
            else:
                discarded += 1
        accuracy = raw.get("accuracy") if raw.get("accuracy") in ACCURACY else None
        if accuracy in ("inaccurate", "partly_inaccurate") and not errors:
            accuracy = "unsupported"  # a rating against an evaluator must show its evidence
        statuses = {}
        for c in raw.get("coverage") or []:
            status = c.get("status") if isinstance(c, dict) else None
            if not isinstance(status, str) or status not in COVERAGE:
                # dropping it would silently score the criterion "missed" and never retry
                raise ValueError(f"unsupported coverage status: {status!r}")
            statuses[str(c.get("id"))] = status
        coverage = (
            round(sum(COVERAGE[statuses.get(i, "missed")] for i in ids) / len(ids), 3)
            if ids
            else None
        )
        usefulness = raw.get("usefulness")
        ratings[key] = {
            "label": label,
            "rated": True,
            "verdict": review.get("verdict"),
            "accuracy": accuracy,
            "verdict_supported": (
                raw.get("verdict_supported")
                if isinstance(raw.get("verdict_supported"), bool)
                else None
            ),
            "errors": errors,
            "coverage": coverage,
            "coverage_detail": statuses,
            "usefulness": (
                usefulness if isinstance(usefulness, int) and 1 <= usefulness <= 5 else None
            ),
            "usefulness_reason": str(raw.get("usefulness_reason", ""))[:400],
        }
    return {
        "criteria": [
            {"id": str(c.get("id")), "text": str(c.get("text", ""))[:300]}
            for c in answer.get("criteria") or []
            if isinstance(c, dict)
        ],
        "reference_verdict": answer.get("reference_verdict"),
        "reference_reasoning": str(answer.get("reference_reasoning", ""))[:1500],
        "ratings": ratings,
        "discarded_errors": discarded,
    }


def adjudicate(
    record: dict[str, Any],
    context: str,
    diff: str | None,
    comparison: dict[str, Any],
    client: Any,
    adjudicator: dict[str, str],
) -> dict[str, Any]:
    """One adjudication of one run; a failure is recorded, never raised."""
    stamp = datetime.now(UTC).isoformat()
    base = {
        "provider": adjudicator["provider"],
        "model": adjudicator["model"],
        "adjudicated_at": stamp,
        "error": None,
    }
    evaluators = evaluators_for(record, comparison)
    if not any(k.startswith("candidate:") for k in evaluators):
        return {**base, "error": "no candidate review to adjudicate"}
    labelled = blind(evaluators, f"{record.get('repository')}:{record.get('run_id')}")
    try:
        answer = _json_object(_content(client.invoke(build_prompt(context, diff, labelled))))
    except Exception as exc:  # noqa: BLE001 - one run must never stop the others
        return {**base, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    if answer is None:
        return {**base, "error": "adjudicator answer was not a JSON object"}
    try:
        return {**base, **validate(answer, labelled, context, diff)}
    except (TypeError, ValueError, AttributeError, KeyError) as exc:
        return {**base, "error": f"malformed adjudicator answer: {type(exc).__name__}"}


def needs_adjudication(record: dict[str, Any], wanted: list[dict[str, Any]], now: datetime) -> bool:
    """Adjudicate once every EXTERNAL candidate has answered, or when the artifact is about to expire.

    ``wanted`` is the external candidates only: an in-workflow candidate answers inside the
    verifier run, so its entry is final when the record is collected, and waiting for one that is
    missing (a run recorded before it was added, or before its pipeline changed) would hold every
    such run for SETTLE_DAYS for nothing.
    """
    if record.get("semantic_mode") is True:
        return False
    done = record.get("adjudication") or {}
    if done and not done.get("error"):
        return False
    if record.get("adjudication_attempts", 0) >= MAX_ATTEMPTS:
        return False
    current = [c for c in record.get("candidates", []) if c.get("pipeline") in ACCEPTED_PIPELINES]
    if not any(c.get("review") for c in current):
        return False
    answered = {(c.get("provider"), c.get("model")) for c in current}
    if all((c["provider"], c["model"]) in answered for c in wanted):
        return True
    stamp = record.get("recorded_at")
    if not stamp:
        return True
    return now - datetime.fromisoformat(stamp) >= timedelta(days=SETTLE_DAYS)


def read_run(blob: bytes) -> dict[str, Any] | None:
    found: dict[str, str] = {}
    with zipfile.ZipFile(BytesIO(blob)) as archive:
        for name in archive.namelist():
            base = name.rsplit("/", 1)[-1]
            if base in (CONTEXT_FILE, DIFF_FILE, COMPARISON_FILE):
                found[base] = archive.read(name).decode("utf-8", errors="replace")
    if not found.get(CONTEXT_FILE) or not found.get(COMPARISON_FILE):
        return None
    try:
        comparison = json.loads(found[COMPARISON_FILE])
    except ValueError:
        return None
    return {
        "context": found[CONTEXT_FILE],
        "diff": found.get(DIFF_FILE) or None,
        "comparison": comparison if isinstance(comparison, dict) else {},
    }


def make_client(adjudicator: dict[str, str]) -> Any:
    from tools.langchain_client import build_chat_client  # the verifier's own client factory

    info = build_chat_client(
        model=adjudicator["model"],
        provider=adjudicator["provider"],
        timeout=CALL_TIMEOUT_SECONDS,
        max_retries=1,
    )
    if info is None:
        raise RuntimeError("adjudicator client unavailable (missing credential or dependency)")
    return info.client


def adjudicate_ledger(
    ledger: list[dict[str, Any]],
    config: dict[str, Any],
    repos: list[str],
    *,
    since: datetime,
    max_runs: int,
    now: datetime | None = None,
    list_artifacts: Callable[[str, list[str]], list[dict[str, Any]]] = gh_artifacts_for_runs,
    download: Callable[[str, int], bytes] = gh_download,
    is_public: Callable[[str], bool] = gh_is_public,
    client_factory: Callable[[dict[str, str]], Any] = make_client,
    deadline: float | None = None,
    checkpoint: Callable[[], None] | None = None,
) -> dict[str, int]:
    """Adjudicate settled daily runs while enabled; leave retained backlog intact when off."""
    now = now or datetime.now(UTC)
    counts = {
        "disabled": 0,
        "adjudicated": 0,
        "artifacts_seen": 0,
        "listing_failed": 0,
        "failed": 0,
        "skipped_private": 0,
        "unusable": 0,
        "capped": 0,
        "out_of_time": 0,
    }
    if not config.get("enabled"):
        counts["disabled"] = 1
        return counts
    # Only external candidates can still answer after the run; wait for those when enabled.
    wanted = external_candidates(config)
    adjudicator = config["adjudicator"]  # defined once, in config/verifier_shadow.json
    todo = {
        (r.get("repository"), str(r.get("run_id"))): r
        for r in ledger
        if needs_adjudication(r, wanted, now)
    }
    client = None
    for repo in repos:
        if not any(k[0] == repo for k in todo):
            continue
        if not is_public(repo):
            counts["skipped_private"] += 1
            continue
        try:
            artifacts = list_artifacts(repo, [k[1] for k in todo if k[0] == repo])
        except ListingError as exc:
            counts["listing_failed"] += 1
            print(f"{repo}: LISTING FAILED: {exc}")
            continue
        for artifact in artifacts:
            created = datetime.fromisoformat(artifact["created_at"].replace("Z", "+00:00"))
            if artifact.get("expired") or created < since:
                continue
            if not str(artifact.get("name", "")).startswith("comparison-results-"):
                continue
            counts["artifacts_seen"] += 1
            record = todo.get((repo, str(artifact["name"]).rsplit("-", 1)[-1]))
            if record is None:
                continue
            if counts["adjudicated"] + counts["failed"] >= max_runs:
                counts["capped"] += 1
                continue
            if deadline is not None and time.monotonic() + RUN_RESERVE_SECONDS > deadline:
                counts["out_of_time"] += 1
                continue
            try:
                run = read_run(download(repo, int(artifact["id"])))
            except (OSError, ValueError, zipfile.BadZipFile, zlib.error):
                run = None  # a corrupt archive is unusable, never a crash of the whole step
            if run is None:
                counts["unusable"] += 1
                continue
            client = client or client_factory(adjudicator)
            result = adjudicate(
                record, run["context"], run["diff"], run["comparison"], client, adjudicator
            )
            record["adjudication"] = result
            record["adjudication_attempts"] = record.get("adjudication_attempts", 0) + 1
            counts["failed" if result.get("error") else "adjudicated"] += 1
            if checkpoint is not None:
                checkpoint()
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config/verifier_shadow.json"))
    parser.add_argument("--repos", required=True, help="comma separated owner/name list")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--max-runs", type=int, default=20)
    parser.add_argument("--budget-seconds", type=float, default=None)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text())
    ledger = json.loads(args.ledger.read_text()) if args.ledger.exists() else []
    repos = [r.strip() for r in args.repos.split(",") if r.strip()]

    def save() -> None:
        tmp = args.ledger.with_name(args.ledger.name + ".tmp")
        tmp.write_text(json.dumps(ledger, indent=1) + "\n")
        tmp.replace(args.ledger)

    started = time.monotonic()
    since = datetime.now(UTC) - timedelta(days=args.days)
    counts = adjudicate_ledger(
        ledger,
        config,
        repos,
        since=since,
        max_runs=args.max_runs,
        list_artifacts=gh_artifacts_for_runs,
        download=gh_download,
        is_public=gh_is_public,
        client_factory=make_client,
        deadline=None if args.budget_seconds is None else started + args.budget_seconds,
        checkpoint=save,
    )
    save()
    print(f"adjudication: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
