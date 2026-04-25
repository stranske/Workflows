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
import yaml

REPORT_SCHEMA = "workflows-consumer-sync-drift/v1"
SUMMARY_ITEM_LIMIT = 50
CONTENT_ERROR_THRESHOLD = 5


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


def local_path_for(source: str) -> Path | None:
    template_candidate = Path("templates/consumer-repo") / source
    if template_candidate.exists():
        return template_candidate
    root_candidate = Path(source)
    if root_candidate.exists():
        return root_candidate
    return None


def file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sorted_items(values: set[str]) -> list[str]:
    return sorted(values)


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
) -> dict[str, object]:
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
    return {
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
        "drift": sorted_items(drift),
        "missing": sorted_items(missing),
        "errors": sorted_items(errors),
        "obsolete": sorted_items(obsolete),
    }


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

        for title, key in (
            ("Drift detected for", "drift"),
            ("Missing files", "missing"),
            ("Errors", "errors"),
            ("Obsolete files present (should be removed)", "obsolete"),
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

    token = os.environ.get("DRIFT_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("::error::No GitHub token available for cross-repo reads")
        write_report_json(
            args.report_json,
            build_report(
                repos=repos,
                drift=set(),
                missing=set(),
                errors={"No GitHub token available for cross-repo reads"},
                obsolete=set(),
            ),
        )
        return 1

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    sections = [
        "workflows",
        "prompts",
        "scripts",
        "codex_config",
        "docs",
        "copilot_config",
        "templates",
        "actions",
        "llm_config",
        "git_config",
        "issue_templates",
        "user_docs",
    ]

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
    )

    drift: set[str] = set()
    missing: set[str] = set()
    errors: set[str] = set()
    obsolete: set[str] = set()

    accessible_repos: list[str] = []
    for repo in repos:
        access_error = repo_access_error(session, repo)
        if access_error:
            errors.add(access_error)
        else:
            accessible_repos.append(repo)

    repo_content_error_counts: dict[str, int] = {}
    skipped_content_repos: set[str] = set()

    def _check_file(local_file: Path, remote_target: str, repo: str) -> None:
        """Compare a single local file against its remote counterpart."""
        if repo in skipped_content_repos:
            return
        local_digest = file_hash(local_file.read_bytes())
        url = f"https://api.github.com/repos/{repo}/contents/{remote_target}"
        response = session.get(url)
        if response.status_code == 404:
            missing.add(f"{repo}: {remote_target}")
            return
        if response.status_code >= 400:
            record_content_error(
                errors=errors,
                repo_error_counts=repo_content_error_counts,
                skipped_repos=skipped_content_repos,
                repo=repo,
                target=remote_target,
                status_code=response.status_code,
            )
            return
        data = response.json()
        if data.get("encoding") != "base64" or "content" not in data:
            errors.add(f"{repo}: {remote_target} (unexpected content encoding)")
            return
        remote_content = base64.b64decode(data["content"])
        if file_hash(remote_content) != local_digest:
            drift.add(f"{repo}: {remote_target}")

    for section in sections:
        for entry in manifest.get(section, []) or []:
            source = entry.get("source")
            if not source:
                continue
            if entry.get("sync_mode") == "create_only":
                continue
            target = entry.get("target", source)
            is_directory = entry.get("is_directory", False)
            local_path = local_path_for(source)
            if not local_path:
                errors.add(f"{section}: missing local file for {source}")
                continue

            for repo in accessible_repos:
                if repo in skipped_content_repos:
                    continue
                if is_directory or local_path.is_dir():
                    # Recursively compare all files within the directory
                    for child in sorted(local_path.rglob("*")):
                        if child.is_file():
                            rel = child.relative_to(local_path)
                            remote_target = join_remote_path(target, rel)
                            _check_file(child, remote_target, repo)
                else:
                    _check_file(local_path, target, repo)

    for entry in manifest.get("removals", []) or []:
        target = entry.get("target")
        if not target:
            continue
        for repo in accessible_repos:
            if repo in skipped_content_repos:
                continue
            url = f"https://api.github.com/repos/{repo}/contents/{target}"
            response = session.get(url)
            if response.status_code == 404:
                continue
            if response.status_code >= 400:
                record_content_error(
                    errors=errors,
                    repo_error_counts=repo_content_error_counts,
                    skipped_repos=skipped_content_repos,
                    repo=repo,
                    target=target,
                    status_code=response.status_code,
                )
                continue
            obsolete.add(f"{repo}: {target}")

    report = build_report(
        repos=repos,
        drift=drift,
        missing=missing,
        errors=errors,
        obsolete=obsolete,
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
