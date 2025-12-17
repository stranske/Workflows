from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

import scripts.auto_type_hygiene as auto_type_hygiene
import scripts.fix_cosmetic_aggregate as fix_cosmetic_aggregate
import scripts.fix_numpy_asserts as fix_numpy_asserts
import scripts.mypy_autofix as mypy_autofix
import scripts.mypy_return_autofix as mypy_return_autofix
import scripts.update_autofix_expectations as update_autofix_expectations


def _run(
    cmd: list[str],
    cwd: Path,
    *,
    ok_exit_codes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode not in ok_exit_codes:
        raise AssertionError(
            "Command failed: {cmd}\nReturn code: {code}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}".format(
                cmd=" ".join(cmd),
                code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        )
    return result


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
    (sample_pkg / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")

    sample_module = sample_pkg / "diagnostic_module.py"
    sample_module.write_text(
        dedent(
            '''
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
            '''
        ).lstrip(),
        encoding="utf-8",
    )

    automation_module = trend_pkg / "automation_multifailure.py"
    automation_module.write_text(
        dedent(
            """
            from typing import Iterable


            def aggregate_numbers(values: Iterable[int]) -> str:
                return ",".join(str(v) for v in values)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    numpy_test = tests_dir / "test_pipeline_warmup_autofix.py"
    numpy_test.write_text(
        dedent(
            """
            import numpy as np


            def test_numpy_array_equality():
                array_payload = np.array([1, 2, 3])
                assert array_payload == [1, 2, 3]
            """
        ).lstrip(),
        encoding="utf-8",
    )

    expectations_module = tests_dir / "test_expectations_mod.py"
    expectations_module.write_text(
        dedent(
            """
            EXPECTED_REPORT_COUNT = 0


            def compute_expected_report_count() -> int:
                return 7
            """
        ).lstrip(),
        encoding="utf-8",
    )

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
        ([sys.executable, "-m", "black", str(repo_root)], (0,)),
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
    _run([sys.executable, "-m", "black", str(repo_root)], cwd=repo_root)
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
    _run([sys.executable, "-m", "black", "--check", str(repo_root)], cwd=repo_root)
    _run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--ignore-missing-imports",
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
