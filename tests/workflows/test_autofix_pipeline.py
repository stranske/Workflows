from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest
from scripts import (
    auto_type_hygiene,
    fix_cosmetic_aggregate,
    fix_numpy_asserts,
    mypy_autofix,
    mypy_return_autofix,
    update_autofix_expectations,
)
from scripts.auto_type_hygiene import process_file


def _run(
    cmd: list[str],
    cwd: Path,
    *,
    ok_exit_codes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode not in ok_exit_codes:
        raise AssertionError(
            f"Command failed: {' '.join(cmd)}\nReturn code: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


@pytest.mark.slow
@pytest.mark.integration
def test_autofix_pipeline_fixes_trivial_ruff_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("ruff")
    pytest.importorskip("isort")
    pytest.importorskip("docformatter")
    pytest.importorskip("black")

    # Ensure the type-hygiene helper treats ``yaml`` as untyped even if local
    # test stubs exist elsewhere in the repository.
    monkeypatch.setattr(auto_type_hygiene, "SRC_DIRS", [tmp_path], raising=False)

    sample = tmp_path / "bad_format.py"
    sample.write_text(
        'import os\nimport yaml\n\n\ndef add(a,b):\n    yaml.safe_load("[]")\n    return  a + b\n',
        encoding="utf-8",
    )

    fail = subprocess.run(
        [sys.executable, "-m", "ruff", "check", str(sample)],
        capture_output=True,
        text=True,
    )
    assert fail.returncode != 0, "Expected initial ruff check to fail"

    commands = [
        [sys.executable, "-m", "ruff", "check", "--fix", "--exit-zero", str(sample)],
        [sys.executable, "-m", "isort", str(sample)],
        [sys.executable, "-m", "docformatter", "-i", str(sample)],
        [sys.executable, "-m", "black", str(sample)],
        [sys.executable, "-m", "ruff", "check", "--fix", "--exit-zero", str(sample)],
    ]

    for cmd in commands:
        _run(cmd, cwd=tmp_path)

    changed, new_lines = process_file(sample)
    assert changed is False
    if changed:
        sample.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    final = subprocess.run(
        [sys.executable, "-m", "ruff", "check", str(sample)],
        capture_output=True,
        text=True,
    )
    assert final.returncode == 0, final.stderr

    content = sample.read_text(encoding="utf-8")
    assert "type: ignore" not in content
    assert "return a + b" in content


@pytest.mark.slow
@pytest.mark.integration
def test_autofix_pipeline_resolves_lint_and_typing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the full autofix toolchain on a synthetic module."""

    for module in ("ruff", "isort", "docformatter", "black", "mypy"):
        pytest.importorskip(module)

    src_dir = tmp_path / "src"
    tests_dir = tmp_path / "tests"
    src_dir.mkdir()
    tests_dir.mkdir()
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff.lint]\nselect = ["E4", "E7", "E9", "F"]\n',
        encoding="utf-8",
    )

    sample = src_dir / "autofix_target.py"
    sample.write_text(
        dedent('''
            import yaml
            import os


            def messy_function(a:int,b:int)->int:
                """Bad docstring spacing.   The docstring should be reformatted to follow conventions.
                Extra indentation should be removed."""
                if a>b:
                    return  yaml.safe_load("[]")
                return a +b


            def needs_optional(value: Optional[int])->int:
                if value is None:
                    return 0
                return value
            ''').lstrip() + "\n",
        encoding="utf-8",
    )

    # Ruff should detect the style issues before fixes are applied.
    initial_ruff = subprocess.run(
        [sys.executable, "-m", "ruff", "check", str(sample)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert initial_ruff.returncode != 0, "Expected initial ruff check to fail"

    # Mypy should report the missing Optional import prior to autofix.
    initial_mypy = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--ignore-missing-imports",
            "--disable-error-code=import-untyped",
            str(sample),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert initial_mypy.returncode != 0, "Expected mypy to fail before autofix"
    assert "Optional" in (initial_mypy.stderr + initial_mypy.stdout)

    commands: list[tuple[list[str], tuple[int, ...]]] = [
        (
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--fix",
                "--exit-zero",
                str(sample),
            ],
            (0,),
        ),
        ([sys.executable, "-m", "isort", str(sample)], (0,)),
        ([sys.executable, "-m", "docformatter", "-i", str(sample)], (0, 3)),
        ([sys.executable, "-m", "black", str(sample)], (0,)),
        (
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--fix",
                "--exit-zero",
                str(sample),
            ],
            (0,),
        ),
    ]
    for cmd, ok_codes in commands:
        _run(cmd, cwd=tmp_path, ok_exit_codes=ok_codes)

    # Auto-type hygiene should attach import-untyped ignore comments to yaml.
    monkeypatch.setattr(auto_type_hygiene, "ROOT", tmp_path, raising=False)
    monkeypatch.setattr(auto_type_hygiene, "SRC_DIRS", [src_dir], raising=False)
    monkeypatch.setattr(auto_type_hygiene, "DRY_RUN", False, raising=False)
    monkeypatch.setenv("AUTO_TYPE_ALLOWLIST", "yaml")
    monkeypatch.setattr(auto_type_hygiene, "ALLOWLIST", ["yaml"], raising=False)
    auto_type_hygiene.main()

    # Mypy autofix should inject missing typing imports and normalise code again.
    monkeypatch.setattr(mypy_autofix, "ROOT", tmp_path, raising=False)
    monkeypatch.setattr(
        mypy_autofix,
        "DEFAULT_TARGETS",
        [src_dir, tests_dir],
        raising=False,
    )
    exit_code = mypy_autofix.main(["--paths", str(sample)])
    assert exit_code == 0

    # The type-hygiene pass can add imports after the initial formatter pass.
    _run([sys.executable, "-m", "black", str(sample)], cwd=tmp_path)

    for cmd in (
        [sys.executable, "-m", "isort", str(sample)],
        [sys.executable, "-m", "black", str(sample)],
        [sys.executable, "-m", "ruff", "check", "--fix", "--exit-zero", str(sample)],
    ):
        _run(cmd, cwd=tmp_path)

    _run([sys.executable, "-m", "ruff", "check", str(sample)], cwd=tmp_path)
    _run([sys.executable, "-m", "black", "--check", str(sample)], cwd=tmp_path)
    _run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--ignore-missing-imports",
            "--disable-error-code=import-untyped",
            str(sample),
        ],
        cwd=tmp_path,
    )

    content = sample.read_text(encoding="utf-8")
    assert "from typing import Optional" in content
    assert "type: ignore" not in content
    assert "if a > b" in content
    assert "return a + b" in content
    assert '"""Bad docstring spacing.\n\n' in content


@pytest.mark.slow
@pytest.mark.integration
def test_autofix_pipeline_handles_diverse_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for module in ("ruff", "isort", "docformatter", "black", "mypy"):
        pytest.importorskip(module)

    repo_root = tmp_path / "workspace"
    src_dir = repo_root / "src"
    tests_dir = repo_root / "tests"
    sample_pkg = src_dir / "sample_pkg"
    trend_pkg = src_dir / "trend_analysis"
    sample_pkg.mkdir(parents=True)
    trend_pkg.mkdir(parents=True)
    tests_dir.mkdir()
    (repo_root / "pyproject.toml").write_text(
        '[tool.ruff.lint]\nselect = ["E4", "E7", "E9", "F"]\n',
        encoding="utf-8",
    )
    (sample_pkg / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")

    sample_module = sample_pkg / "diagnostic_module.py"
    sample_module.write_text(
        dedent('''
            import os
            import yaml  # type: ignore[arg-type]
            from collections import defaultdict


            def build_payload(items: Iterable[int], tag: Optional[str])->list[int]:
                """Docstring with inconsistent   spacing.
                  Additional commentary missing newline.
                """
                data_map = defaultdict(list)
                for index, value in enumerate(items):
                    data_map["numbers"].append(f"{value}-{index}")
                trailing_hint = os.environ.get("AUTOFIX_PIPELINE_VAR")  # noqa: F841
                parsed = yaml.safe_load("{}")
                if isinstance(parsed, list):
                    data_map["numbers"].extend(str(item) for item in parsed)
                if tag is None:
                    return ["fallback"]
                return data_map["numbers"]
            ''').lstrip(),
        encoding="utf-8",
    )

    automation_module = trend_pkg / "automation_multifailure.py"
    automation_module.write_text(
        dedent("""
            from typing import Iterable


            def aggregate_numbers(values: Iterable[int]) -> str:
                return ",".join(str(v) for v in values)
            """).lstrip(),
        encoding="utf-8",
    )

    numpy_test = tests_dir / "test_pipeline_warmup_autofix.py"
    numpy_test.write_text(
        dedent("""
            import numpy as np


            def test_numpy_array_equality():
                array_payload = np.array([1, 2, 3])
                assert array_payload == [1, 2, 3]
            """).lstrip(),
        encoding="utf-8",
    )

    expectations_module = tests_dir / "test_expectations_mod.py"
    expectations_module.write_text(
        dedent("""
            EXPECTED_REPORT_COUNT = 0


            def compute_expected_report_count() -> int:
                return 7
            """).lstrip(),
        encoding="utf-8",
    )

    black_targets = (sample_module, automation_module, numpy_test, expectations_module)

    commands = [
        (
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--fix",
                "--exit-zero",
                str(sample_module),
            ],
            (0,),
        ),
        ([sys.executable, "-m", "isort", str(sample_module)], (0,)),
        ([sys.executable, "-m", "docformatter", "-i", str(sample_module)], (0, 3)),
        (
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--fix",
                "--exit-zero",
                str(sample_module),
            ],
            (0,),
        ),
    ]

    for command, ok_codes in commands:
        _run(command, cwd=repo_root, ok_exit_codes=ok_codes)

    for target in black_targets:
        _run([sys.executable, "-m", "black", str(target)], cwd=repo_root)

    monkeypatch.setattr(auto_type_hygiene, "ROOT", repo_root, raising=False)
    monkeypatch.setattr(auto_type_hygiene, "SRC_DIRS", [src_dir, tests_dir], raising=False)
    monkeypatch.setattr(auto_type_hygiene, "DRY_RUN", False, raising=False)
    auto_type_hygiene.main()

    monkeypatch.setattr(fix_cosmetic_aggregate, "ROOT", repo_root, raising=False)
    monkeypatch.setattr(fix_cosmetic_aggregate, "TARGET", automation_module, raising=False)
    fix_cosmetic_aggregate.main()

    monkeypatch.setattr(fix_numpy_asserts, "ROOT", repo_root, raising=False)
    monkeypatch.setattr(fix_numpy_asserts, "TEST_ROOT", tests_dir, raising=False)
    monkeypatch.setattr(
        fix_numpy_asserts,
        "TARGET_FILES",
        {Path("tests/test_pipeline_warmup_autofix.py")},
        raising=False,
    )
    fix_numpy_asserts.main()

    monkeypatch.syspath_prepend(str(repo_root))
    tests_pkg = importlib.import_module("tests")
    existing_path = list(getattr(tests_pkg, "__path__", []))
    monkeypatch.setattr(
        tests_pkg,
        "__path__",
        [str(tests_dir), *existing_path],
        raising=False,
    )
    monkeypatch.setattr(update_autofix_expectations, "ROOT", repo_root, raising=False)
    expectation_target = update_autofix_expectations.AutofixTarget(
        module="tests.test_expectations_mod",
        callable_name="compute_expected_report_count",
        constant_name="EXPECTED_REPORT_COUNT",
    )
    monkeypatch.setattr(
        update_autofix_expectations, "TARGETS", (expectation_target,), raising=False
    )
    try:
        update_autofix_expectations.main()
    finally:
        sys.modules.pop("tests.test_expectations_mod", None)

    monkeypatch.setattr(mypy_autofix, "ROOT", repo_root, raising=False)
    monkeypatch.setattr(mypy_autofix, "DEFAULT_TARGETS", [src_dir, tests_dir], raising=False)
    mypy_autofix.main(["--paths", str(sample_module)])

    sample_rel = sample_module.relative_to(repo_root)
    monkeypatch.setattr(mypy_return_autofix, "ROOT", repo_root, raising=False)
    monkeypatch.setattr(mypy_return_autofix, "PROJECT_DIRS", [src_dir, tests_dir], raising=False)
    monkeypatch.setattr(
        mypy_return_autofix,
        "MYPY_CMD",
        [
            sys.executable,
            "-m",
            "mypy",
            "--hide-error-context",
            "--no-error-summary",
            str(sample_rel),
        ],
        raising=False,
    )
    mypy_return_autofix.main()

    _run([sys.executable, "-m", "isort", str(sample_module)], cwd=repo_root)
    for target in black_targets:
        _run([sys.executable, "-m", "black", str(target)], cwd=repo_root)
    _run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--fix",
            "--exit-zero",
            str(sample_module),
        ],
        cwd=repo_root,
    )

    _run([sys.executable, "-m", "ruff", "check", str(repo_root)], cwd=repo_root)
    for target in black_targets:
        _run([sys.executable, "-m", "black", "--check", str(target)], cwd=repo_root)
    _run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--ignore-missing-imports",
            "--disable-error-code=import-untyped",
            str(sample_module),
        ],
        cwd=repo_root,
    )

    sample_text = sample_module.read_text(encoding="utf-8")
    assert "from typing import Iterable, Optional" in sample_text
    assert "# type: ignore[arg-type]" in sample_text
    assert "import-untyped" not in sample_text
    assert "-> list[str]:" in sample_text
    assert "Docstring with inconsistent" in sample_text
    assert "Additional commentary missing newline." in sample_text

    automation_text = automation_module.read_text(encoding="utf-8")
    assert '" | ".join(str(v) for v in values)' in automation_text

    numpy_text = numpy_test.read_text(encoding="utf-8")
    assert ".tolist() == [1, 2, 3]" in numpy_text

    expectations_text = expectations_module.read_text(encoding="utf-8")
    assert "EXPECTED_REPORT_COUNT = 7" in expectations_text
