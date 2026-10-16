"""Raw evidence must be present, bound, complete, and within cumulative limits."""

import hashlib
import io
import zipfile

import pytest
from tools import verifier_artifact_capture as capture


def retained(tmp_path):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("large.json", b'{"actual":true}')
        archive.writestr("late.xml", b'<testsuite failures="0"/>')
    raw = stream.getvalue()
    sha = hashlib.sha256(raw).hexdigest()
    (tmp_path / f"{sha}.zip").write_bytes(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = []
        for index, item in enumerate(archive.infolist()):
            value = archive.read(item)
            digest = hashlib.sha256(value).hexdigest()
            (tmp_path / f"{digest}.txt").write_bytes(value)
            members.append(
                {
                    "name": item.filename,
                    "occurrence": index,
                    "status": "captured",
                    "raw_bytes": len(value),
                    "raw_sha256": digest,
                    "encoding": "utf-8",
                }
            )
    record = {
        "repository": "owner/repo",
        "run_id": 10,
        "artifact_id": 20,
        "head_sha": "a" * 40,
        "name": "actual-proof",
        "status": "captured",
        "archive_sha256": sha,
        "archive_bytes": len(raw),
        "member_count": 2,
        "member_inventory_complete": True,
        "members": members,
    }
    return {"artifact_capture_inventory": [record]}


def test_complete_retained_raw_members_become_native_inputs(tmp_path):
    coverage = retained(tmp_path)
    inputs, sources = capture.load_artifact_capture(coverage, tmp_path)
    assert inputs == {
        "artifact:10:20:0": b'{"actual":true}',
        "artifact:10:20:1": b'<testsuite failures="0"/>',
    }
    assert sources == {"Run 10: actual-proof"}


@pytest.mark.parametrize(
    "defect", ["missing", "tampered", "omitted", "duplicate", "crc", "overflow"]
)
def test_bad_capture_never_upgrades_rendering_gap(tmp_path, monkeypatch, defect):
    coverage = retained(tmp_path)
    record = coverage["artifact_capture_inventory"][0]
    member = record["members"][0]
    sidecar = tmp_path / f"{member['raw_sha256']}.txt"
    if defect == "missing":
        sidecar.unlink()
    elif defect == "tampered":
        sidecar.write_bytes(b"x" * member["raw_bytes"])
    elif defect == "omitted":
        record["members"].pop()
    elif defect == "duplicate":
        coverage["artifact_capture_inventory"].append(record)
    elif defect == "crc":
        archive = tmp_path / f"{record['archive_sha256']}.zip"
        archive.write_bytes(b"x" * record["archive_bytes"])
    else:
        monkeypatch.setattr(capture, "MAX_EXTRACT_BYTES", 1)
    with pytest.raises((ValueError, OSError)):
        capture.load_artifact_capture(coverage, tmp_path)


def test_obligation_and_byte_inventory_require_available_raw_sidecars(tmp_path, monkeypatch):
    import json

    from tools.verifier_capture_obligation_manifest import (
        build_capture_obligation_manifest,
        record_capture_obligations,
    )

    coverage = retained(tmp_path)
    coverage.update(
        schema="verifier-context-source-coverage/v1",
        stage="generated-context",
        acceptance_sources=[
            {"source": "Issue #612", "status": "included", "included_chars": 1, "total_chars": 1}
        ],
        changed_code_sources=[
            {"source": "a.py", "status": "included", "included_chars": 1, "total_chars": 1}
        ],
        acceptance_source_discovery={"required": True, "status": "included"},
        acceptance_evidence_sources=[
            {
                "source": "Run 10: actual-proof",
                "status": "truncated",
                "included_chars": 1,
                "total_chars": None,
            }
        ],
        full_diff_artifact={"source": "verifier-pr-diff.patch", "chars": 1, "status": "included"},
    )
    context = (
        "# Verifier context\n\n## Context source coverage\n\n```json\n"
        + json.dumps(coverage)
        + "\n```\n\n## CI Information\n"
    )
    assert not build_capture_obligation_manifest(context)["sufficient"]
    monkeypatch.setenv("VERIFIER_EVIDENCE_CAPTURE_DIR", str(tmp_path))
    monkeypatch.setenv("VERIFIER_SEMANTIC_MODE", "0")
    assert not build_capture_obligation_manifest(context)["sufficient"]
    from scripts.langchain import pr_verifier

    assert any(
        "legacy prompt" in reason
        for reason in pr_verifier.build_prompt_inputs(context, "diff").coverage.reasons
    )
    monkeypatch.setenv("VERIFIER_SEMANTIC_MODE", "1")
    assert build_capture_obligation_manifest(context)["sufficient"]
    context_path = tmp_path / "verifier-context.md"
    context_path.write_text(context)
    record_capture_obligations(context_path)
    inventory = json.loads((tmp_path / "verifier-capture-byte-inventory.json").read_text())
    identities = {row["input"] for row in inventory["inputs"]}
    assert identities == {"context", "artifact:10:20:0", "artifact:10:20:1"}
    (
        tmp_path / f"{coverage['artifact_capture_inventory'][0]['members'][0]['raw_sha256']}.txt"
    ).unlink()
    assert not build_capture_obligation_manifest(context)["sufficient"]
