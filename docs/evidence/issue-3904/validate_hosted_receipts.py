"""Independent, read-only reconciliation of a retained hosted comparison archive.

Usage: python validate_hosted_receipts.py ARCHIVE ARTIFACT_METADATA
Metadata is the unmodified Actions artifacts API response for the run.
"""

import ast
import hashlib
import json
import math
import re
import subprocess
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

from defusedxml import ElementTree

if not __debug__:
    raise SystemExit("Optimized execution refuses validation before accepting any archive")

REPO = Path(__file__).resolve().parents[3]
SUITES = (
    "tests/scripts/test_pr_verifier_delivery_destinations.py",
    "tests/scripts/test_pr_verifier_prompt_coverage.py",
    "tests/scripts/test_pr_verifier_body_overall_integration.py",
)
VERIFIER = "scripts/langchain/pr_verifier.py"
PAIR = {
    "baseline": "00f43f81e51c4f8b9a057ac51f7e3c2d870d7769",
    "candidate": "8c0afc3ef0263cf85949b6167435ceabed5dd2a3",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(["git", "-C", str(REPO), *args])


def validate(archive, metadata):
    """Reconcile a runtime archive with its retained GitHub metadata and Git sources."""
    raw = archive.read_bytes()
    archive_hash = digest(raw)
    matching = [a for a in metadata["artifacts"] if a["digest"] == f"sha256:{archive_hash}"]
    assert len(matching) == 1, "archive differs from GitHub artifact digest"
    artifact = matching[0]
    with zipfile.ZipFile(archive) as z:
        assert len(z.namelist()) == len(set(z.namelist())), "duplicate archive members"
        members = {name: z.read(name) for name in z.namelist() if not name.endswith("/")}
    required_members = {"result.json", "manifest.json"}
    for arm in PAIR:
        required_members.update((f"{arm}/pytest-junit.xml", f"{arm}/coverage.json", f"{arm}.log"))
    missing_members = sorted(required_members - members.keys())
    if missing_members:
        raise ValueError(f"missing required archive members: {', '.join(missing_members)}")
    result, manifest = (json.loads(members[name]) for name in ("result.json", "manifest.json"))
    workflow_sha = manifest.get("workflow_sha")
    if not isinstance(workflow_sha, str) or not re.fullmatch(
        r"(?:[0-9a-f]{40}|[0-9a-f]{64})", workflow_sha
    ):
        raise ValueError("workflow_sha must be a full lowercase 40- or 64-character commit ID")
    runtime = result.get("python")
    runtime_match = (
        re.fullmatch(r"([0-9]+\.[0-9]+)\.[0-9]+(?: [^\r\n]+)?", runtime)
        if isinstance(runtime, str)
        else None
    )
    if runtime_match is None:
        raise ValueError("Python runtime must be a full major.minor.patch version")
    run_id = artifact["workflow_run"]["id"]
    if artifact.get("name") != f"verifier-runtime-{runtime_match[1]}-{run_id}":
        raise ValueError("artifact name does not match recorded Python runtime and workflow run")
    phase_prefixes = tuple(f"{arm}/phase-clocks/" for arm in PAIR)
    if "phase_plugin_sha256" not in result and (
        any("phases" in result["arms"][arm] for arm in PAIR)
        or any(path.startswith(phase_prefixes) for path in members)
    ):
        raise ValueError("phase measurements require phase_plugin_sha256")
    if "phase_plugin_sha256" in result:
        for arm in PAIR:
            phases = result["arms"][arm].get("phases")
            if (
                not isinstance(phases, dict)
                or phases.get("available") is not True
                or phases.get("gaps") != []
                or not isinstance(phases.get("processes"), dict)
                or set(phases["processes"]) != {"controller", "gw0", "gw1", "gw2", "gw3"}
            ):
                raise ValueError(
                    f"{arm} requires complete available phase measurements declared by "
                    "phase_plugin_sha256"
                )
    assert result["manifest"] == manifest
    assert manifest["workflow_sha"] == artifact["workflow_run"]["head_sha"]
    assert manifest["dependency_lock"] == "candidate/requirements.lock"
    for path, key in (
        ("scripts/measure_verifier_runtime.py", "harness_sha256"),
        (".github/workflows/maint-88-verifier-runtime-comparison.yml", "workflow_sha256"),
    ):
        assert digest(git("show", f'{manifest["workflow_sha"]}:{path}')) == manifest[key]
    for arm, ref in PAIR.items():
        source = manifest["arms"][arm]
        assert source["commit"] == ref
        assert source["tree"] == git("rev-parse", f"{ref}^{{tree}}").decode().strip()
        assert set(source["sha256"]) == {*SUITES, VERIFIER, "pyproject.toml", "requirements.lock"}
        for path, expected in source["sha256"].items():
            assert (
                digest(git("show", f"{ref}:{path}")) == expected
            ), f"source mismatch: {arm}/{path}"
        for boundary in ("before", "after"):
            assert result["source_integrity"][boundary]["verified"] is True
            assert result["source_integrity"][boundary]["sha256"][arm] == source["sha256"]
    for path in (VERIFIER, "pyproject.toml", "requirements.lock"):
        assert (
            manifest["arms"]["baseline"]["sha256"][path]
            == manifest["arms"]["candidate"]["sha256"][path]
        )
    assert result["source_integrity"]["verified"] is True
    assert result["packages_unchanged"] is True
    missing = []
    for path, expected in result["artifact_sha256"].items():
        if path not in members:
            assert path in {
                f"{arm}/docs/evidence/issue-3743/runtime-probes/{name}.log"
                for arm in PAIR
                for name in PAIR
            }, f"missing required hash member: {path}"
            missing.append(path)
        else:
            assert digest(members[path]) == expected, f"uploaded hash mismatch: {path}"
    if "phase_plugin_sha256" in result:
        source = ast.parse(
            git("show", f'{manifest["workflow_sha"]}:scripts/measure_verifier_runtime.py')
        )
        plugin = next(
            ast.literal_eval(node.value)
            for node in source.body
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "PHASE_PLUGIN" for t in node.targets)
        )
        assert digest(plugin.encode()) == result["phase_plugin_sha256"]
    outcomes, coverage, phases = {}, {}, {}
    for arm in PAIR:
        row = result["arms"][arm]
        assert row["exit_code"] == 0
        assert (
            type(row["wall_seconds"]) in (int, float)
            and math.isfinite(row["wall_seconds"])
            and row["wall_seconds"] >= 0
        )
        for name in ("coverage.json", "pytest-junit.xml"):
            assert f"{arm}/{name}" in result["artifact_sha256"]
        assert f"{arm}.log" in result["artifact_sha256"]
        root = ElementTree.fromstring(members[f"{arm}/pytest-junit.xml"])
        groups = defaultdict(
            lambda: {
                "cases": 0,
                "passed": 0,
                "failures": 0,
                "errors": 0,
                "skipped": 0,
                "worker_seconds": 0.0,
            }
        )
        for case in root.iter("testcase"):
            group = groups[case.attrib["classname"]]
            group["cases"] += 1
            found = [tag for tag in ("failure", "error", "skipped") if case.find(tag) is not None]
            assert len(found) <= 1
            group[
                {"failure": "failures", "error": "errors", "skipped": "skipped"}.get(
                    found[0] if found else "", "passed"
                )
            ] += 1
            seconds = float(case.attrib["time"])
            assert math.isfinite(seconds) and seconds >= 0
            group["worker_seconds"] += seconds
        assert set(groups) == {suite[:-3].replace("/", ".") for suite in SUITES}
        for container in root.iter():
            if container.tag not in ("testsuite", "testsuites"):
                continue
            cases = list(container.iter("testcase"))
            for attr, count in {
                "tests": len(cases),
                **{
                    label: sum(c.find(tag) is not None for c in cases)
                    for label, tag in (
                        ("failures", "failure"),
                        ("errors", "error"),
                        ("skipped", "skipped"),
                    )
                },
            }.items():
                if attr in container.attrib:
                    assert container.attrib[attr].isascii() and container.attrib[attr].isdecimal()
                    assert int(container.attrib[attr]) == count
        for name, counts in groups.items():
            assert counts["passed"] == counts["cases"] > 0
            assert math.isfinite(counts["worker_seconds"])
            for key, value in counts.items():
                assert row["junit"]["per_file"][name][key] == value
            assert row["junit"]["per_file"][name]["timing_status"] == "KNOWN"
        outcomes[arm] = dict(groups)
        report = json.loads(members[f"{arm}/coverage.json"])
        assert report["meta"]["branch_coverage"] is True
        cov = report["files"][VERIFIER]
        assert all(type(line) is int and line > 0 for line in cov["executed_lines"])
        assert all(
            len(pair) == 2 and all(type(n) is int and n != 0 for n in pair)
            for pair in cov["executed_branches"]
        )
        coverage[arm] = (set(cov["executed_lines"]), {tuple(a) for a in cov["executed_branches"]})
        if "phases" in row:
            measured = {}
            for role in ("controller", "gw0", "gw1", "gw2", "gw3"):
                path = f"{arm}/phase-clocks/{role}.json"
                assert path in result["artifact_sha256"]
                clock = json.loads(members[path])
                assert clock["role"] == role and clock["clock"] == "time.monotonic"
                intervals = {}
                labels = [
                    ("session", "session"),
                    ("collection", "collection"),
                    ("controller_worker_loop", "loop"),
                    ("reporting", "reporting"),
                ]
                if role == "controller":
                    labels.append(("coverage_reporting", "coverage_reporting"))
                for label, prefix in labels:
                    start, end = (
                        clock["boundaries"][f"{prefix}_{edge}"] for edge in ("start", "end")
                    )
                    assert all(
                        type(t) in (int, float) and math.isfinite(t) and t >= 0
                        for t in (start, end)
                    )
                    assert end >= start
                    intervals[label] = {"start": start, "end": end, "seconds": end - start}
                measured[role] = intervals
            assert row["phases"]["available"] is True and row["phases"]["gaps"] == []
            assert row["phases"]["processes"] == measured
            phases[arm] = measured
    before, after = coverage["baseline"], coverage["candidate"]
    comparison = {
        "lost_lines": sorted(before[0] - after[0]),
        "lost_branches": [list(a) for a in sorted(before[1] - after[1])],
        "baseline_lines": len(before[0]),
        "candidate_lines": len(after[0]),
        "baseline_branches": len(before[1]),
        "candidate_branches": len(after[1]),
    }
    assert comparison == result["verifier_coverage"]
    assert not comparison["lost_lines"] and not comparison["lost_branches"]
    assert result["outcome_comparison"] == {"successful": True, "gaps": []}
    assert result["timing_comparison"] == {"available": True, "gaps": []}
    return {
        "verified": True,
        "artifact_id": artifact["id"],
        "archive_sha256": archive_hash,
        "run_id": artifact["workflow_run"]["id"],
        "workflow_sha": manifest["workflow_sha"],
        "python": result["python"],
        "coverage": comparison,
        "outcomes": outcomes,
        "source_manifests_verified_against_git": True,
        "uploaded_hashes_verified": True,
        "unuploaded_inherited_entries_UNKNOWN": missing,
        "packages_unchanged_reported_by_harness": True,
        "phase_measurement": phases or "UNKNOWN: original run has no phase probe",
        "limitations": "One pair per runtime; no causal speedup inference. Concurrent process intervals overlap; unavailable exclusive overhead stays UNKNOWN.",
    }


if __name__ == "__main__":
    print(
        json.dumps(
            validate(Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))),
            indent=2,
            allow_nan=False,
        )
    )
