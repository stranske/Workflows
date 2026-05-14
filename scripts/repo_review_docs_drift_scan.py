#!/usr/bin/env python3
"""Weekly scan of source-of-truth operational docs for drift vs current implementation.

The 2026-05-13 weekly cycle confirmed three drift instances in Workflows
source-of-truth docs (README model versions, docs/ci/WORKFLOWS.md autofix
self-contradiction, docs/ops/REPO_REVIEW_PROCESS.md pre-Phase-4 entry point).
Each was discovered ad-hoc by a round-1 reviewer agent looking at a different
design slice. There is no recurring mechanism that catches drift between
weekly cycles -- drift just accumulates until somebody happens to read an
affected doc and notice. CLAUDE.md flags this failure mode explicitly
(agents read docs as authoritative input to their reasoning; stale docs
compound the damage).

This scanner runs once per cycle, after backlog-scan and before notify. For
each (repo, doc) pair in ``config/source_of_truth_docs.yml`` it invokes
claude with a focused prompt that reads the doc plus the relevant
implementation files, and emits a JSON list of drift instances each
classified as ``stale``, ``contradictory``, or ``accurate-no-drift``. The
output JSON lands at ``<output_dir>/docs-drift-scan.json``; the notify
helper renders one bundled remediation block per repo with non-empty
non-accurate drift, with a ready-to-paste ``gh issue create`` snippet.

The scanner is structurally non-fatal: any failure (claude unavailable,
prompt rejection, JSON parse error, doc missing) is recorded against that
(repo, doc) pair and the scan continues. The coordinator wraps the whole
script in the same non-fatal pattern as ``repo_review_backlog_scan.py``.

GitNexus integration is graceful: when the repo's ``.gitnexus/meta.json``
is missing or marked stale, the scanner instructs claude to skip behavioral
call-graph checks and rely on ``rg`` for pattern-based existence checks
only. This is not failure -- it is documented in the per-doc result.

CLI:

    python scripts/repo_review_docs_drift_scan.py \\
        --registry config/repo_review_registry.json \\
        --docs-config config/source_of_truth_docs.yml \\
        --out docs/reports/repo-review/docs-drift-scan.json

Flags:

    --workspace-root <path>   parent dir containing each repo's local_path
                              (default: '..' relative to --registry parent)
    --repos <repo> [<repo>]   restrict to a subset (default: all active)
    --timeout <seconds>       per-doc claude timeout (default: 600)
    --dry-run                 skip claude calls; emit empty drift result per
                              doc. Used by tests and by local cron rehearsal
                              when claude auth is unavailable.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

VALID_CLASSIFICATIONS = ("stale", "contradictory", "accurate-no-drift")
DRIFT_CLASSIFICATIONS = ("stale", "contradictory")

DEFAULT_PER_DOC_TIMEOUT = 600

CLAUDE_OAUTH_TOKEN_FILE = Path(
    os.path.expanduser(
        "~/.codex/automations/reviewed-repo-weekly-design-review/claude-oauth-token.txt"
    )
)


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class DriftInstance:
    doc_path: str
    claim: str
    authoritative_source: str
    classification: str  # stale | contradictory | accurate-no-drift


@dataclass
class DocResult:
    repo: str
    doc_path: str
    instances: list[DriftInstance] = field(default_factory=list)
    gitnexus_status: str = "unknown"
    error: str | None = None  # populated when claude/JSON parsing failed


# ---------------------------------------------------------------------------
# Config + registry
# ---------------------------------------------------------------------------


def load_docs_config(path: Path) -> dict[str, dict[str, Any]]:
    """Return ``{ "<owner>/<repo>": {"local_path": ..., "docs": [...]} }``."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    repos = data.get("repos") or {}
    if not isinstance(repos, dict):
        raise ValueError(f"docs config root.repos must be a mapping, got {type(repos).__name__}")
    return repos


def load_active_repos(registry_path: Path) -> set[str]:
    """Return the active-repo full-names from the registry (filter set)."""
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    return {
        str(r.get("repo"))
        for r in (data.get("repos") or [])
        if isinstance(r, dict) and r.get("status") == "active" and r.get("repo")
    }


def resolve_workspace_root(registry_path: Path) -> Path:
    """Resolve the registry's workspace_root using the evaluator contract."""
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    workspace_root = Path(data.get("workspace_root", "."))
    if not workspace_root.is_absolute():
        workspace_root = (registry_path.resolve().parent.parent / workspace_root).resolve()
    return workspace_root


# ---------------------------------------------------------------------------
# GitNexus staleness
# ---------------------------------------------------------------------------


def is_gitnexus_stale(repo_root: Path) -> str:
    """Return ``fresh``, ``stale``, or ``missing`` for the repo's GitNexus map.

    ``.gitnexus/meta.json`` is the source of truth. ``stale: true`` (or any
    truthy value at that key) means the map is older than the configured TTL
    and behavioral call-graph queries should be skipped. Anything that fails
    to parse is treated as ``missing`` so the scanner degrades gracefully.
    """
    meta = repo_root / ".gitnexus" / "meta.json"
    if not meta.is_file():
        return "missing"
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "missing"
    if data.get("stale"):
        return "stale"
    return "fresh"


# ---------------------------------------------------------------------------
# Response parsing (pure -- this is what the tests pin down)
# ---------------------------------------------------------------------------


def parse_drift_response(raw_text: str, *, doc_path: str) -> tuple[list[DriftInstance], str | None]:
    """Extract the drift-instance list from a claude response.

    Claude may wrap the JSON in prose, fenced code blocks, or commentary.
    We extract the outermost JSON object, validate its shape, and coerce
    each instance to ``DriftInstance``. Returns ``(instances, error)``;
    ``error`` is non-None when nothing parseable was found.
    """
    if not raw_text or not raw_text.strip():
        return [], "empty response"
    decoder = json.JSONDecoder()
    payload: Any | None = None
    last_error: json.JSONDecodeError | None = None
    for start, char in enumerate(raw_text):
        if char != "{":
            continue
        try:
            candidate, _end = decoder.raw_decode(raw_text[start:])
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(candidate, dict) and "instances" in candidate:
            payload = candidate
            break
    if payload is None:
        if last_error:
            return [], f"JSON decode failed: {last_error.msg}"
        return [], "no JSON object found in response"
    if not isinstance(payload, dict):
        return [], "JSON root is not an object"

    raw_instances = payload.get("instances") or []
    if not isinstance(raw_instances, list):
        return [], "'instances' is not a list"

    result: list[DriftInstance] = []
    for item in raw_instances:
        if not isinstance(item, dict):
            continue
        classification = str(item.get("classification") or "").strip()
        if classification not in VALID_CLASSIFICATIONS:
            # Treat unknown classifications as not-actionable; skip rather
            # than fail the whole doc.
            continue
        result.append(
            DriftInstance(
                doc_path=doc_path,
                claim=str(item.get("claim") or "").strip()[:500],
                authoritative_source=str(item.get("authoritative_source") or "").strip()[:500],
                classification=classification,
            )
        )
    return result, None


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def build_doc_prompt(
    *,
    repo: str,
    doc_path: str,
    doc_focus: str,
    gitnexus_status: str,
) -> str:
    """Compose the per-doc claude prompt.

    Kept short and explicit. Claude has the repo at cwd and may invoke ``rg``,
    ``gitnexus``, ``git``, etc. directly. Only the JSON output is consumed.
    """
    behavioral_clause = {
        "fresh": (
            "GitNexus map is FRESH for this repo. You MAY call "
            "`gitnexus context <symbol>` or `gitnexus impact <path>` for "
            "behavioral claims about call paths."
        ),
        "stale": (
            "GitNexus map is STALE. SKIP behavioral call-graph checks "
            "gracefully -- rely on `rg` for pattern/identifier existence "
            "checks only. Note skipped checks in your reasoning but do not "
            "fail the doc."
        ),
        "missing": (
            "No GitNexus map present. SKIP behavioral call-graph checks. "
            "Use `rg` for pattern/identifier existence checks only."
        ),
    }[gitnexus_status]
    return f"""You are auditing a source-of-truth operational doc for drift against current implementation.

REPO: {repo}
DOC: {doc_path}
FOCUS: {doc_focus}

{behavioral_clause}

Process:
1. Read the doc at `{doc_path}`.
2. For each load-bearing operational claim (commands, file paths, identifiers, labels, workflow filenames, model identifiers, expected outputs), verify it against the CURRENT implementation in this repo. Use `rg` to confirm strings/identifiers/filenames still exist as cited; cross-reference against the file(s) the claim cites or implies.
3. Classify each verified claim as one of:
   - `stale`: the claim was true once but no longer reflects current implementation (e.g. command renamed, file moved, identifier deprecated).
   - `contradictory`: the claim disagrees with another source-of-truth doc or with current implementation in a way that is actively misleading.
   - `accurate-no-drift`: the claim is verified against current implementation.

Output ONLY a single JSON object on its own line(s), no prose, no markdown fence, with this shape:

{{
  "doc_path": "{doc_path}",
  "instances": [
    {{
      "claim": "<short quote or paraphrase, <=500 chars>",
      "authoritative_source": "<file:line or scripts/foo.py:42 form, <=500 chars>",
      "classification": "stale|contradictory|accurate-no-drift"
    }}
  ]
}}

Include at least one `accurate-no-drift` entry per doc when no drift is found, so the audit trail records the doc was actually scanned. If the doc cannot be located, return an empty `instances` list.
"""


# ---------------------------------------------------------------------------
# Claude invocation (mirrors round2_runner._build_claude_env / invoke_claude)
# ---------------------------------------------------------------------------


def _resolve_claude_binary() -> str | None:
    env_path = os.environ.get("CLAUDE_CODE_EXECPATH")
    if env_path and Path(env_path).is_file():
        return env_path
    bundled_root = Path(os.path.expanduser("~/Library/Application Support/Claude/claude-code"))
    if bundled_root.is_dir():

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
    return shutil.which("claude")


def _read_claude_oauth_token() -> str | None:
    try:
        if not CLAUDE_OAUTH_TOKEN_FILE.is_file():
            return None
        token = CLAUDE_OAUTH_TOKEN_FILE.read_text(encoding="utf-8").strip()
        return token or None
    except OSError:
        return None


def _build_claude_env() -> dict[str, str]:
    keep = ("HOME", "PATH", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "TERM", "SHELL", "TZ")
    env = {k: v for k, v in os.environ.items() if k in keep}
    token = _read_claude_oauth_token()
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    return env


def invoke_claude_for_doc(
    *,
    prompt: str,
    cwd: Path,
    timeout: int,
    log_file: Path,
) -> tuple[bool, str]:
    """Run claude against the repo at ``cwd`` with the given prompt.

    Returns ``(ok, output_or_error)``. ``output_or_error`` is the stdout text
    on success (which the parser then extracts JSON from), or a short error
    description on failure.
    """
    binary = _resolve_claude_binary()
    if binary is None:
        return False, "claude CLI not found"
    cmd = [
        binary,
        "-p",
        "--permission-mode",
        "bypassPermissions",
        "--no-session-persistence",
    ]
    env = _build_claude_env()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        log_file.write_text(f"TIMEOUT after {timeout}s\n", encoding="utf-8")
        return False, f"claude timed out after {timeout}s"
    log_file.write_text(
        f"=== stdout ===\n{result.stdout}\n=== stderr ===\n{result.stderr}\n",
        encoding="utf-8",
    )
    if result.returncode != 0:
        return False, f"claude exited rc={result.returncode}: {result.stderr.strip()[:200]}"
    return True, result.stdout


# ---------------------------------------------------------------------------
# Scanner core (the dependency-injected invoker is what tests pin)
# ---------------------------------------------------------------------------


ClaudeInvoker = Callable[..., tuple[bool, str]]


def scan_doc(
    *,
    repo: str,
    doc_path: str,
    doc_focus: str,
    repo_root: Path,
    log_dir: Path,
    timeout: int,
    invoker: ClaudeInvoker,
) -> DocResult:
    """Scan one (repo, doc) pair and return a DocResult.

    Bounded: any failure is captured on the result; the caller continues.
    """
    gitnexus = is_gitnexus_stale(repo_root)
    result = DocResult(repo=repo, doc_path=doc_path, gitnexus_status=gitnexus)
    if not (repo_root / doc_path).is_file():
        result.error = f"doc not found at {doc_path}"
        return result
    prompt = build_doc_prompt(
        repo=repo,
        doc_path=doc_path,
        doc_focus=doc_focus,
        gitnexus_status=gitnexus,
    )
    safe_doc = doc_path.replace("/", "__")
    log_file = log_dir / f"docs-drift-scan.{repo.replace('/', '__')}.{safe_doc}.log"
    ok, output = invoker(prompt=prompt, cwd=repo_root, timeout=timeout, log_file=log_file)
    if not ok:
        result.error = output
        return result
    instances, parse_err = parse_drift_response(output, doc_path=doc_path)
    if parse_err and not instances:
        result.error = parse_err
        return result
    result.instances = instances
    return result


def dry_run_invoker(*, prompt: str, cwd: Path, timeout: int, log_file: Path) -> tuple[bool, str]:
    """Stand-in invoker used for ``--dry-run`` / local rehearsal / tests.

    Returns an empty-but-valid JSON payload so the rest of the pipeline runs
    end-to-end without touching the live LLM. Real drift detection requires
    the production invoker; this exists so coordinator integration and
    notify rendering can be exercised offline.
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text("dry-run -- skipped claude invocation\n", encoding="utf-8")
    return True, '{"doc_path": "<dry-run>", "instances": []}'


# ---------------------------------------------------------------------------
# Aggregation -- one drift-block per repo, NOT per doc
# ---------------------------------------------------------------------------


def aggregate(doc_results: list[DocResult]) -> dict[str, Any]:
    """Group results by repo, sort, compute summary counts."""
    by_repo: dict[str, dict[str, Any]] = {}
    for res in doc_results:
        bucket = by_repo.setdefault(
            res.repo,
            {
                "repo": res.repo,
                "docs_scanned": 0,
                "drift_instances": [],
                "accurate_instances": [],
                "errors": [],
                "gitnexus_summary": {},
            },
        )
        bucket["docs_scanned"] += 1
        bucket["gitnexus_summary"][res.gitnexus_status] = (
            bucket["gitnexus_summary"].get(res.gitnexus_status, 0) + 1
        )
        if res.error:
            bucket["errors"].append({"doc_path": res.doc_path, "error": res.error})
            continue
        for inst in res.instances:
            record = asdict(inst)
            if inst.classification in DRIFT_CLASSIFICATIONS:
                bucket["drift_instances"].append(record)
            else:
                bucket["accurate_instances"].append(record)

    # Stable ordering: repos alphabetically; within a repo, drift items by doc_path.
    repos_sorted = sorted(by_repo.values(), key=lambda b: b["repo"])
    for bucket in repos_sorted:
        bucket["drift_instances"].sort(key=lambda i: (i["doc_path"], i["classification"]))
        bucket["accurate_instances"].sort(key=lambda i: i["doc_path"])

    total_drift = sum(len(b["drift_instances"]) for b in repos_sorted)
    total_accurate = sum(len(b["accurate_instances"]) for b in repos_sorted)
    total_errors = sum(len(b["errors"]) for b in repos_sorted)
    return {
        "generated_on": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_docs_scanned": sum(b["docs_scanned"] for b in repos_sorted),
        "total_drift_instances": total_drift,
        "total_accurate_instances": total_accurate,
        "total_errors": total_errors,
        "by_repo": repos_sorted,
    }


# ---------------------------------------------------------------------------
# Top-level scan
# ---------------------------------------------------------------------------


def scan(
    *,
    docs_config: dict[str, dict[str, Any]],
    active_repos: set[str],
    workspace_root: Path,
    repo_subset: set[str] | None,
    log_dir: Path,
    timeout: int,
    invoker: ClaudeInvoker,
) -> dict[str, Any]:
    doc_results: list[DocResult] = []
    for repo, repo_config in docs_config.items():
        if repo not in active_repos:
            continue
        if repo_subset and repo not in repo_subset:
            continue
        local_path = str(repo_config.get("local_path") or "")
        if not local_path:
            doc_results.append(
                DocResult(
                    repo=repo,
                    doc_path="<config>",
                    error=f"docs config for {repo} missing 'local_path'",
                )
            )
            continue
        repo_root = (workspace_root / local_path).resolve()
        if not repo_root.is_dir():
            doc_results.append(
                DocResult(
                    repo=repo,
                    doc_path="<workspace>",
                    error=f"repo root not found at {repo_root}",
                )
            )
            continue
        for index, doc_entry in enumerate(repo_config.get("docs") or []):
            if not isinstance(doc_entry, dict):
                doc_results.append(
                    DocResult(
                        repo=repo,
                        doc_path=f"<config.docs[{index}]>",
                        error=(
                            "docs config entry must be a mapping, "
                            f"got {type(doc_entry).__name__}"
                        ),
                    )
                )
                continue
            doc_path = str(doc_entry.get("path") or "")
            doc_focus = str(doc_entry.get("focus") or "")
            if not doc_path:
                continue
            doc_results.append(
                scan_doc(
                    repo=repo,
                    doc_path=doc_path,
                    doc_focus=doc_focus,
                    repo_root=repo_root,
                    log_dir=log_dir,
                    timeout=timeout,
                    invoker=invoker,
                )
            )
    return aggregate(doc_results)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--docs-config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=None,
        help="parent dir containing each repo's local_path (default: registry parent's parent)",
    )
    parser.add_argument("--repos", nargs="*", default=[])
    parser.add_argument("--timeout", type=int, default=DEFAULT_PER_DOC_TIMEOUT)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="skip claude calls; emit empty drift result per doc (used for "
        "offline rehearsal and unit tests)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        docs_config = load_docs_config(args.docs_config)
    except (FileNotFoundError, yaml.YAMLError, ValueError) as exc:
        print(f"[docs-drift-scan] cannot load docs config: {exc}", file=sys.stderr)
        return 2
    try:
        active = load_active_repos(args.registry)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"[docs-drift-scan] cannot load registry: {exc}", file=sys.stderr)
        return 2

    if args.workspace_root:
        workspace_root = args.workspace_root.resolve()
    else:
        try:
            workspace_root = resolve_workspace_root(args.registry)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            print(f"[docs-drift-scan] cannot resolve workspace root: {exc}", file=sys.stderr)
            return 2
    log_dir = args.out.parent / "logs" / "coordinator"
    log_dir.mkdir(parents=True, exist_ok=True)

    invoker: ClaudeInvoker = dry_run_invoker if args.dry_run else invoke_claude_for_doc
    repo_subset = set(args.repos) if args.repos else None

    result = scan(
        docs_config=docs_config,
        active_repos=active,
        workspace_root=workspace_root,
        repo_subset=repo_subset,
        log_dir=log_dir,
        timeout=args.timeout,
        invoker=invoker,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        f"[docs-drift-scan] scanned {result['total_docs_scanned']} doc(s) across "
        f"{len(result['by_repo'])} repo(s); "
        f"drift={result['total_drift_instances']} "
        f"accurate={result['total_accurate_instances']} "
        f"errors={result['total_errors']} -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
