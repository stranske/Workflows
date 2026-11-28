# Autofix cosmetic-repair sample

`automation_multifailure.py` is a deliberately imperfect module: its aggregate string
uses `",".join`, which the [cosmetic repair](../../../scripts/fix_cosmetic_aggregate.py)
rewrites to `" | ".join`. It is a test input, not production code, and is not imported.

It moved here from `src/trend_analysis/` on 2026-11-28 (round-2 E3), when `src/` was
removed. The four other samples there had no reader and were deleted; the tests that
exercise the autofix pipeline (`tests/workflows/test_autofix_pipeline*.py`,
`tests/scripts/test_fix_cosmetic_aggregate.py`) write their own damaged modules into a
temporary project.

To run the repair against this sample, work in a disposable checkout:

```sh
cd tests/fixtures/autofix
python ../../../scripts/fix_cosmetic_aggregate.py
```
