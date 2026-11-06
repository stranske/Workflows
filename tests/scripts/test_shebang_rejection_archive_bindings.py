"""Verify delivered shebang-rejection archives and current input bindings."""

import io
import json
import runpy
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-3743/shebang-rejection"
VERIFIER = EVIDENCE / "verify_archives.py"
NOTE = EVIDENCE / "current-acceptance.md"


def load_verifier():
    return runpy.run_path(str(VERIFIER))


@pytest.mark.parametrize(
    "defect",
    [
        None,
        "duplicate-payload",
        "duplicate-manifest",
        "directory",
        "symlink",
        "hardlink",
        "unlisted-file",
        "missing-file",
        "wrong-hash",
        "wrong-length",
    ],
)
def test_archive_verification_requires_unique_manifested_regular_members(tmp_path, defect):
    module = load_verifier()
    payload = b"retained proof bytes\n"
    manifest = {"receipt.txt": {"sha256": module["digest"](payload), "bytes": len(payload)}}
    if defect == "missing-file":
        manifest["missing.txt"] = dict(manifest["receipt.txt"])
    elif defect == "wrong-hash":
        manifest["receipt.txt"]["sha256"] = "0" * 64
    elif defect == "wrong-length":
        manifest["receipt.txt"]["bytes"] += 1
    manifest_bytes = json.dumps(manifest).encode()
    archive = tmp_path / "proof.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:

        def add_file(name, data):
            member = tarfile.TarInfo(name)
            member.size = len(data)
            tar.addfile(member, io.BytesIO(data))

        add_file("receipt.txt", payload)
        add_file("manifest.json", manifest_bytes)
        if defect == "duplicate-payload":
            add_file("receipt.txt", payload)
        elif defect == "duplicate-manifest":
            add_file("manifest.json", manifest_bytes)
        elif defect in {"directory", "symlink", "hardlink"}:
            member = tarfile.TarInfo("extra")
            member.type = {
                "directory": tarfile.DIRTYPE,
                "symlink": tarfile.SYMTYPE,
                "hardlink": tarfile.LNKTYPE,
            }[defect]
            if defect != "directory":
                member.linkname = "receipt.txt"
            tar.addfile(member)
        elif defect == "unlisted-file":
            add_file("extra.txt", payload)
    data = archive.read_bytes()
    summary = {
        "archive": {
            "path": archive.name,
            "sha256": module["digest"](data),
            "bytes": len(data),
            "manifest_sha256": module["digest"](manifest_bytes),
            "verified_manifest_members": len(manifest),
        }
    }
    (tmp_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    # Outer archive hashes are valid even for defects in the member inventory.
    report = module["verify_archive"](tmp_path, Path("summary.json"), "historical")
    assert report["sha256_matches_summary"] is True
    assert report["bytes_match_summary"] is True
    assert report["verified"] is (defect is None)


def test_delivered_archives_and_current_bindings_match_the_note():
    module = load_verifier()
    report = module["validate"](ROOT)
    archives = report["archives"]
    assert [item["kind"] for item in archives] == [
        "historical",
        "historical",
        "historical",
        "current",
    ]
    assert all(item["verified"] for item in archives)
    assert all(item["member_mismatches"] == [] for item in archives)
    assert all(item["members"] > 0 for item in archives)
    assert report["problems"] == []
    assert report["historical_input_mismatches"] > 0
    assert report["matched_comparison"] == {
        "added": 8,
        "removed": 0,
        "changed": 0,
        "universes_identical": True,
        "exclusions": 0,
        "line_regressions": 0,
        "branch_regressions": 0,
    }
    note = NOTE.read_text(encoding="utf-8")
    assert note == module["render"](report)
    assert "Historical receipts" in note
    assert "are not current acceptance" in note
    assert "Current acceptance" in note
    for path in report["interpreters"].values():
        assert path in note
        assert Path(path).is_absolute()
    counts = report["measured_file_counts"]
    assert counts["black_files"] > 0
    assert counts["ruff_files"] > 0
    assert counts["workflows_directory_yml"] > 0
    assert counts["template_directory_yml"] > 0
    assert counts["manifest_workflow_targets"] > 0
    assert counts["strict_validation_inputs"] == (
        counts["workflows_directory_yml"] + counts["template_directory_yml"] + 1
    )
    for value in counts.values():
        assert str(value) in note
