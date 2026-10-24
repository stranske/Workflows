"""Grouped chunk-boundary regressions from retained #683/#703/#4048/#4069 reports.

The seven-case capture retains flattened results, not original chunk responses.
These offline responses reproduce the observed scope contradictions; they are
not represented as replays of provider generations or new acceptance verdicts.
"""

import json
from types import SimpleNamespace

import pytest
from scripts.langchain import pr_verifier as verifier

from tests.scripts.test_pr_verifier_file_chunks import Client, patch


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.delenv("VERIFIER_SEMANTIC_MODE", raising=False)
    monkeypatch.delenv("VERIFIER_EVIDENCE_PROFILE", raising=False)
    monkeypatch.setenv("VERIFIER_DIFF_BUDGET_TOKENS", "16000")


class Responses(Client):
    def __init__(self, responses):
        super().__init__()
        self.responses = iter(responses)

    def invoke(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return SimpleNamespace(content=json.dumps(next(self.responses)))


def reply(verdict="PASS", **fields):
    return {"verdict": verdict, "summary": "Assigned code inspected.", **fields}


def run(monkeypatch, responses, paths=None):
    client = Responses(responses)
    monkeypatch.setattr(verifier, "_get_llm_client", lambda **kwargs: (client, "openai"))
    paths = paths or [("a/module.py", 40000), ("b/module.py", 40000)]
    result = verifier.evaluate_pr(
        "Review all requirements.", "".join(patch(p, n) for p, n in paths)
    )
    return result, client


def test_sibling_omissions_do_not_erase_assigned_reviews_or_same_basename(monkeypatch):
    result, client = run(
        monkeypatch,
        [
            reply(files_not_reviewed=["b/module.py"]),
            reply(),
            reply(),
        ],
    )
    assert result.verdict == "PASS"
    assert result.files_not_reviewed == []
    assert result.input_coverage["files_complete"] == 2
    assert result.chunk_reviews[0]["provider_result"]["files_not_reviewed"] == ["b/module.py"]
    assert result.chunk_reviews[0]["sibling_files_not_supplied"] == ["b/module.py"]
    assert len(client.prompts) == 3


def test_assigned_omission_is_not_waived_as_a_sibling(monkeypatch):
    result, client = run(monkeypatch, [reply(files_not_reviewed=["a/module.py"]), reply()])
    assert result.verdict == "UNVERIFIABLE_INPUT"
    assert result.files_not_reviewed == ["a/module.py"]
    assert result.input_coverage["files_complete"] == 1
    assert len(client.prompts) == 2


def test_unknown_provider_omission_remains_a_nonpass_gap(monkeypatch):
    result, client = run(monkeypatch, [reply(files_not_reviewed=["unknown.py"]), reply()])
    assert result.verdict == "UNVERIFIABLE_INPUT"
    assert result.files_not_reviewed == ["unknown.py"]
    assert not result.input_coverage["sufficient"]
    assert len(client.prompts) == 2


def test_operational_uncertainty_does_not_erase_code_review_or_become_pass(monkeypatch):
    result, client = run(
        monkeypatch,
        [
            reply(
                "UNVERIFIABLE_INPUT",
                summary="Code inspected; 24-hour operational proof unavailable.",
                files_reviewed=["a/module.py"],
            ),
            reply(),
            reply(),
        ],
    )
    assert result.input_coverage["files_complete"] == 2
    assert result.files_not_reviewed == []
    assert result.verdict == "UNVERIFIABLE_INPUT"
    assert result.chunk_reviews[0]["provider_result"]["verdict"] == "UNVERIFIABLE_INPUT"
    assert len(client.prompts) == 3


def scoped_concern(verdict="CONCERNS", concrete=False):
    concerns = ["b/module.py is not supplied in this chunk."]
    if concrete:
        concerns.append("Real local correctness defect: invalid zero division.")
    return reply(
        verdict,
        concerns=concerns,
        deferred_concerns=[{"concern_index": 0, "sibling_files": ["b/module.py"]}],
    )


def resolution(**changes):
    return {
        "chunk_index": 0,
        "concern_index": 0,
        "supporting_files": ["b/module.py"],
        "explanation": "The second chunk implements this criterion in b/module.py.",
        **changes,
    }


def test_only_attributed_sibling_concern_is_resolved_real_defect_survives(monkeypatch):
    result, client = run(
        monkeypatch,
        [
            scoped_concern(concrete=True),
            reply(),
            reply(
                "CONCERNS",
                summary="All files reviewed; local correctness defect remains.",
                resolved_chunk_concerns=[resolution()],
            ),
        ],
    )
    assert result.verdict == "CONCERNS"
    assert result.concerns == ["Real local correctness defect: invalid zero division."]
    assert "not supplied" not in result.summary
    assert "not supplied" in result.chunk_reviews[0]["provider_result"]["concerns"][0]
    assert result.input_coverage["files_complete"] == 2
    assert len(client.prompts) == 3


def test_complete_sibling_evidence_can_discharge_only_scoped_concern(monkeypatch):
    result, _ = run(
        monkeypatch, [scoped_concern(), reply(), reply(resolved_chunk_concerns=[resolution()])]
    )
    assert result.verdict == "PASS" and result.concerns == []


@pytest.mark.parametrize(
    "change",
    [
        {"supporting_files": ["a/module.py"]},
        {"supporting_files": ["not-changed.py"]},
        {"chunk_index": 99},
        {"concern_index": 1},
    ],
)
def test_invalid_reconciliation_cannot_erase_original_concern(monkeypatch, change):
    result, _ = run(
        monkeypatch,
        [scoped_concern(), reply(), reply(resolved_chunk_concerns=[resolution(**change)])],
    )
    assert result.verdict == "CONCERNS"
    assert "not supplied" in result.concerns[0]


@pytest.mark.parametrize(
    "local", [reply("CONCERNS", concerns=["Real code defect"]), scoped_concern("FAIL")]
)
def test_synthesis_pass_never_waives_unattributed_or_failed_finding(monkeypatch, local):
    result, _ = run(monkeypatch, [local, reply(), reply(resolved_chunk_concerns=[resolution()])])
    assert result.verdict == local["verdict"]
    assert result.concerns == local["concerns"]
    assert "did not discharge" in result.summary


def test_global_acceptance_gap_survives_complete_local_reviews(monkeypatch):
    result, _ = run(
        monkeypatch,
        [
            reply(),
            reply(),
            reply("CONCERNS", concerns=["Required post-merge duration proof is missing."]),
        ],
    )
    assert result.verdict == "CONCERNS" and result.input_coverage["files_complete"] == 2
    assert result.concerns == ["Required post-merge duration proof is missing."]


def test_synthesis_omission_withholds_pass(monkeypatch):
    result, _ = run(monkeypatch, [reply(), reply(), reply(files_not_reviewed=["b/module.py"])])
    assert result.verdict == "UNVERIFIABLE_INPUT"
    assert result.files_not_reviewed == ["b/module.py"]


def test_703_ten_plus_three_chunk_shape_keeps_all_successful_assigned_reviews(monkeypatch):
    first = [
        (p, 6000)
        for p in [
            ".verify-floor.json",
            "docs/capacity-pacing.md",
            "docs/evidence/issue-668/scheduled-poll-pacing-report.txt",
            "scripts/usage_poll/claude-usage-poll.py",
            "scripts/usage_poll/codex-usage-poll.py",
            "scripts/usage_poll/com.stranske.usage-poll.plist",
            "scripts/usage_poll/usage-poll.sh",
            "scripts/usage_poll/usage_history.py",
            "src/capacity.py",
            "src/pacing.py",
        ]
    ]
    siblings = ["src/pacing_usage.py", "tests/test_pacing.py", "tests/test_usage_poll.py"]
    result, _ = run(
        monkeypatch,
        [reply(files_not_reviewed=siblings), reply(), reply()],
        first + [(p, 10000) for p in siblings],
    )
    assert result.input_coverage["chunks"] == 2
    assert result.input_coverage["files_complete"] == 13
    assert result.files_not_reviewed == []
    assert "files reviewed 13 of 13" in verifier.format_comparison_report([result])


def test_unattested_unverifiable_response_cannot_claim_files_reviewed(monkeypatch):
    result, client = run(
        monkeypatch,
        [reply("UNVERIFIABLE_INPUT", summary="I could not inspect the supplied code."), reply()],
    )
    assert result.input_coverage["files_complete"] == 1
    assert result.files_not_reviewed == ["a/module.py"]
    assert result.verdict == "UNVERIFIABLE_INPUT"
    assert len(client.prompts) == 2


def test_unverifiable_synthesis_cannot_discharge_original_concerns(monkeypatch):
    result, _ = run(
        monkeypatch,
        [
            scoped_concern(),
            reply(),
            reply("UNVERIFIABLE_INPUT", resolved_chunk_concerns=[resolution()]),
        ],
    )
    assert result.verdict == "CONCERNS"
    assert result.concerns == scoped_concern()["concerns"]
    assert result.resolved_chunk_concerns == []


def test_assigned_partial_omission_keeps_other_assigned_review_credit(monkeypatch):
    paths = [("a.py", 20000), ("b.py", 20000), ("c.py", 40000)]
    result, client = run(monkeypatch, [reply(files_not_reviewed=["a.py"]), reply()], paths)
    assert result.verdict == "UNVERIFIABLE_INPUT"
    assert result.files_not_reviewed == ["a.py"]
    assert result.input_coverage["files_complete"] == 2
    assert len(client.prompts) == 2


@pytest.mark.parametrize(
    "case,total,first_count,first_size,last_size",
    [
        ("683", 30, 22, 2000, 2000),
        ("4048", 31, 24, 2000, 2000),
        ("4069", 8, 6, 8000, 8000),
    ],
)
def test_retained_chunk_shapes_reconcile_sibling_context_without_waiving_global_proof(
    monkeypatch, case, total, first_count, first_size, last_size
):
    names = [f"case{case}/file{i}.py" for i in range(total)]
    sibling = names[first_count]
    original = reply(
        "CONCERNS",
        concerns=[
            f"{sibling} is not present in this chunk.",
            "Required operational acceptance proof remains missing.",
        ],
        deferred_concerns=[{"concern_index": 0, "sibling_files": [sibling]}],
    )
    reconciliation = reply(
        "CONCERNS",
        summary="All assigned code reviewed; operational proof remains missing.",
        resolved_chunk_concerns=[resolution(supporting_files=[sibling])],
    )
    paths = [
        (name, first_size if i < first_count else 30000 if i == first_count else last_size)
        for i, name in enumerate(names)
    ]
    result, client = run(monkeypatch, [original, reply(), reconciliation], paths)
    assert result.input_coverage["chunks"] == 2
    assert result.input_coverage["files_complete"] == total
    assert result.verdict == "CONCERNS"
    assert result.concerns == ["Required operational acceptance proof remains missing."]
    assert "not present" not in result.summary
    assert len(client.prompts) == 3


def test_chunk_provenance_and_full_native_requests_remain_bound(monkeypatch):
    import hashlib

    result, client = run(monkeypatch, [reply(), reply(), reply()])
    assert client.root_client.responses.input_tokens.count.call_count == 3
    for record, prompt in zip(result.chunk_reviews, client.prompts, strict=False):
        assert record["prompt_sha256"] == hashlib.sha256(prompt.encode()).hexdigest()
        assert record["prompt_coverage"]["sufficient"] is True
        assert record["assigned_files"][0] in prompt
        assert (
            record["patch_sha256"]
            == hashlib.sha256(patch(record["assigned_files"][0], 40000).encode()).hexdigest()
        )


def test_conflicting_duplicate_attribution_cannot_erase_unproven_sibling_gap(monkeypatch):
    local = scoped_concern()
    local["deferred_concerns"].append({"concern_index": 0, "sibling_files": ["unknown.py"]})
    result, _ = run(monkeypatch, [local, reply(), reply(resolved_chunk_concerns=[resolution()])])
    assert result.verdict == "CONCERNS"
    assert result.concerns == local["concerns"]


def test_blank_resolution_explanation_cannot_discharge_original_concern(monkeypatch):
    result, _ = run(
        monkeypatch,
        [
            scoped_concern(),
            reply(),
            reply(resolved_chunk_concerns=[resolution(explanation=" \t ")]),
        ],
    )
    assert result.verdict == "CONCERNS"
    assert result.concerns == scoped_concern()["concerns"]


@pytest.mark.parametrize(
    "concern",
    [
        "Real local correctness defect: invalid zero division.",
        "a/module.py divides by zero; b/module.py is not supplied.",
        "other-b/module.py is missing.",
    ],
)
def test_attribution_cannot_relabel_unrelated_or_mixed_local_defect(monkeypatch, concern):
    local = scoped_concern()
    local["concerns"] = [concern]
    result, _ = run(monkeypatch, [local, reply(), reply(resolved_chunk_concerns=[resolution()])])
    assert result.verdict == "CONCERNS"
    assert result.concerns == [concern]
    assert result.resolved_chunk_concerns == []
