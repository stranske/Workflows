#!/usr/bin/env python3
"""Grow the verifier evaluation corpus from realized PR outcomes.

Move 2 of the self-feeding verifier-model promotion system (stranske/Workflows#2819).

The evaluation corpus (``config/model_eval_pilot.json``) is frozen, versioned, and
its expected verdicts must be trustworthy. It was hand-built and never grows, so
the approval benchmark stays perpetually under its 75-case minimum and no model is
ever promoted. This harvester grows it from outcomes the world has *already*
adjudicated by merging or reverting a PR:

  - A PR that merged cleanly and stayed stable for ``stability_days`` with no
    revert and no verifier follow-up → the verifier's PASS was borne out →
    high-confidence ``clean-pass`` (expected_verdict=PASS).
  - A PR that was reverted within the window → high-confidence
    ``regression-after-merge`` (expected_verdict=NON_PASS).
  - A PR with a resolved verifier-driven follow-up → high-confidence
    ``follow-up-required`` (expected_verdict=NON_PASS).

High-confidence cases auto-promote into the frozen corpus (bumping its version).
Everything ambiguous (too-recent to be stable, unresolved follow-up) goes to an
FYI-only staging file that AUTO-EXPIRES after ``staging_expiry_days`` so no
adjudication backlog can accumulate — a human never has to act on it.

The semantically-subtle NON_PASS categories the policy also requires
(``stale-verifier-claim``, ``review-thread-debt``, ``missing-acceptance-criterion``)
cannot be labeled from realized outcomes and remain owner-sourced; this tool never
fabricates them.

``--from-json`` reads pre-fetched records (used by tests and for a deterministic
CI run); without it the tool fetches live PR data via ``gh``.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS_PATH = _REPO_ROOT / "config" / "model_eval_pilot.json"
DEFAULT_STAGING_PATH = _REPO_ROOT / "config" / "model_eval_corpus_staging.json"
DEFAULT_POLICY_PATH = _REPO_ROOT / "config" / "model_selection_policy.json"
DEFAULT_PROFILE = "verifier-balanced"

# Categories this harvester can label from realized outcomes. The other policy
# categories require human judgment and are intentionally never produced here.
CATEGORY_CLEAN_PASS = "clean-pass"
CATEGORY_REGRESSION = "regression-after-merge"
CATEGORY_FOLLOW_UP = "follow-up-required"


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def classify(
    record: dict[str, Any], *, now: datetime, stability_days: int
) -> dict[str, Any] | None:
    """Label a single PR record from its realized outcome.

    Returns ``{expected_verdict, category, confidence}`` or ``None`` when the PR
    carries no usable verifier signal (e.g. never merged).
    """
    if not record.get("merged"):
        return None
    merged_at = _parse_ts(record.get("merged_at"))
    if merged_at is None:
        return None

    if record.get("reverted"):
        return {
            "expected_verdict": "NON_PASS",
            "category": CATEGORY_REGRESSION,
            "confidence": "high",
        }

    if record.get("verifier_followup"):
        confidence = "high" if record.get("followup_resolved") else "low"
        return {
            "expected_verdict": "NON_PASS",
            "category": CATEGORY_FOLLOW_UP,
            "confidence": confidence,
        }

    age_days = (now - merged_at).total_seconds() / 86400.0
    confidence = "high" if age_days >= stability_days else "low"
    return {
        "expected_verdict": "PASS",
        "category": CATEGORY_CLEAN_PASS,
        "confidence": confidence,
    }


def _case_id(record: dict[str, Any]) -> str:
    repo = str(record.get("repo", "")).split("/")[-1].lower()
    return f"{repo}-{record.get('pr')}"


def to_case(record: dict[str, Any], label: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    return {
        "case_id": _case_id(record),
        "repo": record.get("repo"),
        "pr": record.get("pr"),
        "expected_verdict": label["expected_verdict"],
        "category": label["category"],
        "provenance": "harvested",
        "harvested_at": now.date().isoformat(),
    }


def partition(
    records: Iterable[dict[str, Any]], *, now: datetime, stability_days: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split records into high-confidence promotions and low-confidence staging."""
    promote: list[dict[str, Any]] = []
    stage: list[dict[str, Any]] = []
    for record in records:
        label = classify(record, now=now, stability_days=stability_days)
        if label is None:
            continue
        case = to_case(record, label, now=now)
        if label["confidence"] == "high":
            promote.append(case)
        else:
            stage.append(case)
    return promote, stage


def _corpus_keys(cases: Iterable[dict[str, Any]]) -> set[tuple[Any, Any]]:
    return {(c.get("repo"), c.get("pr")) for c in cases}


def _bump_version(version: str | None, added: int) -> str:
    """Bump the trailing ``+N`` harvest counter on the corpus version string."""
    base = version or "unversioned"
    if "+harvest" in base:
        head, _, tail = base.partition("+harvest")
        try:
            prior = int(tail)
        except ValueError:
            prior = 0
        return f"{head}+harvest{prior + added}"
    return f"{base}+harvest{added}"


def grow_corpus(
    corpus: dict[str, Any],
    promote: list[dict[str, Any]],
    *,
    max_size: int,
    category_caps: dict[str, int] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Append new high-confidence cases to the corpus.

    Dedups by repo+pr, respects ``max_size``, and honours per-category caps so an
    easy-to-source category (``clean-pass``) cannot flood the corpus and starve
    the balance the approval stage needs (10 per required category).
    """
    caps = category_caps or {}
    cases = list(corpus.get("cases", []))
    existing = _corpus_keys(cases)
    counts: dict[str, int] = {}
    for case in cases:
        counts[case.get("category", "")] = counts.get(case.get("category", ""), 0) + 1
    added: list[dict[str, Any]] = []
    for case in promote:
        key = (case.get("repo"), case.get("pr"))
        category = case.get("category", "")
        if key in existing or len(cases) >= max_size:
            continue
        if category in caps and counts.get(category, 0) >= caps[category]:
            continue
        existing.add(key)
        counts[category] = counts.get(category, 0) + 1
        cases.append(case)
        added.append(case)
    if not added:
        return corpus, []
    grown = dict(corpus)
    grown["cases"] = cases
    grown["corpus_version"] = _bump_version(corpus.get("corpus_version"), len(added))
    return grown, added


def prune_staging(
    staging: dict[str, Any], stage_new: list[dict[str, Any]], *, now: datetime, expiry_days: int
) -> dict[str, Any]:
    """Merge new staging cases and drop any older than ``expiry_days`` (auto-expiry)."""
    kept: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any]] = set()
    for case in list(staging.get("cases", [])) + stage_new:
        key = (case.get("repo"), case.get("pr"))
        if key in seen:
            continue
        first_seen = _parse_ts(case.get("harvested_at")) or now
        if (now - first_seen).total_seconds() / 86400.0 > expiry_days:
            continue
        seen.add(key)
        kept.append(case)
    return {
        "schema": staging.get("schema", "verifier-corpus-staging/v1"),
        "note": "FYI-only. Auto-expiring candidate cases pending stability or adjudication; "
        "nothing here gates anything.",
        "cases": kept,
    }


# --------------------------------------------------------------------------- gh layer


def _gh_json(args: list[str]) -> Any:
    result = subprocess.run(["gh", *args], check=True, capture_output=True, text=True)  # noqa: S607
    return json.loads(result.stdout or "null")


_REVERT_REF = re.compile(r"#(\d+)")


def _reverted_pr_numbers(repo: str) -> set[int]:  # pragma: no cover - integration
    """PR numbers referenced by any recent revert PR/commit in the repo."""
    reverts = (
        _gh_json(
            [
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "merged",
                "--search",
                "revert in:title",
                "--limit",
                "100",
                "--json",
                "title,body",
            ]
        )
        or []
    )
    numbers: set[int] = set()
    for pr in reverts:
        for match in _REVERT_REF.findall(f"{pr.get('title', '')} {pr.get('body', '')}"):
            numbers.add(int(match))
    return numbers


def fetch_records(
    repos: list[str], *, per_repo: int, stability_days: int, harvest_window_days: int
) -> list[dict[str, Any]]:  # pragma: no cover - integration
    """Fetch PRs that crossed the stability line recently, with revert/follow-up signals.

    Targets PRs merged in ``[now - stability_days - harvest_window, now - stability_days]``
    so every candidate is already past the stability window (a newest-N fetch only
    returns too-recent merges that can never promote — the live-data failure mode
    this window fixes).
    """
    now = datetime.now(UTC)
    end = (now - timedelta(days=stability_days)).date().isoformat()
    start = (now - timedelta(days=stability_days + harvest_window_days)).date().isoformat()
    records: list[dict[str, Any]] = []
    for repo in repos:
        merged = (
            _gh_json(
                [
                    "pr",
                    "list",
                    "--repo",
                    repo,
                    "--state",
                    "merged",
                    "--search",
                    f"merged:{start}..{end}",
                    "--limit",
                    str(per_repo),
                    "--json",
                    "number,title,mergedAt,body,labels",
                ]
            )
            or []
        )
        reverted = _reverted_pr_numbers(repo)
        for pr in merged:
            number = pr.get("number")
            labels = {lb.get("name") for lb in pr.get("labels", []) if isinstance(lb, dict)}
            records.append(
                {
                    "repo": repo,
                    "pr": number,
                    "merged": True,
                    "merged_at": pr.get("mergedAt"),
                    "reverted": number in reverted,
                    "verifier_followup": bool(
                        labels & {"verify:create-issue", "verifier-followup"}
                    ),
                    # Resolution of a follow-up needs semantic judgment; stay conservative
                    # (unresolved -> staged, never auto-labeled NON_PASS).
                    "followup_resolved": False,
                }
            )
    return records


# ------------------------------------------------------------------------------- CLI


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _growth_config(policy: dict[str, Any], profile: str) -> dict[str, Any]:
    prof = policy.get("profiles", {}).get(profile, {})
    cfg = dict(prof.get("corpus_growth", {}))
    cfg.setdefault("enabled", False)
    cfg.setdefault("stability_days", 30)
    cfg.setdefault("staging_expiry_days", 60)
    cfg.setdefault("harvest_window_days", 60)
    cfg.setdefault("max_corpus_size", 150)
    cfg.setdefault(
        "category_caps",
        {CATEGORY_CLEAN_PASS: 40, CATEGORY_REGRESSION: 20, CATEGORY_FOLLOW_UP: 20},
    )
    cfg.setdefault("source_repos", [])
    return cfg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Grow the verifier corpus from realized PR outcomes."
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_PATH)
    parser.add_argument("--staging", type=Path, default=DEFAULT_STAGING_PATH)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--from-json", type=Path, help="Read pre-fetched PR records instead of gh.")
    parser.add_argument("--per-repo", type=int, default=50)
    parser.add_argument(
        "--write", action="store_true", help="Persist corpus + staging (default: dry-run)."
    )
    args = parser.parse_args(argv)

    policy = _load(args.policy, {})
    cfg = _growth_config(policy, args.profile)
    if not cfg["enabled"]:
        print("corpus_growth is disabled in the policy; nothing to do.")
        return 0

    now = datetime.now(UTC)
    if args.from_json:
        records = _load(args.from_json, [])
    else:  # pragma: no cover - integration path
        records = fetch_records(
            list(cfg["source_repos"]),
            per_repo=args.per_repo,
            stability_days=int(cfg["stability_days"]),
            harvest_window_days=int(cfg["harvest_window_days"]),
        )

    promote, stage = partition(records, now=now, stability_days=int(cfg["stability_days"]))
    corpus = _load(args.corpus, {"cases": []})
    grown, added = grow_corpus(
        corpus,
        promote,
        max_size=int(cfg["max_corpus_size"]),
        category_caps=dict(cfg.get("category_caps") or {}),
    )
    staging = _load(args.staging, {"cases": []})
    new_staging = prune_staging(
        staging, stage, now=now, expiry_days=int(cfg["staging_expiry_days"])
    )

    print(
        f"harvest: {len(records)} records → {len(added)} promoted "
        f"(corpus {len(corpus.get('cases', []))}→{len(grown.get('cases', []))}), "
        f"{len(new_staging['cases'])} staged (FYI, auto-expiring)."
    )
    for case in added:
        print(f"  + {case['case_id']} {case['expected_verdict']} ({case['category']})")

    if args.write:
        if added:
            args.corpus.write_text(json.dumps(grown, indent=2) + "\n", encoding="utf-8")
        args.staging.write_text(json.dumps(new_staging, indent=2) + "\n", encoding="utf-8")
        print(f"wrote corpus={args.corpus} staging={args.staging}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
