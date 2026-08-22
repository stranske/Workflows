#!/usr/bin/env python3
"""Build bounded docs-drift repair plans from existing drift detectors.

This is the missing "fix-agent" layer for docs drift: it does not perform a
new semantic scan and it does not edit files. It composes the deterministic
docs-drift check plus an optional weekly ``docs-drift-scan.json`` export into
small repair batches with:

- an agent prompt for opening a focused fix PR
- an agent-ready GitHub issue body
- a local verification checklist

Default mode is read-only. ``--apply`` creates one issue per repair batch and
never edits repository files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import check_docs_drift  # noqa: E402

DEFAULT_REPO = "stranske/Workflows"
DEFAULT_MAX_PER_BATCH = 8
DEFAULT_DOCS_CONFIG = Path("config/source_of_truth_docs.yml")


@dataclass(frozen=True)
class Finding:
    source: str
    kind: str
    doc_path: str
    target: str
    detail: str
    classification: str = ""
    authoritative_source: str = ""


@dataclass(frozen=True)
class RepairBatch:
    batch_id: str
    findings: tuple[Finding, ...]


def detect_repo_root(cwd: Path | None = None) -> Path:
    """Find the git root, falling back to the current directory."""
    probe = cwd or Path.cwd()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=False,
            cwd=probe,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        result = None
    if result and result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return probe.resolve()


def detect_repo_slug(repo_root: Path) -> str | None:
    """Return the GitHub origin slug when available."""
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            check=False,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?$", result.stdout.strip())
    return f"{match.group(1)}/{match.group(2)}" if match else None


def detect_configured_repo(repo_root: Path) -> str | None:
    """Infer a registered repo from its configured local checkout name.

    Consumer checkouts occasionally use a non-GitHub origin (for example, a
    local mirror), so remote parsing alone must not silently fall back to the
    Workflows default configuration.
    """
    config_path = repo_root / DEFAULT_DOCS_CONFIG
    if not config_path.is_file():
        return None
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid docs config YAML: {exc}") from exc
    repos = data.get("repos", {}) if isinstance(data, Mapping) else {}
    if not isinstance(repos, Mapping):
        return None
    matches = [
        str(slug)
        for slug, entry in repos.items()
        if isinstance(entry, Mapping) and str(entry.get("local_path") or "") == repo_root.name
    ]
    return matches[0] if len(matches) == 1 else None


def _doc_from_detail(detail: str) -> str:
    match = re.search(r"Referenced in ([^`]+)$", detail or "")
    if match:
        return match.group(1).strip()
    return "docs/ci/WORKFLOWS.md"


def findings_from_deterministic_report(report: dict[str, Any]) -> list[Finding]:
    """Map ``check_docs_drift.build_report`` output into repair findings."""
    findings: list[Finding] = []
    for row in report.get("drift") or []:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("type") or "")
        path = str(row.get("path") or "")
        detail = str(row.get("detail") or "")
        doc_path = (
            _doc_from_detail(detail) if kind == "dangling_reference" else "docs/ci/WORKFLOWS.md"
        )
        findings.append(
            Finding(
                source="deterministic",
                kind=kind,
                doc_path=doc_path,
                target=path,
                detail=detail,
                classification=kind,
                authoritative_source=path,
            )
        )
    return findings


def findings_from_scan_json(payload: dict[str, Any], *, repo: str) -> list[Finding]:
    """Extract stale/contradictory semantic drift from docs-drift-scan JSON."""
    if not isinstance(payload, Mapping):
        raise ValueError("scan JSON must contain a top-level mapping")
    findings: list[Finding] = []
    for bucket in payload.get("by_repo") or []:
        if not isinstance(bucket, dict) or bucket.get("repo") != repo:
            continue
        for row in bucket.get("drift_instances") or []:
            if not isinstance(row, dict):
                continue
            classification = str(row.get("classification") or "")
            if classification not in {"stale", "contradictory"}:
                continue
            claim = str(row.get("claim") or "").strip()
            doc_path = str(row.get("doc_path") or "").strip() or "<unknown-doc>"
            findings.append(
                Finding(
                    source="semantic-scan",
                    kind="semantic_drift",
                    doc_path=doc_path,
                    target=claim[:160] or doc_path,
                    detail=claim,
                    classification=classification,
                    authoritative_source=str(row.get("authoritative_source") or "").strip(),
                )
            )
    return findings


def dedupe_findings(findings: Sequence[Finding]) -> list[Finding]:
    """Collapse obvious duplicates while preferring deterministic findings."""
    priority = {"deterministic": 0, "semantic-scan": 1}
    ordered = sorted(
        findings, key=lambda f: (priority.get(f.source, 9), f.doc_path, f.kind, f.target)
    )
    seen: set[tuple[str, str, str]] = set()
    out: list[Finding] = []
    for finding in ordered:
        key = (
            finding.doc_path.strip().lower(),
            finding.kind.strip().lower(),
            finding.target.strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(finding)
    return sorted(out, key=lambda f: (f.doc_path, f.source, f.kind, f.target))


def batch_findings(
    findings: Sequence[Finding],
    *,
    max_per_batch: int = DEFAULT_MAX_PER_BATCH,
) -> list[RepairBatch]:
    if max_per_batch <= 0:
        raise ValueError("max_per_batch must be positive")
    unique = dedupe_findings(findings)
    batches: list[RepairBatch] = []
    for index in range(0, len(unique), max_per_batch):
        chunk = tuple(unique[index : index + max_per_batch])
        batches.append(RepairBatch(batch_id=f"docs-drift-{len(batches) + 1:02d}", findings=chunk))
    return batches


def _docs_arg(docs: Sequence[str] | None) -> str:
    if not docs:
        return ""
    return " --docs " + " ".join(shlex.quote(doc) for doc in docs)


def _only_arg(findings: Sequence[Finding] | None) -> str:
    if not findings:
        return ""
    targets = sorted({finding.target for finding in findings if finding.source == "deterministic"})
    if not targets:
        return ""
    return " --only " + " ".join(shlex.quote(target) for target in targets)


def verification_commands(
    docs: Sequence[str] | None = None, findings: Sequence[Finding] | None = None
) -> tuple[str, ...]:
    """Commands that must pass after a single repair batch."""
    docs_arg = _docs_arg(docs)
    only_arg = _only_arg(findings)
    return (
        f"python3 scripts/check_docs_drift.py --json{docs_arg}{only_arg}",
        "python3 -m py_compile scripts/check_docs_drift.py scripts/docs_drift_fix_agent.py",
    )


def semantic_verification_requirements(
    findings: Sequence[Finding] | None = None,
) -> tuple[str, ...]:
    """Return required human evidence for semantic-only drift findings.

    The deterministic checker cannot prove that a stale or contradictory claim
    was repaired. Keep that limitation explicit in every generated artifact so
    a green deterministic command cannot satisfy a semantic repair by itself.
    """
    requirements: list[str] = []
    for finding in findings or ():
        if finding.source != "semantic-scan":
            continue
        source = finding.authoritative_source or "the authoritative implementation"
        requirement = (
            f"Manually compare `{finding.doc_path}` claim `{finding.target}` against "
            f"`{source}` and record the before/after evidence in the pull request body."
        )
        if requirement not in requirements:
            requirements.append(requirement)
    return tuple(requirements)


def informational_commands(docs: Sequence[str] | None = None) -> tuple[str, ...]:
    """Commands that refresh full-plan context but may still report other batches."""
    docs_arg = _docs_arg(docs)
    return (f"python3 scripts/docs_drift_fix_agent.py --repo-root . --json{docs_arg}",)


def _finding_line(finding: Finding) -> str:
    suffix = f" ({finding.classification})" if finding.classification else ""
    source = f"; source={finding.authoritative_source}" if finding.authoritative_source else ""
    return (
        f"- `{finding.doc_path}`: {finding.kind}{suffix}; target `{finding.target}`; "
        f"{finding.detail}{source}"
    )


def build_repair_prompt(
    batch: RepairBatch,
    *,
    repo: str = DEFAULT_REPO,
    checks: Sequence[str] | None = None,
    informational_checks: Sequence[str] | None = None,
) -> str:
    finding_lines = "\n".join(_finding_line(finding) for finding in batch.findings)
    check_lines = "\n".join(
        f"- `{cmd}`" for cmd in (checks or verification_commands(findings=batch.findings))
    )
    info_lines = "\n".join(
        f"- `{cmd}`" for cmd in (informational_checks or informational_commands())
    )
    semantic_lines = "\n".join(
        f"- {requirement}" for requirement in semantic_verification_requirements(batch.findings)
    )
    semantic_section = (
        f"\nRequired semantic evidence:\n{semantic_lines}\n" if semantic_lines else ""
    )
    return f"""You are repairing documentation drift in {repo}.

Goal: open one focused docs-only fix PR for repair batch `{batch.batch_id}`.

Findings to repair:
{finding_lines}

Rules:
- Fix the documentation to match the current repository tree unless the finding names a stronger source of truth.
- Keep edits narrow. Do not rewrite whole documents or introduce new design content.
- Do not change workflows, scripts, templates, generated files, or consumer repositories in this batch.
- Cite exact file paths in the PR body and include the verification commands you ran.

Required verification before opening the PR:
{check_lines}
{semantic_section}

Informational full-plan refresh:
{info_lines}

Deliverable:
- Commit the docs-only changes.
- Push a branch.
- Open a PR titled `[Docs Drift] Repair {batch.batch_id}`.
"""


def build_pr_plan(
    batch: RepairBatch,
    *,
    checks: Sequence[str] | None = None,
    informational_checks: Sequence[str] | None = None,
) -> str:
    doc_paths = sorted({finding.doc_path for finding in batch.findings})
    check_lines = "\n".join(
        f"- [ ] `{cmd}`" for cmd in (checks or verification_commands(findings=batch.findings))
    )
    info_lines = "\n".join(
        f"- [ ] `{cmd}`" for cmd in (informational_checks or informational_commands())
    )
    semantic_lines = "\n".join(
        f"- [ ] {requirement}" for requirement in semantic_verification_requirements(batch.findings)
    )
    semantic_section = f"\n## Semantic Evidence\n{semantic_lines}\n" if semantic_lines else ""
    findings = "\n".join(_finding_line(finding) for finding in batch.findings)
    docs = "\n".join(f"- [ ] `{doc}`" for doc in doc_paths)
    return f"""# Docs Drift Repair Plan: {batch.batch_id}

## Scope
{docs}

## Findings
{findings}

## Verification
{check_lines}
{semantic_section}

## Informational Refresh
{info_lines}
"""


def build_issue_body(
    batch: RepairBatch,
    *,
    repo: str = DEFAULT_REPO,
    checks: Sequence[str] | None = None,
    informational_checks: Sequence[str] | None = None,
) -> str:
    findings = "\n".join(_finding_line(finding) for finding in batch.findings)
    docs = sorted({finding.doc_path for finding in batch.findings})
    docs_tasks = "\n".join(
        f"- [ ] Update `{doc}` so its cited claims match the current tree." for doc in docs
    )
    check_items = "\n".join(
        f"- [ ] `{cmd}` passes after the repair."
        for cmd in (checks or verification_commands(findings=batch.findings))
    )
    semantic_items = "\n".join(
        f"- [ ] {requirement}" for requirement in semantic_verification_requirements(batch.findings)
    )
    info_items = "\n".join(
        f"- [ ] `{cmd}` was reviewed for remaining non-batch findings."
        for cmd in (informational_checks or informational_commands())
    )
    evidence = "\n".join(
        f"- `{finding.doc_path}` -> `{finding.target}` ({finding.source}/{finding.kind})"
        for finding in batch.findings
    )
    return f"""## Why
The docs-drift fix-agent found source-of-truth documentation claims that no longer match current repository state in `{repo}`. Stale operational docs mislead agents and humans during workflow maintenance.

## Scope
Repair only the docs named in this issue for batch `{batch.batch_id}`:

{findings}

## Non-Goals
- Do not change workflow YAML, scripts, templates, generated artifacts, or consumer repositories.
- Do not broaden the docs or rewrite unrelated sections.
- Do not resolve findings outside this batch.

## Tasks
{docs_tasks}
- [ ] Keep each edit tied to one listed finding and preserve unrelated wording.
- [ ] Include the relevant before/after claim in the pull request body.
- [ ] Run the bounded docs-drift and Python compile verification commands.
- [ ] Refresh the full fix-agent plan as informational context.

## Acceptance Criteria
{check_items}
{semantic_items}
- [ ] The pull request changes only documentation files for this batch.
- [ ] The PR body lists each repaired finding and the source used to verify it.

## Informational Checks
These commands may still report findings for other batches and should not block this batch once the required checks pass:

{info_items}

## Implementation Notes
Use `scripts/docs_drift_fix_agent.py` output for the repair prompt and plan. Evidence trace:

{evidence}
"""


def load_scan_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"by_repo": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("scan JSON must contain a top-level mapping")
    return dict(payload)


def default_docs_from_config(repo_root: Path, *, repo: str = DEFAULT_REPO) -> list[str]:
    config_path = repo_root / DEFAULT_DOCS_CONFIG
    if not config_path.is_file():
        return [doc for doc in check_docs_drift.DEFAULT_DOCS if (repo_root / doc).is_file()]
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid docs config YAML: {exc}") from exc
    if not isinstance(data, Mapping):
        raise ValueError("docs config must contain a top-level mapping")
    repos = data.get("repos", {})
    if repos is None:
        repos = {}
    if not isinstance(repos, Mapping):
        raise ValueError("docs config 'repos' must be a mapping")
    repo_config = repos.get(repo, {})
    if repo_config is None:
        repo_config = {}
    if not isinstance(repo_config, Mapping):
        raise ValueError(f"docs config entry for {repo!r} must be a mapping")
    docs = [
        str(item.get("path"))
        for item in repo_config.get("docs") or []
        if isinstance(item, dict) and item.get("path")
    ]
    candidates = docs or list(check_docs_drift.DEFAULT_DOCS)
    missing = [doc for doc in candidates if not (repo_root / doc).is_file()]
    if docs and missing:
        raise FileNotFoundError(f"configured docs not found for {repo}: {', '.join(missing)}")
    return [doc for doc in candidates if (repo_root / doc).is_file()]


def collect_findings(
    *,
    repo_root: Path,
    repo: str,
    docs: Sequence[str] | None = None,
    scan_json: Path | None = None,
) -> list[Finding]:
    docs_to_scan = (
        list(docs) if docs is not None else default_docs_from_config(repo_root, repo=repo)
    )
    deterministic = check_docs_drift.build_report(
        check_docs_drift.check_docs_drift(repo_root, docs_to_scan)
    )
    findings = findings_from_deterministic_report(deterministic)
    if scan_json is not None:
        findings.extend(findings_from_scan_json(load_scan_json(scan_json), repo=repo))
    return dedupe_findings(findings)


def build_plan(
    *,
    repo_root: Path,
    repo: str,
    docs: Sequence[str] | None = None,
    scan_json: Path | None = None,
    max_per_batch: int = DEFAULT_MAX_PER_BATCH,
) -> dict[str, Any]:
    docs_to_scan = (
        list(docs) if docs is not None else default_docs_from_config(repo_root, repo=repo)
    )
    findings = collect_findings(
        repo_root=repo_root, repo=repo, docs=docs_to_scan, scan_json=scan_json
    )
    batches = batch_findings(findings, max_per_batch=max_per_batch)
    return {
        "repo": repo,
        "repo_root": str(repo_root),
        "finding_count": len(findings),
        "batch_count": len(batches),
        "checks": list(verification_commands(docs_to_scan)),
        "findings": [asdict(finding) for finding in findings],
        "batches": [
            {
                "batch_id": batch.batch_id,
                "findings": [asdict(finding) for finding in batch.findings],
                "semantic_verification": list(semantic_verification_requirements(batch.findings)),
                "repair_prompt": build_repair_prompt(
                    batch,
                    repo=repo,
                    checks=verification_commands(docs_to_scan, batch.findings),
                    informational_checks=informational_commands(docs_to_scan),
                ),
                "issue_title": f"[Docs Drift] Repair {batch.batch_id}",
                "issue_body": build_issue_body(
                    batch,
                    repo=repo,
                    checks=verification_commands(docs_to_scan, batch.findings),
                    informational_checks=informational_commands(docs_to_scan),
                ),
                "pr_plan": build_pr_plan(
                    batch,
                    checks=verification_commands(docs_to_scan, batch.findings),
                    informational_checks=informational_commands(docs_to_scan),
                ),
            }
            for batch in batches
        ],
    }


def write_plan_outputs(plan: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    for batch in plan["batches"]:
        batch_id = batch["batch_id"]
        (out_dir / f"{batch_id}-repair-prompt.md").write_text(
            batch["repair_prompt"], encoding="utf-8"
        )
        (out_dir / f"{batch_id}-issue-body.md").write_text(batch["issue_body"], encoding="utf-8")
        (out_dir / f"{batch_id}-pr-plan.md").write_text(batch["pr_plan"], encoding="utf-8")


def apply_issues(plan: dict[str, Any]) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    existing_by_marker: dict[str, str] = {}
    for batch in plan["batches"]:
        issue_body = batch["issue_body"]
        digest = hashlib.sha256(f"{batch['issue_title']}\0{issue_body}".encode()).hexdigest()[:16]
        marker = f"<!-- docs-drift-fix-agent:{digest} -->"
        list_result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                plan["repo"],
                "--state",
                "open",
                "--label",
                "documentation",
                "--search",
                f'"{marker}" in:body',
                "--limit",
                "1",
                "--json",
                "body,url",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if list_result.returncode != 0:
            raise RuntimeError(f"gh issue list failed: {list_result.stderr.strip()}")
        matches = json.loads(list_result.stdout or "[]")
        if not isinstance(matches, list):
            raise ValueError("gh issue list returned a non-list payload")
        for row in matches:
            if isinstance(row, Mapping) and marker in str(row.get("body") or ""):
                existing_by_marker[marker] = str(row.get("url") or "")
                break
        if marker in existing_by_marker:
            created.append(
                {
                    "batch_id": batch["batch_id"],
                    "disposition": "already-open",
                    "returncode": 0,
                    "stdout": existing_by_marker[marker],
                    "stderr": "",
                }
            )
            continue
        result = subprocess.run(
            [
                "gh",
                "issue",
                "create",
                "--repo",
                plan["repo"],
                "--title",
                batch["issue_title"],
                "--body",
                f"{issue_body.rstrip()}\n\n{marker}\n",
                "--label",
                "documentation",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        created.append(
            {
                "batch_id": batch["batch_id"],
                "disposition": "created",
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"gh issue create failed for {batch['batch_id']}: {result.stderr.strip()}"
            )
    return created


def format_summary(plan: dict[str, Any], out_dir: Path | None = None) -> str:
    lines = [
        f"Docs drift fix-agent: {plan['finding_count']} finding(s) in {plan['batch_count']} batch(es)"
    ]
    by_source: dict[str, int] = {}
    for finding in plan["findings"]:
        by_source[finding["source"]] = by_source.get(finding["source"], 0) + 1
    if by_source:
        lines.append("  " + " ".join(f"{key}={by_source[key]}" for key in sorted(by_source)))
    for batch in plan["batches"]:
        docs = sorted({finding["doc_path"] for finding in batch["findings"]})
        lines.append(f"  {batch['batch_id']}: {', '.join(docs)}")
    if out_dir is not None:
        lines.append(f"Outputs: {out_dir}")
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build bounded docs-drift repair prompts and issue bodies."
    )
    parser.add_argument("--repo-root", type=Path, help="repository root to scan")
    parser.add_argument("--repo", help="GitHub repo name for issue/prompt output")
    parser.add_argument("--docs", nargs="+", help="repo-relative docs to scan for dangling refs")
    parser.add_argument("--scan-json", type=Path, help="optional repo_review docs-drift-scan.json")
    parser.add_argument("--out-dir", type=Path, help="write plan and per-batch prompt files")
    parser.add_argument("--max-per-batch", type=int, default=DEFAULT_MAX_PER_BATCH)
    parser.add_argument("--json", action="store_true", help="print plan JSON")
    parser.add_argument(
        "--apply", action="store_true", help="create one GitHub issue per repair batch"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        repo_root = (args.repo_root or detect_repo_root()).expanduser().resolve()
        if not repo_root.is_dir():
            raise FileNotFoundError(f"repo root not found: {repo_root}")
        scan_json = args.scan_json.expanduser().resolve() if args.scan_json else None
        if scan_json is not None and not scan_json.is_file():
            raise FileNotFoundError(f"scan json not found: {scan_json}")
        repo = args.repo or detect_repo_slug(repo_root) or detect_configured_repo(repo_root)
        if repo is None:
            raise ValueError("could not determine GitHub repo from origin; pass --repo")
        plan = build_plan(
            repo_root=repo_root,
            repo=repo,
            docs=args.docs,
            scan_json=scan_json,
            max_per_batch=args.max_per_batch,
        )
        out_dir = args.out_dir.expanduser().resolve() if args.out_dir else None
        if out_dir is not None:
            write_plan_outputs(plan, out_dir)
        if args.apply:
            plan["created_issues"] = apply_issues(plan)
        if args.json:
            print(json.dumps(plan, indent=2))
        else:
            print(format_summary(plan, out_dir))
        return 0 if args.apply else 1 if plan["finding_count"] else 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
