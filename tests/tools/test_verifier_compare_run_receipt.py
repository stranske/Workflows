"""Receipt contract for Orphan Steward dual-run verify:compare capture."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from tools import verifier_compare_run_receipt as receipt

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/verifier_compare_receipt"
BASELINE_DIR = FIXTURES / "run-37400729553"
BASELINE_TERMINAL = FIXTURES / "run-37400729553-terminal/verifier-terminal-disposition.ndjson"
FOLLOWUP_DIR = FIXTURES / "run-followup-example"
FOLLOWUP_TERMINAL = FIXTURES / "run-followup-example-terminal/verifier-terminal-disposition.ndjson"
PRODUCTION_FOLLOWUP_DIR = FIXTURES / "run-37567257334"
PRODUCTION_FOLLOWUP_TERMINAL = (
    FIXTURES / "run-37567257334-terminal/verifier-terminal-disposition.ndjson"
)
PRODUCTION_FOLLOWUP_RUN_ID = "37567257334"


def test_baseline_inventory_lists_seven_comparison_files() -> None:
    inventory = receipt.inventory_from_comparison_dir(BASELINE_DIR)
    assert inventory["complete"] is True
    assert inventory["missing_files"] == []
    assert inventory["file_count"] == 7
    assert inventory["present_files"] == sorted(receipt.COMPARISON_ARTIFACT_FILES)


def test_summarize_baseline_preserves_production_non_pass() -> None:
    terminal = receipt.load_terminal_disposition(BASELINE_TERMINAL)
    summary = receipt.summarize_compare_run(
        run_id=receipt.BASELINE_RUN_ID,
        comparison_dir=BASELINE_DIR,
        terminal_disposition=terminal,
        role="baseline",
    )
    assert summary["run_id"] == "37400729553"
    assert summary["pr"] == "3769"
    assert summary["provider_verdicts"] == ["CONCERNS", "CONCERNS"]
    assert summary["corpus_verdict"] == "NON_PASS"
    assert summary["acceptance_source_discovery"]["required"] is True
    assert "#3768" in summary["acceptance_source_discovery"]["reason"]
    assert summary["artifact_inventory"]["comparison_results"]["complete"] is True
    assert summary["artifact_inventory"]["comparison_results"]["artifact_name"] == (
        "comparison-results-37400729553"
    )
    assert summary["artifact_inventory"]["terminal_disposition"]["disposition"] == ("needs-human")


def test_dual_run_receipt_freezes_baseline_when_followup_attached() -> None:
    baseline = receipt.summarize_compare_run(
        run_id=receipt.BASELINE_RUN_ID,
        comparison_dir=BASELINE_DIR,
        terminal_disposition=receipt.load_terminal_disposition(BASELINE_TERMINAL),
        role="baseline",
    )
    followup = receipt.summarize_compare_run(
        run_id="39999999999",
        comparison_dir=FOLLOWUP_DIR,
        terminal_disposition=receipt.load_terminal_disposition(FOLLOWUP_TERMINAL),
        role="followup",
    )
    before = json.loads(json.dumps(baseline))
    built = receipt.build_dual_run_receipt(baseline=baseline, followup=followup)

    assert built["schema"] == receipt.SCHEMA
    assert built["baseline_preserved"] is True
    assert built["baseline"] == before
    assert built["baseline"]["corpus_verdict"] == "NON_PASS"
    assert built["baseline"]["provider_verdicts"] == ["CONCERNS", "CONCERNS"]
    assert built["baseline"]["run_id"] == "37400729553"
    assert built["followup"]["run_id"] == "39999999999"
    assert built["followup"]["acceptance_source_discovery"]["required"] is False
    assert built["followup"]["source_repair_demonstrated"] is True
    assert built["independent_gates"]["source_3757_topology"] == "required_external"
    assert "mode=compare" in built["steward_dispatch"]["command"]
    assert built["steward_dispatch"]["pr_number"] == "3769"


def test_production_followup_receipt_preserves_baseline_and_records_repair() -> None:
    baseline = receipt.summarize_compare_run(
        run_id=receipt.BASELINE_RUN_ID,
        comparison_dir=BASELINE_DIR,
        terminal_disposition=receipt.load_terminal_disposition(BASELINE_TERMINAL),
        role="baseline",
    )
    followup = receipt.summarize_compare_run(
        run_id=PRODUCTION_FOLLOWUP_RUN_ID,
        comparison_dir=PRODUCTION_FOLLOWUP_DIR,
        terminal_disposition=receipt.load_terminal_disposition(PRODUCTION_FOLLOWUP_TERMINAL),
        role="followup",
    )
    built = receipt.build_dual_run_receipt(baseline=baseline, followup=followup)

    assert built["baseline"]["run_id"] == "37400729553"
    assert built["baseline"]["provider_verdicts"] == ["CONCERNS", "CONCERNS"]
    assert built["baseline"]["corpus_verdict"] == "NON_PASS"
    assert built["baseline_preserved"] is True
    assert built["followup"]["run_id"] == PRODUCTION_FOLLOWUP_RUN_ID
    assert built["followup"]["provider_verdicts"] == ["CONCERNS", "PASS"]
    assert built["followup"]["corpus_verdict"] == "NON_PASS"
    assert built["followup"]["acceptance_source_discovery"]["required"] is False
    assert "#3768" not in str(built["followup"]["acceptance_source_discovery"].get("reason", ""))
    assert built["followup"]["artifact_inventory"]["comparison_results"]["complete"] is True
    assert built["followup"]["artifact_inventory"]["comparison_results"]["file_count"] == 7
    assert built["followup"]["source_repair_demonstrated"] is True


def test_dual_run_receipt_rejects_incomplete_followup_inventory() -> None:
    baseline = receipt.summarize_compare_run(
        run_id=receipt.BASELINE_RUN_ID, comparison_dir=BASELINE_DIR, role="baseline"
    )
    followup = receipt.summarize_compare_run(
        run_id="39999999999", comparison_dir=FOLLOWUP_DIR, role="followup"
    )
    followup["artifact_inventory"]["comparison_results"]["complete"] = False
    followup["artifact_inventory"]["comparison_results"]["missing_files"] = [
        "comparison-stderr.log"
    ]
    with pytest.raises(ValueError, match="inventory must be complete"):
        receipt.build_dual_run_receipt(baseline=baseline, followup=followup)


def test_dual_run_receipt_rejects_unrepaired_followup_source() -> None:
    baseline = receipt.summarize_compare_run(
        run_id=receipt.BASELINE_RUN_ID, comparison_dir=BASELINE_DIR, role="baseline"
    )
    followup = receipt.summarize_compare_run(
        run_id="39999999999", comparison_dir=FOLLOWUP_DIR, role="followup"
    )
    followup["acceptance_source_discovery"] = {
        "source": "Linked issues",
        "status": "unavailable",
        "reason": (
            "Known source issue #3768 was not retrieved; no retrieved linked issue "
            "can substitute for that acceptance contract."
        ),
        "required": True,
    }
    with pytest.raises(ValueError, match="repaired source discovery"):
        receipt.build_dual_run_receipt(baseline=baseline, followup=followup)


def test_dual_run_receipt_rejects_baseline_relabel() -> None:
    baseline = receipt.summarize_compare_run(
        run_id=receipt.BASELINE_RUN_ID,
        comparison_dir=BASELINE_DIR,
        role="baseline",
    )
    relabeled = json.loads(json.dumps(baseline))
    relabeled["corpus_verdict"] = "PASS"
    with pytest.raises(ValueError, match="NON_PASS"):
        receipt.build_dual_run_receipt(baseline=relabeled)

    same_id_followup = json.loads(json.dumps(baseline))
    same_id_followup["role"] = "followup"
    with pytest.raises(ValueError, match="differ from the frozen baseline"):
        receipt.build_dual_run_receipt(baseline=baseline, followup=same_id_followup)


def test_cli_writes_baseline_only_receipt(tmp_path: Path) -> None:
    out = tmp_path / "receipt.json"
    rc = receipt.main(
        [
            "--baseline-comparison-dir",
            str(BASELINE_DIR),
            "--baseline-terminal",
            str(BASELINE_TERMINAL),
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["followup"] is None
    assert payload["baseline"]["run_id"] == "37400729553"
    assert payload["baseline_preserved"] is True


def test_reusable_verifier_uploads_comparison_artifact_bundle() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/reusable-agents-verifier.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["verifier"]["steps"]
    upload = next(step for step in steps if step.get("name") == "Upload comparison artifacts")
    assert upload["uses"] == "actions/upload-artifact@v7"
    assert upload["with"]["name"] == "comparison-results-${{ github.run_id }}"
    path_block = upload["with"]["path"]
    for name in receipt.COMPARISON_ARTIFACT_FILES:
        assert name in path_block
    assert "inputs.mode == 'compare'" in str(upload.get("if", ""))


def test_agents_verifier_dispatch_exposes_compare_mode() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/agents-verifier.yml").read_text(encoding="utf-8")
    )
    # PyYAML 1.1 parses the workflow `on:` key as boolean True.
    triggers = workflow.get("on", workflow.get(True))
    options = triggers["workflow_dispatch"]["inputs"]["mode"]["options"]
    assert "compare" in options
    assert triggers["workflow_dispatch"]["inputs"]["pr_number"]["required"] is True


@pytest.mark.parametrize("source", ["manifest", "corpus", "terminal"])
def test_run_receipt_rejects_cross_run_artifacts(tmp_path: Path, source: str) -> None:
    import shutil

    bundle = tmp_path / "comparison"
    shutil.copytree(BASELINE_DIR, bundle)
    terminal = receipt.load_terminal_disposition(BASELINE_TERMINAL)
    if source == "manifest":
        path = bundle / "verifier-input-manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["source_run_id"] = "123"
        path.write_text(json.dumps(manifest), encoding="utf-8")
    elif source == "corpus":
        path = bundle / "comparison-comment.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace('"run_id": "37400729553"', '"run_id": "123"'),
            encoding="utf-8",
        )
    else:
        terminal["run_id"] = "123"
    with pytest.raises(ValueError, match="run identity"):
        receipt.summarize_compare_run(
            run_id=receipt.BASELINE_RUN_ID, comparison_dir=bundle, terminal_disposition=terminal
        )


@pytest.mark.parametrize("field,value", [("repository", "stranske/Other"), ("pr", "99")])
def test_dual_run_receipt_rejects_cross_target_followup(field: str, value: str) -> None:
    baseline = receipt.summarize_compare_run(
        run_id=receipt.BASELINE_RUN_ID, comparison_dir=BASELINE_DIR
    )
    followup = receipt.summarize_compare_run(
        run_id="39999999999", comparison_dir=FOLLOWUP_DIR, role="followup"
    )
    followup[field] = value
    with pytest.raises(ValueError, match="target identity"):
        receipt.build_dual_run_receipt(baseline=baseline, followup=followup)


def test_dual_run_receipt_rejects_zero_followup_run() -> None:
    baseline = receipt.summarize_compare_run(
        run_id=receipt.BASELINE_RUN_ID, comparison_dir=BASELINE_DIR
    )
    followup = receipt.summarize_compare_run(
        run_id="39999999999", comparison_dir=FOLLOWUP_DIR, role="followup"
    )
    followup["run_id"] = "0"
    with pytest.raises(ValueError, match="positive integer"):
        receipt.build_dual_run_receipt(baseline=baseline, followup=followup)
