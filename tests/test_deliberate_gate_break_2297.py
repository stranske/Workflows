"""DELIBERATE gate-break for #2297 required-check verification.

This test fails on purpose so we can confirm the re-enabled ruleset BLOCKS a
red PR (summary check-run = failure). It must be deleted and its PR closed as
soon as verification completes — do NOT merge.
"""


def test_deliberate_break_for_2297():
    assert False, "deliberate #2297 verification break — delete me"
