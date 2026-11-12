"""Protect source restoration, interpreter selection, and target coverage in r3 helpers."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "docs/evidence/issue-4019/r3/mutate.py"
TARGET_MISSING = ROOT / "docs/evidence/issue-4019/r3/target_missing.py"
RECEIPTS_PATH = ROOT / "docs/evidence/issue-4019/r3/mutations/mutation-receipts.json"


def load_driver():
    """Dynamically load the issue 4019 mutation driver module."""
    spec = importlib.util.spec_from_file_location("issue_4019_mutation_driver", DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_partial_write_restores_original(tmp_path, monkeypatch):
    """Ensure original source bytes are restored when writing a mutation fails mid-write."""
    driver = load_driver()
    source = tmp_path / "source.py"
    original = b"original = True\n"
    source.write_bytes(original)
    monkeypatch.setattr(
        driver, "MUTATIONS", [("injected", "unused", str(source), "True", "False", 1)]
    )

    def partial_write(path, text):
        path.write_bytes(b"partial")
        raise OSError("injected partial write")

    monkeypatch.setattr(Path, "write_text", partial_write)
    with pytest.raises(OSError, match="injected partial write"):
        driver.main(tmp_path)
    assert source.read_bytes() == original


def test_subprocess_uses_active_interpreter(monkeypatch):
    """Ensure the mutation runner invokes pytest using sys.executable."""
    # Use a distinct value so a hardcoded path cannot pass by coincidence.
    active = "/selected/environment/bin/python"
    monkeypatch.setattr(sys, "executable", active)
    driver = load_driver()
    calls = []

    def subprocess_run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout="passed\n", stderr="")

    monkeypatch.setattr(driver.subprocess, "run", subprocess_run)
    assert driver.run("test.py::test_case") == (0, "passed\n")
    assert calls == [[active, "-m", "pytest", "test.py::test_case", "-q", "-p", "no:cacheprovider"]]


def test_run_handles_timeout_expired(monkeypatch):
    """Ensure subprocess.TimeoutExpired is caught and reported as exit code 124."""
    driver = load_driver()

    def subprocess_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=argv, timeout=120, output="partial out\n", stderr="partial err\n"
        )

    monkeypatch.setattr(driver.subprocess, "run", subprocess_run)
    code, out = driver.run("test.py::test_timeout")
    assert code == 124
    assert "partial out" in out
    assert "partial err" in out
    assert "TimeoutExpired" in out


def test_empty_subprocess_output_does_not_raise_index_error(tmp_path, monkeypatch):
    """Ensure empty red/green subprocess outputs fall back to empty strings in receipts."""
    driver = load_driver()
    source = tmp_path / "source.py"
    original = b"value = 1\n"
    source.write_bytes(original)
    monkeypatch.setattr(driver, "MUTATIONS", [("empty", "node", str(source), "1", "2", 1)])
    monkeypatch.setattr(driver, "run", lambda node: (1, ""))

    rc = driver.main(tmp_path)
    assert rc == 1
    assert source.read_bytes() == original
    receipts = json.loads((tmp_path / "mutation-receipts.json").read_text())
    assert len(receipts) == 1
    assert receipts[0]["red_last_line"] == ""
    assert receipts[0]["green_last_line"] == ""
    assert receipts[0]["proof_ok"] is False


def test_count_mismatch_records_failed_receipt_without_replacing_source(tmp_path, monkeypatch):
    """Ensure an occurrence count mismatch prevents replacement and records a failed receipt."""
    driver = load_driver()
    source = tmp_path / "source.py"
    original = b"value = 1\n"
    source.write_bytes(original)
    monkeypatch.setattr(driver, "MUTATIONS", [("mismatch", "node", str(source), "1", "2", 2)])
    monkeypatch.setattr(driver, "run", lambda node: (0, "1 passed\n"))

    rc = driver.main(tmp_path)
    assert rc == 1
    assert source.read_bytes() == original
    receipts = json.loads((tmp_path / "mutation-receipts.json").read_text())
    assert len(receipts) == 1
    assert receipts[0]["red_exit"] == 2
    assert "Occurrence count mismatch" in receipts[0]["red_last_line"]
    assert receipts[0]["proof_ok"] is False


def test_target_missing_script_calculates_missing_totals(tmp_path):
    """Verify target_missing.py sums missing lines and branches across the three targets."""
    coverage_fixture = tmp_path / "coverage.json"
    coverage_fixture.write_text(
        json.dumps(
            {
                "totals": {
                    "num_statements": 800,
                    "num_branches": 200,
                    "covered_lines": 750,
                    "covered_branches": 150,
                },
                "files": {
                    "scripts/aggregate_agent_metrics.py": {
                        "summary": {"missing_lines": 0, "missing_branches": 2},
                        "missing_lines": [],
                        "missing_branches": [[492, 481], [954, 910]],
                    },
                    "scripts/check_consumer_sync_drift.py": {
                        "summary": {"missing_lines": 0, "missing_branches": 0},
                        "missing_lines": [],
                        "missing_branches": [],
                    },
                    "tools/llm_provider.py": {
                        "summary": {"missing_lines": 3, "missing_branches": 0},
                        "missing_lines": [265, 270, 292],
                        "missing_branches": [],
                    },
                },
            }
        )
    )
    proc = subprocess.run(
        [sys.executable, str(TARGET_MISSING), str(coverage_fixture)],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = proc.stdout.strip().splitlines()
    assert lines[0] == "TOTAL 900 1000 90.0"
    assert "scripts/aggregate_agent_metrics.py 0 + 2 = 2 [] [[492, 481], [954, 910]]" in lines[1]
    assert "scripts/check_consumer_sync_drift.py 0 + 0 = 0 [] []" in lines[2]
    assert "tools/llm_provider.py 3 + 0 = 3 [265, 270, 292] []" in lines[3]
    assert lines[4] == "TARGET_MISSING 5"


def test_verified_mutation_receipts_inventory():
    """Verify the 27 mutation receipts on disk all have proof_ok and matching SHA-256 digests."""
    assert RECEIPTS_PATH.is_file()
    receipts = json.loads(RECEIPTS_PATH.read_text())
    assert len(receipts) == 27
    for receipt in receipts:
        assert receipt["proof_ok"] is True
        assert receipt["red_exit"] == 1
        assert receipt["green_exit"] == 0
        assert receipt["sha256_before"] == receipt["sha256_restored"]
