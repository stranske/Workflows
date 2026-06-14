#!/usr/bin/env python3
"""Surface the weekly repo-review cycle's outcome to the human reviewer.

The cron writes the packet + queue, but does NOT auto-upload — humans must
review the packet, optionally update `config/repo_review_feedback.json`, then
run `upload_repo_review_issues.py --apply`. Without an active reminder, the
packet sits unread.

This helper produces two surfaces:

A. macOS user notification (osascript "display notification") with a one-line
   summary the moment the cycle ends. Lands in Notification Center; visible
   if the user is at their desk.

B. Persistent desktop file at `~/Desktop/REPO-REVIEW-ACTION-NEEDED.md`. Stays
   until the user deletes it (typically after running --apply). Survives any
   away period, can't be missed when the user opens their desk.

Both surfaces include the packet path, uploadable issue count, and the exact
command to run. The desktop file overwrites each weekly cycle; only the most
recent week is on disk.

Usage (from coordinator or manually):

    python scripts/repo_review_notify.py \
        --output-dir docs/reports/repo-review \
        --queue docs/reports/repo-review/approved-issue-queue.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DESKTOP_FILENAME = "REPO-REVIEW-ACTION-NEEDED.md"


def load_queue(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"issues": [], "skipped": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"issues": [], "skipped": []}


def summarize_queue(queue: dict[str, Any]) -> dict[str, Any]:
    issues = queue.get("issues", []) or []
    skipped = queue.get("skipped", []) or []
    by_repo: dict[str, int] = {}
    for issue in issues:
        repo = str(issue.get("repo", "?"))
        by_repo[repo] = by_repo.get(repo, 0) + 1
    return {
        "total": len(issues),
        "by_repo": by_repo,
        "skipped_count": len(skipped),
        "issue_titles": [str(i.get("title", "?"))[:80] for i in issues],
    }


def display_notification(title: str, subtitle: str, message: str) -> None:
    """Show a macOS user notification via osascript.

    Best-effort: failures are logged and ignored — notification is a courtesy
    surface, not a hard dependency.
    """
    if not shutil.which("osascript"):
        print("[notify] osascript not on PATH; skipping macOS notification", file=sys.stderr)
        return

    # Escape double quotes for AppleScript string
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    script = (
        f'display notification "{esc(message)}" '
        f'with title "{esc(title)}" '
        f'subtitle "{esc(subtitle)}" '
        f'sound name "Glass"'
    )
    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"[notify] osascript failed: {exc}", file=sys.stderr)


def load_backlog_scan(path: Path | None) -> dict[str, Any]:
    """Load the backlog-scan.json output, or return empty if absent/malformed."""
    if path is None or not path.is_file():
        return {"items": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"items": []}


def format_auto_labeled_section(backlog: dict[str, Any]) -> str:
    """Return a brief info section listing items the cron auto-labeled this week.

    No action required from the user — this is FYI. The cron added the label
    (when --apply was passed); the opener will pick these up on its next pass.
    """
    items = backlog.get("auto_labeled", []) or []
    if not items:
        return ""
    apply_mode = backlog.get("apply_mode", False)
    note = (
        "These were auto-labeled by the cron (the opener will pick them up " "on its next pass)."
        if apply_mode
        else "These WOULD be auto-labeled if the cron ran with --apply (the "
        "current run was dry-run only — the labels are NOT on the issues yet)."
    )
    header = (
        f"\n\n## Auto-labeled this week ({len(items)} item"
        f"{'s' if len(items) != 1 else ''}) — FYI, no action required\n\n"
        f"{note}\n\n"
    )
    lines: list[str] = []
    for item in items:
        repo = item["repo"]
        num = item["number"]
        title = item["title"]
        age = item.get("age_days", 0)
        prio = item.get("applied_priority", "priority:?").replace("priority:", "")
        applied = item.get("applied", False)
        applied_marker = "" if applied else " _(dry-run; not yet applied)_"
        lines.append(
            f"- {repo}#{num} → **{prio}**{applied_marker} — _{title[:80]}_ " f"({age:.0f}d stale)"
        )
    return header + "\n".join(lines) + "\n"


def format_needs_human_section(backlog: dict[str, Any]) -> str:
    """Return a markdown section for items the cron declined to auto-label.

    These are typically umbrella/epic-shaped or blocked issues. Each gets the
    EXACT three gh commands to promote / deprioritize / close, so the user can
    resolve every entry inline.
    """
    items = backlog.get("needs_human", []) or backlog.get("items", []) or []
    if not items:
        return ""

    threshold = backlog.get("stale_days_threshold", 7)
    header = (
        f"\n\n## Backlog needing your decision ({len(items)} item"
        f"{'s' if len(items) != 1 else ''})\n\n"
        f"These open issues are stale (>{threshold}d) and labeled "
        "`enhancement`/`feature` without priority. The cron declined to "
        "auto-label them because each looks like an umbrella/epic, has a "
        "blocked label, or shows another signal that human judgment is "
        "required. Decide each: **promote**, **deprioritize**, or **close**.\n\n"
    )

    lines: list[str] = []
    for item in items:
        repo = item["repo"]
        num = item["number"]
        title = item["title"]
        age = item.get("age_days", 0)
        url = item.get("url", "")
        reason = item.get("surface_reason", "")
        labels = item.get("labels", []) or []
        relevant = [label for label in labels if label not in {"enhancement", "feature"}][:2]
        label_hint = (
            f"  _(also labeled: {', '.join(f'`{label}`' for label in relevant)})_\n"
            if relevant
            else ""
        )
        reason_line = f"  _Surface reason: {reason}_\n" if reason else ""
        lines.append(
            f"### {repo}#{num}: {title}\n"
            f"  ({age:.0f} days since last update — {url})\n"
            f"{label_hint}"
            f"{reason_line}"
            f"  - Promote: `gh issue edit {num} --repo {repo} --add-label priority:normal`\n"
            f"  - Deprioritize: `gh issue edit {num} --repo {repo} --add-label priority:low`\n"
            f'  - Close: `gh issue close {num} --repo {repo} --comment "Out of scope; closing per backlog scan."`\n'
        )

    return header + "\n".join(lines) + "\n"


def format_backlog_section(backlog: dict[str, Any]) -> str:
    """Combined backlog section: auto-labeled FYI + needs-human action items."""
    return format_auto_labeled_section(backlog) + format_needs_human_section(backlog)


def load_docs_drift_scan(path: Path | None) -> dict[str, Any]:
    """Load the docs-drift-scan.json output, or return empty if absent/malformed."""
    if path is None or not path.is_file():
        return {"by_repo": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"by_repo": []}


def format_docs_drift_section(drift: dict[str, Any]) -> str:
    """Render the docs-drift section: ONE bundled remediation block per repo
    with non-empty drift, with a ready-to-paste ``gh issue create`` snippet.

    Repos with only accurate-no-drift instances are not shown (the audit
    trail lives in the JSON output for those). Repos with errors but no
    drift are surfaced briefly so the human knows the scan ran.
    """
    by_repo = drift.get("by_repo") or []
    drifting = [b for b in by_repo if b.get("drift_instances")]
    error_only = [b for b in by_repo if b.get("errors") and not b.get("drift_instances")]

    if not drifting and not error_only:
        return ""

    parts: list[str] = []
    if drifting:
        plural = "s" if len(drifting) != 1 else ""
        parts.append(
            f"\n\n## Doc drift detected ({len(drifting)} repo{plural})\n\n"
            "The weekly doc-drift scanner flagged source-of-truth docs that "
            "no longer reflect current implementation. Each repo gets ONE "
            "bundled remediation issue (drifting docs as task checkboxes); "
            "do not file per-doc issues.\n"
        )
        for bucket in drifting:
            repo = bucket["repo"]
            instances = bucket["drift_instances"]
            doc_list = sorted({inst["doc_path"] for inst in instances})
            instance_count = len(instances)
            inst_plural = "s" if instance_count != 1 else ""
            doc_plural = "s" if len(doc_list) != 1 else ""
            parts.append(
                f"\n### {repo} -- {instance_count} drift instance{inst_plural} "
                f"across {len(doc_list)} doc{doc_plural}\n"
            )
            for inst in instances:
                cls = inst["classification"]
                claim = inst["claim"][:160]
                src = inst["authoritative_source"][:160]
                parts.append(f"  - **{cls}** _{inst['doc_path']}_: {claim}\n")
                if src:
                    parts.append(f"    Authoritative source: `{src}`\n")
            body_lines = "\n".join(f"- [ ] {p}" for p in doc_list)
            title = f"Remediate doc drift across {len(doc_list)} source-of-truth doc{doc_plural}"
            body_arg = (
                f"## Drift detected by weekly doc-drift scanner\n\n"
                f"Affected docs:\n\n{body_lines}\n\n"
                f"See `<output_dir>/docs-drift-scan.json` for per-claim detail."
            )
            parts.append(
                f"\n  Bundled remediation snippet:\n\n"
                f"  ```\n"
                f"  gh issue create --repo {repo} \\\n"
                f'      --title "{title}" \\\n'
                f"      --label priority:normal \\\n"
                f"      --body {json.dumps(body_arg)}\n"
                f"  ```\n"
            )

    if error_only:
        plural = "s" if len(error_only) != 1 else ""
        parts.append(
            f"\n\n## Doc-drift scan errors ({len(error_only)} repo{plural})\n\n"
            "The scanner ran but couldn't classify the listed docs. No "
            "drift was detected in the docs it COULD scan -- the errors "
            "may be transient (claude unavailable, doc moved, etc.).\n"
        )
        for bucket in error_only:
            parts.append(f"- **{bucket['repo']}**: {len(bucket['errors'])} doc(s) errored\n")

    return "".join(parts)


def summarize_docs_drift(docs_drift: dict[str, Any]) -> tuple[int, int]:
    """Return (drift_count, error_count) with a by_repo fallback.

    Older/malformed payloads may omit aggregate counters; derive them from
    by_repo so reminder headline logic still reflects real scan output.
    """
    drift_count = int((docs_drift or {}).get("total_drift_instances", 0) or 0)
    error_count = int((docs_drift or {}).get("total_errors", 0) or 0)
    if drift_count == 0 and error_count == 0:
        by_repo = (docs_drift or {}).get("by_repo") or []
        drift_count = sum(len(bucket.get("drift_instances") or []) for bucket in by_repo)
        error_count = sum(len(bucket.get("errors") or []) for bucket in by_repo)
    return drift_count, error_count


try:
    from scripts.repo_review_scorecard import load_scorecard_scan as _load_scorecard_scan_impl
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_review_scorecard import (
        load_scorecard_scan as _load_scorecard_scan_impl,  # type: ignore[no-redef]
    )


def load_scorecard_scan(path: Path | None) -> dict[str, Any]:
    """Load scorecard-scan.json, or return empty when absent/malformed."""
    loaded = _load_scorecard_scan_impl(path)
    if loaded is None:
        return {"by_repo": [], "total_findings": 0, "total_errors": 0}
    return loaded


def summarize_scorecard(scorecard: dict[str, Any]) -> tuple[int, int]:
    """Return (finding_count, error_count) with by_repo fallback."""
    finding_count = int((scorecard or {}).get("total_findings", 0) or 0)
    error_count = int((scorecard or {}).get("total_errors", 0) or 0)
    if finding_count == 0 and error_count == 0:
        by_repo = (scorecard or {}).get("by_repo") or []
        finding_count = sum(len(bucket.get("findings") or []) for bucket in by_repo)
        error_count = sum(len(bucket.get("errors") or []) for bucket in by_repo)
    return finding_count, error_count


def format_scorecard_section(scorecard: dict[str, Any]) -> str:
    """Render one human-action section per repo with approval snippets."""
    by_repo = scorecard.get("by_repo") or []
    actionable = [
        bucket
        for bucket in by_repo
        if isinstance(bucket, dict) and (bucket.get("findings") or bucket.get("errors"))
    ]
    if not actionable:
        return ""

    parts: list[str] = [
        "\n\n## Scorecard findings need explicit approval\n\n",
        "Low-scoring OpenSSF Scorecard checks were scanned from the public API. ",
        "They do **not** enter `approved-issue-queue.json` until you edit ",
        "`config/repo_review_feedback.json` and list explicit `approved_findings` ",
        "under each repo's `scorecard` decision. Do not create issues directly from ",
        "this section.\n",
    ]
    for bucket in actionable:
        repo = str(bucket.get("repo") or "?")
        findings = bucket.get("findings") or []
        errors = bucket.get("errors") or []
        parts.append(f"\n### {repo}\n")
        if errors and not findings:
            parts.append(f"- Scan errors: {len(errors)} (see `scorecard-scan.json`)\n")
            continue
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            finding_id = str(finding.get("finding_id") or "")
            check = str(finding.get("check") or "")
            score = finding.get("score", "?")
            reason = str(finding.get("reason") or "")[:200]
            doc_url = str(finding.get("documentation_url") or "")
            parts.append(f"- **{finding_id}** — score `{score}` — {reason}\n")
            if doc_url:
                parts.append(f"  - Docs: {doc_url}\n")
            snippet = {
                "decision": "approve",
                "approved_findings": [finding_id],
                "dropped_findings": [],
                "priority": finding.get("priority", "normal"),
                "priority_overrides": {},
                "notes": f"Explicit approval for {check} after human review.",
            }
            parts.append(
                f'\n  Paste under `decisions["{repo}"].scorecard` in '
                f"`config/repo_review_feedback.json`:\n\n"
                f"  ```json\n"
                f"{json.dumps(snippet, indent=2)}\n"
                f"  ```\n"
            )
    parts.append(
        "\nAfter editing feedback, rerun the evaluator to regenerate the queue:\n\n"
        "```bash\n"
        "python scripts/repo_review_evaluator.py \\\n"
        "  --output-dir docs/reports/repo-review \\\n"
        "  --skip-gitnexus-preflight\n"
        "```\n"
    )
    return "".join(parts)


def write_desktop_reminder(
    *,
    queue_summary: dict[str, Any],
    backlog: dict[str, Any],
    docs_drift: dict[str, Any],
    scorecard: dict[str, Any],
    packet_path: Path,
    queue_path: Path,
    output_dir: Path,
    workflows_steward_root: Path,
) -> Path:
    """Write a persistent reminder file to the user's desktop.

    Overwrites any prior file (we keep only the latest cycle's reminder).
    Includes both upload-ready issues AND the unaddressed backlog (issues
    that fell between the opener and the design-vs-impl review).
    """
    desktop = Path(os.path.expanduser("~/Desktop"))
    target = desktop / DESKTOP_FILENAME
    try:
        desktop.mkdir(parents=True, exist_ok=True)
    except OSError:
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / DESKTOP_FILENAME

    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    total = queue_summary["total"]
    by_repo = queue_summary["by_repo"]
    skipped_count = queue_summary["skipped_count"]
    titles = queue_summary["issue_titles"]
    auto_labeled_count = len(backlog.get("auto_labeled", []) or [])
    needs_human_count = len(backlog.get("needs_human", []) or [])
    backlog_count = auto_labeled_count + needs_human_count
    docs_drift_count, docs_drift_error_count = summarize_docs_drift(docs_drift)
    docs_drift_signal_count = docs_drift_count + docs_drift_error_count
    scorecard_count, scorecard_error_count = summarize_scorecard(scorecard)
    scorecard_signal_count = scorecard_count + scorecard_error_count

    if (
        total == 0
        and backlog_count == 0
        and docs_drift_signal_count == 0
        and scorecard_signal_count == 0
    ):
        headline = (
            "## ✓ Clean week — no action required\n\n"
            "No fresh design-vs-implementation gaps, no unaddressed "
            "enhancement issues across the fleet. The system will run "
            "again next Wednesday."
        )
    elif total == 0 and backlog_count == 0:
        headline = (
            f"## {docs_drift_signal_count} doc-drift item"
            f"{'s' if docs_drift_signal_count != 1 else ''} need review\n\n"
            "No fresh design-vs-implementation gaps or backlog decisions, "
            "but the docs-drift scan found remediation work or scan errors. "
            "See the doc-drift section below."
        )
    elif total == 0 and needs_human_count == 0 and docs_drift_signal_count == 0:
        headline = (
            f"## ✓ Clean week ({auto_labeled_count} backlog item"
            f"{'s' if auto_labeled_count != 1 else ''} auto-labeled)\n\n"
            "No fresh design-vs-implementation gaps. The cron found "
            f"{auto_labeled_count} stale unaddressed enhancement"
            f"{'s' if auto_labeled_count != 1 else ''} and labeled them with "
            "priority — no action required from you, see the FYI section below."
        )
    elif total == 0:
        detail_parts = []
        if needs_human_count:
            detail_parts.append(
                f"{needs_human_count} backlog item" f"{'s' if needs_human_count != 1 else ''}"
            )
        if docs_drift_signal_count:
            detail_parts.append(
                f"{docs_drift_signal_count} doc-drift item"
                f"{'s' if docs_drift_signal_count != 1 else ''}"
            )
        detail = " and ".join(detail_parts)
        headline = (
            f"## {detail} need your decision\n\n"
            "No fresh design-vs-implementation gaps this week, but the cron "
            "found items that need review before the queue is clean. See the "
            "backlog and doc-drift sections below."
        )
    else:
        repo_lines = "\n".join(f"- **{r}**: {n}" for r, n in sorted(by_repo.items()))
        title_lines = "\n".join(f"  - {t}" for t in titles)
        headline = (
            f"## {total} issue{'s' if total != 1 else ''} ready to upload\n\n"
            f"{repo_lines}\n\n"
            "### Titles\n"
            f"{title_lines}\n"
        )

    skipped_note = (
        f"\n_{skipped_count} repo decision(s) skipped uploading (defer / no-new-work / sync failure)._\n"
        if skipped_count
        else ""
    )

    backlog_section = format_backlog_section(backlog)
    docs_drift_section = format_docs_drift_section(docs_drift)
    scorecard_section = format_scorecard_section(scorecard)

    next_action = (
        ""
        if total == 0
        else f"""

## Next action — upload the queued issues

1. Open the packet to review the candidate set:

   ```
   open "{packet_path}"
   ```

2. (Optional) edit `config/repo_review_feedback.json` to revise/drop/defer specific candidates.

3. Upload the approved issues to the remote repos:

   ```
   cd "{workflows_steward_root}"
   python scripts/upload_repo_review_issues.py \\
       --queue "{queue_path}" \\
       --apply
   ```
"""
    )

    body = f"""# Weekly repo-review packet ready — {today}

{headline}
{skipped_note}{next_action}{backlog_section}{docs_drift_section}{scorecard_section}
## When you're done

Delete this file once you've acted on the queued issues AND the backlog:

```
rm "{target}"
```

---

## Cycle artifacts

- Packet: `{packet_path}`
- Queue: `{queue_path}`
- Output dir: `{output_dir}`
- Generated: {today} (UTC)

If this file isn't deleted by next Wednesday's cron run, that run will overwrite it with the next cycle's summary.
"""
    target.write_text(body, encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="path to <output_dir>/ (where packet + queue live)",
    )
    parser.add_argument(
        "--queue",
        type=Path,
        required=True,
        help="path to approved-issue-queue.json",
    )
    parser.add_argument(
        "--workflows-steward-root",
        type=Path,
        default=None,
        help="path to Workflows-steward checkout (default: 3 parents up from --output-dir, i.e. <root>/docs/reports/repo-review/.. = <root>/docs/reports = .. = <root>/docs = .. = <root>)",
    )
    parser.add_argument(
        "--backlog-scan",
        type=Path,
        default=None,
        help="path to backlog-scan.json from scripts/repo_review_backlog_scan.py "
        "(default: <output_dir>/backlog-scan.json if present); when present, "
        "adds a 'Backlog needing your attention' section to the desktop file",
    )
    parser.add_argument(
        "--docs-drift-scan",
        type=Path,
        default=None,
        help="path to docs-drift-scan.json from scripts/repo_review_docs_drift_scan.py "
        "(default: <output_dir>/docs-drift-scan.json if present); when present, "
        "adds a 'Doc drift detected' section to the desktop file",
    )
    parser.add_argument(
        "--scorecard-scan",
        type=Path,
        default=None,
        help="path to scorecard-scan.json from scripts/repo_review_scorecard.py "
        "(default: <output_dir>/scorecard-scan.json if present); when present, "
        "adds a 'Scorecard findings need explicit approval' section to the desktop file",
    )
    parser.add_argument(
        "--skip-notification",
        action="store_true",
        help="suppress the macOS notification (still writes the desktop file)",
    )
    parser.add_argument(
        "--skip-desktop",
        action="store_true",
        help="suppress the desktop file (still shows the notification)",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    queue_path = args.queue.resolve()
    packet_path = output_dir / "human-decision-packet.md"
    # output_dir is typically <root>/docs/reports/repo-review/, so the steward
    # root is 3 levels up. Walk parents safely instead of guessing.
    workflows_steward_root = (
        args.workflows_steward_root.resolve()
        if args.workflows_steward_root
        else output_dir.parent.parent.parent.resolve()
    )

    queue = load_queue(queue_path)
    summary = summarize_queue(queue)

    # Default backlog path is alongside the queue; coordinator writes it there.
    backlog_path = (
        args.backlog_scan if args.backlog_scan is not None else output_dir / "backlog-scan.json"
    )
    backlog = load_backlog_scan(backlog_path)

    docs_drift_path = (
        args.docs_drift_scan
        if args.docs_drift_scan is not None
        else output_dir / "docs-drift-scan.json"
    )
    docs_drift = load_docs_drift_scan(docs_drift_path)
    scorecard_path = (
        args.scorecard_scan
        if args.scorecard_scan is not None
        else output_dir / "scorecard-scan.json"
    )
    scorecard = load_scorecard_scan(scorecard_path)
    auto_labeled_count = len(backlog.get("auto_labeled", []) or [])
    needs_human_count = len(backlog.get("needs_human", []) or [])
    backlog_count = auto_labeled_count + needs_human_count

    total = summary["total"]
    by_repo_str = ", ".join(
        f"{r.split('/')[-1]} ({n})" for r, n in sorted(summary["by_repo"].items())
    )

    # Auto-labeled items are FYI — they don't trigger an action-required ping.
    action_required = (total > 0) or (needs_human_count > 0)

    if not args.skip_notification:
        if not action_required and backlog_count == 0:
            display_notification(
                title="Repo-review: clean week",
                subtitle="No fresh gaps, no backlog rot",
                message="No action required. Next run: next Wednesday.",
            )
        elif not action_required:
            display_notification(
                title="Repo-review: clean week",
                subtitle=f"Auto-labeled {auto_labeled_count} stale backlog item{'s' if auto_labeled_count != 1 else ''}",
                message="No action required — opener will pick them up next.",
            )
        elif total == 0:
            display_notification(
                title=f"Repo-review: {needs_human_count} backlog decision{'s' if needs_human_count != 1 else ''} needed",
                subtitle="No fresh upload queue this week",
                message="Action required — see ~/Desktop/REPO-REVIEW-ACTION-NEEDED.md",
            )
        else:
            extras = []
            if needs_human_count:
                extras.append(f"{needs_human_count} backlog")
            if auto_labeled_count:
                extras.append(f"{auto_labeled_count} auto-labeled")
            suffix = f" (+{', '.join(extras)})" if extras else ""
            display_notification(
                title=f"Repo-review: {total} issue{'s' if total != 1 else ''} to upload{suffix}",
                subtitle=by_repo_str or "Review packet for details",
                message="Action required — see ~/Desktop/REPO-REVIEW-ACTION-NEEDED.md",
            )

    if not args.skip_desktop:
        target = write_desktop_reminder(
            queue_summary=summary,
            backlog=backlog,
            docs_drift=docs_drift,
            scorecard=scorecard,
            packet_path=packet_path,
            queue_path=queue_path,
            output_dir=output_dir,
            workflows_steward_root=workflows_steward_root,
        )
        print(f"[notify] wrote {target}")

    docs_drift_total = (docs_drift or {}).get("total_drift_instances", 0) or 0
    docs_drift_repos = sum(
        1 for b in (docs_drift or {}).get("by_repo") or [] if b.get("drift_instances")
    )
    scorecard_total = (scorecard or {}).get("total_findings", 0) or 0
    scorecard_repos = sum(1 for b in (scorecard or {}).get("by_repo") or [] if b.get("findings"))
    print(
        f"[notify] {total} issue(s) ready, {summary['skipped_count']} repo decision(s) skipped, "
        f"{auto_labeled_count} backlog auto-labeled, {needs_human_count} backlog need decision, "
        f"{docs_drift_total} doc-drift instance(s) across {docs_drift_repos} repo(s), "
        f"{scorecard_total} scorecard finding(s) across {scorecard_repos} repo(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
