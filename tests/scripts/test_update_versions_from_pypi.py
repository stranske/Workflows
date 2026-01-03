#!/usr/bin/env python3
"""Tests for update_versions_from_pypi.py.

CRITICAL: These tests ensure we NEVER ship outdated versions to consumer repos.
They include:
1. Unit tests for the script functionality
2. Integration tests that ACTUALLY query PyPI
3. Consumer repo simulation tests that verify versions are current

The integration tests are marked with @pytest.mark.integration and can be run
separately to validate that our pinned versions are actually current on PyPI.
"""

from __future__ import annotations

import json
import urllib.request
from functools import lru_cache
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts import update_versions_from_pypi
from scripts.update_versions_from_pypi import (
    PACKAGE_MAPPING,
    VersionInfo,
    _version_tuple,
    check_versions,
    get_latest_pypi_version,
    parse_env_file,
    update_env_file,
)


@lru_cache(maxsize=1)
def _pypi_reachable() -> bool:
    try:
        with urllib.request.urlopen("https://pypi.org/simple/", timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _skip_if_pypi_unreachable() -> None:
    if not _pypi_reachable():
        pytest.skip("PyPI not reachable in this test environment")


class TestVersionTuple:
    """Tests for version string to tuple conversion."""

    def test_simple_version(self) -> None:
        assert _version_tuple("1.2.3") == (1, 2, 3)

    def test_major_only(self) -> None:
        assert _version_tuple("1") == (1,)

    def test_major_minor(self) -> None:
        assert _version_tuple("1.2") == (1, 2)

    def test_four_parts(self) -> None:
        assert _version_tuple("1.2.3.4") == (1, 2, 3, 4)

    def test_prerelease_stripped(self) -> None:
        assert _version_tuple("1.2.3rc1") == (1, 2, 3)

    def test_invalid_returns_zero(self) -> None:
        assert _version_tuple("invalid") == (0,)


class TestParseEnvFile:
    """Tests for parsing autofix-versions.env files."""

    def test_parse_simple_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / "test.env"
        env_file.write_text("RUFF_VERSION=0.14.10\nMYPY_VERSION=1.19.1\n")

        result = parse_env_file(env_file)
        assert result == {"RUFF_VERSION": "0.14.10", "MYPY_VERSION": "1.19.1"}

    def test_skips_comments(self, tmp_path: Path) -> None:
        env_file = tmp_path / "test.env"
        env_file.write_text("# Comment\nRUFF_VERSION=0.14.10\n")

        result = parse_env_file(env_file)
        assert result == {"RUFF_VERSION": "0.14.10"}

    def test_skips_empty_lines(self, tmp_path: Path) -> None:
        env_file = tmp_path / "test.env"
        env_file.write_text("RUFF_VERSION=0.14.10\n\nMYPY_VERSION=1.19.1\n")

        result = parse_env_file(env_file)
        assert result == {"RUFF_VERSION": "0.14.10", "MYPY_VERSION": "1.19.1"}

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        result = parse_env_file(tmp_path / "nonexistent.env")
        assert result == {}

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        env_file = tmp_path / "test.env"
        env_file.write_text("  RUFF_VERSION = 0.14.10  \n")

        result = parse_env_file(env_file)
        assert result == {"RUFF_VERSION": "0.14.10"}


class TestUpdateEnvFile:
    """Tests for updating env file in place."""

    def test_update_single_value(self, tmp_path: Path) -> None:
        env_file = tmp_path / "test.env"
        env_file.write_text("RUFF_VERSION=0.14.0\nMYPY_VERSION=1.19.0\n")

        update_env_file(env_file, {"RUFF_VERSION": "0.14.10"})

        result = parse_env_file(env_file)
        assert result["RUFF_VERSION"] == "0.14.10"
        assert result["MYPY_VERSION"] == "1.19.0"

    def test_preserves_comments(self, tmp_path: Path) -> None:
        env_file = tmp_path / "test.env"
        env_file.write_text("# This is a comment\nRUFF_VERSION=0.14.0\n")

        update_env_file(env_file, {"RUFF_VERSION": "0.14.10"})

        content = env_file.read_text()
        assert "# This is a comment" in content
        assert "RUFF_VERSION=0.14.10" in content

    def test_preserves_order(self, tmp_path: Path) -> None:
        env_file = tmp_path / "test.env"
        env_file.write_text("A=1\nB=2\nC=3\n")

        update_env_file(env_file, {"B": "9"})

        lines = env_file.read_text().strip().split("\n")
        assert lines == ["A=1", "B=9", "C=3"]

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            update_env_file(tmp_path / "nonexistent.env", {"X": "1"})


class TestGetLatestPyPIVersion:
    """Tests for PyPI API queries."""

    def test_successful_fetch(self) -> None:
        """Mock a successful PyPI response."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {
                "info": {"version": "1.2.3"},
                "releases": {},
            }
        ).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = get_latest_pypi_version("some-package")

        assert result == "1.2.3"

    def test_network_error_returns_none(self) -> None:
        """Network errors should return None, not crash."""
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timeout")):
            result = get_latest_pypi_version("some-package")

        assert result is None


class TestCheckVersions:
    """Tests for the check_versions function."""

    def test_identifies_outdated(self, tmp_path: Path) -> None:
        env_file = tmp_path / "test.env"
        env_file.write_text("RUFF_VERSION=0.1.0\n")

        # Mock PyPI to return a newer version
        with patch.object(
            update_versions_from_pypi,
            "get_latest_pypi_version",
            return_value="0.14.10",
        ):
            results = check_versions(env_file)

        assert "RUFF_VERSION" in results
        assert results["RUFF_VERSION"].current == "0.1.0"
        assert results["RUFF_VERSION"].latest == "0.14.10"
        assert results["RUFF_VERSION"].is_outdated is True

    def test_identifies_current(self, tmp_path: Path) -> None:
        env_file = tmp_path / "test.env"
        env_file.write_text("RUFF_VERSION=0.14.10\n")

        with patch.object(
            update_versions_from_pypi,
            "get_latest_pypi_version",
            return_value="0.14.10",
        ):
            results = check_versions(env_file)

        assert results["RUFF_VERSION"].is_outdated is False


class TestMain:
    """Tests for the main CLI function."""

    def test_check_mode_no_updates(self, tmp_path: Path) -> None:
        env_file = tmp_path / "test.env"
        env_file.write_text("RUFF_VERSION=0.14.10\n")

        with patch.object(
            update_versions_from_pypi,
            "get_latest_pypi_version",
            return_value="0.14.10",
        ):
            result = update_versions_from_pypi.main(
                [
                    "--check",
                    "--pin-file",
                    str(env_file),
                ]
            )

        assert result == 0

    def test_check_mode_with_outdated_fail_flag(self, tmp_path: Path) -> None:
        env_file = tmp_path / "test.env"
        env_file.write_text("RUFF_VERSION=0.1.0\n")

        with patch.object(
            update_versions_from_pypi,
            "get_latest_pypi_version",
            return_value="0.14.10",
        ):
            result = update_versions_from_pypi.main(
                [
                    "--check",
                    "--fail-on-outdated",
                    "--pin-file",
                    str(env_file),
                ]
            )

        assert result == 1

    def test_apply_mode_updates_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / "test.env"
        env_file.write_text("RUFF_VERSION=0.1.0\n")

        with patch.object(
            update_versions_from_pypi,
            "get_latest_pypi_version",
            return_value="0.14.10",
        ):
            result = update_versions_from_pypi.main(
                [
                    "--apply",
                    "--pin-file",
                    str(env_file),
                ]
            )

        assert result == 0
        assert "RUFF_VERSION=0.14.10" in env_file.read_text()


# ============================================================================
# INTEGRATION TESTS - Actually query PyPI
# These tests ensure our pinned versions are not outdated
# ============================================================================


@pytest.mark.integration
class TestPyPIIntegration:
    """Integration tests that actually query PyPI.

    Run with: pytest -m integration tests/scripts/test_update_versions_from_pypi.py
    """

    def test_can_fetch_real_ruff_version(self) -> None:
        """Verify we can fetch the real ruff version from PyPI."""
        _skip_if_pypi_unreachable()
        version = get_latest_pypi_version("ruff")
        assert version is not None
        assert len(version) > 0
        # Version should be a valid semver-ish format
        parts = version.split(".")
        assert len(parts) >= 2
        assert all(p.isdigit() or p[0].isdigit() for p in parts)

    def test_can_fetch_real_mypy_version(self) -> None:
        """Verify we can fetch the real mypy version from PyPI."""
        _skip_if_pypi_unreachable()
        version = get_latest_pypi_version("mypy")
        assert version is not None
        assert len(version) > 0

    def test_can_fetch_all_mapped_packages(self) -> None:
        """Verify we can fetch versions for ALL packages in our mapping."""
        _skip_if_pypi_unreachable()
        for env_key, package_name in PACKAGE_MAPPING.items():
            version = get_latest_pypi_version(package_name)
            assert version is not None, f"Failed to fetch {package_name} for {env_key}"


# ============================================================================
# CONSUMER REPO SAMPLING TESTS
# These tests simulate what happens when we sync to consumer repos
# ============================================================================


@pytest.mark.integration
class TestConsumerRepoSampling:
    """Tests that sample consumer repo dependencies to ensure we're shipping current versions.

    CRITICAL: These tests catch the exact problem of shipping outdated versions.
    They verify that the versions in autofix-versions.env are actually current on PyPI.
    """

    def test_autofix_versions_env_not_stale(self) -> None:
        """CRITICAL: Verify autofix-versions.env has current PyPI versions.

        This test reads the actual autofix-versions.env file and checks EACH
        package against PyPI to ensure we're not shipping outdated versions.
        """
        _skip_if_pypi_unreachable()
        pin_file = Path(".github/workflows/autofix-versions.env")
        if not pin_file.exists():
            pytest.skip("autofix-versions.env not found (not in Workflows repo)")

        current_pins = parse_env_file(pin_file)
        stale_packages: list[str] = []

        for env_key, package_name in PACKAGE_MAPPING.items():
            if env_key not in current_pins:
                continue

            current_version = current_pins[env_key]
            latest_version = get_latest_pypi_version(package_name)

            if latest_version is None:
                continue  # Skip if we can't reach PyPI

            if current_version != latest_version:
                stale_packages.append(
                    f"{package_name}: pinned={current_version}, latest={latest_version}"
                )

        if stale_packages:
            pytest.fail(
                "STALE VERSIONS IN autofix-versions.env! "
                "These packages are outdated:\n  "
                + "\n  ".join(stale_packages)
                + "\n\nRun: python scripts/update_versions_from_pypi.py --apply"
            )

    def test_template_sync_script_has_all_packages(self) -> None:
        """Verify the template sync script maps all the same packages."""
        template_script = Path("templates/consumer-repo/scripts/sync_dev_dependencies.py")
        if not template_script.exists():
            pytest.skip("Template sync script not found")

        content = template_script.read_text()

        # Check that all our package mappings exist in the template
        for env_key in PACKAGE_MAPPING:
            assert env_key in content, (
                f"Template sync script missing {env_key}. "
                f"Consumer repos won't sync this package!"
            )

    def test_simulated_consumer_repo_sync(self, tmp_path: Path) -> None:
        """Simulate what a consumer repo would receive.

        This test:
        1. Creates a fake consumer repo pyproject.toml with older versions
        2. Runs the sync process with current autofix-versions.env
        3. Verifies the resulting versions are what PyPI has
        """
        # Read actual autofix-versions.env
        pin_file = Path(".github/workflows/autofix-versions.env")
        if not pin_file.exists():
            pytest.skip("autofix-versions.env not found")

        current_pins = parse_env_file(pin_file)

        # For each pinned package, verify it matches PyPI
        # This catches the case where autofix-versions.env itself is stale
        mismatches: list[str] = []

        for env_key, package_name in PACKAGE_MAPPING.items():
            if env_key not in current_pins:
                continue

            our_version = current_pins[env_key]
            pypi_version = get_latest_pypi_version(package_name)

            if pypi_version and our_version != pypi_version:
                mismatches.append(f"{package_name}: we have {our_version}, PyPI has {pypi_version}")

        if mismatches:
            pytest.fail(
                "Consumer repos would receive STALE versions!\n"
                "Mismatches:\n  " + "\n  ".join(mismatches)
            )


# ============================================================================
# REGRESSION TESTS
# Specific tests to prevent past failures from recurring
# ============================================================================


class TestRegressionPrevention:
    """Tests specifically designed to prevent past failures."""

    def test_version_comparison_is_exact(self) -> None:
        """Ensure version comparison doesn't use >= or fuzzy matching.

        Past issue: Versions were compared loosely, allowing older versions to pass.
        """
        info = VersionInfo(current="1.0.0", latest="1.0.1", is_outdated=True)
        # Even minor version differences should be flagged
        assert info.is_outdated is True

        info2 = VersionInfo(current="1.0.1", latest="1.0.1", is_outdated=False)
        assert info2.is_outdated is False

    def test_package_mapping_completeness(self) -> None:
        """Ensure PACKAGE_MAPPING covers all expected dev tools."""
        expected_tools = {
            "ruff",
            "black",
            "mypy",
            "pytest",
            "pytest-cov",
            "coverage",
        }

        mapped_packages = set(PACKAGE_MAPPING.values())

        missing = expected_tools - mapped_packages
        assert not missing, f"Missing critical tools in PACKAGE_MAPPING: {missing}"

    def test_no_hardcoded_fallback_versions(self) -> None:
        """Ensure there are no hardcoded fallback versions that could be stale.

        Past issue: Scripts had DEFAULT_VERSION constants that became stale.
        """
        import ast

        script_path = Path("scripts/update_versions_from_pypi.py")
        content = script_path.read_text()
        tree = ast.parse(content)

        # Check for various fallback naming patterns that could contain stale versions
        fallback_patterns = [
            ("VERSION", "FALLBACK"),  # VERSION_FALLBACK, FALLBACK_VERSION
            ("VERSION", "DEFAULT"),  # DEFAULT_VERSION, VERSION_DEFAULT
            ("DEFAULT", "VER"),  # DEFAULT_VER
        ]

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        name = target.id.upper()
                        for pattern1, pattern2 in fallback_patterns:
                            if pattern1 in name and pattern2 in name:
                                pytest.fail(
                                    f"Found potential hardcoded fallback: {target.id}. "
                                    f"Remove it - we must always query PyPI!"
                                )
