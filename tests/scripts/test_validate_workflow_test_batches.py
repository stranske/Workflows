"""Verify bounded workflow evidence cannot mistake partial or failed runs for PASS."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

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


@pytest.mark.parametrize("transfer", ["swap", "move"])
def test_reports_cannot_be_borrowed_from_another_batch(transfer):
    original = ["a.py::test_one", "b.py::test_two"]
    first, second = [receipt([node]) for node in original]
    if transfer == "swap":
        first["reports"], second["reports"] = second["reports"], first["reports"]
    else:
        first["reports"].extend(second["reports"])
        second["reports"] = []

    result = batches.compare_receipts(original, [first, second])

    # The global node multisets still match, but neither batch proves its own run.
    assert result["expected"] == result["collected"] == result["terminal"] == 2
    assert result["missing"] == result["extra"] == {}
    assert result["missing_results"] == result["extra_results"] == {}
    assert not result["success"]
    assert result["batch_result_mismatches"][0] == {
        "batch": 1,
        "missing": {original[0]: 1} if transfer == "swap" else {},
        "extra": {original[1]: 1},
    }
    assert result["batch_result_mismatches"][1] == {
        "batch": 2,
        "missing": {original[1]: 1},
        "extra": {original[0]: 1} if transfer == "swap" else {},
    }


@pytest.mark.parametrize("corruption", ["partial", "nonmapping", "unreadable"])
@pytest.mark.parametrize("child_exit", [0, 1])
def test_bad_child_receipt_retains_failure_summary(tmp_path, monkeypatch, corruption, child_exit):
    output = tmp_path / "evidence"
    node = "test_one.py::test_one"

    def popen(command, **kwargs):
        path = Path(command[command.index("--workflow-batch-receipt") + 1])
        collecting = "--collect-only" in command

        def wait(timeout):
            if collecting:
                path.write_text(json.dumps({"nodes": [node], "files": {node: "test_one.py"}}))
            else:
                path.write_text("[]" if corruption == "nonmapping" else '{"nodes":')
                kwargs["stdout"].write("child stopped while writing receipt\n")
            return 0 if collecting else child_exit

        return SimpleNamespace(wait=wait)

    original_read = Path.read_text

    def read_text(path, *args, **kwargs):
        if corruption == "unreadable" and path == output / "batch-01.json":
            raise OSError("receipt read failed")
        return original_read(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(batches.subprocess, "Popen", popen)
        patch.setattr(Path, "read_text", read_text)
        assert batches.main(["test_one.py", "--output", str(output)]) == 1

    summary = json.loads((output / "summary.json").read_text())
    batch = json.loads((output / "batch-01.json").read_text())
    assert not summary["success"]
    assert summary["missing"] == summary["missing_results"] == {node: 1}
    assert batch["exit_code"] == child_exit
    assert batch["receipt_error"] == "unreadable pytest receipt"
    assert batch["command"][-2:] == ["test_one.py", "-v"]
    assert batch["seconds"] >= 0
    assert not batch.get("nodes")
    assert "child stopped" in (output / "batch-01.log").read_text()
