"""Contract tests for the core-label sync workflow.

maint-69 writes labels into OTHER repositories. Two defects made it report success
while syncing nothing (see issue #3007):

* it passed the default ``GITHUB_TOKEN``, which is scoped to this repository and
  cannot create labels elsewhere; and
* every failed write was swallowed by a ``try``/``catch`` that only appended to the
  run summary, so the job concluded ``success`` with zero labels created.

These tests pin both fixes plus the ``issues: write`` permission.
"""

import re
from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/maint-69-sync-labels.yml")
SYNC_JOB = "sync-labels"
SYNC_STEP = "Sync labels to repos"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _job() -> dict:
    return _workflow()["jobs"][SYNC_JOB]


def _step(name: str) -> dict:
    return next(step for step in _job()["steps"] if step.get("name") == name)


def test_label_sync_declares_issues_write_permission() -> None:
    permissions = _workflow()["permissions"]

    assert permissions.get("issues") == "write", (
        "label creation requires issues: write; without it the sync cannot write labels "
        "even in this repository"
    )


def test_label_sync_uses_cross_repo_token_not_default_github_token() -> None:
    job = _job()
    step = _step(SYNC_STEP)
    token = step["with"]["github-token"]

    assert "REPO_TOKEN" not in job.get(
        "env", {}
    ), "the cross-repository credential must not be exposed to unrelated job steps"
    assert "secrets.OWNER_PR_PAT" in token
    assert "secrets.SERVICE_BOT_PAT" in token
    assert "github.token" in token, "tokenless dry runs need a read-only fallback"


def test_label_sync_refuses_to_run_without_a_cross_repo_token() -> None:
    guard = _step("Assert cross-repo token is present")

    assert guard["if"] == "inputs.dry_run != true"
    assert "secrets.OWNER_PR_PAT" in guard["env"]["REPO_TOKEN"]
    assert "secrets.SERVICE_BOT_PAT" in guard["env"]["REPO_TOKEN"]
    assert "REPO_TOKEN" in guard["run"]
    assert (
        "exit 1" in guard["run"]
    ), "a missing PAT must fail loudly rather than silently syncing nothing"


def test_label_sync_fails_the_job_when_any_label_write_errors() -> None:
    script = _step(SYNC_STEP)["with"]["script"]

    assert "totalErrors" in script, "per-repo error counts must be aggregated across repos"
    assert "if (totalErrors > 0)" in script
    aggregate_index = script.index("if (totalErrors > 0)")
    failure_index = script.index("core.setFailed", aggregate_index)
    assert failure_index > aggregate_index
    assert "label sync error(s)" in script[failure_index:]


def test_label_sync_records_fetch_errors_before_failing_the_aggregate() -> None:
    script = _step(SYNC_STEP)["with"]["script"]

    fetch_index = script.index("github.rest.issues.listLabelsForRepo")
    fetch_error_index = script.index("Failed to fetch labels", fetch_index)
    increment_index = script.index("totalErrors++", fetch_error_index)
    summary_index = script.index("await core.summary.addRaw(summary.join('')).write()")
    failure_index = script.index("core.setFailed", summary_index)

    assert fetch_index < fetch_error_index < increment_index < summary_index < failure_index


def test_label_sync_paginates_all_existing_labels_before_creating() -> None:
    """Labels after page one must not be mistaken for missing labels."""
    script = _step(SYNC_STEP)["with"]["script"]

    assert "const { withRetry, paginateWithRetry } = retryHelpers;" in script
    pagination_index = script.index("existingLabels = await paginateWithRetry(")
    list_method_index = script.index("github.rest.issues.listLabelsForRepo", pagination_index)
    map_index = script.index("const existingMap = new Map(existingLabels", list_method_index)
    assert pagination_index < list_method_index < map_index
    assert (
        "const { data } = await withRetry(() => github.rest.issues.listLabelsForRepo" not in script
    )


# --- label colours must survive a YAML 1.2 loader -------------------------
#
# Third defect in this workflow, found 2026-08-23 once the hold on maint-69 was
# lifted: 79 label-sync errors across 14 repos, every one of them
#
#     For 'properties/color', 53190000000 is not a string.
#
# 53190000000 is `5319e7` read as scientific notation. The sync step runs
# `yaml.load` from js-yaml, whose YAML 1.2 core schema resolves `5319e7` to a
# float; PyYAML follows YAML 1.1, which requires a decimal point, so it keeps the
# same text as a string. Every local check therefore passed while the deployed
# job failed against the API -- the two loaders disagreed and only one of them
# ran in CI.
#
# The invariant is loader-independent and cheap: colours are quoted in the source.
# Checking the PyYAML-parsed value cannot catch this, because PyYAML is the loader
# that gets it right, so these tests read the raw text.

LABEL_FILES = (Path(".github/labels-core.yml"), Path(".github/labels.yml"))

_COLOR_LINE = re.compile(r"^\s*color:\s*(\S+)\s*$", re.MULTILINE)
# What a YAML 1.2 core-schema loader would resolve to a number rather than a str.
_NUMERIC_LOOKING = re.compile(r"^(?:[0-9]+(?:[eE][+-]?[0-9]+)?|0[xX][0-9a-fA-F]+)$")


def _color_values(path: Path) -> list[str]:
    return _COLOR_LINE.findall(path.read_text(encoding="utf-8"))


def test_every_label_colour_is_quoted_in_source() -> None:
    """Quoting is the invariant, because it is loader-independent."""
    for path in LABEL_FILES:
        values = _color_values(path)
        assert values, f"{path} parsed no colours - the regex or the file shape changed"
        unquoted = [v for v in values if v[:1] not in "\"'"]
        assert not unquoted, (
            f"{path} has unquoted label colours {unquoted}. js-yaml resolves an "
            f"unquoted hex colour like 5319e7 to the number 5.319e10, and the "
            f'GitHub API rejects it with "is not a string". Quote it.'
        )


def test_no_label_colour_would_be_coerced_to_a_number() -> None:
    """Belt and braces: catch a numeric-looking colour even if quoting slips.

    `123456` is as dangerous as `5319e7` -- both are valid hex colours and both
    resolve to numbers unquoted.
    """
    for path in LABEL_FILES:
        for value in _color_values(path):
            bare = value.strip("\"'")
            if value[:1] in "\"'":
                continue  # quoted, so the loader keeps it a string
            assert not _NUMERIC_LOOKING.match(
                bare
            ), f"{path}: colour {value} would be loaded as a number by js-yaml"


def test_label_colours_are_six_hex_digits() -> None:
    """A colour the API will accept: exactly six hex digits, no leading '#'."""
    for path in LABEL_FILES:
        for value in _color_values(path):
            bare = value.strip("\"'")
            assert re.fullmatch(
                r"[0-9a-fA-F]{6}", bare
            ), f"{path}: {value!r} is not a bare six-hex-digit colour"
