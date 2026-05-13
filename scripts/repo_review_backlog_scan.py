#!/usr/bin/env python3
"""Scan active repos for open enhancement/feature issues that fell between systems,
auto-label them with `priority:low|normal`, and surface only the items the cron
isn't confident about for human decision.

The opener cron selects work units by `priority:high|normal|low` label or by
presence in the weekly approved-issue-queue. Issues created manually with
`enhancement` or `feature` labels but no `priority:*` label are invisible to
both: the opener doesn't see them, and the repo-review's design-vs-impl
discovery doesn't promote them (they aren't a design gap, they're declared
work). They sit indefinitely.

The 2026-05-07 worked example: Inv-Man-Intake #25/#26/#27 were created
2026-03-01 with `enhancement` + `milestone:B-extraction-queue-images` labels
only. 70 days later, no activity, no agent ever picked them up.

## Two-tier resolution

For each stale unaddressed issue, the scanner classifies it as either:

**auto-labelable** — the heuristics confidently determine a priority, and (with
`--apply`) the scanner calls `gh issue edit --add-label priority:X`. The user
sees these as a "Auto-labeled this week" summary; no action required.

**needs human** — the scanner can't safely auto-label because the issue looks
like an umbrella/epic (children referenced inline), or it's blocked, or some
other signal suggests human judgment is required. These surface in the
desktop file with the same three commands (promote/deprioritize/close) as
before.

## Priority heuristic for auto-label

- If has `milestone:*` label → `priority:normal` (declared as part of planned work)
- Otherwise if created >90 days ago → `priority:low` (long-stalled, lower confidence in scope)
- Otherwise → `priority:normal` (default for declared enhancements)

## Reasons to surface for human decision (NOT auto-label)

- Looks like an umbrella/epic: title contains epic/tracker/umbrella/roadmap,
  has `epic`/`umbrella`/`tracker`/`meta`/`parent` label, or body has ≥2
  task-checkbox issue refs (`- [ ] #NNN`).
- Has `blocked` or `blocked:*` label.

## Exclusions (filtered out before classification)

- Has any `priority:*` label (opener would already see it)
- Has any `agent:*` label (an agent owns it)
- Has dependabot / sync* / process-eval / langsmith / campaign:* / tracker:durable
  labels — those have their own automations and shouldn't bubble up here.
- Has been updated in the past `--stale-days` days (default 7).
- Has neither `enhancement` nor `feature` label.

## Output

JSON to `--out` with `auto_labeled` and `needs_human` arrays. The notify step
reads this and renders both sections in the desktop reminder.

## Apply mode

By default the scanner is dry-run: it classifies but does NOT mutate GitHub.
Pass `--apply` to actually add labels. The cron's coordinator passes `--apply`.

## CLI

    python scripts/repo_review_backlog_scan.py \
        --registry config/repo_review_registry.json \
        --out docs/reports/repo-review/backlog-scan.json \
        [--apply]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Filtering — labels that exclude an issue from any consideration
# ---------------------------------------------------------------------------

# Already visible to the opener (it queues priority-labeled issues directly).
PRIORITY_LABEL_PREFIXES = ("priority:",)

# An agent is already assigned/working — don't double-surface.
AGENT_LABEL_PREFIXES = ("agent:",)

# Handled by other crons (dependabot bridge, sync workers, process-eval cron).
EXCLUDE_LABELS_EXACT = {
    # Dependabot ecosystem
    "dependabot",
    "dependencies",
    # Sync automation (workflows / consumer template sync)
    "sync",
    "sync-pr",
    "sync-generated",
    "consumer-sync",
    "integration-sync",
    "workflows-sync",
    "template-sync",
    # Process-evaluation / observability automation
    "langsmith",
    "process-evaluation",
    "ops-data",
    "automation-metrics",
    # Tracker / campaign labels (handled by their own controller)
    "tracker:durable",
    "campaign:active",
    "campaign:sync-dependabot",
}
EXCLUDE_LABEL_PREFIXES = ("campaign:",)  # all campaign:* are controller-owned

# Include only if at least one of these labels is present.
INCLUDE_LABELS = {"enhancement", "feature"}


# ---------------------------------------------------------------------------
# Classification — labels and patterns that mean "surface for human"
# ---------------------------------------------------------------------------

# Labels that signal "this isn't a leaf — needs human judgment".
HUMAN_DECISION_LABELS_EXACT = {
    "epic",
    "umbrella",
    "tracker",
    "meta",
    "parent",
    "needs-triage",
    "discussion",
}
HUMAN_DECISION_LABEL_PREFIXES = ("blocked",)  # "blocked" or "blocked:waiting-on-X"

# Title words that signal umbrella/epic shape.
UMBRELLA_TITLE_WORDS = ("epic", "tracker", "umbrella", "roadmap", "rollup", "parent issue")

# Body patterns: an issue body with multiple task-checkboxes that mention
# other issue numbers is almost certainly an umbrella tracking children.
# Matches both `- [ ] #25` and `- [ ] Child issue #25: title text` forms.
UMBRELLA_BODY_PATTERN = re.compile(r"(?m)^\s*-\s*\[[ xX]\].*#\d+")
UMBRELLA_BODY_MIN_CHILD_REFS = 2

# Explicit textual declaration of children — even without checkboxes, a body
# section like "Children: #24, #25, #26, #27" or "Child issues: #1, #2" is an
# umbrella signal.
UMBRELLA_DECLARATION_PATTERN = re.compile(
    r"(?im)^\s*(?:#+\s*)?(?:children|child issues?)\s*:.*#\d+"
)


def looks_like_umbrella(title: str, body: str, labels: list[str]) -> tuple[bool, str]:
    """Return (yes, reason) if the issue looks like an umbrella/epic.

    Conservative: any single positive signal trips it. Better to surface a
    leaf as a human-decision occasionally than to auto-label an umbrella.
    """
    title_l = (title or "").lower()
    for w in UMBRELLA_TITLE_WORDS:
        if w in title_l:
            return True, f"title contains '{w}'"
    label_set = {label.lower() for label in labels}
    overlap = label_set & HUMAN_DECISION_LABELS_EXACT
    if overlap:
        return True, f"has label: {sorted(overlap)[0]}"
    for prefix in HUMAN_DECISION_LABEL_PREFIXES:
        for lbl in labels:
            if lbl.startswith(prefix):
                return True, f"has {prefix}* label: {lbl}"
    child_refs = UMBRELLA_BODY_PATTERN.findall(body or "")
    if len(child_refs) >= UMBRELLA_BODY_MIN_CHILD_REFS:
        return True, f"body has {len(child_refs)} child-issue checkboxes"
    if UMBRELLA_DECLARATION_PATTERN.search(body or ""):
        return True, "body declares 'Children: #...' or 'Child issues: #...'"
    return False, ""


def decide_priority(*, labels: list[str], created_at: str | None, very_stale_days: int = 90) -> str:
    """Return `priority:normal` or `priority:low` for a leaf enhancement issue.

    Heuristic:
      - Has `milestone:*` label → declared as part of planned work → normal.
      - Created >very_stale_days ago → low (long-stalled, less confidence the
        scope is still current; the user can promote back if needed).
      - Otherwise → normal (default for fresh declared enhancements).
    """
    if any(label.startswith("milestone:") for label in labels):
        return "priority:normal"
    age = days_since(created_at)
    if age > very_stale_days:
        return "priority:low"
    return "priority:normal"


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def load_registry(registry_path: Path) -> list[str]:
    """Return the list of active repo full-names from the registry."""
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    repos = data.get("repos", []) or []
    return [
        str(r.get("repo"))
        for r in repos
        if isinstance(r, dict) and r.get("status") == "active" and r.get("repo")
    ]


def gh_list_open_issues(repo: str) -> list[dict[str, Any]]:
    """Return all open issues for `repo`, including body text for umbrella detection.

    Best-effort: on gh failure returns [].
    """
    if not shutil.which("gh"):
        print(f"[backlog-scan] gh not on PATH; skipping {repo}", file=sys.stderr)
        return []
    cmd = [
        "gh",
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        "open",
        "--limit",
        "500",
        "--json",
        "number,title,body,labels,updatedAt,createdAt,url",
    ]
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        print(f"[backlog-scan] gh timed out on {repo}", file=sys.stderr)
        return []
    if result.returncode != 0:
        print(
            f"[backlog-scan] gh issue list failed on {repo}: {result.stderr[:200]}", file=sys.stderr
        )
        return []
    try:
        return json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []


def gh_add_label(repo: str, number: int, label: str) -> tuple[bool, str]:
    """Add `label` to issue #number in `repo` via gh CLI. Returns (ok, message)."""
    if not shutil.which("gh"):
        return False, "gh not on PATH"
    cmd = [
        "gh",
        "issue",
        "edit",
        str(number),
        "--repo",
        repo,
        "--add-label",
        label,
    ]
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return False, "gh timed out"
    if result.returncode != 0:
        return False, f"rc={result.returncode}: {result.stderr.strip()[:200]}"
    return True, "labeled"


def label_names(issue: dict[str, Any]) -> list[str]:
    return [
        str(label.get("name", ""))
        for label in (issue.get("labels") or [])
        if isinstance(label, dict)
    ]


def is_excluded(labels: list[str]) -> tuple[bool, str]:
    """Return (excluded, reason). reason is empty string when not excluded."""
    label_set = set(labels)
    for prefix in PRIORITY_LABEL_PREFIXES:
        for lbl in labels:
            if lbl.startswith(prefix):
                return True, f"has priority label: {lbl}"
    for prefix in AGENT_LABEL_PREFIXES:
        for lbl in labels:
            if lbl.startswith(prefix):
                return True, f"has agent label: {lbl}"
    for prefix in EXCLUDE_LABEL_PREFIXES:
        for lbl in labels:
            if lbl.startswith(prefix):
                return True, f"excluded prefix: {lbl}"
    overlap = label_set & EXCLUDE_LABELS_EXACT
    if overlap:
        return True, f"excluded label: {sorted(overlap)[0]}"
    return False, ""


def is_included(labels: list[str]) -> bool:
    return bool(set(labels) & INCLUDE_LABELS)


def days_since(timestamp: str | None) -> float:
    if not timestamp:
        return 0.0
    try:
        ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return 0.0
    return (datetime.now(tz=UTC) - ts).total_seconds() / 86400.0


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


def scan(repos: list[str], stale_days: int, apply_labels: bool) -> dict[str, Any]:
    auto_labeled: list[dict[str, Any]] = []
    needs_human: list[dict[str, Any]] = []
    scanned = 0
    repo_summary: dict[str, dict[str, int]] = {}

    for repo in repos:
        repo_total = 0
        repo_auto = 0
        repo_human = 0
        for issue in gh_list_open_issues(repo):
            scanned += 1
            repo_total += 1
            labels = label_names(issue)
            if not is_included(labels):
                continue
            excluded, _reason = is_excluded(labels)
            if excluded:
                continue
            age_days = days_since(issue.get("updatedAt"))
            if age_days < stale_days:
                continue  # something recently happened to it

            number = issue.get("number")
            title = issue.get("title") or ""
            body = issue.get("body") or ""
            url = issue.get("url", "")
            created_at = issue.get("createdAt")

            # Classify: umbrella / blocked → needs human; else → auto-label.
            umbrella, umbrella_reason = looks_like_umbrella(title, body, labels)

            base_record = {
                "repo": repo,
                "number": number,
                "title": title,
                "url": url,
                "age_days": round(age_days, 1),
                "created_age_days": round(days_since(created_at), 1),
                "last_updated": issue.get("updatedAt"),
                "created_at": created_at,
                "labels": labels,
            }

            if umbrella:
                base_record["surface_reason"] = umbrella_reason
                needs_human.append(base_record)
                repo_human += 1
                continue

            # Leaf enhancement → auto-label.
            priority = decide_priority(labels=labels, created_at=created_at)
            applied = False
            apply_message = "dry-run (not applied)"
            if apply_labels:
                ok, msg = gh_add_label(repo, int(number), priority)
                applied = ok
                apply_message = msg
                if not ok:
                    # If labeling fails, surface for human.
                    base_record["surface_reason"] = f"auto-label FAILED: {msg}"
                    base_record["intended_priority"] = priority
                    needs_human.append(base_record)
                    repo_human += 1
                    continue

            base_record["applied_priority"] = priority
            base_record["applied"] = applied
            base_record["apply_message"] = apply_message
            auto_labeled.append(base_record)
            repo_auto += 1

        repo_summary[repo] = {
            "open_issues": repo_total,
            "auto_labeled": repo_auto,
            "needs_human": repo_human,
        }

    # Order: oldest-stale-first inside each list.
    auto_labeled.sort(key=lambda i: i.get("age_days", 0), reverse=True)
    needs_human.sort(key=lambda i: i.get("age_days", 0), reverse=True)

    return {
        "generated_on": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stale_days_threshold": stale_days,
        "apply_mode": apply_labels,
        "scanned_open_issues": scanned,
        "auto_labeled": auto_labeled,
        "needs_human": needs_human,
        # `items` retained for backwards-compat with the prior notify step (it
        # treated all matches as needs-human). It now mirrors `needs_human`.
        "items": needs_human,
        "by_repo": repo_summary,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        required=True,
        help="path to config/repo_review_registry.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="path to write backlog-scan.json",
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=7,
        help="surface issues NOT updated in this many days (default: 7)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually add priority labels to auto-labelable issues. "
        "Default is dry-run: classify and report but do not mutate GitHub.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress per-repo progress chatter",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        repos = load_registry(args.registry)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"[backlog-scan] cannot load registry: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        mode = "APPLY" if args.apply else "dry-run"
        print(
            f"[backlog-scan] scanning {len(repos)} active repos (stale>{args.stale_days}d, {mode})"
        )

    result = scan(repos, args.stale_days, args.apply)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    n_auto = len(result["auto_labeled"])
    n_human = len(result["needs_human"])
    print(
        f"[backlog-scan] scanned {result['scanned_open_issues']} open issues; "
        f"auto-labeled={n_auto}, needs-human={n_human} → {args.out}"
    )

    if not args.quiet:
        for label, items in (
            ("Auto-labeled", result["auto_labeled"]),
            ("Needs human", result["needs_human"]),
        ):
            if not items:
                continue
            print(f"  {label}:")
            for it in items[:5]:
                if label == "Auto-labeled":
                    extra = f" → {it.get('applied_priority','?')}" + (
                        " (dry-run)" if not it.get("applied") else ""
                    )
                else:
                    extra = f" — {it.get('surface_reason','?')}"
                print(
                    f"    - {it['repo']}#{it['number']} ({it['age_days']}d): {it['title'][:60]}{extra}"
                )
            if len(items) > 5:
                print(f"    - ...and {len(items) - 5} more")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
