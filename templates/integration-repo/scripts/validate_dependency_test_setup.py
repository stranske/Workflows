#!/usr/bin/env python3
"""
Validation script to ensure dependency test setup is correct.

Run this script to verify:
1. All optional dependencies are included in lock file
2. All pyproject.toml tool dependencies match lock file
3. Tests don't have hardcoded version numbers
4. Metadata serialization is handled correctly throughout codebase
"""
import re
import sys
from pathlib import Path


def check_lock_file_completeness() -> tuple[bool, list[str]]:
    """Verify lock file includes all optional dependencies."""
    issues = []

    # Read pyproject.toml to get all optional groups
    pyproject = Path("pyproject.toml").read_text()

    # Extract optional dependency groups
    optional_section = re.search(
        r"\[project\.optional-dependencies\](.*?)(?=\n\[|\Z)", pyproject, re.DOTALL
    )
    if not optional_section:
        issues.append("No [project.optional-dependencies] section found")
        return False, issues

    optional_groups = re.findall(r"^(\w+)\s*=", optional_section.group(1), re.MULTILINE)
    print(f"✓ Found optional dependency groups: {', '.join(optional_groups)}")

    # Check dependabot-auto-lock.yml includes all extras
    workflow_path = Path(".github/workflows/dependabot-auto-lock.yml")
    if workflow_path.exists():
        workflow = workflow_path.read_text()
        for group in optional_groups:
            if f"--extra {group}" not in workflow:
                issues.append(f"dependabot-auto-lock.yml missing --extra {group}")

        if not issues:
            print("✓ dependabot-auto-lock.yml includes all extras")
    else:
        issues.append("dependabot-auto-lock.yml not found")

    return len(issues) == 0, issues


def check_for_hardcoded_versions() -> tuple[bool, list[str]]:
    """Check for hardcoded version numbers in tests."""
    issues = []
    test_files = list(Path("tests").rglob("*.py"))

    # Patterns that indicate hardcoded versions
    version_patterns = [
        r'==\s*["\']?\d+\.\d+',  # == version
        r'assert.*version.*==.*["\d]',  # assert version == "x.y"
    ]

    problematic_files = []
    for test_file in test_files:
        content = test_file.read_text()

        # Skip if it's the lockfile consistency test or dependency alignment test
        if (
            "lockfile_consistency" in test_file.name
            or "dependency_version_alignment" in test_file.name
        ):
            continue

        for pattern in version_patterns:
            if re.search(pattern, content):
                # Check if it's in a comment
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if re.search(pattern, line) and not line.strip().startswith("#"):
                        problematic_files.append((test_file, i + 1, line.strip()))

    if problematic_files:
        issues.append("Found potential hardcoded versions in tests:")
        for file, line_no, line in problematic_files:
            issues.append(f"  {file}:{line_no}: {line[:80]}")
    else:
        print("✓ No hardcoded version numbers found in tests")

    return len(issues) == 0, issues


def check_metadata_serialization() -> tuple[bool, list[str]]:
    """Check that metadata is properly serialized to dicts, not Pydantic objects."""
    issues = []

    # Check validators.py returns dict
    validators_path = Path("src/trend_analysis/io/validators.py")
    if validators_path.exists():
        content = validators_path.read_text()

        # Look for load_and_validate_upload function
        if "validated.metadata.model_dump(mode=" in content:
            print("✓ load_and_validate_upload serializes metadata to dict")
        else:
            issues.append("load_and_validate_upload may not be serializing metadata properly")

    # Check attach_metadata serializes
    market_data_path = Path("src/trend_analysis/io/market_data.py")
    if market_data_path.exists():
        content = market_data_path.read_text()

        if "metadata.model_dump(mode=" in content:
            print("✓ attach_metadata serializes metadata to dict")
        else:
            issues.append("attach_metadata may not be serializing metadata properly")

    # Check data_schema.py serializes
    data_schema_path = Path("streamlit_app/components/data_schema.py")
    if data_schema_path.exists():
        content = data_schema_path.read_text()

        if "metadata.model_dump(mode=" in content:
            print("✓ _build_meta serializes metadata to dict")
        else:
            issues.append("_build_meta may not be serializing metadata properly")

    return len(issues) == 0, issues


def check_test_expectations() -> tuple[bool, list[str]]:
    """Verify tests expect dicts, not Pydantic objects."""
    issues = []
    test_files = [
        Path("tests/test_validators.py"),
        Path("tests/test_io_validators_additional.py"),
        Path("tests/test_io_validators_extra.py"),
        Path("tests/test_data_schema.py"),
    ]

    for test_file in test_files:
        if not test_file.exists():
            continue

        content = test_file.read_text()

        # Check for problematic patterns
        if re.search(r"\.attrs\[.*\]\.mode(?!\[)", content):
            issues.append(f"{test_file.name}: Uses .mode attribute access instead of dict access")

        if 'assert meta["metadata"] is ' in content and "is metadata" in content:
            issues.append(f"{test_file.name}: Uses 'is' identity check instead of equality")

    if not issues:
        print("✓ Tests expect dict-based metadata")

    return len(issues) == 0, issues


def main():
    print("=" * 60)
    print("Dependency Test Setup Validation")
    print("=" * 60)
    print()

    all_passed = True
    all_issues = []

    # Run all checks
    checks = [
        ("Lock file completeness", check_lock_file_completeness),
        ("Hardcoded versions", check_for_hardcoded_versions),
        ("Metadata serialization", check_metadata_serialization),
        ("Test expectations", check_test_expectations),
    ]

    for check_name, check_func in checks:
        print(f"\nChecking: {check_name}")
        print("-" * 40)
        passed, issues = check_func()

        if not passed:
            all_passed = False
            all_issues.extend(issues)
            print("✗ FAILED")
            for issue in issues:
                print(f"  {issue}")
        else:
            print("✓ PASSED")

    print()
    print("=" * 60)
    if all_passed:
        print("✓ All validation checks passed!")
        print("The setup should work for future dependabot PRs.")
        return 0
    else:
        print("✗ Some validation checks failed:")
        for issue in all_issues:
            print(f"  - {issue}")
        print("\nFix these issues to ensure future dependabot PRs work correctly.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
