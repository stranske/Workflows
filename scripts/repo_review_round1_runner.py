"""Round-1 fan-out runner for the weekly repo-review system.

Per repo, this runner:

1. Refreshes the GitNexus map BEFORE spawning agents (iter-2 lesson #1: avoid
   FTS lock contention while agents are querying).
2. Spawns Codex + Claude in parallel via ThreadPoolExecutor — different API
   backends, no shared rate limit.
3. Each agent gets a hard timeout (default 90 min). On timeout, the runner
   marks the agent's attempt failed and retries up to `--retries` times.
4. After both agents land, validates each findings.json against the round-1
   schema. Validation failure triggers retry.
5. Updates the per-repo state file (`<output_dir>/round2/<repo_safe>/state.json`)
   to `round1-complete` (both validated), `round1-failed` (any agent failed
   past retries), or leaves at `round1-running` if interrupted mid-flight.

The runner re-uses the agent-invocation primitives (`invoke_codex`,
`invoke_claude`) from `repo_review_round2_runner.py` so behavior stays
consistent across rounds.

Usage:

    python scripts/repo_review_round1_runner.py \\
        --repo stranske/Manager-Database \\
        --output-dir docs/reports/repo-review \\
        --registry config/repo_review_registry.json

CLI flags mirror the round-2 runner where applicable.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

# Re-use agent invocation + state primitives from sibling scripts.
try:
    from scripts.repo_review_evaluator import (
        collect_gitnexus_map,
        load_registry,
        run_gitnexus_analyze,
    )
    from scripts.repo_review_round1_schema import validate_findings
    from scripts.repo_review_round2_runner import (
        invoke_agent,
    )
    from scripts.repo_review_state import (
        begin_attempt,
        finish_attempt,
        load_state,
        record_round1_finding,
        save_state,
        transition,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_review_evaluator import (  # type: ignore[no-redef]
        collect_gitnexus_map,
        load_registry,
        run_gitnexus_analyze,
    )
    from repo_review_round1_schema import (  # type: ignore[no-redef]
        validate_findings,
    )
    from repo_review_round2_runner import (  # type: ignore[no-redef]
        invoke_agent,
    )
    from repo_review_state import (  # type: ignore[no-redef]
        begin_attempt,
        finish_attempt,
        load_state,
        record_round1_finding,
        save_state,
        transition,
    )


PRODUCTION_AGENTS: tuple[str, ...] = ("codex", "claude")
DEFAULT_TURN_TIMEOUT_SECONDS = 90 * 60  # 90 min hard ceiling per agent


@dataclass
class AgentResult:
    agent: str
    findings_path: Path
    log_path: Path
    succeeded: bool
    error: str = ""
    spawned: bool = False


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def round1_findings_path(output_dir: Path, agent: str, repo: str) -> Path:
    safe = repo.replace("/", "__")
    return output_dir / "round1" / agent / safe / "findings.json"


def review_inputs_path(output_dir: Path, repo: str) -> Path:
    safe = repo.replace("/", "__")
    return output_dir / "repos" / safe / "review-inputs.md"


def round1_prompt_template_path() -> Path:
    """Locate the canonical round-1 prompt template.

    Resolution order: ``REPO_REVIEW_PROMPT_DIR`` env var, then a couple of
    plausible repo-relative defaults. Returning a missing path is acceptable;
    the caller will surface a clear error.
    """
    import os

    env_dir = os.environ.get("REPO_REVIEW_PROMPT_DIR")
    candidates = []
    if env_dir:
        candidates.append(Path(env_dir) / "REPO_REVIEW_ROUND1_PROMPT.md")
    here = Path(__file__).resolve().parent.parent  # scripts/.. → repo root
    candidates.extend(
        [
            here / "docs" / "ops" / "REPO_REVIEW_ROUND1_PROMPT.md",
            Path.cwd() / "docs" / "ops" / "REPO_REVIEW_ROUND1_PROMPT.md",
        ]
    )
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


# ---------------------------------------------------------------------------
# GitNexus refresh (pre-fan-out)
# ---------------------------------------------------------------------------


def sync_repo_to_origin(
    repo_path: Path,
    *,
    timeout: int = 120,
) -> tuple[bool, str]:
    """Sync the local working tree to origin's primary branch (main, then phase-3).

    Per the iter-9 lesson: round-1 reviewers MUST run against current main, not
    a stale local checkout. A stale checkout silently produces false negatives
    (cited files no longer exist locally → INSUFFICIENT_EVIDENCE) and false
    positives (gaps that have already shipped in unpulled PRs get re-raised).

    Procedure: stash any dirty changes (preserved as a stash entry), checkout
    the canonical branch (try `main` then `phase-3`), `git pull --ff-only`.
    Returns (ok, summary). Untracked workloop-state.md is removed proactively
    because upstream often adds a tracked version with the same name.
    """
    import subprocess

    def _git(args: list[str], check: bool = False) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(repo_path), *args],
            check=check,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    notes: list[str] = []
    try:
        # 1. Fetch all refs from origin so origin/main is fresh.
        result = _git(["fetch", "origin", "--quiet"])
        if result.returncode != 0:
            return False, f"git fetch failed: {result.stderr.strip()[:200]}"

        # 2. Remove untracked workloop-state.md if upstream has a tracked version.
        wls = repo_path / "workloop-state.md"
        if wls.exists():
            tracked = _git(["ls-files", "--error-unmatch", "workloop-state.md"])
            if tracked.returncode != 0:
                # Untracked locally; check if upstream has it tracked.
                show = _git(["cat-file", "-e", "origin/main:workloop-state.md"])
                if show.returncode == 0:
                    wls.unlink()
                    notes.append("removed untracked workloop-state.md (upstream tracked)")

        # 3. Stash any dirty changes so checkout is safe.
        dirty = _git(["status", "--short"])
        if dirty.stdout.strip():
            stash = _git(
                [
                    "stash",
                    "push",
                    "-m",
                    "round1-runner sync: stash before sync to origin head",
                    "-u",  # include untracked
                ]
            )
            if stash.returncode == 0:
                notes.append("stashed dirty changes")

        # 4. Determine target branch — try main, fall back to phase-3.
        target = None
        for candidate in ("main", "phase-3"):
            check = _git(["rev-parse", "--verify", f"origin/{candidate}"])
            if check.returncode == 0:
                target = candidate
                break
        if target is None:
            return False, "neither origin/main nor origin/phase-3 exists"

        # 5. Checkout the target branch if not already on it.
        current = _git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        if current != target:
            checkout = _git(["checkout", target])
            if checkout.returncode != 0:
                return False, (f"checkout {target} failed: {checkout.stderr.strip()[:200]}")
            notes.append(f"checked out {target} (was {current})")

        # 6. Fast-forward pull.
        pull = _git(["pull", "--ff-only", "origin", target])
        if pull.returncode != 0:
            return False, f"pull --ff-only failed: {pull.stderr.strip()[:200]}"

        head = _git(["rev-parse", "--short", "HEAD"]).stdout.strip()
        notes.append(f"HEAD now {head} on {target}")
        return True, "; ".join(notes)
    except subprocess.TimeoutExpired:
        return False, f"sync timed out after {timeout}s"


def refresh_map_blocking(
    repo_path: Path,
    *,
    gitnexus_bin: str,
    timeout: int = 1200,
) -> tuple[bool, str]:
    """Refresh the GitNexus map for `repo_path` BEFORE spawning agents.

    Per the iter-2 lesson, the refresh must complete before agents start
    querying — otherwise FTS/embedding rebuild contends with their reads.
    Always passes `--force --embeddings`: forces rebuild on commit-current
    maps when embeddings are absent (otherwise analyze short-circuits).
    """
    return run_gitnexus_analyze(
        repo_path, gitnexus_bin, with_embeddings=True, force=True, timeout=timeout
    )


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


def build_agent_prompt(
    *,
    agent: str,
    repo: str,
    review_inputs: Path,
    findings_out: Path,
    template_path: Path,
) -> str:
    """Render the round-1 prompt by appending the per-run variables.

    The canonical procedure lives in the template. We prepend a small
    variable-binding header so the spawned agent sees its repo, paths, and
    agent identity unambiguously.
    """
    if template_path.is_file():
        template = template_path.read_text(encoding="utf-8")
    else:
        template = (
            "<!-- prompt template missing at "
            f"{template_path} — proceed using the protocol your training has -->"
        )
    header = (
        f"You are running round 1 of the weekly design-vs-implementation review for "
        f"**{repo}**.\n\n"
        f"Variables for this run:\n\n"
        f"- `<REPO>` = `{repo}`\n"
        f"- `<REVIEW_INPUTS_PATH>` = `{review_inputs}`\n"
        f"- `<FINDINGS_OUT_PATH>` = `{findings_out}`\n"
        f"- Your agent identifier: `{agent}` (use exactly this in the JSON `agent` field).\n\n"
        "Read your canonical procedure (the rest of this prompt) carefully. "
        "Apply defensive-write semantics: produce a substantive draft "
        "findings.json early and refine in place; do not leave the write for "
        "the end. The runner enforces a hard timeout; defensive writes ensure "
        "partial output survives if the timeout fires.\n\n"
        "When done, return a SHORT (under 200 words) report: candidate count, "
        "deeper_review_needed (yes/no), one-sentence honest confidence summary, "
        "and the path written to.\n\n"
        "---\n\n"
    )
    return header + template


# ---------------------------------------------------------------------------
# Per-agent invocation with retries
# ---------------------------------------------------------------------------


def invoke_round1_agent(
    *,
    agent: str,
    repo: str,
    repo_path: Path,
    output_dir: Path,
    workspace_root: Path,
    template_path: Path,
    log_dir: Path,
    timeout: int,
    retries: int,
    workflows_steward_root: Path,
) -> AgentResult:
    findings_path = round1_findings_path(output_dir, agent, repo)
    findings_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"round1-{agent}-{repo.replace('/', '__')}.log"
    review_inputs = review_inputs_path(output_dir, repo)

    prompt = build_agent_prompt(
        agent=agent,
        repo=repo,
        review_inputs=review_inputs,
        findings_out=findings_path,
        template_path=template_path,
    )

    additional_dirs = sorted(
        {
            workflows_steward_root,
            output_dir,
            repo_path,
        }
    )

    last_error = ""
    for attempt in range(retries + 1):
        if findings_path.is_file():
            # Maybe a prior attempt completed (or this is a re-run). Validate
            # before reusing — a stale or malformed findings.json should not
            # be silently accepted.
            errors = _validate_findings_file(findings_path, expected_repo=repo)
            if not errors:
                return AgentResult(
                    agent=agent,
                    findings_path=findings_path,
                    log_path=log_path,
                    succeeded=True,
                    spawned=False,
                )
            # Otherwise fall through to spawn (overwrite invalid file).
            last_error = "existing findings.json failed schema validation: " + "; ".join(errors[:3])

        ok, message = invoke_agent(
            agent,
            prompt,
            cwd=workflows_steward_root,
            additional_dirs=additional_dirs,
            log_file=log_path,
            timeout=timeout,
        )
        if not ok:
            last_error = f"attempt {attempt + 1}: {message}"
            continue

        if not findings_path.is_file():
            last_error = (
                f"attempt {attempt + 1}: agent exited cleanly but did not write "
                f"findings.json at {findings_path}"
            )
            continue

        errors = _validate_findings_file(findings_path, expected_repo=repo)
        if errors:
            last_error = (
                f"attempt {attempt + 1}: findings.json failed schema validation: "
                + "; ".join(errors[:3])
            )
            # Overwrite invalid file so retry is fresh.
            with contextlib.suppress(OSError):
                findings_path.unlink()
            continue

        return AgentResult(
            agent=agent,
            findings_path=findings_path,
            log_path=log_path,
            succeeded=True,
            spawned=True,
        )

    return AgentResult(
        agent=agent,
        findings_path=findings_path,
        log_path=log_path,
        succeeded=False,
        error=last_error or "unknown failure",
    )


def _validate_findings_file(path: Path, *, expected_repo: str) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot parse JSON: {exc}"]
    return validate_findings(data, expected_repo=expected_repo)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    registry_path = Path(args.registry).resolve()
    workspace_root, _excluded, repos, _archive_paths = load_registry(registry_path)

    repo_config = next((r for r in repos if r.repo == args.repo), None)
    if repo_config is None:
        print(
            f"[round1] {args.repo}: not in registry {registry_path}; nothing to do",
            file=sys.stderr,
        )
        return 2

    repo_path = workspace_root / repo_config.local_path
    if not repo_path.is_dir():
        print(
            f"[round1] {args.repo}: local path {repo_path} not found; cannot review",
            file=sys.stderr,
        )
        return 2

    workflows_steward_root = registry_path.parent.parent

    review_inputs = review_inputs_path(output_dir, args.repo)
    if not review_inputs.is_file():
        print(
            f"[round1] {args.repo}: missing review-inputs at {review_inputs}; "
            "run the evaluator preflight first",
            file=sys.stderr,
        )
        return 2

    state = load_state(output_dir, args.repo)
    transition(state, status="round1-running", note=f"round-1 runner started for {args.repo}")
    save_state(output_dir, state)

    # 0. Sync local repo to origin head BEFORE anything else (iter-9 lesson:
    #    stale checkouts produce false negatives + false positives in review).
    if not args.skip_local_sync:
        attempt = begin_attempt(state, phase="round-1-sync", agent="runner")
        save_state(output_dir, state)
        ok, message = sync_repo_to_origin(repo_path)
        finish_attempt(state, attempt, succeeded=ok, notes=message[:400])
        save_state(output_dir, state)
        if not ok:
            print(
                f"[round1] {args.repo}: local sync to origin failed: {message}",
                file=sys.stderr,
            )
            transition(
                state,
                status="round1-failed",
                note=f"local sync failed: {message[:200]}",
            )
            save_state(output_dir, state)
            return 1
        print(f"[round1] {args.repo}: synced to origin ({message})")

    # 1. Refresh map BLOCKING before fan-out (iter-2 lesson #1).
    if not args.skip_map_refresh:
        attempt = begin_attempt(state, phase="round-1-map-refresh", agent="runner")
        save_state(output_dir, state)
        ok, message = refresh_map_blocking(
            repo_path,
            gitnexus_bin=args.gitnexus_bin,
            timeout=args.map_refresh_timeout,
        )
        finish_attempt(state, attempt, succeeded=ok, notes=message[:400])
        save_state(output_dir, state)
        if not ok:
            print(
                f"[round1] {args.repo}: map refresh failed: {message}",
                file=sys.stderr,
            )
            transition(
                state,
                status="round1-failed",
                note=f"map refresh failed: {message[:200]}",
            )
            save_state(output_dir, state)
            return 1
        gn_map = collect_gitnexus_map(workspace_root, repo_path, repo_config)
        embeddings = (gn_map.get("stats") or {}).get("embeddings", 0)
        print(
            f"[round1] {args.repo}: map refreshed "
            f"(embeddings={embeddings}, indexed={(gn_map.get('indexed_commit') or '')[:12]})"
        )

    # 2. Fan out: Codex + Claude in parallel.
    template_path = round1_prompt_template_path()
    if not template_path.is_file():
        print(
            f"[round1] {args.repo}: prompt template missing at {template_path}; "
            "agent prompts will lack the canonical procedure",
            file=sys.stderr,
        )

    log_dir = output_dir / "logs" / "round1"
    log_dir.mkdir(parents=True, exist_ok=True)

    agents = list(args.agents)
    print(
        f"[round1] {args.repo}: spawning {len(agents)} agent(s) in parallel: "
        f"{', '.join(agents)} (timeout={args.turn_timeout}s)"
    )

    results: dict[str, AgentResult] = {}
    with ThreadPoolExecutor(max_workers=len(agents) or 1) as exe:
        futures = {
            agent: exe.submit(
                invoke_round1_agent,
                agent=agent,
                repo=args.repo,
                repo_path=repo_path,
                output_dir=output_dir,
                workspace_root=workspace_root,
                template_path=template_path,
                log_dir=log_dir,
                timeout=args.turn_timeout,
                retries=args.retries,
                workflows_steward_root=workflows_steward_root,
            )
            for agent in agents
        }
        for agent, future in futures.items():
            try:
                results[agent] = future.result()
            except Exception as exc:  # pragma: no cover - defensive
                results[agent] = AgentResult(
                    agent=agent,
                    findings_path=round1_findings_path(output_dir, agent, args.repo),
                    log_path=log_dir / f"round1-{agent}-{args.repo.replace('/', '__')}.log",
                    succeeded=False,
                    error=f"runner exception: {exc}",
                )

    # 3. Update state.
    successes: list[str] = []
    failures: list[tuple[str, str]] = []
    for agent, result in results.items():
        attempt = begin_attempt(state, phase="round-1-fan-out", agent=agent)
        finish_attempt(
            state,
            attempt,
            succeeded=result.succeeded,
            notes=(result.error if not result.succeeded else f"spawned={result.spawned}"),
        )
        if result.succeeded:
            successes.append(agent)
            record_round1_finding(state, agent, result.findings_path)
        else:
            failures.append((agent, result.error))
        spawn = "spawned" if result.spawned else "reused"
        status = "succeeded" if result.succeeded else f"failed: {result.error[:200]}"
        print(f"[round1] {args.repo}: {agent} → {status} ({spawn})")

    if failures:
        # Even partial success isn't enough — round 2 needs both findings.
        transition(
            state,
            status="round1-failed",
            note="; ".join(f"{a}={e[:120]}" for a, e in failures)[:400],
        )
        save_state(output_dir, state)
        print(
            f"[round1] {args.repo}: round-1 FAILED ({len(successes)} of {len(agents)} agents succeeded)",
            file=sys.stderr,
        )
        return 1

    transition(
        state,
        status="round1-complete",
        note=f"both agents validated: {', '.join(successes)}",
    )
    save_state(output_dir, state)
    print(
        f"[round1] {args.repo}: round-1 COMPLETE "
        f"({len(successes)} of {len(agents)} agents validated)"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/name from the registry")
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
        "--agents",
        nargs="+",
        default=list(PRODUCTION_AGENTS),
        help="agent identifiers to spawn (default: codex claude)",
    )
    parser.add_argument(
        "--gitnexus-bin",
        default="gitnexus",
        help="gitnexus CLI binary name on PATH",
    )
    parser.add_argument(
        "--skip-local-sync",
        action="store_true",
        help="skip the git-fetch + checkout-main + ff-pull pre-step (NOT recommended)",
    )
    parser.add_argument(
        "--skip-map-refresh",
        action="store_true",
        help="skip the GitNexus map refresh (use cached map as-is)",
    )
    parser.add_argument(
        "--map-refresh-timeout",
        type=int,
        default=1200,
        help="seconds to allow for the map refresh (default: 1200)",
    )
    parser.add_argument(
        "--turn-timeout",
        type=int,
        default=DEFAULT_TURN_TIMEOUT_SECONDS,
        help="hard timeout per agent in seconds (default: 5400 = 90 min)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=1,
        help="retry budget per agent on validation/timeout failure (default: 1)",
    )
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
