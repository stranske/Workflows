"""#4231/#4235 artifact expiry is explicit and is not archive authentication."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from tools.verifier_event_recovery import (
    AUTHENTICATED_RETAINED_READBACK,
    EXPLICIT_EXPIRED_ARTIFACT_REJECTION,
    IDENTITY_MISMATCH,
    KNOWN_RETAINED_ARTIFACTS,
    MISSING_STATUS,
    classify_retained_artifact_outcome,
    classify_retained_artifact_report,
    inspect_digest_bound_archive,
)


def _sha(raw: bytes) -> str:
    import hashlib

    return hashlib.sha256(raw).hexdigest()


def _zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _known(comment_id: int, **over):
    known = KNOWN_RETAINED_ARTIFACTS[comment_id]
    row = {
        "pr": known["pr"],
        "comment_id": comment_id,
        "run_id": known["run_id"],
        "artifact_id": known["artifact_id"],
        "published_archive_sha256": known["published_archive_sha256"],
        "marker_published": True,
        "artifact_http_status": 404,
        "artifact_expired": None,
        "original_event_accepting": False,
        "provider_calls": 0,
        "subject": {"event_id": "a" * 64, "material_sha256": "b" * 64},
        "proof_status": "included",
        "proof_body_sha256": "c" * 64,
    }
    row.update(over)
    return row


def test_marker_and_404_are_expired_rejection_not_readback():
    report = classify_retained_artifact_report(
        {"observations": [_known(6390994169), _known(6392557346)]}
    )
    assert report["operational_outcome"] == EXPLICIT_EXPIRED_ARTIFACT_REJECTION
    assert report["provider_calls"] == 0
    for row in report["results"]:
        assert row["authenticated_readback"] is False
        assert row["native_admission_succeeded"] is False
        assert row["original_event_accepting"] is False
        assert row["provider_generation_performed"] is False
        assert row["marker_authenticates_archive"] is False
        assert row["marker_published"] is True
        assert row["owner_decision"]["date"] == "2026-11-06"
        assert row["owner_decision"]["fresh_provider_evaluation"] is False
        assert row["local_archive"]["available"] is False
        assert row["collected_subject"]["event_id"] == "a" * 64


def test_local_result_bytes_are_not_the_published_archive(tmp_path: Path):
    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures/verification_input_repair/4231-original/comparison.json"
    )
    row = classify_retained_artifact_outcome(_known(6390994169, local_archive_path=str(fixture)))
    assert row["outcome"] == EXPLICIT_EXPIRED_ARTIFACT_REJECTION
    assert row["authenticated_readback"] is False
    assert row["local_archive"]["available"] is True
    assert row["local_archive"]["authenticated"] is False
    assert row["local_archive"]["reason"] == "digest_mismatch"
    missing = classify_retained_artifact_outcome(
        _known(6390994169, local_archive_path=str(tmp_path / "missing.zip"))
    )
    assert missing["local_archive"] == {
        "available": False,
        "authenticated": False,
        "sha256": None,
        "reason": "absent",
    }


def test_matching_local_copy_does_not_authenticate_a_404(tmp_path: Path):
    raw = _zip({"comparison.json": b'{"results":[]}'})
    path = tmp_path / "archive.zip"
    path.write_bytes(raw)
    published = _sha(raw)
    claim = {"path": "comparison.json", "raw_sha256": _sha(b'{"results":[]}')}
    row = classify_retained_artifact_outcome(
        {
            "pr": 4231,
            "comment_id": 100,
            "run_id": 40143755394,
            "artifact_id": 12579928048,
            "published_archive_sha256": published,
            "marker_published": True,
            "artifact_http_status": 404,
            "local_archive_path": str(path),
            "member_claims": [claim],
            "original_event_accepting": False,
            "provider_calls": 0,
        }
    )
    assert row["local_archive"]["authenticated"] is True
    assert row["local_archive"]["sha256"] == published
    assert row["authenticated_readback"] is False
    assert row["native_admission_succeeded"] is False
    assert row["outcome"] == EXPLICIT_EXPIRED_ARTIFACT_REJECTION
    assert row["reason"] == "artifact_expired_or_unavailable"


def test_downloaded_archive_can_authenticate_without_admitting_original_event():
    raw = _zip({"comparison.json": b"kept"})
    published = _sha(raw)
    claim = {"path": "comparison.json", "raw_sha256": _sha(b"kept")}
    row = classify_retained_artifact_outcome(
        {
            "pr": 9,
            "comment_id": 100,
            "run_id": 10,
            "artifact_id": 11,
            "published_archive_sha256": published,
            "marker_published": True,
            "artifact_http_status": 200,
            "artifact_expired": False,
            "actions_archive_bytes": raw,
            "member_claims": [claim],
            "original_event_accepting": False,
            "provider_calls": 0,
            "admission_prerequisites_met": True,
            "admission_result_evidence": True,
            "subject": {"event_id": "d" * 64},
        }
    )
    assert row["outcome"] == AUTHENTICATED_RETAINED_READBACK
    assert row["authenticated_readback"] is True
    assert row["native_admission_succeeded"] is True
    assert row["original_event_accepting"] is False
    assert row["owner_decision"] is None
    expired = classify_retained_artifact_outcome(
        {
            "pr": 9,
            "comment_id": 100,
            "run_id": 10,
            "artifact_id": 11,
            "published_archive_sha256": published,
            "artifact_http_status": 200,
            "artifact_expired": True,
            "actions_archive_bytes": raw,
            "original_event_accepting": False,
            "provider_calls": 0,
        }
    )
    assert expired["outcome"] == EXPLICIT_EXPIRED_ARTIFACT_REJECTION
    assert expired["authenticated_readback"] is False


def test_wrong_member_and_provider_call_do_not_authenticate():
    raw = _zip({"comparison.json": b"kept"})
    published = _sha(raw)
    mismatch = classify_retained_artifact_outcome(
        {
            "pr": 9,
            "comment_id": 100,
            "published_archive_sha256": published,
            "artifact_http_status": 200,
            "artifact_expired": False,
            "actions_archive_bytes": raw,
            "member_claims": [{"path": "comparison.json", "raw_sha256": "e" * 64}],
            "original_event_accepting": False,
            "provider_calls": 0,
        }
    )
    assert mismatch["authenticated_readback"] is False
    assert mismatch["outcome"] == "unauthenticated retained evidence"
    called = classify_retained_artifact_outcome(_known(6392557346, provider_calls=1))
    assert called["provider_calls"] == 1
    assert called["authenticated_readback"] is False
    assert called["outcome"] == "provider call observed; recovery stopped"


def test_absent_bytes_report_is_absence_not_authentication():
    assert inspect_digest_bound_archive(None, "ab" * 32)["reason"] == "absent"


def test_cli_prints_the_pair_outcome(tmp_path: Path):
    payload = tmp_path / "observation.json"
    receipt = tmp_path / "receipt.json"
    payload.write_text(
        json.dumps({"observations": [_known(6390994169), _known(6392557346)]}),
        encoding="utf-8",
    )
    import subprocess
    import sys

    completed = subprocess.run(
        [
            sys.executable,
            "tools/verifier_event_recovery.py",
            "--classify-retained-artifact",
            str(payload),
            "--receipt",
            str(receipt),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == EXPLICIT_EXPIRED_ARTIFACT_REJECTION
    saved = json.loads(receipt.read_text(encoding="utf-8"))
    assert saved["operational_outcome"] == EXPLICIT_EXPIRED_ARTIFACT_REJECTION
    assert [row["comment_id"] for row in saved["results"]] == [6390994169, 6392557346]


def test_collector_receipt_conversion():
    """Test that collector receipt format is properly converted to observation format."""
    from tools.verifier_event_recovery import _observation_from_collector_receipt

    # Simulate a collector receipt with expired artifact
    receipt = {
        "pr": 4231,
        "comment": 6390994169,
        "run_id": 40143755394,
        "artifact_id": 12579928048,
        "subject": {"event_id": "a" * 64, "material_sha256": "b" * 64},
        "proof_status": "included",
        "proof_body_sha256": "c" * 64,
        "marker_published": True,
        "artifact_http_status": 404,
        "artifact_failures": [{"kind": "expired", "detail": "expired"}],
        "archive_inventory": [{"run_id": 40143755394, "artifact_id": 12579928048}],
        "published_archive_sha256": "c432b89fca7af092f08bc6cddf032b62b2f15ac0c727e75b9fcb30b9695e9d58",
        "original_event_accepting": False,
        "provider_calls": 0,
        "admission_prerequisites_met": False,
    }

    observation = _observation_from_collector_receipt(receipt)

    assert observation["pr"] == 4231
    assert observation["comment_id"] == 6390994169
    assert observation["run_id"] == 40143755394
    assert observation["artifact_id"] == 12579928048
    assert observation["artifact_http_status"] == 404
    assert observation["artifact_expired"] is True  # inferred from "expired" failure
    assert observation["original_event_accepting"] is False
    assert observation["provider_calls"] == 0


def test_identity_mismatch_outcome():
    """Test that identity mismatch produces a distinct non-expiry outcome."""
    # Use a known comment_id but with wrong PR
    row = classify_retained_artifact_outcome(
        {
            "pr": 9999,  # Wrong PR
            "comment_id": 6390994169,
            "run_id": 40143755394,
            "artifact_id": 12579928048,
            "published_archive_sha256": "c432b89fca7af092f08bc6cddf032b62b2f15ac0c727e75b9fcb30b9695e9d58",
            "artifact_http_status": 404,
            "original_event_accepting": False,
            "provider_calls": 0,
        }
    )
    assert row["outcome"] == IDENTITY_MISMATCH
    assert row["authenticated_readback"] is False
    assert row["native_admission_succeeded"] is False


def test_missing_status_outcome():
    """Test that missing status produces a distinct non-expiry outcome."""
    row = classify_retained_artifact_outcome(
        {
            "pr": 4231,
            "comment_id": 6390994169,
            "run_id": 40143755394,
            "artifact_id": 12579928048,
            "published_archive_sha256": "c432b89fca7af092f08bc6cddf032b62b2f15ac0c727e75b9fcb30b9695e9d58",
            # Missing artifact_http_status and actions_archive_bytes
            "original_event_accepting": False,
            "provider_calls": 0,
        }
    )
    assert row["outcome"] == MISSING_STATUS
    assert row["authenticated_readback"] is False
    assert row["native_admission_succeeded"] is False


def test_missing_duplicate_empty_pairs():
    """Test handling of missing, duplicate, and empty pair observations."""
    # Empty observations
    empty_report = classify_retained_artifact_report({"observations": []})
    assert empty_report["operational_outcome"] == "mixed retained-artifact outcomes"
    assert empty_report["provider_calls"] == 0

    # Duplicate comment IDs
    duplicate_report = classify_retained_artifact_report(
        {"observations": [_known(6390994169), _known(6390994169)]}
    )
    comment_ids = {row["comment_id"] for row in duplicate_report["results"]}
    assert len(comment_ids) == 1
    assert 6390994169 in comment_ids

    # Missing one of the pair
    single_report = classify_retained_artifact_report({"observations": [_known(6390994169)]})
    comment_ids = {row["comment_id"] for row in single_report["results"]}
    assert comment_ids == {6390994169}
    known_ids = set(KNOWN_RETAINED_ARTIFACTS.keys())
    assert comment_ids != known_ids


def test_mixed_outcomes():
    """Test that mixed outcomes are properly detected."""
    raw = _zip({"comparison.json": b"kept"})
    published = _sha(raw)
    claim = {"path": "comparison.json", "raw_sha256": _sha(b"kept")}

    # Use raw observations, not pre-classified ones
    observations = [
        {
            "pr": 9,
            "comment_id": 100,
            "run_id": 10,
            "artifact_id": 11,
            "published_archive_sha256": published,
            "artifact_http_status": 200,
            "artifact_expired": False,
            "actions_archive_bytes": raw,
            "member_claims": [claim],
            "original_event_accepting": False,
            "provider_calls": 0,
            "admission_result_evidence": True,
        },
        {
            "pr": 9,
            "comment_id": 101,
            "run_id": 11,
            "artifact_id": 12,
            "published_archive_sha256": published,
            "artifact_http_status": 404,
            "artifact_expired": True,
            "actions_archive_bytes": None,
            "original_event_accepting": False,
            "provider_calls": 0,
        },
    ]

    report = classify_retained_artifact_report({"observations": observations})
    # Should be mixed because we have two different outcomes
    assert report["operational_outcome"] == "mixed retained-artifact outcomes"


def test_admission_prerequisites_without_execution():
    """Test that admission prerequisites without actual execution evidence don't set native_admission_succeeded."""
    raw = _zip({"comparison.json": b"kept"})
    published = _sha(raw)
    claim = {"path": "comparison.json", "raw_sha256": _sha(b"kept")}

    # Has prerequisites but no actual admission result evidence
    row = classify_retained_artifact_outcome(
        {
            "pr": 9,
            "comment_id": 100,
            "run_id": 10,
            "artifact_id": 11,
            "published_archive_sha256": published,
            "artifact_http_status": 200,
            "artifact_expired": False,
            "actions_archive_bytes": raw,
            "member_claims": [claim],
            "original_event_accepting": False,
            "provider_calls": 0,
            "admission_prerequisites_met": True,
            # Note: no admission_result_evidence
        }
    )
    assert row["outcome"] == AUTHENTICATED_RETAINED_READBACK
    assert row["authenticated_readback"] is True
    assert row["native_admission_succeeded"] is False  # Should be False without actual evidence


def test_invalid_provider_calls_count():
    """Test that invalid provider_calls counts are handled properly."""
    row = classify_retained_artifact_outcome(
        {
            "pr": 4231,
            "comment_id": 6390994169,
            "run_id": 40143755394,
            "artifact_id": 12579928048,
            "published_archive_sha256": "c432b89fca7af092f08bc6cddf032b62b2f15ac0c727e75b9fcb30b9695e9d58",
            "artifact_http_status": 404,
            "original_event_accepting": False,
            "provider_calls": -1,  # Invalid: negative
        }
    )
    assert row["provider_calls"] is None  # Should be rejected as invalid

    row = classify_retained_artifact_outcome(
        {
            "pr": 4231,
            "comment_id": 6390994169,
            "run_id": 40143755394,
            "artifact_id": 12579928048,
            "published_archive_sha256": "c432b89fca7af092f08bc6cddf032b62b2f15ac0c727e75b9fcb30b9695e9d58",
            "artifact_http_status": 404,
            "original_event_accepting": False,
            "provider_calls": "invalid",  # Invalid: not a number
        }
    )
    assert row["provider_calls"] is None  # Should be rejected as invalid
