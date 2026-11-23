"""Exercise the local formatter entry points with checkout and tool controls."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
SHARED = SCRIPTS / "fix-integration-tests-formatting.sh"
LEGACY = SCRIPTS / "fix_integration_tests_formatting.sh"
TARGETS = (
    "scripts/validate_dependency_test_setup.py",
    "tests/test_dependency_version_alignment.py",
)


def executable(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def integration_checkout(tmp_path: Path) -> tuple[Path, Path, Path]:
    checkout = tmp_path / "integration checkout"
    tools = tmp_path / "bin"
    tools.mkdir()
    for name in ("bash", "dirname", "git"):
        program = shutil.which(name)
        if not program or not Path("/bin/sh").exists():
            pytest.skip("requires a Unix shell and git")
        (tools / name).symlink_to(program)
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    for name in (
        *TARGETS,
        ".github/workflows/notify-workflows.yml",
        "pyproject.toml",
        "outside.py",
    ):
        path = checkout / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("original\n", encoding="utf-8")
    log = tmp_path / "calls.txt"
    executable(
        tools / "black",
        """
echo "black $*" >> "$FORMATTER_LOG"
for file; do printf 'formatted\n' > "$file"; done
""",
    )
    executable(
        tools / "python3",
        """
echo "python3 $*" >> "$FORMATTER_LOG"
case "$*" in
  "-m black --version") exit 0 ;;
  "-m ruff --version") exit "${RUFF_CHECK_STATUS:-0}" ;;
  "-m black .") printf 'formatted\n' > outside.py ;;
  "-m ruff check --fix .") exit "${RUFF_RUN_STATUS:-0}" ;;
  *) exit 91 ;;
esac
""",
    )
    return checkout, tools, log


def run_formatter(
    fixture: tuple[Path, Path, Path], mode: str, **statuses: str
) -> tuple[int, list[str]]:
    checkout, tools, log = fixture
    shell = tools / "bash"
    if mode == "legacy":
        args = [str(shell), str(LEGACY), "ignored-by-legacy"]
    else:
        args = [str(shell), str(SHARED)]
        if mode == "all":
            args.append("--all")
        args.append(str(checkout))
    result = subprocess.run(
        args,
        cwd=checkout if mode == "legacy" else checkout.parent,
        env={**os.environ, "PATH": str(tools), "FORMATTER_LOG": str(log), **statuses},
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, log.read_text().splitlines() if log.exists() else []


def test_default_formats_only_named_files(integration_checkout: tuple[Path, Path, Path]) -> None:
    checkout, _, _ = integration_checkout
    assert run_formatter(integration_checkout, "narrow") == (0, ["black " + " ".join(TARGETS)])
    assert all((checkout / target).read_text() == "formatted\n" for target in TARGETS)
    assert (checkout / "outside.py").read_text() == "original\n"


@pytest.mark.parametrize("mode", ["all", "legacy"])
def test_full_formatting_uses_existing_python_modules(
    integration_checkout: tuple[Path, Path, Path], mode: str
) -> None:
    checkout, tools, _ = integration_checkout
    (tools / "black").unlink()
    assert run_formatter(integration_checkout, mode) == (
        0,
        [
            "python3 -m black --version",
            "python3 -m ruff --version",
            "python3 -m black .",
            "python3 -m ruff check --fix .",
        ],
    )
    assert (checkout / "outside.py").read_text() == "formatted\n"


@pytest.mark.parametrize(
    ("mode", "missing"),
    [
        ("legacy", ".github/workflows/notify-workflows.yml"),
        ("all", "pyproject.toml"),
        ("legacy", TARGETS[0]),
        ("narrow", TARGETS[1]),
    ],
)
def test_invalid_inputs_fail_before_invoking_tools(
    integration_checkout: tuple[Path, Path, Path], mode: str, missing: str
) -> None:
    checkout, _, _ = integration_checkout
    (checkout / missing).unlink()
    assert run_formatter(integration_checkout, mode) == (1, [])
    assert (checkout / "outside.py").read_text() == "original\n"


def test_missing_black_does_not_install(integration_checkout: tuple[Path, Path, Path]) -> None:
    checkout, tools, _ = integration_checkout
    (tools / "black").unlink()
    assert run_formatter(integration_checkout, "narrow") == (1, [])
    assert (checkout / TARGETS[0]).read_text() == "original\n"


def test_missing_ruff_stops_before_formatting(
    integration_checkout: tuple[Path, Path, Path],
) -> None:
    checkout, _, _ = integration_checkout
    assert run_formatter(integration_checkout, "legacy", RUFF_CHECK_STATUS="1") == (
        1,
        ["python3 -m black --version", "python3 -m ruff --version"],
    )
    assert (checkout / "outside.py").read_text() == "original\n"


def test_full_formatter_propagates_failure(
    integration_checkout: tuple[Path, Path, Path],
) -> None:
    code, calls = run_formatter(integration_checkout, "legacy", RUFF_RUN_STATUS="7")
    assert code == 7
    assert calls[-1] == "python3 -m ruff check --fix ."
