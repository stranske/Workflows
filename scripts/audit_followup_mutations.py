"""Audit issue #3956 receipts without executing their recorded commands."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path

PYTHON_SOURCE = "scripts/langchain/followup_issue_generator.py"
PYTHON_TEST = "tests/test_followup_issue_generator.py"
NODE_SOURCE = ".github/scripts/agents_pr_meta_update_body.js"
NODE_TEST = ".github/scripts/__tests__/agents-pr-meta-update-body.test.js"
NODE_CASES = {
    "parseCheckboxStates captures numbered checklist completions",
    "mergeCheckboxStates restores numbered contract checklist items across refresh",
}
EVIDENCE = "docs/evidence/issue-3956"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _functions(text: str) -> set[str]:
    def discover(nodes, prefix=""):
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    yield prefix + node.name
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                yield from discover(node.body, prefix + node.name + "::")

    return set(discover(ast.parse(text).body))


def _is_commit_sha(value: object) -> bool:
    """Require an immutable revision identifier, not a branch or abbreviation."""
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def _matches_mutation(source: str, before: str, mutant: str, expected: str) -> bool:
    """Bind the replacement to its recorded location even when text repeats."""
    if not before or before == mutant:
        return False
    position = source.find(before)
    while position >= 0:
        candidate = source[:position] + mutant + source[position + len(before) :]
        if _sha(candidate) == expected:
            return True
        position = source.find(before, position + 1)
    return False


def _single_pytest_result(output: str, outcome: str) -> bool:
    """Require the final pytest summary to report exactly one outcome."""
    lines = output.strip().splitlines()
    return bool(
        lines
        and re.fullmatch(
            rf"(?:=+\s*)?1 {outcome}(?: in \d+(?:\.\d+)?s)?(?:\s*=+)?",
            lines[-1],
        )
    )


def _single_node_result(output: str, case: str, *, passed: bool) -> bool:
    """Bind the retained spec-reporter result and counts to the selected case."""
    marker = "✔" if passed else "✖"
    if not re.search(
        rf"^[ \t]*{marker} {re.escape(case)}(?: \([^\r\n]*\))?[ \t]*$",
        output,
        re.MULTILINE,
    ):
        return False
    counts = {"tests": 1, "pass": int(passed), "fail": int(not passed)}
    for label, expected in counts.items():
        recorded = re.findall(rf"^[ \t]*(?:ℹ[ \t]*)?{label} (\d+)[ \t]*$", output, re.MULTILINE)
        if recorded != [str(expected)]:
            return False
    return True


def audit(root: Path, baseline_tests: str, collected: set[str]) -> dict:
    """Compare independently collected added cases with the retained evidence."""
    original_receipt = (root / EVIDENCE / "retained-mutation-reconciliation.json").read_text(
        encoding="utf-8"
    )
    python = json.loads(original_receipt)
    node = json.loads(
        (root / EVIDENCE / "numbered-checklist-repair-proof.json").read_text(encoding="utf-8")
    )
    source = (root / PYTHON_SOURCE).read_text(encoding="utf-8")
    tests = (root / PYTHON_TEST).read_text(encoding="utf-8")
    node_source = (root / NODE_SOURCE).read_text(encoding="utf-8")
    added = _functions(tests) - _functions(baseline_tests)
    expected = {
        case
        for case in collected
        if case.startswith(PYTHON_TEST + "::")
        and case.removeprefix(PYTHON_TEST + "::").split("[")[0] in added
    }
    mapped = {proof["test"] for proof in python["proofs"]}
    problems = []
    rows = []
    for label, receipt in (("Python", python), ("Node", node)):
        if not _is_commit_sha(receipt.get("revision")):
            problems.append(f"{label} receipt revision must be a full commit SHA")
    python_revisions = [python.get("revision")] * len(python["proofs"])
    python_receipt_files = ["retained-mutation-reconciliation.json"] * len(python["proofs"])
    python_receipt_indices = list(range(len(python["proofs"])))
    reruns = root / EVIDENCE / "retained-mutation-unabridged-reruns.json"
    rerun_revision = None
    if reruns.exists():
        supplement = json.loads(reruns.read_text(encoding="utf-8"))
        if not _is_commit_sha(supplement.get("revision")):
            problems.append("Supplemental receipt revision must be a full commit SHA")
        elif (
            supplement["historical_sha256"] != _sha(original_receipt)
            or supplement["source_sha256"] != _sha(source)
            or supplement["test_sha256"] != _sha(tests)
        ):
            problems.append(
                "Supplemental receipts are not bound to the historical index/source/tests"
            )
        else:
            rerun_revision = supplement["revision"]
            seen = set()
            for replacement_index, replacement in enumerate(supplement["proofs"]):
                index = replacement["historical_index"]
                if (
                    type(index) is not int
                    or not 0 <= index < len(python["proofs"])
                    or index in seen
                ):
                    problems.append("Supplemental receipt has an invalid or duplicate index")
                    continue
                seen.add(index)
                original = python["proofs"][index]
                if any(
                    original[key] != replacement[key]
                    for key in ("name", "test", "before", "mutant", "mutant_source_sha256")
                ):
                    problems.append(f"Supplemental receipt {index} changes the historical mutation")
                    continue
                python["proofs"][index] = replacement
                python_revisions[index] = supplement["revision"]
                python_receipt_files[index] = reruns.name
                python_receipt_indices[index] = replacement_index
    if python["source_sha256"] != _sha(source) or python["test_sha256"] != _sha(tests):
        problems.append("Python source/test hashes do not match the inspected checkout")
    if python.get("revision") != node.get("revision"):
        problems.append("Python and Node receipts name different source revisions")
    uncollected = added - {case.removeprefix(PYTHON_TEST + "::").split("[")[0] for case in expected}
    if not expected or uncollected:
        problems.append(f"Added tests missing from collection: {sorted(uncollected)}")
    if mapped != expected:
        problems.append(
            f"Case mapping differs: missing={sorted(expected - mapped)}, "
            f"unexpected={sorted(mapped - expected)}"
        )

    for language, receipts in (("python", python["proofs"]), ("node", node["proofs"])):
        for index, proof in enumerate(receipts):
            issues = []
            red, green = proof["red_output"], proof["green_output"]
            assertion = (
                re.search(r"^E\s+AssertionError\b|^.+\.py:\d+: AssertionError\b", red, re.MULTILINE)
                if language == "python"
                else re.search(r"^\s*AssertionError \[ERR_ASSERTION\]", red, re.MULTILINE)
            )
            if proof["red_exit"] != 1 or not assertion:
                issues.append("RED is not an assertion failure with exit 1")
            if proof["green_exit"] != 0:
                issues.append("GREEN exit is not 0")
            if re.search(r"output truncated|\d+ lines? hidden", red + green, re.IGNORECASE):
                issues.append("receipt output is truncated")
            if language == "python":
                selected_failure = re.search(
                    rf"^FAILED {re.escape(proof['test'])}(?: -|$)", red, re.MULTILINE
                )
                if (
                    not selected_failure
                    or not _single_pytest_result(red, "failed")
                    or not _single_pytest_result(green, "passed")
                ):
                    issues.append("RED/GREEN does not identify a single selected case")
                if proof["test"] not in proof["command"]:
                    issues.append("command does not select the recorded case")
                if proof["restored_source_sha256"] != _sha(source):
                    issues.append("restored source hash mismatch")
                mutant_hash = proof["mutant_source_sha256"]
                original = source
            else:
                if proof["test"] not in red or proof["test"] not in green:
                    issues.append("RED/GREEN names a different Node case")
                if not re.search(r"\bpass 1\b", green) or not re.search(r"\bfail 0\b", green):
                    issues.append("Node GREEN does not report one pass and zero failures")
                if not _single_node_result(
                    red, proof["test"], passed=False
                ) or not _single_node_result(green, proof["test"], passed=True):
                    issues.append("Node RED/GREEN does not identify a single selected case")
                if (
                    f"--test-name-pattern={proof['test']}" not in proof["command"]
                    or NODE_TEST not in proof["command"]
                ):
                    issues.append("command does not select the recorded Node case")
                if proof["source_sha256"] != _sha(node_source):
                    issues.append("Node source hash mismatch")
                mutant_hash = proof["mutant_sha256"]
                original = node_source
            if not _matches_mutation(original, proof["before"], proof["mutant"], mutant_hash):
                issues.append("mutation text/location does not reproduce its source hash")
            rows.append(
                {
                    "language": language,
                    "test": proof["test"],
                    "mutation": proof.get("name", proof["test"]),
                    "receipt_index": (
                        python_receipt_indices[index] if language == "python" else index
                    ),
                    "historical_index": index,
                    "receipt_file": (
                        python_receipt_files[index]
                        if language == "python"
                        else "numbered-checklist-repair-proof.json"
                    ),
                    "source_revision": (
                        python_revisions[index] if language == "python" else node.get("revision")
                    ),
                    "before": proof["before"],
                    "mutant": proof["mutant"],
                    "assertion": "\n".join(
                        line
                        for line in red.splitlines()
                        if line.startswith(("E ", ">")) or "AssertionError" in line
                    ),
                    "restored_green": green,
                    "issues": issues,
                }
            )
    expected_node = set(
        re.findall(r"test\('([^']+)'", (root / NODE_TEST).read_text(encoding="utf-8"))
    )
    mapped_node = {proof["test"] for proof in node["proofs"]}
    if mapped_node != NODE_CASES or not mapped_node <= expected_node:
        problems.append("The two retained Node cases are missing or do not exist in the test file")
    return {
        "revision": python.get("revision"),
        "rerun_revision": rerun_revision,
        "source_sha256": python["source_sha256"],
        "test_sha256": python["test_sha256"],
        "added_functions": len(added),
        "collected_added_cases": len(expected),
        "python_receipts": len(python["proofs"]),
        "node_receipts": len(node["proofs"]),
        "problems": problems,
        "receipts": rows,
        "complete": not problems and all(not row["issues"] for row in rows),
    }


def main() -> int:
    """Audit independently collected cases against UTF-8 repository evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--baseline-tests", type=Path, required=True)
    parser.add_argument("--collected-tests", type=Path, required=True)
    args = parser.parse_args()
    collected = set(args.collected_tests.read_text(encoding="utf-8").splitlines())
    result = audit(args.root, args.baseline_tests.read_text(encoding="utf-8"), collected)
    print(json.dumps(result, indent=2))
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
