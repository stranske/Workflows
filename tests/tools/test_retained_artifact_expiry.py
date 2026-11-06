"""Expired #4231/#4235 archives are rejected without treating a marker as bytes."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

from tools.verifier_event_recovery import (
    AUTHENTICATED_RETAINED_READBACK,
    EXPLICIT_EXPIRED_ARTIFACT_REJECTION,
    IDENTITY_MISMATCH,
    INCOMPLETE_OBSERVATION_SET,
    INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE,
    MISSING_STATUS,
    classify_retained_artifact_outcome,
    classify_retained_artifact_report,
    inspect_digest_bound_archive,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/verification_input_repair/2026-11-06-collector-observations.json"
SCRIPT = ROOT / "tools/verifier_event_recovery.py"


def _observation(**overrides):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    row = dict(payload["observations"][0])
    row.update(overrides)
    return row


def _zip(member: bytes = b"retained-result") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("comparison.json", member)
    return buffer.getvalue()


def test_live_404_pair_is_explicit_expiry_without_admission_or_provider_calls():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    report = classify_retained_artifact_report(payload)
    assert report["operational_outcome"] == EXPLICIT_EXPIRED_ARTIFACT_REJECTION
    assert report["provider_calls"] == 0
    assert report["provider_generation_performed"] is False
    assert report["context"]["provider_calls_during_check"] == 0
    assert report["context"]["existing_collector_command"].endswith(
        "tools/verifier_event_recovery.py --revalidate-retained"
    )
    assert "two repair attempts" in report["context"]["stop_rule"]
    assert report["context"]["existing_behavior_before_change"]["artifact_digest_equality"]
    assert (
        "ca33a4b6472836a494f4f6d53d96a72ed21b8b64"
        in report["context"]["source_revision_before_change"]
    )
    assert len(report["results"]) == 2
    for row in report["results"]:
        assert row["artifact_outcome"] == EXPLICIT_EXPIRED_ARTIFACT_REJECTION
        assert row["authenticated_readback"] is False
        assert row["native_admission_succeeded"] is False
        assert row["original_event_accepting"] is False
        assert row["marker_published"] is True
        assert row["marker_authenticates_archive"] is False
        assert row["actions_archive"]["http_status"] == 404
        assert row["actions_archive"]["available"] is False
        assert row["local_archive"]["available"] is False
        assert row["owner_decision"]["fresh_provider_evaluation"] is False
        assert row["owner_decision"]["date"] == "2026-11-06"
        assert row["collected_subject"]["event_id"]


def test_marker_and_missing_counts_are_not_authenticated_readback():
    row = classify_retained_artifact_outcome(
        _observation(provider_calls=None, original_event_accepting=None)
    )
    assert row["artifact_outcome"] == EXPLICIT_EXPIRED_ARTIFACT_REJECTION
    assert row["authenticated_readback"] is False
    assert row["evidence_complete"] is False
    report = classify_retained_artifact_report({"observations": [_observation(), _observation()]})
    assert report["operational_outcome"] == INCOMPLETE_OBSERVATION_SET


def test_identity_mismatch_and_missing_status_are_not_expiry():
    mismatch = classify_retained_artifact_outcome(_observation(artifact_id=1))
    assert mismatch["outcome"] == IDENTITY_MISMATCH
    assert mismatch["artifact_outcome"] != EXPLICIT_EXPIRED_ARTIFACT_REJECTION
    missing = classify_retained_artifact_outcome(
        _observation(artifact_http_status=None, artifact_expired=None)
    )
    assert missing["artifact_outcome"] == MISSING_STATUS
    contradictory = classify_retained_artifact_outcome(
        _observation(artifact_http_status=404, artifact_expired=False)
    )
    assert contradictory["artifact_outcome"] == "contradictory artifact status"


def test_expired_flag_rejects_and_wrong_bytes_do_not_authenticate():
    expired = classify_retained_artifact_outcome(
        _observation(artifact_http_status=200, artifact_expired=True)
    )
    assert expired["artifact_outcome"] == EXPLICIT_EXPIRED_ARTIFACT_REJECTION
    assert expired["authenticated_readback"] is False
    raw = _zip()
    digest = hashlib.sha256(raw).hexdigest()
    member = hashlib.sha256(b"retained-result").hexdigest()
    matched = inspect_digest_bound_archive(
        raw, digest, [{"path": "comparison.json", "raw_sha256": member}]
    )
    assert matched["authenticated"] is True
    assert matched["reason"] == "digest_match"
    wrong = classify_retained_artifact_outcome(
        _observation(
            artifact_http_status=200,
            artifact_expired=False,
            actions_archive_bytes=raw,
            admission_result={
                "succeeded": True,
                "evidence_source": "native_admission",
                "event_id": "a" * 64,
                "predecessor_event_id": "b" * 64,
                "original_event_accepting": False,
            },
        )
    )
    assert wrong["artifact_outcome"] == "unauthenticated retained evidence"
    assert wrong["authenticated_readback"] is False
    assert wrong["native_admission_succeeded"] is False
    assert wrong["actions_archive"]["reason"] == "digest_mismatch"
    assert wrong["actions_archive"]["sha256"] == digest


def test_matching_actions_bytes_authenticate_only_with_real_admission_evidence(monkeypatch):
    raw = _zip()
    digest = hashlib.sha256(raw).hexdigest()
    member = hashlib.sha256(b"retained-result").hexdigest()
    from tools import verifier_event_recovery as recovery

    known = dict(recovery.KNOWN_RETAINED_ARTIFACTS[6390994169])
    known["published_archive_sha256"] = digest
    monkeypatch.setitem(recovery.KNOWN_RETAINED_ARTIFACTS, 6390994169, known)
    admitted = recovery.classify_retained_artifact_outcome(
        _observation(
            published_archive_sha256=digest,
            artifact_http_status=200,
            artifact_expired=False,
            actions_archive_bytes=raw,
            member_claims=[{"path": "comparison.json", "raw_sha256": member}],
            admission_result={
                "succeeded": True,
                "evidence_source": "native_admission",
                "event_id": "a" * 64,
                "predecessor_event_id": "b" * 64,
                "original_event_accepting": False,
            },
        )
    )
    assert admitted["outcome"] == AUTHENTICATED_RETAINED_READBACK
    assert admitted["authenticated_readback"] is True
    assert admitted["native_admission_succeeded"] is True
    assert admitted["owner_decision"] is None
    mismatched_member = recovery.classify_retained_artifact_outcome(
        _observation(
            published_archive_sha256=digest,
            artifact_http_status=200,
            artifact_expired=False,
            actions_archive_bytes=raw,
            member_claims=[{"path": "comparison.json", "raw_sha256": "e" * 64}],
        )
    )
    assert mismatched_member["authenticated_readback"] is False
    assert mismatched_member["actions_archive"]["reason"] == "member_digest_mismatch"


def test_local_archive_is_recorded_without_assuming_it_exists_or_replacing_404():
    raw = _zip()
    digest = hashlib.sha256(raw).hexdigest()
    absent = classify_retained_artifact_outcome(_observation(local_archive_path="missing.zip"))
    assert absent["local_archive"]["available"] is False
    assert absent["local_archive"]["reason"] == "absent"
    assert absent["authenticated_readback"] is False
    directory = Path(__file__).parent
    archive = directory / "not-written"
    assert not archive.exists()
    report = inspect_digest_bound_archive(None, digest)
    assert report["available"] is False
    mismatched = inspect_digest_bound_archive(raw, "c" * 64)
    assert mismatched["authenticated"] is False
    assert mismatched["reason"] == "digest_mismatch"
    unsafe = io.BytesIO()
    with zipfile.ZipFile(unsafe, "w") as opened:
        opened.writestr("nested/comparison.json", b"retained-result")
    unsafe_report = inspect_digest_bound_archive(
        unsafe.getvalue(),
        hashlib.sha256(unsafe.getvalue()).hexdigest(),
        [{"path": "nested/comparison.json", "raw_sha256": "d" * 64}],
    )
    assert unsafe_report["reason"] == "member_authentication_failed"
    bounded = inspect_digest_bound_archive(b"x" * 8388609, digest)
    assert bounded["reason"] == "archive_byte_bound"


def test_local_digest_mismatch_does_not_authenticate_a_404(tmp_path: Path):
    raw = _zip()
    archive = tmp_path / "archive.zip"
    archive.write_bytes(raw)
    link = tmp_path / "link.zip"
    link.symlink_to(archive)
    row = classify_retained_artifact_outcome(_observation(local_archive_path=str(archive)))
    assert row["local_archive"]["available"] is True
    assert row["local_archive"]["authenticated"] is False
    assert row["local_archive"]["reason"] == "digest_mismatch"
    assert row["artifact_outcome"] == EXPLICIT_EXPIRED_ARTIFACT_REJECTION
    assert row["authenticated_readback"] is False
    assert row["marker_authenticates_archive"] is False
    linked = classify_retained_artifact_outcome(_observation(local_archive_path=str(link)))
    assert linked["local_archive"]["available"] is False


def test_provider_call_and_accepting_original_block_the_expiry_phrase():
    second = _observation(
        pr=4235,
        comment_id=6392557346,
        run_id=40155311407,
        artifact_id=12584318436,
        published_archive_sha256="526dcef67f26160ece176b800e7a4d18a2e6d6883d7a2e4294b07570570486ab",
        provider_calls=1,
    )
    called = classify_retained_artifact_report(
        {"observations": [_observation(provider_calls=1), second]}
    )
    assert called["operational_outcome"] == "provider call observed"
    accepting = classify_retained_artifact_outcome(_observation(original_event_accepting=True))
    assert accepting["outcome"] == "original event accepting"
    assert accepting["original_event_accepting"] is True


def test_receipt_404_maps_without_inventing_provider_calls():
    report = classify_retained_artifact_report(
        {
            "receipts": [
                {
                    "pr": 4231,
                    "comment_id": 6390994169,
                    "run_id": 40143755394,
                    "artifact_id": 12579928048,
                    "retained_artifact": {
                        "available": False,
                        "status": 404,
                        "message": "Not Found",
                    },
                    "marker_published": True,
                    "original_event_accepting": False,
                    "provider_calls": 0,
                },
                {
                    "pr": 4235,
                    "proof": [
                        {
                            "url": "https://github.com/stranske/Workflows/pull/4235#issuecomment-6392557346"
                        }
                    ],
                    "run_id": 40155311407,
                    "artifact_id": 12584318436,
                    "artifact_failures": [
                        {"kind": "expired", "detail": "artifact 12584318436 Not Found"}
                    ],
                    "marker_published": True,
                    "original_event_accepting": False,
                    "provider_calls": 0,
                },
            ]
        }
    )
    assert report["operational_outcome"] == EXPLICIT_EXPIRED_ARTIFACT_REJECTION
    assert report["results"][1]["comment_id"] == 6392557346
    assert all(row["provider_calls"] == 0 for row in report["results"])


def test_cli_prints_the_pair_outcome_and_rejects_mixed_modes(tmp_path: Path):
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--classify-retained-artifact", str(FIXTURE)],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["operational_outcome"] == EXPLICIT_EXPIRED_ARTIFACT_REJECTION
    assert report["provider_calls"] == 0
    mixed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--classify-retained-artifact",
            str(FIXTURE),
            "--revalidate-retained",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert mixed.returncode != 0
    invalid = tmp_path / "bad.json"
    invalid.write_text("[]", encoding="utf-8")
    rejected = subprocess.run(
        [sys.executable, str(SCRIPT), "--classify-retained-artifact", str(invalid)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode == 0
    assert (
        json.loads(rejected.stdout)["operational_outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE
    )


def test_digest_gate_transcript_matches_restored_production_bytes():
    gate_path = ROOT / "tests/fixtures/verification_input_repair/2026-11-06-digest-gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    production = (ROOT / ".github/scripts/verification_event.js").read_bytes()
    template = (ROOT / "templates/consumer-repo/.github/scripts/verification_event.js").read_bytes()
    current = hashlib.sha256(production).hexdigest()
    assert production == template
    assert production.count(b"|| found[0].raw_sha256!==claim.raw_sha256") == 1
    assert gate["before_sha256"] == gate["restored_sha256"] == current
    assert gate["broken_exit"] == 1
    assert gate["restored_exit"] == 0
    assert gate["broken_tests"] == [
        "#4231 negative matrix: wrong artifact digest is rejected",
        "#4235 negative matrix: wrong artifact digest is rejected",
    ]
    post = gate["post_delivery_collector"]
    assert post["exit_code"] == 1
    assert post["operational_outcome"] == EXPLICIT_EXPIRED_ARTIFACT_REJECTION
    assert post["provider_calls"] == 0
    assert post["native_admission_succeeded"] is False
    assert post["artifact_http_status"] == {"12579928048": 404, "12584318436": 404}
