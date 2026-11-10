"""Authenticated retained revalidation never invokes a provider or rewrites history."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import pytest
import yaml
from tools import verifier_event_recovery
from tools.verifier_artifact_capture import load_artifact_capture
from tools.verifier_capture_obligation_manifest import (
    build_capture_obligation_manifest,
    parse_context_source_coverage,
    record_capture_obligations,
    validate_capture_byte_inventory,
)
from tools.verifier_corpus_evidence import admitted_decision, event_metadata, validated_payload
from tools.verifier_event_recovery import (
    incomplete_cause,
    original_final_projection,
    revalidate_retained,
    verify_revalidation_admission,
)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("profile", ["standard", "expanded"])
def test_exact_4509_without_provider_output_cannot_recover_a_review(
    tmp_path, monkeypatch, capsys, profile
):
    from scripts.langchain import pr_verifier
    from tools.verifier_corpus_evidence import settled_verdict

    def unexpected_evaluation(*args, **kwargs):
        pytest.fail("No provider output exists to invoke or parse during retained recovery")

    for name in (
        "get_llm_client",
        "get_llm_clients",
        "_get_llm_client",
        "_get_llm_clients",
        "_build_semantic_clients",
        "_invoke_llm",
        "_parse_semantic_evaluation_payload",
    ):
        monkeypatch.setattr(pr_verifier, name, unexpected_evaluation)
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", profile)
    # Use the retained configured pair, independent of runner model overrides.
    for name in ("VERIFIER_MODEL", "VERIFIER_MODEL2", "LANGCHAIN_MODEL", "LANGCHAIN_SLOT_CONFIG"):
        monkeypatch.delenv(name, raising=False)
    fixtures = Path(__file__).resolve().parents[2] / ".github/scripts/__tests__/fixtures"
    capture_path = fixtures / "verifier-4509-capture.zip"
    original = capture_path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    for name, raw in files.items():
        assert Path(name).name == name
        (tmp_path / name).write_bytes(raw)
    manifest = json.loads(files["verification-event-manifest.json"])
    payload = json.loads(files["comparison.json"])
    metadata = event_metadata(tmp_path / "verification-event-manifest.json")
    rows, verdict, available = validated_payload(payload, mode="compare")
    assert available is False
    assert verdict != "PASS"
    assert len(rows) == 2
    for row in rows:
        assert row["used_llm"] is False
        assert row["raw_content"] is None
        assert row["files_reviewed"] is None
        assert row["files_not_reviewed"] == [
            "scripts/ci_history.py",
            "tests/scripts/test_ci_history.py",
        ]
    cause = incomplete_cause(manifest, directory=tmp_path, step_outcome="success")
    assert cause["retry_kind"] == "known_no_evaluation"
    assert cause["failure_cause"] == "validated_no_evaluation"
    # The operational CLI may succeed at classification while recovery remains
    # inadmissible. Its retry hint is not an accepted review or provider authority.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "verifier_event_recovery.py",
            "--manifest",
            str(tmp_path / "verification-event-manifest.json"),
            "--step-outcome",
            "success",
        ],
    )
    assert verifier_event_recovery.main() == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert json.loads(output.out) == {
        "retry_kind": "known_no_evaluation",
        "retryable": True,
        "failure_cause": "validated_no_evaluation",
    }
    identity = {
        key: metadata["verification_event"][key]
        for key in ("repo", "pr", "head_sha", "evaluated_sha")
    }
    identity.update(run_id="42330898168", run_attempt="1")
    decision = admitted_decision(
        tmp_path / "comparison.json",
        tmp_path / "comparison-execution.json",
        identity,
        mode="compare",
        ci_failed="false",
    )
    assert decision is None
    assert settled_verdict(decision) == "UNVERIFIABLE_INPUT"

    # Even the supported historical parser cannot project a nonexistent final.
    # This digest selects a parser compatibility case only; it is NOT an origin
    # claim for #4509 and supplies no native recovery/publication authority.
    with pytest.raises(ValueError, match="^No audited original parse failure to project$"):
        original_final_projection(
            payload,
            mode="compare",
            validator_sha256="5e8f7a842231f16d8f5ba3ae1a48ed7625afa2feafe774963cdba066196fd0b8",
            assessment=metadata["assessment_identity"],
        )
    assert payload == json.loads(files["comparison.json"])
    assert capture_path.read_bytes() == original
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == files


def test_exact_4509_capture_validation_preserves_gaps_event_and_zero_provider_coverage(
    tmp_path, monkeypatch, capsys
):
    from scripts.langchain import pr_verifier

    def unexpected_provider(*args, **kwargs):
        pytest.fail("Retained input validation must never construct a provider client")

    for name in ("get_llm_client", "get_llm_clients", "_get_llm_client", "_get_llm_clients"):
        monkeypatch.setattr(pr_verifier, name, unexpected_provider)
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "standard")
    monkeypatch.setenv("VERIFICATION_MATERIAL", "[]")
    monkeypatch.setenv("VERIFIER_SEMANTIC_MODE", "0")
    monkeypatch.delenv("VERIFIER_EVIDENCE_CAPTURE_DIR", raising=False)
    fixtures = Path(__file__).resolve().parents[2] / ".github/scripts/__tests__/fixtures"
    identity = json.loads((fixtures / "verifier-4509-capture-identity.json").read_bytes())
    archive_path = fixtures / "verifier-4509-capture.zip"
    original = archive_path.read_bytes()
    assert f"sha256:{sha(original)}" == identity["capture"]["digest"]
    assert len(original) == identity["capture"]["size_in_bytes"]
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        # Read exact members, without executing or trusting archive-provided code.
        files = {name: archive.read(name) for name in archive.namelist()}
    for name, raw in files.items():
        assert Path(name).name == name
        (tmp_path / name).write_bytes(raw)
    snapshot = json.loads(files["verifier-input-manifest.json"])
    manifest = json.loads(files["verification-event-manifest.json"])
    comparison = json.loads(files["comparison.json"])
    context, diff = files["verifier-context.md"], files["verifier-pr-diff.patch"]
    validate_capture_byte_inventory(
        snapshot["capture_byte_inventory"], {"context": context, "diff": diff}
    )
    obligations = build_capture_obligation_manifest(context.decode(), full_diff_bytes=diff)
    assert obligations["sufficient"] is False
    assert obligations["gaps"] == snapshot["capture_obligations"]["gaps"]
    assert "acceptance_evidence:artifacts:unavailable" in obligations["gaps"]
    # Replay the production recorder against the unchanged snapshot, rather
    # than only rebuilding obligations in memory. Its emitted contracts must
    # retain all six gaps and exactly bind the original context/diff ranges.
    recorded = record_capture_obligations(
        tmp_path / "verifier-context.md", diff_path=tmp_path / "verifier-pr-diff.patch"
    )
    assert recorded == obligations
    assert len(recorded["gaps"]) == 6
    sidecars = {
        "verifier-capture-obligation-manifest.json": "capture_obligations",
        "verifier-capture-byte-inventory.json": "capture_byte_inventory",
        "verifier-capture-reassembly-contract.json": "capture_reassembly_contract",
    }
    for name, field in sidecars.items():
        assert json.loads((tmp_path / name).read_bytes()) == snapshot[field]
    contract = json.loads((tmp_path / "verifier-capture-reassembly-contract.json").read_bytes())
    assert contract["sufficient"] is False
    assert [gap["value"] for gap in contract["gaps"]] == recorded["gaps"]
    metadata = event_metadata(tmp_path / "verification-event-manifest.json")
    assert metadata["verification_event"] == manifest["verification_event"]
    assert metadata["assessment_identity"] == manifest["assessment_identity"]
    assert (
        metadata["verification_event"]["event_id"]
        == "872cfa6b5cc9d664566f1aa1ecb5dbeaf303b27bd5a96288414318455a343e9c"
    )
    rows, verdict, available = validated_payload(comparison, mode="compare")
    assert verdict == "UNVERIFIABLE_INPUT"
    assert available is False
    assert len(rows) == 2
    for row, retained in zip(rows, comparison["results"], strict=True):
        assert (row["provider_used"], row["model"]) == (
            retained["provider_used"],
            retained["model"],
        )
        assert row["used_llm"] is False
        assert row["verdict"] == "UNVERIFIABLE_INPUT"
        assert row["files_reviewed"] is None
        assert row["files_not_reviewed"] == [
            "scripts/ci_history.py",
            "tests/scripts/test_ci_history.py",
        ]
    # The exact local archive cannot supply the native origin refused by the JS
    # collector. Exercise recovery without manufacturing that missing authority.
    source = tmp_path / "verification-recovery-source.zip"
    source.write_bytes(original)
    with pytest.raises(FileNotFoundError, match="verification-recovery-origin.json"):
        revalidate_retained(directory=tmp_path)
    # The operational revalidation CLI must fail before publishing any verdict
    # to Actions, even after its separate recorder successfully emitted files.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["verifier_event_recovery.py", "--revalidate-retained"])
    output_path = tmp_path / "actions-output"
    original_output = "existing_output=preserved\n"
    output_path.write_text(original_output)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
    with pytest.raises(FileNotFoundError, match="verification-recovery-origin.json"):
        verifier_event_recovery.main()
    output = capsys.readouterr()
    assert output.out == output.err == ""
    assert output_path.read_text() == original_output
    assert not (tmp_path / "verification-revalidation-receipt.json").exists()
    assert not (tmp_path / "retained-source").exists()
    assert {entry.name for entry in tmp_path.iterdir()} == (
        set(files) | set(sidecars) | {source.name, output_path.name}
    )
    assert all((tmp_path / name).read_bytes() == raw for name, raw in files.items())
    assert source.read_bytes() == original
    assert archive_path.read_bytes() == original


@pytest.mark.parametrize(
    "defect", [None, "missing_archive", "missing_member", "tampered", "occurrence"]
)
def test_exact_4509_raw_archive_admission_clears_only_its_own_gap(tmp_path, monkeypatch, defect):
    from scripts.langchain import pr_verifier

    def unexpected_provider(*args, **kwargs):
        pytest.fail("Raw capture admission must never construct a provider client")

    for name in ("get_llm_client", "get_llm_clients", "_get_llm_client", "_get_llm_clients"):
        monkeypatch.setattr(pr_verifier, name, unexpected_provider)
    monkeypatch.setenv("VERIFIER_SEMANTIC_MODE", "0")
    monkeypatch.delenv("VERIFIER_EVIDENCE_CAPTURE_DIR", raising=False)
    fixtures = Path(__file__).resolve().parents[2] / ".github/scripts/__tests__/fixtures"
    capture_path = fixtures / "verifier-4509-capture.zip"
    original_capture = capture_path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(original_capture)) as retained:
        context = retained.read("verifier-context.md").decode()
        diff = retained.read("verifier-pr-diff.patch")
        event = retained.read("verification-event-manifest.json")
        comparison = retained.read("comparison.json")
    baseline = build_capture_obligation_manifest(context, full_diff_bytes=diff)
    coverage = parse_context_source_coverage(context)
    record = next(
        row for row in coverage["artifact_capture_inventory"] if row["artifact_id"] == 13556090021
    )
    assert record["status"] == "incomplete"
    artifact_path = fixtures / "verifier-4509-selftest-autofix-3.13.zip"
    archive = artifact_path.read_bytes()
    assert sha(archive) == record["archive_sha256"]
    assert len(archive) == record["archive_bytes"]
    archive_sidecar = tmp_path / f"{sha(archive)}.zip"
    archive_sidecar.write_bytes(archive)
    identity = json.loads((fixtures / "verifier-4509-capture-identity.json").read_bytes())
    expected_inputs = {}
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        assert zipped.namelist() == [row["name"] for row in identity["first_archive_members"]]
        record["members"] = []
        for index, expected in enumerate(identity["first_archive_members"]):
            raw = zipped.read(expected["name"])
            assert len(raw) == expected["bytes"]
            assert sha(raw) == expected["sha256"]
            (tmp_path / f"{sha(raw)}.txt").write_bytes(raw)
            record["members"].append(
                {
                    "name": expected["name"],
                    "occurrence": index,
                    "status": "captured",
                    "raw_bytes": len(raw),
                    "raw_sha256": sha(raw),
                    "encoding": "utf-8",
                }
            )
            expected_inputs[f"artifact:{record['run_id']}:{record['artifact_id']}:{index}"] = raw
    record["status"] = "captured"
    member_sidecar = tmp_path / f"{record['members'][1]['raw_sha256']}.txt"
    if defect == "missing_archive":
        archive_sidecar.unlink()
    elif defect == "missing_member":
        member_sidecar.unlink()
    elif defect == "tampered":
        member_sidecar.write_bytes(b"x" * record["members"][1]["raw_bytes"])
    elif defect == "occurrence":
        record["members"][1]["occurrence"] = 0

    # A local derived inventory tests raw-byte admission only. It is never
    # written over the retained context, event or native recovery origin.
    block = re.search(r"## Context source coverage\n.*?```json\n(.*?)\n```", context, re.S)
    derived_context = context[: block.start(1)] + json.dumps(coverage) + context[block.end(1) :]
    assert build_capture_obligation_manifest(derived_context, full_diff_bytes=diff) == baseline
    monkeypatch.setenv("VERIFIER_EVIDENCE_CAPTURE_DIR", str(tmp_path))
    monkeypatch.setenv("VERIFIER_SEMANTIC_MODE", "1")
    result = build_capture_obligation_manifest(derived_context, full_diff_bytes=diff)
    assert result["sufficient"] is False
    if defect is None:
        inputs, recovered = load_artifact_capture(coverage, tmp_path)
        assert inputs == expected_inputs
        assert recovered == {"Run 42326161711: selftest-autofix-3.13"}
        recovered_gap = "acceptance_evidence:Run 42326161711: selftest-autofix-3.13:truncated"
        assert result["gaps"] == [gap for gap in baseline["gaps"] if gap != recovered_gap]
    else:
        with pytest.raises((OSError, ValueError)):
            load_artifact_capture(coverage, tmp_path)
        assert set(baseline["gaps"]) <= set(result["gaps"])
        assert any(gap.startswith("artifact_raw_capture:") for gap in result["gaps"])

    # Exercise the real semantic comparison preflight, beyond the raw loader.
    # Partial byte recovery must never reach client construction or generation.
    monkeypatch.setattr(pr_verifier, "_build_semantic_clients", unexpected_provider)
    monkeypatch.setattr(pr_verifier, "_invoke_llm", unexpected_provider)
    monkeypatch.setenv("PR_HEAD_SHA", record["head_sha"])
    monkeypatch.delenv("VERIFIER_SEMANTIC_KEY_PATH", raising=False)
    semantic = pr_verifier._semantic_capture(derived_context, diff.decode())
    assert semantic["manifest"] == result
    assert semantic["resource_admitted"] is False
    assert set(result["gaps"]) <= set(semantic["gaps"])
    expected_hashes = {"context": sha(derived_context.encode()), "diff": sha(diff)}
    if defect is None:
        expected_hashes.update({name: sha(raw) for name, raw in expected_inputs.items()})
    assert semantic["raw_inputs"] == expected_hashes
    blocked = pr_verifier.evaluate_pr_multiple(derived_context, diff.decode())
    assert len(blocked) == 1
    assert blocked[0].used_llm is False
    assert blocked[0].verdict != "PASS"
    assert "complete capture is unavailable" in blocked[0].error
    assert blocked.semantic_acceptance["capture"] == semantic
    assert blocked.semantic_acceptance["admission"]["verdict"] == "CONCERNS"
    assert "execution" not in blocked.semantic_acceptance

    # Persist the derived capture through the existing provider-free recorder.
    # Its byte ranges must bind the recovered members without clearing other
    # required gaps or allowing the original snapshot to be silently replaced.
    derived = tmp_path / "derived"
    derived.mkdir()
    context_path = derived / "verifier-context.md"
    context_path.write_bytes(derived_context.encode())
    diff_path = derived / "verifier-pr-diff.patch"
    diff_path.write_bytes(diff)
    snapshot_path = derived / "verifier-input-manifest.json"
    with zipfile.ZipFile(capture_path) as retained:
        original_snapshot = retained.read("verifier-input-manifest.json")
    snapshot_path.write_bytes(original_snapshot)
    with pytest.raises(ValueError, match="context does not match the verifier input snapshot"):
        record_capture_obligations(context_path, diff_path=diff_path)
    assert snapshot_path.read_bytes() == original_snapshot
    assert {path.name for path in derived.iterdir()} == {
        context_path.name,
        diff_path.name,
        snapshot_path.name,
    }
    snapshot_path.unlink()
    recorded = record_capture_obligations(context_path, diff_path=diff_path)
    assert recorded == result
    assert (
        json.loads((derived / "verifier-capture-obligation-manifest.json").read_bytes()) == result
    )
    inventory = json.loads((derived / "verifier-capture-byte-inventory.json").read_bytes())
    admitted_inputs = {"context": derived_context.encode(), "diff": diff}
    if defect is None:
        admitted_inputs.update(expected_inputs)
    validate_capture_byte_inventory(inventory, admitted_inputs)
    contract = json.loads((derived / "verifier-capture-reassembly-contract.json").read_bytes())
    assert contract["sufficient"] is False
    assert [gap["value"] for gap in contract["gaps"]] == result["gaps"]
    assert contract["required_range_ids"] == [
        part["id"] for entry in inventory["inputs"] for part in entry["ranges"]
    ]
    assert context_path.read_bytes() == derived_context.encode()
    assert diff_path.read_bytes() == diff
    assert not snapshot_path.exists()

    # No original event or provider verdict is upgraded by this partial recovery.
    with zipfile.ZipFile(capture_path) as retained:
        assert retained.read("verification-event-manifest.json") == event
        assert retained.read("comparison.json") == comparison
        assert retained.read("verifier-context.md").decode() == context
    assert capture_path.read_bytes() == original_capture
    assert artifact_path.read_bytes() == archive
    assert not (tmp_path / "verification-recovery-origin.json").exists()
    assert not (tmp_path / "verification-revalidation-receipt.json").exists()


def setup_case(tmp_path, monkeypatch, *, mode="evaluate"):
    head, merge = "a" * 40, "b" * 40
    request = {"schema": "verification-request/v1", "sources": []}
    diff, context, summary = b"diff original", b"authentic original requirements", b"one file"
    material = {
        "schema": "verification-material/v1",
        "code": {"head_sha": head, "evaluated_sha": merge, "diff_sha256": sha(diff)},
    }
    event = {
        "schema": "verification-event/v1",
        "repo": "owner/repo",
        "pr": "7",
        "head_sha": head,
        "evaluated_sha": merge,
        "request_sha256": sha(encoded(request)),
        "material_sha256": sha(encoded(material)),
    }
    event["event_id"] = sha(encoded(event))
    assessment = {
        "mode": mode,
        "provider": "anthropic" if mode == "evaluate" else "",
        "model": "m",
        "model2": "" if mode == "evaluate" else "n",
        "canonical": True,
    }
    manifest = {
        "verification_event": event,
        "assessment_identity": assessment,
        "request": request,
        "material": material,
    }
    row = {
        "verdict": "PASS",
        "concerns": [],
        "summary": "Complete retained review",
        "used_llm": True,
        "provider_used": "anthropic",
        "model": "m",
    }
    payload = (
        row
        if mode == "evaluate"
        else {"results": [row, {**row, "provider_used": "openai", "model": "n"}]}
    )
    stem = "evaluation" if mode == "evaluate" else "comparison"
    raw = encoded(payload)
    snapshot = {
        "schema": "workflows-verifier-input-snapshot/v1",
        "capture_kind": "production",
        "repository": "owner/repo",
        "pr": 7,
        "merge_sha": merge,
        "mode": mode,
        "source_run_id": "10",
        "context_sha256": sha(context),
        "diff_sha256": sha(diff),
        "diff_summary_sha256": sha(summary),
    }
    snapshot_raw = encoded(snapshot)
    receipt = {
        "schema": f"workflows-verifier-{stem}-execution/v1",
        "mode": mode,
        "status": "invalid_output",
        "exit_code": 0,
        "validation_error_type": "ImportError",
        "decision_available": False,
        "repository": "owner/repo",
        "source_run_id": "10",
        "source_run_attempt": "1",
        "input_manifest": {"sha256": sha(snapshot_raw)},
        "outputs": {
            f"{stem}.json": {
                "sha256": sha(raw),
                "bytes": len(raw),
                "original_complete": True,
                "truncated": False,
            }
        },
    }
    blobs = {
        f"{stem}.json": raw,
        f"{stem}-execution.json": encoded(receipt),
        "verifier-input-manifest.json": snapshot_raw,
        "verification-event-manifest.json": encoded(manifest),
        "verifier-context.md": context,
        "verifier-pr-diff.patch": diff,
        "verifier-diff-summary.md": summary,
    }
    origin = {
        "schema": "workflows-retained-origin/v1",
        "repository": "owner/repo",
        "current_run_id": "20",
        "source_run_id": "10",
        "source_run_attempt": "1",
        "artifact_id": 30,
        "helper_sha": "c" * 40,
        "validator_sha256": "d" * 64,
        "verification_event": event,
        "assessment_identity": assessment,
        "recovery_key": "e" * 64,
    }
    (tmp_path / "verification-event-manifest.json").write_bytes(encoded(manifest))
    for key, value in {
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_RUN_ID": "20",
        "GITHUB_RUN_ATTEMPT": "1",
        "VERIFICATION_RECOVERY": json.dumps({"run_id": 10, "run_attempt": 1, "artifact_id": 30}),
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("VERIFIER_EVIDENCE_PROFILE", raising=False)
    write_archive(tmp_path, origin, blobs)
    return origin, blobs, stem


def write_archive(directory, origin, blobs, *, duplicate=False):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, raw in blobs.items():
            archive.writestr(name, raw)
        if duplicate:
            with pytest.warns(UserWarning, match="Duplicate name"):
                archive.writestr("evaluation.json", b"{}")
    raw = stream.getvalue()
    origin.update(archive_bytes=len(raw), archive_sha256=sha(raw))
    (directory / "verification-recovery-source.zip").write_bytes(raw)
    (directory / "verification-recovery-origin.json").write_bytes(encoded(origin))


@pytest.mark.parametrize("mode", ["evaluate", "compare"])
def test_invalid_wrapper_revalidates_without_generation_and_preserves_originals(
    tmp_path, monkeypatch, mode
):
    origin, blobs, stem = setup_case(tmp_path, monkeypatch, mode=mode)
    receipt = revalidate_retained(directory=tmp_path)
    assert receipt["status"] == "completed"
    assert receipt["retained_revalidation"]["provider_generation_performed"] is False
    retained = tmp_path / "retained-source" / origin["archive_sha256"]
    assert all((retained / name).read_bytes() == raw for name, raw in blobs.items())
    assert (
        json.loads((retained / f"{stem}-execution.json").read_bytes())["status"] == "invalid_output"
    )
    assert verify_revalidation_admission(receipt, directory=tmp_path)
    event = origin["verification_event"]
    identity = {key: event[key] for key in ["repo", "pr", "head_sha", "evaluated_sha"]}
    identity.update(run_id="20", run_attempt="1")
    result = admitted_decision(
        tmp_path / f"{stem}.json",
        tmp_path / f"{stem}-execution.json",
        identity,
        mode=mode,
        ci_failed="false",
    )
    assert result["verdict"] == "PASS"
    assert result["retained_revalidation"]["source_run_id"] == "10"
    monkeypatch.setenv("GITHUB_RUN_ID", "21")
    assert not verify_revalidation_admission(receipt, directory=tmp_path)


@pytest.mark.parametrize(
    "mutation",
    [
        "tamper",
        "missing",
        "duplicate",
        "path",
        "truncated",
        "input",
        "foreign",
        "event",
        "assessment",
        "selector",
        "raw_error",
    ],
)
def test_bad_source_never_creates_current_receipt(tmp_path, monkeypatch, mutation):
    origin, blobs, stem = setup_case(tmp_path, monkeypatch)
    if mutation == "missing":
        del blobs["verifier-context.md"]
    elif mutation == "path":
        blobs["../overwrite"] = b"untrusted"
    elif mutation in {"truncated", "input", "foreign", "raw_error"}:
        receipt = json.loads(blobs[f"{stem}-execution.json"])
        if mutation == "truncated":
            receipt["outputs"][f"{stem}.json"]["truncated"] = True
        elif mutation == "input":
            receipt["input_manifest"]["sha256"] = "0" * 64
        elif mutation == "foreign":
            receipt["repository"] = "foreign/repo"
        else:
            data = json.loads(blobs[f"{stem}.json"])
            data.update(error="provider unavailable", used_llm=False)
            blobs[f"{stem}.json"] = encoded(data)
        blobs[f"{stem}-execution.json"] = encoded(receipt)
    elif mutation in {"event", "assessment"}:
        original = json.loads(blobs["verification-event-manifest.json"])
        if mutation == "event":
            original["verification_event"]["request_sha256"] = "f" * 64
        else:
            original["assessment_identity"]["model"] = "another-model"
        blobs["verification-event-manifest.json"] = encoded(original)
    elif mutation == "selector":
        monkeypatch.setenv(
            "VERIFICATION_RECOVERY", '{"run_id":10,"run_attempt":2,"artifact_id":30}'
        )
    write_archive(tmp_path, origin, blobs, duplicate=mutation == "duplicate")
    if mutation == "tamper":
        with (tmp_path / "verification-recovery-source.zip").open("ab") as stream:
            stream.write(b"changed")
    with pytest.raises((ValueError, KeyError)):
        revalidate_retained(directory=tmp_path)
    assert not (tmp_path / f"{stem}-execution.json").exists()


def test_authored_workflow_presence_guard_excludes_all_generation_routes():
    workflow = yaml.safe_load(Path(".github/workflows/reusable-agents-verifier.yml").read_text())
    steps = workflow["jobs"]["verifier"]["steps"]
    generation = [
        "Run LLM evaluation",
        "Run multi-provider comparison",
        "Check provider secrets",
        "Validate Codex auth for checkbox/compare modes",
        "Setup Codex auth",
        "Install Codex CLI",
        "Shadow candidate verifier judges (recorded only; never posted, never counted)",
    ]
    for name in generation:
        step = next(step for step in steps if step["name"] == name)
        assert "inputs.verification_recovery == ''" in step["if"]
    recovery = next(step for step in steps if step.get("id") == "retained_recovery")
    assert "--revalidate-retained" in recovery["run"]
    assert not any(
        "KEY" in key or "SECRET" in key or "TOKEN" in key for key in recovery.get("env", {})
    )


def test_authored_recovery_shell_runs_without_credentials_or_provider_generation(
    tmp_path, monkeypatch
):
    import os
    import subprocess
    import sys

    setup_case(tmp_path, monkeypatch)
    root = Path(__file__).resolve().parents[2]
    (tmp_path / ".workflows-lib").symlink_to(root, target_is_directory=True)
    workflow = yaml.safe_load((root / ".github/workflows/reusable-agents-verifier.yml").read_text())
    step = next(
        step
        for step in workflow["jobs"]["verifier"]["steps"]
        if step.get("id") == "retained_recovery"
    )
    # Count every external generation boundary in the actual authored process.
    # The startup guard is test-only; it records and refuses even an attempted
    # network connection, so absent credentials cannot hide a provider attempt.
    guard = tmp_path / "guard"
    guard.mkdir()
    counter = tmp_path / "provider-network-attempts"
    (guard / "sitecustomize.py").write_text(
        "import os,sys\nfrom pathlib import Path\n"
        "def audit(event,args):\n"
        " if event in {'socket.connect','socket.getaddrinfo'}:\n"
        "  Path(os.environ['PROVIDER_COUNTER']).write_text(event)\n"
        "  raise RuntimeError('provider/network forbidden during recovery')\n"
        "sys.addaudithook(audit)\n"
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(secret in key for secret in ["API_KEY", "TOKEN", "SECRET", "CLAUDE_API"])
    }
    env.update(
        PYTHONPATH=str(guard),
        PROVIDER_COUNTER=str(counter),
        GITHUB_OUTPUT=str(tmp_path / "outputs"),
    )
    # Pin this test's interpreter while executing the authored shell verbatim.
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "python3").symlink_to(sys.executable)
    env["PATH"] = str(bindir) + os.pathsep + env["PATH"]
    result = subprocess.run(
        ["bash", "-c", step["run"]],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "verdict=PASS" in (tmp_path / "outputs").read_text()
    assert not counter.exists()
    receipt = json.loads((tmp_path / "verification-revalidation-receipt.json").read_text())
    assert receipt["retained_revalidation"]["provider_generation_performed"] is False


@pytest.mark.parametrize("ci_failed", ["false", "true"])
def test_authored_recovery_publisher_event_and_unified_share_current_admission(
    tmp_path, monkeypatch, ci_failed
):
    import os
    import re
    import subprocess
    import sys

    from tests.workflows.test_repeat_verification_lifecycle import authored, run_state_step

    origin, _, _ = setup_case(tmp_path, monkeypatch)
    revalidate_retained(directory=tmp_path)
    root = Path(__file__).resolve().parents[2]
    (tmp_path / ".workflows-lib").symlink_to(root, target_is_directory=True)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "python3").symlink_to(sys.executable)
    event = origin["verification_event"]
    env = {
        **os.environ,
        "PATH": str(bindir) + os.pathsep + os.environ["PATH"],
        "PR_NUMBER": event["pr"],
        "PR_HEAD_SHA": event["head_sha"],
        "EVALUATED_SHA": event["evaluated_sha"],
        "CI_FAILED": ci_failed,
        "VERIFIER_MODE": "evaluate",
    }
    script = authored("Publish retained revalidation through verifier lifecycle")["with"]["script"]
    runner = """
const fs=require('fs'); const input=JSON.parse(fs.readFileSync(0,'utf8'));
const comments=[],outputs={};
const github={rest:{pulls:{get:async()=>({data:{merged:true,head:{sha:process.env.PR_HEAD_SHA},merge_commit_sha:process.env.EVALUATED_SHA}})},issues:{listComments:async()=>({data:[],headers:{}}),createComment:async row=>{comments.push(row);return {data:{id:5}};}}}};
const context={runId:Number(process.env.GITHUB_RUN_ID)};
const core={setOutput:(key,value)=>{outputs[key]=value;}};
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('require','github','context','core',input.script)(require,github,context,core)
.then(()=>process.stdout.write(JSON.stringify({comments,outputs}))).catch(error=>{console.error(error);process.exitCode=1;});
"""
    published = subprocess.run(
        ["node", "-e", runner],
        input=json.dumps({"script": script}),
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert published.returncode == 0, published.stderr
    result = json.loads(published.stdout)
    assert result["outputs"]["published"] == "true"
    report = result["comments"][0]["body"]
    expected = "PASS" if ci_failed == "false" else "CONCERNS"
    assert f"**Verdict:** {expected}" in report
    decision = json.loads(
        re.search(r"<!-- verifier-corpus-decision/v1 (\{[^\n]+\}) -->", report)[1]
    )
    assert decision["verdict"] == ("PASS" if ci_failed == "false" else "NON_PASS")
    assert decision["verification_event"] == event
    assert not decision.get("predecessor_event_id")
    terminal = run_state_step(
        tmp_path, "Record verification event terminal", posted=True, extra_env=env
    )
    assert terminal["outputs"]["complete"] == "true"
    unified = authored("Set unified verdict")["run"]
    values = {
        "steps.verdict.outputs.verdict": "",
        "steps.llm_evaluate.outputs.verdict": "",
        "steps.llm_compare.outputs.verdict": "",
        "steps.context.outputs.ci_failed": ci_failed,
    }
    unified = re.sub(r"\$\{\{\s*(.*?)\s*\}\}", lambda match: values[match[1]], unified)
    env.update(
        RETAINED_RECOVERY_VERDICT="PASS",
        RETAINED_RECOVERY_PUBLISHED="true",
        GITHUB_OUTPUT=str(tmp_path / "unified-output"),
    )
    settled = subprocess.run(
        ["bash", "-c", unified], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30
    )
    assert settled.returncode == 0, settled.stderr
    assert (tmp_path / "unified-output").read_text().strip() == f"verdict={expected}"
    env.update(
        RETAINED_RECOVERY_PUBLISHED="false", GITHUB_OUTPUT=str(tmp_path / "unpublished-output")
    )
    refused = subprocess.run(
        ["bash", "-c", unified], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30
    )
    assert refused.returncode == 0, refused.stderr
    assert (tmp_path / "unpublished-output").read_text().strip() == "verdict=UNVERIFIABLE_INPUT"


def test_actual_comparison_receipt_shape_joins_complete_authenticated_archive(
    tmp_path, monkeypatch
):
    origin, blobs, stem = setup_case(tmp_path, monkeypatch, mode="compare")
    receipt = json.loads(blobs[f"{stem}-execution.json"])
    # The authored pre-recovery compare producer has result hash/bytes but no
    # input_manifest/transport flags. The authenticated whole archive supplies
    # that missing cross-member join; every original input hash still verifies.
    receipt.pop("input_manifest")
    receipt["outputs"][f"{stem}.json"].pop("original_complete")
    receipt["outputs"][f"{stem}.json"].pop("truncated")
    blobs[f"{stem}-execution.json"] = encoded(receipt)
    write_archive(tmp_path, origin, blobs)
    result = revalidate_retained(directory=tmp_path)
    assert result["verdict"] == "PASS"
    retained = tmp_path / "retained-source" / origin["archive_sha256"]
    assert (retained / f"{stem}-execution.json").read_bytes() == blobs[f"{stem}-execution.json"]


def test_unicode_required_material_uses_the_actual_collector_canonical_digest(
    tmp_path, monkeypatch
):
    import subprocess

    origin, blobs, _ = setup_case(tmp_path, monkeypatch)
    manifest = json.loads(blobs["verification-event-manifest.json"])
    material = manifest["material"]
    material["required_evidence"] = [
        {
            "kind": "artifact_member",
            "run_id": 5,
            "artifact_id": 6,
            "path": "résumé-評価.txt",
            "raw_sha256": "a" * 64,
        }
    ]
    root = Path(__file__).resolve().parents[2]
    js = "const fs=require('fs'); const {digest}=require('./.github/scripts/verification_event.js'); process.stdout.write(digest(JSON.parse(fs.readFileSync(0,'utf8'))));"
    material_sha = subprocess.check_output(
        ["node", "-e", js], input=json.dumps(material), cwd=root, text=True
    )
    event = manifest["verification_event"]
    event["material_sha256"] = material_sha
    event.pop("event_id")
    event["event_id"] = sha(encoded(event))
    origin["verification_event"] = event
    blobs["verification-event-manifest.json"] = encoded(manifest)
    (tmp_path / "verification-event-manifest.json").write_bytes(encoded(manifest))
    write_archive(tmp_path, origin, blobs)
    result = revalidate_retained(directory=tmp_path)
    assert result["verdict"] == "PASS"


@pytest.mark.parametrize("verdict", ["CONCERNS", "FAIL"])
def test_recovered_report_keeps_actionable_findings_without_summary(tmp_path, monkeypatch, verdict):
    origin, blobs, stem = setup_case(tmp_path, monkeypatch)
    payload = json.loads(blobs[f"{stem}.json"])
    payload.update(
        verdict=verdict,
        summary=None,
        concerns=["Repair the login timeout", "Retain proof <without forging markers>"],
        input_coverage={"files_total": 13, "files_complete": 13},
    )
    raw = encoded(payload)
    blobs[f"{stem}.json"] = raw
    receipt = json.loads(blobs[f"{stem}-execution.json"])
    receipt["outputs"][f"{stem}.json"].update(sha256=sha(raw), bytes=len(raw))
    blobs[f"{stem}-execution.json"] = encoded(receipt)
    write_archive(tmp_path, origin, blobs)
    result = revalidate_retained(directory=tmp_path)
    assert result["verdict"] == verdict
    report = (tmp_path / f"{stem}-comment.md").read_text()
    assert f"**Verdict:** {verdict}" in report
    assert "files reviewed 13 of 13" in report
    assert "- Repair the login timeout" in report
    assert "- Retain proof &lt;without forging markers&gt;" in report
    assert (
        tmp_path / "retained-source" / origin["archive_sha256"] / f"{stem}.json"
    ).read_bytes() == raw


@pytest.mark.parametrize(
    ("publication_outcome", "publication_effect", "retryable"),
    [
        ("skipped", "", True),
        ("failure", "none", True),
        ("failure", "uncertain", False),
        ("success", "none", False),
    ],
)
def test_authored_failed_recovery_can_retry_only_before_publication(
    tmp_path, monkeypatch, publication_outcome, publication_effect, retryable
):
    import os
    import re
    import subprocess

    from tests.workflows.test_repeat_verification_lifecycle import run_state_step

    origin, _, _ = setup_case(tmp_path, monkeypatch)
    manifest_path = tmp_path / "verification-event-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    key = "c" * 64
    manifest["retained_revalidation"] = {"schema": "retained-revalidation/v1", "recovery_key": key}
    manifest_path.write_text(json.dumps(manifest))
    env = {
        "GITHUB_REPOSITORY": "owner/repo",
        "RECOVERY_PUBLICATION_OUTCOME": publication_outcome,
        "RECOVERY_PUBLICATION_EFFECT": publication_effect,
    }
    pending = run_state_step(tmp_path, "Record verification event pending", extra_env=env)
    terminal = run_state_step(
        tmp_path, "Record verification event terminal", outcome="failure", extra_env=env
    )
    state = json.loads(re.search(r"(\{.*\}) -->", terminal["comments"][0]["body"])[1])
    assert state["retryable"] is retryable
    assert state["retained_revalidation"]["recovery_key"] == key
    comments = [
        {
            "author": "github-actions[bot]",
            "url": f"https://github.com/owner/repo/pull/7#issuecomment-{index}",
            "body": item["body"],
        }
        for index, item in enumerate([*pending["comments"], *terminal["comments"]], 1)
    ]
    root = Path(__file__).resolve().parents[2]
    script = """
const fs=require('fs'); const data=JSON.parse(fs.readFileSync(0,'utf8'));
const {guardRecoveryHistory}=require('./.github/scripts/verifier_pending_execution.js');
try {process.stdout.write(guardRecoveryHistory(data));} catch {process.stdout.write('blocked');}
"""
    result = subprocess.check_output(
        ["node", "-e", script],
        input=json.dumps(
            {
                "event": origin["verification_event"],
                "assessment": manifest["assessment_identity"],
                "comments": comments,
                "sourceRun": 10,
                "currentRun": 21,
                "recoveryKey": key,
            }
        ),
        text=True,
        cwd=root,
        env=os.environ,
    )
    assert result == ("ready" if retryable else "blocked")
