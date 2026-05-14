"""Sequential per-repo coordinator for the weekly repo-review system.

Drives the full Phase-4 production flow:

1. Run the evaluator preflight (produces review-inputs.md + remote-progress.md
   + archive-progress.md per repo).
2. For each active repo, sequentially:
   a. **Skip-this-cycle gate**: borrowed from the Workflows campaign-controller
      pattern. Compare round-1 candidate fingerprint to the prior cycle's
      converged set. If materially identical, skip round-2 + upload and
      surface a "no fresh signal — coverage stable" note. Saves real compute
      on stable repos.
   b. Round-1 runner — refresh map, fan out Codex + Claude in parallel.
   c. Round-2 runner — negotiate, synthesize converged.json.
   d. Update per-repo state file.
3. Final evaluator pass produces the human-decision-packet.md with all repos'
   sections rendered.

Sequential execution is intentional (per the user's "1 repo per hour" rate-
limit-conservative cadence). Inter-repo state is held in per-repo state.json
files; there is NO global state file.

Usage:

    python scripts/repo_review_coordinator.py \\
        --output-dir docs/reports/repo-review \\
        --registry config/repo_review_registry.json

Optional `--repos REPO [REPO ...]` runs only the named subset; default is all
`active` repos in the registry.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.repo_review_evaluator import load_registry
    from scripts.repo_review_state import (
        load_state,
        save_state,
        transition,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_review_evaluator import load_registry  # type: ignore[no-redef]
    from repo_review_state import (  # type: ignore[no-redef]
        load_state,
        save_state,
        transition,
    )


# ---------------------------------------------------------------------------
# Skip-this-cycle gate
# ---------------------------------------------------------------------------


def candidate_fingerprint(candidates: list[dict[str, Any]]) -> tuple[tuple[str, ...], ...]:
    """Stable fingerprint: sorted tuple of (title, gap, primary_design_ref) tuples.

    Round-2 framing nuances (origin, source-detail, etc.) are deliberately
    NOT in the fingerprint — semantic identity should match across cycles
    even if the runner relabels the source agent.
    """
    out: list[tuple[str, ...]] = []
    for cand in candidates:
        title = str(cand.get("title") or "").strip()
        gap = str(cand.get("gap") or "").strip()
        design_refs = cand.get("design_refs") or []
        primary_ref = str(design_refs[0]) if design_refs else ""
        out.append((title, gap, primary_ref))
    return tuple(sorted(out))


def archive_prior_cycle(output_dir: Path) -> dict[str, Any]:
    """Move the previous cycle's `round1/`, `round2/`, and queue artifacts into
    `<output_dir>/archive/<YYYY-MM-DD>/` so the skip-this-cycle gate has a prior
    fingerprint and the new cycle starts on a clean slate.

    The archived date is inferred from the newest `converged.json`'s mtime in
    the prior `round2/` tree. If no `round2/converged.json` exists, archiving
    is a no-op (nothing to preserve). Idempotent: re-running on an already-
    archived cycle is a no-op once the source dirs are gone.

    Returns a dict with `archived` (bool), `archive_date` (str or None),
    `moved_paths` (list of str), and `notes` (str).
    """
    import shutil

    summary: dict[str, Any] = {
        "archived": False,
        "archive_date": None,
        "moved_paths": [],
        "notes": "",
    }

    round2_dir = output_dir / "round2"
    if not round2_dir.is_dir():
        summary["notes"] = "no prior round2/ to archive"
        return summary

    # Find the newest converged.json under round2/<repo>/
    converged_paths = list(round2_dir.glob("*/converged.json"))
    if not converged_paths:
        summary["notes"] = "round2/ exists but contains no converged.json files"
        return summary

    newest_mtime = max(p.stat().st_mtime for p in converged_paths)
    archive_date = datetime.fromtimestamp(newest_mtime, tz=UTC).strftime("%Y-%m-%d")

    archive_dir = output_dir / "archive" / archive_date
    archive_dir.mkdir(parents=True, exist_ok=True)

    # If the archive target already has round2/, append a suffix so we don't clobber
    # a same-day re-run. (Multiple runs on the same day get -01, -02 suffixes.)
    if (archive_dir / "round2").exists():
        suffix = 1
        while (output_dir / "archive" / f"{archive_date}-{suffix:02d}").exists():
            suffix += 1
        archive_dir = output_dir / "archive" / f"{archive_date}-{suffix:02d}"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_date = archive_dir.name

    moved: list[str] = []
    for name in ("round1", "round2"):
        src = output_dir / name
        if src.exists():
            dst = archive_dir / name
            shutil.move(str(src), str(dst))
            moved.append(str(dst.relative_to(output_dir)))

    queue = output_dir / "approved-issue-queue.json"
    if queue.is_file():
        dst = archive_dir / "approved-issue-queue.json"
        shutil.move(str(queue), str(dst))
        moved.append(str(dst.relative_to(output_dir)))

    summary["archived"] = True
    summary["archive_date"] = archive_date
    summary["moved_paths"] = moved
    summary["notes"] = (
        f"archived prior cycle (mtime-inferred date={archive_date}) — moved {len(moved)} paths"
    )
    return summary


def prior_converged_for_skip_check(output_dir: Path, repo: str) -> dict[str, Any] | None:
    """Look for a previously-archived converged.json for this repo to compare against.

    Convention: prior cycles' converged sets are archived under
    `<output_dir>/archive/<YYYY-MM-DD>/round2/<repo_safe>/converged.json`.
    If no archive exists, returns None and the gate cannot fire.
    """
    safe = repo.replace("/", "__")
    archive_root = output_dir / "archive"
    if not archive_root.is_dir():
        return None
    candidates: list[tuple[str, Path]] = []
    for cycle_dir in sorted(archive_root.iterdir(), reverse=True):
        if not cycle_dir.is_dir():
            continue
        path = cycle_dir / "round2" / safe / "converged.json"
        if path.is_file():
            candidates.append((cycle_dir.name, path))
            break  # newest only (we sorted reverse)
    if not candidates:
        return None
    try:
        return json.loads(candidates[0][1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def round1_fingerprint_from_findings(
    output_dir: Path, repo: str, agents: list[str]
) -> tuple[tuple[str, ...], ...] | None:
    """Compute the round-1 fingerprint by reading both agents' findings.json."""
    safe = repo.replace("/", "__")
    fingerprints: list[tuple[str, ...]] = []
    for agent in agents:
        path = output_dir / "round1" / agent / safe / "findings.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        for cand in data.get("candidates") or []:
            title = str(cand.get("title") or "").strip()
            gap = str(cand.get("gap") or "").strip()
            design_refs = cand.get("design_refs") or []
            primary_ref = str(design_refs[0]) if design_refs else ""
            fingerprints.append((title, gap, primary_ref))
    return tuple(sorted(fingerprints))


def should_skip_cycle(
    output_dir: Path,
    repo: str,
    agents: list[str],
) -> tuple[bool, str]:
    """Decide whether to short-circuit round-2 + upload for this repo.

    Returns (should_skip, reason). Skip fires only when:
      - prior converged set exists, AND
      - round-1 fingerprint is identical to prior converged + meta + deadlocked
        candidate set fingerprint, AND
      - prior wasn't itself a skip outcome (don't compound).
    """
    prior = prior_converged_for_skip_check(output_dir, repo)
    if prior is None:
        return False, "no prior cycle to compare against"
    if prior.get("synthesized_via_skip_gate"):
        return False, "prior cycle was itself a skip outcome — re-run to confirm"

    prior_candidates = list(prior.get("converged_candidates") or [])
    prior_meta = prior.get("meta_candidate")
    if isinstance(prior_meta, dict):
        prior_candidates.append(prior_meta)
    for dl in prior.get("deadlocked_candidates") or []:
        if isinstance(dl, dict):
            prior_candidates.append(dl)

    prior_fp = candidate_fingerprint(prior_candidates)
    current_fp = round1_fingerprint_from_findings(output_dir, repo, agents)
    if current_fp is None:
        return False, "round-1 findings missing — cannot compute fingerprint"
    if not current_fp:
        return False, "round-1 produced 0 candidates — handle via no-new-work path, not skip"
    if prior_fp == current_fp:
        return True, (
            f"round-1 fingerprint matches prior cycle ({len(current_fp)} candidate(s) unchanged)"
        )
    return False, (
        f"round-1 fingerprint differs from prior cycle "
        f"(prior={len(prior_fp)}, current={len(current_fp)} candidate(s))"
    )


def write_skip_converged(output_dir: Path, repo: str, reason: str) -> Path:
    """Synthesize a 'skip-this-cycle' converged.json so downstream evaluator
    surfaces a clear note instead of empty round-2 state."""
    safe = repo.replace("/", "__")
    converged_path = output_dir / "round2" / safe / "converged.json"
    converged_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "v1",
        "repo": repo,
        "turns_completed": 0,
        "round1_sources": [],
        "converged_candidates": [],
        "deadlocked_candidates": [],
        "dropped_candidates": [],
        "meta_candidate": None,
        "meta_status": "absent",
        "deadlocked_meta": None,
        "no_new_work_justifications": [],
        "negotiation_log": [],
        "synthesized_at": datetime.now(UTC).isoformat(),
        "synthesized_via_skip_gate": True,
        "skip_reason": reason,
    }
    converged_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return converged_path


# ---------------------------------------------------------------------------
# Subprocess wrappers
# ---------------------------------------------------------------------------


@dataclass
class StepResult:
    name: str
    succeeded: bool
    duration_seconds: float
    notes: str = ""


def run_subprocess(
    cmd: list[str],
    *,
    cwd: Path,
    log_path: Path,
    name: str,
    timeout: int,
) -> StepResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC)
    with log_path.open("w", encoding="utf-8") as fh:
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                stdout=fh,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            duration = (datetime.now(UTC) - started).total_seconds()
            return StepResult(
                name=name,
                succeeded=False,
                duration_seconds=duration,
                notes=f"timed out after {timeout}s; log: {log_path}",
            )
    duration = (datetime.now(UTC) - started).total_seconds()
    if result.returncode != 0:
        return StepResult(
            name=name,
            succeeded=False,
            duration_seconds=duration,
            notes=f"exit {result.returncode}; log: {log_path}",
        )
    return StepResult(
        name=name,
        succeeded=True,
        duration_seconds=duration,
        notes=f"log: {log_path}",
    )


# ---------------------------------------------------------------------------
# Per-repo coordinator
# ---------------------------------------------------------------------------


def coordinate_repo(
    *,
    repo: str,
    output_dir: Path,
    workflows_steward_root: Path,
    registry_path: Path,
    agents: list[str],
    log_dir: Path,
    round1_timeout: int,
    round2_timeout: int,
    skip_gate_enabled: bool,
) -> dict[str, Any]:
    """Run the full Phase-4 flow for one repo. Returns a small report dict."""
    safe = repo.replace("/", "__")
    repo_log_dir = log_dir / safe
    repo_log_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "repo": repo,
        "started_at": datetime.now(UTC).isoformat(),
        "round1": None,
        "round2": None,
        "skip_gate_fired": False,
        "skip_reason": "",
    }

    # 1. Round-1 fan-out (refreshes map + spawns Codex + Claude in parallel).
    r1_cmd = [
        sys.executable,
        str(workflows_steward_root / "scripts" / "repo_review_round1_runner.py"),
        "--repo",
        repo,
        "--output-dir",
        str(output_dir),
        "--registry",
        str(registry_path),
        "--agents",
        *agents,
        "--turn-timeout",
        str(round1_timeout),
    ]
    r1_result = run_subprocess(
        r1_cmd,
        cwd=workflows_steward_root,
        log_path=repo_log_dir / "round1-runner.log",
        name="round-1",
        timeout=round1_timeout + 1500,
    )
    report["round1"] = {
        "succeeded": r1_result.succeeded,
        "duration_seconds": r1_result.duration_seconds,
        "notes": r1_result.notes,
    }
    if not r1_result.succeeded:
        return report

    # 2. Skip-this-cycle gate (after round-1, before round-2).
    if skip_gate_enabled:
        should_skip, reason = should_skip_cycle(output_dir, repo, agents)
        report["skip_gate_fired"] = should_skip
        report["skip_reason"] = reason
        if should_skip:
            converged_path = write_skip_converged(output_dir, repo, reason)
            state = load_state(output_dir, repo)
            transition(
                state,
                status="round2-converged",
                note=f"skip-this-cycle gate fired: {reason}",
            )
            save_state(output_dir, state)
            print(
                f"[coordinator] {repo}: SKIP gate fired ({reason}); "
                f"converged.json written at {converged_path.name}"
            )
            return report

    # 3. Round-2 negotiation + synthesis.
    # NB: round-2 runner takes `--agents` as a SINGLE comma-separated string
    # (`"codex,claude"`), unlike round-1 runner which takes `nargs="+"`. Don't
    # spread `*agents` here — that becomes positional args round-2 rejects.
    r2_cmd = [
        sys.executable,
        str(workflows_steward_root / "scripts" / "repo_review_round2_runner.py"),
        "--repo",
        repo,
        "--output-dir",
        str(output_dir),
        "--agents",
        ",".join(agents),
        "--turn-timeout",
        str(round2_timeout),
    ]
    r2_result = run_subprocess(
        r2_cmd,
        cwd=workflows_steward_root,
        log_path=repo_log_dir / "round2-runner.log",
        name="round-2",
        timeout=round2_timeout + 1500,
    )
    report["round2"] = {
        "succeeded": r2_result.succeeded,
        "duration_seconds": r2_result.duration_seconds,
        "notes": r2_result.notes,
    }
    if not r2_result.succeeded:
        return report

    # 4. Body-writer pass (iter-9 lesson): convert structured candidates into
    #    AGENT_ISSUE_FORMAT.md-compliant agent-ready issue bodies. The local
    #    repo is already at origin head from the round-1-runner sync step.
    bw_cmd = [
        sys.executable,
        str(workflows_steward_root / "scripts" / "repo_review_body_writer.py"),
        "--repo",
        repo,
        "--output-dir",
        str(output_dir),
        "--registry",
        str(registry_path),
        # `claude` is required (not `codex`) when the body-writer runs nested
        # under `codex exec` — codex's `apply_patch` and `exec_command` tools
        # both go through a fs sandbox helper that calls `sandbox-exec` to
        # apply a sub-sandbox profile. macOS does not allow nested
        # `sandbox-exec` calls and the helper fails with status 71:
        # "sandbox_apply: Operation not permitted". The body-writer specifically
        # needs to MODIFY an existing converged.json (round-1/round-2 agents
        # write fresh files and lucked through with apply_patch retries; the
        # body-writer's update-file path consistently EPERMs). Claude's Edit
        # tool writes directly without sandbox-exec wrapping and works in the
        # nested context. Empirically verified 2026-05-07 (attempt-7).
        "--agent",
        "claude",
        "--timeout",
        str(min(round2_timeout, 60 * 60)),
    ]
    bw_result = run_subprocess(
        bw_cmd,
        cwd=workflows_steward_root,
        log_path=repo_log_dir / "body-writer.log",
        name="body-writer",
        timeout=min(round2_timeout, 60 * 60) + 600,
    )
    report["body_writer"] = {
        "succeeded": bw_result.succeeded,
        "duration_seconds": bw_result.duration_seconds,
        "notes": bw_result.notes,
    }

    return report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    registry_path = Path(args.registry).resolve()
    workflows_steward_root = registry_path.parent.parent

    workspace_root, _excluded, repos, _archive_paths = load_registry(registry_path)
    target_repos: list[str]
    if args.repos:
        registry_set = {r.repo for r in repos}
        target_repos = [r for r in args.repos if r in registry_set]
        skipped = [r for r in args.repos if r not in registry_set]
        if skipped:
            print(
                f"[coordinator] skipping unregistered: {', '.join(skipped)}",
                file=sys.stderr,
            )
    else:
        target_repos = [r.repo for r in repos if r.status == "active"]

    if not target_repos:
        print("[coordinator] no active repos to process", file=sys.stderr)
        return 2

    log_dir = output_dir / "logs" / "coordinator"
    log_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"[coordinator] processing {len(target_repos)} repo(s) sequentially: "
        f"{', '.join(target_repos)}"
    )

    # 0. Auto-archive the prior cycle so the skip-this-cycle gate has a prior
    #    fingerprint and the new cycle starts clean. No-op if `<output_dir>/round2/`
    #    is absent or empty. Skip with --skip-auto-archive.
    if not args.skip_auto_archive:
        archive_summary = archive_prior_cycle(output_dir)
        if archive_summary["archived"]:
            print(
                f"[coordinator] auto-archive: {archive_summary['notes']} → "
                f"archive/{archive_summary['archive_date']}/"
            )
        else:
            print(f"[coordinator] auto-archive: skipped — {archive_summary['notes']}")

    # 1. Evaluator preflight (produces review-inputs.md, remote-progress.md, etc.).
    if not args.skip_preflight:
        print("[coordinator] running evaluator preflight")
        preflight_cmd = [
            sys.executable,
            str(workflows_steward_root / "scripts" / "repo_review_evaluator.py"),
            "--output-dir",
            str(output_dir),
        ]
        if args.skip_gitnexus_preflight:
            preflight_cmd.append("--skip-gitnexus-preflight")
        preflight_result = run_subprocess(
            preflight_cmd,
            cwd=workflows_steward_root,
            log_path=log_dir / "preflight.log",
            name="preflight",
            timeout=1200,
        )
        if not preflight_result.succeeded:
            print(
                f"[coordinator] preflight FAILED: {preflight_result.notes}",
                file=sys.stderr,
            )
            return 1

    # 2. Per-repo sequential coordination.
    reports: list[dict[str, Any]] = []
    for repo in target_repos:
        print(f"[coordinator] {repo}: starting per-repo flow")
        report = coordinate_repo(
            repo=repo,
            output_dir=output_dir,
            workflows_steward_root=workflows_steward_root,
            registry_path=registry_path,
            agents=list(args.agents),
            log_dir=log_dir,
            round1_timeout=args.round1_timeout,
            round2_timeout=args.round2_timeout,
            skip_gate_enabled=not args.disable_skip_gate,
        )
        reports.append(report)

    # 3. Build the approved-issue-queue.json from converged.json + feedback.
    #    Pure data assembly, no subprocess; safe to run even if some repos
    #    deadlocked (they're skipped by the queue builder's per-repo decision
    #    routing). The cron does NOT auto-upload — that requires --apply on
    #    the upload helper, which the human runs after reviewing the packet.
    feedback_path = workflows_steward_root / "config" / "repo_review_feedback.json"
    queue_out = output_dir / "approved-issue-queue.json"
    if feedback_path.is_file():
        try:
            from scripts.repo_review_queue_builder import (
                build_queue,  # type: ignore[import-not-found]
            )
        except ModuleNotFoundError:
            sys.path.insert(0, str(workflows_steward_root / "scripts"))
            from repo_review_queue_builder import build_queue  # type: ignore[no-redef]
        try:
            queue_data = build_queue(output_dir / "round2", feedback_path)
            queue_out.write_text(json.dumps(queue_data, indent=2) + "\n", encoding="utf-8")
            n = len(queue_data["issues"])
            print(f"[coordinator] queue-builder: wrote {n} issues → {queue_out.name}")
        except Exception as exc:  # pragma: no cover - never blocks the cycle
            print(f"[coordinator] queue-builder FAILED (non-fatal): {exc}", file=sys.stderr)
    else:
        print(
            f"[coordinator] queue-builder: skipping — feedback file absent at {feedback_path}",
            file=sys.stderr,
        )

    # 4. Final evaluator pass produces the human-decision-packet.md.
    print("[coordinator] running final evaluator pass to refresh packet")
    final_cmd = [
        sys.executable,
        str(workflows_steward_root / "scripts" / "repo_review_evaluator.py"),
        "--output-dir",
        str(output_dir),
        "--skip-gitnexus-preflight",  # maps already refreshed by round-1
    ]
    final_result = run_subprocess(
        final_cmd,
        cwd=workflows_steward_root,
        log_path=log_dir / "final-evaluator.log",
        name="final-evaluator",
        timeout=600,
    )

    # 5. Backlog scan: surface enhancement/feature issues that fell between
    #    the opener (selects by priority:* label) and the design-vs-impl review
    #    (selects by traced gap). Without this safety net, manually-created
    #    enhancement issues with no priority label sit invisible indefinitely
    #    (the Inv-Man-Intake #25/#26/#27 case from 2026-05-07).
    backlog_scan_path = output_dir / "backlog-scan.json"
    backlog_cmd = [
        sys.executable,
        str(workflows_steward_root / "scripts" / "repo_review_backlog_scan.py"),
        "--registry",
        str(registry_path),
        "--out",
        str(backlog_scan_path),
        # --apply means the cron actually adds the priority labels (default
        # priority:normal, or priority:low if the issue was created >90 days
        # ago with no milestone). Umbrellas/epics/blocked items are NOT
        # auto-labeled — they get surfaced for human decision instead.
        "--apply",
    ]
    backlog_result = run_subprocess(
        backlog_cmd,
        cwd=workflows_steward_root,
        log_path=log_dir / "backlog-scan.log",
        name="backlog-scan",
        timeout=300,  # 9 repos x roughly 30s of GitHub API time
    )
    if not backlog_result.succeeded:
        print(
            f"[coordinator] backlog-scan FAILED (non-fatal): {backlog_result.notes}",
            file=sys.stderr,
        )

    # 5b. Docs-drift scan: classify load-bearing claims in source-of-truth
    #     operational docs (README/AGENTS/CLAUDE/docs/ops/...) for drift vs
    #     current implementation. Issue #2090. Same non-fatal pattern as
    #     backlog-scan -- failures are logged but don't abort the cycle.
    docs_drift_path = output_dir / "docs-drift-scan.json"
    docs_drift_config = workflows_steward_root / "config" / "source_of_truth_docs.yml"
    if docs_drift_config.is_file():
        docs_drift_cmd = [
            sys.executable,
            str(workflows_steward_root / "scripts" / "repo_review_docs_drift_scan.py"),
            "--registry",
            str(registry_path),
            "--docs-config",
            str(docs_drift_config),
            "--out",
            str(docs_drift_path),
            "--workspace-root",
            str(workspace_root),
        ]
        docs_drift_result = run_subprocess(
            docs_drift_cmd,
            cwd=workflows_steward_root,
            log_path=log_dir / "docs-drift-scan.log",
            name="docs-drift-scan",
            timeout=1800,  # ~5-10 min across 9 repos with claude LLM calls per doc
        )
        if not docs_drift_result.succeeded:
            print(
                f"[coordinator] docs-drift-scan FAILED (non-fatal): {docs_drift_result.notes}",
                file=sys.stderr,
            )
    else:
        print(
            f"[coordinator] docs-drift-scan: skipping -- config not found at {docs_drift_config}",
            file=sys.stderr,
        )

    # 6. Surface the cycle outcome to the human reviewer (macOS notification +
    #    persistent desktop file). The cron does NOT auto-upload; humans must
    #    review the packet and run upload_repo_review_issues.py --apply. The
    #    desktop file includes both the upload queue AND the backlog scan so
    #    the human has one place to act each week.
    notify_cmd = [
        sys.executable,
        str(workflows_steward_root / "scripts" / "repo_review_notify.py"),
        "--output-dir",
        str(output_dir),
        "--queue",
        str(output_dir / "approved-issue-queue.json"),
        "--backlog-scan",
        str(backlog_scan_path),
        "--docs-drift-scan",
        str(docs_drift_path),
        "--workflows-steward-root",
        str(workflows_steward_root),
    ]
    notify_result = run_subprocess(
        notify_cmd,
        cwd=workflows_steward_root,
        log_path=log_dir / "notify.log",
        name="notify",
        timeout=60,
    )
    if not notify_result.succeeded:
        print(
            f"[coordinator] notify FAILED (non-fatal): {notify_result.notes}",
            file=sys.stderr,
        )

    # 6. Summary report on stderr (cron will capture).
    print("[coordinator] summary:")
    for report in reports:
        repo = report["repo"]
        if report.get("skip_gate_fired"):
            print(f"  - {repo}: SKIP gate fired ({report['skip_reason']})")
            continue
        r1 = report.get("round1") or {}
        r2 = report.get("round2") or {}
        r1_label = "ok" if r1.get("succeeded") else "FAIL"
        r2_label = "ok" if r2.get("succeeded") else ("FAIL" if r2 else "n/a")
        print(
            f"  - {repo}: round1={r1_label} round2={r2_label} "
            f"(r1 {int(r1.get('duration_seconds') or 0)}s, "
            f"r2 {int((r2 or {}).get('duration_seconds') or 0)}s)"
        )
    print(f"[coordinator] final evaluator: {'ok' if final_result.succeeded else 'FAIL'}")
    return (
        0
        if all(
            (r.get("round1") or {}).get("succeeded")
            and (r.get("skip_gate_fired") or (r.get("round2") or {}).get("succeeded"))
            for r in reports
        )
        else 1
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        required=True,
        help="output dir, e.g. docs/reports/repo-review",
    )
    parser.add_argument(
        "--registry",
        default="config/repo_review_registry.json",
        help="path to repo_review_registry.json",
    )
    parser.add_argument(
        "--repos",
        nargs="*",
        default=[],
        help="optional explicit repo subset (default: all active in registry)",
    )
    parser.add_argument(
        "--agents",
        nargs="+",
        default=["codex", "claude"],
        help="agent identifiers to use (default: codex claude)",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="skip the initial evaluator preflight (use existing inputs)",
    )
    parser.add_argument(
        "--skip-gitnexus-preflight",
        action="store_true",
        help="skip the GitNexus preflight inside the evaluator (round-1 still refreshes)",
    )
    parser.add_argument(
        "--round1-timeout",
        type=int,
        default=90 * 60,
        help="hard timeout per round-1 agent in seconds (default: 5400)",
    )
    parser.add_argument(
        "--round2-timeout",
        type=int,
        default=45 * 60,
        help="hard timeout per round-2 agent-turn in seconds (default: 2700)",
    )
    parser.add_argument(
        "--disable-skip-gate",
        action="store_true",
        help="run round-2 even when round-1 fingerprint matches prior cycle",
    )
    parser.add_argument(
        "--skip-auto-archive",
        action="store_true",
        help="do not move the prior cycle's round1/round2/queue into archive/<date>/ "
        "before starting (useful for re-running a cycle in place)",
    )
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
