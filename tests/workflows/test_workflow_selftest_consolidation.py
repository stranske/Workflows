from __future__ import annotations

import pathlib

import yaml

ARCHIVE_LEDGER_PATH = pathlib.Path("docs/archive/ARCHIVE_WORKFLOWS.md")
WORKFLOW_SYSTEM_DOC = pathlib.Path("docs/ci/WORKFLOW_SYSTEM.md")
WORKFLOWS_DOC = pathlib.Path("docs/ci/WORKFLOWS.md")
RUNNER_PLAN_PATH = pathlib.Path("docs/ci/selftest_runner_plan.md")

LEGACY_COMMENT_WRAPPERS = (
    "maint-43-selftest-pr-comment.yml",
    "pr-20-selftest-pr-comment.yml",
    "selftest-pr-comment.yml",
)

LEGACY_COMMENT_WRAPPER_STEMS = tuple(pathlib.Path(name).stem for name in LEGACY_COMMENT_WRAPPERS)


def _normalize(text: str) -> str:
    return text.replace("\u00a0", " ")


WORKFLOW_DIR = pathlib.Path(".github/workflows")
ARCHIVE_DIR = pathlib.Path("Old/workflows")
SELFTEST_WORKFLOW = WORKFLOW_DIR / "selftest-reusable-ci.yml"
SELFTEST_WORKFLOW_NAME = "selftest-reusable-ci.yml"
SELFTEST_TITLE = "Selftest: Reusables"


def _read_workflow(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def _resolve_triggers(data: dict) -> dict:
    """Normalize workflow `on` definitions to a mapping."""

    triggers_raw = data.get("on")
    if triggers_raw is None and True in data:
        triggers_raw = data[True]
    if triggers_raw is None:
        return {}

    if isinstance(triggers_raw, list):
        return {str(event): {} for event in triggers_raw}
    if isinstance(triggers_raw, str):
        return {triggers_raw: {}}
    if isinstance(triggers_raw, dict):
        return triggers_raw

    raise AssertionError(f"Unexpected trigger configuration: {type(triggers_raw)!r}")


def test_selftest_workflow_inventory() -> None:
    """Selftest: Reusables should be the only active workflow."""

    selftest_workflows = sorted(path.name for path in WORKFLOW_DIR.glob("*selftest*.yml"))
    expected = [SELFTEST_WORKFLOW_NAME]
    assert (
        selftest_workflows == expected
    ), f"Active self-test inventory drifted; expected {expected} but saw {selftest_workflows}."


def test_legacy_selftest_pr_comment_wrappers_absent() -> None:
    """Redundant PR comment wrappers should remain deleted."""

    expected_missing = set(LEGACY_COMMENT_WRAPPER_STEMS)

    active_matches = _collect_comment_wrapper_variants(WORKFLOW_DIR)
    archived_matches = _collect_comment_wrapper_variants(ARCHIVE_DIR)

    unexpected_active = sorted(
        name
        for stem, names in active_matches.items()
        if stem in expected_missing
        for name in sorted(names)
    )
    unexpected_archived = sorted(
        name
        for stem, names in archived_matches.items()
        if stem in expected_missing
        for name in sorted(names)
    )

    assert not unexpected_active, (
        "Legacy self-test comment workflows resurfaced in .github/workflows/: "
        f"{unexpected_active}"
    )
    assert not unexpected_archived, (
        "Legacy self-test comment workflows should no longer be tracked in "
        "Old/workflows/: "
        f"{unexpected_archived}"
    )


def test_archive_ledgers_comment_wrappers() -> None:
    """Archive ledger must document the retired comment wrappers."""

    ledger_text = _normalize(ARCHIVE_LEDGER_PATH.read_text())
    for wrapper in LEGACY_COMMENT_WRAPPERS:
        assert (
            wrapper in ledger_text
        ), f"Archive ledger missing entry for retired workflow {wrapper}."

    assert (
        "Gate summary job" in ledger_text
    ), "Archive ledger should point readers to the Gate summary job path."
    assert (
        SELFTEST_WORKFLOW_NAME in ledger_text
    ), "Archive ledger should reference the consolidated self-test workflow."
    assert (
        "selftest-reusable-ci.yml" in ledger_text
    ), "Archive ledger should reference the consolidated Selftest: Reusables workflow."
    assert (
        "Issue #2814" in ledger_text or "Issue #2814" in ledger_text
    ), "Archive ledger should acknowledge the reinstatement tracked by Issue #2814."


def test_workflow_docs_highlight_comment_consolidation() -> None:
    """Documentation must highlight the surviving self-test comment surfaces."""

    system_text = _normalize(WORKFLOW_SYSTEM_DOC.read_text())
    catalog_text = _normalize(WORKFLOWS_DOC.read_text())

    for doc_text in (system_text, catalog_text):
        assert (
            "Gate summary job" in doc_text
        ), "Docs should explain the Gate summary job as the canonical comment path."
        assert (
            SELFTEST_WORKFLOW_NAME in doc_text
        ), "Docs should reference the canonical self-test workflow."

    for wrapper in LEGACY_COMMENT_WRAPPERS:
        assert (
            wrapper in system_text or wrapper in catalog_text
        ), f"Docs should mention the retirement of {wrapper}."


def test_selftest_runner_plan_status_highlights_completion() -> None:
    """Runner plan should mark consolidation completion and spotlight the single workflow."""

    plan_text = _normalize(RUNNER_PLAN_PATH.read_text())
    assert (
        "Status (2026-11-15, Issue #2728)" in plan_text
    ), "Runner plan should flag Issue #2728 completion in the status block."
    assert (
        SELFTEST_WORKFLOW_NAME in plan_text
    ), "Runner plan should point to the consolidated self-test workflow."


def test_selftest_runner_inputs_cover_variants() -> None:
    """The consolidated runner should expose the requested input variants."""

    data = _read_workflow(SELFTEST_WORKFLOW)
    triggers = _resolve_triggers(data)

    assert triggers, f"{SELFTEST_WORKFLOW_NAME} is missing trigger definitions."
    assert set(triggers) == {
        "schedule",
        "workflow_dispatch",
    }, "Runner must expose schedule and workflow_dispatch triggers."

    schedule_entries = triggers.get("schedule", [])
    assert (
        isinstance(schedule_entries, list) and schedule_entries
    ), "Runner schedule trigger should declare at least one cron entry."
    primary_schedule = schedule_entries[0]
    assert (
        primary_schedule.get("cron") == "30 6 * * *"
    ), "Selftest: Reusables nightly cron drifted; update docs/tests with intentional changes."

    workflow_dispatch = triggers.get("workflow_dispatch") or {}
    inputs = workflow_dispatch.get("inputs", {})

    def _assert_choice(
        field_name: str, expected_options: list[str], *, default: str | None
    ) -> None:
        field = inputs.get(field_name)
        assert field is not None, f"Missing `{field_name}` input on {SELFTEST_WORKFLOW_NAME}."
        assert (
            field.get("type", "choice") == "choice"
        ), f"`{field_name}` should remain a choice input."
        options_raw = field.get("options", [])
        options_normalized = [str(option).lower() for option in options_raw]
        expected_normalized = [option.lower() for option in expected_options]
        assert (
            options_normalized == expected_normalized
        ), f"Unexpected option set for `{field_name}`: {options_raw!r}."
        if default is not None:
            actual_default = field.get("default")
            if isinstance(actual_default, bool):
                actual_default_normalized = str(actual_default).lower()
            else:
                actual_default_normalized = str(actual_default)
            assert (
                actual_default_normalized == default
            ), f"`{field_name}` default drifted from {default!r}."

    _assert_choice("mode", ["summary", "comment", "dual-runtime"], default="summary")
    _assert_choice("post_to", ["pr-number", "none"], default="none")
    _assert_choice("enable_history", ["true", "false"], default="false")

    pr_number = inputs.get("pull_request_number", {})
    required_raw = pr_number.get("required")
    assert required_raw in (
        None,
        False,
        "false",
    ), "pull_request_number must remain optional to reuse comment mode outside PRs."

    jobs = data.get("jobs", {})
    scenario_job = jobs.get("scenarios") or {}
    assert scenario_job, f"{SELFTEST_WORKFLOW_NAME} must declare the scenario job."
    assert (
        scenario_job.get("uses") == "./.github/workflows/reusable-10-ci-python.yml"
    ), "Runner should delegate execution to reusable-10-ci-python.yml."


def test_selftest_runner_jobs_contract() -> None:
    data = _read_workflow(SELFTEST_WORKFLOW)
    jobs = data.get("jobs", {})

    scenario = jobs.get("scenarios") or {}
    assert scenario, "Reusable CI workflow must define the scenario job."
    assert (
        scenario.get("uses") == "./.github/workflows/reusable-10-ci-python.yml"
    ), "Scenario job must fan out to reusable-10-ci-python.yml via jobs.<id>.uses."
    assert (
        scenario.get("secrets") == "inherit"
    ), "Scenario job should inherit caller secrets for repo access."

    scenario_with = scenario.get("with", {})
    required_with = {
        "python-versions",
        "artifact-prefix",
        "enable-metrics",
        "enable-history",
        "enable-classification",
        "enable-coverage-delta",
        "enable-soft-gate",
        "baseline-coverage",
        "coverage-alert-drop",
    }
    assert required_with.issubset(
        scenario_with
    ), f"Scenario job is missing inputs: {sorted(required_with - set(scenario_with))}."
    assert (
        scenario_with["artifact-prefix"] == "sf-${{ matrix.name }}-"
    ), "Scenario job should namespace artifacts with the matrix name prefix."
    python_versions_expr = scenario_with["python-versions"]
    assert (
        "github.event_name == 'workflow_dispatch'" in python_versions_expr
    ), "Scenario job should branch on workflow_dispatch triggers."
    assert (
        "inputs.python_versions != ''" in python_versions_expr
    ), "Scenario job should respect custom python_versions overrides."
    assert (
        "inputs.mode == 'dual-runtime'" in python_versions_expr
    ), "Scenario job should enable dual-runtime mode when requested."
    assert (
        "'[\"3.11\"]'" in python_versions_expr
    ), "Scenario job should fall back to the default 3.11 matrix."

    strategy = scenario.get("strategy", {})
    assert (
        strategy.get("fail-fast") is False
    ), "Scenario matrix must disable fail-fast to exercise every combination."
    matrix_include = strategy.get("matrix", {}).get("include", [])
    names = [entry.get("name") for entry in matrix_include]
    expected_names = [
        "minimal",
        "metrics_only",
        "metrics_history",
        "classification_only",
        "coverage_delta",
        "full_soft_gate",
    ]
    assert (
        names == expected_names
    ), "Reusable CI scenario matrix drifted; update tests if intentional."

    def _entry(name: str) -> dict:
        return next((item for item in matrix_include if item.get("name") == name), {})

    coverage_delta = _entry("coverage_delta")
    assert (
        coverage_delta.get("baseline-coverage") == "65"
    ), "coverage_delta scenario baseline-coverage should remain '65'."
    assert (
        coverage_delta.get("coverage-alert-drop") == "2"
    ), "coverage_delta scenario coverage-alert-drop should remain '2'."

    full_soft_gate = _entry("full_soft_gate")
    assert (
        full_soft_gate.get("baseline-coverage") == "65"
    ), "full_soft_gate scenario baseline-coverage should remain '65'."
    assert (
        full_soft_gate.get("coverage-alert-drop") == "2"
    ), "full_soft_gate scenario coverage-alert-drop should remain '2'."

    summarize = jobs.get("summarize") or {}
    assert summarize, "Reusable CI workflow must include the aggregate job."
    assert (
        summarize.get("needs") == "scenarios"
    ), "Aggregate job should depend on the matrix execution."
    assert (
        summarize.get("if") == "${{ always() }}"
    ), "Aggregate job must always run to collect results."
    assert (
        summarize.get("runs-on") == "ubuntu-latest"
    ), "Aggregate job should execute on ubuntu-latest."

    permissions = summarize.get("permissions", {})
    assert (
        permissions.get("contents") == "read"
    ), "Aggregate job should only require read access to contents."
    assert (
        permissions.get("actions") == "read"
    ), "Aggregate job should only require read access to actions metadata."

    outputs = summarize.get("outputs", {})
    assert {"summary_table", "failure_count", "run_id"}.issubset(
        outputs
    ), "Aggregate job outputs drifted; downstream jobs require table, failures, and run_id."

    env = summarize.get("env", {})
    assert (
        env.get("SCENARIO_LIST")
        == "minimal,metrics_only,metrics_history,classification_only,coverage_delta,full_soft_gate"
    ), "Aggregate SCENARIO_LIST should enumerate the scenario matrix."
    aggregate_python = env.get("REQUESTED_PYTHONS", "")
    assert (
        "github.event_name == 'workflow_dispatch'" in aggregate_python
    ), "Aggregate job should branch on workflow_dispatch events."
    assert (
        "inputs.python_versions != ''" in aggregate_python
    ), "Aggregate job should honor manual python_versions overrides."
    assert (
        "inputs.mode == 'dual-runtime'" in aggregate_python
    ), "Aggregate job should forward dual-runtime requests."
    assert (
        "'[\"3.11\"]'" in aggregate_python
    ), "Aggregate job should fall back to the default 3.11 matrix."
    assert env.get("RUN_REASON"), "Aggregate job should capture the run reason for summaries."
    assert (
        env.get("TRIGGER_EVENT") == "${{ github.event_name }}"
    ), "Aggregate job should capture the trigger event name."

    steps = summarize.get("steps", [])

    def _find_step(predicate) -> dict:
        return next((step for step in steps if predicate(step)), {})

    verify_step = _find_step(lambda step: step.get("id") == "verify")
    assert verify_step, "Aggregate job must include the verification step."
    assert (
        verify_step.get("uses") == "actions/github-script@v7"
    ), "Verification step should leverage actions/github-script@v7."
    verify_env = verify_step.get("env", {})
    assert (
        verify_env.get("PYTHON_VERSIONS") == "${{ env.REQUESTED_PYTHONS }}"
    ), "Verification step should read python versions from aggregate env."
    assert (
        verify_env.get("SCENARIO_LIST") == "${{ env.SCENARIO_LIST }}"
    ), "Verification step should read scenario list from aggregate env."

    upload_step = _find_step(lambda step: step.get("name") == "Upload self-test report")
    assert upload_step, "Aggregate job must upload the self-test report artifact."
    assert (
        upload_step.get("uses") == "actions/upload-artifact@v4"
    ), "Self-test report upload should use actions/upload-artifact@v4."
    upload_with = upload_step.get("with", {})
    assert (
        upload_with.get("name") == "selftest-report"
    ), "Self-test report artifact name should remain stable for documentation/tests."
    assert (
        upload_with.get("path") == "selftest-report.json"
    ), "Self-test report upload path drifted; keep JSON summary name stable."

    fail_step = _find_step(lambda step: step.get("name") == "Fail on verification errors")
    assert fail_step, "Aggregate job must fail when verification mismatches occur."
    assert (
        fail_step.get("if") == "${{ steps.verify.outputs.failures != '0' }}"
    ), "Failure guard should inspect verification failure count."


def test_selftest_runner_publish_job_contract() -> None:
    """Publish job must enforce verification guardrails consistently."""

    data = _read_workflow(SELFTEST_WORKFLOW)
    jobs = data.get("jobs", {})
    publish = jobs.get("publish") or {}

    assert publish, f"{SELFTEST_WORKFLOW_NAME} should retain the publish job."
    assert set(publish.get("needs", [])) == {
        "scenarios",
        "summarize",
    }, "publish should depend on both the matrix execution and aggregation jobs."
    assert (
        publish.get("if") == "${{ always() }}"
    ), "publish should always execute to surface matrix status."

    permissions = publish.get("permissions", {})
    assert permissions, "publish must declare minimal permissions."
    assert (
        permissions.get("contents") == "read"
    ), "publish should only require read access to contents."
    assert (
        permissions.get("actions") == "read"
    ), "publish should only require read access to actions metadata."
    assert (
        permissions.get("pull-requests") == "write"
    ), "publish needs pull request write access for comment mode."

    unexpected_permissions = sorted(
        key for key in permissions if key not in {"contents", "actions", "pull-requests"}
    )
    assert not unexpected_permissions, (
        "publish should not request extra permissions: " f"{unexpected_permissions}."
    )

    required_env = {
        "MODE",
        "POST_TO",
        "ENABLE_HISTORY",
        "PR_NUMBER",
        "SUMMARY_TITLE",
        "COMMENT_TITLE",
        "REASON",
        "WORKFLOW_RESULT",
        "SUMMARY_TABLE",
        "FAILURE_COUNT",
        "RUN_ID",
        "REQUESTED_VERSIONS",
    }
    env = publish.get("env", {})
    missing_env = sorted(required_env - set(env))
    assert not missing_env, "publish env block drifted; missing keys: " f"{missing_env}."

    steps = publish.get("steps", [])

    def _find_step(name: str) -> dict:
        return next((step for step in steps if step.get("name") == name), {})

    download_step = _find_step("Download self-test report")
    assert download_step, "Download step missing from publish job."
    assert (
        download_step.get("uses") == "actions/download-artifact@v4"
    ), "Download step should use actions/download-artifact@v4."
    assert (
        download_step.get("if") == "${{ env.ENABLE_HISTORY == 'true' && env.RUN_ID != '' }}"
    ), "Download step must guard on enable_history input and aggregate run id."
    download_with = download_step.get("with", {})
    assert (
        download_with.get("run-id") == "${{ env.RUN_ID }}"
    ), "Download step should forward the aggregate run id."
    assert (
        download_with.get("name") == "selftest-report"
    ), "Download step must keep artifact name stable for docs/tests."

    surface_failures = _find_step("Surface failures in logs")
    assert surface_failures, "Missing surface failures guard for summary mode."
    surface_script = surface_failures.get("run", "")
    for expected_snippet in (
        "Verification table output missing",
        "Failure count output missing",
        "Self-test reported",
        "Self-test matrix completed with status",
    ):
        assert (
            expected_snippet in surface_script
        ), f"Surface failures step should mention '{expected_snippet}'."

    comment_finalize = _find_step("Finalize status for comment mode")
    assert comment_finalize, "Comment mode finalizer missing."
    assert (
        comment_finalize.get("if") == "${{ env.MODE == 'comment' }}"
    ), "Comment finalizer should only run during comment mode."
    comment_script = comment_finalize.get("run", "")
    for snippet in (
        "Verification table output missing",
        "Failure count output missing",
        "Self-test reported",
        "Self-test matrix completed with status",
    ):
        assert snippet in comment_script, f"Comment finalizer guard should mention '{snippet}'."


def test_selftest_triggers_are_manual_only() -> None:
    """Self-test workflows must expose manual triggers (with optional
    workflow_call reuse)."""

    selftest_files = sorted(WORKFLOW_DIR.glob("*selftest*.yml"))
    assert selftest_files, "Expected at least one self-test workflow definition."

    disallowed_triggers = {
        "pull_request",
        "pull_request_target",
        "push",
    }
    required_manual_trigger = "workflow_dispatch"
    allowed_triggers = {required_manual_trigger, "workflow_call", "schedule"}

    for workflow_file in selftest_files:
        data = _read_workflow(workflow_file)

        triggers_raw = data.get("on")
        if triggers_raw is None and True in data:
            # `on:` is a YAML keyword; in 1.1 it can be parsed as boolean True.
            triggers_raw = data[True]
        if triggers_raw is None:
            triggers_raw = {}

        if isinstance(triggers_raw, list):
            triggers = {str(event): {} for event in triggers_raw}
        elif isinstance(triggers_raw, str):
            triggers = {triggers_raw: {}}
        elif isinstance(triggers_raw, dict):
            triggers = triggers_raw
        else:
            raise AssertionError(
                f"Unexpected trigger configuration in {workflow_file.name}: {type(triggers_raw)!r}"
            )

        trigger_keys = set(triggers)

        unexpected = sorted(trigger_keys & disallowed_triggers)
        assert not unexpected, (
            f"{workflow_file.name} exposes disallowed triggers: {unexpected}. "
            "Self-tests should not run automatically on PRs or pushes."
        )

        unsupported = sorted(trigger_keys - allowed_triggers)
        assert not unsupported, (
            f"{workflow_file.name} declares unsupported triggers: {unsupported}. "
            "Only workflow_dispatch, schedule, or workflow_call are permitted."
        )

        assert required_manual_trigger in trigger_keys, (
            f"{workflow_file.name} must provide a {required_manual_trigger} "
            "trigger so self-tests remain manually invoked."
        )

        assert "schedule" in trigger_keys, (
            f"{workflow_file.name} should expose a nightly schedule in addition to "
            "workflow_dispatch."
        )
        assert (
            trigger_keys <= allowed_triggers
        ), f"{workflow_file.name} declares unexpected trigger set: {sorted(trigger_keys)}."


def test_selftest_dispatch_reason_input() -> None:
    """Self-test dispatch should keep the reason field optional but present."""

    raw_data = _read_workflow(SELFTEST_WORKFLOW)

    triggers_raw = raw_data.get("on")
    if triggers_raw is None and True in raw_data:
        triggers_raw = raw_data[True]
    if triggers_raw is None:
        triggers_raw = {}

    if isinstance(triggers_raw, dict):
        workflow_dispatch = triggers_raw.get("workflow_dispatch", {})
    else:
        raise AssertionError("Selftest workflow must declare workflow_dispatch as a mapping")

    inputs = workflow_dispatch.get("inputs", {})
    assert "reason" in inputs, "Selftest workflow dispatch is missing a reason input."

    reason_input = inputs["reason"] or {}
    # Normalize the "required" field to a boolean for consistency.
    required_raw = reason_input.get("required")
    required_bool = False if required_raw in (False, "false", None) else True
    assert (
        not required_bool
    ), "Selftest workflow dispatch reason should be optional for manual launches."

    description = reason_input.get("description", "").strip()
    assert description, "Reason input should document why it is collected."

    default_value = reason_input.get("default")
    assert (
        default_value == "manual test"
    ), "Reason input default should remain 'manual test' so callers understand the context."


def test_archived_selftest_inventory() -> None:
    archived_workflows = sorted(path.name for path in ARCHIVE_DIR.glob("*selftest*.yml"))
    assert not archived_workflows, (
        "Self-test archives should no longer live on disk. "
        "Remove duplicates under Old/workflows/ and retrieve historical YAML from git history when needed."
    )

    ledger_text = _normalize(ARCHIVE_LEDGER_PATH.read_text())
    assert (
        "Historical copies of `maint-90-selftest.yml`" in ledger_text
    ), "Archive ledger should document where to find the retired self-test wrappers."
    assert (
        "Old/workflows" in ledger_text
    ), "Archive ledger should mention the former archive directory so contributors know it was removed."
    assert (
        "#2728" in ledger_text
    ), "Archive ledger must reference the consolidation issue that removed the residual files."


def test_selftest_matrix_and_aggregate_contract() -> None:
    assert (
        SELFTEST_WORKFLOW.exists()
    ), f"{SELFTEST_WORKFLOW_NAME} is missing from .github/workflows/"

    data = _read_workflow(SELFTEST_WORKFLOW)
    jobs = data.get("jobs", {})

    scenario_job = jobs.get("scenarios") or {}
    assert (
        scenario_job.get("uses") == "./.github/workflows/reusable-10-ci-python.yml"
    ), "Scenario job must invoke reusable-10-ci-python.yml via jobs.<id>.uses"

    matrix = scenario_job.get("strategy", {}).get("matrix", {}).get("include", [])
    scenario_names = [entry.get("name") for entry in matrix]
    expected_names = [
        "minimal",
        "metrics_only",
        "metrics_history",
        "classification_only",
        "coverage_delta",
        "full_soft_gate",
    ]
    assert (
        scenario_names == expected_names
    ), "Self-test scenario matrix drifted; update verification docs/tests if intentional."

    aggregate_job = jobs.get("summarize") or {}
    assert (
        aggregate_job.get("needs") == "scenarios"
    ), "Aggregate job must depend on the scenario matrix"
    assert (
        aggregate_job.get("if") == "${{ always() }}"
    ), "Aggregate job should always run to summarise results"

    permissions = aggregate_job.get("permissions", {})
    assert permissions.get("actions") == "read", "Aggregate job must read workflow artifacts"
    assert permissions.get("contents") == "read", "Aggregate job must read repository contents"

    env = aggregate_job.get("env", {})
    aggregate_list = env.get("SCENARIO_LIST", "")
    env_names = [name.strip() for name in aggregate_list.split(",") if name.strip()]
    assert (
        env_names == expected_names
    ), "Aggregate SCENARIO_LIST must stay aligned with the scenario matrix to keep summaries accurate."

    outputs = aggregate_job.get("outputs", {})
    assert {"summary_table", "failure_count", "run_id"}.issubset(
        outputs
    ), "Aggregate job should surface verification outputs for downstream consumers."

    steps = aggregate_job.get("steps", [])
    verify_step = next((step for step in steps if step.get("id") == "verify"), None)
    assert verify_step is not None, "Aggregate job must include the github-script verification step"
    verify_env = verify_step.get("env", {})
    assert (
        verify_env.get("PYTHON_VERSIONS") == "${{ env.REQUESTED_PYTHONS }}"
    ), "Verification step should read python version overrides from the aggregate env."


def _collect_comment_wrapper_variants(
    directory: pathlib.Path,
) -> dict[str, set[str]]:
    """Return discovered legacy wrapper names grouped by stem.

    The historical files occasionally resurfaced with a `.yaml` extension when
    copied manually.  Guard against that variant by collecting both `.yml` and
    `.yaml` matches.
    """

    variants: dict[str, set[str]] = {}
    if not directory.exists():
        return {}

    for pattern in ("*selftest*pr-comment*.yml", "*selftest*pr-comment*.yaml"):
        for path in directory.glob(pattern):
            variants.setdefault(path.stem, set()).add(path.name)
    return variants
