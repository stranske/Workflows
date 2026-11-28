"""No live workflow, script or tool refers to the retired Auto-Pilot workflow or label.

Auto-Pilot (`agents-auto-pilot.yml`, label `agents:auto-pilot`) was retired in #5379. The
cohesion review of 2026-11-28 found leftovers that skipped issues, dispatched a workflow that
no longer exists, and labelled follow-ups so intake ignored them. This keeps them out.

`agents:auto-pilot-pause` and `agents:auto-pilot-failed` are NOT matched: the format guard,
optimizer and opener lane still use the pause label as the issue-format hold.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIVE_PATHS = [
    ".github/workflows",
    ".github/scripts",
    "templates/consumer-repo/.github/workflows",
    "templates/consumer-repo/.github/scripts",
    "scripts",
    "tools",
    "templates/consumer-repo/scripts",
    "templates/consumer-repo/tools",
]
PATTERN = re.compile(r"agents-auto-pilot|agents:auto-pilot(?![-\w])")
# Legacy markers that must keep matching what retired Auto-Pilot already wrote.
ALLOWED = {
    # Reuse-marker workflow tag on issue bodies Auto-Pilot formatted; removing it would
    # re-derive formatting for every such body.
    "scripts/langchain/issue_formatter.py",
    # Label inventory used by the label cleaner.
    "scripts/cleanup_labels.py",
}


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "--", *LIVE_PATHS],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    return [
        line
        for line in out.splitlines()
        if "/__tests__/" not in line
        and line.endswith((".yml", ".yaml", ".js", ".py", ".txt"))
        and (ROOT / line).exists()
    ]


def test_no_live_reference_to_retired_auto_pilot() -> None:
    offenders = []
    for rel in _tracked_files():
        if rel in ALLOWED:
            continue
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            if PATTERN.search(line):
                offenders.append(f"{rel}:{number}: {line.strip()[:100]}")
    assert offenders == [], "retired Auto-Pilot references:\n" + "\n".join(offenders)


def test_allowlisted_legacy_markers_still_exist() -> None:
    for rel in ALLOWED:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert PATTERN.search(text), f"{rel} no longer needs its allowlist entry"
