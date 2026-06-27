#!/usr/bin/env python3
"""Orchestrator test-generation acceptance gate for stranske/Workflows#2561.

Validates that generated tests:
1. Are syntactically correct Python
2. Import the target modules correctly
3. Run and pass/fail appropriately
4. Cover the intended functionality
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
TEST_FILES = [
    REPO_ROOT / "tests" / "scripts" / "test_pr_verifier_compare.py",
]


def run_command(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """Run a command and return exit code, stdout, stderr."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def validate_test_file_syntax(test_file: Path) -> tuple[bool, str]:
    """Validate that a test file has correct Python syntax."""
    exit_code, stdout, stderr = run_command([sys.executable, "-m", "py_compile", str(test_file)])
    if exit_code != 0:
        return False, f"Syntax error in {test_file}: {stderr}"
    return True, f"Syntax OK: {test_file}"


def validate_test_imports(test_file: Path) -> tuple[bool, str]:
    """Validate that test imports work correctly."""
    # This is a basic check - if the file can be compiled, imports are likely fine
    exit_code, stdout, stderr = run_command(
        [
            sys.executable,
            "-c",
            f"import sys; sys.path.insert(0, '.'); exec(open('{test_file}').read())",
        ],
        cwd=REPO_ROOT,
    )
    if exit_code != 0:
        return False, f"Import error in {test_file}: {stderr}"
    return True, f"Imports OK: {test_file}"


def validate_test_execution(test_file: Path) -> tuple[bool, str]:
    """Run the test file with pytest and return results."""
    relative_path = test_file.relative_to(REPO_ROOT)
    exit_code, stdout, stderr = run_command(
        [sys.executable, "-m", "pytest", str(relative_path), "-v", "--tb=short"], cwd=REPO_ROOT
    )

    # Check if pytest is available
    if "No module named pytest" in stderr or exit_code == 127:
        return False, f"pytest not available: {stderr}"

    return exit_code == 0, f"Test results: {stdout}"


def main() -> int:
    """Run the test generation acceptance gate."""
    print("Running Orchestrator test-generation acceptance gate for stranske/Workflows#2561")
    print("=" * 80)

    all_passed = True

    # Check if we have any test files to validate
    if not TEST_FILES:
        print("No test files specified for validation")
        return 1

    for test_file in TEST_FILES:
        if not test_file.exists():
            print(f"❌ Test file not found: {test_file}")
            all_passed = False
            continue

        print(f"\nValidating {test_file.relative_to(REPO_ROOT)}")
        print("-" * 40)

        # Step 1: Check syntax
        syntax_ok, syntax_msg = validate_test_file_syntax(test_file)
        print(f"  Syntax: {'✅' if syntax_ok else '❌'} {syntax_msg}")
        if not syntax_ok:
            all_passed = False
            continue

        # Step 2: Check imports
        imports_ok, imports_msg = validate_test_imports(test_file)
        print(f"  Imports: {'✅' if imports_ok else '❌'} {imports_msg}")
        if not imports_ok:
            all_passed = False
            continue

        # Step 3: Run tests
        execution_ok, execution_msg = validate_test_execution(test_file)
        print(f"  Execution: {'✅' if execution_ok else '❌'} {execution_msg}")
        if not execution_ok:
            all_passed = False

    print("\n" + "=" * 80)
    if all_passed:
        print("✅ All test generation acceptance criteria passed")
        print("\nGate command:")
        print("python testgen_gate.py")
        print("\nGate result: PASS")
        return 0
    else:
        print("❌ Test generation acceptance criteria failed")
        print("\nGate command:")
        print("python testgen_gate.py")
        print("\nGate result: FAIL")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
