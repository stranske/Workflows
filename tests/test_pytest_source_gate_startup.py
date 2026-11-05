"""The named Python source gate must collect tests when LangSmith is installed."""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_LANGSMITH_FILTER = "ignore:.*asyncio.iscoroutinefunction.*:DeprecationWarning"


def test_pytest_config_keeps_warnings_as_errors_except_langsmith_startup() -> None:
    project = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    filters = project["tool"]["pytest"]["ini_options"]["filterwarnings"]
    assert filters[0] == "error"
    assert _LANGSMITH_FILTER in filters


def test_unmodified_pytest_collects_with_repository_warning_filters() -> None:
    """Match the source-fix gate: no extra -o filters and plugin autoload left on."""
    env = os.environ.copy()
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTEST_DISABLE_PLUGIN_AUTOLOAD", None)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "tests/test_dependency_version_alignment.py",
            "-p",
            "no:cacheprovider",
        ],
        cwd=_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "asyncio.iscoroutinefunction" not in completed.stderr
    assert "test_reported_wasm_install_aligns_to_development_pytest_pin" in completed.stdout
