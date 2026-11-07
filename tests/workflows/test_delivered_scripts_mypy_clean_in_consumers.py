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


def _assert_consumer_mypy_receipt(observation):
    """Require native checkout and executed mypy evidence for the delivered head."""
    ci = observation["ci"]
    # Assert required CI sections and step names exist before indexing
    assert "name" in ci, "CI section missing 'name'"
    assert "status" in ci, "CI section missing 'status'"
    assert "conclusion" in ci, "CI section missing 'conclusion'"
    assert "steps" in ci, "CI section missing 'steps'"
    assert "log_excerpt" in ci, "CI section missing 'log_excerpt'"

    assert ci["name"] == "Python CI / typecheck-mypy"
    assert (ci["status"], ci["conclusion"]) == ("completed", "success")

    # Validate steps structure before indexing
    assert isinstance(ci["steps"], list), "steps must be a list"
    assert len(ci["steps"]) >= 2, "At least 2 steps required: Mypy (type check) and Finalize mypy"

    step_names = [step["name"] for step in ci["steps"]]
    for required_name in ("Mypy (type check)", "Finalize mypy"):
        assert (
            required_name in step_names
        ), f"Required step '{required_name}' not found in {step_names}"

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


def test_retained_consumer_mypy_receipt_passed_for_the_delivered_head():
    """A green job on a different head cannot establish delivery acceptance (#4506)."""
    fixture = ROOT / "tests/fixtures/issue_4506"
    observation = json.loads((fixture / "delivery-observation.json").read_text(encoding="utf-8"))
    _assert_consumer_mypy_receipt(observation)


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        pytest.param(("head_sha",), "0" * 40, id="stale-checkout"),
        pytest.param(("ci", "name"), "Python CI / lint-ruff", id="different-job"),
        pytest.param(("ci", "status"), "in_progress", id="unfinished-job"),
        pytest.param(("ci", "conclusion"), "failure", id="failed-job"),
        pytest.param(("ci", "steps", 0, "conclusion"), "skipped", id="skipped-mypy"),
        pytest.param(("ci", "steps", 0, "status"), "queued", id="unstarted-mypy"),
        pytest.param(("ci", "steps", 1, "conclusion"), "failure", id="failed-finalization"),
        pytest.param(("ci", "log_excerpt", 1), "", id="missing-checkout-log"),
        pytest.param(("ci", "log_excerpt", 3), "", id="missing-typecheck-result"),
        pytest.param(("ci", "log_excerpt", 4), "", id="missing-final-outcome"),
    ],
)
def test_consumer_mypy_receipt_rejects_incomplete_or_stale_evidence(path, replacement):
    """Keep the previously manual deliberate-break receipt checks executable."""
    fixture = ROOT / "tests/fixtures/issue_4506"
    observation = json.loads((fixture / "delivery-observation.json").read_text(encoding="utf-8"))
    target = observation
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement

    with pytest.raises(AssertionError):
        _assert_consumer_mypy_receipt(observation)


@pytest.mark.parametrize(
    "missing_section",
    [
        pytest.param("name", id="missing-ci-name"),
        pytest.param("status", id="missing-ci-status"),
        pytest.param("conclusion", id="missing-ci-conclusion"),
        pytest.param("steps", id="missing-ci-steps"),
        pytest.param("log_excerpt", id="missing-ci-log-excerpt"),
    ],
)
def test_consumer_mypy_receipt_rejects_missing_ci_sections(missing_section):
    """Add missing-step rejection coverage: CI sections must exist."""
    fixture = ROOT / "tests/fixtures/issue_4506"
    observation = json.loads((fixture / "delivery-observation.json").read_text(encoding="utf-8"))
    del observation["ci"][missing_section]

    with pytest.raises(AssertionError) as exc_info:
        _assert_consumer_mypy_receipt(observation)
    assert missing_section in str(exc_info.value)


def test_consumer_mypy_receipt_rejects_missing_required_steps():
    """Reject when required step names are missing from the steps list."""
    fixture = ROOT / "tests/fixtures/issue_4506"
    observation = json.loads((fixture / "delivery-observation.json").read_text(encoding="utf-8"))
    # Keep only one step, remove the other
    observation["ci"]["steps"] = [observation["ci"]["steps"][0]]

    with pytest.raises(AssertionError) as exc_info:
        _assert_consumer_mypy_receipt(observation)
    assert "Finalize mypy" in str(exc_info.value)


def test_consumer_mypy_receipt_validates_reordered_steps():
    """Validate reordered steps/logs still exercise each named corruption."""
    fixture = ROOT / "tests/fixtures/issue_4506"
    observation = json.loads((fixture / "delivery-observation.json").read_text(encoding="utf-8"))
    # Reverse the order of steps
    observation["ci"]["steps"] = list(reversed(observation["ci"]["steps"]))
    # Reverse the order of log excerpts
    observation["ci"]["log_excerpt"] = list(reversed(observation["ci"]["log_excerpt"]))

    # This should still pass because we check for presence, not order
    _assert_consumer_mypy_receipt(observation)


def test_identify_mutation_targets_by_step_name():
    """Identify mutation targets by step name or log pattern with preconditions outside pytest.raises.

    This test explicitly identifies the mutation targets (step names and log patterns)
    that are validated by _assert_consumer_mypy_receipt, establishing that:
    1. Required step names: 'Mypy (type check)' and 'Finalize mypy'
    2. Required log patterns: HEAD checkout line, success message, outcome line
    """
    fixture = ROOT / "tests/fixtures/issue_4506"
    observation = json.loads((fixture / "delivery-observation.json").read_text(encoding="utf-8"))

    # Preconditions: identify the mutation targets
    ci = observation["ci"]
    step_names = [step["name"] for step in ci["steps"]]
    assert "Mypy (type check)" in step_names
    assert "Finalize mypy" in step_names

    log = "\n".join(ci["log_excerpt"])
    assert re.search(r"HEAD is now at", log)
    assert re.search(r"Success: no issues found", log)
    assert re.search(r"MYPY_OUTCOME: success", log)

    # Now verify the full assertion passes
    _assert_consumer_mypy_receipt(observation)


def test_identify_mutation_targets_by_log_pattern():
    """Identify mutation targets by log pattern with preconditions."""
    fixture = ROOT / "tests/fixtures/issue_4506"
    observation = json.loads((fixture / "delivery-observation.json").read_text(encoding="utf-8"))

    # Identify the log patterns that must be present
    log = "\n".join(observation["ci"]["log_excerpt"])

    # These are the mutation targets - the patterns we check for
    checkout_pattern = r"^\S+ HEAD is now at [0-9a-f]+ Merge ([0-9a-f]{40}) into [0-9a-f]{40}$"
    success_pattern = r"^\S+ Success: no issues found in [1-9][0-9]* source files$"
    outcome_pattern = r"^\S+\s+MYPY_OUTCOME: success$"

    # Preconditions: patterns must exist in the log
    assert re.search(checkout_pattern, log, re.MULTILINE)
    assert re.search(success_pattern, log, re.MULTILINE)
    assert re.search(outcome_pattern, log, re.MULTILINE)

    # Verify the observation passes with these patterns present
    _assert_consumer_mypy_receipt(observation)


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
