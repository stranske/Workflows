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
   `body` field is empty, missing, or fails the deterministic quality gate,
   reads the cited files at the cited line numbers, then composes or repairs a
   body matching the 468/908 reference depth.
4. If cited files no longer match current main (gap was fixed in an unpulled
   PR), records `body: "INSUFFICIENT_EVIDENCE: <reason>"` instead of
   fabricating — these become deeper-review items in the human packet.
5. Validates the updated converged.json against the round-2 schema.

Per the iter-9 sync-pre-step in round-1, the local repo should already be at
origin head when this runs. If callers want to verify, they can pass
`--require-clean-sync` which checks that the repo's HEAD matches `origin/main`
before spawning the agent.

Usage:

    python scripts/repo_review_body_writer.py \\
        --repo stranske/Manager-Database \\
        --output-dir docs/reports/repo-review \\
        --registry config/repo_review_registry.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from contextlib import suppress
from copy import deepcopy
from pathlib import Path
from typing import Any

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

# Falsifiability heuristic (Definition of Ready, AGENT_ISSUE_FORMAT.md §2):
# an issue's Acceptance Criteria must name at least one observable, falsifiable
# gate — a test, a runnable command, or a documented verification step. This is
# a deliberately conservative string heuristic (no LLM) so it never blocks a
# genuinely test-backed body and reliably catches the "no gate at all" case.
# A criterion qualifies if it matches any of:
#   - a test path / id            (`tests/`, `::`, `_test`, `.test.`, `spec`)
#   - a runner / verification verb (`pytest`, `gh workflow run`, `npm test`, ...)
#   - the literal tokens          (`smoke`, `verif`)
VERIFICATION_GATE_PATTERNS = (
    r"tests?/",
    r"::",
    r"_test\b",
    r"\.test\.",
    r"\bspec\b",
    r"\bpytest\b",
    r"gh workflow run\b",
    r"\bnpm (?:run )?test\b",
    r"\bnpm ci\b",
    r"\byarn test\b",
    r"\bcurl\b",
    r"dev_check\.sh",
    r"\bsmoke\b",
    r"\bverif",
)
_VERIFICATION_GATE_RE = re.compile("|".join(VERIFICATION_GATE_PATTERNS), re.IGNORECASE)
_ACCEPTANCE_HEADINGS = ("## acceptance criteria", "## acceptance")
_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:\.github|config|docs|out|scripts|src|tests)/"
    r"[A-Za-z0-9_./*{}@+-]+(?:::\w+|:\d+)?|"
    r"(?<![A-Za-z0-9_.-])(?:AGENTS|CLAUDE|README)\.md|"
    r"(?<![A-Za-z0-9_.-])pyproject\.toml"
)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def converged_path(output_dir: Path, repo: str) -> Path:
    return output_dir / "round2" / repo.replace("/", "__") / "converged.json"


def canonical_body_writer_prompt() -> Path:
    here = Path(__file__).resolve().parent.parent
    return here / "docs" / "ops" / "REPO_REVIEW_BODY_WRITER_PROMPT.md"


def repair_feedback_path(output_dir: Path, repo: str) -> Path:
    """Return the repo-scoped feedback carried from the prior failed write."""
    return converged_path(output_dir, repo).with_name("body-writer-repair-feedback.txt")


# ---------------------------------------------------------------------------
# Sync verification (optional)
# ---------------------------------------------------------------------------


def verify_clean_sync(repo_path: Path) -> tuple[bool, str]:
    """Confirm `repo_path` is at origin/main HEAD with no review-blocking changes."""

    def _git(args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(repo_path), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    head = _git(["rev-parse", "HEAD"]).stdout.strip()
    ref = _git(["rev-parse", "origin/main"])
    if ref.returncode == 0 and ref.stdout.strip() == head:
        return True, f"HEAD matches origin/main ({head[:12]})"
    return False, (
        f"HEAD ({head[:12]}) does not match origin/main; "
        "run round-1-runner first or pass --skip-sync-check"
    )


def sync_check_required(repo_path: Path, workflows_steward_root: Path) -> bool:
    """Do not reject the executing steward for running unreleased repair code.

    Round 1 preserves this checkout so later phases cannot load a different
    implementation mid-cycle. Every consumer repo must still match
    ``origin/main`` before body writing.
    """
    return repo_path.resolve() != workflows_steward_root.resolve()


# ---------------------------------------------------------------------------
# Body quality gate (post-write)
# ---------------------------------------------------------------------------


def _section_block(body: str, headings: tuple[str, ...]) -> str:
    """Return one level-two Markdown section, excluding its heading."""
    lines = body.splitlines()
    start: int | None = None
    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        if any(stripped == heading or stripped.startswith(heading + " ") for heading in headings):
            start = i
            break
    if start is None:
        return ""
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start + 1 : end])


def _acceptance_block(body: str) -> str:
    """Return the text of the `## Acceptance Criteria` section (through the next
    `## ` heading), or "" if no such heading is present. Heading match is
    case-insensitive and accepts the `## Acceptance` alias.
    """
    return _section_block(body, _ACCEPTANCE_HEADINGS)


def _reference_paths(section: str) -> set[str]:
    """Extract normalized repository-relative paths from a Markdown section."""
    paths: set[str] = set()
    values = [match.group(0) for match in _PATH_RE.finditer(section)]
    for code_span in re.findall(r"`([^`\n]+)`", section):
        for token in code_span.split():
            value = token.strip("'\"(),;").rstrip(".")
            if (
                "/" in value
                and not value.startswith(("/", "http://", "https://", "github.com/"))
                and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_./*{}@:+-]+", value)
                and re.search(r"[A-Za-z_]", value)
            ):
                values.append(value)
    for value in values:
        value = value.rstrip(".,;:)")
        value = re.sub(r"::[A-Za-z0-9_]+$", "", value)
        value = re.sub(r"(?::\d+(?:-\d+)?|#L\d+(?:-L?\d+)?)$", "", value)
        paths.add(value)
    return paths


def _path_resolves(repo_path: Path, reference: str) -> bool:
    if any(char in reference for char in "*?["):
        return any(repo_path.glob(reference))
    return (repo_path / reference).exists()


def acceptance_has_verification_gate(body: str) -> bool:
    """Conservative, LLM-free readiness lint shared with other generators
    (AGENT_ISSUE_FORMAT.md §2 / Definition of Ready). Returns True when the
    body's Acceptance Criteria block references at least one falsifiable gate
    (a test path/id, a runnable command, or a `smoke`/`verif` token). Returns
    False only when an Acceptance Criteria block exists but names no such gate.

    Intentionally string-based so it never blocks a genuinely test-backed body;
    it only fires on the "no observable gate at all" failure.
    """
    block = _acceptance_block(body)
    if not block.strip():
        # No acceptance section to evaluate; the missing-section check owns this.
        return True
    return bool(_VERIFICATION_GATE_RE.search(block))


def body_quality_errors(
    body: str,
    *,
    repo_path: Path | None = None,
    expected_repo: str | None = None,
) -> list[str]:
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
    elif not acceptance_has_verification_gate(body):
        errors.append(
            "Acceptance Criteria contain no falsifiable gate; at least one "
            "criterion must name a test, smoke test, runnable command, or "
            "documented live-verification step (see AGENT_ISSUE_FORMAT.md "
            "'Definition of Ready')"
        )
    if len(body) < 1500:
        errors.append(
            f"body is too short ({len(body)} chars); reference issues like #468 "
            "and #908 sit at 3000-5000 chars"
        )
    task_paths = _reference_paths(_section_block(body, ("## tasks", "## task list")))
    task_paths.discard(expected_repo)
    if len(task_paths) < 4:
        errors.append(
            f"Tasks reference {len(task_paths)} distinct repository paths; at least 4 are required"
        )
    implementation_paths = _reference_paths(_section_block(body, ("## implementation notes",)))
    implementation_paths.discard(expected_repo)
    if len(implementation_paths) < 6:
        errors.append(
            "Implementation Notes reference "
            f"{len(implementation_paths)} distinct repository paths; at least 6 are required"
        )
    if repo_path is not None:
        unresolved = sorted(
            reference
            for reference in task_paths | implementation_paths
            if not _path_resolves(repo_path, reference)
        )
        if unresolved:
            errors.append(
                "body contains repository paths that do not resolve: " + ", ".join(unresolved[:8])
            )
    return errors


def candidate_records(data: object) -> tuple[list[dict[str, object]], list[str]]:
    """Return candidate records only when their container shapes are safe."""
    if not isinstance(data, dict):
        return [], ["converged.json root must be an object"]
    raw = data.get("converged_candidates")
    if not isinstance(raw, list):
        return [], ["converged_candidates must be a list of objects"]
    errors = [
        f"converged_candidates[{index}] must be an object"
        for index, candidate in enumerate(raw)
        if not isinstance(candidate, dict)
    ]
    if errors:
        return [], errors
    records = list(raw)
    meta = data.get("meta_candidate")
    if meta is not None and not isinstance(meta, dict):
        return [], ["meta_candidate must be an object or null"]
    if isinstance(meta, dict):
        records.append(meta)
    return records, []


def restore_non_body_fields(
    before: dict[str, object], after: object
) -> tuple[dict[str, object], list[str], int]:
    """Preserve every pre-invocation field except candidate body values."""
    before_records, before_errors = candidate_records(before)
    after_records, after_errors = candidate_records(after)
    errors = [*before_errors, *after_errors]
    if errors or len(before_records) != len(after_records):
        if not errors:
            errors.append("candidate count changed during body writing")
        return deepcopy(before), errors, 0

    restored = deepcopy(before)
    restored_records, _ = candidate_records(restored)
    restored_count = 0
    for old, new, destination in zip(before_records, after_records, restored_records, strict=True):
        if {key: value for key, value in old.items() if key != "body"} != {
            key: value for key, value in new.items() if key != "body"
        }:
            restored_count += 1
        if "body" in new:
            destination["body"] = deepcopy(new["body"])
        else:
            destination.pop("body", None)
    return restored, [], restored_count


# ---------------------------------------------------------------------------
# Per-repo body-writer invocation
# ---------------------------------------------------------------------------


def build_prompt(*, repo: str, output_dir: Path, repo_path: Path) -> str:
    template = canonical_body_writer_prompt().read_text(encoding="utf-8")
    safe = repo.replace("/", "__")
    cj = converged_path(output_dir, repo)
    repair_targets: list[str] = []
    if cj.is_file():
        try:
            data = json.loads(cj.read_text(encoding="utf-8"))
            candidates, shape_errors = candidate_records(data)
            if shape_errors:
                repair_targets.append("- converged.json structure: " + "; ".join(shape_errors))
            for index, candidate in enumerate(candidates, start=1):
                errors = body_quality_errors(
                    str(candidate.get("body") or ""),
                    repo_path=repo_path,
                    expected_repo=repo,
                )
                if errors:
                    repair_targets.append(
                        f"- candidate #{index} {candidate.get('title', '?')!r}: "
                        + "; ".join(errors)
                    )
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    feedback_path = repair_feedback_path(output_dir, repo)
    repair_feedback = ""
    if feedback_path.is_file():
        with suppress(OSError):
            repair_feedback = feedback_path.read_text(encoding="utf-8")[-12_000:]

    repair_directive = ""
    if repair_targets:
        repair_directive = (
            "BODY REPAIR REQUIRED: rewrite every target below even when it already "
            "has a non-empty `body`; the current body failed the deterministic "
            "post-write gate. Preserve all non-body fields.\n" + "\n".join(repair_targets) + "\n\n"
        )
    if repair_feedback:
        repair_directive += (
            "PRIOR DETERMINISTIC VALIDATOR FEEDBACK (authoritative; correct every "
            "listed failure before returning; schema-only validation is insufficient):\n"
            "<validator-feedback>\n"
            f"{repair_feedback}\n"
            "</validator-feedback>\n\n"
        )

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
        "Then run the stricter body/path validator. Do not report success unless it "
        "exits zero:\n\n"
        f"  python scripts/repo_review_body_writer.py --repo {repo} --output-dir {output_dir} "
        "--registry config/repo_review_registry.json --validate-only --skip-sync-check\n\n"
        "Return a SHORT (<200 words) report: titles + char counts of new or "
        "repaired bodies, any INSUFFICIENT_EVIDENCE markings, validation result.\n\n"
        + repair_directive
        + "---\n\n"
    )
    return header + template


def validate_body_data(
    data: Any,
    *,
    expected_repo: str,
    repo_path: Path,
) -> tuple[list[str], list[str], int, int]:
    """Apply schema and body-quality gates without invoking an agent."""
    schema_errors = validate_converged_set(data, expected_repo=expected_repo)
    candidates, shape_errors = candidate_records(data)
    schema_errors.extend(shape_errors)

    body_failures: list[str] = []
    insufficient_count = 0
    written_count = 0
    for i, candidate in enumerate(candidates, start=1):
        body = str(candidate.get("body") or "")
        title = str(candidate.get("title") or "?")[:50]
        if body.strip().startswith("INSUFFICIENT_EVIDENCE"):
            insufficient_count += 1
            continue
        errors = body_quality_errors(body, repo_path=repo_path, expected_repo=expected_repo)
        if errors:
            body_failures.append(f"  candidate #{i} '{title}': {'; '.join(errors[:3])}")
        else:
            written_count += 1
    return schema_errors, body_failures, insufficient_count, written_count


def print_validation_result(
    *,
    repo: str,
    schema_errors: list[str],
    body_failures: list[str],
    insufficient_count: int,
    written_count: int,
    restored_non_body: int = 0,
) -> bool:
    """Print the canonical deterministic summary and return its success state."""
    summary = (
        f"written={written_count}, insufficient={insufficient_count}, "
        f"failures={len(body_failures)}, schema_errors={len(schema_errors)}, "
        f"restored_non_body={restored_non_body}"
    )
    print(f"[body-writer] {repo}: {summary}")
    if schema_errors:
        print("  schema errors:", file=sys.stderr)
        for err in schema_errors[:5]:
            print(f"    - {err}", file=sys.stderr)
    if body_failures:
        print("  body-quality failures:", file=sys.stderr)
        for failure in body_failures:
            print(f"  {failure}", file=sys.stderr)
    return not schema_errors and not body_failures


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

    if not args.skip_sync_check and sync_check_required(repo_path, workflows_steward_root):
        ok, message = verify_clean_sync(repo_path)
        if not ok:
            print(f"[body-writer] {args.repo}: sync check failed — {message}", file=sys.stderr)
            return 1
        print(f"[body-writer] {args.repo}: {message}")
    elif not args.skip_sync_check:
        print(
            f"[body-writer] {args.repo}: preserving executing steward checkout "
            "for phase consistency"
        )

    if getattr(args, "validate_only", False):
        try:
            data = json.loads(cj.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[body-writer] {args.repo}: cannot parse converged.json: {exc}", file=sys.stderr)
            return 1
        schema_errors, body_failures, insufficient_count, written_count = validate_body_data(
            data,
            expected_repo=args.repo,
            repo_path=repo_path,
        )
        succeeded = print_validation_result(
            repo=args.repo,
            schema_errors=schema_errors,
            body_failures=body_failures,
            insufficient_count=insufficient_count,
            written_count=written_count,
        )
        return 0 if succeeded else 1

    log_dir = output_dir / "logs" / "body-writer"
    log_dir.mkdir(parents=True, exist_ok=True)

    state = load_state(output_dir, args.repo)
    attempt = begin_attempt(state, phase="body-writer", agent=args.agent)
    save_state(output_dir, state)

    try:
        original_data = json.loads(cj.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        finish_attempt(state, attempt, succeeded=False, notes=f"cannot parse converged.json: {exc}")
        save_state(output_dir, state)
        print(f"[body-writer] {args.repo}: cannot parse converged.json: {exc}", file=sys.stderr)
        return 1
    _records, initial_shape_errors = candidate_records(original_data)
    if initial_shape_errors:
        notes = "; ".join(initial_shape_errors)
        finish_attempt(state, attempt, succeeded=False, notes=notes)
        save_state(output_dir, state)
        print(f"[body-writer] {args.repo}: {notes}", file=sys.stderr)
        return 1

    print(
        f"[body-writer] {args.repo}: spawning agent={args.agent} "
        f"(timeout={args.timeout}s, log: {log_dir / f'body-writer-{args.repo.replace(chr(47), chr(95) * 2)}.log'})"
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

    data, preservation_errors, restored_non_body = restore_non_body_fields(original_data, data)
    if preservation_errors or restored_non_body:
        try:
            cj.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            preservation_errors.append(f"cannot restore non-body fields: {exc}")
    schema_errors, body_failures, insufficient_count, written_count = validate_body_data(
        data,
        expected_repo=args.repo,
        repo_path=repo_path,
    )
    schema_errors.extend(preservation_errors)

    summary = (
        f"written={written_count}, insufficient={insufficient_count}, "
        f"failures={len(body_failures)}, schema_errors={len(schema_errors)}, "
        f"restored_non_body={restored_non_body}"
    )
    succeeded = not schema_errors and not body_failures
    finish_attempt(state, attempt, succeeded=succeeded, notes=summary)
    save_state(output_dir, state)

    print_validation_result(
        repo=args.repo,
        schema_errors=schema_errors,
        body_failures=body_failures,
        insufficient_count=insufficient_count,
        written_count=written_count,
        restored_non_body=restored_non_body,
    )

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
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate existing bodies and paths without spawning an agent",
    )
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
