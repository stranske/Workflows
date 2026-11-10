"""#4231/#4235 artifact expiry is explicit and is not archive authentication."""

from __future__ import annotations

import io
import json
import math
import zipfile
from pathlib import Path

from tools.verifier_event_recovery import (
    AUTHENTICATED_RETAINED_READBACK,
    EXPLICIT_EXPIRED_ARTIFACT_REJECTION,
    IDENTITY_MISMATCH,
    INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE,
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
    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures/verification_input_repair/4231-original/comparison.json"
    )
    raw = _zip({"comparison.json": fixture.read_bytes()})
    path = tmp_path / "archive.zip"
    path.write_bytes(raw)
    published = _sha(raw)
    claim = {"path": "comparison.json", "raw_sha256": _sha(fixture.read_bytes())}
    row = classify_retained_artifact_outcome(
        {
            "pr": 4231,
            "comment_id": 6390994169,
            "run_id": 40143755394,
            "artifact_id": 12579928048,
            "published_archive_sha256": "c432b89fca7af092f08bc6cddf032b62b2f15ac0c727e75b9fcb30b9695e9d58",
            "marker_published": True,
            "artifact_http_status": 404,
            "local_archive_path": str(path),
            "member_claims": [claim],
            "original_event_accepting": False,
            "provider_calls": 0,
            "proof_status": "included",
            "proof_body_sha256": "c" * 64,
            "subject": {"event_id": "a" * 64, "material_sha256": "b" * 64},
        }
    )
    assert row["local_archive"]["authenticated"] is False
    assert row["local_archive"]["sha256"] == published
    assert row["local_archive"]["reason"] == "digest_mismatch"
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
            "subject": {"event_id": "d" * 64, "material_sha256": "b" * 64},
            "proof_status": "included",
            "proof_body_sha256": "c" * 64,
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
            "marker_published": True,
            "proof_status": "included",
            "proof_body_sha256": "c" * 64,
            "subject": {"event_id": "d" * 64, "material_sha256": "b" * 64},
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
            "run_id": 10,
            "artifact_id": 11,
            "published_archive_sha256": published,
            "marker_published": True,
            "artifact_http_status": 200,
            "artifact_expired": False,
            "actions_archive_bytes": raw,
            "member_claims": [{"path": "comparison.json", "raw_sha256": "e" * 64}],
            "original_event_accepting": False,
            "provider_calls": 0,
            "proof_status": "included",
            "proof_body_sha256": "c" * 64,
            "subject": {"event_id": "a" * 64, "material_sha256": "b" * 64},
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

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "tools/verifier_event_recovery.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
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


def test_cli_rejects_classify_with_manifest():
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "tools/verifier_event_recovery.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--classify-retained-artifact", "x.json", "--manifest", "y.json"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0

    completed_revalidate = subprocess.run(
        [sys.executable, str(script), "--classify-retained-artifact", "x.json", "--revalidate-retained"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed_revalidate.returncode != 0


def test_archive_byte_bounds_and_unsafe_and_member_failure():
    """Test archive size limit, unsafe zip entries and member authentication failure."""
    import io
    import zipfile
    from tools.verifier_event_recovery import _sha

    # Archive byte bound (> 8MB)
    over_size = b"x" * (8388608 + 1)
    res = inspect_digest_bound_archive(over_size, _sha(over_size))
    assert res["available"] is False
    assert res["authenticated"] is False
    assert res["reason"] == "archive_byte_bound"

    # Corrupted zip archive
    corrupt = b"PK\x03\x04corrupted zip payload"
    res_corrupt = inspect_digest_bound_archive(
        corrupt, _sha(corrupt), member_claims=[{"path": "file.txt", "raw_sha256": "a" * 64}]
    )
    assert res_corrupt["available"] is True
    assert res_corrupt["authenticated"] is False
    assert res_corrupt["reason"] == "member_authentication_failed"

    # Unsafe zip with path traversal
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../traversal.txt", b"evil")
    unsafe_bytes = buf.getvalue()
    res_unsafe = inspect_digest_bound_archive(
        unsafe_bytes, _sha(unsafe_bytes), member_claims=[{"path": "../traversal.txt", "raw_sha256": _sha(b"evil")}]
    )
    assert res_unsafe["available"] is True
    assert res_unsafe["authenticated"] is False
    assert res_unsafe["reason"] == "member_authentication_failed"

    # Unsafe zip with absolute path
    buf2 = io.BytesIO()
    with zipfile.ZipFile(buf2, "w") as zf:
        zf.writestr("/root.txt", b"evil")
    unsafe_bytes2 = buf2.getvalue()
    res_unsafe2 = inspect_digest_bound_archive(
        unsafe_bytes2, _sha(unsafe_bytes2), member_claims=[{"path": "/root.txt", "raw_sha256": _sha(b"evil")}]
    )
    assert res_unsafe2["available"] is True
    assert res_unsafe2["authenticated"] is False
    assert res_unsafe2["reason"] == "member_authentication_failed"


def test_collector_receipt_conversion():
    """Test that collector receipt format is properly converted to observation format."""
    from tools.verifier_event_recovery import _observation_from_collector_receipt

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
    assert observation["artifact_expired"] is True
    assert observation["original_event_accepting"] is False
    assert observation["provider_calls"] == 0

    not_found_receipt = dict(receipt)
    not_found_receipt.pop("artifact_http_status")
    not_found_receipt["artifact_failures"] = [
        {"kind": "metadata_lookup_failed", "detail": "artifact 12579928048 Not Found"},
    ]
    not_found = _observation_from_collector_receipt(not_found_receipt)
    assert not_found["artifact_http_status"] == 404

    missing_calls_receipt = dict(receipt)
    missing_calls_receipt.pop("provider_calls")
    missing_calls = _observation_from_collector_receipt(missing_calls_receipt)
    assert missing_calls["provider_calls"] is None
    incomplete = classify_retained_artifact_outcome(missing_calls)
    assert incomplete["outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE

    # Non-finite provider calls through collector-receipt conversion
    for non_finite in [float("nan"), float("inf"), float("-inf"), 1e309]:
        nf_receipt = dict(receipt)
        nf_receipt["provider_calls"] = non_finite
        obs = _observation_from_collector_receipt(nf_receipt)
        res = classify_retained_artifact_outcome(obs)
        assert res["provider_calls"] is None
        assert res["outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE

    # Non-boolean acceptance through collector-receipt conversion (including 0 and empty string)
    for nb in [0, "", "false", "0", 1]:
        nb_receipt = dict(receipt)
        nb_receipt["original_event_accepting"] = nb
        obs = _observation_from_collector_receipt(nb_receipt)
        res = classify_retained_artifact_outcome(obs)
        assert res["original_event_accepting"] is None
        assert res["outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE

    # Stop-plus-incomplete combinations through collector-receipt conversion
    stop_inc_1 = dict(receipt)
    stop_inc_1["provider_calls"] = 1
    stop_inc_1.pop("original_event_accepting", None)
    res_stop_1 = classify_retained_artifact_outcome(_observation_from_collector_receipt(stop_inc_1))
    assert res_stop_1["outcome"] == "provider call observed; recovery stopped"
    assert res_stop_1["reason"] == "provider_call_forbidden;missing_original_event_acceptance"
    assert res_stop_1["provider_calls"] == 1
    assert res_stop_1["original_event_accepting"] is None

    stop_inc_2 = dict(receipt)
    stop_inc_2["original_event_accepting"] = True
    stop_inc_2["provider_calls"] = "invalid"
    res_stop_2 = classify_retained_artifact_outcome(_observation_from_collector_receipt(stop_inc_2))
    assert res_stop_2["outcome"] == "original event accepting; recovery stopped"
    assert res_stop_2["reason"] == "original_event_must_stay_nonaccepting;missing_or_invalid_provider_calls"
    assert res_stop_2["original_event_accepting"] is True
    assert res_stop_2["provider_calls"] is None

    # Full report via collector receipts payload (with second receipt)
    receipt_4235 = {
        "pr": 4235,
        "comment": 6392557346,
        "run_id": 40155311407,
        "artifact_id": 12584318436,
        "subject": {"event_id": "a" * 64, "material_sha256": "b" * 64},
        "proof_status": "included",
        "proof_body_sha256": "c" * 64,
        "marker_published": True,
        "artifact_http_status": 404,
        "original_event_accepting": False,
        "provider_calls": 0,
    }
    pair_report = classify_retained_artifact_report({"receipts": [receipt, receipt_4235]})
    assert pair_report["operational_outcome"] == EXPLICIT_EXPIRED_ARTIFACT_REJECTION
    assert pair_report["provider_calls"] == 0

    # Receipts payload with duplicate and extra
    dup_report = classify_retained_artifact_report({"receipts": [receipt, receipt_4235, receipt]})
    assert dup_report["operational_outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE
    assert dup_report["provider_calls"] is None

    extra_rcpt = dict(receipt)
    extra_rcpt["comment"] = 9999999999
    extra_report = classify_retained_artifact_report({"receipts": [receipt, receipt_4235, extra_rcpt]})
    assert extra_report["operational_outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE
    assert extra_report["provider_calls"] is None


def test_identity_mismatch_outcome():
    """Test that identity mismatch produces a distinct non-expiry outcome."""
    row = classify_retained_artifact_outcome(
        {
            "pr": 9999,
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
            "original_event_accepting": False,
            "provider_calls": 0,
        }
    )
    assert row["outcome"] == MISSING_STATUS
    assert row["authenticated_readback"] is False
    assert row["native_admission_succeeded"] is False


def test_missing_duplicate_empty_pairs():
    """Test handling of missing, duplicate, and empty pair observations."""
    empty_report = classify_retained_artifact_report({"observations": []})
    assert empty_report["operational_outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE
    assert empty_report["provider_calls"] is None

    duplicate_report = classify_retained_artifact_report(
        {"observations": [_known(6390994169), _known(6390994169)]}
    )
    comment_ids = {row["comment_id"] for row in duplicate_report["results"]}
    assert len(comment_ids) == 1
    assert 6390994169 in comment_ids
    assert duplicate_report["operational_outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE

    single_report = classify_retained_artifact_report({"observations": [_known(6390994169)]})
    comment_ids = {row["comment_id"] for row in single_report["results"]}
    assert comment_ids == {6390994169}
    known_ids = set(KNOWN_RETAINED_ARTIFACTS.keys())
    assert comment_ids != known_ids
    assert single_report["operational_outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE

    extra_report = classify_retained_artifact_report(
        {"observations": [_known(6390994169), _known(6392557346), _known(6390994169)]}
    )
    assert extra_report["operational_outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE


def test_mixed_outcomes():
    """Test that mixed outcomes are properly detected with known comment IDs."""
    raw = _zip({"comparison.json": b"kept"})
    claim = {"path": "comparison.json", "raw_sha256": _sha(b"kept")}

    observations = [
        {
            "pr": 4231,
            "comment_id": 6390994169,
            "run_id": 40143755394,
            "artifact_id": 12579928048,
            "published_archive_sha256": "c432b89fca7af092f08bc6cddf032b62b2f15ac0c727e75b9fcb30b9695e9d58",
            "artifact_http_status": 200,
            "artifact_expired": False,
            "actions_archive_bytes": raw,
            "member_claims": [claim],
            "original_event_accepting": False,
            "provider_calls": 0,
            "admission_result_evidence": True,
            "marker_published": True,
            "proof_status": "included",
            "proof_body_sha256": "c" * 64,
            "subject": {"event_id": "a" * 64, "material_sha256": "b" * 64},
        },
        {
            "pr": 4235,
            "comment_id": 6392557346,
            "run_id": 40155311407,
            "artifact_id": 12584318436,
            "published_archive_sha256": "526dcef67f26160ece176b800e7a4d18a2e6d6883d7a2e4294b07570570486ab",
            "artifact_http_status": 404,
            "artifact_expired": True,
            "actions_archive_bytes": None,
            "original_event_accepting": False,
            "provider_calls": 0,
            "marker_published": True,
            "proof_status": "included",
            "proof_body_sha256": "c" * 64,
            "subject": {"event_id": "a" * 64, "material_sha256": "b" * 64},
        },
    ]

    report = classify_retained_artifact_report({"observations": observations})
    assert report["operational_outcome"] == "mixed retained-artifact outcomes"


def test_admission_prerequisites_without_execution():
    """Test that admission prerequisites without actual execution evidence don't set native_admission_succeeded."""
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
            "artifact_http_status": 200,
            "artifact_expired": False,
            "actions_archive_bytes": raw,
            "member_claims": [claim],
            "original_event_accepting": False,
            "provider_calls": 0,
            "admission_prerequisites_met": True,
            "marker_published": True,
            "proof_status": "included",
            "proof_body_sha256": "c" * 64,
            "subject": {"event_id": "a" * 64, "material_sha256": "b" * 64},
        }
    )
    assert row["outcome"] == AUTHENTICATED_RETAINED_READBACK
    assert row["authenticated_readback"] is True
    assert row["native_admission_succeeded"] is False


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
            "provider_calls": -1,
        }
    )
    assert row["provider_calls"] is None
    assert row["outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE

    row = classify_retained_artifact_outcome(
        {
            "pr": 4231,
            "comment_id": 6390994169,
            "run_id": 40143755394,
            "artifact_id": 12579928048,
            "published_archive_sha256": "c432b89fca7af092f08bc6cddf032b62b2f15ac0c727e75b9fcb30b9695e9d58",
            "artifact_http_status": 404,
            "original_event_accepting": False,
            "provider_calls": "invalid",
        }
    )
    assert row["provider_calls"] is None
    assert row["outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE


def test_non_finite_provider_calls():
    """Test that non-finite provider_calls (NaN, infinity) are rejected."""
    row = classify_retained_artifact_outcome(
        {
            "pr": 4231,
            "comment_id": 6390994169,
            "run_id": 40143755394,
            "artifact_id": 12579928048,
            "published_archive_sha256": "c432b89fca7af092f08bc6cddf032b62b2f15ac0c727e75b9fcb30b9695e9d58",
            "artifact_http_status": 404,
            "original_event_accepting": False,
            "provider_calls": float("nan"),
        }
    )
    assert row["provider_calls"] is None
    assert row["outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE

    row = classify_retained_artifact_outcome(
        {
            "pr": 4231,
            "comment_id": 6390994169,
            "run_id": 40143755394,
            "artifact_id": 12579928048,
            "published_archive_sha256": "c432b89fca7af092f08bc6cddf032b62b2f15ac0c727e75b9fcb30b9695e9d58",
            "artifact_http_status": 404,
            "original_event_accepting": False,
            "provider_calls": float("inf"),
        }
    )
    assert row["provider_calls"] is None
    assert row["outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE

    row = classify_retained_artifact_outcome(
        {
            "pr": 4231,
            "comment_id": 6390994169,
            "run_id": 40143755394,
            "artifact_id": 12579928048,
            "published_archive_sha256": "c432b89fca7af092f08bc6cddf032b62b2f15ac0c727e75b9fcb30b9695e9d58",
            "artifact_http_status": 404,
            "original_event_accepting": False,
            "provider_calls": float("-inf"),
        }
    )
    assert row["provider_calls"] is None
    assert row["outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE


def test_overflow_provider_calls():
    """Test that overflow-to-infinity provider_calls are rejected."""
    row = classify_retained_artifact_outcome(
        {
            "pr": 4231,
            "comment_id": 6390994169,
            "run_id": 40143755394,
            "artifact_id": 12579928048,
            "published_archive_sha256": "c432b89fca7af092f08bc6cddf032b62b2f15ac0c727e75b9fcb30b9695e9d58",
            "artifact_http_status": 404,
            "original_event_accepting": False,
            "provider_calls": 1e309,
        }
    )
    assert row["provider_calls"] is None
    assert row["outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE


def test_expired_without_http_status():
    row = classify_retained_artifact_outcome(
        {
            "pr": 4231,
            "comment_id": 6390994169,
            "run_id": 40143755394,
            "artifact_id": 12579928048,
            "published_archive_sha256": "c432b89fca7af092f08bc6cddf032b62b2f15ac0c727e75b9fcb30b9695e9d58",
            "artifact_expired": True,
            "original_event_accepting": False,
            "provider_calls": 0,
        }
    )
    assert row["outcome"] == EXPLICIT_EXPIRED_ARTIFACT_REJECTION
    assert row["actions_archive"]["http_status"] is None


def test_non_boolean_original_event_accepting_is_incomplete():
    row = classify_retained_artifact_outcome(
        _known(6390994169, **{"original_event_accepting": "false"})
    )
    assert row["original_event_accepting"] is None
    assert row["outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE

    row = classify_retained_artifact_outcome(
        _known(6390994169, **{"original_event_accepting": ""})
    )
    assert row["original_event_accepting"] is None
    assert row["outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE

    row = classify_retained_artifact_outcome(
        _known(6390994169, **{"original_event_accepting": 0})
    )
    assert row["original_event_accepting"] is None
    assert row["outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE


def test_pair_aggregate_incomplete_when_acceptance_unknown():
    one = _known(6390994169)
    two = _known(6392557346, original_event_accepting=None)
    report = classify_retained_artifact_report({"observations": [one, two]})
    assert report["operational_outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE
    assert report["provider_calls"] is None


def test_identity_mismatch_preserves_local_digest_without_authenticating_readback(tmp_path: Path):
    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures/verification_input_repair/4231-original/comparison.json"
    )
    row = classify_retained_artifact_outcome(
        _known(
            6390994169,
            pr=9999,
            local_archive_path=str(fixture),
        )
    )
    assert row["outcome"] == IDENTITY_MISMATCH
    assert row["local_archive"]["available"] is True
    assert row["authenticated_readback"] is False


def test_duplicate_extra_rows_rejected():
    """Test that duplicate and extra rows are rejected for pair outcome."""
    observations = [
        _known(6390994169),
        _known(6392557346),
        _known(6390994169),  # Duplicate
    ]
    report = classify_retained_artifact_report({"observations": observations})
    assert report["operational_outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE

    # Create an extra observation with an unknown comment_id manually
    extra_row = {
        "pr": 9999,
        "comment_id": 9999999999,
        "run_id": 9999999999,
        "artifact_id": 9999999999,
        "published_archive_sha256": "d" * 64,
        "marker_published": True,
        "artifact_http_status": 404,
        "artifact_expired": None,
        "original_event_accepting": False,
        "provider_calls": 0,
        "subject": {"event_id": "a" * 64, "material_sha256": "b" * 64},
        "proof_status": "included",
        "proof_body_sha256": "c" * 64,
    }
    observations = [
        _known(6390994169),
        _known(6392557346),
        extra_row,  # Extra
    ]
    report = classify_retained_artifact_report({"observations": observations})
    assert report["operational_outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE


def test_stop_plus_incomplete_preserves_outcomes():
    """Test that stop-plus-incomplete cases retain observed outcomes."""
    one = _known(6390994169, provider_calls=1)
    two = _known(6392557346, provider_calls=None)
    report = classify_retained_artifact_report({"observations": [one, two]})
    assert report["operational_outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE
    results = {row["comment_id"]: row for row in report["results"]}
    assert results[6390994169]["outcome"] == "provider call observed; recovery stopped"
    assert results[6390994169]["provider_calls"] == 1
    assert results[6392557346]["outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE

    # Single observation with both stop and incomplete evidence
    stop_and_inc_1 = classify_retained_artifact_outcome(
        _known(6390994169, provider_calls=1, original_event_accepting=None)
    )
    assert stop_and_inc_1["outcome"] == "provider call observed; recovery stopped"
    assert stop_and_inc_1["reason"] == "provider_call_forbidden;missing_original_event_acceptance"
    assert stop_and_inc_1["provider_calls"] == 1
    assert stop_and_inc_1["original_event_accepting"] is None

    stop_and_inc_2 = classify_retained_artifact_outcome(
        _known(6392557346, original_event_accepting=True, provider_calls=None)
    )
    assert stop_and_inc_2["outcome"] == "original event accepting; recovery stopped"
    assert stop_and_inc_2["reason"] == "original_event_must_stay_nonaccepting;missing_or_invalid_provider_calls"
    assert stop_and_inc_2["original_event_accepting"] is True
    assert stop_and_inc_2["provider_calls"] is None


def test_cli_paths_for_retained_artifact_cases(tmp_path: Path):
    """Test CLI paths for non-finite counts, duplicate/extra rows, stop+incomplete, and non-boolean acceptance."""
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "tools/verifier_event_recovery.py"

    def _run_cli(payload_dict: dict[str, Any]) -> tuple[subprocess.CompletedProcess, dict[str, Any]]:
        p_file = tmp_path / f"p_{id(payload_dict)}_{len(payload_dict)}.json"
        r_file = tmp_path / f"r_{id(payload_dict)}_{len(payload_dict)}.json"
        p_file.write_text(json.dumps(payload_dict), encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                str(script),
                "--classify-retained-artifact",
                str(p_file),
                "--receipt",
                str(r_file),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        saved = json.loads(r_file.read_text(encoding="utf-8")) if r_file.exists() else {}
        return completed, saved

    # 1. Non-finite provider calls via CLI
    comp, saved = _run_cli(
        {"observations": [_known(6390994169, provider_calls=1e309), _known(6392557346)]}
    )
    assert comp.returncode == 0
    assert comp.stdout.strip() == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE
    assert saved["operational_outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE
    assert saved["provider_calls"] is None

    # 2. Duplicate rows via CLI
    comp, saved = _run_cli(
        {"observations": [_known(6390994169), _known(6392557346), _known(6390994169)]}
    )
    assert comp.returncode == 0
    assert comp.stdout.strip() == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE
    assert saved["operational_outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE

    # 3. Extra row via CLI
    extra_row = dict(_known(6390994169))
    extra_row["comment_id"] = 9999999999
    comp, saved = _run_cli(
        {"observations": [_known(6390994169), _known(6392557346), extra_row]}
    )
    assert comp.returncode == 0
    assert comp.stdout.strip() == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE
    assert saved["operational_outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE

    # 4. Stop-plus-incomplete via CLI
    comp, saved = _run_cli(
        {
            "observations": [
                _known(6390994169, provider_calls=1, original_event_accepting=None),
                _known(6392557346, original_event_accepting=None),
            ]
        }
    )
    assert comp.returncode == 0
    assert comp.stdout.strip() == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE
    assert saved["operational_outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE
    res = {r["comment_id"]: r for r in saved["results"]}
    assert res[6390994169]["outcome"] == "provider call observed; recovery stopped"
    assert res[6390994169]["reason"] == "provider_call_forbidden;missing_original_event_acceptance"

    # 5. Non-boolean acceptance via CLI (0 and empty string)
    for nb in [0, ""]:
        comp, saved = _run_cli(
            {"observations": [_known(6390994169, original_event_accepting=nb), _known(6392557346)]}
        )
        assert comp.returncode == 0
        assert comp.stdout.strip() == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE
        assert saved["operational_outcome"] == INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE


def test_real_retained_fixture_payload_and_receipts():
    """Verify that committed fixture payloads and receipts are valid and reproducible."""
    repo_root = Path(__file__).resolve().parents[2]
    fix_dir = repo_root / "tests/fixtures/verification_input_repair"

    historical_receipt = fix_dir / "2026-11-06-expiry-receipts.json"
    assert historical_receipt.exists()
    hist = json.loads(historical_receipt.read_text(encoding="utf-8"))
    assert hist["schema"] == "retained-artifact-report/v1"
    assert hist["operational_outcome"] == EXPLICIT_EXPIRED_ARTIFACT_REJECTION
    assert len(hist["results"]) == 2

    current_payload_path = fix_dir / "2026-11-10-retained-payload.json"
    current_receipt_path = fix_dir / "2026-11-10-expiry-receipts.json"
    assert current_payload_path.exists()
    assert current_receipt_path.exists()

    payload = json.loads(current_payload_path.read_text(encoding="utf-8"))
    classified = classify_retained_artifact_report(payload)

    receipt = json.loads(current_receipt_path.read_text(encoding="utf-8"))
    assert classified["operational_outcome"] == EXPLICIT_EXPIRED_ARTIFACT_REJECTION
    assert classified["provider_calls"] == 0
    assert classified["operational_outcome"] == receipt["operational_outcome"]
    assert classified["provider_calls"] == receipt["provider_calls"]
    assert len(classified["results"]) == 2
    for exp_res, act_res in zip(receipt["results"], classified["results"], strict=True):
        assert exp_res["comment_id"] == act_res["comment_id"]
        assert exp_res["outcome"] == act_res["outcome"]
        assert exp_res["reason"] == act_res["reason"]
        assert exp_res["original_event_accepting"] == act_res["original_event_accepting"]
        assert exp_res["provider_calls"] == act_res["provider_calls"]
