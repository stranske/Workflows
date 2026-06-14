#!/usr/bin/env python3
"""Assemble an approved-issue-queue payload from per-repo converged.json files
plus config/repo_review_feedback.json.

NOTE (#2272): this module is NOT the producer of the weekly pipeline's
``docs/reports/repo-review/approved-issue-queue.json``. The coordinator invokes
``build_queue`` for a log-only preview (step 3) and the final evaluator pass
(``repo_review_evaluator.write_approved_issue_queue``, step 4) is the SOLE writer
of that artifact, applying the priority-tiering and cycle-binding guards. The
standalone ``--out`` CLI here is a developer/debugging helper that writes
wherever you point it; it does not feed the opener/uploader by itself.

Honors per-repo feedback decisions:

- `approve` / `approve all` / `revise` → include all converged_candidates with
  bodies; include the meta candidate when `include_meta_candidate: true`.
- `no_new_work_accept` → include nothing for this repo (dual no-new-work outcome
  was accepted by the human).
- `defer` → include nothing for this repo (out-of-scope this cycle).
- Anything else → recorded as skipped with the decision tag in the report.

Candidates with empty `body` or `body` starting with `INSUFFICIENT_EVIDENCE:`
are skipped — those are body-writer-flagged stubs that need deeper review.

The queue file shape matches what `scripts/upload_repo_review_issues.py`
expects: a top-level dict with `issues: [...]`, where each issue has
`repo`, `title`, `body`, `labels`, and `review_evidence_trace`.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.repo_review_scorecard import approved_scorecard_issue_items, load_scorecard_scan
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_review_scorecard import (  # type: ignore[no-redef]
        approved_scorecard_issue_items,
        load_scorecard_scan,
    )

META_AUDIT_LABEL = "repo-review-meta-audit"
APPROVE_DECISIONS = {"approve", "revise"}
SKIP_DECISIONS = {"defer", "no_new_work_accept"}


def trace_for(c: dict[str, Any]) -> dict[str, Any]:
    """Build a review_evidence_trace dict the upload helper accepts."""
    return {
        "gap": c.get("gap", "") or "",
        "current_state": c.get("current_state", "") or "",
        "required_change": c.get("required_change", "") or "",
        "design_refs": list(c.get("design_refs", []) or []),
        "implementation_refs": list(c.get("implementation_refs", []) or []),
        "test_refs": list(c.get("test_refs", []) or []),
        "issue_title_pattern": c.get("title", "") or "",
    }


def labels_for(c: dict[str, Any], *, is_meta: bool = False) -> list[str]:
    pri = c.get("priority", "normal")
    if pri not in ("high", "normal", "low"):
        pri = "normal"
    labels = ["repo-review-approved", f"priority:{pri}"]
    if is_meta:
        labels.append(META_AUDIT_LABEL)
    return labels


def is_uploadable_body(body: str | None) -> tuple[bool, str]:
    if not body:
        return False, "empty body"
    if body.startswith("INSUFFICIENT_EVIDENCE"):
        return False, "INSUFFICIENT_EVIDENCE marker"
    if "## Why" not in body or "## Tasks" not in body:
        return False, "missing required sections"
    return True, ""


def build_queue(
    round2_dir: Path,
    feedback_path: Path,
    scorecard_scan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    feedback = json.loads(feedback_path.read_text(encoding="utf-8"))
    decisions = feedback.get("decisions", {}) or {}

    if not round2_dir.is_dir():
        raise FileNotFoundError(f"round2 dir not found: {round2_dir}")

    repo_dirs = {d.name.replace("__", "/"): d for d in round2_dir.iterdir() if d.is_dir()}

    queue: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for repo, decision in decisions.items():
        decision_type = (decision.get("decision") or "").strip()

        # Normalize compound decisions like "revise|deeper-review" — take the
        # first segment for routing.
        primary = decision_type.split("|", 1)[0].strip().lower()

        if primary in SKIP_DECISIONS:
            skipped.append({"repo": repo, "reason": f"decision={primary}"})
            continue
        if primary not in APPROVE_DECISIONS:
            skipped.append({"repo": repo, "reason": f"unhandled decision={decision_type}"})
            continue

        repo_dir = repo_dirs.get(repo)
        if not repo_dir:
            skipped.append({"repo": repo, "reason": "no converged.json directory"})
            continue
        cj = repo_dir / "converged.json"
        if not cj.exists():
            skipped.append({"repo": repo, "reason": "converged.json missing"})
            continue

        try:
            data = json.loads(cj.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            skipped.append({"repo": repo, "reason": f"converged.json parse error: {exc}"})
            continue

        # converged candidates
        for i, c in enumerate(data.get("converged_candidates", []) or []):
            ok, why = is_uploadable_body(c.get("body"))
            if not ok:
                skipped.append(
                    {
                        "repo": repo,
                        "candidate_index": str(i),
                        "title": str(c.get("title", ""))[:80],
                        "reason": why,
                    }
                )
                continue
            queue.append(
                {
                    "repo": repo,
                    "title": c.get("title", ""),
                    "body": c.get("body", ""),
                    "labels": labels_for(c, is_meta=False),
                    "review_evidence_trace": trace_for(c),
                }
            )

        # meta candidate (audit-scope) — only if explicitly opted in
        if decision.get("include_meta_candidate", False):
            meta = data.get("meta_candidate")
            if meta:
                ok, why = is_uploadable_body(meta.get("body"))
                if ok:
                    queue.append(
                        {
                            "repo": repo,
                            "title": meta.get("title", ""),
                            "body": meta.get("body", ""),
                            "labels": labels_for(meta, is_meta=True),
                            "review_evidence_trace": trace_for(meta),
                        }
                    )
                else:
                    skipped.append(
                        {
                            "repo": repo,
                            "candidate_index": "meta",
                            "title": str(meta.get("title", ""))[:80],
                            "reason": why,
                        }
                    )

    if scorecard_scan is None:
        scorecard_scan = load_scorecard_scan(round2_dir.parent / "scorecard-scan.json")
    generated_on = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    scorecard = approved_scorecard_issue_items(scorecard_scan, feedback, generated_on)
    for item in scorecard["issues"]:
        if item.get("body_valid") is not True or item.get("body_quality_errors"):
            skipped.append(
                {
                    "repo": item.get("repo", "?"),
                    "finding_id": str(item.get("scorecard_finding_id", "")),
                    "reason": "scorecard issue body failed quality gate",
                }
            )
            continue
        queue.append(item)
    for pending in scorecard["pending"]:
        skipped.append(
            {
                "repo": pending.get("repo", "?"),
                "finding_id": str(pending.get("finding_id", "")),
                "reason": str(pending.get("reason", "scorecard finding pending")),
            }
        )
    for dropped in scorecard["dropped"]:
        skipped.append(
            {
                "repo": dropped.get("repo", "?"),
                "finding_id": str(dropped.get("finding_id", "")),
                "reason": "scorecard finding dropped",
            }
        )

    return {
        "generated_on": datetime.now(tz=UTC).strftime("%Y-%m-%d"),
        "feedback_source": str(feedback_path),
        "round2_source": str(round2_dir),
        "issues": queue,
        "skipped": skipped,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--round2-dir",
        type=Path,
        required=True,
        help="path to <output_dir>/round2/ containing per-repo converged.json files",
    )
    parser.add_argument(
        "--feedback",
        type=Path,
        required=True,
        help="path to config/repo_review_feedback.json",
    )
    parser.add_argument(
        "--scorecard-scan",
        type=Path,
        default=None,
        help="path to scorecard-scan.json (default: <round2-dir>/../scorecard-scan.json)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="path to write approved-issue-queue.json",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="only print summary line",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scorecard_scan_path = (
        args.scorecard_scan
        if args.scorecard_scan is not None
        else args.round2_dir.parent / "scorecard-scan.json"
    )
    scorecard_scan = load_scorecard_scan(scorecard_scan_path)
    try:
        result = build_queue(args.round2_dir, args.feedback, scorecard_scan)
    except FileNotFoundError as exc:
        print(f"[queue-builder] {exc}", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    n_issues = len(result["issues"])
    n_skipped = len(result["skipped"])
    print(f"[queue-builder] wrote {n_issues} issues to {args.out}")

    if not args.quiet:
        by_repo: dict[str, int] = {}
        for q in result["issues"]:
            by_repo[q["repo"]] = by_repo.get(q["repo"], 0) + 1
        for r in sorted(by_repo):
            print(f"  {r}: {by_repo[r]}")
        if n_skipped:
            print(f"\nSkipped ({n_skipped}):")
            for s in result["skipped"]:
                bits = [f"{k}={v}" for k, v in s.items()]
                print(f"  - {' '.join(bits)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
