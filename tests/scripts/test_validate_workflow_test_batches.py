"""Verify bounded workflow evidence cannot mistake partial or failed runs for PASS."""

import copy
import json

import pytest
from scripts import validate_workflow_test_batches as batches


def receipt(nodes):
    return {
        "nodes": nodes,
        "exit_code": 0,
        "reports": [
            {"nodeid": node, "when": phase, "outcome": "passed"}
            for node in nodes
            for phase in ("setup", "call", "teardown")
        ],
    }


@pytest.mark.parametrize("corruption", ["missing", "extra", "duplicate", "partial", "timeout"])
def test_incomplete_or_changed_batch_inventory_cannot_pass(corruption):
    original = ["a.py::test_one", "b.py::test_two"]
    batch = receipt(original.copy())
    assert batches.compare_receipts(original, [batch])["success"]
    if corruption == "missing":
        batch = receipt(original[:1])
    elif corruption == "extra":
        batch = receipt(original + ["c.py::test_three"])
    elif corruption == "duplicate":
        # Equal counts alone miss this replacement of one node with another.
        batch = receipt([original[0], original[0]])
    elif corruption == "partial":
        batch["reports"].pop()
    else:
        batch["exit_code"] = 124
    assert not batches.compare_receipts(original, [batch])["success"]


@pytest.mark.parametrize("phase", ["setup", "call", "teardown"])
def test_failure_in_any_phase_cannot_pass_even_with_zero_exit(phase):
    batch = receipt(["a.py::test_one"])
    next(report for report in batch["reports"] if report["when"] == phase)["outcome"] = "failed"
    result = batches.compare_receipts(batch["nodes"], [batch])
    assert result["outcomes"] == {"failed": 1}
    assert not result["success"]


def test_file_partition_preserves_oversized_file_and_original_order():
    collection = {
        "nodes": ["a1", "a2", "b1", "b2", "b3", "c1"],
        "files": {
            "a1": "a.py",
            "a2": "a.py",
            "b1": "b.py",
            "b2": "b.py",
            "b3": "b.py",
            "c1": "c.py",
        },
    }
    assert batches.partition_files(collection, 2) == [["a.py"], ["b.py"], ["c.py"]]


def test_real_batches_retain_exact_parametrized_ids_and_skips(tmp_path):
    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "test_one.py").write_text(
        "import pytest\n"
        "@pytest.mark.parametrize('value', ['PASSED [100%]', 'two::parts'])\n"
        "def test_values(value):\n    assert value\n"
        "@pytest.mark.skip(reason='ordinary skip')\n"
        "def test_skip():\n    assert False\n"
    )
    (suite / "test_two.py").write_text("def test_other():\n    assert True\n")
    output = tmp_path / "evidence"
    assert batches.main([str(suite), "--output", str(output), "--max-nodes", "2"]) == 0
    summary = json.loads((output / "summary.json").read_text())
    assert summary["expected"] == summary["collected"] == summary["terminal"] == 4
    assert summary["missing"] == summary["extra"] == {}
    assert summary["outcomes"] == {"passed": 3, "skipped": 1}
    assert len(list(output.glob("batch-*.json"))) == 2


def test_real_teardown_failure_is_not_hidden_by_passing_call(tmp_path):
    suite = tmp_path / "test_failure.py"
    suite.write_text(
        "import pytest\n"
        "@pytest.fixture\n"
        "def broken():\n    yield\n    assert False, 'teardown failed'\n"
        "def test_ok(broken):\n    assert True\n"
    )
    output = tmp_path / "evidence"
    assert batches.main([str(suite), "--output", str(output)]) == 1
    summary = json.loads((output / "summary.json").read_text())
    assert summary["terminal"] == 1
    assert summary["outcomes"] == {"failed": 1}
    assert "teardown failed" in (output / "batch-01.log").read_text()


def test_timeout_cannot_reuse_a_stale_success_receipt(tmp_path):
    prefix = tmp_path / "timed-out"
    prefix.with_suffix(".json").write_text(json.dumps(receipt(["old.py::test_old"])))
    suite = tmp_path / "test_wait.py"
    suite.write_text("import time\ndef test_wait():\n    time.sleep(30)\n")
    result = batches.execute_pytest([str(suite)], prefix, timeout=0.01)
    assert result["exit_code"] == 124
    assert not result.get("nodes")
    assert not batches.compare_receipts(["old.py::test_old"], [result])["success"]


def test_collection_error_prevents_batch_execution(tmp_path):
    suite = tmp_path / "test_invalid.py"
    suite.write_text("raise RuntimeError('collection failed')\n")
    output = tmp_path / "evidence"
    output.mkdir()
    (output / "summary.json").write_text('{"success": true}\n')
    assert batches.main([str(suite), "--output", str(output)]) == 1
    assert not list(output.glob("batch-*.json"))
    assert not (output / "summary.json").exists()
    assert "collection failed" in (output / "collection.log").read_text()


def test_duplicate_phase_reports_cannot_prove_terminal_execution():
    batch = receipt(["a.py::test_one"])
    batch["reports"].append(copy.deepcopy(batch["reports"][1]))
    result = batches.compare_receipts(batch["nodes"], [batch])
    assert result["missing_results"] == {"a.py::test_one": 1}
    assert not result["success"]
