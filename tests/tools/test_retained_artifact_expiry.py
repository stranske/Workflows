"""#4231/#4235 artifact expiry is explicit and is not archive authentication."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from tools.verifier_event_recovery import (
    AUTHENTICATED_RETAINED_READBACK,
    EXPLICIT_EXPIRED_ARTIFACT_REJECTION,
    KNOWN_RETAINED_ARTIFACTS,
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
