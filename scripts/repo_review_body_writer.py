"""Body-writer pass: convert round-2 converged candidates into AGENT_ISSUE_FORMAT.md-compliant bodies.

Per the iter-9 lesson: round-1 reviewer agents focus on discovering and tracing
gaps with structured fields (gap, current_state, refs, tasks, acceptance, etc.)
but historically wrote `body` fields inconsistently — sometimes a polished
agent-ready issue body, sometimes nothing. The auto-constructor inside the
evaluator falls short of the AGENT_ISSUE_FORMAT.md quality bar (generic tasks
and acceptance criteria, no concrete file:line refs, no calibration to the
real reference examples 468/908).

This pass invokes a focused agent per repo that:

1. Reads the canonical prompt at `docs/ops/REPO_REVIEW_BODY_WRITER_PROMPT.md`.
2. Reads the converged.json for the target repo.
3. For each `converged_candidates[*]` and (if present) `meta_candidate` whose
   `body` field is empty or missing, reads the cited files at the cited line
   numbers, then composes a body matching the 468/908 reference depth.
4. If cited files no longer match current main (gap was fixed in an unpulled
   PR), records `body: "INSUFFICIENT_EVIDENCE: <reason>"` instead of
   fabricating — these become deeper-review items in the human packet.
5. Validates the updated converged.json against the round-2 schema.

Per the iter-9 sync-pre-step in round-1, the local repo should already be at
origin head when this runs. If callers want to verify, they can pass
`--require-clean-sync` which checks that the repo's HEAD matches `origin/main`
or `origin/phase-3` before spawning the agent.

Usage:

    python scripts/repo_review_body_writer.py \\
        --repo stranske/Manager-Database \\
        --output-dir docs/reports/repo-review \\
        --registry config/repo_review_registry.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

try:
    from scripts.repo_review_evaluator import load_registry
    from scripts.repo_review_round2_runner import invoke_agent
    from scripts.repo_review_round2_schema import validate_converged_set
    from scripts.repo_review_state import (
        begin_attempt,
        finish_attempt,
        load_state,
        save_state,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_review_evaluator import load_registry  # type: ignore[no-redef]
    from repo_review_round2_runner import invoke_agent  # type: ignore[no-redef]
    from repo_review_round2_schema import validate_converged_set  # type: ignore[no-redef]
    from repo_review_state import (  # type: ignore[no-redef]
        begin_attempt,
        finish_attempt,
        load_state,
        save_state,
    )


DEFAULT_TIMEOUT_SECONDS = 60 * 60  # 60 min hard ceiling
GENERIC_BODY_PHRASES = (
    "no completed semantic review is recorded",
    "implement the approved review gap",
    "the reviewed design/readiness gap is implemented",
    "at least one targeted automated test",
    "approved weekly-review candidate",
)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def converged_path(output_dir: Path, repo: str) -> Path:
    return output_dir / "round2" / repo.replace("/", "__") / "converged.json"


def canonical_body_writer_prompt() -> Path:
    here = Path(__file__).resolve().parent.parent
    return here / "docs" / "ops" / "REPO_REVIEW_BODY_WRITER_PROMPT.md"


# ---------------------------------------------------------------------------
# Sync verification (optional)
# ---------------------------------------------------------------------------


def verify_clean_sync(repo_path: Path) -> tuple[bool, str]:
    """Confirm `repo_path` is at origin/main or origin/phase-3 HEAD with no
    review-blocking dirty changes."""

    def _git(args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(repo_path), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    head = _git(["rev-parse", "HEAD"]).stdout.strip()
    for branch in ("main", "phase-3"):
        ref = _git(["rev-parse", f"origin/{branch}"])
        if ref.returncode == 0 and ref.stdout.strip() == head:
            return True, f"HEAD matches origin/{branch} ({head[:12]})"
    return False, (
        f"HEAD ({head[:12]}) does not match origin/main or origin/phase-3; "
        "run round-1-runner first or pass --skip-sync-check"
    )


# ---------------------------------------------------------------------------
# Body quality gate (post-write)
# ---------------------------------------------------------------------------


def body_quality_errors(body: str) -> list[str]:
    """Lightweight quality check for written bodies. Mirrors the
    AGENT_ISSUE_FORMAT.md standard at validation time so low-quality bodies
    can be rejected before upload.

    INSUFFICIENT_EVIDENCE markers are accepted as-is — they're a legitimate
    outcome that routes to deeper-review.
    """
    if not body or not body.strip():
        return ["body is empty"]
    if body.strip().startswith("INSUFFICIENT_EVIDENCE"):
        return []  # legitimate routing, not a quality failure

    errors: list[str] = []
    lowered = body.lower()
    for phrase in GENERIC_BODY_PHRASES:
        if phrase in lowered:
            errors.append(
                f"body contains generic boilerplate phrase ({phrase!r}); "
                "tasks and acceptance criteria must be specific to the repo."
            )
    if "## tasks" not in lowered and "## task list" not in lowered:
        errors.append("body is missing the required `## Tasks` section")
    if "## acceptance criteria" not in lowered and "## acceptance" not in lowered:
        errors.append("body is missing the required `## Acceptance Criteria` section")
    if len(body) < 1500:
        errors.append(
            f"body is too short ({len(body)} chars); reference issues like #468 "
            "and #908 sit at 3000-5000 chars"
        )
    return errors


# ---------------------------------------------------------------------------
# Per-repo body-writer invocation
# ---------------------------------------------------------------------------


def build_prompt(*, repo: str, output_dir: Path, repo_path: Path) -> str:
    template = canonical_body_writer_prompt().read_text(encoding="utf-8")
    safe = repo.replace("/", "__")
    cj = converged_path(output_dir, repo)
    header = (
        f"You are running the body-writer pass for **{repo}**.\n\n"
        f"Variables:\n"
        f"- `<REPO>` = `{repo}`\n"
        f"- `<REPO_SAFE>` = `{safe}`\n"
        f"- `<LOCAL_REPO_PATH>` = `{repo_path}`\n"
        f"- Converged.json: `{cj}`\n\n"
        "The local repo has been synced to origin head before this pass; cite "
        "files and line numbers from the current checkout. If a candidate's "
        "structured `design_refs` / `implementation_refs` cite files that no "
        "longer exist in current main (gap was shipped in an unpulled PR), "
        'record `body: "INSUFFICIENT_EVIDENCE: <reason>"` rather than '
        "fabricating. INSUFFICIENT_EVIDENCE is a legitimate outcome.\n\n"
        "After writing, validate:\n\n"
        f"  python scripts/repo_review_round2_schema.py --converged {cj} --expected-repo {repo}\n\n"
        "Return a SHORT (<200 words) report: titles + char counts of new "
        "bodies, any INSUFFICIENT_EVIDENCE markings, validation result.\n\n---\n\n"
    )
    return header + template


def run_body_writer(
    *,
    repo: str,
    repo_path: Path,
    output_dir: Path,
    workflows_steward_root: Path,
    log_dir: Path,
    timeout: int,
    agent: str,
) -> tuple[bool, str]:
    log_path = log_dir / f"body-writer-{repo.replace('/', '__')}.log"
    prompt = build_prompt(repo=repo, output_dir=output_dir, repo_path=repo_path)
    additional_dirs = sorted({workflows_steward_root, output_dir, repo_path})
    return invoke_agent(
        agent,
        prompt,
        cwd=workflows_steward_root,
        additional_dirs=additional_dirs,
        log_file=log_path,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir).resolve()
    registry_path = Path(args.registry).resolve()
    workspace_root, _excluded, repos, _archive_paths = load_registry(registry_path)
    workflows_steward_root = registry_path.parent.parent

    repo_config = next((r for r in repos if r.repo == args.repo), None)
    if repo_config is None:
        print(f"[body-writer] {args.repo}: not in registry", file=sys.stderr)
        return 2

    repo_path = workspace_root / repo_config.local_path
    cj = converged_path(output_dir, args.repo)
    if not cj.is_file():
        print(
            f"[body-writer] {args.repo}: converged.json missing at {cj}; "
            "run the round-2 runner first",
            file=sys.stderr,
        )
        return 2

    if not args.skip_sync_check:
        ok, message = verify_clean_sync(repo_path)
        if not ok:
            print(f"[body-writer] {args.repo}: sync check failed — {message}", file=sys.stderr)
            return 1
        print(f"[body-writer] {args.repo}: {message}")

    log_dir = output_dir / "logs" / "body-writer"
    log_dir.mkdir(parents=True, exist_ok=True)

    state = load_state(output_dir, args.repo)
    attempt = begin_attempt(state, phase="body-writer", agent=args.agent)
    save_state(output_dir, state)

    print(
        f"[body-writer] {args.repo}: spawning agent={args.agent} "
        f"(timeout={args.timeout}s, log: {log_dir / f'body-writer-{args.repo.replace(chr(47), chr(95)*2)}.log'})"
    )
    ok, message = run_body_writer(
        repo=args.repo,
        repo_path=repo_path,
        output_dir=output_dir,
        workflows_steward_root=workflows_steward_root,
        log_dir=log_dir,
        timeout=args.timeout,
        agent=args.agent,
    )
    if not ok:
        finish_attempt(state, attempt, succeeded=False, notes=message[:400])
        save_state(output_dir, state)
        print(f"[body-writer] {args.repo}: FAILED — {message}", file=sys.stderr)
        return 1

    # Validate written bodies + schema.
    try:
        data = json.loads(cj.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        finish_attempt(state, attempt, succeeded=False, notes=f"cannot parse converged.json: {exc}")
        save_state(output_dir, state)
        print(
            f"[body-writer] {args.repo}: cannot parse converged.json after run: {exc}",
            file=sys.stderr,
        )
        return 1

    schema_errors = validate_converged_set(data, expected_repo=args.repo)
    candidates = list(data.get("converged_candidates") or [])
    meta = data.get("meta_candidate")
    if isinstance(meta, dict):
        candidates.append(meta)

    body_failures: list[str] = []
    insufficient_count = 0
    written_count = 0
    for i, c in enumerate(candidates, start=1):
        body = str(c.get("body") or "")
        title = c.get("title", "?")[:50]
        if body.strip().startswith("INSUFFICIENT_EVIDENCE"):
            insufficient_count += 1
            continue
        errors = body_quality_errors(body)
        if errors:
            body_failures.append(f"  candidate #{i} '{title}': {'; '.join(errors[:3])}")
        else:
            written_count += 1

    summary = (
        f"written={written_count}, insufficient={insufficient_count}, "
        f"failures={len(body_failures)}, schema_errors={len(schema_errors)}"
    )
    succeeded = not schema_errors and not body_failures
    finish_attempt(state, attempt, succeeded=succeeded, notes=summary)
    save_state(output_dir, state)

    print(f"[body-writer] {args.repo}: {summary}")
    if schema_errors:
        print("  schema errors:", file=sys.stderr)
        for err in schema_errors[:5]:
            print(f"    - {err}", file=sys.stderr)
    if body_failures:
        print("  body-quality failures:", file=sys.stderr)
        for failure in body_failures:
            print(f"  {failure}", file=sys.stderr)

    return 0 if succeeded else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/name from the registry")
    parser.add_argument("--output-dir", required=True, help="output dir")
    parser.add_argument(
        "--registry",
        default="config/repo_review_registry.json",
        help="path to repo_review_registry.json",
    )
    parser.add_argument(
        "--agent",
        default="codex",
        help="agent identifier to spawn (default: codex)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="hard timeout in seconds (default: 3600 = 60 min)",
    )
    parser.add_argument(
        "--skip-sync-check",
        action="store_true",
        help="skip the local-repo-at-origin-head check (NOT recommended)",
    )
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
