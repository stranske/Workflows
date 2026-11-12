"""Protect source restoration, interpreter selection, and target coverage in r3 helpers."""

import hashlib
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
RERUN_RECEIPTS_PATH = (
    ROOT / "docs/evidence/issue-4019/r3/integration-rerun/mutations/mutation-receipts.json"
)


def load_driver():
    """Dynamically load the issue 4019 mutation driver module."""
    spec = importlib.util.spec_from_file_location("issue_4019_mutation_driver", DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_target_missing():
    """Dynamically load the issue 4019 target_missing helper module."""
    spec = importlib.util.spec_from_file_location("issue_4019_target_missing", TARGET_MISSING)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_partial_write_restores_original(tmp_path, monkeypatch):
    """Ensure original source bytes are restored when writing a mutation fails mid-write."""
    driver = load_driver()
    monkeypatch.setattr(driver, "is_worktree_clean", lambda: True)
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
        driver.main(tmp_path, revision="deadbeef")
    assert source.read_bytes() == original


def test_get_revision_handles_git_success_and_failure(monkeypatch):
    """Ensure get_revision() returns clean HEAD SHA, '<sha>-dirty' for dirty trees, or 'unknown'."""
    driver = load_driver()

    def clean_git(argv, **kwargs):
        if argv[:2] == ["git", "rev-parse"]:
            return SimpleNamespace(returncode=0, stdout="abc1234\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(driver.subprocess, "run", clean_git)
    assert driver.is_worktree_clean() is True
    assert driver.get_revision() == "abc1234"

    def dirty_git(argv, **kwargs):
        if argv[:2] == ["git", "rev-parse"]:
            return SimpleNamespace(returncode=0, stdout="abc1234\n", stderr="")
        return SimpleNamespace(
            returncode=0, stdout=" M tools/llm_provider.py\n?? scratch.txt\n", stderr=""
        )

    monkeypatch.setattr(driver.subprocess, "run", dirty_git)
    assert driver.is_worktree_clean() is False
    assert driver.get_revision() == "abc1234-dirty"

    monkeypatch.setattr(
        driver.subprocess,
        "run",
        lambda argv, **kwargs: SimpleNamespace(returncode=128, stdout="", stderr="fatal"),
    )
    assert driver.is_worktree_clean() is False
    assert driver.get_revision() == "unknown"

    def raise_os_error(argv, **kwargs):
        raise OSError("git missing")

    monkeypatch.setattr(driver.subprocess, "run", raise_os_error)
    assert driver.is_worktree_clean() is False
    assert driver.get_revision() == "unknown"


def test_main_rejects_dirty_worktree_or_marks_non_commit_evidence(tmp_path, monkeypatch):
    """Ensure main() rejects dirty worktrees by default or marks results as <sha>-dirty."""
    driver = load_driver()
    source = tmp_path / "source.py"
    original = b"value = 1\n"
    source.write_bytes(original)
    monkeypatch.setattr(driver, "MUTATIONS", [("01", "test.py::test_ok", str(source), "1", "2", 1)])
    monkeypatch.setattr(driver, "is_worktree_clean", lambda: False)
    monkeypatch.setattr(driver, "get_revision", lambda: "abc1234-dirty")

    with pytest.raises(RuntimeError, match="Refusing to record commit-keyed mutation proofs"):
        driver.main(tmp_path)
    with pytest.raises(RuntimeError, match="Refusing to record commit-keyed mutation proofs"):
        driver.main(tmp_path, revision="abc1234")
    assert source.read_bytes() == original
    assert not (tmp_path / "mutation-receipts.json").exists()

    calls = []

    def stub_run(node):
        calls.append(node)
        if len(calls) == 1:
            return 1, "FAILED test.py::test_ok\n"
        return 0, "1 passed\n"

    monkeypatch.setattr(driver, "run", stub_run)
    rc = driver.main(tmp_path, revision="abc1234", allow_dirty=True)
    assert rc == 0
    receipts = json.loads((tmp_path / "mutation-receipts.json").read_text())
    assert receipts[0]["revision"] == "abc1234-dirty"
    assert (tmp_path / "01-red.txt").read_text().startswith("# revision: abc1234-dirty\n")
    assert (tmp_path / "01-green.txt").read_text().startswith("# revision: abc1234-dirty\n")


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

    def subprocess_run_bytes(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=120, output=b"bytes out\n", stderr=None)

    monkeypatch.setattr(driver.subprocess, "run", subprocess_run_bytes)
    code_bytes, out_bytes = driver.run("test.py::test_timeout_bytes")
    assert code_bytes == 124
    assert "bytes out" in out_bytes
    assert "TimeoutExpired" in out_bytes


def test_empty_subprocess_output_does_not_raise_index_error(tmp_path, monkeypatch):
    """Ensure empty red/green subprocess outputs fall back to empty strings in receipts."""
    driver = load_driver()
    monkeypatch.setattr(driver, "get_revision", lambda: "clean-rev")
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
    monkeypatch.setattr(driver, "get_revision", lambda: "clean-rev")
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


def test_successful_mutation_path_records_verified_receipt(tmp_path, monkeypatch):
    """Verify main() executes red-then-green in order, restores source, and returns 0."""
    driver = load_driver()
    monkeypatch.setattr(driver, "is_worktree_clean", lambda: True)
    source = tmp_path / "source.py"
    original = b"value = 1\n"
    source.write_bytes(original)
    monkeypatch.setattr(driver, "MUTATIONS", [("01", "test.py::test_ok", str(source), "1", "2", 1)])
    observed_states = []

    def stub_run(node):
        current_text = source.read_text(encoding="utf-8")
        observed_states.append((node, current_text))
        if len(observed_states) == 1:
            return 1, "FAILED test.py::test_ok - assert 2 == 1\n1 failed in 0.01s\n"
        return 0, "1 passed in 0.01s\n"

    monkeypatch.setattr(driver, "run", stub_run)

    rc = driver.main(tmp_path, revision="test-rev-001")
    assert rc == 0
    assert observed_states == [
        ("test.py::test_ok", "value = 2\n"),
        ("test.py::test_ok", "value = 1\n"),
    ]
    assert source.read_bytes() == original
    assert (tmp_path / "01-red.txt").read_text().startswith("# revision: test-rev-001\n")
    assert (tmp_path / "01-green.txt").read_text().startswith("# revision: test-rev-001\n")
    receipts = json.loads((tmp_path / "mutation-receipts.json").read_text())
    assert len(receipts) == 1
    assert receipts[0]["id"] == "01"
    assert receipts[0]["revision"] == "test-rev-001"
    assert receipts[0]["red_exit"] == 1
    assert receipts[0]["green_exit"] == 0
    assert receipts[0]["red_last_line"] == "1 failed in 0.01s"
    assert receipts[0]["green_last_line"] == "1 passed in 0.01s"
    assert receipts[0]["sha256_before"] == receipts[0]["sha256_restored"]
    assert receipts[0]["proof_ok"] is True


def test_timeout_in_main_stops_subsequent_mutations(tmp_path, monkeypatch):
    """Ensure main() stops the mutation loop after recording a timed-out (exit 124) run."""
    driver = load_driver()
    monkeypatch.setattr(driver, "get_revision", lambda: "clean-rev")
    source = tmp_path / "source.py"
    original = b"value = 1\n"
    source.write_bytes(original)
    monkeypatch.setattr(
        driver,
        "MUTATIONS",
        [
            ("01", "test.py::test_timeout", str(source), "1", "2", 1),
            ("02", "test.py::test_never_called", str(source), "1", "3", 1),
        ],
    )
    called_nodes = []

    def stub_run(node):
        called_nodes.append(node)
        if len(called_nodes) == 1:
            return 124, "TimeoutExpired: timed out\n"
        return 0, "1 passed\n"

    monkeypatch.setattr(driver, "run", stub_run)

    rc = driver.main(tmp_path)
    assert rc == 1
    assert source.read_bytes() == original
    assert called_nodes == ["test.py::test_timeout", "test.py::test_timeout"]
    receipts = json.loads((tmp_path / "mutation-receipts.json").read_text())
    assert [r["id"] for r in receipts] == ["01"]
    assert receipts[0]["red_exit"] == 124
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
    """Verify the 27 mutation receipts on disk match MUTATIONS IDs, revisions, and proof_ok."""
    driver = load_driver()
    expected_ids = [mid for mid, *_ in driver.MUTATIONS]
    assert len(expected_ids) == 27
    assert len(set(expected_ids)) == 27
    expected_sets = (
        (
            RECEIPTS_PATH,
            "69e5b6d6cd3fb154be29890f2ae212772de8ce45",
            "tests/tools/test_llm_provider.py:2154: AssertionError",
            False,
        ),
        (
            RERUN_RECEIPTS_PATH,
            "c1f18728c6b215fa7a66353b311fa12277074437",
            "tests/tools/test_llm_provider.py:2178: AssertionError",
            True,
        ),
    )
    for path, expected_rev, expected_04_line, verify_live_digest in expected_sets:
        assert path.is_file()
        receipts = json.loads(path.read_text())
        receipt_ids = [receipt["id"] for receipt in receipts]
        assert len(receipt_ids) == 27
        assert len(set(receipt_ids)) == 27
        assert receipt_ids == expected_ids
        for (mid, node, rel_path, old, new, count), receipt in zip(
            driver.MUTATIONS, receipts, strict=True
        ):
            assert receipt["id"] == mid
            assert receipt["revision"] == expected_rev
            assert receipt["node"] == node
            assert receipt["file"] == rel_path
            assert receipt["replace"] == old
            assert receipt["with"] == new
            assert receipt["occurrences"] == count
            assert receipt["proof_ok"] is True
            assert receipt["red_exit"] == 1
            assert receipt["green_exit"] == 0
            assert receipt["sha256_before"] == receipt["sha256_restored"]
            for kind in ("red", "green"):
                transcript = (path.parent / f"{mid}-{kind}.txt").read_text()
                assert transcript.startswith(f"# revision: {expected_rev}\n")
            live_bytes = (ROOT / rel_path).read_bytes()
            assert live_bytes.decode("utf-8").count(old) == count
            if verify_live_digest:
                assert hashlib.sha256(live_bytes).hexdigest() == receipt["sha256_before"]
        red_04 = (path.parent / "04-red.txt").read_text()
        assert expected_04_line in red_04


def test_driver_cli_validates_arguments_and_invokes_main(tmp_path, monkeypatch):
    """Verify mutate.cli() validates arguments and forwards output_dir and allow_dirty to main()."""
    driver = load_driver()
    with pytest.raises(SystemExit, match="Usage: mutate.py"):
        driver.cli([])

    captured = []
    monkeypatch.setattr(
        driver,
        "main",
        lambda out_dir, *, allow_dirty=False: captured.append((out_dir, allow_dirty)) or 0,
    )
    assert driver.cli([str(tmp_path)]) == 0
    assert driver.cli(["--allow-dirty", str(tmp_path)]) == 0
    assert captured == [(tmp_path, False), (tmp_path, True)]


def test_target_missing_module_main_and_usage_guard(tmp_path):
    """Verify target_missing.main() validates arguments and handles zero-unit denominators."""
    helper = load_target_missing()
    with pytest.raises(SystemExit, match="Usage: target_missing.py"):
        helper.main([])

    zero_fixture = tmp_path / "zero_coverage.json"
    zero_fixture.write_text(
        json.dumps(
            {
                "totals": {
                    "num_statements": 0,
                    "num_branches": 0,
                    "covered_lines": 0,
                    "covered_branches": 0,
                },
                "files": {
                    target: {
                        "summary": {"missing_lines": 0, "missing_branches": 0},
                        "missing_lines": [],
                        "missing_branches": [],
                    }
                    for target in helper.TARGETS
                },
            }
        )
    )
    assert helper.summarize_coverage(zero_fixture) == 0
    assert helper.main([str(zero_fixture)]) == 0
