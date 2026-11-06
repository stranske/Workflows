"""Scripts delivered to consumers must type-check in a consumer layout (Workflows#3993).

trip-planner's mypy gate rejected the delivered scripts/ledger_validate.py: its direct-execution
import fallbacks (`belt_ledger_completion`, `utils.paths`) cannot be resolved there. A consumer
has none of this repo's `src/` or mypy settings, so check the files alone with only a package
marker next to them.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DELIVERED = ("scripts/ledger_validate.py", "scripts/belt_ledger_completion.py")

mypy_available = (
    subprocess.run([sys.executable, "-m", "mypy", "--version"], capture_output=True).returncode == 0
)


@pytest.mark.skipif(not mypy_available, reason="mypy is not installed")
def test_delivered_ledger_scripts_type_check_in_a_consumer_layout(tmp_path):
    package = tmp_path / "scripts"
    package.mkdir()
    (package / "__init__.py").write_text("")
    for rel in DELIVERED:
        shutil.copy(ROOT / rel, package / Path(rel).name)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "scripts",
            "--warn-unused-ignores",
            "--no-incremental",
            # third-party stubs (PyYAML) vary by environment; the unresolved-import errors this
            # test exists to catch use different codes and still fail.
            "--disable-error-code=import-untyped",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout
    assert "Success: no issues found in 3 source files" in result.stdout


@pytest.mark.skipif(not mypy_available, reason="mypy is not installed")
@pytest.mark.parametrize("source_tree", [".", "templates/consumer-repo"])
@pytest.mark.parametrize("restore_bug", [False, True], ids=["fixed", "pre-fix"])
def test_delivered_llm_registry_type_checks_in_a_consumer_layout(
    tmp_path, source_tree, restore_bug
):
    """Consumer settings must catch optional providers passed to SlotDefinition (#4485).

    Mirror trip-planner's mypy gate (explicit_package_bases / namespace_packages) rather
    than Workflows' pyproject, which sets ignore_errors for tools.* and would hide the
    shipped arg-type failure that sync-core reported on tools/llm_registry.py:580.
    """
    package = tmp_path / "tools"
    package.mkdir()
    (package / "__init__.py").write_text("")
    delivered = package / "llm_registry.py"
    shutil.copy(ROOT / source_tree / "tools/llm_registry.py", delivered)
    if restore_bug:
        # Break only the isolated consumer copy: prove mypy really checks this call,
        # rather than passing because an ignore_errors setting hid the defect.
        source = delivered.read_text(encoding="utf-8")
        guard = "if provider is not None and (profile, provider) in retired:"
        assert source.count(guard) == 1
        delivered.write_text(
            source.replace(guard, "if (profile, provider) in retired:"), encoding="utf-8"
        )

    # Match the consumer pyproject knobs that surfaced the shipment-caused failure.
    (tmp_path / "mypy.ini").write_text(
        "[mypy]\nexplicit_package_bases = true\nnamespace_packages = true\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            "mypy.ini",
            "--cache-dir",
            str(tmp_path / "mypy-cache"),
            "--no-incremental",
            "tools/llm_registry.py",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    if restore_bug:
        assert result.returncode == 1, result.stdout + result.stderr
        errors = [line for line in result.stdout.splitlines() if ": error:" in line]
        assert len(errors) == 1, result.stdout + result.stderr
        assert (
            'Argument "provider" to "SlotDefinition" has incompatible type "str | None"; '
            'expected "str"  [arg-type]'
        ) in errors[0]
    else:
        # Zero exit code is the shipment gate; keep it explicit like other consumer
        # typecheck regressions (tests/scripts/test_consumer_script_typecheck.py).
        assert result.returncode == 0, result.stdout + result.stderr
