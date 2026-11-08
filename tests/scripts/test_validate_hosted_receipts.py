"""Regression controls for the independent hosted archive validator."""

import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

VALIDATOR_PATH = (
    Path(__file__).resolve().parents[2] / "docs/evidence/issue-3904/validate_hosted_receipts.py"
)
spec = importlib.util.spec_from_file_location("validate_hosted_receipts", VALIDATOR_PATH)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


@pytest.fixture
def hosted_archive(tmp_path, monkeypatch):
    """Build small complete archives with deterministic immutable Git responses."""
    git_calls = []
    source_bytes = b"retained source\n"
    harness = b'PHASE_PLUGIN = "# identical external probe\\n"\n'
    workflow = b"retained workflow\n"
    sources = {
        path: validator.digest(source_bytes)
        for path in (*validator.SUITES, validator.VERIFIER, "pyproject.toml", "requirements.lock")
    }
    tree = "c" * 40

    def git(*args):
        git_calls.append(args)
        if args[0] == "rev-parse":
            assert args[1] in {f"{ref}^{{tree}}" for ref in validator.PAIR.values()}
            return tree.encode()
        assert args[0] == "show"
        ref, path = args[1].split(":", 1)
        if path == "scripts/measure_verifier_runtime.py":
            return harness
        if path == ".github/workflows/maint-88-verifier-runtime-comparison.yml":
            return workflow
        assert ref in validator.PAIR.values() and path in sources
        return source_bytes

    monkeypatch.setattr(validator, "git", git)

    def build(*, phase_enabled=False, workflow_sha="a" * 40, mutate=None):
        manifest = {
            "workflow_sha": workflow_sha,
            "dependency_lock": "candidate/requirements.lock",
            "harness_sha256": validator.digest(harness),
            "workflow_sha256": validator.digest(workflow),
            "arms": {
                arm: {"commit": ref, "tree": tree, "sha256": sources.copy()}
                for arm, ref in validator.PAIR.items()
            },
        }
        result = {
            "manifest": manifest,
            "python": "3.13.fixture",
            "source_integrity": {
                "verified": True,
                **{
                    boundary: {
                        "verified": True,
                        "sha256": {arm: sources.copy() for arm in validator.PAIR},
                    }
                    for boundary in ("before", "after")
                },
            },
            "packages_unchanged": True,
            "arms": {},
            "artifact_sha256": {},
            "verifier_coverage": {
                "lost_lines": [],
                "lost_branches": [],
                "baseline_lines": 2,
                "candidate_lines": 2,
                "baseline_branches": 1,
                "candidate_branches": 1,
            },
            "outcome_comparison": {"successful": True, "gaps": []},
            "timing_comparison": {"available": True, "gaps": []},
        }
        members = {}
        for arm in validator.PAIR:
            per_file = {
                suite[:-3].replace("/", "."): {
                    "cases": 1,
                    "passed": 1,
                    "failures": 0,
                    "errors": 0,
                    "skipped": 0,
                    "worker_seconds": 1.0,
                    "timing_status": "KNOWN",
                }
                for suite in validator.SUITES
            }
            members[f"{arm}/pytest-junit.xml"] = (
                '<testsuites><testsuite tests="3" failures="0" errors="0" skipped="0">'
                + "".join(f'<testcase classname="{name}" time="1"/>' for name in per_file)
                + "</testsuite></testsuites>"
            ).encode()
            members[f"{arm}/coverage.json"] = json.dumps(
                {
                    "meta": {"branch_coverage": True},
                    "files": {
                        validator.VERIFIER: {
                            "executed_lines": [1, 2],
                            "executed_branches": [[1, 2]],
                        }
                    },
                }
            ).encode()
            members[f"{arm}.log"] = b"all scoped cases passed\n"
            row = {"exit_code": 0, "wall_seconds": 10, "junit": {"per_file": per_file}}
            result["arms"][arm] = row
            if phase_enabled:
                result["phase_plugin_sha256"] = validator.digest(b"# identical external probe\n")
                processes = {}
                for role in ("controller", "gw0", "gw1", "gw2", "gw3"):
                    intervals = {
                        "session": ("session", 1, 10),
                        "collection": ("collection", 2, 3),
                        "controller_worker_loop": ("loop", 3, 8),
                        "reporting": ("reporting", 8, 9),
                    }
                    if role == "controller":
                        intervals["coverage_reporting"] = ("coverage_reporting", 6, 7)
                    processes[role] = {
                        label: {"start": start, "end": end, "seconds": end - start}
                        for label, (_, start, end) in intervals.items()
                    }
                    members[f"{arm}/phase-clocks/{role}.json"] = json.dumps(
                        {
                            "role": role,
                            "clock": "time.monotonic",
                            "boundaries": {
                                f"{prefix}_{edge}": value
                                for prefix, start, end in intervals.values()
                                for edge, value in (("start", start), ("end", end))
                            },
                        }
                    ).encode()
                row["phases"] = {"available": True, "gaps": [], "processes": processes}
        result["artifact_sha256"] = {path: validator.digest(raw) for path, raw in members.items()}
        # These unuploaded historical logs must remain explicitly UNKNOWN.
        for arm in validator.PAIR:
            for name in validator.PAIR:
                path = f"{arm}/docs/evidence/issue-3743/runtime-probes/{name}.log"
                result["artifact_sha256"][path] = "d" * 64
        if mutate:
            mutate(result, members)
        members["manifest.json"] = json.dumps(manifest).encode()
        members["result.json"] = json.dumps(result).encode()
        archive = tmp_path / "verifier-runtime.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            for path, raw in members.items():
                zipped.writestr(path, raw)
        metadata = {
            "artifacts": [
                {
                    "id": 123,
                    "digest": f"sha256:{validator.digest(archive.read_bytes())}",
                    "workflow_run": {"id": 456, "head_sha": workflow_sha},
                }
            ]
        }
        return archive, metadata

    return build, git_calls


@pytest.mark.parametrize("workflow_sha", ["a" * 40, "b" * 64])
@pytest.mark.parametrize("phase_enabled", [False, True])
def test_valid_legacy_and_phase_archives(hosted_archive, workflow_sha, phase_enabled):
    build, git_calls = hosted_archive
    summary = validator.validate(*build(phase_enabled=phase_enabled, workflow_sha=workflow_sha))
    assert summary["verified"] is True
    assert summary["workflow_sha"] == workflow_sha
    assert git_calls
    assert len(summary["unuploaded_inherited_entries_UNKNOWN"]) == 4
    assert "exclusive overhead stays UNKNOWN" in summary["limitations"]
    if phase_enabled:
        assert set(summary["phase_measurement"]) == set(validator.PAIR)
        for arm in validator.PAIR:
            assert set(summary["phase_measurement"][arm]) == {
                "controller",
                "gw0",
                "gw1",
                "gw2",
                "gw3",
            }
            assert (
                summary["phase_measurement"][arm]["controller"]["coverage_reporting"]["seconds"]
                == 1
            )
    else:
        assert summary["phase_measurement"] == "UNKNOWN: original run has no phase probe"


@pytest.mark.parametrize(
    "workflow_sha",
    [
        None,
        True,
        123,
        [],
        {},
        "",
        "HEAD",
        "--help",
        "a" * 39,
        "a" * 41,
        "a" * 63,
        "a" * 65,
        "A" * 40,
        "A" * 64,
        "g" * 40,
        "a" * 40 + "\n",
        " " + "a" * 40,
        "a" * 40 + ":file",
    ],
)
def test_invalid_workflow_identity_rejected_before_git(hosted_archive, workflow_sha):
    build, git_calls = hosted_archive
    with pytest.raises(ValueError, match="workflow_sha.*full lowercase.*commit"):
        validator.validate(*build(workflow_sha=workflow_sha))
    assert git_calls == []


@pytest.mark.parametrize("arms", [("baseline",), ("candidate",), ("baseline", "candidate")])
def test_phase_plugin_requires_phases_in_both_arms(hosted_archive, arms):
    build, _ = hosted_archive

    def remove_phases(result, members):
        for arm in arms:
            del result["arms"][arm]["phases"]

    with pytest.raises(ValueError, match=f"{arms[0]}.*phase measurements"):
        validator.validate(*build(phase_enabled=True, mutate=remove_phases))


@pytest.mark.parametrize("arm", ["baseline", "candidate"])
@pytest.mark.parametrize("change", ["unavailable", "gaps", "missing_worker", "missing_coverage"])
def test_phase_plugin_rejects_unavailable_or_incomplete_phases(hosted_archive, arm, change):
    build, _ = hosted_archive

    def damage_phases(result, members):
        phases = result["arms"][arm]["phases"]
        if change == "unavailable":
            phases["available"] = False
        elif change == "gaps":
            phases["gaps"] = ["missing boundary"]
        elif change == "missing_worker":
            del phases["processes"]["gw3"]
        else:
            del phases["processes"]["controller"]["coverage_reporting"]

    with pytest.raises((AssertionError, ValueError)):
        validator.validate(*build(phase_enabled=True, mutate=damage_phases))
