#!/usr/bin/env python3
"""Extend the incumbent presence reporter with exact-head topology receipts.

The historical frequency/ratchet reporter remains useful as a warning, but is
not an event-specific completeness proof. This adapter reuses its paginated
transport, never copies its reference algorithm, and fails closed for topology
that it cannot statically establish. It does not authorize a merge.
"""

from __future__ import annotations

import argparse
import ast
import base64
import copy
import hashlib
import importlib.util
import itertools
import json
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

# Import only the trusted local pure resolver, never execute fetched helper code.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_client import GITHUB_API  # noqa: E402
from reusable_ci_scope import SelectionOptions, select_python_matrix, select_scenarios  # noqa: E402

# Audited legacy producer/helper from Workflows5656aa96 and PR3773 parent.
# Only this immutable contract may use the old Actions environment transcript.
LEGACY_PRODUCER_SHA256 = "97cccd183c1e6a8eed465c55c6cdfdee4c0611eca0074d41901d893ec5c6aad2"
LEGACY_HELPER_SHA256 = "ba653f7e90af12b4f8651b6fb8ecb629b2703a1ed161f96f447b31db8c224499"


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
        seen_ids = set()
        for page in self.pages(endpoint):
            values = page if key is None else page.get(key)
            if not isinstance(values, list):
                raise UnknownEvidence(f"{endpoint}: invalid list page")
            # A stable count alone cannot prove completeness: a moving page
            # boundary can repeat one object while silently omitting another.
            for value in values:
                if isinstance(value, dict) and value.get("id") is not None:
                    ident = value["id"]
                    if ident in seen_ids:
                        raise UnknownEvidence(f"{endpoint}: repeated object id {ident}")
                    seen_ids.add(ident)
            items.extend(values)
            if key is not None and "total_count" in page:
                page_total = page["total_count"]
                if type(page_total) is not int or page_total < 0:
                    raise UnknownEvidence(f"{endpoint}: invalid total_count")
                if total is not None and page_total != total:
                    raise UnknownEvidence(f"{endpoint}: total_count changed during pagination")
                total = page_total
        if total is not None and len(items) != total:
            raise UnknownEvidence(f"{endpoint}: enumerated {len(items)} of {total} items")
        return items

    def content(self, repo: str, path: str, ref: str) -> bytes:
        obj = self.one(f"repos/{repo}/contents/{path}?ref={quote(ref, safe='')}")
        if obj.get("encoding") != "base64":
            raise UnknownEvidence(f"{repo}/{path}: unsupported content encoding")
        return base64.b64decode(obj["content"])

    def job_log(self, repo: str, job_id: int) -> str:
        """Supplement the incumbent JSON transport with the producer's text log."""
        endpoint = f"repos/{repo}/actions/jobs/{job_id}/logs"
        proc = subprocess.run(
            ["gh", "api", endpoint], capture_output=True, text=True, timeout=60, check=False
        )
        if proc.returncode:
            raise UnknownEvidence(f"{endpoint}: producer log unavailable")
        self.requests.append(
            {"endpoint": endpoint, "sha256": hashlib.sha256(proc.stdout.encode()).hexdigest()}
        )
        return proc.stdout

    def job_receipts(
        self, repo: str, job_id: int, marker: str = "PYTHON_MATRIX_RECEIPT"
    ) -> list[dict[str, Any]]:
        result = []
        for line in self.job_log(repo, job_id).splitlines():
            match = re.fullmatch(r"(?:[0-9T:Z.+-]+\s+)?" + re.escape(marker) + r"=(\{.*\})", line)
            if match:
                result.append(json.loads(match[1]))
        return result

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
    if isinstance(types, str):
        types = [types]
    if not isinstance(types, list):
        raise UnknownEvidence("invalid types filter")
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


def actions_str(value: Any) -> str:
    """Render literal scalars with GitHub Actions boolean spelling."""
    return ("true" if value else "false") if isinstance(value, bool) else str(value)


def job_names(job_id: str, job: dict[str, Any]) -> list[str]:
    """Expand literal Cartesian or include-only matrices, rejecting transforms."""
    matrix = (job.get("strategy") or {}).get("matrix")
    name = str(job.get("name", job_id))
    if matrix is None:
        if "${{" in name:
            raise UnknownEvidence(f"dynamic job name: {name}")
        return [name]
    if not isinstance(matrix, dict) or "exclude" in matrix:
        raise UnknownEvidence(f"unsupported matrix on {job_id}")
    if set(matrix) == {"include"}:
        rows = matrix["include"]
        if (
            not isinstance(rows, list)
            or not rows
            or any(not isinstance(row, dict) or not row for row in rows)
        ):
            raise UnknownEvidence(f"invalid include-only matrix on {job_id}")
    else:
        if (
            not matrix
            or "include" in matrix
            or any(not isinstance(v, list) or not v for v in matrix.values())
        ):
            raise UnknownEvidence(f"dynamic/empty matrix on {job_id}")
        rows = [
            dict(zip(matrix, values, strict=True)) for values in itertools.product(*matrix.values())
        ]
    if len(rows) > 256:
        raise UnknownEvidence(f"matrix too large on {job_id}")
    names = []
    for row in rows:
        expanded = name
        for key, value in row.items():
            if (
                not isinstance(key, str)
                or not isinstance(value, (str, int, float))
                or "${{" in str(value)
            ):
                raise UnknownEvidence(f"dynamic matrix value on {job_id}")
            expanded = re.sub(
                r"\$\{\{\s*matrix\." + re.escape(key) + r"\s*\}\}",
                lambda _match, literal=value: actions_str(literal),
                expanded,
            )
        if "${{" in expanded:
            raise UnknownEvidence(f"unresolved job name: {expanded}")
        names.append(
            expanded
            if "name" in job
            else f"{expanded} ({', '.join(map(actions_str, row.values()))})"
        )
    if len(names) != len(set(names)):
        raise UnknownEvidence(f"ambiguous duplicate matrix names on {job_id}")
    return names


def legacy_python_receipt(log: str, run: dict[str, Any]) -> dict[str, Any]:
    """Extract checkout and input witnesses from the audited two-step producer."""
    lines = []
    for line in log.splitlines():
        match = re.fullmatch(r"[0-9T:Z.+-]+ (.*)", line)
        if match:
            lines.append(match[1])
    checkout = [
        i for i, line in enumerate(lines) if line == "[command]/usr/bin/git log -1 --format=%H"
    ]
    groups = [i for i, line in enumerate(lines) if line == "##[group]Run python - <<'PY'"]
    if len(checkout) != 1 or len(groups) != 1 or checkout[0] + 1 >= groups[0]:
        raise UnknownEvidence("legacy Python checkout/producer transcript ambiguous")
    helper_sha = lines[checkout[0] + 1]
    if not re.fullmatch(r"[0-9a-f]{40}", helper_sha):
        raise UnknownEvidence("legacy Python helper checkout SHA missing")
    group = lines[groups[0] + 1 :]
    try:
        group = group[: group.index("##[endgroup]")]
    except ValueError as exc:
        raise UnknownEvidence("legacy Python input group incomplete") from exc
    fields = {
        "WORKFLOW_NAME",
        "PYTHON_VERSIONS",
        "PYTHON_VERSION",
        "CHANGED_FILES_JSON",
        "FORCE_FULL",
    }
    values = {}
    for line in group:
        match = re.fullmatch(r"  ([A-Z_]+): (.*)", line)
        if match and match[1] in fields:
            if match[1] in values or "***" in match[2]:
                raise UnknownEvidence("legacy Python inputs ambiguous or masked")
            values[match[1]] = match[2]
    if set(values) != fields or values["FORCE_FULL"] not in {"true", "false"}:
        raise UnknownEvidence("legacy Python input witness incomplete")
    try:
        changed = json.loads(values["CHANGED_FILES_JSON"])
    except ValueError as exc:
        raise UnknownEvidence("legacy Python changed paths malformed") from exc
    return {
        "schema": "python-matrix-producer/v1",
        "repository": run["repository"]["full_name"],
        "head_sha": run["head_sha"],
        "run_id": run["id"],
        "run_attempt": run.get("run_attempt", 1),
        "helper_sha": helper_sha,
        "helper_sha256": LEGACY_HELPER_SHA256,
        "inputs": {
            "workflow_name": values["WORKFLOW_NAME"],
            "python_versions": values["PYTHON_VERSIONS"],
            "python_version": values["PYTHON_VERSION"],
            "changed_files": changed,
            "force_full": values["FORCE_FULL"] == "true",
        },
        "legacy_transcript": True,
    }


def bind_python_matrix(
    evidence: Evidence,
    repo: str,
    path: str,
    workflow: dict[str, Any],
    job: dict[str, Any],
    prefix: str,
    run: dict[str, Any] | None,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    """Recompute only the known source-bound producer; job successes are not inputs."""
    matrix = (job.get("strategy") or {}).get("matrix")
    if not isinstance(matrix, str) or "needs.select-scope.outputs.python_matrix" not in matrix:
        return job
    if (
        path != ".github/workflows/reusable-10-ci-python.yml"
        or repo != "stranske/Workflows"
        or run is None
    ):
        raise UnknownEvidence("Python matrix lacks supported executed producer")
    trusted = yaml.load((Path(__file__).parents[1] / path).read_bytes(), Loader=WorkflowLoader)[
        "jobs"
    ]["select-scope"]
    producer = workflow["jobs"].get("select-scope")
    producer_digest = hashlib.sha256(json.dumps(producer, sort_keys=True).encode()).hexdigest()
    legacy = producer_digest == LEGACY_PRODUCER_SHA256
    if producer != trusted and not legacy:
        raise UnknownEvidence("Python matrix producer source differs from supported contract")
    if matrix.strip() != "${{ fromJson(needs.select-scope.outputs.python_matrix) }}":
        raise UnknownEvidence("unsupported Python matrix expression")
    jobs = [j for j in run.get("jobs", []) if j.get("name") == prefix + "select reusable CI scope"]
    if (
        len(jobs) != 1
        or jobs[0].get("run_id") != run["id"]
        or jobs[0].get("run_attempt") != run.get("run_attempt", 1)
    ):
        raise UnknownEvidence("Python matrix producer job/run/attempt binding missing")
    producer_job = jobs[0]
    steps = [
        s for s in producer_job.get("steps", []) if s.get("name") == "Select Python version matrix"
    ]
    if len(steps) != 1 or steps[0].get("conclusion") != "success":
        raise UnknownEvidence("Python matrix producer step did not complete")
    if legacy:
        checkout_steps = [
            s for s in producer_job.get("steps", []) if s.get("name") == "Checkout Workflows helper"
        ]
        if len(checkout_steps) != 1 or checkout_steps[0].get("conclusion") != "success":
            raise UnknownEvidence("legacy Python helper checkout did not complete")
        receipts = [
            legacy_python_receipt(
                evidence.job_log(run["repository"]["full_name"], producer_job["id"]), run
            )
        ]
    else:
        receipts = evidence.job_receipts(run["repository"]["full_name"], producer_job["id"])
    if len(receipts) != 1:
        raise UnknownEvidence("missing/ambiguous Python matrix producer receipt")
    receipt = receipts[0]
    for key, expected in {
        "schema": "python-matrix-producer/v1",
        "repository": run["repository"]["full_name"],
        "run_id": run["id"],
        "run_attempt": run.get("run_attempt", 1),
        "head_sha": run["head_sha"],
    }.items():
        if receipt.get(key) != expected:
            raise UnknownEvidence(f"Python matrix receipt {key} mismatch")
    helper_sha = receipt.get("helper_sha", "")
    if not isinstance(helper_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", helper_sha):
        raise UnknownEvidence("Python matrix helper revision missing")
    helper_path = "scripts/reusable_ci_scope.py"
    trusted_helper = (Path(__file__).parent / "reusable_ci_scope.py").read_bytes()
    actual_helper = evidence.content(repo, helper_path, helper_sha)
    digest = hashlib.sha256(actual_helper).hexdigest()
    if (
        digest != LEGACY_HELPER_SHA256 if legacy else actual_helper != trusted_helper
    ) or receipt.get("helper_sha256") != digest:
        raise UnknownEvidence("executed Python helper differs from trusted pure resolver")
    arguments = receipt.get("inputs")
    keys = {"workflow_name", "python_versions", "python_version", "changed_files", "force_full"}
    if (
        not isinstance(arguments, dict)
        or set(arguments) != keys
        or arguments.get("workflow_name") != run.get("name")
    ):
        raise UnknownEvidence("Python producer inputs incomplete or workflow mismatch")
    # Literals must agree with the authored caller. Dynamic caller values are
    # witnessed by the immutable producer step, never inferred from child jobs.
    for source, argument in {
        "python-versions": "python_versions",
        "python-version": "python_version",
        "changed-files-json": "changed_files",
        "force-full": "force_full",
    }.items():
        raw = inputs.get(source)
        if isinstance(raw, str) and "${{" in raw:
            continue
        if source == "changed-files-json":
            try:
                raw = json.loads(raw or "[]")
            except (ValueError, TypeError) as exc:
                raise UnknownEvidence("invalid caller changed paths") from exc
        if source == "force-full":
            raw = raw in (True, "true")
        if raw != arguments[argument]:
            raise UnknownEvidence(f"Python producer input {source} differs from caller")
    try:
        selected = select_python_matrix(**arguments)
    except (TypeError, ValueError) as exc:
        raise UnknownEvidence(f"invalid Python producer inputs: {exc}") from exc
    if legacy:
        receipt["matrix"] = selected.matrix
        receipt["matrix_source"] = (
            "independent pure recomputation from exact legacy input transcript"
        )
    elif receipt.get("matrix") != selected.matrix:
        raise UnknownEvidence("Python producer matrix disagrees with independent recomputation")
    run.setdefault("matrix_evidence", []).append(
        {
            "producer_job_id": producer_job["id"],
            "producer_source_sha256": producer_digest,
            "receipt_source": (
                "audited legacy step transcript" if legacy else "producer-emitted log receipt"
            ),
            "helper_sha": helper_sha,
            "helper_sha256": digest,
            "receipt": receipt,
            "recomputed_matrix": selected.matrix,
        }
    )
    result = dict(job)
    result["strategy"] = {**job["strategy"], "matrix": selected.matrix}
    return result


SCENARIO_PATHS = {
    ".github/workflows/selftest-reusable-ci.yml",
    ".github/workflows/maint-62-integration-consumer.yml",
}


def root_topology_equivalent(base: dict[str, Any], head: dict[str, Any], path: str) -> bool:
    """Adjudicate only helper checkout pins and the observer's exact source addition."""
    if path not in SCENARIO_PATHS | {".github/workflows/pr-00-gate.yml"}:
        return False
    candidate = copy.deepcopy(head)
    for key, job in candidate.get("jobs", {}).items():
        old_job = base.get("jobs", {}).get(key, {})
        if job.get("uses", "").startswith("./.github/workflows/"):
            values = job.get("with", {})
            if values.get("workflows_ref") == "${{ github.sha }}":
                if "workflows_ref" in old_job.get("with", {}):
                    values["workflows_ref"] = old_job["with"]["workflows_ref"]
                else:
                    values.pop("workflows_ref")
        if key == "select-scenarios" and path in SCENARIO_PATHS:
            for step in job.get("steps", []):
                if step.get("name") != "Select scenarios":
                    continue
                env = step.get("env", {})
                for name, value in {
                    "PR_HEAD_SHA": "${{ github.event.pull_request.head.sha || github.sha }}",
                    "PR_BASE_SHA": "${{ github.event.pull_request.base.sha || '' }}",
                }.items():
                    if env.get(name) == value:
                        env.pop(name)
                code = step.get("run", "")
                code = code.replace(
                    "from scripts.reusable_ci_scope import SelectionOptions, describe_selection, select_scenarios, scenario_matrix_receipt",
                    "from scripts.reusable_ci_scope import SelectionOptions, describe_selection, select_scenarios",
                )
                observer = (
                    'print("SCENARIO_MATRIX_RECEIPT=" + json.dumps(scenario_matrix_receipt("'
                    + path
                    + '", changed_files, matrix, selected), sort_keys=True))\n'
                )
                step["run"] = code.replace(observer, "")
    return candidate == base


def scenario_source_matrix(producer: dict[str, Any]) -> dict[str, Any]:
    """Read only constant matrix assignments from trusted source, without executing it."""
    steps = [s for s in producer.get("steps", []) if s.get("name") == "Select scenarios"]
    if len(steps) != 1:
        raise UnknownEvidence("scenario selector step ambiguous")
    script = steps[0].get("run", "")
    lines = script.splitlines()
    if not lines or lines[0] != "python - <<'PY'" or lines[-1] != "PY":
        raise UnknownEvidence("unsupported scenario selector source")
    try:
        tree = ast.parse("\n".join(lines[1:-1]))
        values: dict[str, Any] = {}

        def literal(node):
            if isinstance(node, ast.Constant):
                return node.value
            if isinstance(node, ast.Name) and node.id in values:
                return values[node.id]
            if isinstance(node, ast.List):
                return [literal(v) for v in node.elts]
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                left, right = literal(node.left), literal(node.right)
                if isinstance(left, list) and isinstance(right, list):
                    return left + right
            if isinstance(node, ast.Dict):
                return {literal(k): literal(v) for k, v in zip(node.keys, node.values, strict=True)}
            raise ValueError("nonliteral scenario matrix")

        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                name = node.targets[0]
                if isinstance(name, ast.Name) and name.id in {"matrix", "common_scope"}:
                    values[name.id] = literal(node.value)
        return values["matrix"]
    except (SyntaxError, KeyError, ValueError, TypeError) as exc:
        raise UnknownEvidence("scenario matrix source is not constant") from exc


def bind_scenario_matrix(evidence, repo, path, workflow, job, run):
    """Replay witnessed scenario selection independently of reported child jobs."""
    matrix = (job.get("strategy") or {}).get("matrix")
    if matrix != "${{ fromJson(needs.select-scenarios.outputs.matrix) }}":
        return job
    if repo != "stranske/Workflows" or path not in SCENARIO_PATHS or run is None:
        raise UnknownEvidence("scenario matrix lacks supported producer")
    trusted = yaml.load((Path(__file__).parents[1] / path).read_bytes(), Loader=WorkflowLoader)
    producer = workflow["jobs"].get("select-scenarios")
    # Base roots are allowed only through the complete observer/pin equivalence check.
    if producer != trusted["jobs"]["select-scenarios"] and not root_topology_equivalent(
        workflow, trusted, path
    ):
        raise UnknownEvidence("scenario producer differs from trusted source")
    jobs = [
        j for j in run.get("jobs", []) if j.get("name") == producer.get("name", "select-scenarios")
    ]
    if (
        len(jobs) != 1
        or jobs[0].get("run_id") != run["id"]
        or jobs[0].get("run_attempt") != run.get("run_attempt", 1)
    ):
        raise UnknownEvidence("scenario producer run/attempt binding missing")
    steps = [s for s in jobs[0].get("steps", []) if s.get("name") == "Select scenarios"]
    if len(steps) != 1 or steps[0].get("conclusion") != "success":
        raise UnknownEvidence("scenario producer did not execute")
    receipts = evidence.job_receipts(
        run["repository"]["full_name"], jobs[0]["id"], "SCENARIO_MATRIX_RECEIPT"
    )
    if len(receipts) != 1:
        raise UnknownEvidence("missing/ambiguous scenario producer receipt")
    receipt = receipts[0]
    for key, value in {
        "schema": "scenario-matrix-producer/v1",
        "repository": run["repository"]["full_name"],
        "run_id": run["id"],
        "run_attempt": run.get("run_attempt", 1),
        "head_sha": run["head_sha"],
        "workflow_path": path,
    }.items():
        if receipt.get(key) != value:
            raise UnknownEvidence(f"scenario producer {key} mismatch")
    helper_sha, base_sha = receipt.get("helper_sha"), receipt.get("base_sha")
    if any(
        not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha)
        for sha in (helper_sha, base_sha)
    ):
        raise UnknownEvidence("scenario immutable checkout/base missing")
    helper = evidence.content(repo, "scripts/reusable_ci_scope.py", helper_sha)
    actual_workflow = evidence.content(repo, path, helper_sha)
    if helper != (Path(__file__).parent / "reusable_ci_scope.py").read_bytes() or hashlib.sha256(
        helper
    ).hexdigest() != receipt.get("helper_sha256"):
        raise UnknownEvidence("scenario executed helper differs from trusted resolver")
    if (
        hashlib.sha256(actual_workflow).hexdigest() != receipt.get("workflow_sha256")
        or yaml.load(actual_workflow, Loader=WorkflowLoader) != trusted
    ):
        raise UnknownEvidence("scenario executed workflow differs from trusted producer")
    args = receipt.get("inputs")
    expected_matrix = scenario_source_matrix(trusted["jobs"]["select-scenarios"])
    if (
        not isinstance(args, dict)
        or set(args) != {"workflow_name", "changed_files", "full_matrix", "force_full"}
        or args["full_matrix"] != expected_matrix
        or args["workflow_name"] != Path(path).stem
        or not isinstance(args["changed_files"], list)
        or any(not isinstance(value, str) for value in args["changed_files"])
        or len(args["changed_files"]) != len(set(args["changed_files"]))
    ):
        raise UnknownEvidence("scenario inputs differ from authored matrix")
    if run.get("event") != "pull_request" or args["force_full"] is not False:
        raise UnknownEvidence("unsupported scenario event/force-full evidence")
    comparison = evidence.one(f"repos/{repo}/compare/{base_sha}...{helper_sha}")
    files = comparison.get("files")
    if (
        comparison.get("merge_base_commit", {}).get("sha") != base_sha
        or not isinstance(files, list)
        or len(files) >= 300
        or sorted(args["changed_files"]) != sorted(f["filename"] for f in files)
    ):
        raise UnknownEvidence("scenario changed-path witness incomplete or mismatched")
    selected = select_scenarios(
        args["workflow_name"],
        args["changed_files"],
        expected_matrix,
        SelectionOptions(force_full=False),
    )
    if receipt.get("matrix") != selected.matrix:
        raise UnknownEvidence("scenario matrix disagrees with independent recomputation")
    run.setdefault("matrix_evidence", []).append(
        {"producer_job_id": jobs[0]["id"], "receipt": receipt, "recomputed_matrix": selected.matrix}
    )
    result = dict(job)
    result["strategy"] = {**job["strategy"], "matrix": selected.matrix}
    return result


def expected_jobs(
    evidence: Evidence,
    repo: str,
    path: str,
    ref: str,
    workflow: dict[str, Any],
    prefix: str = "",
    stack: tuple[str, ...] = (),
    run: dict[str, Any] | None = None,
    inputs: dict[str, Any] | None = None,
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
        job = bind_job_inputs(job, inputs or {})
        job = bind_scenario_matrix(evidence, repo, path, workflow, job, run)
        job = bind_python_matrix(evidence, repo, path, workflow, job, prefix, run, inputs or {})
        uses = job.get("uses")
        for name in job_names(job_id, job):
            full_name = prefix + name
            if not uses:
                if full_name in names:
                    raise UnknownEvidence(f"duplicate expected job name in {identity}: {full_name}")
                names.add(full_name)
                continue
            if job.get("if") and run is None:
                raise UnknownEvidence(f"conditional reusable call: {identity}:{job_id}")
            if run is not None:
                skipped = [
                    item
                    for item in run.get("jobs", [])
                    if item.get("name") == full_name
                    and item.get("conclusion") == "skipped"
                    and item.get("check_run_url")
                ]
                if len(skipped) == 1:
                    if full_name in names:
                        raise UnknownEvidence(
                            f"duplicate expected job name in {identity}: {full_name}"
                        )
                    names.add(full_name)
                    run.setdefault("reusable_absences", []).append(
                        {
                            "caller": identity,
                            "job": job_id,
                            "uses": uses,
                            "check_run_url": skipped[0]["check_run_url"],
                            "reason": "GitHub emitted the skipped caller job on this exact run",
                        }
                    )
                    continue
            if uses.startswith("./.github/workflows/"):
                child_repo, child_path, child_ref = repo, uses[2:], ref
            else:
                match = re.fullmatch(r"([^/]+/[^/]+)/(.github/workflows/[^@]+)@([^\s]+)", uses)
                if not match:
                    raise UnknownEvidence(f"unpinned/dynamic reusable workflow: {uses}")
                child_repo, child_path, child_ref = match.groups()
            if run is not None:
                source = f"{child_repo}/{child_path}@"
                refs = [
                    item
                    for item in run.get("referenced_workflows", [])
                    if str(item.get("path", "")).startswith(source)
                    and (uses.startswith("./") or item.get("path") == uses)
                ]
                shas = {item.get("sha") for item in refs}
                if len(shas) != 1 or not re.fullmatch(r"[0-9a-f]{40}", str(next(iter(shas), ""))):
                    raise UnknownEvidence(f"ambiguous/missing executed reusable SHA: {uses}")
                resolved = next(iter(shas))
                if (
                    not uses.startswith("./")
                    and re.fullmatch(r"[0-9a-f]{40}", child_ref)
                    and resolved != child_ref
                ):
                    raise UnknownEvidence(
                        f"executed reusable SHA differs from pinned source: {uses}"
                    )
                if job.get("if") and not any(
                    item.get("name", "").startswith(full_name + " / ")
                    for item in run.get("jobs", [])
                ):
                    raise UnknownEvidence(
                        f"conditional reusable call lacks execution/skip evidence: {uses}"
                    )
                child_ref = resolved
            elif not re.fullmatch(r"[0-9a-f]{40}", child_ref):
                raise UnknownEvidence(f"unpinned/dynamic reusable workflow: {uses}")
            child = evidence.workflow(child_repo, child_path, child_ref)
            if "workflow_call" not in (child.get("on") or {}):
                raise UnknownEvidence(f"{uses}: not a reusable workflow")
            triggers = child.get("on")
            definitions = (
                (triggers.get("workflow_call") or {}) if isinstance(triggers, dict) else {}
            )
            child_inputs = {
                key: value.get("default")
                for key, value in (definitions.get("inputs") or {}).items()
                if isinstance(value, dict) and "default" in value
            }
            child_inputs.update(job.get("with") or {})
            children = expected_jobs(
                evidence,
                child_repo,
                child_path,
                child_ref,
                child,
                full_name + " / ",
                (*stack, identity),
                run,
                child_inputs,
            )
            duplicates = names & children
            if duplicates:
                raise UnknownEvidence(
                    f"duplicate expected child names in {identity}: {sorted(duplicates)}"
                )
            names |= children
    return names


def bind_job_inputs(job: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    """Resolve only literal caller inputs, never arbitrary Actions expressions."""

    def bind(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: bind(item) for key, item in value.items()}
        if isinstance(value, list):
            return [bind(item) for item in value]
        if not isinstance(value, str):
            return value
        match = re.fullmatch(r"\$\{\{\s*fromJSON\(inputs\.([\w-]+)\)\s*\}\}", value)
        if match:
            raw = inputs.get(match[1])
            if not isinstance(raw, str) or "${{" in raw:
                raise UnknownEvidence(f"nonliteral matrix input: {match[1]}")
            try:
                return json.loads(raw)
            except ValueError as exc:
                raise UnknownEvidence(f"invalid JSON matrix input: {match[1]}") from exc

        def replace(match: re.Match[str]) -> str:
            raw = inputs.get(match[1])
            if raw is None or isinstance(raw, (list, dict)) or "${{" in str(raw):
                raise UnknownEvidence(f"nonliteral job input: {match[1]}")
            return actions_str(raw)

        return re.sub(r"\$\{\{\s*inputs\.([\w-]+)\s*\}\}", replace, value)

    # Conditions and steps may intentionally use runtime inputs; only the
    # display-name/matrix topology and nested caller literals need binding.
    result = dict(job)
    for key in ("name", "strategy"):
        if key in result:
            result[key] = bind(result[key])
    return result


def gate_status_provenance(
    repo: str,
    head: str,
    statuses: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    suites: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    platform_app: dict[str, Any],
    platform_bot: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    """Bind the latest Actions Gate status; REST statuses have no app foreign key.

    Only the built-in github.com publisher is supported. All inputs come from
    authenticated API reads in collect(); URL text and raw caller app_id fields
    never establish identity. Unknown publishers and incomplete attempts stay
    unbound. The status itself must exist and succeed independently of the job.
    """
    owner = platform_app.get("owner") or {}
    bot = {"id": 41898282, "login": "github-actions[bot]", "type": "Bot"}
    if (
        platform_app.get("id") != 15368
        or platform_app.get("slug") != "github-actions"
        or owner.get("id") != 9919
        or owner.get("login") != "github"
        or owner.get("type") != "Organization"
        or any(platform_bot.get(key) != value for key, value in bot.items())
    ):
        return {}
    candidates = [item for item in statuses if item.get("context") == "Gate / gate"]
    if not candidates:
        return {}
    status = max(candidates, key=lambda item: (item.get("created_at") or "", item.get("id", 0)))
    creator = status.get("creator") or {}
    if (
        status.get("state") != "success"
        or type(status.get("id")) is not int
        or status["id"] < 1
        or status.get("url") != f"{GITHUB_API}/repos/{repo}/statuses/{head}"
        or any(creator.get(key) != value for key, value in bot.items())
    ):
        return {}

    def instant(value: Any) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo is not None else None
        except (AttributeError, TypeError, ValueError):
            return None

    created = instant(status.get("created_at"))
    matches = []
    for run in runs:
        if (
            (run.get("repository") or {}).get("full_name") != repo
            or run.get("head_sha") != head
            or run.get("event") != "pull_request"
            or run.get("path") != ".github/workflows/pr-00-gate.yml"
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
            or any(
                type(run.get(key)) is not int or run[key] < 1
                for key in ("id", "check_suite_id", "run_attempt")
            )
            or run["run_attempt"] < 1
            or status.get("target_url") != f"https://github.com/{repo}/actions/runs/{run.get('id')}"
        ):
            continue
        bound_suites = [
            suite
            for suite in suites
            if suite.get("id") == run.get("check_suite_id")
            and suite.get("head_sha") == head
            and (suite.get("app") or {}).get("id") == 15368
            and (suite.get("app") or {}).get("slug") == "github-actions"
        ]
        if len(bound_suites) != 1:
            continue
        for job in run.get("jobs", []):
            if (
                type(job.get("id")) is not int
                or job["id"] < 1
                or job.get("name") not in {"summary", "gate-summary"}
                or job.get("run_id") != run.get("id")
                or job.get("run_attempt") != run["run_attempt"]
                or job.get("head_sha") != head
                or job.get("status") != "completed"
                or job.get("conclusion") != "success"
                or job.get("check_run_url")
                != f"{GITHUB_API}/repos/{repo}/check-runs/{job.get('id')}"
            ):
                continue
            bound_checks = [
                check
                for check in checks
                if check.get("id") == job.get("id")
                and check.get("head_sha") == head
                and (check.get("check_suite") or {}).get("id") == run.get("check_suite_id")
                and (check.get("app") or {}).get("id") == 15368
                and (check.get("app") or {}).get("slug") == "github-actions"
                and check.get("status") == "completed"
                and check.get("conclusion") == "success"
            ]
            if len(bound_checks) != 1:
                continue
            for step in job.get("steps", []):
                start, end = instant(step.get("started_at")), instant(step.get("completed_at"))
                if (
                    step.get("name") == "Report Gate commit status"
                    and step.get("status") == "completed"
                    and step.get("conclusion") == "success"
                    and created is not None
                    and start is not None
                    and end is not None
                    and start <= created <= end
                ):
                    matches.append(
                        {
                            "status_id": status["id"],
                            "app_id": 15368,
                            "publisher_id": bot["id"],
                            "repository": repo,
                            "head": head,
                            "run_id": run["id"],
                            "run_attempt": run["run_attempt"],
                            "suite_id": run["check_suite_id"],
                            "job_id": job["id"],
                            "report_started_at": step["started_at"],
                            "report_completed_at": step["completed_at"],
                        }
                    )
    return {status["id"]: matches[0]} if len(matches) == 1 else {}


def latest_checks(
    checks: list[dict[str, Any]],
    statuses: list[dict[str, Any]],
    status_provenance: dict[int, dict[str, Any]] | None = None,
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
            "app_id": (status_provenance or {}).get(item.get("id"), {}).get("app_id"),
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
    applicable_suite_ids: set[Any] | None = None,
    status_provenance: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    states = latest_checks(checks, statuses, status_provenance)
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
    startup = []
    for suite in suites:
        if suite.get("conclusion") not in {
            "failure",
            "action_required",
            "startup_failure",
            "timed_out",
        }:
            continue
        suite_id = suite.get("id")
        if applicable_suite_ids is not None and suite_id not in applicable_suite_ids:
            continue
        if suite.get("latest_check_runs_count", 1) != 0:
            continue
        startup.append(
            {"kind": "suite", "id": suite.get("id"), "conclusion": suite.get("conclusion")}
        )
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


def complete_workflow_runs(
    evidence: Evidence, repo: str, head: str, event: str, suites: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Reconcile head-filtered search with every exact-head Actions suite.

    GitHub can omit historical merged-head runs from its head search while
    retaining their suites and suite-filtered run metadata. Neither successful
    checks nor an empty search prove that those workflows did not execute.
    """
    runs = evidence.items(
        f"repos/{repo}/actions/runs?head_sha={head}&event={quote(event)}&per_page=100",
        "workflow_runs",
    )
    recovered = []
    by_id = {}
    for run in runs:
        if run.get("head_sha") != head or run.get("event") != event:
            raise UnknownEvidence("Actions returned a run for a different head or event")
        by_id[run["id"]] = run
    known_suites = {run.get("check_suite_id") for run in runs}
    for suite in suites:
        if (suite.get("app") or {}).get("slug") != "github-actions":
            continue
        suite_id = suite.get("id")
        if not isinstance(suite_id, int) or suite.get("head_sha") != head:
            raise UnknownEvidence("Actions suite identity/head binding missing")
        if suite_id in known_suites:
            continue
        candidates = evidence.items(
            f"repos/{repo}/actions/runs?check_suite_id={suite_id}&per_page=100",
            "workflow_runs",
        )
        if not candidates:
            raise UnknownEvidence(f"Actions suite {suite_id} has no discoverable run")
        for run in candidates:
            if (
                run.get("check_suite_id") != suite_id
                or run.get("head_sha") != head
                or not isinstance(run.get("event"), str)
            ):
                raise UnknownEvidence(f"Actions suite {suite_id} run identity/head/event mismatch")
            recovered.append(
                {
                    "suite_id": suite_id,
                    "run_id": run["id"],
                    "event": run["event"],
                    "included": run["event"] == event,
                    "source": "complete exact-head suite inventory and paginated suite lookup",
                }
            )
            if run["event"] != event:
                continue
            if run["id"] in by_id and by_id[run["id"]] != run:
                raise UnknownEvidence("Actions run metadata disagrees across inventory sources")
            by_id[run["id"]] = run
    return list(by_id.values()), recovered


def paths_from_files(files: list[dict[str, Any]]) -> list[str]:
    """Normalize the complete path inventory, including both sides of renames."""
    return sorted(
        {value["filename"] for value in files}
        | {value["previous_filename"] for value in files if value.get("previous_filename")}
    )


def collect(
    evidence: Evidence, repo: str, number: int, head: str, event: str, action: str
) -> dict[str, Any]:
    pr = evidence.one(f"repos/{repo}/pulls/{number}")
    if pr["head"]["sha"] != head:
        raise UnknownEvidence(f"head changed: requested {head}, observed {pr['head']['sha']}")
    branch, base = pr["base"]["ref"], pr["base"]["sha"]
    files = evidence.items(f"repos/{repo}/pulls/{number}/files?per_page=100")
    paths = paths_from_files(files)
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
    # The endpoint alone is not a head witness. Validate every returned object,
    # including advisory checks, stale attempts and suites from other apps.
    for kind, inventory in (("check run", checks), ("check suite", suites)):
        for item in inventory:
            if item.get("head_sha") != head:
                raise UnknownEvidence(
                    f"{kind} {item.get('id')}: full head binding missing/mismatched"
                )
    statuses = evidence.items(f"repos/{repo}/commits/{head}/statuses?per_page=100")
    workflows = evidence.one(f"repos/{repo}/contents/.github/workflows?ref={base}")
    # Collect every Actions run and every job page for this head; no bounded
    # latest-N sample and no zero-job success inference.
    runs, recovered_runs = complete_workflow_runs(evidence, repo, head, event, suites)
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
    required = []
    branch_info = evidence.one(f"repos/{repo}/branches/{quote(branch, safe='')}")
    if branch_info.get("protected"):
        protection_endpoint = f"repos/{repo}/branches/{quote(branch, safe='')}/protection"
        try:
            protection = evidence.one(protection_endpoint)
        except UnknownEvidence as exc:
            # `protected` also covers rulesets. Their requirements are read
            # independently below; the classic endpoint explicitly reports
            # "Branch not protected" when no classic rule exists. Generic
            # 404s (including permission-masked ones) remain UNKNOWN.
            if "gh: Branch not protected (HTTP 404)" not in str(exc):
                raise
            protection = {}
            evidence.requests.append(
                {
                    "endpoint": protection_endpoint,
                    "classic_protection": "absent",
                    "evidence": str(exc),
                }
            )
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
    job_provenance: dict[str, set[str]] = {}
    absences = []
    sources = []
    if not isinstance(workflows, list) or not workflows:
        unknown.append("workflow directory is empty or inaccessible")
        workflows = []
    known_paths = {entry["path"] for entry in workflows}
    for changed in paths:
        if (
            changed.startswith(".github/workflows/")
            and changed.endswith((".yml", ".yaml"))
            and changed not in known_paths
        ):
            unknown.append(
                f"new workflow on PR head: {changed}; merge-ref topology needs adjudication"
            )
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
            applies, reason = event_applies(workflow, event, action, branch, paths)
            if path in paths:
                head_workflow = evidence.workflow(repo, path, head)
                head_applies, _ = event_applies(head_workflow, event, action, branch, paths)
                if applies or head_applies:
                    if root_topology_equivalent(workflow, head_workflow, path):
                        source["head_topology_ref"] = head
                        source["head_document"] = head_workflow
                        source["topology_adjudication"] = (
                            "only exact helper pin / observer additions"
                        )
                    else:
                        unknown.append(
                            f"workflow changed on PR head: {path}; merge-ref topology needs adjudication"
                        )
                else:
                    source["head_absence_ref"] = head
                    source["head_document"] = head_workflow
            if not applies:
                absences.append({**source, "reason": reason, "triggers": workflow.get("on")})
                continue
            source_key = f"{repo}/{path}@{base}"
            run_matches = [run for run in latest_runs.values() if run.get("path") == path]
            bound_run = run_matches[0] if len(run_matches) == 1 else None
            for job_name in expected_jobs(evidence, repo, path, base, workflow, run=bound_run):
                job_provenance.setdefault(job_name, set()).add(source_key)
        except UnknownEvidence as exc:
            unknown.append(f"{path}: {exc}")
    identity_evidence = []
    for job_name, origins in job_provenance.items():
        if len(origins) <= 1:
            continue
        claims = []
        for origin in sorted(origins):
            source_path = origin.split("/", 2)[2].rsplit("@", 1)[0]
            matched_runs = [run for run in latest_runs.values() if run.get("path") == source_path]
            if len(matched_runs) != 1:
                unknown.append(
                    f"duplicate expected check identity {job_name!r}: missing run for {origin}"
                )
                continue
            jobs = [job for job in matched_runs[0]["jobs"] if job.get("name") == job_name]
            if len(jobs) != 1:
                unknown.append(
                    f"duplicate expected check identity {job_name!r}: ambiguous/missing job for {origin}"
                )
                continue
            job = jobs[0]
            check_matches = [
                check
                for check in checks
                if check.get("url") == job.get("check_run_url")
                and check.get("name") == job_name
                and check.get("head_sha") == head
                and (check.get("app") or {}).get("slug") == "github-actions"
            ]
            if len(check_matches) != 1 or check_matches[0].get("conclusion") not in {
                "success",
                "skipped",
                "neutral",
            }:
                unknown.append(
                    f"duplicate expected check identity {job_name!r}: independent success unproven for {origin}"
                )
                continue
            claims.append(
                {
                    "source": origin,
                    "run_id": matched_runs[0]["id"],
                    "job_id": job.get("id"),
                    "check_run_url": job.get("check_run_url"),
                    "conclusion": check_matches[0]["conclusion"],
                }
            )
        if len(claims) == len(origins):
            identity_evidence.append({"name": job_name, "independent_claims": claims})
    workflow_expected = set(job_provenance)
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
    applicable_suite_ids = {
        run.get("check_suite_id")
        for run in latest_runs.values()
        if run.get("check_suite_id") is not None
    }
    status_provenance = {}
    if any(
        rule.get("context") == "Gate / gate" and rule.get("app_id") == 15368 for rule in required
    ):
        try:
            status_provenance = gate_status_provenance(
                repo,
                head,
                statuses,
                list(latest_runs.values()),
                suites,
                checks,
                evidence.one("apps/github-actions"),
                evidence.one("users/github-actions[bot]"),
            )
        except UnknownEvidence as exc:
            unknown.append(f"Actions status publisher discovery unavailable: {exc}")
    # Re-enumerate paths before the closing PR snapshot. Equal commit SHAs
    # alone do not bind a retargeted branch or a delayed/truncated files API.
    after_files = evidence.items(f"repos/{repo}/pulls/{number}/files?per_page=100")
    after_paths = paths_from_files(after_files)
    after = evidence.one(f"repos/{repo}/pulls/{number}")
    if after["head"]["sha"] != head or after["base"]["sha"] != base:
        unknown.append("PR head or base changed during evidence collection")
    if after["base"]["ref"] != branch:
        unknown.append("PR base branch changed during evidence collection")
    if after.get("changed_files") != pr.get("changed_files"):
        unknown.append("PR changed-path count changed during evidence collection")
    if after_paths != paths or len(after_files) != len(files):
        unknown.append("changed-path inventory changed during evidence collection")
    receipt = adjudicate(
        expected,
        checks,
        statuses,
        suites,
        list(latest_runs.values()),
        unknown,
        required,
        applicable_suite_ids,
        status_provenance,
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
            "closing_context": {
                "head": after["head"]["sha"],
                "base": after["base"]["sha"],
                "base_branch": after["base"]["ref"],
                "changed_file_count": after.get("changed_files"),
                "enumerated_file_count": len(after_files),
                "changed_paths": after_paths,
            },
            "required_checks": required,
            "status_provenance": list(status_provenance.values()),
            "duplicate_identity_evidence": identity_evidence,
            "workflow_sources": sources,
            "legitimate_absences": absences,
            "check_runs": checks,
            "check_suites": suites,
            "workflow_runs": list(latest_runs.values()),
            "workflow_run_inventory": runs,
            "workflow_run_inventory_recovery": recovered_runs,
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
