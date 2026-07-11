#!/usr/bin/env python3
"""Check consumer repos for drift against manifest-defined templates."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path

import requests

try:
    from sync_manifest_compiler import (
        COPY_SYNCED_SECTIONS,
        CompiledManifest,
        ManifestCompileError,
        ManifestEntry,
        compile_manifest,
        resolve_source_path,
    )
except ImportError:
    from scripts.sync_manifest_compiler import (  # type: ignore[no-redef]
        COPY_SYNCED_SECTIONS,
        CompiledManifest,
        ManifestCompileError,
        ManifestEntry,
        compile_manifest,
        resolve_source_path,
    )

REPORT_SCHEMA = "workflows-consumer-sync-drift/v1"
SUMMARY_ITEM_LIMIT = 50
CONTENT_ERROR_THRESHOLD = 5
SYNC_BRANCH_PREFIX = "sync/workflows-"
TOKEN_ENV_ORDER = (
    "DRIFT_TOKEN",
    "SERVICE_BOT_PAT",
    "OWNER_PR_PAT",
    "ACTIONS_BOT_PAT",
    "AGENTS_AUTOMATION_PAT",
    "GITHUB_TOKEN",
    "GH_TOKEN",
)
TOKEN_PROBE_REPO_LIMIT = 3
TOKEN_PROBE_PATH_LIMIT = 16


def join_remote_path(base: str, *parts: object) -> str:
    """Join manifest target fragments without creating API paths with doubled slashes."""
    fragments = [str(base).strip("/")]
    fragments.extend(str(part).strip("/") for part in parts if str(part))
    return "/".join(fragment for fragment in fragments if fragment)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check consumer repos for drift against Workflows templates and manifest entries."
    )
    parser.add_argument(
        "--repos",
        help="Comma-separated list of repos to check (owner/name).",
    )
    parser.add_argument(
        "--manifest",
        default=".github/sync-manifest.yml",
        help="Path to sync manifest.",
    )
    parser.add_argument(
        "--summary",
        default=os.environ.get("GITHUB_STEP_SUMMARY", ""),
        help="Optional path to write a summary markdown.",
    )
    parser.add_argument(
        "--report-json",
        default=os.environ.get("CONSUMER_SYNC_DRIFT_REPORT_JSON", ""),
        help="Optional path to write a machine-readable drift report.",
    )
    return parser.parse_args()


def resolve_repos(raw: str | None) -> list[str]:
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    env_repos = os.environ.get("REGISTERED_CONSUMER_REPOS", "")
    repos = [item.strip() for item in env_repos.splitlines() if item.strip()]
    return repos


def local_path_for(source: str, section: str | None = None) -> Path | None:
    """Compatibility wrapper around the compiler's canonical resolver."""
    return resolve_source_path(source, section, repo_root=Path("."))


def git_blob_hash(content: bytes) -> str:
    """Return the Git object SHA for file content without fetching the remote blob."""
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content).hexdigest()


def comparable_lines(text: str) -> list[str]:
    """Lines after leading comment/blank header lines, matching maint-68's
    `comparable_lines`. The syncer compares files header-insensitively, so a
    difference only in leading blank/`#` lines is something it never rewrites.
    EOL-insensitive via splitlines()."""
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped == "" or stripped.startswith("#"):
            index += 1
            continue
        break
    return lines[index:]


def remote_blob_text(session: requests.Session, repo: str, sha: str) -> str | None:
    """Fetch a remote blob's UTF-8 text by SHA, or None if it can't be fetched or
    decoded (e.g. binary, API error) -- caller falls back to the raw-bytes verdict."""
    try:
        response = session.get(f"https://api.github.com/repos/{repo}/git/blobs/{sha}")
        if response.status_code != 200:
            return None
        data = response.json()
        if data.get("encoding") != "base64":
            return None
        return base64.b64decode(data.get("content", "")).decode("utf-8")
    except (ValueError, UnicodeDecodeError, requests.RequestException):
        return None


def sorted_items(values: set[str]) -> list[str]:
    return sorted(values)


def manifest_skip_reason(entry: ManifestEntry, repo: str) -> str:
    """Return the manifest-declared skip reason for a repo, if any."""
    for skip in entry.skip_repos:
        if skip.repo == repo:
            return skip.reason or "Manifest skip for repo"
    return ""


def repo_overwrites_create_only(entry: ManifestEntry, repo: str) -> bool:
    """Return whether repo should be drift-checked for create_only entries."""
    return repo in entry.overwrite_repos


def token_candidates(env: dict[str, str] | None = None) -> list[dict[str, str]]:
    """Return deduplicated token candidates without exposing token values."""
    values = env if env is not None else os.environ
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    for source in TOKEN_ENV_ORDER:
        token = str(values.get(source, "")).strip()
        if not token or token in seen:
            continue
        seen.add(token)
        candidates.append({"source": source, "token": token})
    return candidates


def response_message(response: object) -> str:
    try:
        payload = response.json()  # type: ignore[attr-defined]
    except Exception:
        return ""
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str):
            return message
    return ""


def response_failure_reason(response: object) -> str:
    status_code = getattr(response, "status_code", "unknown")
    headers = getattr(response, "headers", {}) or {}
    remaining = str(headers.get("x-ratelimit-remaining", ""))
    message = response_message(response)
    if str(status_code) == "403" and remaining == "0":
        return "rate_limited"
    if message:
        return f"HTTP {status_code}: {message}"
    return f"HTTP {status_code}"


def session_for_token(token: str, session_factory=requests.Session) -> requests.Session:
    session = session_factory()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
    )
    return session


def probe_targets(compiled: CompiledManifest, sections: list[str]) -> list[str]:
    targets: list[str] = []
    for section in sections:
        section_target = ""
        for entry in compiled.section(section):
            if entry.sync_mode == "create_only":
                continue
            local_path = Path(entry.resolved_source)
            if not local_path.exists():
                continue
            if entry.is_directory or local_path.is_dir():
                first_child = next(
                    (child for child in sorted(local_path.rglob("*")) if child.is_file()), None
                )
                if first_child:
                    section_target = join_remote_path(
                        entry.target, first_child.relative_to(local_path)
                    )
            else:
                section_target = entry.target
            if section_target:
                targets.append(section_target)
                break
        if len(targets) >= TOKEN_PROBE_PATH_LIMIT:
            return targets
    return targets


def select_read_token(
    *,
    candidates: list[dict[str, str]],
    repos: list[str],
    paths: list[str],
    session_factory=requests.Session,
) -> tuple[requests.Session | None, dict[str, object]]:
    """Select a token that can read consumer repo contents, with safe diagnostics."""
    diagnostics: dict[str, object] = {
        "schema": "workflows-drift-token-selection/v1",
        "attempted_sources": [candidate["source"] for candidate in candidates],
        "selected_source": "",
        "rejected": [],
        "probe_repos": repos[:TOKEN_PROBE_REPO_LIMIT],
        "probe_paths": paths[:TOKEN_PROBE_PATH_LIMIT],
    }
    rejected = diagnostics["rejected"]
    assert isinstance(rejected, list)

    if not candidates:
        diagnostics["error"] = "no_token_candidates"
        return None, diagnostics
    if not repos:
        diagnostics["error"] = "no_repos_to_probe"
        return None, diagnostics

    probe_paths = paths[:TOKEN_PROBE_PATH_LIMIT] or [""]
    for candidate in candidates:
        source = candidate["source"]
        session = session_for_token(candidate["token"], session_factory=session_factory)
        first_failure = ""
        for repo in repos[:TOKEN_PROBE_REPO_LIMIT]:
            repo_response = session.get(f"https://api.github.com/repos/{repo}")
            if repo_response.status_code >= 400:
                first_failure = (
                    first_failure
                    or f"repo preflight failed for {repo}: {response_failure_reason(repo_response)}"
                )
                continue
            for path in probe_paths:
                if not path:
                    diagnostics["selected_source"] = source
                    return session, diagnostics
                content_response = session.get(
                    f"https://api.github.com/repos/{repo}/contents/{path}"
                )
                if content_response.status_code in {200, 404}:
                    diagnostics["selected_source"] = source
                    diagnostics["probe_repo"] = repo
                    diagnostics["probe_path"] = path
                    return session, diagnostics
                first_failure = (
                    first_failure
                    or f"content preflight failed for {repo}/{path}: "
                    f"{response_failure_reason(content_response)}"
                )
        rejected.append({"source": source, "reason": first_failure or "no readable probe target"})

    diagnostics["error"] = "no_usable_token"
    return None, diagnostics


def split_report_item(item: str) -> tuple[str, str]:
    repo, separator, detail = item.partition(": ")
    if not separator:
        return "", item
    return repo, detail


def path_prefix(detail: str) -> str:
    path = detail.split(" (", 1)[0].strip()
    parts = [part for part in path.split("/") if part]
    if not parts:
        return "unknown"
    if parts[0] == ".github" and len(parts) > 1:
        return "/".join(parts[:2])
    if len(parts) > 1 and parts[0] in {"scripts", "tools", "docs", "templates"}:
        return "/".join(parts[:2])
    return parts[0]


def build_repo_summaries(
    *,
    repos: list[str],
    drift: set[str],
    missing: set[str],
    errors: set[str],
    obsolete: set[str],
) -> dict[str, dict[str, int]]:
    summaries = {
        repo: {"drift": 0, "missing": 0, "errors": 0, "obsolete": 0} for repo in sorted(repos)
    }
    for category, items in (
        ("drift", drift),
        ("missing", missing),
        ("errors", errors),
        ("obsolete", obsolete),
    ):
        for item in items:
            repo, _detail = split_report_item(item)
            if not repo:
                continue
            summaries.setdefault(repo, {"drift": 0, "missing": 0, "errors": 0, "obsolete": 0})
            summaries[repo][category] += 1
    return summaries


def build_prefix_counts(items: set[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        _repo, detail = split_report_item(item)
        prefix = path_prefix(detail)
        counts[prefix] = counts.get(prefix, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def build_top_repo_gaps(
    repo_summaries: dict[str, dict[str, int]], limit: int = 10
) -> list[dict[str, object]]:
    gaps: list[dict[str, object]] = []
    for repo, counts in repo_summaries.items():
        total = sum(
            int(counts.get(category, 0)) for category in ("drift", "missing", "errors", "obsolete")
        )
        if total <= 0:
            continue
        gaps.append({"repo": repo, "total": total, **counts})
    return sorted(gaps, key=lambda item: (-int(item["total"]), str(item["repo"])))[:limit]


def fetch_open_sync_prs(
    session: requests.Session, repo: str
) -> tuple[list[dict[str, object]], str | None]:
    """Return open Workflows sync PRs for a consumer repo, or a non-fatal lookup error."""
    response = session.get(f"https://api.github.com/repos/{repo}/pulls?state=open&per_page=50")
    if response.status_code >= 400:
        return [], f"{repo}: sync PR lookup failed ({response_failure_reason(response)})"

    prs: list[dict[str, object]] = []
    for item in response.json() or []:
        if not isinstance(item, dict):
            continue
        head = item.get("head") if isinstance(item.get("head"), dict) else {}
        branch = str(head.get("ref", "")).strip()
        if not branch.startswith(SYNC_BRANCH_PREFIX):
            continue
        prs.append(
            {
                "repo": repo,
                "number": item.get("number"),
                "title": item.get("title", ""),
                "url": item.get("html_url", ""),
                "branch": branch,
                "head_sha": head.get("sha", ""),
                "created_at": item.get("created_at", ""),
                "updated_at": item.get("updated_at", ""),
            }
        )
    prs.sort(
        key=lambda item: (
            str(item.get("repo", "")),
            str(item.get("created_at", "")),
            int(item.get("number") or 0),
        ),
        reverse=True,
    )
    return prs, None


def record_content_error(
    *,
    errors: set[str],
    repo_error_counts: dict[str, int],
    skipped_repos: set[str],
    repo: str,
    target: str,
    status_code: int,
    threshold: int = CONTENT_ERROR_THRESHOLD,
) -> None:
    if repo in skipped_repos:
        return
    repo_error_counts[repo] = repo_error_counts.get(repo, 0) + 1
    if repo_error_counts[repo] >= threshold:
        errors.add(
            f"{repo}: content comparison skipped after {threshold} HTTP errors; "
            f"last path {target} (HTTP {status_code})"
        )
        skipped_repos.add(repo)
        return
    errors.add(f"{repo}: {target} (HTTP {status_code})")


def build_report(
    *,
    repos: list[str],
    drift: set[str],
    missing: set[str],
    errors: set[str],
    obsolete: set[str],
    skipped: set[str] | None = None,
    open_sync_prs: list[dict[str, object]] | None = None,
    sync_pr_lookup_errors: list[str] | None = None,
    token_diagnostics: dict[str, object] | None = None,
) -> dict[str, object]:
    skipped = skipped or set()
    open_sync_prs = open_sync_prs or []
    sync_pr_lookup_errors = sync_pr_lookup_errors or []
    counts = {
        "drift": len(drift),
        "missing": len(missing),
        "errors": len(errors),
        "obsolete": len(obsolete),
    }
    status = "pass" if all(value == 0 for value in counts.values()) else "drift"
    repo_summaries = build_repo_summaries(
        repos=repos,
        drift=drift,
        missing=missing,
        errors=errors,
        obsolete=obsolete,
    )
    top_repo_gaps = build_top_repo_gaps(repo_summaries)
    targeted_repos = [str(item["repo"]) for item in top_repo_gaps]
    open_sync_repo_count = len({str(item.get("repo", "")) for item in open_sync_prs if item})
    latest_open_sync_pr = open_sync_prs[0] if open_sync_prs else None
    remediation_state = "pass"
    if status != "pass":
        remediation_state = "pending_sync_prs" if open_sync_prs else "needs_sync"
    report: dict[str, object] = {
        "schema": REPORT_SCHEMA,
        "status": status,
        "repo_count": len(repos),
        "repos": repos,
        "counts": counts,
        "repo_summaries": repo_summaries,
        "repo_summary_count": len(repo_summaries),
        "top_repo_gaps": top_repo_gaps,
        "path_prefix_counts": {
            "drift": build_prefix_counts(drift),
            "missing": build_prefix_counts(missing),
            "errors": build_prefix_counts(errors),
            "obsolete": build_prefix_counts(obsolete),
        },
        "follow_up": {
            "workflow": "maint-68-sync-consumer-repos.yml",
            "all_repos_command": (
                "gh workflow run maint-68-sync-consumer-repos.yml "
                "--repo stranske/Workflows --ref main"
            ),
            "targeted_repos_command": (
                "gh workflow run maint-68-sync-consumer-repos.yml "
                f"--repo stranske/Workflows --ref main -f repos={','.join(targeted_repos)}"
                if targeted_repos
                else ""
            ),
        },
        "summary_limits": {
            "content_error_threshold_per_repo": CONTENT_ERROR_THRESHOLD,
            "max_items_per_section": SUMMARY_ITEM_LIMIT,
        },
        "sync_remediation": {
            "state": remediation_state,
            "open_pr_count": len(open_sync_prs),
            "repo_count": open_sync_repo_count,
            "latest_open_pr": latest_open_sync_pr,
            "stale_open_pr_count": max(0, len(open_sync_prs) - open_sync_repo_count),
            "open_prs": open_sync_prs,
            "lookup_errors": sync_pr_lookup_errors,
        },
        "skip_count": len(skipped),
        "skipped": sorted_items(skipped),
        "drift": sorted_items(drift),
        "missing": sorted_items(missing),
        "errors": sorted_items(errors),
        "obsolete": sorted_items(obsolete),
    }
    if token_diagnostics:
        report["token_diagnostics"] = token_diagnostics
    return report


def write_summary_markdown(path: str, report: dict[str, object]) -> None:
    if not path:
        return
    summary_path = Path(path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    counts = report.get("counts", {})
    repos = report.get("repos", [])
    with summary_path.open("a", encoding="utf-8") as handle:
        handle.write("## Consumer Sync Drift Check\n")
        handle.write(f"Checked repos: {', '.join(str(repo) for repo in repos)}\n\n")
        handle.write("### Counts\n")
        for category in ("drift", "missing", "errors", "obsolete"):
            handle.write(f"- {category}: {counts.get(category, 0)}\n")
        handle.write("\n")

        repo_summaries = report.get("repo_summaries", {})
        if isinstance(repo_summaries, dict) and repo_summaries:
            handle.write("### Repo summary\n")
            for repo, repo_counts in repo_summaries.items():
                if not isinstance(repo_counts, dict):
                    continue
                total = sum(int(repo_counts.get(category, 0)) for category in counts)
                if total <= 0:
                    continue
                details = ", ".join(
                    f"{category}={repo_counts.get(category, 0)}" for category in counts
                )
                handle.write(f"- {repo}: {details}\n")
            handle.write("\n")

        top_repo_gaps = report.get("top_repo_gaps", [])
        if isinstance(top_repo_gaps, list) and top_repo_gaps:
            handle.write("### Highest-impact repos\n")
            for item in top_repo_gaps[:10]:
                if not isinstance(item, dict):
                    continue
                handle.write(
                    "- {repo}: total={total}, drift={drift}, missing={missing}, "
                    "errors={errors}, obsolete={obsolete}\n".format(
                        repo=item.get("repo", "unknown"),
                        total=item.get("total", 0),
                        drift=item.get("drift", 0),
                        missing=item.get("missing", 0),
                        errors=item.get("errors", 0),
                        obsolete=item.get("obsolete", 0),
                    )
                )
            handle.write("\n")

        path_prefix_counts = report.get("path_prefix_counts", {})
        if isinstance(path_prefix_counts, dict) and path_prefix_counts:
            handle.write("### Path prefixes\n")
            for category, prefixes in path_prefix_counts.items():
                if not isinstance(prefixes, dict) or not prefixes:
                    continue
                rendered = ", ".join(f"{prefix}={count}" for prefix, count in prefixes.items())
                handle.write(f"- {category}: {rendered}\n")
            handle.write("\n")

        follow_up = report.get("follow_up", {})
        if isinstance(follow_up, dict):
            all_repos_command = str(follow_up.get("all_repos_command", "")).strip()
            targeted_repos_command = str(follow_up.get("targeted_repos_command", "")).strip()
            if all_repos_command or targeted_repos_command:
                handle.write("### Follow-up commands\n")
                if all_repos_command:
                    handle.write(f"- All repos: `{all_repos_command}`\n")
                if targeted_repos_command:
                    handle.write(f"- Top repos: `{targeted_repos_command}`\n")
                handle.write("\n")

        sync_remediation = report.get("sync_remediation", {})
        if isinstance(sync_remediation, dict):
            open_prs = sync_remediation.get("open_prs", [])
            if isinstance(open_prs, list) and open_prs:
                open_pr_limit = 10
                handle.write("### Open sync PRs\n")
                for item in open_prs[:open_pr_limit]:
                    if not isinstance(item, dict):
                        continue
                    repo = item.get("repo", "unknown")
                    number = item.get("number", "")
                    branch = item.get("branch", "")
                    url = item.get("url", "")
                    handle.write(f"- {repo}#{number}: `{branch}` {url}\n")
                remaining = len(open_prs) - open_pr_limit
                if remaining > 0:
                    handle.write(f"- ... {remaining} more in consumer-sync-drift-report.json\n")
                handle.write("\n")

        for title, key in (
            ("Drift detected for", "drift"),
            ("Missing files", "missing"),
            ("Errors", "errors"),
            ("Obsolete files present (should be removed)", "obsolete"),
            ("Skipped by manifest policy", "skipped"),
        ):
            items = report.get(key, [])
            if not isinstance(items, list) or not items:
                if key == "drift":
                    handle.write("✅ No drift detected.\n\n")
                continue
            handle.write(f"### {title}\n")
            for item in items[:SUMMARY_ITEM_LIMIT]:
                handle.write(f"- {item}\n")
            remaining = len(items) - SUMMARY_ITEM_LIMIT
            if remaining > 0:
                handle.write(f"- ... {remaining} more in consumer-sync-drift-report.json\n")
            handle.write("\n")


def write_report_json(path: str, report: dict[str, object]) -> None:
    if not path:
        return
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def repo_access_error(session: requests.Session, repo: str) -> str | None:
    """Return a concise access error for an unreadable repo, or None when readable."""
    url = f"https://api.github.com/repos/{repo}"
    response = session.get(url)
    if response.status_code < 400:
        return None
    return f"{repo}: repository access preflight failed (HTTP {response.status_code})"


def fetch_remote_tree(
    session: requests.Session, repo: str
) -> tuple[dict[str, dict[str, object]] | None, str | None]:
    """Fetch a repo's default-branch tree once so file comparisons are cheap."""
    repo_response = session.get(f"https://api.github.com/repos/{repo}")
    if repo_response.status_code >= 400:
        return (
            None,
            f"{repo}: repository access preflight failed ({response_failure_reason(repo_response)})",
        )

    repo_data = repo_response.json()
    default_branch = str(repo_data.get("default_branch") or "main")
    tree_response = session.get(
        f"https://api.github.com/repos/{repo}/git/trees/{default_branch}?recursive=1"
    )
    if tree_response.status_code >= 400:
        return (
            None,
            f"{repo}: repository tree fetch failed ({response_failure_reason(tree_response)})",
        )

    tree_data = tree_response.json()
    if tree_data.get("truncated"):
        return None, f"{repo}: repository tree fetch was truncated"

    entries: dict[str, dict[str, object]] = {}
    for item in tree_data.get("tree", []) or []:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if isinstance(path, str) and path:
            entries[path] = item
    return entries, None


def main() -> int:
    args = parse_args()
    repos = resolve_repos(args.repos)
    if not repos:
        print("::error::No repos provided or found in REGISTERED_CONSUMER_REPOS")
        write_report_json(
            args.report_json,
            build_report(
                repos=[],
                drift=set(),
                missing=set(),
                errors={"No repos provided or found in REGISTERED_CONSUMER_REPOS"},
                obsolete=set(),
            ),
        )
        return 1

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print("::error::sync-manifest.yml not found")
        write_report_json(
            args.report_json,
            build_report(
                repos=repos,
                drift=set(),
                missing=set(),
                errors={"sync-manifest.yml not found"},
                obsolete=set(),
            ),
        )
        return 1

    candidates = token_candidates()
    if not candidates:
        print("::error::No GitHub token available for cross-repo reads")
        write_report_json(
            args.report_json,
            build_report(
                repos=repos,
                drift=set(),
                missing=set(),
                errors={"No GitHub token available for cross-repo reads"},
                obsolete=set(),
                token_diagnostics={
                    "schema": "workflows-drift-token-selection/v1",
                    "error": "no_token_candidates",
                },
            ),
        )
        return 1

    try:
        compiled = compile_manifest(manifest_path)
    except ManifestCompileError as exc:
        print(f"::error::Manifest is invalid — refusing to run drift check:\n{exc}")
        write_report_json(
            args.report_json,
            build_report(
                repos=repos,
                drift=set(),
                missing=set(),
                errors={f"Invalid manifest: {exc.problems[0]}"},
                obsolete=set(),
            ),
        )
        return 1

    sections = list(COPY_SYNCED_SECTIONS)

    session, token_diagnostics = select_read_token(
        candidates=candidates,
        repos=repos,
        paths=probe_targets(compiled, sections),
    )
    if session is None:
        print("::error::No usable GitHub token available for consumer repo contents reads")
        write_report_json(
            args.report_json,
            build_report(
                repos=repos,
                drift=set(),
                missing=set(),
                errors={"No usable GitHub token available for consumer repo contents reads"},
                obsolete=set(),
                token_diagnostics=token_diagnostics,
            ),
        )
        return 1

    drift: set[str] = set()
    missing: set[str] = set()
    errors: set[str] = set()
    obsolete: set[str] = set()
    skipped: set[str] = set()

    remote_trees: dict[str, dict[str, dict[str, object]]] = {}
    open_sync_prs: list[dict[str, object]] = []
    sync_pr_lookup_errors: list[str] = []
    for repo in repos:
        remote_tree, tree_error = fetch_remote_tree(session, repo)
        if tree_error:
            errors.add(tree_error)
        else:
            remote_trees[repo] = remote_tree or {}
        repo_sync_prs, sync_pr_error = fetch_open_sync_prs(session, repo)
        open_sync_prs.extend(repo_sync_prs)
        if sync_pr_error:
            sync_pr_lookup_errors.append(sync_pr_error)

    def _check_file(local_file: Path, remote_target: str, repo: str) -> None:
        """Compare a single local file against its remote counterpart."""
        remote_entry = remote_trees.get(repo, {}).get(remote_target)
        if remote_entry is None:
            missing.add(f"{repo}: {remote_target}")
            return
        if remote_entry.get("type") != "blob" or not remote_entry.get("sha"):
            errors.add(f"{repo}: {remote_target} (unexpected remote tree entry)")
            return
        local_bytes = local_file.read_bytes()
        if str(remote_entry["sha"]) == git_blob_hash(local_bytes):
            return
        # Raw bytes differ -- but maint-68 syncs using a header-insensitive comparison
        # (comparable_lines), so a difference only in leading comment/blank headers is
        # something the syncer will NEVER rewrite; reporting it as drift would be an
        # eternal false positive (review E1). Confirm real drift the same way before
        # flagging. On any fetch/decode failure, fall back to the raw-bytes verdict.
        remote_text = remote_blob_text(session, repo, str(remote_entry["sha"]))
        try:
            local_text = local_bytes.decode("utf-8")
        except UnicodeDecodeError:
            local_text = None
        if remote_text is None or local_text is None:
            drift.add(f"{repo}: {remote_target}")
            return
        if comparable_lines(local_text) != comparable_lines(remote_text):
            drift.add(f"{repo}: {remote_target}")

    for section in sections:
        for entry in compiled.section(section):
            local_path = Path(entry.resolved_source)
            if not local_path.exists():
                errors.add(f"{section}: missing local file for {entry.source}")
                continue

            for repo in remote_trees:
                if entry.sync_mode == "create_only" and not repo_overwrites_create_only(
                    entry, repo
                ):
                    continue
                skip_reason = manifest_skip_reason(entry, repo)
                if skip_reason:
                    skipped.add(f"{repo}: {entry.target} ({skip_reason})")
                    continue
                if entry.is_directory or local_path.is_dir():
                    # Recursively compare all files within the directory
                    for child in sorted(local_path.rglob("*")):
                        if child.is_file():
                            rel = child.relative_to(local_path)
                            remote_target = join_remote_path(entry.target, rel)
                            _check_file(child, remote_target, repo)
                else:
                    _check_file(local_path, entry.target, repo)

    for removal in compiled.removals:
        for repo, remote_tree in remote_trees.items():
            if removal.target in remote_tree:
                obsolete.add(f"{repo}: {removal.target}")

    report = build_report(
        repos=repos,
        drift=drift,
        missing=missing,
        errors=errors,
        obsolete=obsolete,
        skipped=skipped,
        open_sync_prs=open_sync_prs,
        sync_pr_lookup_errors=sync_pr_lookup_errors,
        token_diagnostics=token_diagnostics,
    )
    write_report_json(args.report_json, report)
    write_summary_markdown(args.summary, report)

    if report["status"] != "pass":
        print("::warning::Consumer repo drift detected")
        return 1

    print("Consumer repos are in sync.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
