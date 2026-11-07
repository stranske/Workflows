"""Lock the #4000 and #4405 inventory against this branch and the evidence files.

#4000's three verifier tests are already in the tree. #4405's added tests were
absent at the recorded observation; later checkouts may contain them. Its Gate
run failed lint while pytest passed. Coverage arithmetic uses
the recovered 3.14 counters and keeps the original about-180 rule intact.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-4426"
INVENTORY_PATH = EVIDENCE / "pr-inventory.json"
MERGE_4000 = "5b1c6424716c413871d4eda7f6a125fa070e097f"


def _inventory() -> dict:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def _git_ok(*args: str) -> bool:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _show(revision: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def test_pr_4000_tests_are_on_this_branch_and_artifacts_are_unavailable() -> None:
    record = _inventory()["pull_requests"]["4000"]
    source = (ROOT / "tests/scripts/test_verifier_config.py").read_text(encoding="utf-8")
    for name in record["added_tests"]:
        assert f"def {name}" in source

    assert record["state"] == "MERGED"
    assert record["merge_commit"] == MERGE_4000
    assert record["head_oid"] == "faab1a08c210db85b803f4a54af408cc60bf792d"
    assert record["head_present_in_this_clone"] is False
    assert record["coverage_artifacts"]["available"] is False
    assert record["coverage_artifacts"]["gate_run_total_count"] == 0
    assert record["coverage_artifacts"]["selftest_run_total_count"] == 0
    assert record["ci"]["gate_conclusion"] == "success"
    assert record["ci"]["gate_head_sha"] == record["head_oid"]
    body = (ROOT / record["body_path"]).read_text(encoding="utf-8")
    assert hashlib.sha256(body.encode()).hexdigest() == record["body_sha256"]
    assert record["head_oid"] in body or "verifier" in body

    if _git_ok("cat-file", "-e", f"{MERGE_4000}^{{commit}}"):
        assert _git_ok("merge-base", "--is-ancestor", MERGE_4000, "HEAD")
        merged = _show(MERGE_4000, "tests/scripts/test_verifier_config.py")
        assert merged is not None
        for name in record["added_tests"]:
            assert f"def {name}" in merged


def test_pr_4405_tests_were_absent_at_the_recorded_observation() -> None:
    record = _inventory()["pull_requests"]["4405"]
    assert record["state"] == "OPEN"
    assert record["merge_commit"] is None
    assert record["head_on_observed_main"] is False
    assert record["added_tests_on_observed_main"] is False
    # These flags describe the pinned historical main, not today's checkout.
    assert record["added_tests"]
    assert all(names for names in record["added_tests"].values())

    body = (ROOT / record["body_path"]).read_text(encoding="utf-8")
    assert hashlib.sha256(body.encode()).hexdigest() == record["body_sha256"]
    assert record["ci"]["gate_conclusion"] == "failure"
    assert record["ci"]["gate_head_sha"] == record["head_oid"]
    assert record["ci"]["pytest_3_14"]["failures"] == 0
    assert "F841" in record["ci"]["lint_ruff"]["message"]
    assert "FakeChatOpenAI" in record["ci"]["lint_ruff"]["message"]


def test_recovered_4405_coverage_keeps_blended_accounting() -> None:
    record = _inventory()
    coverage = record["pull_requests"]["4405"]["coverage_artifacts"]
    totals = coverage["python_3_14"]
    covered = totals["covered_lines"] + totals["covered_branches"]
    denominator = totals["num_statements"] + totals["num_branches"]
    assert (covered, denominator) == (63015, 69223)
    assert f"{covered / denominator * 100:.2f}" == totals["percent_covered_display"]
    assert totals["missing_lines"] + totals["missing_branches"] == 6208
    assert totals["missing_lines"] + totals["num_partial_branches"] == 5564
    assert totals["summary_json_percent"] == 92.46
    assert coverage["python_3_13"]["coverage_json"] is False
    assert coverage["coverage_json_sha256"]
    assert "about 180" in (EVIDENCE / "pr-inventory.md").read_text(encoding="utf-8")

    missing_units = 0
    for target in coverage["targets"].values():
        missing_units += target["missing_lines"] + target["missing_branches"]
    assert missing_units == 3 + 5 + 13 + 9 + 0 + 0 + 1 + 1 + 3 + 3 + 158 + 116
    assert coverage["targets"]["scripts/langchain/verifier_config.py"]["missing_lines"] == 0
