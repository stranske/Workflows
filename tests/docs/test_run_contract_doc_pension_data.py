"""Keep run-contract documentation aligned with Pension-Data emitter references."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN_CONTRACT_DOC = ROOT / "docs" / "contracts" / "run-contract-v1.md"
SYNC_MANIFEST = ROOT / ".github" / "sync-manifest.yml"


def test_run_contract_doc_mentions_pension_data_emitter() -> None:
    text = RUN_CONTRACT_DOC.read_text(encoding="utf-8")
    assert text.count("stranske/Pension-Data") >= 1
    assert text.count("build_backplane_reference_run") >= 1
    assert text.count("backplane_emitter.py") >= 1
    assert text.count("config/backplane_participants.json") >= 1


def test_run_contract_doc_is_declared_in_sync_manifest() -> None:
    manifest = SYNC_MANIFEST.read_text(encoding="utf-8")
    assert manifest.count("docs/contracts/run-contract-v1.md") >= 1
