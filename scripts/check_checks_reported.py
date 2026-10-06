#!/usr/bin/env python3
"""Extend the incumbent presence reporter with exact-head topology receipts.

The historical frequency/ratchet reporter remains useful as a warning, but is
not an event-specific completeness proof. This adapter reuses its paginated
transport, never copies its reference algorithm, and fails closed for topology
that it cannot statically establish. It does not authorize a merge.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import itertools
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml


class UnknownEvidence(Exception):
    """Evidence unavailable or not supported by the conservative evaluator."""


class WorkflowLoader(yaml.SafeLoader):
    """GitHub uses YAML 1.2: its `on` key must not become the boolean True."""


WorkflowLoader.yaml_implicit_resolvers = {
    key: [(tag, pattern) for tag, pattern in values if tag != "tag:yaml.org,2002:bool"]
    for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load_presence_reporter(path: Path) -> Callable[[str], list[Any]]:
    """Use the existing Orchestrator reporter's complete-page REST transport."""
    spec = importlib.util.spec_from_file_location("incumbent_presence_reporter", path)
    if spec is None or spec.loader is None:
        raise UnknownEvidence("cannot load incumbent presence reporter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    transport = getattr(module, "_gh_json", None)
    if not callable(transport):
        raise UnknownEvidence("incumbent reporter lacks its paginated _gh_json transport")
    return transport


class Evidence:
    def __init__(self, transport: Callable[[str], list[Any]]):
        self.transport = transport
        self.requests: list[dict[str, Any]] = []

    def pages(self, endpoint: str) -> list[Any]:
        try:
            pages = self.transport(endpoint)
        except (SystemExit, Exception) as exc:
            raise UnknownEvidence(f"{endpoint}: {exc}") from exc
        if not isinstance(pages, list) or not pages:
            raise UnknownEvidence(f"{endpoint}: missing page evidence")
        self.requests.append(
            {
                "endpoint": endpoint,
                "pages": len(pages),
                "sha256": hashlib.sha256(json.dumps(pages, sort_keys=True).encode()).hexdigest(),
            }
        )
        return pages

    def one(self, endpoint: str) -> Any:
        pages = self.pages(endpoint)
        if len(pages) != 1:
            raise UnknownEvidence(f"{endpoint}: unexpected multiple objects")
        return pages[0]

    def items(self, endpoint: str, key: str | None = None) -> list[Any]:
        items = []
        total = None
        for page in self.pages(endpoint):
            values = page if key is None else page.get(key)
            if not isinstance(values, list):
                raise UnknownEvidence(f"{endpoint}: invalid list page")
            items.extend(values)
            if key is not None and "total_count" in page:
                total = page["total_count"]
        if total is not None and len(items) != total:
            raise UnknownEvidence(f"{endpoint}: enumerated {len(items)} of {total} items")
        return items

    def workflow(self, repo: str, path: str, ref: str) -> dict[str, Any]:
        obj = self.one(f"repos/{repo}/contents/{path}?ref={quote(ref, safe='')}")
        if obj.get("encoding") != "base64":
            raise UnknownEvidence(f"{repo}/{path}: unsupported content encoding")
        document = yaml.load(base64.b64decode(obj["content"]), Loader=WorkflowLoader)
        if not isinstance(document, dict):
            raise UnknownEvidence(f"{repo}/{path}: invalid workflow document")
        return document


def glob_match(value: str, pattern: str) -> bool:
    """Only the unambiguous *, ** and ? subset of Actions glob syntax."""
    if not isinstance(pattern, str) or re.search(r"[!\[\]{}+\\]", pattern):
        raise UnknownEvidence(f"unsupported Actions glob: {pattern!r}")
    pieces, index = [], 0
    while index < len(pattern):
        if pattern[index : index + 3] == "**/":
            pieces.append("(?:.*/)?")
            index += 3
        elif pattern[index : index + 2] == "**":
            pieces.append(".*")
            index += 2
        else:
            char = pattern[index]
            pieces.append("[^/]*" if char == "*" else "[^/]" if char == "?" else re.escape(char))
            index += 1
    return re.fullmatch("".join(pieces), value) is not None


def event_applies(
    workflow: dict[str, Any], event: str, action: str, branch: str, paths: list[str]
) -> tuple[bool, str]:
    triggers = workflow.get("on")
    if isinstance(triggers, str):
        triggers = {triggers: None}
    elif isinstance(triggers, list):
        triggers = dict.fromkeys(triggers)
    if not isinstance(triggers, dict):
        raise UnknownEvidence("missing/invalid workflow triggers")
    if event not in triggers:
        return False, f"event {event!r} not in {sorted(triggers)}"
    config = triggers[event] or {}
    if not isinstance(config, dict):
        raise UnknownEvidence("invalid event configuration")
    if event not in {"pull_request", "pull_request_target"}:
        raise UnknownEvidence(f"unsupported event context: {event}")
    types = config.get("types", ["opened", "synchronize", "reopened"])
    if action not in types:
        return False, f"action {action!r} not in {types}"
    for unknown in set(config) - {"types", "branches", "branches-ignore", "paths", "paths-ignore"}:
        raise UnknownEvidence(f"unsupported event filter: {unknown}")
    for positive, negative, values in [
        ("branches", "branches-ignore", [branch]),
        ("paths", "paths-ignore", paths),
    ]:
        if positive in config and negative in config:
            raise UnknownEvidence(f"conflicting filters: {positive}/{negative}")
        if positive in config:
            patterns = config[positive]
            if not isinstance(patterns, list):
                raise UnknownEvidence(f"invalid {positive} filter")
            matches = [glob_match(value, pattern) for value in values for pattern in patterns]
            if not any(matches):
                return False, f"{positive} excludes the bound branch/changed paths"
        if negative in config:
            patterns = config[negative]
            if not isinstance(patterns, list):
                raise UnknownEvidence(f"invalid {negative} filter")
            # Validate all patterns even if an earlier one matches.
            matches = [[glob_match(value, pattern) for pattern in patterns] for value in values]
            if matches and all(any(row) for row in matches):
                return False, f"{negative} excludes all bound branch/changed paths"
    return True, "event/action/branch/changed-path filters apply"


def job_names(job_id: str, job: dict[str, Any]) -> list[str]:
    """Expand literal matrices; dynamic matrices and expressions are UNKNOWN."""
    matrix = (job.get("strategy") or {}).get("matrix")
    name = str(job.get("name", job_id))
    if not matrix:
        if "${{" in name:
            raise UnknownEvidence(f"dynamic job name: {name}")
        return [name]
    if not isinstance(matrix, dict) or set(matrix) & {"include", "exclude"}:
        raise UnknownEvidence(f"unsupported matrix on {job_id}")
    if any(not isinstance(values, list) or not values for values in matrix.values()):
        raise UnknownEvidence(f"dynamic/empty matrix on {job_id}")
    combinations = list(itertools.product(*matrix.values()))
    if len(combinations) > 256:
        raise UnknownEvidence(f"matrix too large on {job_id}")
    names = []
    for values in combinations:
        expanded = name
        for key, value in zip(matrix, values, strict=True):
            if not isinstance(value, (str, int, float)) or "${{" in str(value):
                raise UnknownEvidence(f"dynamic matrix value on {job_id}")
            expanded = re.sub(
                r"\$\{\{\s*matrix\." + re.escape(key) + r"\s*\}\}", str(value), expanded
            )
        if "${{" in expanded:
            raise UnknownEvidence(f"unresolved job name: {expanded}")
        # Actions appends literal axis values when a display name was not authored.
        names.append(expanded if "name" in job else f"{expanded} ({', '.join(map(str, values))})")
    if len(names) != len(set(names)):
        raise UnknownEvidence(f"ambiguous duplicate matrix names on {job_id}")
    return names


def expected_jobs(
    evidence: Evidence,
    repo: str,
    path: str,
    ref: str,
    workflow: dict[str, Any],
    prefix: str = "",
    stack: tuple[str, ...] = (),
) -> set[str]:
    identity = f"{repo}/{path}@{ref}"
    if identity in stack or len(stack) >= 10:
        raise UnknownEvidence(f"recursive reusable workflow: {identity}")
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        raise UnknownEvidence(f"{identity}: missing jobs")
    names: set[str] = set()
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            raise UnknownEvidence(f"invalid job {job_id}")
        # Conditional ordinary jobs still report a skipped check; conditional
        # reusable calls can omit child checks, so do not guess their topology.
        uses = job.get("uses")
        for name in job_names(job_id, job):
            full_name = prefix + name
            if not uses:
                names.add(full_name)
                continue
            if job.get("if"):
                raise UnknownEvidence(f"conditional reusable call: {identity}:{job_id}")
            if uses.startswith("./.github/workflows/"):
                child_repo, child_path, child_ref = repo, uses[2:], ref
            else:
                match = re.fullmatch(
                    r"([^/]+/[^/]+)/(.github/workflows/[^@]+)@([0-9a-f]{40})", uses
                )
                if not match:
                    raise UnknownEvidence(f"unpinned/dynamic reusable workflow: {uses}")
                child_repo, child_path, child_ref = match.groups()
            child = evidence.workflow(child_repo, child_path, child_ref)
            if "workflow_call" not in (child.get("on") or {}):
                raise UnknownEvidence(f"{uses}: not a reusable workflow")
            names |= expected_jobs(
                evidence,
                child_repo,
                child_path,
                child_ref,
                child,
                full_name + " / ",
                (*stack, identity),
            )
    return names


def latest_checks(
    checks: list[dict[str, Any]], statuses: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for item in checks:
        key = item["name"]
        stamp = (item.get("started_at") or item.get("created_at") or "", item.get("id", 0))
        if key not in latest or stamp > latest[key]["order"]:
            latest[key] = {
                "order": stamp,
                "state": (
                    item.get("conclusion")
                    if item.get("status") == "completed"
                    else item.get("status")
                ),
                "url": item.get("html_url"),
                "app_id": (item.get("app") or {}).get("id"),
            }
    latest_statuses: dict[str, dict[str, Any]] = {}
    for item in statuses:
        key = item["context"]
        stamp = (item.get("created_at") or "", item.get("id", 0))
        if key in latest_statuses and stamp <= latest_statuses[key]["order"]:
            continue
        latest_statuses[key] = {
            "order": stamp,
            "state": item.get("state"),
            "url": item.get("target_url"),
            "app_id": None,
        }
    for key, item in latest_statuses.items():
        # A status cannot erase a failing check-run with the same context name.
        if key in latest:
            if item["state"] != "success":
                latest[key]["state"] = item["state"]
            continue
        latest[key] = item
    return latest


def adjudicate(
    expected: set[str],
    checks: list[dict[str, Any]],
    statuses: list[dict[str, Any]],
    suites: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    unknown: list[str],
    required: list[dict[str, Any]],
) -> dict[str, Any]:
    states = latest_checks(checks, statuses)
    missing = sorted(expected - states.keys())
    failures = []
    for name in sorted(expected & states.keys()):
        state = states[name]["state"]
        allowed = {"success", "skipped", "neutral"}
        if any(rule["context"] == name for rule in required):
            allowed = {"success"}
        if state not in allowed:
            failures.append({"name": name, **states[name]})
    for rule in required:
        app_id = rule.get("app_id")
        if (
            app_id not in (None, -1)
            and rule["context"] in states
            and states[rule["context"]]["app_id"] != app_id
        ):
            unknown.append(
                f"required app provenance not established: {rule['context']} app {app_id}"
            )
    startup = [
        {"kind": "suite", "id": suite.get("id"), "conclusion": suite.get("conclusion")}
        for suite in suites
        if suite.get("conclusion") in {"failure", "action_required", "startup_failure", "timed_out"}
    ]
    startup += [
        {"kind": "run", "id": run.get("id"), "conclusion": run.get("conclusion")}
        for run in runs
        if not run.get("jobs")
        and run.get("conclusion") in {"failure", "action_required", "startup_failure", "timed_out"}
    ]
    # Completed retries replace stale failed suites/runs of the SAME workflow.
    # Suite failures are retained conservatively when replacement cannot be tied.
    verdict = (
        "FAIL"
        if missing or failures or startup
        else "UNKNOWN" if unknown or not expected else "PASS"
    )
    return {
        "verdict": verdict,
        "expected_names": sorted(expected),
        "reported_names": sorted(states),
        "passing_names": sorted(
            name for name, value in states.items() if value["state"] == "success"
        ),
        "states": states,
        "missing_names": missing,
        "failing_checks": failures,
        "startup_failures": startup,
        "unknown": unknown,
    }


def collect(
    evidence: Evidence, repo: str, number: int, head: str, event: str, action: str
) -> dict[str, Any]:
    pr = evidence.one(f"repos/{repo}/pulls/{number}")
    if pr["head"]["sha"] != head:
        raise UnknownEvidence(f"head changed: requested {head}, observed {pr['head']['sha']}")
    branch, base = pr["base"]["ref"], pr["base"]["sha"]
    files = evidence.items(f"repos/{repo}/pulls/{number}/files?per_page=100")
    paths = sorted(
        {value["filename"] for value in files}
        | {value["previous_filename"] for value in files if value.get("previous_filename")}
    )
    unknown = []
    if len(files) != pr.get("changed_files") or len(files) >= 300:
        unknown.append(
            "changed-path evidence exceeds trustworthy Actions filter window or is incomplete"
        )
    checks = evidence.items(
        f"repos/{repo}/commits/{head}/check-runs?filter=all&per_page=100", "check_runs"
    )
    suites = evidence.items(
        f"repos/{repo}/commits/{head}/check-suites?per_page=100", "check_suites"
    )
    statuses = evidence.items(f"repos/{repo}/commits/{head}/statuses?per_page=100")
    workflows = evidence.one(f"repos/{repo}/contents/.github/workflows?ref={base}")
    required = []
    branch_info = evidence.one(f"repos/{repo}/branches/{quote(branch, safe='')}")
    if branch_info.get("protected"):
        protection = evidence.one(f"repos/{repo}/branches/{quote(branch, safe='')}/protection")
        settings = protection.get("required_status_checks") or {}
        required.extend(
            settings.get("checks") or [{"context": name} for name in settings.get("contexts", [])]
        )
    rules = evidence.items(f"repos/{repo}/rules/branches/{quote(branch, safe='')}")
    for rule in rules:
        if rule.get("type") == "required_status_checks":
            required.extend(rule.get("parameters", {}).get("required_status_checks", []))
        elif rule.get("type") == "workflows":
            unknown.append("ruleset requires workflow evidence; unsupported rule topology")
    for rule in required:
        if "integration_id" in rule:
            rule["app_id"] = rule["integration_id"]
    expected = {rule["context"] for rule in required}
    workflow_expected: set[str] = set()
    absences = []
    sources = []
    if not isinstance(workflows, list) or not workflows:
        unknown.append("workflow directory is empty or inaccessible")
        workflows = []
    for entry in workflows:
        path = entry["path"]
        if not path.endswith((".yml", ".yaml")):
            continue
        try:
            workflow = evidence.workflow(repo, path, base)
            source = {
                "repository": repo,
                "path": path,
                "ref": base,
                "blob_sha": entry["sha"],
                "document": workflow,
            }
            sources.append(source)
            if path in paths:
                unknown.append(
                    f"workflow changed on PR head: {path}; merge-ref topology needs adjudication"
                )
            applies, reason = event_applies(workflow, event, action, branch, paths)
            if not applies:
                absences.append({**source, "reason": reason, "triggers": workflow.get("on")})
                continue
            workflow_expected |= expected_jobs(evidence, repo, path, base, workflow)
        except UnknownEvidence as exc:
            unknown.append(f"{path}: {exc}")
    expected |= workflow_expected
    action_checks = [
        check for check in checks if (check.get("app") or {}).get("slug") == "github-actions"
    ]
    action_states = latest_checks(action_checks, [])
    for name in workflow_expected & latest_checks(checks, statuses).keys():
        if name not in action_states or action_states[name]["state"] not in {
            "success",
            "skipped",
            "neutral",
        }:
            unknown.append(
                f"GitHub Actions provenance/success not established for workflow job: {name}"
            )
    # Collect every Actions run and every job page for this head; no bounded
    # latest-N sample and no zero-job success inference.
    runs = evidence.items(
        f"repos/{repo}/actions/runs?head_sha={head}&per_page=100", "workflow_runs"
    )
    latest_runs: dict[tuple[Any, Any], dict[str, Any]] = {}
    for run in runs:
        if run.get("head_sha") != head:
            raise UnknownEvidence("Actions returned a run for a different head")
        key = (run.get("workflow_id"), run.get("event"))
        previous = latest_runs.get(key)
        if previous is None or (run.get("run_number", 0), run.get("run_attempt", 1)) > (
            previous.get("run_number", 0),
            previous.get("run_attempt", 1),
        ):
            latest_runs[key] = run
    for run in latest_runs.values():
        run["jobs"] = evidence.items(
            f"repos/{repo}/actions/runs/{run['id']}/jobs?filter=latest&per_page=100", "jobs"
        )
    after = evidence.one(f"repos/{repo}/pulls/{number}")
    if after["head"]["sha"] != head or after["base"]["sha"] != base:
        unknown.append("PR head or base changed during evidence collection")
    receipt = adjudicate(
        expected, checks, statuses, suites, list(latest_runs.values()), unknown, required
    )
    receipt.update(
        {
            "schema": "expected-check-receipt/v1",
            "repository": repo,
            "pr": number,
            "head": head,
            "base": base,
            "base_branch": branch,
            "event": event,
            "action": action,
            "event_source": "explicit caller context; Actions REST does not expose webhook action",
            "changed_paths": paths,
            "required_checks": required,
            "workflow_sources": sources,
            "legitimate_absences": absences,
            "check_runs": checks,
            "check_suites": suites,
            "workflow_runs": list(latest_runs.values()),
            "workflow_run_inventory": runs,
            "request_evidence": evidence.requests,
            "merge_authorization": False,
        }
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--head", required=True)
    parser.add_argument("--event", choices=["pull_request", "pull_request_target"], required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--presence-reporter", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    receipt = {
        "schema": "expected-check-receipt/v1",
        "repository": args.repo,
        "pr": args.pr,
        "head": args.head,
        "event": args.event,
        "action": args.action,
        "merge_authorization": False,
    }
    evidence = None
    try:
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo) or not re.fullmatch(
            r"[0-9a-f]{40}", args.head
        ):
            raise UnknownEvidence(
                "repository and full lowercase 40-character head SHA are required"
            )
        # Bind source identity before loading or requesting evidence so even
        # an import/discovery failure retains the incumbent being audited.
        source_digest = hashlib.sha256(args.presence_reporter.read_bytes()).hexdigest()
        receipt["presence_reporter"] = {
            "path": str(args.presence_reporter),
            "sha256": source_digest,
        }
        transport = load_presence_reporter(args.presence_reporter)
        evidence = Evidence(transport)
        receipt.update(collect(evidence, args.repo, args.pr, args.head, args.event, args.action))
        if hashlib.sha256(args.presence_reporter.read_bytes()).hexdigest() != source_digest:
            raise UnknownEvidence("incumbent reporter changed during evidence collection")
    except (Exception, SystemExit) as exc:
        receipt.update({"verdict": "UNKNOWN", "unknown": [str(exc)]})
        if evidence is not None:
            receipt["request_evidence"] = evidence.requests
    receipt["evidence_complete"] = receipt["verdict"] != "UNKNOWN" and not receipt.get("unknown")
    receipt["collected_at"] = datetime.now(UTC).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                key: receipt.get(key)
                for key in ["repository", "pr", "head", "verdict", "unknown", "missing_names"]
            }
        )
    )
    return {"PASS": 0, "FAIL": 1, "UNKNOWN": 2}[receipt["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
