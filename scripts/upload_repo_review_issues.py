#!/usr/bin/env python3
"""Create GitHub issues from the approved weekly repo-review queue.

The script is intentionally explicit: dry-run is the default, and `--apply`
is required before it writes to GitHub. Creation is idempotent: each created
issue carries a stable per-item marker (`<!-- repo-review-item: <repo>#<hash> -->`)
and dedup consults open AND recently-closed issues by that marker, then by exact
title, then by token-Jaccard similarity — so re-running `--apply` after items
were materialized-and-closed does not recreate them (#2272).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from scripts.repo_review_issue_quality import (
        issue_body_quality_errors,
        review_evidence_trace_errors,
    )
except ModuleNotFoundError:  # pragma: no cover - supports direct script execution.
    from repo_review_issue_quality import (  # type: ignore[no-redef]
        issue_body_quality_errors,
        review_evidence_trace_errors,
    )

LABELS = {
    "repo-review-approved": {
        "color": "5319e7",
        "description": "Approved by weekly design-vs-implementation repo review",
    },
    "repo-review-meta-audit": {
        "color": "8957a0",
        "description": "Audit-scope candidate from weekly repo review (produce a report + follow-ups, not a single fix)",
    },
    "priority:high": {
        "color": "b60205",
        "description": "High-priority weekly repo-review work",
    },
    "priority:normal": {
        "color": "fbca04",
        "description": "Normal-priority weekly repo-review work",
    },
    "priority:low": {
        "color": "0e8a16",
        "description": "Low-priority weekly repo-review work",
    },
}
ORCHESTRATOR_MIRROR = Path.home() / ".codex" / "orchestrator-mirror"

SEMANTIC_DUPLICATE_LABEL = "repo-review-approved"
SEMANTIC_DUPLICATE_THRESHOLD = 0.20
SEMANTIC_DUPLICATE_MARGIN = 0.08
SEMANTIC_DUPLICATE_STOPWORDS = {
    "acceptance",
    "add",
    "after",
    "and",
    "are",
    "before",
    "behavior",
    "code",
    "complete",
    "coverage",
    "criteria",
    "current",
    "database",
    "design",
    "docs",
    "documentation",
    "document",
    "existing",
    "file",
    "files",
    "finish",
    "fix",
    "for",
    "from",
    "goals",
    "implementation",
    "implement",
    "into",
    "issue",
    "issues",
    "local",
    "manager",
    "mode",
    "non",
    "notes",
    "path",
    "paths",
    "readiness",
    "relevant",
    "repo",
    "review",
    "reviewed",
    "scope",
    "should",
    "tasks",
    "test",
    "tests",
    "than",
    "that",
    "the",
    "this",
    "use",
    "using",
    "why",
    "with",
    "without",
}


def run_command(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, capture_output=True, text=True)


def run_command_with_retry(
    args: list[str], *, attempts: int = 2, label: str = ""
) -> subprocess.CompletedProcess[str]:
    """Run `gh` with one retry on non-zero exit. The pilot upload hit two
    transient subprocess failures (one on `gh issue list` for a repo with
    1000+ issues, one on `gh issue create`) that succeeded on retry. We
    don't want the entire weekly upload to crash on a one-off network or
    rate-limit blip — retry once, then surface the failure if it persists.
    """
    last_result: subprocess.CompletedProcess[str] | None = None
    for attempt in range(1, attempts + 1):
        result = subprocess.run(args, check=False, capture_output=True, text=True)
        if result.returncode == 0:
            return result
        last_result = result
        if attempt < attempts:
            print(
                f"[upload] {label or args[1] if len(args) > 1 else 'gh'} attempt {attempt}/{attempts} "
                f"failed (rc={result.returncode}); retrying. stderr: {result.stderr.strip()[:200]}",
                file=sys.stderr,
            )
    assert last_result is not None
    raise subprocess.CalledProcessError(
        last_result.returncode,
        last_result.args,
        output=last_result.stdout,
        stderr=last_result.stderr,
    )


def gh_command(prefix: list[str], *args: str) -> list[str]:
    return [*prefix, *args]


def load_queue(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    issues = data.get("issues", [])
    if not isinstance(issues, list):
        raise ValueError(f"{path} does not contain an issues list")
    loaded = [issue for issue in issues if isinstance(issue, dict)]
    validate_issue_queue(loaded)
    return loaded


def validate_issue_queue(issues: list[dict[str, Any]]) -> None:
    failures: list[str] = []
    for index, issue in enumerate(issues, start=1):
        repo = str(issue.get("repo") or "<missing repo>")
        title = str(issue.get("title") or "<missing title>")
        body = str(issue.get("body") or "")
        if not repo or repo == "<missing repo>":
            failures.append(f"issue {index} is missing repo")
        if not title or title == "<missing title>":
            failures.append(f"issue {index} is missing title")
        for error in issue_body_quality_errors(body):
            failures.append(f"{repo} :: {title}: {error}")
        for error in review_evidence_trace_errors(issue.get("review_evidence_trace")):
            failures.append(f"{repo} :: {title}: {error}")
    if failures:
        joined = "\n- ".join(failures)
        raise ValueError(f"approved issue queue failed quality validation:\n- {joined}")


ITEM_MARKER_RE = re.compile(r"<!--\s*repo-review-item:\s*(\S+?)\s*-->")


def item_hash(repo: str, title: str) -> str:
    """Stable short hash identifying a repo-review item by repo + candidate title.

    Materialization ledger (#2272): the same approved candidate must hash to the
    same value across re-runs and across cycles, so re-materialization can be
    detected from the marker alone. Title is lowercased/whitespace-collapsed so
    trivial formatting differences don't change the identity.
    """
    norm_title = re.sub(r"\s+", " ", str(title or "").strip().lower())
    digest = hashlib.sha256(f"{repo}\x00{norm_title}".encode()).hexdigest()
    return digest[:12]


def item_marker(repo: str, title: str) -> str:
    """The per-item HTML-comment marker embedded in created issue bodies."""
    return f"<!-- repo-review-item: {repo}#{item_hash(repo, title)} -->"


def body_has_item_marker(body: str, marker: str) -> bool:
    """True when an existing issue body already carries this exact item marker."""
    target = ITEM_MARKER_RE.search(marker)
    target_id = target.group(1) if target else marker
    return any(found.group(1) == target_id for found in ITEM_MARKER_RE.finditer(str(body or "")))


def find_marker_duplicate(
    issue: dict[str, Any], existing_issues: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Find an existing (open OR closed) issue already materialized for this item.

    Consults the per-item marker (#2272) so a re-run after the issue was closed
    finds it by identity even if the title was edited. Returns the matching
    existing issue, or None.
    """
    marker = item_marker(str(issue.get("repo", "")), str(issue.get("title", "")))
    for existing in existing_issues:
        if body_has_item_marker(str(existing.get("body") or ""), marker):
            return existing
    return None


def fetch_open_issues(repo: str, prefix: list[str]) -> list[dict[str, Any]]:
    """Fetch issues to dedup against.

    Materialization ledger (#2272): dedup must see recently-CLOSED issues, not
    just open ones. The steady state within days of a weekly cycle is that every
    approved item is already materialized AND closed; re-running ``--apply`` on a
    queue that still lists those titles would otherwise recreate the whole batch
    (the open-only blindness that produced duplicate storms). We therefore query
    ``--state all`` and also pull each issue ``body`` so the per-item marker
    (see ``item_marker``) can be matched exactly, independent of title drift.
    The function name is retained for monkeypatch compatibility.
    """
    result = run_command_with_retry(
        gh_command(
            prefix,
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "all",
            "--limit",
            "500",
            "--json",
            "number,title,labels,url,body,state",
        ),
        label=f"issue-list[{repo}]",
    )
    return json.loads(result.stdout or "[]")


def issue_labels(issue: dict[str, Any]) -> set[str]:
    return {str(label.get("name")) for label in issue.get("labels", []) if isinstance(label, dict)}


def duplicate_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", text.lower())
        if len(token) > 2 and token not in SEMANTIC_DUPLICATE_STOPWORDS
    }


def duplicate_text(issue: dict[str, Any]) -> str:
    trace = issue.get("review_evidence_trace") if isinstance(issue, dict) else None
    trace_text = ""
    if isinstance(trace, dict):
        trace_text = " ".join(
            str(value)
            for key in ("gap", "current_state", "required_change")
            for value in [trace.get(key)]
            if value
        )
    return "\n".join(
        [
            str(issue.get("title") or ""),
            str(issue.get("body") or ""),
            trace_text,
        ]
    )


def duplicate_similarity(candidate: dict[str, Any], existing: dict[str, Any]) -> float:
    candidate_tokens = duplicate_tokens(duplicate_text(candidate))
    existing_tokens = duplicate_tokens(duplicate_text(existing))
    if not candidate_tokens or not existing_tokens:
        return 0.0
    return len(candidate_tokens & existing_tokens) / len(candidate_tokens | existing_tokens)


def find_semantic_duplicate(
    candidate: dict[str, Any], open_issues: list[dict[str, Any]]
) -> dict[str, Any] | None:
    scored: list[tuple[float, dict[str, Any]]] = []
    for issue in open_issues:
        if SEMANTIC_DUPLICATE_LABEL not in issue_labels(issue):
            continue
        scored.append((duplicate_similarity(candidate, issue), issue))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_issue = scored[0]
    next_score = scored[1][0] if len(scored) > 1 else 0.0
    if (
        best_score >= SEMANTIC_DUPLICATE_THRESHOLD
        and best_score - next_score >= SEMANTIC_DUPLICATE_MARGIN
    ):
        return best_issue
    return None


DEFAULT_LABEL_COLOR = "ededed"
DEFAULT_LABEL_DESCRIPTION = "Auto-created by repo-review upload helper."


def ensure_labels(repo: str, labels: list[str], prefix: list[str]) -> None:
    """Create each label on the target repo if missing.

    For labels in the `LABELS` registry, use the canonical color/description.
    For unknown labels (e.g. a future audit-scope label not yet promoted to
    LABELS), create them with neutral defaults rather than crashing — we'd
    rather have a less-pretty label than block 18 issue uploads on a
    schema-registry mismatch. `gh label create` is a no-op if the label
    already exists, so this is idempotent.
    """
    for label in labels:
        config = LABELS.get(
            label,
            {
                "color": DEFAULT_LABEL_COLOR,
                "description": DEFAULT_LABEL_DESCRIPTION,
            },
        )
        run_command(
            gh_command(
                prefix,
                "label",
                "create",
                label,
                "--repo",
                repo,
                "--color",
                config["color"],
                "--description",
                config["description"],
            )
        )


def add_missing_labels(
    repo: str,
    issue_number: int,
    labels: list[str],
    existing_labels: list[dict[str, Any]],
    prefix: list[str],
) -> None:
    existing = {label.get("name") for label in existing_labels}
    missing = [label for label in labels if label not in existing]
    if not missing:
        return
    run_command(
        gh_command(
            prefix,
            "issue",
            "edit",
            str(issue_number),
            "--repo",
            repo,
            "--add-label",
            ",".join(missing),
        ),
        check=True,
    )


def body_with_item_marker(repo: str, title: str, body: str) -> str:
    """Return the issue body with the per-item marker appended (idempotent)."""
    marker = item_marker(repo, title)
    if body_has_item_marker(body, marker):
        return body
    return f"{body.rstrip()}\n\n{marker}\n"


def create_issue(issue: dict[str, Any], prefix: list[str]) -> str:
    labels = [str(label) for label in issue.get("labels", [])]
    repo = str(issue["repo"])
    title = str(issue["title"])
    args = gh_command(
        prefix,
        "issue",
        "create",
        "--repo",
        repo,
        "--title",
        title,
    )
    for label in labels:
        args.extend(["--label", label])
    # Materialization ledger (#2272): stamp the body with a stable per-item
    # marker so future runs can detect this item was already materialized,
    # including after it is closed.
    body = body_with_item_marker(repo, title, str(issue["body"]))
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md") as body_file:
        body_file.write(body)
        body_file.flush()
        result = run_command_with_retry(
            [*args, "--body-file", body_file.name],
            label=f"issue-create[{issue['repo']}]",
        )
    return result.stdout.strip()


def approval_body_key(body: str) -> tuple[str, ...]:
    """Allow prose whitespace formatting only; code and every approved word stay fixed."""
    return tuple(
        part if index % 2 else re.sub(r"\s+", " ", part).strip()
        for index, part in enumerate(re.split(r"(```.*?```|`[^`]*`)", body, flags=re.DOTALL))
    )


def role_body_errors(body: str, approved_body: str | None = None) -> list[str]:
    """Apply both the weekly quality bar and the fleet's runnable-acceptance contract."""
    errors = issue_body_quality_errors(body)
    if approved_body is not None and approval_body_key(body) != approval_body_key(approved_body):
        errors.append(
            "role body changed approved content; retain the approved scope and evidence verbatim"
        )
    spec = importlib.util.spec_from_file_location(
        "_repo_review_issue_format",
        Path(__file__).resolve().parents[1] / ".github/scripts/issue_format.py",
    )
    if spec is None or spec.loader is None:
        return errors + ["fleet issue-format validator unavailable"]
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    report = module.validate(body)
    return (
        errors
        + list(report.problems)
        + [f"missing section: {name}" for name in report.missing_required]
    )


def author_issue_batch(
    issues: list[dict[str, Any]], *, output_root: Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Optional local authoring; validated original bodies remain each item's fallback."""
    mirror = ORCHESTRATOR_MIRROR
    tools = ("capability_advisor.py", "roles.py", "capability_propensity.py")
    if not all((mirror / name).is_file() for name in tools):
        return issues, {"state": "mirror-unavailable"}
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix="batch-", dir=output_root)).resolve()
    except OSError as exc:
        return issues, {"state": "evidence-directory-unavailable", "error": str(exc)}
    receipt: dict[str, Any] = {"state": "baseline", "directory": str(directory), "items": []}

    def invoke(name: str, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                [sys.executable, str(mirror / name), *args],
                cwd=mirror,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            result = subprocess.CompletedProcess([name, *args], 1, "", str(exc))
        (directory / f"{name}.stdout.txt").write_text(result.stdout, encoding="utf-8")
        (directory / f"{name}.stderr.txt").write_text(result.stderr, encoding="utf-8")
        return result

    repos = sorted({str(issue["repo"]) for issue in issues})
    advice_result = invoke(
        "capability_advisor.py",
        "--json",
        "--surface",
        "repo-review-uploader",
        "--repository",
        ",".join(repos),
        f"Author {len(issues)} approved issue bodies for {', '.join(repos)}; preserve each "
        "approved scope, acceptance evidence, title and labels, and validate before filing.",
    )
    try:
        advice = json.loads(advice_result.stdout) if advice_result.returncode == 0 else {}
        if not isinstance(advice, dict):
            advice = {}
    except ValueError:
        advice = {}
    experiment = advice.get("experiment_id")
    offered = any(
        isinstance(cap, dict) and cap.get("capability_id") == "role-prompt"
        for cap in (advice.get("capabilities") or [])
    )
    receipt["experiment_id"] = experiment
    receipt["offered"] = offered
    reason = "The advisor did not offer role-prompt for this batch."
    kind = "wrong_match"
    manifests: dict[str, dict[str, Any]] = {}
    role_directory = directory / "role"
    targets = [
        f"{item['repo']}#review-{item_hash(str(item['repo']), str(item['title']))}"
        for item in issues
    ]
    if offered and len(issues) >= 3:
        batch = [
            {
                "target": target,
                "goal": str(item["title"]),
                "repo": str(item["repo"]),
                "context": "Preserve the complete approved body and evidence verbatim. Only adjust prose "
                "whitespace; do not change code, words, requirements or evidence references.\n"
                + str(item["body"])
                + "\n"
                + json.dumps(item.get("review_evidence_trace", {})),
                "constraints": [
                    "Keep every approved word and code span; substantive rewrites fall back to the original.",
                    "Return an issue_body; do not file issues or change titles/labels.",
                ],
            }
            for target, item in zip(targets, issues, strict=True)
        ]
        batch_file = directory / "batch.json"
        batch_file.write_text(json.dumps(batch, indent=2), encoding="utf-8")
        role_result = invoke(
            "roles.py",
            "prompt",
            "--batch",
            str(batch_file),
            "--output",
            "issue_body",
            "--output-dir",
            str(role_directory),
            "--dispatch",
            "--json",
            timeout=600,
        )
        receipt["role_exit"] = role_result.returncode
        # A partial failure exits nonzero but still publishes valid siblings and failed evidence.
        try:
            manifest = json.loads((role_directory / "manifest.json").read_text(encoding="utf-8"))
            for row in manifest.get("items", []):
                if isinstance(row, dict) and row.get("target") in targets:
                    target = row["target"]
                    if target in manifests:
                        raise ValueError("duplicate target in role manifest")
                    manifests[target] = row
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            receipt["manifest_error"] = str(exc)
            manifests = {}
        receipt["role_manifest"] = str(role_directory / "manifest.json")
        reason, kind = "No role-authored body passed uploader validation.", "precondition_unmet"
    elif offered:
        reason, kind = "The upload batch contains fewer than three new items.", "scope_too_small"

    selected = []
    for target, item in zip(targets, issues, strict=True):
        row = manifests.get(target, {})
        errors: list[str] = []
        body = None
        if row.get("valid") is True and not row.get("errors") and not row.get("role_record_error"):
            try:
                path = Path(row["body_file"]).resolve()
                if not path.is_relative_to(role_directory.resolve()):
                    raise ValueError("body file is outside the retained role directory")
                body = path.read_text(encoding="utf-8")
                errors = role_body_errors(body, str(item["body"]))
            except (OSError, ValueError, TypeError, KeyError) as exc:
                errors = [str(exc)]
        else:
            errors = row.get("errors") or ["no valid role body"]
        used = bool(body and not errors)
        selected.append({**item, "body": body if used else item["body"]})
        receipt["items"].append({"target": target, "used_role": used, "errors": errors})
    receipt["state"] = (
        "role-authored" if any(row["used_role"] for row in receipt["items"]) else "baseline"
    )
    if experiment and receipt["state"] == "baseline":
        invoke(
            "capability_propensity.py",
            "decline",
            "--capability",
            "role-prompt",
            "--experiment",
            str(experiment),
            "--surface",
            "repo-review-uploader",
            "--kind",
            kind,
            "--reason",
            reason,
        )
    (directory / "upload-authoring.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    return selected, receipt


def record_authoring_delivery(receipt: dict[str, Any], index: int, url: str) -> None:
    """Join a used role body to the actual issue identity, never to a synthetic queue ID."""
    if not receipt.get("experiment_id") or not receipt.get("items", [])[index]["used_role"]:
        return
    parts = url.rstrip("/").split("/")
    if len(parts) < 5 or parts[-2] != "issues" or not parts[-1].isdigit():
        return
    target = "/".join(parts[-4:-2]) + "#" + parts[-1]
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(ORCHESTRATOR_MIRROR / "capability_propensity.py"),
                "trigger",
                "--capability",
                "role-prompt",
                "--experiment",
                str(receipt["experiment_id"]),
                "--deliverable",
                target,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        receipt["items"][index]["trigger"] = {
            "exit": result.returncode,
            "deliverable": target,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        receipt["items"][index]["trigger"] = {"error": str(exc), "deliverable": target}
    (Path(receipt["directory"]) / "upload-authoring.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )


def upload_issues(
    issues: list[dict[str, Any]],
    *,
    prefix: list[str],
    apply: bool,
    repo_filter: set[str] | None = None,
    authoring_dir: Path | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "apply": apply,
        "created": [],
        "skipped_duplicates": [],
        "would_create": [],
    }
    by_repo: dict[str, list[dict[str, Any]]] = {}
    validate_issue_queue(issues)
    for issue in issues:
        repo = str(issue.get("repo", ""))
        if not repo:
            continue
        if repo_filter and repo not in repo_filter:
            continue
        by_repo.setdefault(repo, []).append(issue)

    pending: list[dict[str, Any]] = []
    for repo, repo_issues in sorted(by_repo.items()):
        # `existing_issues` now includes recently-closed issues (#2272), so a
        # re-run after items were materialized-and-closed does not recreate them.
        existing_issues = fetch_open_issues(repo, prefix)
        open_by_title = {item.get("title"): item for item in existing_issues}
        labels = sorted({label for issue in repo_issues for label in issue.get("labels", [])})
        if apply:
            ensure_labels(repo, labels, prefix)
        for issue in repo_issues:
            title = str(issue["title"])
            # Dedup precedence: per-item marker (exact identity, open OR closed)
            # > exact title > token-Jaccard semantic match.
            existing = (
                find_marker_duplicate(issue, existing_issues)
                or open_by_title.get(title)
                or find_semantic_duplicate(issue, existing_issues)
            )
            if existing:
                if apply and existing.get("number") is not None:
                    add_missing_labels(
                        repo,
                        int(existing["number"]),
                        [str(label) for label in issue.get("labels", [])],
                        existing.get("labels", []),
                        prefix,
                    )
                summary["skipped_duplicates"].append(
                    {
                        "repo": repo,
                        "title": title,
                        "number": existing.get("number"),
                        "url": existing.get("url"),
                    }
                )
                continue
            if not apply:
                summary["would_create"].append({"repo": repo, "title": title})
                continue
            pending.append(issue)
            # Preserve same-batch duplicate suppression before optional authoring changes wording.
            existing_issues.append(
                {"title": title, "body": body_with_item_marker(repo, title, str(issue["body"]))}
            )
            open_by_title[title] = existing_issues[-1]
    if pending:
        authored, receipt = author_issue_batch(
            pending, output_root=authoring_dir or Path("docs/reports/repo-review/prompt-authoring")
        )
        summary["authoring"] = receipt
        snapshots: dict[str, list[dict[str, Any]]] = {}
        for index, issue in enumerate(authored):
            # Authoring can take minutes; another uploader may have filed the original meanwhile.
            repo_name = str(issue["repo"])
            if repo_name not in snapshots:
                snapshots[repo_name] = fetch_open_issues(repo_name, prefix)
            current = snapshots[repo_name]
            original = pending[index]
            existing = (
                find_marker_duplicate(original, current)
                or next((row for row in current if row.get("title") == original["title"]), None)
                or find_semantic_duplicate(original, current)
            )
            if existing:
                add_missing_labels(
                    str(issue["repo"]),
                    int(existing["number"]),
                    [str(label) for label in issue.get("labels", [])],
                    existing.get("labels", []),
                    prefix,
                )
                summary["skipped_duplicates"].append(
                    {
                        "repo": issue["repo"],
                        "title": issue["title"],
                        "number": existing["number"],
                        "url": existing.get("url"),
                    }
                )
                continue
            url = create_issue(issue, prefix)
            summary["created"].append({"repo": issue["repo"], "title": issue["title"], "url": url})
            record_authoring_delivery(receipt, index, url)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--queue",
        type=Path,
        default=Path("docs/reports/repo-review/approved-issue-queue.json"),
        help="Path to approved-issue-queue.json (default: the path the "
        "final evaluator pass writes)",
    )
    parser.add_argument(
        "--gh-prefix",
        default="gh",
        help="Command prefix for GitHub CLI calls, e.g. 'gh' or 'detached-net.sh gh'",
    )
    parser.add_argument("--repo", action="append", default=[], help="Limit upload to this repo.")
    parser.add_argument(
        "--authoring-dir", type=Path, help="Retain optional role bodies and failure manifests here."
    )
    parser.add_argument("--apply", action="store_true", help="Create/edit issues on GitHub.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        metadata = json.loads(args.queue.read_text(encoding="utf-8"))
        hold = metadata.get("intake_hold", {})
        if not isinstance(hold, dict):
            raise ValueError("Invalid intake hold metadata; upload refused")
        if "active" in hold and not isinstance(hold["active"], bool):
            raise ValueError("Invalid intake hold state; upload refused")
        if "upload_allowed" in metadata and not isinstance(metadata["upload_allowed"], bool):
            raise ValueError("Invalid upload permission; upload refused")
        if args.apply and (hold.get("active") is True or metadata.get("upload_allowed") is False):
            raise ValueError("Owner intake hold active; upload refused before any GitHub mutation")
        if args.apply and metadata.get("approval_scope_conflicts"):
            raise ValueError("Unresolved approved scope conflicts; reconcile before upload")
        issues = load_queue(args.queue)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    summary = upload_issues(
        issues,
        prefix=shlex.split(args.gh_prefix),
        apply=args.apply,
        repo_filter=set(args.repo) if args.repo else None,
        authoring_dir=getattr(args, "authoring_dir", None),
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
