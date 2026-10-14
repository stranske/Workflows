"""Execute authored verifier shells: expanded PASS needs every configured judge."""

import copy
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from tools.llm_registry import resolve_slots

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/reusable-agents-verifier.yml"


def _arms():
    return [
        {
            "provider_used": slot.provider,
            "model": slot.model,
            "used_llm": True,
            "verdict": "PASS",
            "error": None,
        }
        for slot in resolve_slots()[:2]
    ]


def _render(text, values):
    return re.sub(r"\$\{\{\s*(.*?)\s*\}\}", lambda match: values.get(match[1], ""), text)


def run_workflow(
    tmp_path,
    payload,
    *,
    profile="expanded",
    mode="compare",
    ci_failed="false",
    model="",
    model2="",
    raw=None,
    slot_config=None,
):
    """Stub only provider CLI output; execute full production parser + unified shell."""
    workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    job = workflow["jobs"]["verifier"]
    step = next(s for s in job["steps"] if s.get("id") == f"llm_{mode}")
    selected = next(
        s for s in job["steps"] if s.get("name") == "Select bounded verifier evidence profile"
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("LANGCHAIN_", "LANGSMITH_", "VERIFIER_"))
    }
    for key in ["OPENAI_API_KEY", "CLAUDE_API_STRANSKE", "GITHUB_TOKEN", "GH_TOKEN"]:
        env.pop(key, None)
    values = {
        "inputs.evidence_profile": profile,
        "inputs.mode": mode,
        "inputs.model": model,
        "inputs.model2": model2,
        "inputs.provider": "auto",
    }
    env.update({k: _render(v, values) for k, v in job.get("env", {}).items()})
    if slot_config is not None:
        config = tmp_path / "slots.json"
        config.write_text(json.dumps({"slots": slot_config}))
        env["LANGCHAIN_SLOT_CONFIG"] = str(config)
    env["GITHUB_ENV"] = str(tmp_path / "env")
    result = subprocess.run(
        ["bash", "-c", selected["run"]],
        env={**env, **{k: _render(v, values) for k, v in selected.get("env", {}).items()}},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    if Path(env["GITHUB_ENV"]).exists():
        env.update(line.split("=", 1) for line in Path(env["GITHUB_ENV"]).read_text().splitlines())
    (tmp_path / ".workflows-lib").symlink_to(ROOT, target_is_directory=True)
    fixture = tmp_path / "provider-output.json"
    fixture.write_text(json.dumps(payload) if raw is None else raw)
    binary = tmp_path / "python"
    binary.write_text(f"#!/bin/sh\ncat {shlex.quote(str(fixture))}\n")
    binary.chmod(0o755)
    (tmp_path / "python3").symlink_to(sys.executable)
    env["PATH"] = str(tmp_path) + os.pathsep + env["PATH"]
    env.update({k: _render(v, values) for k, v in step["env"].items()})
    env["GITHUB_OUTPUT"] = str(tmp_path / "output")
    result = subprocess.run(
        ["bash", "-c", _render(step["run"], values)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    outputs = dict(
        line.split("=", 1) for line in Path(env["GITHUB_OUTPUT"]).read_text().splitlines()
    )
    unified = next(s for s in job["steps"] if s.get("id") == "unified_verdict")
    values.update(
        {
            f"steps.llm_{mode}.outputs.verdict": outputs.get("verdict", ""),
            "steps.context.outputs.ci_failed": ci_failed,
        }
    )
    env.update({k: _render(v, values) for k, v in unified["env"].items()})
    env["GITHUB_OUTPUT"] = str(tmp_path / "unified-output")
    result = subprocess.run(
        ["bash", "-c", _render(unified["run"], values)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    outputs["unified"] = Path(env["GITHUB_OUTPUT"]).read_text().strip().split("=", 1)[1]
    return outputs


@pytest.mark.parametrize("provider_index", [0, 1], ids=["openai", "anthropic"])
@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "used-false",
        "used-false-pass",
        "CONCERNS",
        "FAIL",
        "UNKNOWN",
        "error-verdict",
        "native-count-error",
        "unsupported-fallback",
        "malformed",
        "empty-arm",
        "no-verdict",
        "no-provider",
        "no-model",
        "used-string",
        "used-int",
        "malformed-scores",
        "wrong-model",
    ],
)
def test_expanded_each_arm_blocks_pass(tmp_path, provider_index, case):
    arms = _arms()
    arm = arms[provider_index]
    if case == "missing":
        arms.pop(provider_index)
    elif case in {"used-false", "used-false-pass"}:
        arm.update(used_llm=False, verdict="CONCERNS" if case == "used-false" else "PASS")
    elif case in {"CONCERNS", "FAIL", "UNKNOWN", "error-verdict"}:
        arm["verdict"] = "ERROR" if case == "error-verdict" else case
    elif case == "native-count-error":
        arm["error"] = "native capacity/count unavailable"
    elif case == "unsupported-fallback":
        arm["provider_used"] = "github-models"
    elif case == "malformed":
        arms[provider_index] = None
    elif case == "empty-arm":
        arms[provider_index] = {}
    elif case.startswith("no-"):
        arm.pop(
            {"no-verdict": "verdict", "no-provider": "provider_used", "no-model": "model"}[case]
        )
    elif case.startswith("used-"):
        arm["used_llm"] = "true" if case == "used-string" else 1
    elif case == "malformed-scores":
        arm["scores"] = "PASS"
    elif case == "wrong-model":
        arm["model"] = "unexpected-model"
    outputs = run_workflow(tmp_path, {"results": arms})
    assert outputs["verdict"] == "CONCERNS", outputs
    assert outputs["unified"] == "CONCERNS", outputs


@pytest.mark.parametrize(
    "case",
    ["empty", "null", "object", "duplicate", "extra", "wrong-provider", "outer-list", "outer-null"],
)
def test_expanded_rejects_incomplete_or_malformed_comparison(tmp_path, case):
    arms = _arms()
    payload = {"results": arms}
    if case in {"empty", "null", "object"}:
        payload["results"] = {"empty": [], "null": None, "object": {}}[case]
    elif case == "duplicate":
        arms[1] = copy.deepcopy(arms[0])
    elif case == "extra":
        arms.append(copy.deepcopy(arms[0]))
    elif case == "wrong-provider":
        arms[1]["provider_used"] = "unknown"
    else:
        payload = [] if case == "outer-list" else None
    outputs = run_workflow(tmp_path, payload)
    assert outputs["verdict"] == outputs["unified"] == "CONCERNS"


@pytest.mark.parametrize("raw", ["", "{broken json"])
def test_expanded_empty_or_invalid_json_stays_nonpass(tmp_path, raw):
    outputs = run_workflow(tmp_path, None, raw=raw)
    assert outputs["verdict"] == outputs["unified"] == "CONCERNS"
    assert outputs["has_results"] == "false"


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("ci_failed", ["false", "true"])
def test_expanded_all_configured_pass_retains_ci_floor(tmp_path, reverse, ci_failed):
    arms = _arms()[::-1] if reverse else _arms()
    outputs = run_workflow(tmp_path, {"results": arms}, ci_failed=ci_failed)
    assert outputs["verdict"] == "PASS"
    assert outputs["has_results"] == "true"
    assert outputs["unified"] == ("concerns" if ci_failed == "true" else "PASS")


@pytest.mark.parametrize(
    "case, expected",
    [("one-unused", "PASS"), ("missing", "PASS"), ("all-unused", "PASS"), ("concerns", "CONCERNS")],
)
def test_standard_preserves_legacy_aggregation(tmp_path, case, expected):
    arms = _arms()
    if case in {"one-unused", "all-unused"}:
        arms[0].update(used_llm=False, verdict="CONCERNS" if case == "one-unused" else "PASS")
    if case == "all-unused":
        arms[1]["used_llm"] = False
    if case == "missing":
        arms.pop()
    if case == "concerns":
        arms[0]["verdict"] = "CONCERNS"
    outputs = run_workflow(tmp_path, {"results": arms}, profile="standard")
    assert outputs["verdict"] == outputs["unified"] == expected


@pytest.mark.parametrize("provider_index", [0, 1], ids=["openai", "anthropic"])
@pytest.mark.parametrize("mode", ["evaluate", "compare"])
def test_source_capacity_failure_reaches_unified_nonpass(
    tmp_path, monkeypatch, provider_index, mode
):
    from types import SimpleNamespace

    from scripts.langchain import pr_verifier

    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    arms = _arms()
    clients = [(object(), arm["provider_used"], arm["model"]) for arm in arms]
    failed_provider = arms[provider_index]["provider_used"]
    response = json.dumps({"verdict": "PASS", "summary": "offline success"})

    def invoke(client, *args, **kwargs):
        if client is clients[provider_index][0]:
            raise pr_verifier.InputCapacityError("native capacity/count unavailable")
        return SimpleNamespace(content=response), None, None

    monkeypatch.setattr(pr_verifier, "_invoke_llm", invoke)
    diff = "diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-old\n+new\n"
    if mode == "compare":
        monkeypatch.setattr(pr_verifier, "_get_llm_clients", lambda *args: clients)
        results = pr_verifier.evaluate_pr_multiple("Review changed code.", diff)
        assert results[provider_index].provider_used == failed_provider
        assert not results[provider_index].used_llm
        assert results[1 - provider_index].verdict == "PASS"
        payload = {"results": [result.model_dump() for result in results]}
    else:
        monkeypatch.setattr(
            pr_verifier, "_get_llm_client", lambda **kwargs: clients[provider_index][:2]
        )
        payload = pr_verifier.evaluate_pr(
            "Review changed code.", diff, provider=failed_provider
        ).model_dump()
        assert not payload["used_llm"]
    outputs = run_workflow(tmp_path, payload, mode=mode)
    assert outputs["verdict"] == outputs["unified"] == "CONCERNS"


@pytest.mark.parametrize("models", [("first-override", "second-override"), ("both-override", "")])
def test_expanded_uses_literal_invocation_model_overrides(tmp_path, models):
    arms = _arms()
    arms[0]["model"] = models[0]
    arms[1]["model"] = models[1] or models[0]
    outputs = run_workflow(tmp_path, {"results": arms}, model=models[0], model2=models[1])
    assert outputs["verdict"] == outputs["unified"] == "PASS"


@pytest.mark.parametrize(
    "case", ["single-slot", "duplicate-family", "missing-configured-judge", "reordered"]
)
def test_expanded_expected_arms_come_from_configuration(tmp_path, case):
    arms = _arms()
    slots = [{"provider": arm["provider_used"], "model": arm["model"]} for arm in arms]
    expected = "CONCERNS"
    if case == "single-slot":
        slots.pop()
    elif case == "duplicate-family":
        slots[1] = copy.deepcopy(slots[0])
    elif case == "missing-configured-judge":
        # Availability must not replace configured slot 2 with fallback slot 3.
        slots.append({"provider": "github-models", "model": "gpt-5.4"})
        arms[1].update(provider_used="github-models", model="gpt-5.4")
    else:
        slots.reverse()
        expected = "PASS"
    outputs = run_workflow(tmp_path, {"results": arms}, slot_config=slots)
    assert outputs["verdict"] == outputs["unified"] == expected


@pytest.mark.parametrize("mode", ["evaluate", "compare"])
@pytest.mark.parametrize("gap", ["code", "evidence"])
def test_source_coverage_floor_survives_workflow_aggregation(tmp_path, monkeypatch, mode, gap):
    from types import SimpleNamespace

    from scripts.langchain import pr_verifier

    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    arms = _arms()
    clients = [(object(), arm["provider_used"], arm["model"]) for arm in arms]
    monkeypatch.setattr(
        pr_verifier,
        "_invoke_llm",
        lambda *args, **kwargs: (SimpleNamespace(content='{"verdict":"PASS"}'), None, None),
    )
    context = "Review changed code."
    diff = "diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-old\n+new\n"
    if gap == "code":
        diff = None
    else:
        from tests.scripts.test_pr_verifier_prompt_coverage import ACCEPTANCE_SENTINEL, _context

        context, _ = _context(1, 1000, 500)
        context = context.replace(
            ACCEPTANCE_SENTINEL,
            "required evidence artifact: a failing and restored passing transcript",
        ).replace(
            "## PR Diff Summary",
            "## Acceptance evidence\n\n"
            "- Overall retrieval status: **unavailable**\n"
            "- Referenced workflow artifacts: **unavailable**\n\n"
            "## PR Diff Summary",
        )
    if mode == "compare":
        monkeypatch.setattr(pr_verifier, "_get_llm_clients", lambda *args: clients)
        results = pr_verifier.evaluate_pr_multiple(context, diff)
        assert all(result.verdict == "CONCERNS" for result in results)
        payload = {"results": [result.model_dump() for result in results]}
    else:
        monkeypatch.setattr(pr_verifier, "_get_llm_client", lambda **kwargs: clients[0][:2])
        payload = pr_verifier.evaluate_pr(
            context, diff, provider=arms[0]["provider_used"]
        ).model_dump()
        assert payload["verdict"] == "CONCERNS"
    outputs = run_workflow(tmp_path, payload, mode=mode)
    assert outputs["verdict"] == outputs["unified"] == "CONCERNS"


@pytest.mark.parametrize("ci_failed", ["false", "true"])
def test_evaluate_pass_and_ci_floor_preserved(tmp_path, ci_failed):
    outputs = run_workflow(tmp_path, _arms()[0], mode="evaluate", ci_failed=ci_failed)
    assert outputs["verdict"] == "PASS"
    assert outputs["unified"] == ("concerns" if ci_failed == "true" else "PASS")
