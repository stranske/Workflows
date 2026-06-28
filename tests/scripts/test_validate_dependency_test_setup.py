"""P0.2 acceptance: validate_dependency_test_setup.py behavior over fixtures.

Asserts all validation checks work correctly:
1. Lock file completeness check
2. Hardcoded versions detection
3. Metadata serialization check
4. Test expectations check

Generated for stranske/Workflows#2620.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _get_repo_root():
    """Get the repository root, handling both import and exec contexts."""
    try:
        return Path(__file__).resolve().parent.parent.parent
    except NameError:
        # When exec'd, __file__ is not defined; use cwd instead
        return Path.cwd()


REPO_ROOT = _get_repo_root()
VALIDATOR = REPO_ROOT / "scripts" / "validate_dependency_test_setup.py"


def _import_validator():
    """Import the validator module dynamically."""
    import importlib.util

    name = "validate_dependency_test_setup"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, VALIDATOR)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestCheckLockFileCompleteness:
    """Tests for check_lock_file_completeness function."""

    def test_missing_optional_dependencies_section(self, tmp_path, monkeypatch) -> None:
        """When pyproject.toml has no optional-dependencies section, should report error."""
        mod = _import_validator()

        # Create a pyproject.toml without optional-dependencies
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"\n')

        monkeypatch.chdir(tmp_path)
        passed, issues = mod.check_lock_file_completeness()

        assert not passed
        assert any("No [project.optional-dependencies] section found" in issue for issue in issues)

    def test_optional_dependencies_section_exists(self, tmp_path, monkeypatch) -> None:
        """When pyproject.toml has optional-dependencies with groups, should pass."""
        mod = _import_validator()

        # Create a pyproject.toml with optional-dependencies
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[project.optional-dependencies]
test = ["pytest>=7.0"]
dev = ["black>=24.0"]
""")

        # Create dependabot-auto-lock.yml that references all groups
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)
        workflow = workflows_dir / "dependabot-auto-lock.yml"
        workflow.write_text("""
name: dependabot-auto-lock
on:
  schedule:
    - cron: '0 0 * * *'
jobs:
  lock:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install --upgrade pip
      - run: pip install --extra test --extra dev
""")

        monkeypatch.chdir(tmp_path)
        passed, issues = mod.check_lock_file_completeness()

        assert passed

    def test_dependabot_missing_extras(self, tmp_path, monkeypatch) -> None:
        """When dependabot-auto-lock.yml is missing --extra for some groups, should report error."""
        mod = _import_validator()

        # Create a pyproject.toml with optional-dependencies
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[project.optional-dependencies]
test = ["pytest>=7.0"]
dev = ["black>=24.0"]
prod = ["requests>=2.0"]
""")

        # Create dependabot-auto-lock.yml that only references test and dev
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)
        workflow = workflows_dir / "dependabot-auto-lock.yml"
        workflow.write_text("""
name: dependabot-auto-lock
on:
  schedule:
    - cron: '0 0 * * *'
jobs:
  lock:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install --upgrade pip
      - run: pip install --extra test --extra dev
""")

        monkeypatch.chdir(tmp_path)
        passed, issues = mod.check_lock_file_completeness()

        assert not passed
        assert any("dependabot-auto-lock.yml missing --extra prod" in issue for issue in issues)

    def test_dependabot_dynamic_groups(self, tmp_path, monkeypatch) -> None:
        """When dependabot uses dynamic group extraction, should pass."""
        mod = _import_validator()

        # Create a pyproject.toml with optional-dependencies
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[project.optional-dependencies]
test = ["pytest>=7.0"]
dev = ["black>=24.0"]
""")

        # Create dependabot-auto-lock.yml with dynamic extraction
        # Note: The script checks for "optional-dependencies", "tomllib", and "tools/requirements-llm.txt"
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)
        workflow = workflows_dir / "dependabot-auto-lock.yml"
        workflow.write_text("""
name: dependabot-auto-lock
on:
  schedule:
    - cron: '0 0 * * *'
jobs:
  lock:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install --upgrade pip
      - run: |
          import tomllib
          import pathlib
          config = tomllib.loads(pathlib.Path('pyproject.toml').read_text())
          extras = list(config['project']['optional-dependencies'].keys())
          # Reference to tools/requirements-llm.txt for dynamic extraction
          with open('tools/requirements-llm.txt', 'r') as f:
              llm_reqs = f.read()
          for extra in extras:
              pip install --extra ${extra}
""")

        monkeypatch.chdir(tmp_path)
        passed, issues = mod.check_lock_file_completeness()

        assert passed

    def test_dependabot_file_missing(self, tmp_path, monkeypatch) -> None:
        """When dependabot-auto-lock.yml doesn't exist, should report error."""
        mod = _import_validator()

        # Create a pyproject.toml with optional-dependencies
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[project.optional-dependencies]
test = ["pytest>=7.0"]
""")

        monkeypatch.chdir(tmp_path)
        passed, issues = mod.check_lock_file_completeness()

        assert not passed
        assert any("dependabot-auto-lock.yml not found" in issue for issue in issues)


class TestCheckForHardcodedVersions:
    """Tests for check_for_hardcoded_versions function."""

    def test_no_hardcoded_versions(self, tmp_path, monkeypatch) -> None:
        """When tests have no hardcoded versions, should pass."""
        mod = _import_validator()

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_example.py"
        test_file.write_text("""
def test_something():
    assert True
    # Version mentioned in comment: == 1.0.0
""")

        monkeypatch.chdir(tmp_path)
        passed, issues = mod.check_for_hardcoded_versions()

        assert passed

    def test_hardcoded_version_in_code(self, tmp_path, monkeypatch) -> None:
        """When tests have hardcoded version assertions, should report error."""
        mod = _import_validator()

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_example.py"
        test_file.write_text("""
def test_version():
    assert version == "1.2.3"
""")

        monkeypatch.chdir(tmp_path)
        passed, issues = mod.check_for_hardcoded_versions()

        assert not passed
        assert any("test_example.py" in issue for issue in issues)
        assert any("==" in issue for issue in issues)

    def test_hardcoded_version_in_requirements(self, tmp_path, monkeypatch) -> None:
        """When tests have hardcoded version in requirements, should report error."""
        mod = _import_validator()

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_example.py"
        test_file.write_text("""
REQUIREMENT = "pytest==7.0.0"

def test_something():
    pass
""")

        monkeypatch.chdir(tmp_path)
        passed, issues = mod.check_for_hardcoded_versions()

        assert not passed
        assert any("test_example.py" in issue for issue in issues)

    def test_allowed_test_files_skipped(self, tmp_path, monkeypatch) -> None:
        """When version alignment test files have versions, they should be skipped."""
        mod = _import_validator()

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        # Create a lockfile consistency test with hardcoded versions
        lockfile_test = tests_dir / "test_lockfile_consistency.py"
        lockfile_test.write_text("""
def test_versions_match():
    assert package_version == "1.2.3"
""")

        # Create a dependency version alignment test
        dep_test = tests_dir / "test_dependency_version_alignment.py"
        dep_test.write_text("""
def test_alignment():
    assert "pytest==7.0.0" in requirements
""")

        monkeypatch.chdir(tmp_path)
        passed, issues = mod.check_for_hardcoded_versions()

        # These files should be skipped, so no issues
        assert passed

    def test_version_in_comment_allowed(self, tmp_path, monkeypatch) -> None:
        """When version is only in comment, should pass."""
        mod = _import_validator()

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_example.py"
        test_file.write_text("""
# This test requires pytest==7.0.0 to run

def test_something():
    assert True
""")

        monkeypatch.chdir(tmp_path)
        passed, issues = mod.check_for_hardcoded_versions()

        assert passed


class TestCheckMetadataSerialization:
    """Tests for check_metadata_serialization function."""

    def test_validators_serializes_metadata(self, tmp_path, monkeypatch) -> None:
        """When validators.py serializes metadata properly, should pass."""
        mod = _import_validator()

        # Create the validators.py file with proper serialization
        # Note: The script looks for "validated.metadata.model_dump(mode=" pattern
        src_dir = tmp_path / "src" / "trend_analysis" / "io"
        src_dir.mkdir(parents=True)
        validators = src_dir / "validators.py"
        validators.write_text("""
def load_and_validate_upload(data):
    result = validated.metadata.model_dump(mode='json')
    return {"metadata": result}
""")

        monkeypatch.chdir(tmp_path)
        passed, issues = mod.check_metadata_serialization()

        assert passed

    def test_validators_missing_serialization(self, tmp_path, monkeypatch) -> None:
        """When validators.py doesn't serialize metadata, should report error."""
        mod = _import_validator()

        # Create the validators.py file without proper serialization
        src_dir = tmp_path / "src" / "trend_analysis" / "io"
        src_dir.mkdir(parents=True)
        validators = src_dir / "validators.py"
        validators.write_text("""
def load_and_validate_upload(data):
    metadata = data.get('metadata')
    return {"metadata": metadata}
""")

        monkeypatch.chdir(tmp_path)
        passed, issues = mod.check_metadata_serialization()

        assert not passed
        assert any(
            "load_and_validate_upload may not be serializing metadata properly" in issue
            for issue in issues
        )

    def test_market_data_serializes_metadata(self, tmp_path, monkeypatch) -> None:
        """When market_data.py serializes metadata properly, should pass."""
        mod = _import_validator()

        # Create the market_data.py file with proper serialization
        src_dir = tmp_path / "src" / "trend_analysis" / "io"
        src_dir.mkdir(parents=True)
        market_data = src_dir / "market_data.py"
        market_data.write_text("""
def attach_metadata(data):
    metadata = data.get('metadata')
    return {"metadata": metadata.model_dump(mode='json')}
""")

        monkeypatch.chdir(tmp_path)
        passed, issues = mod.check_metadata_serialization()

        assert passed

    def test_market_data_missing_serialization(self, tmp_path, monkeypatch) -> None:
        """When market_data.py doesn't serialize metadata, should report error."""
        mod = _import_validator()

        # Create the market_data.py file without proper serialization
        src_dir = tmp_path / "src" / "trend_analysis" / "io"
        src_dir.mkdir(parents=True)
        market_data = src_dir / "market_data.py"
        market_data.write_text("""
def attach_metadata(data):
    metadata = data.get('metadata')
    return {"metadata": metadata}
""")

        monkeypatch.chdir(tmp_path)
        passed, issues = mod.check_metadata_serialization()

        assert not passed
        assert any(
            "attach_metadata may not be serializing metadata properly" in issue for issue in issues
        )

    def test_data_schema_serializes_metadata(self, tmp_path, monkeypatch) -> None:
        """When data_schema.py serializes metadata properly, should pass."""
        mod = _import_validator()

        # Create the data_schema.py file with proper serialization
        streamlit_dir = tmp_path / "streamlit_app" / "components"
        streamlit_dir.mkdir(parents=True)
        data_schema = streamlit_dir / "data_schema.py"
        data_schema.write_text("""
def _build_meta(data):
    metadata = data.get('metadata')
    return metadata.model_dump(mode='json')
""")

        monkeypatch.chdir(tmp_path)
        passed, issues = mod.check_metadata_serialization()

        assert passed

    def test_files_missing(self, tmp_path, monkeypatch) -> None:
        """When required files don't exist, should pass (they're optional checks)."""
        mod = _import_validator()

        monkeypatch.chdir(tmp_path)
        passed, issues = mod.check_metadata_serialization()

        # No files exist, so no errors
        assert passed


class TestCheckTestExpectations:
    """Tests for check_test_expectations function."""

    def test_no_problematic_patterns(self, tmp_path, monkeypatch) -> None:
        """When tests use proper dict access, should pass."""
        mod = _import_validator()

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        # Create test files with proper patterns
        test_validators = tests_dir / "test_validators.py"
        test_validators.write_text("""
def test_metadata_access():
    meta = {"metadata": {"key": "value"}}
    assert meta["metadata"]["key"] == "value"
""")

        monkeypatch.chdir(tmp_path)
        passed, issues = mod.check_test_expectations()

        assert passed

    def test_problematic_mode_attribute(self, tmp_path, monkeypatch) -> None:
        """When tests use .mode attribute access, should report error."""
        mod = _import_validator()

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        test_validators = tests_dir / "test_validators.py"
        test_validators.write_text("""
def test_metadata_mode():
    meta = get_metadata()
    assert meta.attrs["field"].mode == "json"
""")

        monkeypatch.chdir(tmp_path)
        passed, issues = mod.check_test_expectations()

        assert not passed
        assert any(".mode attribute access" in issue for issue in issues)

    def test_problematic_identity_check(self, tmp_path, monkeypatch) -> None:
        """When tests use 'is' identity check for metadata, should report error."""
        mod = _import_validator()

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        # Note: The script checks for both 'assert meta["metadata"] is ' AND 'is metadata'
        test_validators = tests_dir / "test_validators.py"
        test_validators.write_text("""
METADATA = {"key": "value"}

def test_metadata_identity():
    meta = get_metadata()
    assert meta["metadata"] is metadata
""")

        monkeypatch.chdir(tmp_path)
        passed, issues = mod.check_test_expectations()

        assert not passed
        assert any("'is' identity check" in issue for issue in issues)

    def test_missing_test_files(self, tmp_path, monkeypatch) -> None:
        """When test files don't exist, should pass."""
        mod = _import_validator()

        monkeypatch.chdir(tmp_path)
        passed, issues = mod.check_test_expectations()

        assert passed


class TestMainFunction:
    """Tests for the main() function."""

    def test_main_all_pass(self, tmp_path, monkeypatch) -> None:
        """When all checks pass, main should return 0."""
        mod = _import_validator()

        # Create valid pyproject.toml
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[project.optional-dependencies]
test = ["pytest>=7.0"]
""")

        # Create valid dependabot workflow
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)
        workflow = workflows_dir / "dependabot-auto-lock.yml"
        workflow.write_text("""
name: dependabot-auto-lock
on:
  schedule:
    - cron: '0 0 * * *'
jobs:
  lock:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install --extra test
""")

        monkeypatch.chdir(tmp_path)
        result = mod.main()

        assert result == 0

    def test_main_some_fail(self, tmp_path, monkeypatch) -> None:
        """When some checks fail, main should return 1."""
        mod = _import_validator()

        # Create invalid pyproject.toml (no optional-dependencies)
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"\n')

        monkeypatch.chdir(tmp_path)
        result = mod.main()

        assert result == 1
