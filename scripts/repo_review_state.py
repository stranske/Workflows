"""Per-repo state file for the weekly review system.

The state file lives at:

    <output_dir>/round2/<repo_safe>/state.json

Per the design discussion: state is repo-scoped. There is NO global state
file enumerating all repos. If anything goes wrong with one repo, the
remediation work is contained to that repo's directory. Cross-repo views
are computed by enumerating per-repo state files at read time, never by
maintaining a single source of truth across repos.

The state file tracks:
  - the latest run's lifecycle (round-1 → round-2 → human review → upload),
  - per-attempt history (start/end timestamps, outcomes, error if any),
  - pinned issues — known recurring problems for this repo that the
    coordinator should surface to the human packet rather than retry blindly.

The schema is intentionally small. The converged.json and findings.json
files remain the source of truth for content; this state file is operational
metadata only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STATE_SCHEMA_VERSION = "v1"

VALID_STATUSES = {
    "fresh",  # never run
    "round1-running",  # at least one round-1 agent in flight
    "round1-complete",  # both round-1 findings on disk, validated
    "round1-failed",  # one or both round-1 agents failed past retries
    "round2-running",  # negotiation in progress
    "round2-converged",  # converged.json written, ready for human review
    "round2-deadlocked",  # converged.json written WITH deadlocked items
    "round2-failed",  # negotiation aborted past retries
    "human-review-queued",  # waiting on feedback config update
    "approved-pending-upload",  # feedback says approve, queue items waiting
    "uploaded",  # remote issues created for this cycle
}


def _validate_status(status: str) -> str:
    if status not in VALID_STATUSES:
        raise ValueError(f"unknown status {status!r}; valid: {sorted(VALID_STATUSES)}")
    return status


@dataclass
class AttemptRecord:
    started_at: str
    completed_at: str = ""
    phase: str = ""  # round-1 | round-2 | upload
    agent: str = ""  # codex | claude | runner | uploader
    succeeded: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "phase": self.phase,
            "agent": self.agent,
            "succeeded": self.succeeded,
            "notes": self.notes,
        }


@dataclass
class PinnedProblem:
    """A known recurring problem worth surfacing instead of retrying blindly.

    Examples:
      - "Codex round-1 produces empty test_refs without prompting" — surfaced
        after observing the same failure across multiple weeks.
      - "Round-2 deadlocks on candidate X every cycle" — needs human triage.

    The coordinator surfaces these in the human packet so they're visible.
    """

    title: str
    first_seen: str
    last_seen: str = ""
    occurrences: int = 1
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen or self.first_seen,
            "occurrences": self.occurrences,
            "notes": self.notes,
        }


@dataclass
class RepoReviewState:
    schema_version: str
    repo: str
    status: str
    cycle_started_at: str
    cycle_updated_at: str
    last_attempt: AttemptRecord | None = None
    attempts: list[AttemptRecord] = field(default_factory=list)
    pinned_problems: list[PinnedProblem] = field(default_factory=list)
    round1_findings: dict[str, str] = field(default_factory=dict)  # agent → path
    round2_converged_path: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "repo": self.repo,
            "status": self.status,
            "cycle_started_at": self.cycle_started_at,
            "cycle_updated_at": self.cycle_updated_at,
            "last_attempt": (self.last_attempt.to_dict() if self.last_attempt else None),
            "attempts": [a.to_dict() for a in self.attempts],
            "pinned_problems": [p.to_dict() for p in self.pinned_problems],
            "round1_findings": self.round1_findings,
            "round2_converged_path": self.round2_converged_path,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def state_file_path(output_dir: Path, repo: str) -> Path:
    safe = repo.replace("/", "__")
    return output_dir / "round2" / safe / "state.json"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------


def load_state(output_dir: Path, repo: str) -> RepoReviewState:
    """Load the per-repo state file. If absent, return a fresh state object."""
    path = state_file_path(output_dir, repo)
    if not path.is_file():
        ts = now_iso()
        return RepoReviewState(
            schema_version=STATE_SCHEMA_VERSION,
            repo=repo,
            status="fresh",
            cycle_started_at=ts,
            cycle_updated_at=ts,
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return _state_from_dict(data)


def save_state(output_dir: Path, state: RepoReviewState) -> Path:
    path = state_file_path(output_dir, state.repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    state.cycle_updated_at = now_iso()
    path.write_text(json.dumps(state.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def _state_from_dict(data: dict[str, Any]) -> RepoReviewState:
    last_attempt_data = data.get("last_attempt")
    last_attempt = (
        AttemptRecord(**last_attempt_data) if isinstance(last_attempt_data, dict) else None
    )
    attempts = [AttemptRecord(**a) for a in (data.get("attempts") or []) if isinstance(a, dict)]
    pinned = [
        PinnedProblem(**p) for p in (data.get("pinned_problems") or []) if isinstance(p, dict)
    ]
    return RepoReviewState(
        schema_version=str(data.get("schema_version", STATE_SCHEMA_VERSION)),
        repo=str(data.get("repo", "")),
        status=_validate_status(str(data.get("status", "fresh"))),
        cycle_started_at=str(data.get("cycle_started_at", now_iso())),
        cycle_updated_at=str(data.get("cycle_updated_at", now_iso())),
        last_attempt=last_attempt,
        attempts=attempts,
        pinned_problems=pinned,
        round1_findings=dict(data.get("round1_findings") or {}),
        round2_converged_path=str(data.get("round2_converged_path", "")),
        notes=str(data.get("notes", "")),
    )


# ---------------------------------------------------------------------------
# Mutation helpers
# ---------------------------------------------------------------------------


def begin_attempt(state: RepoReviewState, *, phase: str, agent: str) -> AttemptRecord:
    attempt = AttemptRecord(started_at=now_iso(), phase=phase, agent=agent)
    state.last_attempt = attempt
    state.attempts.append(attempt)
    return attempt


def finish_attempt(
    state: RepoReviewState,
    attempt: AttemptRecord,
    *,
    succeeded: bool,
    notes: str = "",
) -> None:
    attempt.completed_at = now_iso()
    attempt.succeeded = succeeded
    if notes:
        attempt.notes = notes


def transition(state: RepoReviewState, *, status: str, note: str = "") -> None:
    state.status = _validate_status(status)
    if note:
        state.notes = note


def record_round1_finding(state: RepoReviewState, agent: str, findings_path: Path) -> None:
    state.round1_findings[agent] = str(findings_path.resolve())


def record_round2_converged(state: RepoReviewState, converged_path: Path) -> None:
    state.round2_converged_path = str(converged_path.resolve())


def add_pinned_problem(state: RepoReviewState, *, title: str, notes: str = "") -> None:
    """Add or bump a pinned problem (recurring issue) for this repo."""
    ts = now_iso()
    for existing in state.pinned_problems:
        if existing.title == title:
            existing.last_seen = ts
            existing.occurrences += 1
            if notes:
                existing.notes = notes
            return
    state.pinned_problems.append(
        PinnedProblem(title=title, first_seen=ts, last_seen=ts, notes=notes)
    )


# ---------------------------------------------------------------------------
# CLI for inspection
# ---------------------------------------------------------------------------


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument(
        "--show",
        action="store_true",
        help="Print current state (default action when no mutation flag is given).",
    )
    parser.add_argument(
        "--status",
        choices=sorted(VALID_STATUSES),
        help="Transition the state to this status (advanced; normally written by runners).",
    )
    parser.add_argument(
        "--add-pinned",
        metavar="TITLE",
        help="Add or bump a pinned problem with the given title.",
    )
    parser.add_argument(
        "--note",
        default="",
        help="Free-form note attached to the transition or pinned problem.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    state = load_state(output_dir, args.repo)
    mutated = False
    if args.status:
        transition(state, status=args.status, note=args.note)
        mutated = True
    if args.add_pinned:
        add_pinned_problem(state, title=args.add_pinned, notes=args.note)
        mutated = True
    if mutated:
        save_state(output_dir, state)

    if mutated or args.show or not (args.status or args.add_pinned):
        print(json.dumps(state.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
