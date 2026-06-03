from __future__ import annotations

from pathlib import Path

import pytest
from scripts import sync_test_dependencies as std


@pytest.mark.parametrize(
    "entry, expected",
    [
        ("requests>=2.0", "requests"),
        ("requests[security]>=2.0", "requests"),
        ("PyYAML; python_version>'3.8'", "PyYAML"),
        ("  numpy~=1.26  ", "numpy"),
        ("", None),
        (" , ", None),
    ],
)
def test_extract_requirement_name(entry: str, expected: str | None) -> None:
    assert std._extract_requirement_name(entry) == expected


def test_detect_local_project_modules_finds_packages_and_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "tool.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "src" / "pkg").mkdir()
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "rootpkg").mkdir()
    (tmp_path / "rootpkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "root_module.py").write_text("value = 2\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    detected = std._detect_local_project_modules()

    assert "tool" in detected
    assert "pkg" in detected
    assert "rootpkg" in detected
    assert "root_module" in detected


def test_detect_local_project_modules_finds_top_level_test_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "conftest.py").write_text("FIXTURE = object()\n", encoding="utf-8")
    (tests_dir / "helpers.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tests_dir / "test_helpers.py").write_text("import pandas\n", encoding="utf-8")
    (tests_dir / "support").mkdir()
    (tests_dir / "support" / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "baseline").mkdir()
    (tests_dir / "baseline" / "adapter.py").write_text("VALUE = 2\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    detected = std._detect_local_project_modules()

    assert {"conftest", "helpers", "support"}.issubset(detected)
    assert "test_helpers" not in detected
    assert "adapter" not in detected


def test_detect_local_project_modules_handles_packaged_tests_without_pythonpath(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "conftest.py").write_text("FIXTURE = object()\n", encoding="utf-8")
    (tests_dir / "helpers.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tests_dir / "api").mkdir()
    (tests_dir / "api" / "__init__.py").write_text("", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    detected = std._detect_local_project_modules()

    assert "conftest" in detected
    assert "api" not in detected
    assert "helpers" not in detected


def test_detect_local_project_modules_keeps_packaged_test_helpers_on_pythonpath(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "\n".join(
            [
                "[tool.pytest.ini_options]",
                'pythonpath = ["tests"]',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "conftest.py").write_text("FIXTURE = object()\n", encoding="utf-8")
    (tests_dir / "helpers.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tests_dir / "api").mkdir()
    (tests_dir / "api" / "__init__.py").write_text("", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(std, "PYPROJECT_FILE", pyproject)

    detected = std._detect_local_project_modules()

    assert {"api", "conftest", "helpers"}.issubset(detected)


@pytest.mark.parametrize(
    "config_name, section",
    [
        ("pytest.ini", "[pytest]"),
        (".pytest.ini", "[pytest]"),
        ("tox.ini", "[pytest]"),
        ("setup.cfg", "[tool:pytest]"),
        ("setup.cfg", "[pytest]"),
    ],
)
def test_detect_local_project_modules_reads_ini_pythonpath_for_packaged_tests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config_name: str, section: str
) -> None:
    (tmp_path / config_name).write_text(
        "\n".join(
            [
                section,
                "pythonpath =",
                "    src",
                "    tests",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "helpers.py").write_text("VALUE = 1\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(std, "PYPROJECT_FILE", tmp_path / "pyproject.toml")

    detected = std._detect_local_project_modules()

    assert "helpers" in detected


@pytest.mark.parametrize("config_name", ["pytest.toml", ".pytest.toml"])
def test_detect_local_project_modules_reads_pytest_toml_pythonpath_for_packaged_tests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config_name: str
) -> None:
    (tmp_path / config_name).write_text(
        "\n".join(
            [
                "[pytest]",
                'pythonpath = ["src", "tests"]',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "helpers.py").write_text("VALUE = 1\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(std, "PYPROJECT_FILE", tmp_path / "pyproject.toml")

    detected = std._detect_local_project_modules()

    assert "helpers" in detected


def test_detect_local_project_modules_reads_native_pyproject_pythonpath_for_packaged_tests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "\n".join(
            [
                "[tool.pytest]",
                'pythonpath = ["tests"]',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "helpers.py").write_text("VALUE = 1\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(std, "PYPROJECT_FILE", pyproject)

    detected = std._detect_local_project_modules()

    assert "helpers" in detected


def test_tests_dir_on_pythonpath_uses_first_existing_pytest_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = -q\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[tool.pytest.ini_options]",
                'pythonpath = ["tests"]',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(std, "PYPROJECT_FILE", tmp_path / "pyproject.toml")

    assert std._tests_dir_on_pythonpath() is False


def test_tests_dir_on_pythonpath_uses_pyproject_before_tox_ini(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[tool.pytest.ini_options]\naddopts = '-q'\n", encoding="utf-8")
    (tmp_path / "tox.ini").write_text(
        "\n".join(
            [
                "[pytest]",
                "pythonpath = tests",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(std, "PYPROJECT_FILE", pyproject)

    assert std._tests_dir_on_pythonpath() is False


@pytest.mark.parametrize(
    "pyproject_contents",
    [
        '[tool]\npytest = "not-a-table"\n',
        '[tool.pytest]\nini_options = "not-a-table"\n',
    ],
)
def test_tests_dir_on_pythonpath_ignores_non_table_pyproject_shapes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pyproject_contents: str
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(pyproject_contents, encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(std, "PYPROJECT_FILE", pyproject)

    assert std._tests_dir_on_pythonpath() is False


def test_detect_local_project_modules_skips_pythonpath_read_for_unpackaged_tests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "helpers.py").write_text("VALUE = 1\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(std, "_tests_dir_on_pythonpath", lambda: pytest.fail("unexpected read"))

    detected = std._detect_local_project_modules()

    assert "helpers" in detected


def test_extract_imports_from_file_parses_top_level_imports(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "\n".join(
            [
                "import os",
                "import requests as req",
                "from yaml import safe_load",
                "from pkg.sub import thing",
                "from . import local",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    imports = std.extract_imports_from_file(sample)

    assert imports == {"os", "requests", "yaml", "pkg"}


def test_extract_imports_from_file_ignores_relative_import_modules(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "\n".join(
            [
                "from .adapter import Adapter",
                "from ..conftest import fixture",
                "from requests import Session",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    imports = std.extract_imports_from_file(sample)

    assert imports == {"requests"}


def test_extract_imports_from_file_handles_parse_errors(tmp_path: Path) -> None:
    sample = tmp_path / "broken.py"
    sample.write_text("def nope(\n", encoding="utf-8")

    assert std.extract_imports_from_file(sample) == set()


def test_get_all_test_imports_returns_empty_without_tests_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert std.get_all_test_imports() == set()


def test_get_all_test_imports_scans_tests_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_one.py").write_text("import os\nimport requests\n", encoding="utf-8")
    (tests_dir / "test_two.py").write_text("from yaml import safe_load\n", encoding="utf-8")
    (tests_dir / "__pycache__").mkdir()
    (tests_dir / "__pycache__" / "ignored.py").write_text("import pandas\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    imports = std.get_all_test_imports()

    assert imports == {"os", "requests", "yaml"}


def test_get_declared_dependencies_skips_missing_pyproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(std, "PYPROJECT_FILE", tmp_path / "pyproject.toml")

    declared, groups = std.get_declared_dependencies()

    assert declared == set()
    assert groups == {}


def test_get_declared_dependencies_reads_pyproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "\n".join(
            [
                "[project]",
                "dependencies = [",
                '  "requests>=2.0",',
                '  "numpy==1.26; python_version>\\"3.9\\"",',
                "]",
                "",
                "[project.optional-dependencies]",
                "dev = [",
                '  "PyYAML",',
                '  "ruff>=0.1",',
                "]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(std, "PYPROJECT_FILE", pyproject)

    declared, groups = std.get_declared_dependencies()

    assert declared == {"requests", "numpy", "pyyaml", "ruff"}
    assert groups["dependencies"] == ["requests>=2.0", "numpy==1.26"]
    assert groups["dev"] == ["PyYAML", "ruff>=0.1"]


def test_get_declared_dependencies_skips_empty_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "\n".join(
            [
                "[project]",
                "dependencies = [",
                '  "",',
                '  "requests",',
                "]",
                "",
                "[project.optional-dependencies]",
                "dev = [",
                '  "",',
                '  "ruff",',
                "]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(std, "PYPROJECT_FILE", pyproject)

    declared, groups = std.get_declared_dependencies()

    assert declared == {"requests", "ruff"}
    assert groups["dependencies"] == ["requests"]
    assert groups["dev"] == ["", "ruff"]


def test_find_missing_dependencies_ignores_local_and_mapped_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "\n".join(
            [
                "[project.optional-dependencies]",
                "dev = [",
                '  "requests",',
                '  "PyYAML",',
                "]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sample.py").write_text(
        "\n".join(
            [
                "import json",
                "import requests",
                "import yaml",
                "import pandas",
                "import pytest",
                "import localpkg",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "localpkg").mkdir()
    (tmp_path / "src" / "localpkg" / "__init__.py").write_text("", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(std, "PYPROJECT_FILE", pyproject)

    assert std.find_missing_dependencies() == {"pandas"}


def test_find_missing_dependencies_ignores_test_helper_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "\n".join(
            [
                "[project.optional-dependencies]",
                "dev = [",
                '  "requests",',
                "]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    helper_dir = tmp_path / "tests" / "baseline"
    helper_dir.mkdir(parents=True)
    (helper_dir / "adapter.py").write_text("value = 1\n", encoding="utf-8")
    (helper_dir / "conftest.py").write_text("fixture_value = 1\n", encoding="utf-8")
    (helper_dir / "test_adapter.py").write_text(
        "from .adapter import value\nfrom .conftest import fixture_value\nimport requests\nimport pandas\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(std, "PYPROJECT_FILE", pyproject)

    assert std.find_missing_dependencies() == {"pandas"}


def test_find_missing_dependencies_keeps_nested_helper_stems_available_for_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "\n".join(
            [
                "[project.optional-dependencies]",
                "dev = [",
                '  "requests",',
                "]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    helper_dir = tmp_path / "tests" / "baseline"
    helper_dir.mkdir(parents=True)
    (helper_dir / "adapter.py").write_text("value = 1\n", encoding="utf-8")
    (helper_dir / "test_adapter.py").write_text(
        "import adapter\nimport requests\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(std, "PYPROJECT_FILE", pyproject)

    assert std.find_missing_dependencies() == {"adapter"}


def test_find_missing_dependencies_ignores_packaged_top_level_test_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "\n".join(
            [
                "[tool.pytest.ini_options]",
                'pythonpath = ["tests"]',
                "",
                "[project.optional-dependencies]",
                "dev = [",
                '  "requests",',
                "]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "expected_cli_outputs.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tests_dir / "test_cli.py").write_text(
        "from expected_cli_outputs import VALUE\nimport requests\nimport pandas\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(std, "PYPROJECT_FILE", pyproject)

    assert std.find_missing_dependencies() == {"pandas"}


def test_find_missing_dependencies_ignores_reviewed_stdlib_and_maps_jwt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "\n".join(
            [
                "[project.optional-dependencies]",
                "dev = [",
                '  "PyJWT[crypto]",',
                "]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_reviewed_imports.py").write_text(
        "\n".join(
            [
                "import fnmatch",
                "import html",
                "from http.server import BaseHTTPRequestHandler",
                "import secrets",
                "import jwt",
                "import pandas",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(std, "PYPROJECT_FILE", pyproject)

    assert std.find_missing_dependencies() == {"pandas"}


def test_detect_local_project_modules_skips_missing_source_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    detected = std._detect_local_project_modules()

    assert detected == set()


def test_add_dependencies_to_pyproject_returns_false_without_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project]\n", encoding="utf-8")

    monkeypatch.setattr(std, "PYPROJECT_FILE", pyproject)

    assert std.add_dependencies_to_pyproject({"pandas"}, fix=False) is False


def test_add_dependencies_to_pyproject_requires_tomlkit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project]\n", encoding="utf-8")

    monkeypatch.setattr(std, "PYPROJECT_FILE", pyproject)
    monkeypatch.setattr(std, "TOMLKIT_ERROR", ImportError("boom"))

    with pytest.raises(SystemExit, match="tomlkit is required"):
        std.add_dependencies_to_pyproject({"pandas"}, fix=True)


def test_add_dependencies_to_pyproject_creates_dev_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("tomlkit")  # Skip if tomlkit not installed

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project]\n", encoding="utf-8")

    monkeypatch.setattr(std, "PYPROJECT_FILE", pyproject)

    assert std.add_dependencies_to_pyproject({"pandas"}, fix=True) is True

    contents = pyproject.read_text(encoding="utf-8")
    assert "[project.optional-dependencies]" in contents
    assert "pandas" in contents


def test_add_dependencies_to_pyproject_no_new_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("tomlkit")  # Skip if tomlkit not installed

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "\n".join(
            [
                "[project.optional-dependencies]",
                "dev = [",
                '  "requests",',
                "]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(std, "PYPROJECT_FILE", pyproject)

    assert std.add_dependencies_to_pyproject({"requests"}, fix=True) is False


def test_add_dependencies_to_pyproject_appends_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("tomlkit")  # Skip if tomlkit not installed

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "\n".join(
            [
                "[project.optional-dependencies]",
                "dev = [",
                '  "requests",',
                "]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(std, "PYPROJECT_FILE", pyproject)

    assert std.add_dependencies_to_pyproject({"requests", "pandas"}, fix=True) is True

    contents = pyproject.read_text(encoding="utf-8")
    assert "requests" in contents
    assert "pandas" in contents


def test_main_reports_no_missing_dependencies(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(std, "find_missing_dependencies", lambda: set())

    assert std.main([]) == 0

    output = capsys.readouterr().out
    assert "All test dependencies" in output


def test_main_verify_mode_exits_nonzero(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(std, "find_missing_dependencies", lambda: {"pandas"})

    assert std.main(["--verify"]) == 1

    output = capsys.readouterr().out
    assert "Run: python scripts/sync_test_dependencies.py --fix" in output


def test_main_handles_missing_without_flags(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(std, "find_missing_dependencies", lambda: {"pandas"})

    assert std.main([]) == 0

    output = capsys.readouterr().out
    assert "To fix, run: python scripts/sync_test_dependencies.py --fix" in output


def test_main_fix_mode_adds_dependencies(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(std, "find_missing_dependencies", lambda: {"pandas"})
    monkeypatch.setattr(std, "add_dependencies_to_pyproject", lambda missing, fix: True)

    assert std.main(["--fix"]) == 0

    output = capsys.readouterr().out
    assert "Added dependencies" in output


def test_main_fix_mode_reports_already_declared(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(std, "find_missing_dependencies", lambda: {"pandas"})
    monkeypatch.setattr(std, "add_dependencies_to_pyproject", lambda missing, fix: False)

    assert std.main(["--fix"]) == 0

    output = capsys.readouterr().out
    assert "Dependencies already declared in dev extra" in output


def test_read_local_modules_returns_empty_without_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test _read_local_modules returns empty set when file doesn't exist."""
    monkeypatch.setattr(std, "LOCAL_MODULES_FILE", tmp_path / ".project_modules.txt")

    assert std._read_local_modules() == set()


def test_read_local_modules_reads_valid_module_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test _read_local_modules parses valid module names."""
    modules_file = tmp_path / ".project_modules.txt"
    modules_file.write_text("diff_holdings\nembeddings\n", encoding="utf-8")
    monkeypatch.setattr(std, "LOCAL_MODULES_FILE", modules_file)

    result = std._read_local_modules()

    assert result == {"diff_holdings", "embeddings"}


def test_read_local_modules_ignores_comments_and_empty_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test _read_local_modules skips comments and blank lines."""
    modules_file = tmp_path / ".project_modules.txt"
    modules_file.write_text(
        "# This is a comment\n\n  # Indented comment  \nmodule_a\n   \nmodule_b\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(std, "LOCAL_MODULES_FILE", modules_file)

    result = std._read_local_modules()

    assert result == {"module_a", "module_b"}


def test_read_local_modules_strips_whitespace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test _read_local_modules strips leading/trailing whitespace."""
    modules_file = tmp_path / ".project_modules.txt"
    modules_file.write_text("  spaced_module  \n\ttabbed_module\t\n", encoding="utf-8")
    monkeypatch.setattr(std, "LOCAL_MODULES_FILE", modules_file)

    result = std._read_local_modules()

    assert result == {"spaced_module", "tabbed_module"}


def test_read_local_modules_warns_on_invalid_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test _read_local_modules warns about invalid Python identifiers."""
    modules_file = tmp_path / ".project_modules.txt"
    modules_file.write_text(
        "valid_module\n123invalid\nhas-hyphen\nhas space\nanother_valid\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(std, "LOCAL_MODULES_FILE", modules_file)

    result = std._read_local_modules()

    assert result == {"valid_module", "another_valid"}
    stderr = capsys.readouterr().err
    assert "123invalid" in stderr
    assert "has-hyphen" in stderr
    assert "has space" in stderr


def test_read_local_modules_handles_read_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test _read_local_modules gracefully handles file read errors."""
    modules_file = tmp_path / ".project_modules.txt"
    # Create a directory with same name to cause read error
    modules_file.mkdir()
    monkeypatch.setattr(std, "LOCAL_MODULES_FILE", modules_file)

    result = std._read_local_modules()

    assert result == set()
    stderr = capsys.readouterr().err
    assert "Warning" in stderr or "could not read" in stderr


def test_get_project_modules_includes_local_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test get_project_modules includes modules from .project_modules.txt."""
    modules_file = tmp_path / ".project_modules.txt"
    modules_file.write_text("custom_module\n", encoding="utf-8")
    monkeypatch.setattr(std, "LOCAL_MODULES_FILE", modules_file)
    monkeypatch.chdir(tmp_path)

    result = std.get_project_modules()

    assert "custom_module" in result
