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


def write_desktop_reminder(
    *,
    queue_summary: dict[str, Any],
    packet_path: Path,
    queue_path: Path,
    output_dir: Path,
    workflows_steward_root: Path,
) -> Path:
    """Write a persistent reminder file to the user's desktop.

    Overwrites any prior file (we keep only the latest cycle's reminder).
    """
    desktop = Path(os.path.expanduser("~/Desktop"))
    desktop.mkdir(parents=True, exist_ok=True)
    target = desktop / DESKTOP_FILENAME

    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    total = queue_summary["total"]
    by_repo = queue_summary["by_repo"]
    skipped_count = queue_summary["skipped_count"]
    titles = queue_summary["issue_titles"]

    if total == 0:
        headline = (
            "## ✓ No issues queued this week\n\n"
            "The cron ran but found no fresh design-vs-implementation gaps "
            "after dedup against existing issues. No action required — "
            "the system will run again next Thursday."
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

    body = f"""# Weekly repo-review packet ready — {today}

{headline}
{skipped_note}
## Next action

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

4. Delete this file once you've uploaded (or chosen to skip the cycle):

   ```
   rm "{target}"
   ```

---

## Cycle artifacts

- Packet: `{packet_path}`
- Queue: `{queue_path}`
- Output dir: `{output_dir}`
- Generated: {today} (UTC)

If this file isn't deleted by next Thursday's cron run, that run will overwrite it with the next cycle's summary.
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

    total = summary["total"]
    by_repo_str = ", ".join(
        f"{r.split('/')[-1]} ({n})" for r, n in sorted(summary["by_repo"].items())
    )

    if not args.skip_notification:
        if total == 0:
            display_notification(
                title="Repo-review: no issues this week",
                subtitle="Cycle complete — nothing to upload",
                message="See packet for details. Next run: next Thursday.",
            )
        else:
            display_notification(
                title=f"Repo-review: {total} issue{'s' if total != 1 else ''} ready to upload",
                subtitle=by_repo_str or "Review packet for details",
                message="Action required — see ~/Desktop/REPO-REVIEW-ACTION-NEEDED.md",
            )

    if not args.skip_desktop:
        target = write_desktop_reminder(
            queue_summary=summary,
            packet_path=packet_path,
            queue_path=queue_path,
            output_dir=output_dir,
            workflows_steward_root=workflows_steward_root,
        )
        print(f"[notify] wrote {target}")

    print(f"[notify] {total} issue(s) ready, {summary['skipped_count']} repo decision(s) skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
