"""Behavioral tests for ``expanded_comparison_verdict``.

Gate run 42250720123 ranks ``scripts/langchain/pr_verifier.py`` first
(escaped-defect weight 62, churn 75, 273 missing statements and branches).
The largest uncovered statement range in that artifact is this function,
lines 8857–8938. It admits a compare verdict without constructing a client
or calling a provider, so it is the first logical chunk.

Lower-ranked files are not excluded. ``scripts/sync_test_dependencies.py``,
``tools/langchain_client.py``, ``scripts/langchain/task_validator.py``,
``scripts/langchain/verifier_config.py``, and
``scripts/langchain/issue_pr_context.py`` stay in regenerated order for a
later chunk. This module does not treat a missing local receipt as a reason
to skip them.
"""

from __future__ import annotations

import scripts.langchain.pr_verifier as pr_verifier
from tools.llm_registry import SlotDefinition

OPENAI = SlotDefinition(name="slot1", provider="openai", model="gpt-default")
ANTHROPIC = SlotDefinition(name="slot2", provider="anthropic", model="claude-default")
SECOND_OPENAI = SlotDefinition(name="slot2", provider="openai", model="gpt-other")


def _legacy(monkeypatch, slots: list[SlotDefinition] | None = None) -> None:
    monkeypatch.delenv("VERIFIER_SEMANTIC_MODE", raising=False)
    monkeypatch.delenv("LANGCHAIN_MODEL", raising=False)
    chosen = [OPENAI, ANTHROPIC] if slots is None else list(slots)

    def resolve_slots() -> list[SlotDefinition]:
        return list(chosen)

    monkeypatch.setattr("tools.llm_registry.resolve_slots", resolve_slots)


def _arm(provider: str, model: str, verdict: str, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "provider_used": provider,
        "model": model,
        "verdict": verdict,
        "used_llm": True,
    }
    payload.update(extra)
    return payload


def _pair(model1: str = "gpt-default", model2: str = "claude-default", **extra: object) -> dict:
    return {
        "results": [
            _arm("openai", model1, "PASS", **extra),
            _arm("anthropic", model2, "PASS"),
        ]
    }


def _signed(monkeypatch, tmp_path, admission: object, **payload_extra: object) -> dict:
    key = tmp_path / "runner-key"
    key.write_bytes(b"k" * 32)
    monkeypatch.setenv("VERIFIER_SEMANTIC_MODE", "1")
    monkeypatch.setenv("VERIFIER_SEMANTIC_KEY_PATH", str(key))
    envelope = {"schema": pr_verifier.SEMANTIC_ENVELOPE_SCHEMA, "admission": admission}
    envelope["signature"] = pr_verifier._semantic_envelope_signature(envelope)
    return {"semantic_acceptance": envelope, **payload_extra}


def test_semantic_mode_rejects_non_dict_payload(monkeypatch) -> None:
    monkeypatch.setenv("VERIFIER_SEMANTIC_MODE", "1")

    assert pr_verifier.expanded_comparison_verdict(["legacy"]) == "CONCERNS"
    assert pr_verifier.expanded_comparison_verdict(None) == "CONCERNS"
    assert pr_verifier.expanded_comparison_verdict({"results": []}) == "CONCERNS"
    assert (
        pr_verifier.expanded_comparison_verdict(
            {"semantic_acceptance": {"schema": "other", "admission": {"verdict": "PASS"}}}
        )
        == "CONCERNS"
    )


def test_semantic_mode_rejects_a_signature_that_does_not_match(monkeypatch, tmp_path) -> None:
    payload = _signed(monkeypatch, tmp_path, {"verdict": "FAIL"})
    payload["semantic_acceptance"]["signature"] = "0" * 64

    assert pr_verifier.expanded_comparison_verdict(payload) == "CONCERNS"


def test_semantic_mode_rejects_unreadable_or_missing_runner_key(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("VERIFIER_SEMANTIC_MODE", "1")
    envelope = {
        "schema": pr_verifier.SEMANTIC_ENVELOPE_SCHEMA,
        "admission": {"verdict": "FAIL"},
        "signature": "ab",
    }
    monkeypatch.setenv("VERIFIER_SEMANTIC_KEY_PATH", str(tmp_path))

    assert pr_verifier.expanded_comparison_verdict({"semantic_acceptance": envelope}) == "CONCERNS"

    monkeypatch.delenv("VERIFIER_SEMANTIC_KEY_PATH", raising=False)

    assert pr_verifier.expanded_comparison_verdict({"semantic_acceptance": envelope}) == "CONCERNS"


def test_semantic_mode_rejects_signed_envelope_without_admission_verdict(
    monkeypatch, tmp_path
) -> None:
    unsigned_input = _signed(monkeypatch, tmp_path, {"verdict": "UNVERIFIABLE_INPUT"})
    not_a_dict = _signed(monkeypatch, tmp_path, "PASS")

    assert pr_verifier.expanded_comparison_verdict(unsigned_input) == "CONCERNS"
    assert pr_verifier.expanded_comparison_verdict(not_a_dict) == "CONCERNS"


def test_semantic_mode_signed_verdict_ignores_legacy_judge_results(monkeypatch, tmp_path) -> None:
    legacy_pass = [
        _arm("openai", "gpt-default", "PASS"),
        _arm("anthropic", "claude-default", "PASS"),
    ]
    failed = _signed(monkeypatch, tmp_path, {"verdict": "FAIL"}, results=legacy_pass)
    passed = _signed(
        monkeypatch,
        tmp_path,
        {"verdict": "PASS"},
        results=[_arm("openai", "gpt-default", "FAIL")],
    )
    concerns = _signed(monkeypatch, tmp_path, {"verdict": "CONCERNS"})

    assert pr_verifier.expanded_comparison_verdict(failed) == "FAIL"
    assert pr_verifier.expanded_comparison_verdict(passed) == "PASS"
    assert pr_verifier.expanded_comparison_verdict(concerns) == "CONCERNS"


def test_legacy_mode_requires_two_distinct_provider_slots(monkeypatch) -> None:
    payload = _pair()
    _legacy(monkeypatch, [OPENAI])
    assert pr_verifier.expanded_comparison_verdict(payload) == "CONCERNS"

    _legacy(monkeypatch, [OPENAI, SECOND_OPENAI])
    assert pr_verifier.expanded_comparison_verdict(payload) == "CONCERNS"


def test_legacy_mode_rejects_payloads_that_are_not_judge_results(monkeypatch) -> None:
    _legacy(monkeypatch)

    assert pr_verifier.expanded_comparison_verdict("nope") == "CONCERNS"
    assert (
        pr_verifier.expanded_comparison_verdict({"results": {"provider_used": "openai"}})
        == "CONCERNS"
    )
    assert pr_verifier.expanded_comparison_verdict({"semantic_acceptance": {}}) == "CONCERNS"
    assert pr_verifier.expanded_comparison_verdict({"results": []}) == "CONCERNS"


def test_legacy_pass_requires_both_configured_judges(monkeypatch) -> None:
    _legacy(monkeypatch)

    assert pr_verifier.expanded_comparison_verdict(_pair()) == "PASS"
    assert (
        pr_verifier.expanded_comparison_verdict(
            {"results": [_arm("openai", "gpt-default", "PASS")]}
        )
        == "CONCERNS"
    )


def test_configured_fail_survives_a_malformed_sibling(monkeypatch) -> None:
    _legacy(monkeypatch)
    payload = {
        "results": [
            _arm("openai", "gpt-default", "FAIL"),
            "not-a-judge",
            {"provider_used": "anthropic", "model": "claude-default", "verdict": "PASS"},
        ]
    }

    assert pr_verifier.expanded_comparison_verdict(payload) == "FAIL"


def test_unused_or_foreign_judge_cannot_impersonate_a_configured_slot(monkeypatch) -> None:
    _legacy(monkeypatch)
    unused = {
        "results": [
            _arm("openai", "gpt-default", "FAIL", used_llm=False),
            _arm("anthropic", "claude-default", "PASS", used_llm=False),
        ]
    }
    foreign = {
        "results": [
            _arm("github-models", "gpt-default", "FAIL"),
            _arm("anthropic", "claude-default", "PASS"),
        ]
    }
    coerced = {
        "results": [
            _arm("openai", "gpt-default", "FAIL", used_llm=1),
            _arm("anthropic", "claude-default", "PASS", extra_field=True),
        ]
    }

    assert pr_verifier.expanded_comparison_verdict(unused) == "CONCERNS"
    assert pr_verifier.expanded_comparison_verdict(foreign) == "CONCERNS"
    assert pr_verifier.expanded_comparison_verdict(coerced) == "CONCERNS"


def test_concerns_and_judge_errors_block_pass_without_becoming_fail(monkeypatch) -> None:
    _legacy(monkeypatch)
    concerns = {
        "results": [
            _arm("openai", "gpt-default", "PASS"),
            _arm("anthropic", "claude-default", "CONCERNS"),
        ]
    }
    errored = {
        "results": [
            _arm("openai", "gpt-default", "PASS", error="could not parse judge output"),
            _arm("anthropic", "claude-default", "PASS"),
        ]
    }
    duplicate = {
        "results": [
            _arm("openai", "gpt-default", "PASS"),
            _arm("openai", "gpt-default", "PASS"),
        ]
    }

    assert pr_verifier.expanded_comparison_verdict(concerns) == "CONCERNS"
    assert pr_verifier.expanded_comparison_verdict(errored) == "CONCERNS"
    assert pr_verifier.expanded_comparison_verdict(duplicate) == "CONCERNS"


def test_unverifiable_input_requires_both_configured_slots(monkeypatch) -> None:
    _legacy(monkeypatch)
    both = {
        "results": [
            _arm("openai", "gpt-default", "UNVERIFIABLE_INPUT", used_llm=False),
            _arm("anthropic", "claude-default", "UNVERIFIABLE_INPUT", used_llm=False),
        ]
    }
    with_error = {
        "results": [
            _arm("openai", "gpt-default", "UNVERIFIABLE_INPUT", used_llm=False, error="missing"),
            _arm("anthropic", "claude-default", "UNVERIFIABLE_INPUT", used_llm=False),
        ]
    }
    only_one = {"results": [_arm("openai", "gpt-default", "UNVERIFIABLE_INPUT", used_llm=False)]}

    assert pr_verifier.expanded_comparison_verdict(both) == "UNVERIFIABLE_INPUT"
    assert pr_verifier.expanded_comparison_verdict(with_error) == "CONCERNS"
    assert pr_verifier.expanded_comparison_verdict(only_one) == "CONCERNS"


def test_model_overrides_follow_the_slot_client_order(monkeypatch) -> None:
    _legacy(monkeypatch)

    assert (
        pr_verifier.expanded_comparison_verdict(_pair("from-arg", "from-arg"), model1="from-arg")
        == "PASS"
    )
    assert pr_verifier.expanded_comparison_verdict(_pair(), model1="from-arg") == "CONCERNS"
    assert (
        pr_verifier.expanded_comparison_verdict(
            _pair("gpt-default", "second-only"), model2="second-only"
        )
        == "PASS"
    )

    monkeypatch.setenv("LANGCHAIN_MODEL", "from-env")
    assert pr_verifier.expanded_comparison_verdict(_pair("from-env", "claude-default")) == "PASS"
    assert pr_verifier.expanded_comparison_verdict(_pair("from-env", "from-env")) == "CONCERNS"
    assert (
        pr_verifier.expanded_comparison_verdict(
            _pair("explicit", "second"), model1="explicit", model2="second"
        )
        == "PASS"
    )
