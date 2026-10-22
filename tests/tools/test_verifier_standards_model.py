from __future__ import annotations

from tools import verifier_standards_model as m

NONE = m.Standard("none", 1.0, 0.0, "none")


def _std(fp, ff, mode="hard"):
    return m.Standard("s", fp, ff, mode)


def test_no_verification_costs_exactly_the_escape_of_every_bad_pr():
    cost = m.standard_cost(NONE, bad=0.05, ratio=10)
    assert abs(cost["hours_per_pr"] - 0.05 * 10 * m.PARAMS["c_rework_h"]) < 1e-9
    assert cost["human_min_week"] == 0


def test_a_perfect_verifier_costs_only_the_verification_round_and_the_fixes_it_forces():
    cost = m.standard_cost(_std(0.0, 0.0), bad=0.05, ratio=10)
    assert abs(cost["hours_per_pr"] - (m.PARAMS["t_verify_h"] + 0.05 * m.PARAMS["c_fix_h"])) < 1e-9


def test_rejecting_everything_stalls_every_verified_pr_and_blows_the_human_budget():
    cost = m.standard_cost(_std(0.0, 1.0), bad=0.05, ratio=10)
    assert cost["stalls_per_week"] > 5
    assert cost["human_min_week"] > m.PARAMS["human_budget_min_week"]


def test_a_time_boxed_block_never_costs_the_human_anything():
    cost = m.standard_cost(_std(0.1, 0.5, "timebox"), bad=0.05, ratio=10)
    assert cost["human_min_week"] == 0 and cost["hours_per_pr"] > 0


def test_a_hard_block_costs_more_delay_than_a_time_box_for_the_same_flags():
    box = m.standard_cost(_std(0.0, 0.2, "timebox"), bad=0.05, ratio=10)["hours_per_pr"]
    hard = m.standard_cost(_std(0.0, 0.2, "hard"), bad=0.05, ratio=10)["hours_per_pr"]
    assert hard > box


def test_cost_rises_with_false_flags_and_with_missed_defects():
    base = m.standard_cost(_std(0.1, 0.1), bad=0.05, ratio=10)["hours_per_pr"]
    assert m.standard_cost(_std(0.1, 0.4), bad=0.05, ratio=10)["hours_per_pr"] > base
    assert m.standard_cost(_std(0.5, 0.1), bad=0.05, ratio=10)["hours_per_pr"] > base


def test_less_surviving_detection_makes_verification_worth_less():
    good = m.standard_cost(_std(0.1, 0.1), bad=0.05, ratio=10, realism=1.0)["hours_per_pr"]
    weak = m.standard_cost(_std(0.1, 0.1), bad=0.05, ratio=10, realism=0.25)["hours_per_pr"]
    assert weak > good


def test_breakeven_base_rate_exists_for_a_good_verifier_and_not_for_a_useless_one():
    box = _std(0.1, 0.1, "timebox")
    low, high = m.breakeven_bad_rate(box, ratio=30), m.breakeven_bad_rate(box, ratio=3)
    assert 0 < low < 1 and (high is None or high > low)  # costlier escapes lower the break-even rate
    assert (
        m.breakeven_bad_rate(_std(1.0, 0.0), ratio=10) is None
    )  # catches nothing, still costs a round


def test_markdown_lists_every_standard_and_every_ratio():
    text = m.markdown([_std(0.1, 0.1), m.Standard("other", 0.2, 0.2, "hard")])
    assert "| other |" in text and text.count("Delay-hours per verified PR") == len(m.ESCAPE_RATIOS)
