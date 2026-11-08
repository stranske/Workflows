"""Verify delivered shebang-rejection archives and current input bindings."""

import io
import json
import runpy
import shutil
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
    "field, replacement",
    [
        (None, None),
        ("baseline_nodes", 0),
        ("added_outcomes", ["failure"] * 8),
        ("universes_identical", False),
        ("exclusions", 1),
        ("covered_line_regressions", [["scripts/check_deliberate_break.py", 1]]),
        ("covered_branch_regressions", [["scripts/check_deliberate_break.py", [1, 2]]]),
    ],
)
def test_comparison_summary_must_match_raw_junit_and_coverage(tmp_path, field, replacement):
    module = load_verifier()
    evidence = tmp_path / module["EVIDENCE"]
    comparison = evidence / "matched-comparison"
    comparison.mkdir(parents=True)
    for name in ("compare_matched.py", "replay.py"):
        shutil.copyfile(EVIDENCE / name, evidence / name)
    for name in (
        "baseline.xml",
        "candidate.xml",
        "baseline.json",
        "candidate.json",
        "comparison.json",
    ):
        shutil.copyfile(EVIDENCE / "matched-comparison" / name, comparison / name)
    summary = json.loads((EVIDENCE / "matched-comparison/summary.json").read_text())
    if field is None:
        assert module["verify_comparison"](tmp_path, summary) == summary["comparison"]
    else:
        summary["comparison"][field] = replacement
        with pytest.raises(ValueError, match="summary comparison drifted from raw inputs"):
            module["verify_comparison"](tmp_path, summary)


def test_collection_rejects_a_summary_claim_without_changing_archive_bytes(monkeypatch):
    module = load_verifier()
    read_json = module["read_json"]

    def damaged_summary(path):
        payload = read_json(path)
        if path == ROOT / module["CURRENT"][0]:
            payload["comparison"]["added_outcomes"] = ["failure"] * 8
        return payload

    monkeypatch.setitem(module["collect"].__globals__, "read_json", damaged_summary)
    with pytest.raises(ValueError, match="summary comparison drifted from raw inputs"):
        module["collect"](ROOT)


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


@pytest.mark.parametrize("defect", ["current-binding", "note"])
def test_validate_rejects_isolated_current_binding_and_note_corruption(tmp_path, defect):
    module = load_verifier()
    evidence_rel = module["EVIDENCE"]
    shutil.copytree(EVIDENCE, tmp_path / evidence_rel)
    relatives = set()
    for summary_path in (*module["HISTORICAL"], *module["CURRENT"]):
        summary = json.loads((ROOT / summary_path).read_text())
        relatives.update(summary["input_sha256"])
    validation = runpy.run_path(str(EVIDENCE / "capture_validation_run.py"))
    relatives.update(validation["HISTORICAL_PATHS"])
    relatives.update((validation["TEMPLATE_SCRIPT"], ".github/sync-manifest.yml"))
    relatives.update(
        str(path.relative_to(ROOT)) for path in (ROOT / ".github/workflows").glob("*.yml")
    )
    relatives.update(
        str(path.relative_to(ROOT))
        for path in (ROOT / "templates/consumer-repo/.github/workflows").glob("*.yml")
    )
    for relative in sorted(relatives):
        source, target = ROOT / relative, tmp_path / relative
        if source.is_file() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    # The unmodified isolated tree must validate before its single corruption.
    assert module["validate"](tmp_path)["problems"] == []
    if defect == "current-binding":
        helper = tmp_path / "scripts/check_deliberate_break.py"
        helper.write_bytes(helper.read_bytes() + b"\n# corrupted current binding\n")
        message = "current binding drifted: scripts/check_deliberate_break.py"
    else:
        note = tmp_path / module["DOC"]
        note.write_text(note.read_text() + "Stale note.\n")
        message = "current-acceptance.md does not match the verified report"
    with pytest.raises(ValueError, match=message):
        module["validate"](tmp_path)
