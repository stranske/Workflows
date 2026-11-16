"""Offline validator regressions; fixtures do not establish hosted acceptance."""

from __future__ import annotations

import json

import pytest
from tools import validate_subscription_analysis_evidence as evidence

SHA = "a" * 40
STAMP = "2026-11-16T06:00:00.1234567Z "


@pytest.fixture
def inputs():
    return {
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


def test_consistent_evidence(inputs):
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


def test_rejects_ambiguous_workflow_revisions(inputs):
    inputs["runner_log"] *= 2
    with pytest.raises(ValueError):
        evidence.validate_evidence(**inputs)


@pytest.mark.parametrize("name", list(evidence.RECEIPTS)[1:])
def test_rejects_present_api_key_flags(inputs, name):
    inputs["analysis_log"] = inputs["analysis_log"].replace(name + "=false", name + "=true")
    with pytest.raises(ValueError, match=name):
        evidence.validate_evidence(**inputs)


def test_rejects_truncated_actions_group(inputs):
    inputs["analysis_log"] += "\n" + STAMP + "##[group]truncated"
    with pytest.raises(ValueError, match="ends inside"):
        evidence.validate_evidence(**inputs)


@pytest.mark.parametrize("key", ["provider", "model"])
def test_rejects_wrong_provider_or_registry_model(inputs, key):
    inputs["analysis"][key] = "unexpected"
    with pytest.raises(ValueError):
        evidence.validate_evidence(**inputs)


@pytest.mark.parametrize("name", [*evidence.RECEIPTS, "completed-tasks-count"])
@pytest.mark.parametrize("mutation", ["missing", "contradictory", "duplicate", "script-echo"])
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
    inputs["registry"]["subscription_analysis"]["codex"] = {"model": "registry-selected-model"}
    evidence.validate_evidence(**inputs)


def test_cli_checks_files_and_does_not_echo_failed_inputs(inputs, tmp_path, capsys):
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
    assert evidence.main(args) == 0
    assert "independently verify hosted provenance and delivery" in capsys.readouterr().out
    (tmp_path / "analysis-json").write_text("do-not-echo-input", encoding="utf-8")
    assert evidence.main(args) == 1
    captured = capsys.readouterr()
    assert "failed" in captured.out
    assert "do-not-echo-input" not in captured.out + captured.err
