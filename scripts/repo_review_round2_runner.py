"""Round-2 negotiation runner.

Coordinates the round-2 negotiation between Codex and Claude Code for one
repo. Given that round-1 findings already exist on disk, this script:

  1. Builds the canonical round-2 prompt (per-agent variable substitution).
  2. Spawns both agents in parallel for the current turn (skips if the turn
     output already exists on disk — idempotent).
  3. Validates each agent's turn output against the round-2 schema.
  4. Computes convergence per-candidate and per-meta.
  5. Repeats turns up to `--max-turns` if anything is still pending.
  6. Synthesizes `converged.json` and writes it.

The protocol is documented in `docs/ops/REPO_REVIEW_ROUND2_PROTOCOL.md`; the
prompt template is `docs/ops/REPO_REVIEW_ROUND2_PROMPT.md`.

Production cron will invoke this once per repo after both round-1 sessions
have written findings.json files. Stall recovery is per-agent-per-turn:
if an agent fails or times out, that single (agent, turn) pair is retried
up to `--retries` times before being marked as `abstain` for the rest of
the negotiation.

Default invocation:

    python scripts/repo_review_round2_runner.py \\
        --repo stranske/Manager-Database \\
        --output-dir docs/reports/repo-review

Useful flags:

    --dry-run                Synthesize converged.json from existing turn
                             outputs only; never spawn agents.
    --max-turns 3            Stop after this many turns even if pending.
    --retries 2              Per-agent-per-turn retry budget.
    --turn-timeout 1800      Seconds to wait for an agent's turn output.
    --agents codex,claude    Override the agent set (default: codex,claude).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.repo_review_round2_schema import (
        validate_converged_set,
        validate_turn_output,
    )
    from scripts.repo_review_state import (
        begin_attempt,
        finish_attempt,
        load_state,
        record_round2_converged,
        save_state,
        transition,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_review_round2_schema import (  # type: ignore[no-redef]
        validate_converged_set,
        validate_turn_output,
    )
    from repo_review_state import (  # type: ignore[no-redef]
        begin_attempt,
        finish_attempt,
        load_state,
        record_round2_converged,
        save_state,
        transition,
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WORKFLOWS_STEWARD = Path(
    "/Users/teacher/Library/CloudStorage/Dropbox/Learning/Code/Workflows-steward"
)
PROMPT_FILE = WORKFLOWS_STEWARD / "docs/ops/REPO_REVIEW_ROUND2_PROMPT.md"
PROTOCOL_FILE = WORKFLOWS_STEWARD / "docs/ops/REPO_REVIEW_ROUND2_PROTOCOL.md"
SCHEMA_FILE = WORKFLOWS_STEWARD / "docs/ops/REPO_REVIEW_ROUND2_SCHEMA.md"
SCHEMA_VALIDATOR = WORKFLOWS_STEWARD / "scripts/repo_review_round2_schema.py"
DEFAULT_AGENTS = ("codex", "claude")
DEFAULT_MAX_TURNS = 3
DEFAULT_TURN_TIMEOUT_SECONDS = 1800  # 30 min
DEFAULT_RETRIES = 2
META_PATTERN_OVERLAP_FLOOR = 0.5  # ≥ half the supporting refs in common


# ---------------------------------------------------------------------------
# Lightweight types
# ---------------------------------------------------------------------------


@dataclass
class AgentTurnResult:
    agent: str
    turn: int
    output_path: Path
    succeeded: bool
    spawned: bool  # True if we actually invoked the agent (vs. reused existing)
    error: str = ""


@dataclass
class CandidateKey:
    source_agent: str
    candidate_index: int

    def __hash__(self) -> int:
        return hash((self.source_agent, self.candidate_index))


@dataclass
class CandidateResolution:
    key: CandidateKey
    status: (
        str  # "converged-keep" | "converged-merge" | "converged-drop" | "pending" | "deadlocked"
    )
    marks_history: list[dict[str, Any]] = field(default_factory=list)
    merge_proposal: dict[str, Any] | None = None
    revision_proposal: dict[str, Any] | None = None
    drop_reason: str = ""


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def safe_repo_name(repo: str) -> str:
    return repo.replace("/", "__")


def round1_findings_path(output_dir: Path, agent: str, repo: str) -> Path:
    return output_dir / "round1" / agent / safe_repo_name(repo) / "findings.json"


def round2_turn_path(output_dir: Path, repo: str, turn: int, agent: str) -> Path:
    return output_dir / "round2" / safe_repo_name(repo) / f"turn-{turn}" / f"{agent}.json"


def round2_converged_path(output_dir: Path, repo: str) -> Path:
    return output_dir / "round2" / safe_repo_name(repo) / "converged.json"


# ---------------------------------------------------------------------------
# Round-1 findings discovery
# ---------------------------------------------------------------------------


def discover_round1_agents(output_dir: Path, repo: str) -> dict[str, Path]:
    """Return {agent_label: round1_findings_path} for every round-1 dir present.

    Production cron will pin the agents to {codex, claude}; this helper
    accommodates pilot identifiers like `pilot-claude` while the production
    flow stabilizes.
    """
    safe = safe_repo_name(repo)
    round1_root = output_dir / "round1"
    if not round1_root.is_dir():
        return {}
    found: dict[str, Path] = {}
    for agent_dir in round1_root.iterdir():
        if not agent_dir.is_dir():
            continue
        candidate = agent_dir / safe / "findings.json"
        if candidate.is_file():
            found[agent_dir.name] = candidate
    return found


def resolve_negotiation_agents(
    output_dir: Path, repo: str, requested: tuple[str, ...]
) -> dict[str, Path]:
    """Map requested agent labels to round-1 findings paths.

    Each requested label can be an exact match (`codex`, `claude`) or a
    prefix that matches a single round-1 dir (e.g. `claude` matching the
    pilot dir `pilot-claude`). This makes the runner usable both for the
    production cron and for pilot runs without renaming files.
    """
    available = discover_round1_agents(output_dir, repo)
    resolved: dict[str, Path] = {}
    for label in requested:
        if label in available:
            resolved[label] = available[label]
            continue
        suffix_matches = [
            (name, path)
            for name, path in available.items()
            if name == label or name.endswith(f"-{label}") or name.endswith(label)
        ]
        if len(suffix_matches) == 1:
            actual_label, path = suffix_matches[0]
            resolved[actual_label] = path
            continue
        if len(suffix_matches) > 1:
            options = ", ".join(name for name, _ in suffix_matches)
            raise SystemExit(
                f"Round-1 findings for agent {label!r} are ambiguous: matches {options}. "
                f"Use the exact label."
            )
        raise SystemExit(
            f"No round-1 findings for agent {label!r} under {output_dir}/round1/. "
            f"Available: {sorted(available.keys()) or 'none'}."
        )
    return resolved


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


PROMPT_PREAMBLE = """You are running turn {turn} of round-2 negotiation for **{repo}**. Read the canonical \
prompt and procedure at:

  {prompt_file}

Read the protocol and schema docs:

  {protocol_file}
  {schema_file}

Your variables for this run:

- `<REPO>` = `{repo}`
- `<TURN_NUMBER>` = `{turn}`
- `<MY_AGENT>` = `{my_agent}`
- `<OTHER_AGENT>` = `{other_agent}`
- `<TURN_OUTPUT_PATH>` = `{turn_output_path}`

Inputs you must read in order:

1. The canonical round-2 prompt, protocol, and schema files above.
2. Your own round-1 findings: `{my_findings}`
3. The counterpart's round-1 findings: `{other_findings}`
{prior_turns_section}
4. The repo at the local path named in your round-1 findings, plus the GitNexus map (use `gitnexus query` and Cypher fallbacks per the canonical prompt's GitNexus section). Verify any `disagree-*` mark with concrete evidence from the actual files, not the counterpart's claims about them.

Procedure:

1. **Per-candidate marks** — for EVERY round-1 candidate from BOTH agents, record exactly one mark (agree-keep | agree-merge | disagree-drop | disagree-revise | abstain) with a substantive reason ≥30 chars. `disagree-drop` reasons must cite a file ref, test ref, open issue, or merged PR. `agree-merge` requires `merge_proposal`; `disagree-revise` requires `revision_proposal`.
2. **Own-candidate revisions** — if reading the counterpart's findings made you re-evaluate one of your own round-1 candidates, record the revision under `own_candidates_revisions`.
3. **Meta-candidate detection** — look across the union of all candidates for a systemic pattern (≥2 candidates pointing to the same class of bug, the same architectural seam, or the same incomplete migration). The validator enforces: `scope=audit`, ≥3 tasks (enumerate, classify, file follow-up issues), ≥3 acceptance criteria (must reference an audit-report artifact path AND per-instance follow-up filing), ≥1 non-goal explicitly forbidding bundling per-instance fixes into a single PR, priority=normal-or-low, confidence=medium-or-lower (high requires ≥4 supporting candidates). If you don't see a pattern, set `proposed: false`. Do NOT invent a pattern.
4. **Write turn output** to `<TURN_OUTPUT_PATH>` conforming to the round-2 schema. The runner validates with `python {schema_validator} <TURN_OUTPUT_PATH>` and rejects malformed output.

Out of scope: do NOT modify the repo, do NOT commit, do NOT touch the counterpart's round-1 findings, do NOT write anywhere besides `<TURN_OUTPUT_PATH>`.

When you finish, return a SHORT message (under 200 words) reporting: count of marks by type, whether you proposed a meta-candidate (yes + theme, or no), and the path you wrote to. Do NOT paste the JSON."""


def build_prompt(
    *,
    repo: str,
    turn: int,
    my_agent: str,
    other_agent: str,
    my_findings: Path,
    other_findings: Path,
    turn_output_path: Path,
    prior_turn_paths: list[Path],
) -> str:
    if prior_turn_paths:
        prior_lines = ["", "Prior-turn outputs (read these for the negotiation history):"]
        for path in prior_turn_paths:
            prior_lines.append(f"   - `{path}`")
        prior_section = "\n".join(prior_lines)
    else:
        prior_section = ""
    return PROMPT_PREAMBLE.format(
        repo=repo,
        turn=turn,
        my_agent=my_agent,
        other_agent=other_agent,
        my_findings=my_findings,
        other_findings=other_findings,
        turn_output_path=turn_output_path,
        prompt_file=PROMPT_FILE,
        protocol_file=PROTOCOL_FILE,
        schema_file=SCHEMA_FILE,
        schema_validator=SCHEMA_VALIDATOR,
        prior_turns_section=prior_section,
    )


# ---------------------------------------------------------------------------
# Agent invocation
# ---------------------------------------------------------------------------


try:
    from scripts.repo_review_heartbeat import run_with_heartbeat
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_review_heartbeat import run_with_heartbeat  # type: ignore[no-redef]


# Stall detection thresholds — overrideable via env so cron operators can
# loosen them without redeploying. Defaults are conservative for cron use.
_HEARTBEAT_INTERVAL = int(os.environ.get("REPO_REVIEW_HEARTBEAT_INTERVAL", "60"))
_STALL_THRESHOLD = int(os.environ.get("REPO_REVIEW_STALL_THRESHOLD", "900"))  # 15 min


def invoke_codex(prompt: str, *, cwd: Path, log_file: Path, timeout: int) -> tuple[bool, str]:
    if shutil.which("codex") is None:
        return False, "codex CLI not on PATH"
    # `--ephemeral` is critical when this runner is itself spawned from inside
    # another `codex exec` (the cron pattern). Without it, the nested codex
    # tries to write session files at `~/.codex/sessions/`, which the outer
    # codex's workspace-write sandbox blocks (EPERM). With `--ephemeral`,
    # session state lives only in memory and the nested codex starts cleanly.
    cmd = [
        "codex",
        "exec",
        "--full-auto",
        "--skip-git-repo-check",
        "--ephemeral",
        "-C",
        str(cwd),
    ]
    result = run_with_heartbeat(
        cmd,
        prompt=prompt,
        cwd=cwd,
        env=None,
        log_file=log_file,
        timeout=timeout,
        heartbeat_interval=_HEARTBEAT_INTERVAL,
        stall_threshold=_STALL_THRESHOLD,
        label="codex",
    )
    if result.succeeded:
        return True, str(log_file)
    if result.stuck:
        return (
            False,
            f"codex stuck (no log growth for >{_STALL_THRESHOLD}s; terminated): {log_file}",
        )
    if result.timed_out:
        return False, f"codex timed out after {timeout}s (log: {log_file})"
    return False, f"codex exited {result.returncode} ({result.note}; log: {log_file})"


def _resolve_claude_binary() -> str | None:
    """Return the path to the Claude Desktop-bundled claude CLI binary.

    The cron MUST use the bundled binary, not whatever's on PATH:

    - `/opt/homebrew/bin/claude` (the homebrew package) is older (2.1.45)
      and its OAuth/keychain auth path is broken — it returns 401 even
      with a clean env. Empirically tested 2026-05-07.
    - `~/Library/Application Support/Claude/claude-code/<version>/claude.app/
      Contents/MacOS/claude` (the bundled binary) authenticates fine when
      invoked with a clean env. This is what Claude Desktop spawns.

    Resolution order:
      1. `CLAUDE_CODE_EXECPATH` env var (set by Claude Desktop when nested,
         points at the bundled binary).
      2. Newest version under `~/Library/Application Support/Claude/claude-code/`.
      3. `shutil.which("claude")` as a last resort (may 401 on auth — log a warning).
    """
    env_path = os.environ.get("CLAUDE_CODE_EXECPATH")
    if env_path and Path(env_path).is_file():
        return env_path
    bundled_root = Path(os.path.expanduser("~/Library/Application Support/Claude/claude-code"))
    if bundled_root.is_dir():
        # Sort versions newest-first using a tuple-of-ints key (e.g. "2.1.128"
        # → (2, 1, 128)) so 2.1.128 sorts higher than 2.1.45 (which is the
        # whole point of skipping the homebrew install).
        def _version_key(p: Path) -> tuple[int, ...]:
            try:
                return tuple(int(x) for x in p.name.split("."))
            except ValueError:
                return (0,)

        candidates = sorted(
            (p for p in bundled_root.iterdir() if p.is_dir()),
            key=_version_key,
            reverse=True,
        )
        for ver_dir in candidates:
            binary = ver_dir / "claude.app" / "Contents" / "MacOS" / "claude"
            if binary.is_file():
                return str(binary)
    fallback = shutil.which("claude")
    return fallback


CLAUDE_OAUTH_TOKEN_FILE = Path(
    os.path.expanduser(
        "~/.codex/automations/reviewed-repo-weekly-design-review/claude-oauth-token.txt"
    )
)


def _read_claude_oauth_token() -> str | None:
    """Read the long-lived OAuth token written by `claude setup-token`.

    Returns the token string if the file exists and is readable, else None.
    Empty files are treated as None.
    """
    try:
        if not CLAUDE_OAUTH_TOKEN_FILE.is_file():
            return None
        token = CLAUDE_OAUTH_TOKEN_FILE.read_text(encoding="utf-8").strip()
        return token or None
    except OSError:
        return None


def _build_claude_env() -> dict[str, str]:
    """Return a minimal env for nested claude invocations, including OAuth token.

    Empirical findings (2026-05-07 / 2026-05-13):

    - Inheriting `CLAUDECODE`, `CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST`,
      `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_AGENT_SDK_VERSION`, etc. causes
      "401 Invalid authentication credentials" — those vars signal "the host
      Claude Desktop manages auth" and steer claude away from its own
      auth path.
    - Inheriting `USER` ALSO causes 401. Reason unknown — likely some
      internal multi-user detection in claude. Other identity-style vars
      (LOGNAME, SHELL) do NOT cause this.
    - All other "neutral" env vars (PATH, HOME, TMPDIR, LANG, TZ, TERM,
      LOGNAME, SHELL, LC_ALL) are fine.

    Auth strategy: `CLAUDE_CODE_OAUTH_TOKEN`. After Claude Desktop 2.1.138
    the OAuth-refresh path requires an XPC connection to Desktop that's
    unreachable from inside `codex exec`'s sandbox (the API returns 401
    on every nested call). The supported workaround is `claude setup-token`,
    which generates a long-lived OAuth token (~1 year TTL) tied to the
    user's Claude subscription. The token is read from the file documented
    on `CLAUDE_OAUTH_TOKEN_FILE` and injected as the
    `CLAUDE_CODE_OAUTH_TOKEN` env var. With this var set, claude skips
    OAuth refresh and authenticates directly — works in any context.

    If the file is absent the env var isn't set and claude falls back to
    its normal auth path. That path WILL fail in cron context (the whole
    reason for the token file), but the function still returns a usable
    env so manual / interactive runs (where OAuth is healthy) keep working.
    """
    keep = ("HOME", "PATH", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "TERM", "SHELL", "TZ")
    env = {k: v for k, v in os.environ.items() if k in keep}
    token = _read_claude_oauth_token()
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    return env


def invoke_claude(
    prompt: str, *, cwd: Path, additional_dirs: list[Path], log_file: Path, timeout: int
) -> tuple[bool, str]:
    binary = _resolve_claude_binary()
    if binary is None:
        return (
            False,
            "claude CLI not found (no CLAUDE_CODE_EXECPATH, no Claude Desktop bundle, not on PATH)",
        )
    cmd = [
        binary,
        "-p",
        "--permission-mode",
        "bypassPermissions",
        "--no-session-persistence",
    ]
    for extra in additional_dirs:
        cmd.extend(["--add-dir", str(extra)])
    env = _build_claude_env()
    result = run_with_heartbeat(
        cmd,
        prompt=prompt,
        cwd=cwd,
        env=env,
        log_file=log_file,
        timeout=timeout,
        heartbeat_interval=_HEARTBEAT_INTERVAL,
        stall_threshold=_STALL_THRESHOLD,
        label="claude",
    )
    if result.succeeded:
        return True, str(log_file)
    if result.stuck:
        return (
            False,
            f"claude stuck (no log growth for >{_STALL_THRESHOLD}s; terminated): {log_file}",
        )
    if result.timed_out:
        return False, f"claude timed out after {timeout}s (log: {log_file})"
    return False, f"claude exited {result.returncode} ({result.note}; log: {log_file})"


def invoke_agent(
    agent_label: str,
    prompt: str,
    *,
    cwd: Path,
    additional_dirs: list[Path],
    log_file: Path,
    timeout: int,
) -> tuple[bool, str]:
    """Dispatch to the right invoker by agent_label.

    Pilot identifiers like `pilot-claude` route to the corresponding base
    agent (`claude`); the production cron uses bare `codex` / `claude`.
    """
    base = agent_label
    if agent_label.startswith("pilot-"):
        base = agent_label[len("pilot-") :]
    if base == "codex":
        return invoke_codex(prompt, cwd=cwd, log_file=log_file, timeout=timeout)
    if base == "claude":
        return invoke_claude(
            prompt,
            cwd=cwd,
            additional_dirs=additional_dirs,
            log_file=log_file,
            timeout=timeout,
        )
    return False, f"unknown agent label {agent_label!r} (base {base!r})"


# ---------------------------------------------------------------------------
# Per-turn orchestration
# ---------------------------------------------------------------------------


def run_one_turn(
    *,
    repo: str,
    turn: int,
    output_dir: Path,
    agents: dict[str, Path],
    additional_dirs: list[Path],
    timeout: int,
    retries: int,
    dry_run: bool,
    log_dir: Path,
) -> dict[str, AgentTurnResult]:
    """Spawn both agents in parallel for one turn (or reuse existing outputs)."""
    results: dict[str, AgentTurnResult] = {}
    prior_turn_paths = sorted(
        path
        for path in (output_dir / "round2" / safe_repo_name(repo)).glob("turn-*/*.json")
        if "turn-" in path.parts[-2] and int(path.parts[-2].rsplit("-", 1)[-1]) < turn
    )

    def task(agent_label: str) -> AgentTurnResult:
        agent_other = next(other for other in agents if other != agent_label)
        out_path = round2_turn_path(output_dir, repo, turn, agent_label)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.is_file():
            return AgentTurnResult(
                agent=agent_label, turn=turn, output_path=out_path, succeeded=True, spawned=False
            )
        if dry_run:
            return AgentTurnResult(
                agent=agent_label,
                turn=turn,
                output_path=out_path,
                succeeded=False,
                spawned=False,
                error="dry-run: turn output absent and agent spawn skipped",
            )
        prompt = build_prompt(
            repo=repo,
            turn=turn,
            my_agent=agent_label,
            other_agent=agent_other,
            my_findings=agents[agent_label],
            other_findings=agents[agent_other],
            turn_output_path=out_path,
            prior_turn_paths=prior_turn_paths,
        )
        last_error = ""
        for attempt in range(1, retries + 2):
            log_file = log_dir / f"{agent_label}-turn-{turn}-attempt-{attempt}.log"
            ok, info = invoke_agent(
                agent_label,
                prompt,
                cwd=WORKFLOWS_STEWARD,
                additional_dirs=additional_dirs,
                log_file=log_file,
                timeout=timeout,
            )
            if ok and out_path.is_file():
                return AgentTurnResult(
                    agent=agent_label,
                    turn=turn,
                    output_path=out_path,
                    succeeded=True,
                    spawned=True,
                )
            last_error = info if not ok else f"agent did not write {out_path}"
            time.sleep(2)
        return AgentTurnResult(
            agent=agent_label,
            turn=turn,
            output_path=out_path,
            succeeded=False,
            spawned=True,
            error=last_error,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(agents)) as executor:
        futures = {executor.submit(task, label): label for label in agents}
        for future in concurrent.futures.as_completed(futures):
            label = futures[future]
            results[label] = future.result()
    return results


# ---------------------------------------------------------------------------
# Validation + convergence computation
# ---------------------------------------------------------------------------


def load_turn(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_or_die(turn_data: dict[str, Any], path: Path, expected_repo: str) -> None:
    errors = validate_turn_output(turn_data, expected_repo=expected_repo)
    if errors:
        formatted = "\n".join(f"  - {e}" for e in errors)
        raise SystemExit(f"Turn output {path} failed schema validation:\n{formatted}")


def index_round1_candidates(
    round1_paths: dict[str, Path],
) -> dict[CandidateKey, dict[str, Any]]:
    """Build a map of (source_agent, candidate_index) -> round-1 candidate dict."""
    index: dict[CandidateKey, dict[str, Any]] = {}
    for agent, path in round1_paths.items():
        data = json.loads(path.read_text(encoding="utf-8"))
        for i, candidate in enumerate(data.get("candidates") or [], start=1):
            if isinstance(candidate, dict):
                index[CandidateKey(agent, i)] = candidate
    return index


def collect_marks_per_candidate(
    turn_outputs: list[dict[str, Any]],
) -> dict[CandidateKey, list[dict[str, Any]]]:
    """Group all marks across all turns by the candidate they target."""
    by_candidate: dict[CandidateKey, list[dict[str, Any]]] = {}
    for turn_out in turn_outputs:
        for mark in turn_out.get("marks", []) or []:
            key = CandidateKey(mark["source_agent"], int(mark["candidate_index"]))
            by_candidate.setdefault(key, []).append(
                {
                    "from_agent": turn_out["agent"],
                    "turn": int(turn_out["turn"]),
                    "mark": mark["mark"],
                    "reason": mark.get("reason", ""),
                    "merge_proposal": mark.get("merge_proposal"),
                    "revision_proposal": mark.get("revision_proposal"),
                }
            )
    return by_candidate


def compute_convergence(
    candidate_keys: list[CandidateKey],
    marks_by_candidate: dict[CandidateKey, list[dict[str, Any]]],
    expected_marker_agents: set[str],
) -> dict[CandidateKey, CandidateResolution]:
    """Decide each candidate's negotiation state from the latest marks.

    A candidate is resolved when all expected agents have marked it AND the
    marks combine to a defined outcome:
      - both `agree-keep` (or `agree-merge` with compatible proposals) → converged
      - both `disagree-drop` → dropped
      - mixed → pending (carries to next turn)

    The latest mark from each agent (highest turn) is what counts.

    **Implicit source-agent endorsement**: a candidate's source agent has
    already declared "this is a real gap" by submitting it in round 1. If
    that agent never issues an explicit turn-N mark on its own candidate,
    we treat its submission as an implicit `agree-keep` at turn 0. Without
    this, the common case (agent A submits, agent B agree-keeps in turn 1,
    agent A doesn't bother to re-affirm) gets stuck in `pending` forever
    and ends up `deadlocked` — even though both agents endorse it.
    Surfaced 2026-05-13 by 2 candidates in attempt-9 (TPP + Inv-Man-Intake)
    that were real, fully-traced gaps misclassified as deadlocked.

    If the source agent issues a real later-turn mark (e.g., revises or
    drops their own candidate), the latest-turn rule preserves that —
    the implicit turn-0 mark is overridden by the explicit one.
    """
    resolutions: dict[CandidateKey, CandidateResolution] = {}
    for key in candidate_keys:
        history = marks_by_candidate.get(key, [])
        latest_per_agent: dict[str, dict[str, Any]] = {}
        for entry in history:
            existing = latest_per_agent.get(entry["from_agent"])
            if existing is None or entry["turn"] > existing["turn"]:
                latest_per_agent[entry["from_agent"]] = entry

        # Inject the implicit source-agent agree-keep iff the source agent
        # hasn't issued any explicit mark. Turn 0 < any real turn, so an
        # explicit later-turn mark from the source agent always wins.
        if key.source_agent and key.source_agent not in latest_per_agent:
            latest_per_agent[key.source_agent] = {
                "from_agent": key.source_agent,
                "turn": 0,
                "mark": "agree-keep",
                "reason": (
                    "(implicit) candidate was sourced by this agent in round 1; "
                    "submission counts as an agree-keep until explicitly revised."
                ),
                "merge_proposal": None,
                "revision_proposal": None,
            }

        missing = expected_marker_agents - set(latest_per_agent.keys())
        if missing:
            resolutions[key] = CandidateResolution(key=key, status="pending", marks_history=history)
            continue

        marks = {a: entry["mark"] for a, entry in latest_per_agent.items()}
        unique = set(marks.values())

        if unique == {"agree-keep"}:
            resolutions[key] = CandidateResolution(
                key=key, status="converged-keep", marks_history=history
            )
        elif unique == {"agree-merge"}:
            # Both sides proposed merges; converged-merge with combined framing.
            merge_a = next(
                e["merge_proposal"] for e in latest_per_agent.values() if e.get("merge_proposal")
            )
            resolutions[key] = CandidateResolution(
                key=key,
                status="converged-merge",
                marks_history=history,
                merge_proposal=merge_a,
            )
        elif unique <= {"agree-keep", "agree-merge"}:
            # One agent agrees-keep, the other proposes merge — accept the merge framing.
            merge_proposal = next(
                (e["merge_proposal"] for e in latest_per_agent.values() if e.get("merge_proposal")),
                None,
            )
            resolutions[key] = CandidateResolution(
                key=key,
                status="converged-merge",
                marks_history=history,
                merge_proposal=merge_proposal,
            )
        elif unique == {"disagree-drop"}:
            reason = "; ".join(
                str(e.get("reason", "")).strip()
                for e in latest_per_agent.values()
                if e.get("reason")
            )
            resolutions[key] = CandidateResolution(
                key=key,
                status="converged-drop",
                marks_history=history,
                drop_reason=reason or "Both agents agreed to drop.",
            )
        else:
            resolutions[key] = CandidateResolution(key=key, status="pending", marks_history=history)
    return resolutions


# ---------------------------------------------------------------------------
# Meta-candidate convergence
# ---------------------------------------------------------------------------


def meta_proposals(turn_outputs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return {agent: latest_meta_proposal} across all turns (latest by turn)."""
    latest: dict[str, dict[str, Any]] = {}
    for turn_out in turn_outputs:
        meta = turn_out.get("meta_candidate_proposal") or {}
        if not isinstance(meta, dict):
            continue
        agent = turn_out["agent"]
        existing = latest.get(agent)
        if existing is None or turn_out["turn"] > existing.get("__turn", 0):
            entry = dict(meta)
            entry["__turn"] = turn_out["turn"]
            latest[agent] = entry
    return latest


def supporting_set(meta: dict[str, Any]) -> set[tuple[str, int]]:
    items = meta.get("supporting_candidate_indexes") or []
    out: set[tuple[str, int]] = set()
    for item in items:
        if isinstance(item, dict):
            agent = str(item.get("agent", ""))
            idx = item.get("candidate_index")
            if agent and isinstance(idx, int):
                out.add((agent, idx))
    return out


def converge_meta(
    meta_by_agent: dict[str, dict[str, Any]],
    expected_marker_agents: set[str],
) -> tuple[dict[str, Any] | None, str]:
    """Return (converged_meta, status_label).

    Status values:
      - "converged"   : both agents proposed compatible meta-candidates.
      - "single-side" : only one agent proposed (no rejection).
      - "deadlocked"  : agents disagree on whether a pattern exists.
      - "absent"      : neither agent proposed.

    Compatibility = supporting-set overlap ≥ META_PATTERN_OVERLAP_FLOOR of the
    smaller set.
    """
    proposing = {
        agent: meta for agent, meta in meta_by_agent.items() if meta.get("proposed") is True
    }
    if not proposing:
        return None, "absent"
    if expected_marker_agents - set(meta_by_agent.keys()):
        return None, "single-side"
    rejecting = [agent for agent, meta in meta_by_agent.items() if meta.get("proposed") is False]
    if proposing and rejecting:
        # Deadlocked: one (or more) agent proposed a meta-candidate; one (or
        # more) explicitly rejected. Per the protocol, surface the rejected
        # meta to the human packet rather than silently dropping it. Returning
        # the proposing-side proposal lets the synthesizer record it in the
        # converged.json under deadlocked_meta with both agents' positions.
        only = next(iter(proposing.values()))
        only["__rejected_by"] = list(rejecting)
        return only, "deadlocked"
    if len(proposing) == 1:
        only = next(iter(proposing.values()))
        return only, "single-side"

    # Both agents proposed. Check supporting-set compatibility.
    sets = {agent: supporting_set(meta) for agent, meta in proposing.items()}
    sizes = sorted((len(s) for s in sets.values()), reverse=True)
    union = set().union(*sets.values())
    intersection = set.intersection(*sets.values())
    if not sizes or sizes[-1] == 0:
        return None, "deadlocked"
    overlap = len(intersection) / sizes[-1]
    if overlap < META_PATTERN_OVERLAP_FLOOR:
        return None, "deadlocked"

    # Compatible. Pick the proposal with the longer pattern + more tasks; it's
    # the more concrete one. Preserve the alternative title in the merged meta.
    def proposal_score(meta: dict[str, Any]) -> int:
        pattern_len = len(str(meta.get("pattern", "")))
        task_count = len(meta.get("tasks", []) or [])
        accept_count = len(meta.get("acceptance_criteria", []) or [])
        return pattern_len + task_count * 30 + accept_count * 30

    primary_agent, primary = max(proposing.items(), key=lambda kv: proposal_score(kv[1]))
    alternative_titles = [
        {"agent": a, "title": m.get("title", "")}
        for a, m in proposing.items()
        if a != primary_agent
    ]
    merged = dict(primary)
    merged.pop("__turn", None)
    merged["compatible_alternative_proposals"] = alternative_titles
    merged["primary_source_agent"] = primary_agent
    merged["supporting_candidate_indexes"] = [
        {"agent": agent, "candidate_index": idx} for agent, idx in sorted(union)
    ]
    return merged, "converged"


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


def candidate_for_resolution(
    resolution: CandidateResolution,
    round1_index: dict[CandidateKey, dict[str, Any]],
) -> dict[str, Any]:
    base = round1_index.get(resolution.key)
    if base is None:
        # Should not happen — every key comes from a round-1 finding.
        raise SystemExit(f"BUG: round-1 candidate {resolution.key} missing from index")
    cand = dict(base)
    cand["scope"] = "fix"
    cand["origin"] = {
        "source_agent": resolution.key.source_agent,
        "round1_index": resolution.key.candidate_index,
        "merged_from": None,
    }
    if resolution.status == "converged-merge" and resolution.merge_proposal:
        # Apply the merge proposal on top of the base — preserves design refs
        # etc. while letting the merged framing override title/gap/etc.
        cand.update({k: v for k, v in resolution.merge_proposal.items() if v is not None})
        cand["origin"]["merged_from"] = [resolution.merge_proposal.get("source", "")]
    return cand


def meta_to_candidate(
    meta: dict[str, Any],
    primary_agent: str,
    round1_index: dict[CandidateKey, dict[str, Any]],
) -> dict[str, Any]:
    """Convert a round-2 meta proposal into a converged candidate dict.

    The meta-candidate inherits design/implementation/test refs from the
    supporting per-instance candidates so the auto-derived evidence trace has
    non-empty ref lists; without that the quality gate's
    `review_evidence_trace_errors` check fails on missing refs.
    """
    merged_from = [{"agent": primary_agent, "turn": 1}]
    for alt in meta.get("compatible_alternative_proposals", []) or []:
        merged_from.append({"agent": alt.get("agent", ""), "turn": 1})

    def _union_refs(field: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for ref in meta.get("supporting_candidate_indexes") or []:
            if not isinstance(ref, dict):
                continue
            key = CandidateKey(str(ref.get("agent", "")), int(ref.get("candidate_index", 0)))
            base = round1_index.get(key) or {}
            for value in base.get(field) or []:
                value_str = str(value)
                if value_str and value_str not in seen:
                    seen.add(value_str)
                    out.append(value_str)
        return out

    return {
        "title": meta.get("title", ""),
        "gap": meta.get("pattern", ""),
        "current_state": meta.get("rationale", ""),
        "required_change": (
            "Enumerate every site matching the pattern, classify each, file "
            "follow-up issues for non-converged instances, and add a regression-"
            "prevention gate."
        ),
        "design_refs": _union_refs("design_refs"),
        "implementation_refs": _union_refs("implementation_refs"),
        "test_refs": _union_refs("test_refs"),
        "acceptance_criteria": list(meta.get("acceptance_criteria") or []),
        "non_goals": list(meta.get("non_goals") or []),
        "tasks": list(meta.get("tasks") or []),
        "priority": meta.get("priority", "normal"),
        "confidence": meta.get("confidence", "medium"),
        "scope": "audit",
        "origin": {
            "source_agent": "merged",
            "round1_index": None,
            "merged_from": merged_from,
        },
        "supporting_per_instance_candidates": [
            {"agent": ref["agent"], "candidate_index": ref["candidate_index"]}
            for ref in meta.get("supporting_candidate_indexes") or []
            if isinstance(ref, dict)
        ],
        "compatible_alternative_proposals": list(
            meta.get("compatible_alternative_proposals") or []
        ),
    }


def _collect_no_new_work_justifications(
    round1_paths: dict[str, Path],
) -> list[dict[str, str]]:
    """Read each round-1 finding's `no_new_work_justification` for packet display.

    Returns a list of {agent, justification} dicts (empty string when absent).
    Only meaningful when round-1 produced 0 candidates on at least one side.
    """
    out: list[dict[str, str]] = []
    for agent, path in round1_paths.items():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        justification = str(data.get("no_new_work_justification") or "").strip()
        out.append(
            {
                "agent": agent,
                "candidate_count": len(data.get("candidates") or []),
                "justification": justification,
            }
        )
    return out


def synthesize_converged(
    *,
    repo: str,
    output_dir: Path,
    round1_paths: dict[str, Path],
    turn_outputs: list[dict[str, Any]],
    turns_completed: int,
    final_resolutions: dict[CandidateKey, CandidateResolution],
    meta_proposal: dict[str, Any] | None,
    meta_status: str,
    deadlocked_reason_max_turns_exhausted: bool,
) -> dict[str, Any]:
    round1_index = index_round1_candidates(round1_paths)

    converged_candidates: list[dict[str, Any]] = []
    deadlocked_candidates: list[dict[str, Any]] = []
    dropped_candidates: list[dict[str, Any]] = []

    # Track merge-proposal titles we've already emitted so that paired
    # agree-merge marks (Codex C2 + Claude C2 → same gap) collapse to one
    # converged entry, not two duplicates. Iteration 3 (Inv-Man-Intake)
    # surfaced this — the design intent of agree-merge is "the two round-1
    # candidates describe the same gap; ship one merged result."
    merge_title_to_index: dict[str, int] = {}

    for key, resolution in final_resolutions.items():
        if resolution.status in ("converged-keep", "converged-merge"):
            cand = candidate_for_resolution(resolution, round1_index)
            if resolution.status == "converged-merge":
                merge_title = (
                    str(resolution.merge_proposal.get("title") or "").strip()
                    if resolution.merge_proposal
                    else ""
                )
                if merge_title and merge_title in merge_title_to_index:
                    # Same merge target as a prior resolution — fold this
                    # round-1 source into the existing entry's merged_from list
                    # and skip emitting a duplicate.
                    existing = converged_candidates[merge_title_to_index[merge_title]]
                    merged_from = existing["origin"].get("merged_from") or []
                    if not isinstance(merged_from, list):
                        merged_from = [merged_from]
                    addition = {
                        "agent": key.source_agent,
                        "round1_index": key.candidate_index,
                    }
                    if addition not in merged_from:
                        merged_from.append(addition)
                    existing["origin"]["merged_from"] = merged_from
                    continue
                if merge_title:
                    merge_title_to_index[merge_title] = len(converged_candidates)
                cand["origin"]["merged_from"] = [
                    {
                        "agent": key.source_agent,
                        "round1_index": key.candidate_index,
                    }
                ]
            converged_candidates.append(cand)
        elif resolution.status == "converged-drop":
            base = round1_index[key]
            dropped_candidates.append(
                {
                    "title": base.get("title", ""),
                    "source_agent": key.source_agent,
                    "round1_index": key.candidate_index,
                    "drop_reason": resolution.drop_reason,
                }
            )
        else:  # pending — became deadlocked because we ran out of turns
            base = round1_index[key]
            deadlocked_candidates.append(
                {
                    "title": base.get("title", ""),
                    "source_agent": key.source_agent,
                    "round1_index": key.candidate_index,
                    "marks_history": resolution.marks_history,
                }
            )

    meta_candidate: dict[str, Any] | None = None
    deadlocked_meta: dict[str, Any] | None = None
    if meta_proposal is not None and meta_status in ("converged", "single-side"):
        primary_agent = meta_proposal.get("primary_source_agent") or next(
            (
                tout["agent"]
                for tout in turn_outputs
                if (tout.get("meta_candidate_proposal") or {}).get("proposed") is True
            ),
            "merged",
        )
        meta_candidate = meta_to_candidate(meta_proposal, primary_agent, round1_index)
    elif meta_proposal is not None and meta_status == "deadlocked":
        # One agent proposed, the other rejected. Surface the proposal to the
        # human packet as a deadlocked meta-candidate so the human can break
        # the tie rather than the rejected proposal getting silently dropped.
        proposing_agent = next(
            (
                tout["agent"]
                for tout in turn_outputs
                if (tout.get("meta_candidate_proposal") or {}).get("proposed") is True
            ),
            "unknown",
        )
        rejecting_agents = list(meta_proposal.get("__rejected_by", []) or [])
        rejection_reasons: dict[str, str] = {}
        for tout in turn_outputs:
            mp = tout.get("meta_candidate_proposal") or {}
            if mp.get("proposed") is False:
                rejection_reasons[tout["agent"]] = str(
                    mp.get("rationale", "") or mp.get("reason", "") or "no rationale recorded"
                )
        deadlocked_meta = {
            "proposed_by": proposing_agent,
            "rejected_by": rejecting_agents,
            "rejection_reasons": rejection_reasons,
            "title": meta_proposal.get("title", ""),
            "pattern": meta_proposal.get("pattern", ""),
            "rationale": meta_proposal.get("rationale", ""),
            "supporting_candidate_indexes": list(
                meta_proposal.get("supporting_candidate_indexes") or []
            ),
            "priority": meta_proposal.get("priority", "low"),
            "confidence": meta_proposal.get("confidence", "low"),
        }

    return {
        "schema_version": "v1",
        "repo": repo,
        "turns_completed": turns_completed,
        "round1_sources": [
            {
                "agent": agent,
                "path": str(path.resolve()),
                "candidate_count": len(
                    json.loads(path.read_text(encoding="utf-8")).get("candidates") or []
                ),
            }
            for agent, path in round1_paths.items()
        ],
        "converged_candidates": converged_candidates,
        "deadlocked_candidates": deadlocked_candidates,
        "dropped_candidates": dropped_candidates,
        "meta_candidate": meta_candidate,
        "meta_status": meta_status,
        "deadlocked_meta": deadlocked_meta,
        # When both round-1 sides produced 0 candidates, both agents wrote a
        # `no_new_work_justification` arguing the active backlog is sufficient.
        # Carry both forward so the human packet can show them side-by-side
        # and the human can verify the justifications match the actual repo
        # state before accepting "no new work" as the cycle outcome.
        "no_new_work_justifications": _collect_no_new_work_justifications(round1_paths),
        "negotiation_log": [
            str(round2_turn_path(output_dir, repo, t["turn"], t["agent"]).resolve())
            for t in turn_outputs
        ],
        "synthesized_at": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir).resolve()
    repo = args.repo
    requested_agents = tuple(a.strip() for a in args.agents.split(",") if a.strip())
    if len(requested_agents) != 2:
        raise SystemExit("--agents must list exactly two labels (e.g. codex,claude)")

    round1_paths = resolve_negotiation_agents(output_dir, repo, requested_agents)
    expected_marker_agents = set(round1_paths.keys())
    print(
        f"[round2] {repo}: round-1 findings resolved → "
        + ", ".join(f"{k}={v}" for k, v in round1_paths.items())
    )

    log_dir = output_dir / "round2" / safe_repo_name(repo) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    additional_dirs = sorted(
        {
            output_dir,
            *(p.parent.parent.parent.parent for p in round1_paths.values()),
        }
    )

    turn_outputs: list[dict[str, Any]] = []
    candidate_keys = list(index_round1_candidates(round1_paths).keys())
    final_resolutions: dict[CandidateKey, CandidateResolution] = {}
    turns_completed = 0
    fully_converged = False
    meta_status = "absent"
    meta_proposal: dict[str, Any] | None = None

    # When both round-1 sides produced 0 candidates, round-2 has nothing to
    # negotiate: no marks to record, no meta possible (the schema requires
    # ≥2 supporting candidates). Short-circuit to direct synthesis with
    # converged_candidates=[] and both agents' no_new_work_justifications
    # carried forward to the human packet via deadlocked-meta-style records.
    if not candidate_keys:
        print(f"[round2] {repo}: both round-1 findings empty — skipping negotiation")
        fully_converged = True
        # No marks, no meta — synthesize a convergence record that carries the
        # round-1 justifications through to the human packet.
        turns_completed = 0
        meta_status = "absent"
        meta_proposal = None
        # Fall through to synthesis with empty resolutions / turn_outputs.
        turn_outputs = []
        final_resolutions = {}

    for turn in range(1, args.max_turns + 1) if candidate_keys else ():
        print(f"[round2] {repo}: turn {turn} starting")
        turn_results = run_one_turn(
            repo=repo,
            turn=turn,
            output_dir=output_dir,
            agents=round1_paths,
            additional_dirs=additional_dirs,
            timeout=args.turn_timeout,
            retries=args.retries,
            dry_run=args.dry_run,
            log_dir=log_dir,
        )
        for label, result in turn_results.items():
            status = "succeeded" if result.succeeded else f"failed: {result.error}"
            spawned = "spawned" if result.spawned else "reused"
            print(f"[round2] {repo}: turn {turn} {label} → {status} ({spawned})")
        if not all(r.succeeded for r in turn_results.values()):
            failures = [
                f"{label}: {r.error}" for label, r in turn_results.items() if not r.succeeded
            ]
            print(
                f"[round2] {repo}: turn {turn} aborted — " + "; ".join(failures),
                file=sys.stderr,
            )
            if args.dry_run:
                # In dry-run we tolerate missing turn outputs and synthesize
                # whatever's on disk.
                break
            return 2

        turns_completed = turn
        # Load + validate
        for label in round1_paths:
            path = round2_turn_path(output_dir, repo, turn, label)
            data = load_turn(path)
            validate_or_die(data, path, expected_repo=repo)
            turn_outputs.append(data)

        marks_by_candidate = collect_marks_per_candidate(turn_outputs)
        final_resolutions = compute_convergence(
            candidate_keys, marks_by_candidate, expected_marker_agents
        )
        meta_by_agent = meta_proposals(turn_outputs)
        meta_proposal, meta_status = converge_meta(meta_by_agent, expected_marker_agents)

        pending = [r for r in final_resolutions.values() if r.status == "pending"]
        meta_pending = meta_status not in ("converged", "absent", "deadlocked", "single-side")
        if not pending and not meta_pending:
            print(
                f"[round2] {repo}: fully converged after turn {turn} "
                f"({len(final_resolutions)} candidates, meta_status={meta_status})"
            )
            fully_converged = True
            break
        print(
            f"[round2] {repo}: after turn {turn}, {len(pending)} pending, meta_status={meta_status}"
        )

    converged = synthesize_converged(
        repo=repo,
        output_dir=output_dir,
        round1_paths=round1_paths,
        turn_outputs=turn_outputs,
        turns_completed=turns_completed,
        final_resolutions=final_resolutions,
        meta_proposal=meta_proposal,
        meta_status=meta_status,
        deadlocked_reason_max_turns_exhausted=not fully_converged,
    )
    errors = validate_converged_set(converged, expected_repo=repo)
    if errors:
        formatted = "\n".join(f"  - {e}" for e in errors)
        print(
            f"[round2] {repo}: synthesized converged set failed validation:\n{formatted}",
            file=sys.stderr,
        )
        return 3

    converged_path = round2_converged_path(output_dir, repo)
    converged_path.parent.mkdir(parents=True, exist_ok=True)
    converged_path.write_text(json.dumps(converged, indent=2) + "\n", encoding="utf-8")

    # Repo-scoped state update — never touches global state. If anything goes
    # wrong with this repo, remediation work stays inside its directory.
    if not args.dry_run:
        state = load_state(output_dir, repo)
        attempt = begin_attempt(state, phase="round-2", agent="runner")
        finish_attempt(
            state,
            attempt,
            succeeded=True,
            notes=(
                f"turns={turns_completed} converged={len(converged['converged_candidates'])} "
                f"deadlocked={len(converged['deadlocked_candidates'])} "
                f"meta={'present' if converged['meta_candidate'] else 'absent'}"
            ),
        )
        record_round2_converged(state, converged_path)
        # A deadlocked meta is still a human-resolution case — surface it as
        # round2-deadlocked even when converged_candidates is clean.
        if converged["deadlocked_candidates"] or converged.get("deadlocked_meta"):
            transition(state, status="round2-deadlocked")
        else:
            transition(state, status="round2-converged")
        save_state(output_dir, state)

    print(
        f"[round2] {repo}: wrote {converged_path} "
        f"(turns={turns_completed}, "
        f"converged={len(converged['converged_candidates'])}, "
        f"deadlocked={len(converged['deadlocked_candidates'])}, "
        f"dropped={len(converged['dropped_candidates'])}, "
        f"meta={'present' if converged['meta_candidate'] else 'none'})"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/name of the repo")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="evaluator output directory containing round1/ and round2/ subtrees",
    )
    parser.add_argument(
        "--agents",
        default=",".join(DEFAULT_AGENTS),
        help=f"Comma-separated agent labels (default: {','.join(DEFAULT_AGENTS)})",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=DEFAULT_MAX_TURNS,
        help=f"Maximum negotiation turns (default {DEFAULT_MAX_TURNS})",
    )
    parser.add_argument(
        "--turn-timeout",
        type=int,
        default=DEFAULT_TURN_TIMEOUT_SECONDS,
        help=f"Per-agent per-turn timeout, seconds (default {DEFAULT_TURN_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help=f"Retries per (agent, turn) on failure (default {DEFAULT_RETRIES})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Synthesize converged.json from existing turn outputs only; never spawn agents.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
