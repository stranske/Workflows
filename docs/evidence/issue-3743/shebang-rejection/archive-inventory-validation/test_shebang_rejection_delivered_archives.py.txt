"""Check the full delivered archive inventory, including supplementary validation."""

import hashlib
import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-3743/shebang-rejection"
HISTORICAL = {
    Path("proof.tar.gz"),
    Path("path-lookup/proof.tar.gz"),
    Path("replay-validation/proof.tar.gz"),
}
# Discover archives independently of the verifier's curated summary list. A new
# validation archive must participate without changing this test's inventory.
ARCHIVES = sorted(path.relative_to(EVIDENCE) for path in EVIDENCE.rglob("*.tar.gz"))
REQUIRED_BINDINGS = {
    "scripts/check_deliberate_break.py",
    "templates/consumer-repo/scripts/check_deliberate_break.py",
    "tests/scripts/test_check_deliberate_break_shebang_rejection.py",
    "docs/evidence/issue-3743/shebang-rejection/replay.py",
}


@pytest.mark.parametrize("relative", ARCHIVES, ids=lambda path: path.as_posix())
def test_every_delivered_archive_and_current_binding_verifies(relative):
    verifier = runpy.run_path(str(EVIDENCE / "verify_archives.py"))
    archive = EVIDENCE / relative
    summary_path = archive.with_name("summary.json")
    kind = "historical" if relative in HISTORICAL else "current"
    report = verifier["verify_archive"](ROOT, summary_path.relative_to(ROOT), kind)
    assert report["archive"] == archive.relative_to(ROOT).as_posix()
    assert report["verified"], report
    assert report["members"] > 0

    if kind == "historical":
        return

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    bindings = summary["input_sha256"]
    retained_bindings = json.loads(
        archive.with_name("input-bindings.json").read_text(encoding="utf-8")
    )
    assert bindings == retained_bindings
    assert bindings.keys() >= REQUIRED_BINDINGS
    for path, spec in bindings.items():
        data = (ROOT / path).read_bytes()
        assert hashlib.sha256(data).hexdigest() == spec["sha256"], path
        assert len(data) == spec["bytes"], path
