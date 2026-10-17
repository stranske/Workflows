import json

from tools import agy_pilot
from tools.agy_pilot import ModelCall, Target

SOURCE = "def gap(a, b):\n" "    if a == b:\n" "        return 0\n" "    return a - b\n"
TESTS = (
    "from tools import clamp_mod\n"
    "def test_gap():\n"
    "    assert clamp_mod.gap(2, 2) == 0\n"
    "    assert clamp_mod.gap(5, 3) == 2\n"
    "    assert clamp_mod.gap(3, 5) == -2\n"
)


def _target():
    mutants = agy_pilot.validated_mutants("clamp_mod", SOURCE, TESTS, 3, seed=1)
    return Target("clamp_mod", SOURCE, None, mutants)


def test_candidates_skip_strings_headers_and_comments():
    src = 'def f(a, b):\n    # a < b\n    s = "a == b"\n    return a < b\n'
    lines = {m.line for m in agy_pilot.candidate_mutants(src)}
    assert lines == {4}


def test_only_mutants_the_modules_own_tests_fail_on_are_kept():
    target = _target()
    assert target.mutants, "gap has behavioural mutants"
    for m in target.mutants:
        assert not agy_pilot._run_pytest("clamp_mod", m.source, TESTS)
    assert (
        agy_pilot.validated_mutants("clamp_mod", SOURCE, "def test_x():\n    assert False\n", 3, 1)
        == []
    )


def test_audit_scores_recall_precision_and_resolving_citations():
    target = _target()
    seeded = [m.line for m in target.mutants]
    findings = [
        {"module": "clamp_mod", "line": seeded[0], "issue": "x"},
        {"module": "clamp_mod", "line": 999, "issue": "bogus"},
    ]
    row = agy_pilot.score_audit(findings, target)
    assert (
        row["found"] == 1 and row["reported"] == 2 and row["useful"] == 1 and row["resolving"] == 1
    )
    assert agy_pilot.score_audit([{"module": "other", "line": seeded[0]}], target)["found"] == 0


def test_testgen_requires_clean_pass_then_counts_kills():
    target = _target()
    good = agy_pilot.score_testgen(TESTS, target)
    assert good["clean_pass"] and good["killed"] == len(target.mutants)
    failing = agy_pilot.score_testgen(
        "from tools import clamp_mod\ndef test_x():\n    assert clamp_mod.gap(5, 3) == 99\n", target
    )
    assert failing == {"mutants": len(target.mutants), "killed": 0, "clean_pass": False}
    assert agy_pilot.score_testgen("", target)["killed"] == 0


def test_single_and_batched_modes_make_the_expected_number_of_calls_and_empty_is_unusable():
    targets = [_target(), Target("clamp_two", SOURCE, None, _target().mutants)]
    prompts = []

    def backend(prompt):
        prompts.append(prompt)
        return ModelCall(text=json.dumps({"findings": []}), tokens_in=100, tokens_out=10)

    single = agy_pilot.run_pilot(backend, targets, "audit", "single", 4)
    batched = agy_pilot.run_pilot(backend, targets, "audit", "batched", 4)
    assert (single["calls"], batched["calls"]) == (2, 1)
    assert single["tokens_per_item"] == 110 and batched["tokens_per_item"] == 55
    assert single["totals"]["recall"] == 0.0

    empty = agy_pilot.run_pilot(
        lambda p: ModelCall(text="", error="agy returned an empty response"),
        targets,
        "testgen",
        "batched",
        4,
    )
    assert empty["empty_or_unusable"] == 2 and empty["totals"]["kill_rate"] == 0.0


def test_unreported_tokens_stay_none_not_zero():
    result = agy_pilot.run_pilot(lambda p: ModelCall(text="{}"), [_target()], "audit", "single", 1)
    assert result["tokens_per_item"] is None and result["tokens_in"] is None
