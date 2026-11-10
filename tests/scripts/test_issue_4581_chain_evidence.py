"""Replay the retained 4557r2 chain receipts against their provenance map (#4604)."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-4369/runtime-4550/4557r2"
PROVENANCE = EVIDENCE / "4581-artifact-provenance.json"
CHAIN_RECEIPT_SHA256 = "c348298582fa08a93b0e845e495d8951af50461f8ac1e2e334c62a659c6879c3"
TERMINAL_RUN = 42585644980
DISPATCHER_RUN = 42585506842
CONTINUATION_KEY = "0646425b9b16c40cb1e9"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def provenance() -> dict:
    return _load(PROVENANCE.name)


def test_provenance_covers_every_retained_receipt(provenance: dict) -> None:
    retained = {
        path.relative_to(EVIDENCE).as_posix()
        for path in EVIDENCE.rglob("*")
        if path.is_file() and path != PROVENANCE
    }
    assert set(provenance["files"]) == retained
    assert len(retained) > 0


def test_every_provenance_hash_matches(provenance: dict) -> None:
    mismatched = {
        name: digest
        for name, digest in provenance["files"].items()
        if _sha256(EVIDENCE / name) != digest
    }
    assert mismatched == {}


def test_chain_receipt_digest_is_pinned(provenance: dict) -> None:
    assert provenance["files"]["chain-receipt.json"] == CHAIN_RECEIPT_SHA256
    assert _sha256(EVIDENCE / "chain-receipt.json") == CHAIN_RECEIPT_SHA256


def test_chain_receipt_references_retained_files(provenance: dict) -> None:
    terminal = _load("chain-receipt.json")["terminal_merger"]
    assert terminal["run_id"] == TERMINAL_RUN
    for key in ("run_receipt", "artifact_receipt", "report", "authorization", "log_excerpt"):
        assert terminal[key] in provenance["files"]


def test_terminal_run_dispatch_lineage_is_bound() -> None:
    run = _load(f"maint71-{TERMINAL_RUN}-run.json")
    assert run["databaseId"] == TERMINAL_RUN
    assert run["event"] == "workflow_dispatch"
    assert run["triggering_actor"] == "stranske-automation-bot"
    assert run["displayTitle"].split()[-1] == CONTINUATION_KEY

    lineage = run["dispatch_lineage"]
    dispatcher = lineage["dispatcher_run"]
    assert dispatcher["run_id"] == DISPATCHER_RUN
    assert lineage["binding"]["continuation_key"] == CONTINUATION_KEY

    dispatcher_run = _load(dispatcher["run_receipt"])
    assert dispatcher_run["databaseId"] == DISPATCHER_RUN
    assert dispatcher_run["event"] == "schedule"
    assert dispatcher_run["path"].endswith("maint-82-sync-dependency-campaign.yml")
    assert dispatcher_run["createdAt"] < run["createdAt"]

    excerpt = (EVIDENCE / dispatcher["log_excerpt"]).read_text(encoding="utf-8")
    assert f'"continuation_key":"{CONTINUATION_KEY}"' in excerpt
    assert lineage["binding"]["plan_id"] in excerpt
    assert lineage["binding"]["source_commit"] in excerpt
    assert dispatcher["notice"] in excerpt
    assert f'{dispatcher["dispatch_notice_at"]} ##[notice]{dispatcher["notice"]}' in excerpt
    # The notice is logged after the dispatches POST returns, so it trails createdAt.
    assert dispatcher["dispatch_notice_at"] > run["createdAt"]
    assert lineage["binding"]["plan_id"] == _load("chain-receipt.json")["plan"]["plan_id"]

    chain_receipt = _load("chain-receipt.json")
    terminal = chain_receipt["terminal_merger"]
    terminal_excerpt_path = EVIDENCE / terminal["log_excerpt"]
    terminal_excerpt = terminal_excerpt_path.read_text(encoding="utf-8")
    handoff_line = [
        line for line in terminal_excerpt.splitlines() if "IMMUTABLE_HANDOFF_JSON" in line
    ][0]
    handoff_json_str = handoff_line.split("IMMUTABLE_HANDOFF_JSON: ", 1)[1]
    handoff = json.loads(handoff_json_str)
    assert handoff["plan_id"] == lineage["binding"]["plan_id"]
    assert handoff["source_commit"] == lineage["binding"]["source_commit"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-W", "ignore::pytest.PytestDeprecationWarning"]))
