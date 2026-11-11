"""Lock Gate's parallel pytest invocation: two calls, one full suite.

The verifier grammar suites run in their own Gate call (python-ci-grammar) so that
neither Python job exceeds the 10-minute CI budget (Workflows#3904). python-ci must
ignore exactly the files python-ci-grammar runs; any other path, marker or
deselection would narrow what the Gate tests.
"""

import ast
import shlex
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEDULING = ["-n", "auto", "--dist", "load"]


def _jobs() -> dict:
    return yaml.safe_load((ROOT / ".github/workflows/pr-00-gate.yml").read_text())["jobs"]


def grammar_files() -> list[str]:
    """The test files the python-ci-grammar call runs, in workflow order."""
    args = shlex.split(_jobs()["python-ci-grammar"]["with"]["pytest_args"])
    assert args[: len(SCHEDULING)] == SCHEDULING
    return args[len(SCHEDULING) :]


def test_gate_pytest_args_are_parallel() -> None:
    inputs = _jobs()["python-ci"]["with"]
    args = shlex.split(inputs["pytest_args"])
    assert args[: len(SCHEDULING)] == SCHEDULING
    # Only scheduling flags plus the grammar split: no other paths, markers or deselection.
    assert args[len(SCHEDULING) :] == [f"--ignore={path}" for path in grammar_files()]
    assert inputs["coverage-min"] == "70"


def test_grammar_call_partitions_the_full_suite() -> None:
    jobs = _jobs()
    files = grammar_files()
    assert files, "python-ci-grammar must run at least one file"
    assert len(set(files)) == len(files)
    for path in files:
        assert (ROOT / path).is_file(), f"{path} is listed but missing"
        assert path.startswith("tests/") and path.endswith(".py")
    main, grammar = jobs["python-ci"], jobs["python-ci-grammar"]
    assert grammar["if"] == main["if"]
    assert grammar["needs"] == main["needs"]
    for key in ("python-versions", "pytest-workers", "marker", "pytest_markers", "workflows_ref"):
        assert grammar["with"][key] == main["with"][key], key
    # Coverage stays on python-ci; the grammar call must not publish into gate-*.
    assert grammar["with"]["coverage"] is False
    assert not grammar["with"]["artifact-prefix"].startswith("gate-")
    assert "python-ci-grammar" in jobs["summary"]["needs"]
    summarize = next(
        step for step in jobs["summary"]["steps"] if step.get("name") == "Summarize results"
    )
    assert "needs.python-ci-grammar.result == 'failure'" in summarize["env"]["PYTHON_RESULT"]


def _sha256_input(node: ast.expr) -> ast.expr:
    match node:
        case ast.Call(
            func=ast.Attribute(
                value=ast.Call(
                    func=ast.Attribute(value=ast.Name(id="hashlib"), attr="sha256"),
                    args=[data],
                    keywords=[],
                ),
                attr="hexdigest" | "digest",
            ),
            args=[],
            keywords=[],
        ):
            return data
    return node


def _assert_digest_guards(
    statements: list[ast.stmt],
    location: str,
    reads: dict[str, str] | None = None,
    guards: set[frozenset[str]] | None = None,
) -> int:
    reads = dict(reads or {})
    guards = set(guards or ())
    comparisons = 0
    assigned = {}

    def file_read(node: ast.expr) -> str | None:
        match node:
            case ast.Call(func=ast.Attribute(value=path, attr="read_bytes" | "read_text")):
                return ast.dump(path)
            case ast.Name(id=name):
                return reads.get(name)
        return None

    for statement in statements:
        match statement:
            case ast.Assign(targets=[ast.Name(id=name)], value=value):
                guards = {pair for pair in guards if reads.get(name) not in pair}
                # Digest booleans must refer to the reads in effect at the assertion.
                if name in reads:
                    assigned.clear()
                assigned[name] = value
                if (path := file_read(value)) is not None:
                    reads[name] = path
                else:
                    reads.pop(name, None)
            case ast.For(body=body):
                comparisons += _assert_digest_guards(body, location, reads, guards)
            case ast.Assert(test=test):
                if isinstance(test, ast.Name):
                    test = assigned.get(test.id, test)
                match test:
                    case ast.Compare(left=left, ops=[ast.Eq()], comparators=[right]):
                        pass
                    case _:
                        continue
                left_data, right_data = _sha256_input(left), _sha256_input(right)
                left_path, right_path = file_read(left_data), file_read(right_data)
                if left_path is None or right_path is None:
                    continue
                pair = frozenset((left_path, right_path))
                if left_data is not left and right_data is not right:
                    guards.add(pair)
                elif left_data is left and right_data is right:
                    comparisons += 1
                    assert (
                        pair in guards
                    ), f"{location}:{statement.lineno} must check sha256 digest before raw equality"
    return comparisons


def test_synced_large_file_parity_checks_guard_against_difflib_hangs() -> None:
    """Require each managed-file equality to follow a digest equality for the same pair."""
    parity_test_functions = {
        "tests/scripts/test_pr_verifier_sync_manifest.py": (
            "test_pr_verifier_api_client_is_available_in_consumer_template",
            "test_pr_verifier_source_and_consumer_template_are_identical",
            "test_capture_obligation_dependency_is_managed_and_identical",
        ),
        "tests/scripts/test_native_capacity_registry.py": (
            "test_native_facts_and_helper_are_managed_with_exact_template_parity",
        ),
        "tests/workflows/test_keepalive_authority_delivery.py": (
            "test_authority_helpers_are_manifested_and_byte_aligned",
        ),
        "tests/workflows/test_repeat_verification_lifecycle.py": (
            "test_template_repeat_bypasses_only_coarse_fingerprint_and_threads_all_inputs",
        ),
        "tests/tools/test_verifier_request_correlation.py": (
            "test_workflow_and_template_forward_basis_to_authenticated_manifest_and_markers",
        ),
    }
    for rel_path, func_names in parity_test_functions.items():
        tree = ast.parse((ROOT / rel_path).read_text(encoding="utf-8"), filename=rel_path)
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        for func_name in func_names:
            location = f"{rel_path}::{func_name}"
            assert func_name in functions, f"{location} missing"
            assert _assert_digest_guards(
                functions[func_name].body, location
            ), f"{location} must check managed-file parity"


@pytest.mark.parametrize("guard", ["", "assert hashlib.sha256(other.read_bytes()).digest()"])
def test_digest_assertion_removal_causes_failure(guard: str) -> None:
    """A missing or unrelated digest assertion must leave raw parity unguarded."""
    tree = ast.parse(
        f"{guard}\n"
        "actual = source.read_bytes()\n"
        "assert (template.read_text(encoding='utf-8')) == actual\n"
    )
    with pytest.raises(AssertionError, match="must check sha256 digest before raw equality"):
        _assert_digest_guards(tree.body, "example")
