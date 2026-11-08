"""Regression controls for the independent hosted archive validator."""

import importlib.util
import json
import os
import subprocess
import sys
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

    def build(
        *,
        phase_enabled=False,
        workflow_sha="a" * 40,
        python_version="3.13.18",
        missing_members=(),
        mutate=None,
    ):
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
            "python": python_version,
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
        for path in missing_members:
            del members[path]
        archive = tmp_path / "verifier-runtime.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            for path, raw in members.items():
                zipped.writestr(path, raw)
        metadata = {
            "artifacts": [
                {
                    "id": 123,
                    "name": f"verifier-runtime-{'.'.join(python_version.split('.')[:2])}-456",
                    "digest": f"sha256:{validator.digest(archive.read_bytes())}",
                    "workflow_run": {"id": 456, "head_sha": workflow_sha},
                }
            ]
        }
        return archive, metadata

    return build, git_calls


@pytest.fixture
def run_validator_cli(tmp_path):
    """Exercise the public command with the test interpreter and no Git on PATH."""

    def run(archive, metadata):
        metadata_path = tmp_path / "artifact-metadata.json"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        environment = os.environ.copy()
        environment["PATH"] = str(tmp_path / "no-git")
        return subprocess.run(
            [sys.executable, str(VALIDATOR_PATH), str(archive), str(metadata_path)],
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    return run


@pytest.mark.parametrize("workflow_sha", [None, 123, [], "--help", "A" * 40, "a" * 40 + "\n"])
def test_cli_rejects_invalid_workflow_identity_before_git(
    hosted_archive, run_validator_cli, workflow_sha
):
    """The unpatched CLI must diagnose invalid identities without needing Git."""
    build, _ = hosted_archive
    result = run_validator_cli(*build(workflow_sha=workflow_sha))

    assert result.returncode != 0
    assert result.stdout == ""
    assert "ValueError: workflow_sha must be a full lowercase" in result.stderr
    assert "FileNotFoundError" not in result.stderr


@pytest.mark.parametrize("arm", ["baseline", "candidate"])
@pytest.mark.parametrize("change", ["missing", "unavailable", "missing_worker"])
def test_cli_rejects_incomplete_phases_before_git(hosted_archive, run_validator_cli, arm, change):
    """Either arm's missing phase data must fail before immutable-source lookup."""
    build, _ = hosted_archive

    def damage_phases(result, members):
        if change == "missing":
            del result["arms"][arm]["phases"]
        elif change == "unavailable":
            result["arms"][arm]["phases"]["available"] = False
        else:
            del result["arms"][arm]["phases"]["processes"]["gw3"]

    result = run_validator_cli(*build(phase_enabled=True, mutate=damage_phases))

    assert result.returncode != 0
    assert result.stdout == ""
    assert f"ValueError: {arm} requires complete available phase measurements" in result.stderr
    assert "FileNotFoundError" not in result.stderr


@pytest.mark.parametrize("phase_enabled", [False, True])
def test_cli_cannot_verify_archive_without_immutable_git_sources(
    hosted_archive, run_validator_cli, phase_enabled
):
    """Complete self-reported receipts cannot replace independent Git verification."""
    build, _ = hosted_archive
    result = run_validator_cli(*build(phase_enabled=phase_enabled))

    assert result.returncode != 0
    assert result.stdout == ""
    assert "FileNotFoundError" in result.stderr
    assert "'git'" in result.stderr


@pytest.mark.parametrize("workflow_sha", ["a" * 40, "b" * 64])
@pytest.mark.parametrize("phase_enabled", [False, True])
@pytest.mark.parametrize(
    "python_version",
    [
        "3.12.16",
        "3.13.18",
        "3.12.16 (main, Oct 26 2026, 14:19:33) [GCC 15.2.0]",
        "3.13.18 (main, Oct 26 2026, 14:19:33) [GCC 15.2.0]",
    ],
)
def test_valid_legacy_and_phase_archives(
    hosted_archive, workflow_sha, phase_enabled, python_version
):
    build, git_calls = hosted_archive
    summary = validator.validate(
        *build(
            phase_enabled=phase_enabled,
            workflow_sha=workflow_sha,
            python_version=python_version,
        )
    )
    assert summary["verified"] is True
    assert summary["workflow_sha"] == workflow_sha
    assert summary["python"] == python_version
    assert git_calls
    assert set(summary["unuploaded_inherited_entries_UNKNOWN"]) == {
        f"{arm}/docs/evidence/issue-3743/runtime-probes/{name}.log"
        for arm in validator.PAIR
        for name in validator.PAIR
    }
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


@pytest.mark.parametrize("phase_enabled", [False, True])
def test_changed_archive_rejected_before_git(hosted_archive, phase_enabled):
    """Readable ZIP bytes must still match the retained GitHub artifact digest."""
    build, git_calls = hosted_archive
    archive, metadata = build(phase_enabled=phase_enabled)
    with zipfile.ZipFile(archive, "a") as zipped:
        zipped.writestr("extra.log", b"added after upload\n")

    with pytest.raises(AssertionError, match="archive differs from GitHub artifact digest"):
        validator.validate(archive, metadata)
    assert git_calls == []


@pytest.mark.parametrize("phase_enabled", [False, True])
def test_ambiguous_artifact_identity_rejected_before_git(hosted_archive, phase_enabled):
    """Two metadata rows with the same digest cannot select an artifact identity."""
    build, git_calls = hosted_archive
    archive, metadata = build(phase_enabled=phase_enabled)
    metadata["artifacts"].append({**metadata["artifacts"][0], "id": 124})

    with pytest.raises(AssertionError, match="archive differs from GitHub artifact digest"):
        validator.validate(archive, metadata)
    assert git_calls == []


@pytest.mark.parametrize("phase_enabled", [False, True])
def test_duplicate_archive_members_rejected_before_git(hosted_archive, phase_enabled):
    """Even an authenticated ZIP must not choose between duplicate manifests."""
    build, git_calls = hosted_archive
    archive, metadata = build(phase_enabled=phase_enabled)
    with zipfile.ZipFile(archive, "a") as zipped:
        manifest = zipped.read("manifest.json")
        with pytest.warns(UserWarning, match="Duplicate name: 'manifest.json'"):
            zipped.writestr("manifest.json", manifest)
    metadata["artifacts"][0]["digest"] = f"sha256:{validator.digest(archive.read_bytes())}"

    with pytest.raises(AssertionError, match="duplicate archive members"):
        validator.validate(archive, metadata)
    assert git_calls == []


@pytest.mark.parametrize("phase_enabled", [False, True])
def test_result_manifest_identity_must_match_archive_manifest(hosted_archive, phase_enabled):
    """The embedded result cannot identify a different workflow from the manifest."""
    build, git_calls = hosted_archive

    def replace_result_identity(result, members):
        result["manifest"] = {**result["manifest"], "workflow_sha": "b" * 40}

    with pytest.raises(AssertionError):
        validator.validate(*build(phase_enabled=phase_enabled, mutate=replace_result_identity))
    assert git_calls == []


@pytest.mark.parametrize("phase_enabled", [False, True])
def test_workflow_identity_must_match_retained_metadata(hosted_archive, phase_enabled):
    """A valid commit ID and digest cannot bypass GitHub's recorded workflow head."""
    build, git_calls = hosted_archive
    archive, metadata = build(phase_enabled=phase_enabled)
    metadata["artifacts"][0]["workflow_run"]["head_sha"] = "b" * 40

    with pytest.raises(AssertionError):
        validator.validate(archive, metadata)
    assert git_calls == []


@pytest.mark.parametrize("phase_enabled", [False, True])
@pytest.mark.parametrize("arm", ["baseline", "candidate"])
@pytest.mark.parametrize("field", ["commit", "tree", "sha256"])
def test_archive_cannot_replace_immutable_source_pair(hosted_archive, phase_enabled, arm, field):
    """A matching artifact digest cannot authenticate a substituted source revision."""
    build, _ = hosted_archive

    def substitute_source(result, members):
        source = result["manifest"]["arms"][arm]
        if field == "sha256":
            path = validator.SUITES[0]
            source[field][path] = "e" * 64
            # Keep both reported integrity boundaries consistent with the forgery.
            # Rejection must come from the independent Git source comparison.
            for boundary in ("before", "after"):
                result["source_integrity"][boundary]["sha256"][arm][path] = "e" * 64
        else:
            source[field] = "e" * 40

    with pytest.raises(AssertionError):
        validator.validate(*build(phase_enabled=phase_enabled, mutate=substitute_source))


@pytest.mark.parametrize("phase_enabled", [False, True])
@pytest.mark.parametrize(
    "dependency_lock", ["baseline/requirements.lock", "candidate/pyproject.toml"]
)
def test_archive_cannot_replace_candidate_dependency_lock(
    hosted_archive, phase_enabled, dependency_lock
):
    """The retained experiment uses the candidate lock for both immutable arms."""
    build, git_calls = hosted_archive

    def substitute_lock(result, members):
        result["manifest"]["dependency_lock"] = dependency_lock

    with pytest.raises(AssertionError):
        validator.validate(*build(phase_enabled=phase_enabled, mutate=substitute_lock))
    assert git_calls == []


@pytest.mark.parametrize("phase_enabled", [False, True])
@pytest.mark.parametrize("field", ["harness_sha256", "workflow_sha256"])
def test_recorded_instrumentation_hash_must_match_git(hosted_archive, phase_enabled, field):
    """An authenticated archive cannot substitute its recorded measurement source."""
    build, git_calls = hosted_archive

    def substitute_hash(result, members):
        result["manifest"][field] = validator.digest(b"different measurement source\n")

    with pytest.raises(AssertionError):
        validator.validate(*build(phase_enabled=phase_enabled, mutate=substitute_hash))
    assert git_calls


@pytest.mark.parametrize("plugin_hash", [None, False, "", "d" * 64, "D" * 64, []])
def test_declared_phase_plugin_must_match_immutable_harness(hosted_archive, plugin_hash):
    """Complete phase receipts still require the probe from the recorded Git source."""
    build, git_calls = hosted_archive

    def substitute_probe(result, members):
        result["phase_plugin_sha256"] = plugin_hash

    with pytest.raises(AssertionError):
        validator.validate(*build(phase_enabled=True, mutate=substitute_probe))
    assert git_calls


@pytest.mark.parametrize("phase_enabled", [False, True])
@pytest.mark.parametrize("arm", ["baseline", "candidate"])
def test_uploaded_historical_log_is_verified_instead_of_unknown(hosted_archive, phase_enabled, arm):
    """Only unavailable inherited logs qualify for the explicit UNKNOWN exception."""
    build, _ = hosted_archive
    path = f"{arm}/docs/evidence/issue-3743/runtime-probes/baseline.log"

    def upload_log(result, members):
        members[path] = b"retained historical log\n"
        result["artifact_sha256"][path] = validator.digest(members[path])

    summary = validator.validate(*build(phase_enabled=phase_enabled, mutate=upload_log))
    assert summary["verified"] is True
    assert path not in summary["unuploaded_inherited_entries_UNKNOWN"]
    assert len(summary["unuploaded_inherited_entries_UNKNOWN"]) == 3
    assert "exclusive overhead stays UNKNOWN" in summary["limitations"]


@pytest.mark.parametrize("phase_enabled", [False, True])
@pytest.mark.parametrize("arm", ["baseline", "candidate"])
@pytest.mark.parametrize("historical", [False, True])
def test_uploaded_log_corruption_cannot_be_treated_as_unknown(
    hosted_archive, phase_enabled, arm, historical
):
    """A valid outer ZIP digest does not waive any uploaded member's hash check."""
    build, _ = hosted_archive
    path = (
        f"{arm}/docs/evidence/issue-3743/runtime-probes/baseline.log"
        if historical
        else f"{arm}.log"
    )

    def corrupt_log(result, members):
        result["artifact_sha256"][path] = validator.digest(b"original log\n")
        members[path] = b"corrupted log\n"

    with pytest.raises(AssertionError, match=f"uploaded hash mismatch: {path}"):
        validator.validate(*build(phase_enabled=phase_enabled, mutate=corrupt_log))


@pytest.mark.parametrize("phase_enabled", [False, True])
@pytest.mark.parametrize("arm", ["baseline", "candidate"])
def test_unknown_exception_does_not_cover_other_missing_historical_logs(
    hosted_archive, phase_enabled, arm
):
    """A neighboring historical path is not one of the four inherited exceptions."""
    build, _ = hosted_archive
    path = f"{arm}/docs/evidence/issue-3743/runtime-probes/other.log"

    def add_missing_log(result, members):
        result["artifact_sha256"][path] = validator.digest(b"unavailable log\n")

    with pytest.raises(AssertionError, match=f"missing required hash member: {path}"):
        validator.validate(*build(phase_enabled=phase_enabled, mutate=add_missing_log))


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


@pytest.mark.parametrize("retained_evidence", ["summaries", "receipts", "both"])
@pytest.mark.parametrize("missing_arm", [None, "baseline", "candidate"])
def test_phase_archive_cannot_fall_back_to_legacy_without_probe_declaration(
    hosted_archive, retained_evidence, missing_arm
):
    """Removing the declaration cannot turn remaining phase evidence into legacy data."""
    build, git_calls = hosted_archive

    def remove_declaration(result, members):
        del result["phase_plugin_sha256"]
        for arm in validator.PAIR:
            if retained_evidence == "receipts" or arm == missing_arm:
                del result["arms"][arm]["phases"]
        if retained_evidence == "summaries":
            for path in list(members):
                if "/phase-clocks/" in path:
                    del members[path]
                    del result["artifact_sha256"][path]

    with pytest.raises(ValueError, match="phase measurements require phase_plugin_sha256"):
        validator.validate(*build(phase_enabled=True, mutate=remove_declaration))
    assert git_calls == []


@pytest.mark.parametrize("arm", ["baseline", "candidate"])
@pytest.mark.parametrize(
    "field, value",
    [
        ("phases", None),
        ("phases", False),
        ("phases", []),
        ("phases", "available"),
        ("phases", {}),
        ("available", 1),
        ("available", False),
        ("gaps", None),
        ("gaps", ["missing boundary"]),
        ("processes", []),
        ("processes", {}),
    ],
)
def test_declared_phase_metadata_must_be_complete_before_git(hosted_archive, arm, field, value):
    """Malformed declared measurements fail explicitly without needing source objects."""
    build, git_calls = hosted_archive

    def damage_phases(result, members):
        if field == "phases":
            result["arms"][arm]["phases"] = value
        else:
            result["arms"][arm]["phases"][field] = value

    with pytest.raises(ValueError, match=f"{arm}.*phase measurements"):
        validator.validate(*build(phase_enabled=True, mutate=damage_phases))
    assert git_calls == []


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


@pytest.mark.parametrize("arm", ["baseline", "candidate"])
@pytest.mark.parametrize("role", ["controller", "gw3"])
@pytest.mark.parametrize("boundary", [None, True, "3", -1, float("nan"), float("inf"), 11])
def test_raw_phase_boundaries_cannot_be_hidden_by_valid_summary(
    hosted_archive, arm, role, boundary
):
    """Rehashing a bad raw clock must not let an unchanged valid summary pass."""
    build, _ = hosted_archive

    def damage_clock(result, members):
        path = f"{arm}/phase-clocks/{role}.json"
        clock = json.loads(members[path])
        clock["boundaries"]["session_start"] = boundary
        members[path] = json.dumps(clock).encode()
        result["artifact_sha256"][path] = validator.digest(members[path])

    with pytest.raises(AssertionError):
        validator.validate(*build(phase_enabled=True, mutate=damage_clock))


@pytest.mark.parametrize("arm", ["baseline", "candidate"])
@pytest.mark.parametrize("role", ["controller", "gw3"])
@pytest.mark.parametrize("change", ["missing_receipt", "missing_hash", "role", "clock"])
def test_phase_summary_cannot_replace_raw_receipt(hosted_archive, arm, role, change):
    """Each arm needs independently hashed receipts with the expected clock identity."""
    build, _ = hosted_archive

    def damage_clock(result, members):
        path = f"{arm}/phase-clocks/{role}.json"
        if change == "missing_receipt":
            del members[path]
            del result["artifact_sha256"][path]
        elif change == "missing_hash":
            del result["artifact_sha256"][path]
        else:
            clock = json.loads(members[path])
            clock[change] = "other-process" if change == "role" else "time.time"
            members[path] = json.dumps(clock).encode()
            result["artifact_sha256"][path] = validator.digest(members[path])

    with pytest.raises(AssertionError):
        validator.validate(*build(phase_enabled=True, mutate=damage_clock))


@pytest.mark.parametrize(
    "member",
    [
        "result.json",
        "manifest.json",
        "baseline/pytest-junit.xml",
        "candidate/pytest-junit.xml",
        "baseline/coverage.json",
        "candidate/coverage.json",
        "baseline.log",
        "candidate.log",
    ],
)
def test_required_archive_members_rejected_before_git(hosted_archive, member):
    """Report missing inputs explicitly even when the archive digest matches."""
    build, git_calls = hosted_archive
    with pytest.raises(ValueError, match=f"missing required archive members:.*{member}"):
        validator.validate(*build(missing_members=(member,)))
    assert git_calls == []


@pytest.mark.parametrize("python_version", ["3.12.16", "3.13.18"])
@pytest.mark.parametrize("name", [None, 123, "", "verifier-runtime-3.14", "verifier-runtime-3.130"])
def test_artifact_name_must_match_recorded_runtime(hosted_archive, python_version, name):
    """A matching digest cannot establish a different runtime's receipt."""
    build, git_calls = hosted_archive
    archive, metadata = build(python_version=python_version)
    metadata["artifacts"][0]["name"] = name
    with pytest.raises(ValueError, match="artifact name.*Python runtime"):
        validator.validate(archive, metadata)
    assert git_calls == []


def test_artifact_name_is_required(hosted_archive):
    """Missing metadata names cannot silently bypass the runtime check."""
    build, git_calls = hosted_archive
    archive, metadata = build()
    del metadata["artifacts"][0]["name"]
    with pytest.raises(ValueError, match="artifact name.*Python runtime"):
        validator.validate(archive, metadata)
    assert git_calls == []


@pytest.mark.parametrize("phase_enabled", [False, True])
@pytest.mark.parametrize("python_version", ["3.12.16", "3.13.18"])
@pytest.mark.parametrize("suffix", ["", "-457", "-0456", "-456-extra"])
def test_artifact_name_must_match_recorded_run(
    hosted_archive, phase_enabled, python_version, suffix
):
    """Use the pinned workflow's runtime/run name without accepting a different run."""
    build, git_calls = hosted_archive
    archive, metadata = build(phase_enabled=phase_enabled, python_version=python_version)
    minor_version = ".".join(python_version.split(".")[:2])
    metadata["artifacts"][0]["name"] = f"verifier-runtime-{minor_version}{suffix}"
    with pytest.raises(ValueError, match="artifact name.*Python runtime"):
        validator.validate(archive, metadata)
    assert git_calls == []


@pytest.mark.parametrize("python_version", ["3.12.16", "3.13.18"])
def test_swapped_runtime_artifact_rejected(hosted_archive, python_version):
    """The two retained runtime labels are not interchangeable."""
    build, git_calls = hosted_archive
    archive, metadata = build(python_version=python_version)
    other_version = "3.13" if python_version.startswith("3.12.") else "3.12"
    metadata["artifacts"][0]["name"] = f"verifier-runtime-{other_version}-456"
    with pytest.raises(ValueError, match="artifact name.*Python runtime"):
        validator.validate(archive, metadata)
    assert git_calls == []


@pytest.mark.parametrize("python_version", [None, True, 313, "", "3.13", "3.13.18\n"])
def test_malformed_recorded_runtime_rejected(hosted_archive, python_version):
    """Malformed runtime fields fail clearly before any immutable-source lookup."""
    build, git_calls = hosted_archive

    def change_runtime(result, members):
        result["python"] = python_version

    with pytest.raises(ValueError, match="Python runtime must be.*major.minor.patch"):
        validator.validate(*build(mutate=change_runtime))
    assert git_calls == []


@pytest.mark.parametrize("optimize_flag", ["-O", "-OO"])
def test_optimized_python_refuses_validation_with_minus_O(tmp_path, hosted_archive, optimize_flag):
    """Optimized Python execution refuses validation before accepting any archive."""
    build, _ = hosted_archive
    archive, metadata = build()
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(metadata))

    result = subprocess.run(
        [sys.executable, optimize_flag, str(VALIDATOR_PATH), str(archive), str(metadata_path)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert "Optimized execution refuses validation" in result.stderr


def test_optimized_python_refuses_validation_with_PYTHONOPTIMIZE(tmp_path, hosted_archive):
    """PYTHONOPTIMIZE=1 refuses validation before accepting any archive."""
    build, _ = hosted_archive
    archive, metadata = build()
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(metadata))

    env = os.environ.copy()
    env["PYTHONOPTIMIZE"] = "1"
    result = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), str(archive), str(metadata_path)],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode != 0
    assert "Optimized execution refuses validation" in result.stderr
