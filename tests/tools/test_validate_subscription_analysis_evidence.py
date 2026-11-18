"""Offline validator regressions; fixtures do not establish hosted acceptance."""

from __future__ import annotations

import json

import pytest
from tools import validate_subscription_analysis_evidence as evidence

SHA = "a" * 40
STAMP = "2026-11-16T06:00:00.1234567Z "


@pytest.fixture
def inputs():
    values = {
        "delivered_sha": SHA,
        "runner_log": f"{STAMP}Uses: {evidence.WORKFLOW}@refs/heads/main ({SHA})\n",
        "analysis_log": "\n".join(
            STAMP + line
            for line in (
                "subscription-auth=chatgpt",
                "OPENAI_API_KEY-present=false",
                "ANTHROPIC_API_KEY-present=false",
                "completed-tasks-count=1",
            )
        ),
        "analysis": {
            "provider": "codex",
            "model": "registry-selected-model",
            "confidence": 0.91,
            "completed_tasks": ["A completed task"],
        },
        "summary": {
            "llm-analysis-run": "true",
            "llm-provider": "codex",
            "llm-model": "registry-selected-model",
            "llm-confidence": "0.91",
            "llm-completed-tasks": '["A completed task"]',
        },
        "registry": {
            "subscription_analysis": {"codex": {"execution_profile": "codex-extract"}},
            "execution_profiles": {"codex-extract": {"model": "registry-selected-model"}},
        },
    }
    values["runner_log"] += values["analysis_log"] + "\n"
    return values


def test_consistent_evidence(inputs):
    evidence.validate_evidence(**inputs)


@pytest.mark.parametrize("name", [*evidence.RECEIPTS, "completed-tasks-count"])
@pytest.mark.parametrize(
    "logs", [("analysis_log",), ("runner_log",), ("analysis_log", "runner_log")]
)
def test_required_receipts_need_timestamps_in_each_log(inputs, name, logs):
    for log in logs:
        inputs[log] = inputs[log].replace(STAMP + name + "=", name + "=")
    with pytest.raises(ValueError, match="timestamp"):
        evidence.validate_evidence(**inputs)


def test_rejects_timestamps_removed_from_both_logs(inputs):
    for log in ("analysis_log", "runner_log"):
        inputs[log] = inputs[log].replace(STAMP, "")
    with pytest.raises(ValueError, match="timestamp"):
        evidence.validate_evidence(**inputs)


def test_accepts_sha_only_workflow_revision(inputs):
    inputs["runner_log"] = (
        f"{STAMP}Uses: {evidence.WORKFLOW}@{SHA}\n" + inputs["analysis_log"] + "\n"
    )
    evidence.validate_evidence(**inputs)


@pytest.mark.parametrize("name", [*evidence.RECEIPTS, "completed-tasks-count"])
@pytest.mark.parametrize(
    "mutation", ["missing", "conflicting", "other-round", "script-echo", "duplicate", "extra"]
)
def test_analysis_receipts_must_appear_in_runner_runtime_log(inputs, name, mutation):
    lines = inputs["runner_log"].splitlines()
    receipt = next(line for line in lines if line.startswith(STAMP + name + "="))
    index = lines.index(receipt)
    if mutation == "missing":
        del lines[index]
    elif mutation == "conflicting":
        lines[index] = STAMP + name + "=unexpected"
    elif mutation == "other-round":
        lines[index] = receipt.replace("T06:00:00", "T07:00:00")
    elif mutation == "duplicate":
        lines.append(receipt)
    elif mutation == "extra":
        lines.append(STAMP + name + "=unexpected")
    else:
        lines[index : index + 1] = [
            STAMP + "##[group]Run script",
            receipt,
            STAMP + "##[endgroup]",
        ]
    inputs["runner_log"] = "\n".join(lines)
    with pytest.raises(ValueError, match="runner log"):
        evidence.validate_evidence(**inputs)


def test_analysis_receipt_binding_accepts_runner_crlf_line_endings(inputs):
    inputs["runner_log"] = inputs["runner_log"].replace("\n", "\r\n")
    evidence.validate_evidence(**inputs)


@pytest.mark.parametrize("revision", [SHA, "b" * 40])
def test_rejects_duplicate_or_conflicting_revisions_across_runner_formats(inputs, revision):
    inputs["runner_log"] += f"{STAMP}Uses: {evidence.WORKFLOW}@{revision}\n"
    with pytest.raises(ValueError, match="revision"):
        evidence.validate_evidence(**inputs)


@pytest.mark.parametrize(
    "reference",
    [
        "refs/heads/main",
        SHA[:7],
        "b" * 40,
        SHA + ")",
        f"refs/heads/main ({SHA}",
        f"refs/heads/main {SHA})",
        f"refs/heads/main ({SHA}) extra",
    ],
)
def test_rejects_unresolved_or_malformed_workflow_reference(inputs, reference):
    inputs["runner_log"] = f"{STAMP}Uses: {evidence.WORKFLOW}@{reference}\n"
    with pytest.raises(ValueError, match="revision"):
        evidence.validate_evidence(**inputs)


@pytest.mark.parametrize("nested", [False, True])
def test_grouped_sha_only_reference_is_not_workflow_revision_evidence(inputs, nested):
    inputs["runner_log"] = (
        f"{STAMP}##[group]Run script\n"
        + (f"{STAMP}##[group]nested script text\n{STAMP}##[endgroup]\n" if nested else "")
        + f"{STAMP}Uses: {evidence.WORKFLOW}@{SHA}\n"
        + f"{STAMP}##[endgroup]\n"
    )
    with pytest.raises(ValueError, match="revision"):
        evidence.validate_evidence(**inputs)


@pytest.mark.parametrize(
    "output", ["analysis-run", "provider", "model", "confidence", "completed-tasks"]
)
@pytest.mark.parametrize("prefix", ["", "##[warning]"])
@pytest.mark.parametrize("empty_tasks", [False, True])
def test_rejects_suppressed_outputs_even_when_summary_fallback_matches(
    inputs, output, prefix, empty_tasks
):
    if empty_tasks:
        inputs["analysis"]["completed_tasks"] = []
        inputs["summary"]["llm-completed-tasks"] = "[]"
        inputs["analysis_log"] = inputs["analysis_log"].replace("tasks-count=1", "tasks-count=0")
    inputs["runner_log"] += (
        f"{STAMP}##[group]Set outputs\n"
        f"{STAMP}{prefix}Skip output 'llm-{output}' since it may contain secret.\n"
        f"{STAMP}##[endgroup]\n"
    )
    with pytest.raises(ValueError, match="suppressed"):
        evidence.validate_evidence(**inputs)


@pytest.mark.parametrize(
    "line",
    [
        "Skip output 'unrelated-output' since it may contain secret.",
        "echo \"Skip output 'llm-completed-tasks' since it may contain secret.\"",
    ],
)
def test_unrelated_suppression_or_script_echo_does_not_invalidate_outputs(inputs, line):
    inputs["runner_log"] += STAMP + line + "\n"
    evidence.validate_evidence(**inputs)


@pytest.mark.parametrize("value", ["", "a" * 7, "b" * 40])
def test_rejects_missing_short_or_different_revision(inputs, value):
    inputs["delivered_sha"] = value
    with pytest.raises(ValueError):
        evidence.validate_evidence(**inputs)


def test_script_echo_is_not_workflow_revision_evidence(inputs):
    inputs["runner_log"] = inputs["runner_log"].replace("Uses:", "echo Uses:")
    with pytest.raises(ValueError):
        evidence.validate_evidence(**inputs)


@pytest.mark.parametrize("nested", [False, True])
def test_grouped_script_text_is_not_workflow_revision_evidence(inputs, nested):
    revision = inputs["runner_log"]
    opening = STAMP + "##[group]Run script\n"
    closing = STAMP + "##[endgroup]\n"
    if nested:
        opening += STAMP + "##[group]nested script text\n" + closing
    inputs["runner_log"] = opening + revision + closing
    with pytest.raises(ValueError, match="revision"):
        evidence.validate_evidence(**inputs)


@pytest.mark.parametrize("echoed_sha", [SHA, "b" * 40])
def test_runtime_workflow_revision_is_not_obscured_by_script_text(inputs, echoed_sha):
    inputs["runner_log"] += (
        STAMP
        + "##[group]Run script\n"
        + f"{STAMP}Uses: {evidence.WORKFLOW}@refs/heads/main ({echoed_sha})\n"
        + STAMP
        + "##[endgroup]\n"
    )
    evidence.validate_evidence(**inputs)


@pytest.mark.parametrize(
    "markers",
    [
        ["##[group]truncated"],
        ["##[group]outer", "##[group]inner", "##[endgroup]"],
        ["##[endgroup]"],
    ],
)
def test_rejects_unbalanced_runner_log_groups(inputs, markers):
    inputs["runner_log"] += "\n".join(STAMP + marker for marker in markers)
    with pytest.raises(ValueError, match="group"):
        evidence.validate_evidence(**inputs)


def test_rejects_ambiguous_workflow_revisions(inputs):
    inputs["runner_log"] *= 2
    with pytest.raises(ValueError):
        evidence.validate_evidence(**inputs)


@pytest.mark.parametrize("name", list(evidence.RECEIPTS)[1:])
def test_rejects_present_api_key_flags(inputs, name):
    inputs["analysis_log"] = inputs["analysis_log"].replace(name + "=false", name + "=true")
    with pytest.raises(ValueError, match=name):
        evidence.validate_evidence(**inputs)


@pytest.mark.parametrize(
    "group_lines",
    [
        ["##[group]truncated"],
        ["##[group]outer", "##[group]inner", "##[endgroup]"],
    ],
)
def test_rejects_truncated_actions_group(inputs, group_lines):
    inputs["analysis_log"] += "\n" + "\n".join(STAMP + line for line in group_lines)
    with pytest.raises(ValueError, match="ends inside"):
        evidence.validate_evidence(**inputs)


@pytest.mark.parametrize("position", ["before", "after"])
def test_rejects_unmatched_actions_group_end(inputs, position):
    terminator = STAMP + "##[endgroup]"
    parts = [terminator, inputs["analysis_log"]]
    inputs["analysis_log"] = "\n".join(parts if position == "before" else reversed(parts))
    with pytest.raises(ValueError, match="unmatched"):
        evidence.validate_evidence(**inputs)


def test_balanced_nested_groups_do_not_hide_subsequent_runtime_receipts(inputs):
    inputs["analysis_log"] = (
        "\n".join(
            STAMP + line
            for line in (
                "##[group]Run script",
                "##[group]nested script text",
                "subscription-auth=not-runtime",
                "##[endgroup]",
                "OPENAI_API_KEY-present=not-runtime",
                "##[endgroup]",
            )
        )
        + "\n"
        + inputs["analysis_log"]
    )
    evidence.validate_evidence(**inputs)


@pytest.mark.parametrize("key", ["provider", "model"])
def test_rejects_wrong_provider_or_registry_model(inputs, key):
    inputs["analysis"][key] = "unexpected"
    with pytest.raises(ValueError):
        evidence.validate_evidence(**inputs)


@pytest.mark.parametrize("name", [*evidence.RECEIPTS, "completed-tasks-count"])
@pytest.mark.parametrize(
    "mutation", ["missing", "contradictory", "duplicate", "script-echo", "nested-script-echo"]
)
def test_rejects_missing_conflicting_or_echoed_receipts(inputs, name, mutation):
    lines = inputs["analysis_log"].splitlines()
    receipt = next(line for line in lines if line.startswith(STAMP + name + "="))
    lines.remove(receipt)
    if mutation == "contradictory":
        lines += [receipt, STAMP + name + "=unexpected"]
    elif mutation == "duplicate":
        lines += [receipt, receipt]
    elif mutation == "script-echo":
        lines += [STAMP + "##[group]Run script", receipt, STAMP + "##[endgroup]"]
    elif mutation == "nested-script-echo":
        lines += [
            STAMP + "##[group]Run script",
            STAMP + "##[group]nested script text",
            STAMP + "##[endgroup]",
            receipt,
            STAMP + "##[endgroup]",
        ]
    inputs["analysis_log"] = "\n".join(lines)
    with pytest.raises(ValueError, match=name):
        evidence.validate_evidence(**inputs)


@pytest.mark.parametrize("key", ["provider", "model", "confidence", "completed_tasks"])
def test_rejects_missing_analysis_fields(inputs, key):
    del inputs["analysis"][key]
    with pytest.raises(ValueError):
        evidence.validate_evidence(**inputs)


@pytest.mark.parametrize(
    "key", ["provider", "model", "confidence", "completed-tasks", "analysis-run"]
)
@pytest.mark.parametrize("value", [None, "", "mismatched"])
def test_rejects_missing_suppressed_or_mismatched_summary_outputs(inputs, key, value):
    if value is None:
        del inputs["summary"]["llm-" + key]
    else:
        inputs["summary"]["llm-" + key] = value
    with pytest.raises(ValueError):
        evidence.validate_evidence(**inputs)


@pytest.mark.parametrize("confidence", [True, "0.91", -1, 2, float("nan"), float("inf")])
def test_rejects_invalid_confidence(inputs, confidence):
    inputs["analysis"]["confidence"] = confidence
    with pytest.raises(ValueError):
        evidence.validate_evidence(**inputs)


def test_zero_tasks_and_confidence_are_valid_and_model_is_registry_driven(inputs):
    inputs["analysis"].update(confidence=0, completed_tasks=[])
    inputs["summary"].update({"llm-confidence": "0", "llm-completed-tasks": "[]"})
    inputs["analysis_log"] = inputs["analysis_log"].replace("tasks-count=1", "tasks-count=0")
    inputs["runner_log"] = inputs["runner_log"].replace("tasks-count=1", "tasks-count=0")
    inputs["registry"]["subscription_analysis"]["codex"] = {"model": "registry-selected-model"}
    evidence.validate_evidence(**inputs)


@pytest.fixture
def evidence_args(inputs, tmp_path):
    args = ["--delivered-sha", SHA]
    for option, key in (
        ("runner-log", "runner_log"),
        ("analysis-log", "analysis_log"),
        ("analysis-json", "analysis"),
        ("summary-json", "summary"),
        ("registry", "registry"),
    ):
        path = tmp_path / option
        value = inputs[key]
        path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
        args += ["--" + option, str(path)]
    return args


def test_cli_checks_files_and_does_not_echo_failed_inputs(evidence_args, tmp_path, capsys):
    args = evidence_args
    assert evidence.main(args) == 0
    assert "independently verify hosted provenance and delivery" in capsys.readouterr().out
    (tmp_path / "analysis-json").write_text("do-not-echo-input", encoding="utf-8")
    assert evidence.main(args) == 1
    captured = capsys.readouterr()
    assert "failed" in captured.out
    assert "do-not-echo-input" not in captured.out + captured.err


def test_cli_rejects_receipts_from_other_runner_without_echoing_logs(
    evidence_args, tmp_path, capsys
):
    runner = tmp_path / "runner-log"
    runner.write_text(
        runner.read_text().replace("T06:00:00", "T07:00:00") + "\ndo-not-echo-runner-data\n",
        encoding="utf-8",
    )
    assert evidence.main(evidence_args) == 1
    captured = capsys.readouterr()
    assert "failed" in captured.out
    assert "do-not-echo-runner-data" not in captured.out + captured.err


@pytest.mark.parametrize(
    "option,key",
    [("analysis-json", key) for key in ("provider", "model", "confidence", "completed_tasks")]
    + [
        ("summary-json", "llm-" + key)
        for key in ("analysis-run", "provider", "model", "confidence", "completed-tasks")
    ],
)
@pytest.mark.parametrize("conflicting", [False, True])
def test_cli_rejects_duplicate_json_fields(
    evidence_args, tmp_path, capsys, option, key, conflicting
):
    path = tmp_path / option
    original = path.read_text(encoding="utf-8")
    value = "do-not-echo-duplicate" if conflicting else json.loads(original)[key]
    path.write_text("{" + json.dumps(key) + ":" + json.dumps(value) + "," + original[1:])

    assert evidence.main(evidence_args) == 1
    captured = capsys.readouterr()
    assert "failed" in captured.out
    assert "do-not-echo-duplicate" not in captured.out + captured.err


@pytest.mark.parametrize(
    "registry",
    [
        """subscription_analysis: {}
subscription_analysis:
  codex:
    model: registry-selected-model
""",
        """subscription_analysis:
  codex: {}
  codex:
    model: registry-selected-model
""",
        """subscription_analysis:
  codex:
    model: do-not-echo-duplicate
    model: registry-selected-model
""",
        """subscription_analysis:
  codex:
    execution_profile: codex-extract
execution_profiles:
  codex-extract:
    model: do-not-echo-duplicate
    model: registry-selected-model
""",
    ],
)
def test_cli_rejects_duplicate_registry_keys(evidence_args, tmp_path, capsys, registry):
    (tmp_path / "registry").write_text(registry, encoding="utf-8")
    assert evidence.main(evidence_args) == 1
    captured = capsys.readouterr()
    assert captured.out == "Evidence consistency check failed: incomplete or mismatched inputs\n"
    assert captured.err == ""
