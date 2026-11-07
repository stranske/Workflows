"""Scripts delivered to consumers must type-check in a consumer layout (Workflows#3993).

trip-planner's mypy gate rejected the delivered scripts/ledger_validate.py: its direct-execution
import fallbacks (`belt_ledger_completion`, `utils.paths`) cannot be resolved there. A consumer
has none of this repo's `src/` or mypy settings, so check the files alone with only a package
marker next to them.
"""

import hashlib
import json
import re
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


def test_retained_consumer_registry_matches_observed_github_blob():
    fixture = ROOT / "tests/fixtures/issue_4506"
    observation = json.loads((fixture / "delivery-observation.json").read_text(encoding="utf-8"))
    source = (fixture / observation["file"]["snapshot"]).read_bytes()
    # Git's blob ID binds the exact bytes fetched at the recorded immutable head.
    git_blob = b"blob " + str(len(source)).encode("ascii") + b"\0" + source
    assert hashlib.sha1(git_blob).hexdigest() == observation["file"]["git_blob_sha"]


def test_retained_consumer_mypy_receipt_passed_for_the_delivered_head():
    """A green job on a different head cannot establish delivery acceptance (#4506)."""
    fixture = ROOT / "tests/fixtures/issue_4506"
    observation = json.loads((fixture / "delivery-observation.json").read_text(encoding="utf-8"))
    ci = observation["ci"]
    assert ci["name"] == "Python CI / typecheck-mypy"
    assert (ci["status"], ci["conclusion"]) == ("completed", "success")
    steps = {step["name"]: step for step in ci["steps"]}
    for name in ("Mypy (type check)", "Finalize mypy"):
        assert (steps[name]["status"], steps[name]["conclusion"]) == ("completed", "success")

    log = "\n".join(ci["log_excerpt"])
    checked_out_heads = re.findall(
        r"^\S+ HEAD is now at [0-9a-f]+ Merge ([0-9a-f]{40}) into [0-9a-f]{40}$",
        log,
        flags=re.MULTILINE,
    )
    assert checked_out_heads == [observation["head_sha"]]
    assert re.search(r"^\S+ Success: no issues found in [1-9][0-9]* source files$", log, re.M)
    assert re.search(r"^\S+\s+MYPY_OUTCOME: success$", log, re.M)
    # This checks the retained native CI evidence only. It cannot substitute for
    # the literal gh command or an independently retained sync-core round.


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
@pytest.mark.parametrize(
    "source_path",
    [
        "tools/llm_registry.py",
        "templates/consumer-repo/tools/llm_registry.py",
        pytest.param(
            "tests/fixtures/issue_4506/llm_registry.py.txt",
            id="trip-planner-1957-head-7ca6deb8",
        ),
    ],
)
@pytest.mark.parametrize("restore_bug", [False, True], ids=["fixed", "pre-fix"])
def test_delivered_llm_registry_type_checks_in_a_consumer_layout(
    tmp_path, source_path, restore_bug
):
    """Consumer settings must catch optional providers passed to SlotDefinition (#4485).

    Mirror trip-planner's mypy gate rather than Workflows' pyproject, which sets
    ignore_errors for tools.* and would hide the shipped arg-type failure that
    sync-core reported on tools/llm_registry.py:580. Match reusable-10-ci-python:
    ``--config-file pyproject.toml --exclude .workflows-lib`` with target ``.``.
    """
    package = tmp_path / "tools"
    package.mkdir()
    (package / "__init__.py").write_text("")
    delivered = package / "llm_registry.py"
    # Include the immutable consumer-head capture: checking source/template alone
    # cannot establish that regeneration delivered the provider guard (#4506).
    shutil.copy(ROOT / source_path, delivered)
    if restore_bug:
        # Break only the isolated consumer copy: prove mypy really checks this call,
        # rather than passing because an ignore_errors setting hid the defect.
        # Reintroduce the pre-#4485 path that fed optional providers into the
        # retired SlotDefinition call (no early None rejection).
        source = delivered.read_text(encoding="utf-8")
        early_reject = (
            "        # Missing/unknown providers cannot form a slot identity (including a\n"
            "        # retired placeholder). Reject early so every SlotDefinition call below\n"
            "        # receives a str — consumer mypy rejects str | None (Workflows#4485).\n"
            "        if provider is None:\n"
            "            continue\n"
        )
        assert source.count(early_reject) == 1, source
        delivered.write_text(source.replace(early_reject, ""), encoding="utf-8")

    # trip-planner pyproject knobs that surfaced the shipment-caused failure.
    (tmp_path / "pyproject.toml").write_text(
        "[tool.mypy]\n" "explicit_package_bases = true\n" "namespace_packages = true\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            "pyproject.toml",
            "--exclude",
            ".workflows-lib",
            "--cache-dir",
            str(tmp_path / "mypy-cache"),
            "--no-incremental",
            ".",
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
        assert "Success: no issues found" in result.stdout
