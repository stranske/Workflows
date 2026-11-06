"""Necessary whole inputs reach the existing native counter; prose is not a duty."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from scripts.langchain import pr_verifier as verifier

from tests.scripts.test_pr_verifier_file_chunks import Client, patch
from tests.scripts.test_verifier_evaluate_evidence_minimum import replace_inventory, run_evaluate
from tests.scripts.verifier_capacity_fakes import complete_capture_context

PARAGRAPH = (
    "These are recovered existing CI artifacts. No new coverage run, mutation run or "
    "provider assessment was performed to produce this supplement. Any subsequent "
    "acceptance decision must evaluate this explicit partial scope against the authentic "
    "request; this evidence is not itself a PASS declaration."
)


def test_descriptive_ci_artifacts_do_not_inherit_unrelated_later_mandate():
    assert verifier._required_evidence_options(PARAGRAPH) == [set()]


@pytest.mark.parametrize(
    "duty,channel",
    [
        ("Upload CI artifacts.", "artifacts"),
        ("The reviewer must upload CI artifacts.", "artifacts"),
        ("Evidence must be posted in a PR comment.", "comments"),
        ("Evidence must be included in the PR body.", "body"),
        ("- [ ] CI artifacts", "artifacts"),
    ],
)
def test_authored_duty_survives_descriptive_neighbors(duty, channel):
    assert verifier._required_evidence_options(PARAGRAPH + "\n" + duty) == [{channel}]


def test_required_single_whole_file_gets_own_chunk_and_native_count(monkeypatch):
    monkeypatch.setenv("VERIFIER_DIFF_BUDGET_TOKENS", "16000")
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    client = Client()
    monkeypatch.setattr(verifier, "_get_llm_client", lambda **_: (client, "openai"))
    large = patch("floor.json", 64816)
    result = verifier.evaluate_pr(whole_context(large), large)
    assert result.used_llm and result.verdict == "PASS"
    assert result.files_not_reviewed == []
    assert sum(large.strip() in prompt for prompt in client.prompts) == 1
    assert client.root_client.responses.input_tokens.count.call_count == len(client.prompts)


def test_native_overflow_refuses_whole_file_without_generation(monkeypatch):
    monkeypatch.setenv("VERIFIER_DIFF_BUDGET_TOKENS", "16000")
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    client = Client()
    client.root_client.responses.input_tokens.count.return_value.input_tokens = 2_000_000
    monkeypatch.setattr(verifier, "_get_llm_client", lambda **_: (client, "openai"))
    large = patch("floor.json", 64816)
    result = verifier.evaluate_pr(whole_context(large), large)
    assert not result.used_llm and result.verdict == "UNVERIFIABLE_INPUT"
    assert result.files_not_reviewed == ["floor.json"]
    assert client.prompts == []
    assert client.root_client.responses.input_tokens.count.called


def whole_context(diff):
    context = complete_capture_context()
    old = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n"
    context = context.replace(old, diff).replace("- a.py (+1/-1)", "- floor.json (+1/-1)")

    def update(inventory):
        inventory["changed_code_sources"] = [
            {
                "source": "floor.json",
                "status": "included",
                "included_chars": len(diff),
                "total_chars": len(diff),
            }
        ]
        inventory["full_diff_artifact"]["chars"] = len(diff)

    return replace_inventory(context, update)


@pytest.mark.parametrize("overflow", [False, True])
def test_real_selected_large_tables_reach_native_admission(monkeypatch, overflow):
    data = json.loads(
        subprocess.check_output(
            [
                "node",
                str(Path(__file__).parent / "fixtures/selected_baseline_collector.js"),
                "--large-selected",
            ],
            text=True,
        )
    )
    context = complete_capture_context().replace("Implement the code change.", data["body"])
    context = replace_inventory(context, lambda inv: inv.update(data["coverage"]))
    context = context.replace("## PR Diff Summary", data["evidence"] + "\n\n## PR Diff Summary")
    monkeypatch.setenv("VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS", "4000")
    monkeypatch.setenv("VERIFIER_CONTEXT_BUDGET_TOKENS", "4000")
    if overflow:
        client = Client()
        client.root_client.responses.input_tokens.count.return_value.input_tokens = 2_000_000
        monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
        monkeypatch.setattr(verifier, "_get_llm_client", lambda **_: (client, "openai"))
        result = verifier.evaluate_pr(context, data["diff"])
        assert not result.used_llm and result.verdict != "PASS"
        assert client.prompts == []
    else:
        result, client = run_evaluate(monkeypatch, context, data["diff"], "CONCERNS")
        assert result.used_llm and result.verdict == "CONCERNS"
        prompt = client.invoke.call_args.args[0]
        assert data["body"] in prompt
        assert data["tables"][0] in prompt and data["tables"][1] in prompt
        assert "OPTIONAL_COMMENT_PAYLOAD_" not in prompt
        assert "x" * 300000 not in prompt
    assert client.root_client.responses.input_tokens.count.called


@pytest.mark.parametrize("missing", ["selected_truncation", "mandatory_other_upload"])
def test_selected_capture_never_waives_missing_required_material(monkeypatch, missing):
    data = json.loads(
        subprocess.check_output(
            [
                "node",
                str(Path(__file__).parent / "fixtures/selected_baseline_collector.js"),
                "--large-selected",
                *(["--require-upload"] if missing == "mandatory_other_upload" else []),
            ],
            text=True,
        )
    )
    context = complete_capture_context().replace("Implement the code change.", data["body"])
    context = replace_inventory(context, lambda inv: inv.update(data["coverage"]))
    context = context.replace("## PR Diff Summary", data["evidence"] + "\n\n## PR Diff Summary")
    if missing == "selected_truncation":
        context = replace_inventory(
            context,
            lambda inv: next(
                row for row in inv["acceptance_evidence_sources"] if row.get("required_material")
            ).update(status="truncated", total_chars=None),
        )
    monkeypatch.setenv("VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS", "4000")
    result, client = run_evaluate(monkeypatch, context, data["diff"])
    assert not result.used_llm and result.verdict == "UNVERIFIABLE_INPUT"
    client.invoke.assert_not_called()


def test_newly_oversized_legacy_unit_without_native_facts_never_generates(monkeypatch):
    monkeypatch.setenv("VERIFIER_DIFF_BUDGET_TOKENS", "16000")
    monkeypatch.setattr(verifier, "_prepare_capacity_client", lambda client: client)
    monkeypatch.setattr(verifier, "_legacy_capacity_route", lambda client: True)
    client = SimpleNamespace(invoke=mock.Mock())
    large = patch("floor.json", 64816)
    context = whole_context(large)
    prompt = verifier._prepare_prompt(context, large)
    with pytest.raises(verifier.InputCapacityError):
        verifier._invoke_llm(
            client, prompt, operation="evaluate_pr_chunk", context=context, diff=large
        )
    client.invoke.assert_not_called()


def test_ordinary_legacy_transport_remains_unchanged(monkeypatch):
    monkeypatch.setattr(verifier, "_prepare_capacity_client", lambda client: client)
    monkeypatch.setattr(verifier, "_legacy_capacity_route", lambda client: True)
    client = SimpleNamespace(
        invoke=mock.Mock(return_value=SimpleNamespace(content="ordinary response"))
    )
    small = patch("floor.json", 500)
    context = whole_context(small)
    prompt = verifier._prepare_prompt(context, small)
    verifier._invoke_llm(client, prompt, operation="evaluate_pr_chunk", context=context, diff=small)
    client.invoke.assert_called_once()


@pytest.mark.parametrize("route", ["native", "overflow", "legacy_unavailable"])
def test_gzip_view_size_not_binary_descriptor_controls_native_minimum(tmp_path, monkeypatch, route):
    from tests.tools.test_verifier_gzip_assets import IDENTITY, asset

    monkeypatch.setenv("VERIFIER_EVIDENCE_CAPTURE_DIR", str(tmp_path))
    monkeypatch.setenv("VERIFIER_DIFF_BUDGET_TOKENS", "16000")
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    monkeypatch.setenv("VERIFIER_SEMANTIC_MODE", "0")
    raw_patch, inventory, _ = asset(
        tmp_path, text="EXACT_ASSET_START\n" + "x" * 65000 + "\nEXACT_ASSET_END"
    )
    assert len(raw_patch) < 64000
    inventory["acceptance_source_discovery"] = {"required": False, "status": "included"}
    inventory["full_diff_artifact"] = {
        "source": "verifier-pr-diff.patch",
        "status": "included",
        "chars": len(raw_patch),
    }
    context = (
        IDENTITY
        + "## Context source coverage\n```json\n"
        + json.dumps(inventory)
        + "\n```\n\n## CI Information\nNo failures.\n\n## Plan sources (scope, tasks, acceptance)\n#### Acceptance criteria\n- Review the supplied evidence asset.\n"
    )
    if route == "legacy_unavailable":
        client = SimpleNamespace(invoke=mock.Mock())
        monkeypatch.setattr(verifier, "_prepare_capacity_client", lambda value: value)
        monkeypatch.setattr(verifier, "_legacy_capacity_route", lambda value: True)
    else:
        client = Client()
        if route == "overflow":
            client.root_client.responses.input_tokens.count.return_value.input_tokens = 2_000_000
    monkeypatch.setattr(verifier, "_get_llm_client", lambda **_: (client, "openai"))
    monkeypatch.setattr(verifier, "_get_llm_clients", lambda *args: [])
    result = verifier.evaluate_pr(context, raw_patch.decode(), provider="openai")
    if route == "native":
        assert result.used_llm and result.verdict == "PASS"
        assert result.files_not_reviewed == []
        assert any(
            "EXACT_ASSET_START" in prompt and "EXACT_ASSET_END" in prompt
            for prompt in client.prompts
        )
        assert client.root_client.responses.input_tokens.count.called
    elif route == "overflow":
        assert not result.used_llm and result.files_not_reviewed
        assert client.prompts == []
        assert client.root_client.responses.input_tokens.count.called
    else:
        assert not result.used_llm and result.files_not_reviewed
        client.invoke.assert_not_called()


@pytest.mark.parametrize("example", ["e.g.", "i.e.", "U.S.", "the U.S.", "E.U.", "Dr.", "A."])
def test_abbreviation_period_is_not_an_evidence_governor_boundary(example):
    assert verifier._required_evidence_options(
        f"The reviewer must upload {example} CI artifacts."
    ) == [{"artifacts"}]


@pytest.mark.parametrize("example", ["e.g.", "U.S."])
def test_abbreviation_preserves_negative_and_product_scope(example):
    assert verifier._required_evidence_options(
        f"The reviewer must not upload {example} CI artifacts."
    ) == [set()]
    assert verifier._required_evidence_options(f"The UI must display {example} CI artifacts.") == [
        set()
    ]


@pytest.mark.parametrize("member", ["`pkg.Type.member`", "https://example.test/file.json"])
def test_member_literal_and_url_periods_preserve_real_delivery(member):
    assert verifier._required_evidence_options(
        f"The reviewer must upload {member} CI artifacts."
    ) == [{"artifacts"}]


def selected_tables_capture():
    data = json.loads(
        subprocess.check_output(
            [
                "node",
                str(Path(__file__).parent / "fixtures/selected_baseline_collector.js"),
                "--large-selected",
            ],
            text=True,
        )
    )
    context = complete_capture_context().replace("Implement the code change.", data["body"])
    context = replace_inventory(context, lambda inv: inv.update(data["coverage"]))
    return context.replace("## PR Diff Summary", data["evidence"] + "\n\n## PR Diff Summary"), data


def test_large_selected_required_proof_cannot_use_uncounted_legacy_route(monkeypatch):
    context, data = selected_tables_capture()
    monkeypatch.setenv("VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS", "4000")
    monkeypatch.setattr(verifier, "_prepare_capacity_client", lambda client: client)
    monkeypatch.setattr(verifier, "_legacy_capacity_route", lambda client: True)
    client = SimpleNamespace(invoke=mock.Mock())
    inputs = verifier.build_prompt_inputs(context, data["diff"])
    assert inputs.coverage.code_included_chars < 64000
    prompt = verifier._prepare_prompt(context, data["diff"])
    with pytest.raises(verifier.InputCapacityError):
        verifier._invoke_llm(
            client, prompt, operation="evaluate_pr", context=context, diff=data["diff"]
        )
    client.invoke.assert_not_called()
    assert inputs.required_evidence_chars > 40000


def test_omitted_optional_history_does_not_require_native_for_ordinary_legacy(monkeypatch):
    from tests.scripts.test_verifier_evaluate_evidence_minimum import large_optional_capture

    monkeypatch.setenv("VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS", "4000")
    context, diff = large_optional_capture("Evidence must be posted in a PR comment.")
    assert len(context) > 40000
    monkeypatch.setattr(verifier, "_prepare_capacity_client", lambda client: client)
    monkeypatch.setattr(verifier, "_legacy_capacity_route", lambda client: True)
    monkeypatch.setattr(
        verifier,
        "_preflight_input_capacity",
        lambda *args, **kwargs: pytest.fail(
            "Optional omitted chatter is not a native admission prerequisite"
        ),
    )
    client = SimpleNamespace(
        invoke=mock.Mock(return_value=SimpleNamespace(content="ordinary response"))
    )
    inputs = verifier.build_prompt_inputs(context, diff)
    assert inputs.required_evidence_chars < 16000
    prompt = verifier._prepare_prompt(context, diff)
    assert "COMMENT_PROOF_COMPLETE" in prompt and "OPTIONAL_ARTIFACT_PAYLOAD_" not in prompt
    verifier._invoke_llm(client, prompt, operation="evaluate_pr", context=context, diff=diff)
    client.invoke.assert_called_once()
