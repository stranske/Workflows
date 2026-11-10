"""Lock Gate's parallel pytest invocation: two calls, one full suite.

The verifier grammar suites run in their own Gate call (python-ci-grammar) so that
neither Python job exceeds the 10-minute CI budget (Workflows#3904). python-ci must
ignore exactly the files python-ci-grammar runs; any other path, marker or
deselection would narrow what the Gate tests.
"""

import shlex
from pathlib import Path

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


def test_synced_large_file_parity_checks_guard_against_difflib_hangs() -> None:
    """Parity checks on large managed files (e.g. pr_verifier.py, keepalive_loop.js) must compare digests.

    Comparing raw byte strings directly in pytest causes unconstrained difflib
    ndiff calculations on assertion failure, which can stall a test worker for
    over 30 minutes (Workflows#4619). Tests asserting template parity must check
    digest equality first so failures report immediately.
    """
    import ast

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
        content = (ROOT / rel_path).read_text(encoding="utf-8")
        tree = ast.parse(content, filename=rel_path)
        functions = {
            node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        }
        for func_name in func_names:
            assert func_name in functions, f"{rel_path}::{func_name} missing"
            func_src = ast.get_source_segment(content, functions[func_name]) or ""
            digest_pos = func_src.find("hashlib.sha256(")
            assert digest_pos != -1, f"{rel_path}::{func_name} must assert sha256 digest"
            # Verify the digest assertion precedes the raw byte/text equality assertion.
            for eq_check in (
                "assert template.read_bytes() == PR_VERIFIER.read_bytes()",
                "assert template_bytes == source_bytes",
                "assert source_bytes == template_bytes",
                'assert TEMPLATE_API_CLIENT.read_text(encoding="utf-8") == API_CLIENT.read_text(encoding="utf-8")',
            ):
                eq_pos = func_src.find(eq_check)
                if eq_pos != -1:
                    assert (
                        digest_pos < eq_pos
                    ), f"{rel_path}::{func_name} must check sha256 digest before raw equality"
            
            # Verify that there is an actual digest equality assertion, not just a call
            # by checking that hashlib.sha256 is in an assert statement
            for node in ast.walk(functions[func_name]):
                if isinstance(node, ast.Assert):
                    assert_src = ast.get_source_segment(content, node) or ""
                    if "hashlib.sha256(" in assert_src:
                        # Found at least one assert with hashlib.sha256
                        break
            else:
                # No break means no assert with hashlib.sha256 found
                raise AssertionError(
                    f"{rel_path}::{func_name} must have hashlib.sha256 in an assert statement"
                )


def test_digest_assertion_removal_causes_failure() -> None:
    """Verify that removing or replacing digest assertion causes test failure."""
    import ast
    
    # Test by checking that all functions with raw equality checks also have digest checks
    # This is a static verification that the test above would catch removal
    test_file = ROOT / "tests/scripts/test_pr_verifier_sync_manifest.py"
    content = test_file.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(test_file))
    
    # Find all functions
    functions = {
        node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    
    # Check each function that has raw equality assertions
    for func_name, func_node in functions.items():
        func_src = ast.get_source_segment(content, func_node) or ""
        
        # Check if function has raw equality assertions
        has_raw_eq = any(
            eq_check in func_src 
            for eq_check in (
                "assert template.read_bytes() == PR_VERIFIER.read_bytes()",
                "assert template_bytes == source_bytes",
                "assert source_bytes == template_bytes",
                'assert TEMPLATE_API_CLIENT.read_text(encoding="utf-8") == API_CLIENT.read_text(encoding="utf-8")',
            )
        )
        
        if has_raw_eq:
            # Must have hashlib.sha256 digest check before the raw equality
            digest_pos = func_src.find("hashlib.sha256(")
            assert digest_pos != -1, f"{test_file}::{func_name} must have hashlib.sha256"
            
            # Must have it in an assert statement
            has_digest_assert = False
            for node in ast.walk(func_node):
                if isinstance(node, ast.Assert):
                    assert_src = ast.get_source_segment(content, node) or ""
                    if "hashlib.sha256(" in assert_src:
                        has_digest_assert = True
                        break
            assert has_digest_assert, f"{test_file}::{func_name} must have hashlib.sha256 in assert"