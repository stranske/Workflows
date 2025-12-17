from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path

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
def test_autofix_pipeline_repairs_live_documents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for module in ("ruff", "isort", "black", "mypy"):
        pytest.importorskip(module)

    repo_root = tmp_path / "workspace"
    src_dir = repo_root / "src"
    tests_dir = repo_root / "tests"
    repo_root.mkdir()
    src_dir.mkdir()
    tests_dir.mkdir()

    real_root = Path(__file__).resolve().parents[2]

    trend_analysis_src = real_root / "src" / "trend_analysis"
    shutil.copytree(trend_analysis_src, src_dir / "trend_analysis")

    yaml_stub_src = real_root / "src" / "yaml"
    if yaml_stub_src.exists():
        shutil.copytree(yaml_stub_src, src_dir / "yaml")

    expectation_module_src = real_root / "tests" / "workflows" / "test_autofix_repo_regressions.py"
    expectation_module_target = tests_dir / "test_autofix_repo_regressions.py"
    shutil.copy2(expectation_module_src, expectation_module_target)

    shutil.copy2(real_root / "tests" / "__init__.py", tests_dir / "__init__.py")
    pyproject_target = repo_root / "pyproject.toml"
    shutil.copy2(real_root / "pyproject.toml", pyproject_target)
    pyproject_text = pyproject_target.read_text(encoding="utf-8")
    pyproject_text = pyproject_text.replace(
        '[[tool.mypy.overrides]]\nmodule = "tests.*"\nignore_errors = true\n\n',
        "",
    )
    pyproject_target.write_text(pyproject_text, encoding="utf-8")

    fixtures_target_dir = tests_dir / "fixtures"
    fixtures_target_dir.mkdir()
    shutil.copy2(
        real_root / "tests" / "fixtures" / "score_frame_2025-06-30.csv",
        fixtures_target_dir / "score_frame_2025-06-30.csv",
    )

    automation_path = src_dir / "trend_analysis" / "automation_multifailure.py"
    automation_original = automation_path.read_text(encoding="utf-8")
    automation_path.write_text(
        automation_original.replace('" | ".join', '",".join'),
        encoding="utf-8",
    )

    expectation_original = expectation_module_target.read_text(encoding="utf-8")
    modified_lines: list[str] = []
    optional_removed = False
    numpy_rewritten = False
    yaml_stripped = False
    for line in expectation_original.splitlines():
        if not optional_removed and line.startswith("from typing import Optional"):
            optional_removed = True
            continue
        if not yaml_stripped and line.startswith("import yaml"):
            modified_lines.append("import yaml")
            yaml_stripped = True
            continue
        if line.startswith("EXPECTED_AUTOFIX_SELECTED_FUNDS"):
            modified_lines.append("EXPECTED_AUTOFIX_SELECTED_FUNDS = 0")
            continue
        if not numpy_rewritten and "fancy_array" in line and "tolist" in line:
            modified_lines.append(line.replace("fancy_array.tolist()", "fancy_array"))
            numpy_rewritten = True
            continue
        modified_lines.append(line)
    expectation_module_target.write_text("\n".join(modified_lines) + "\n", encoding="utf-8")

    return_probe = src_dir / "trend_analysis" / "return_type_probe.py"
    return_probe.write_text(
        """
from __future__ import annotations

from typing import Iterable


def summarise_payload(values: Iterable[int]) -> int:
    pieces = " / ".join(str(value) for value in values)
    return pieces
""".lstrip(),
        encoding="utf-8",
    )

    monkeypatch.syspath_prepend(str(repo_root))
    monkeypatch.syspath_prepend(str(src_dir))
    monkeypatch.syspath_prepend(str(tests_dir))
    importlib.invalidate_caches()
    for name in list(sys.modules):
        if name == "tests" or name.startswith("tests."):
            sys.modules.pop(name, None)

    for module in (
        auto_type_hygiene,
        fix_cosmetic_aggregate,
        fix_numpy_asserts,
        mypy_autofix,
        mypy_return_autofix,
        update_autofix_expectations,
    ):
        importlib.reload(module)

    monkeypatch.setattr(auto_type_hygiene, "ROOT", repo_root, raising=False)
    monkeypatch.setattr(auto_type_hygiene, "SRC_DIRS", [src_dir, tests_dir], raising=False)
    monkeypatch.setattr(auto_type_hygiene, "DRY_RUN", False, raising=False)

    monkeypatch.setattr(fix_cosmetic_aggregate, "ROOT", repo_root, raising=False)
    monkeypatch.setattr(fix_cosmetic_aggregate, "TARGET", automation_path, raising=False)

    monkeypatch.setattr(fix_numpy_asserts, "ROOT", repo_root, raising=False)
    monkeypatch.setattr(fix_numpy_asserts, "TEST_ROOT", tests_dir, raising=False)
    monkeypatch.setattr(
        fix_numpy_asserts,
        "TARGET_FILES",
        {Path("tests/test_autofix_repo_regressions.py")},
        raising=False,
    )

    expectation_target = update_autofix_expectations.AutofixTarget(
        module="tests.test_autofix_repo_regressions",
        callable_name="compute_expected_autofix_selected_funds",
        constant_name="EXPECTED_AUTOFIX_SELECTED_FUNDS",
    )
    monkeypatch.setattr(
        update_autofix_expectations,
        "ROOT",
        repo_root,
        raising=False,
    )
    monkeypatch.setattr(
        update_autofix_expectations, "TARGETS", (expectation_target,), raising=False
    )

    monkeypatch.setattr(mypy_autofix, "ROOT", repo_root, raising=False)
    monkeypatch.setattr(mypy_autofix, "DEFAULT_TARGETS", [src_dir, tests_dir], raising=False)

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
            str(return_probe.relative_to(repo_root)),
        ],
        raising=False,
    )

    relative_targets = [
        str(automation_path.relative_to(repo_root)),
        str(expectation_module_target.relative_to(repo_root)),
        str(return_probe.relative_to(repo_root)),
    ]

    formatting_commands: list[tuple[list[str], tuple[int, ...]]] = [
        (
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--fix",
                "--exit-zero",
                *relative_targets,
            ],
            (0,),
        ),
        ([sys.executable, "-m", "isort", *relative_targets], (0,)),
        ([sys.executable, "-m", "black", *relative_targets], (0,)),
        (
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--fix",
                "--exit-zero",
                *relative_targets,
            ],
            (0,),
        ),
    ]
    for command, ok_codes in formatting_commands:
        _run(command, cwd=repo_root, ok_exit_codes=ok_codes)

    auto_type_hygiene.main()
    fix_cosmetic_aggregate.main()
    fix_numpy_asserts.main()

    update_autofix_expectations.main()

    mypy_autofix.main(["--paths", str(src_dir), str(tests_dir)])
    mypy_return_autofix.main()

    for command, ok_codes in formatting_commands:
        _run(command, cwd=repo_root, ok_exit_codes=ok_codes)

    module = importlib.import_module("tests.test_autofix_repo_regressions")
    module = importlib.reload(module)
    assert module.__file__ is not None
    module_path = Path(module.__file__).resolve()
    assert module_path.is_relative_to(repo_root)
    assert module.EXPECTED_AUTOFIX_SELECTED_FUNDS == 2

    _run([sys.executable, "-m", "ruff", "check", *relative_targets], cwd=repo_root)
    _run([sys.executable, "-m", "black", "--check", *relative_targets], cwd=repo_root)
    _run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--ignore-missing-imports",
            str(expectation_module_target),
            str(return_probe),
        ],
        cwd=repo_root,
    )

    repaired_automation = automation_path.read_text(encoding="utf-8")
    assert repaired_automation == automation_original

    repaired_expectations = expectation_module_target.read_text(encoding="utf-8")
    assert repaired_expectations == expectation_original

    probe_text = return_probe.read_text(encoding="utf-8")
    assert "-> str:" in probe_text
    assert "return pieces" in probe_text
