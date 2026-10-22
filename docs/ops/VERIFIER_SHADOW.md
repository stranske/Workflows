# Verifier shadow evaluation of candidate judges

Owner decision 2026-10-22: a candidate verifier judge earns promotion by running in **shadow** for at
least 7 days against the production comparison, not by clearing a benchmark. Background and costs:
`docs/ops/VERIFIER_STANDARDS_ANALYSIS.md` (zero-error benchmark bounds approved only a perfect model).

## What runs

* The reusable verifier workflow (`reusable-agents-verifier.yml`, called by every consumer at `@main`)
  has a step after the production comparison: `scripts/langchain/verifier_shadow.py`. For each candidate
  in `config/verifier_shadow.json` it runs the production single-judge code path
  (`pr_verifier.evaluate_pr`) on the **same context and diff** the production judges saw and writes
  `verifier-shadow.json` beside `comparison.json` in the `comparison-results-<run>` artifact.
* The step posts nothing, sets no label or output, uses `continue-on-error`, a 10 minute timeout and a
  per-candidate 300 second timeout; any failure is an `error` field in the record. A candidate that is
  already a production judge on the run is skipped.
* Kill switches: `enabled: false` in the config (central), or the repository variable
  `VERIFIER_SHADOW=off`.
* `maint-89-verifier-shadow-report.yml` runs daily: it collects the records from the fleet's artifacts
  (they expire after 7 days) into a 90-day ledger artifact, applies the criteria and updates one issue,
  "Verifier shadow report". Cost: one extra judge call per verification (about 0.03 cents for
  gpt-6-luna), about 13 verifications a week.

## Pre-registered criteria (committed before any shadow data)

The head-to-head baseline is the production slot with the candidate's provider (the judge it would
replace); the unified production verdict is recorded alongside.

| Criterion | Value |
| --- | --- |
| Window | at least 7 days **and** at least 10 paired runs; at 21 days the result is `INSUFFICIENT AT CAP`, never a pass |
| Coverage | the candidate returns a usable verdict on at least 90% of attempts |
| Candidate misses (candidate PASS, incumbent slot not PASS) | at most max(1, 20% of the incumbent's flags) |
| Extra flags (candidate not PASS, incumbent slot PASS) | at most max(1, 25% of the incumbent's passes, rounded up) |
| Class agreement (PASS against not-PASS) | at least 60% |
| Cost | informational unless both report tokens: at most the incumbent's cost per run |
| Rollback signal | a candidate miss on a PR that later reverts or draws a verifier follow-up ends the evaluation as DOES NOT MEET |

Statuses: `MEETS`, `DOES NOT MEET` (the failing criteria are named, and the misses and extra flags are
listed by PR and run), `INSUFFICIENT` (with the paired runs and days still needed).

**What 7 days can and cannot show.** About 13 verifications a week fleet-wide means 10 to 15 paired runs:
enough to catch a candidate that disagrees with the incumbent often or misses what it flags, not enough
to measure a difference of a few points. The criteria are sized for that: they reject a clearly worse
candidate and accept an indistinguishable one, which is the decision the analysis says is worth making.

## Latched-gate check

1. **What decrements the gate?** Each paired run lowers `runs_still_needed`; time lowers
   `days_still_needed`. Both are printed.
2. **Can that run while the gate is closed?** Yes: shadowing runs on every verification whatever the
   status, and nothing the report says changes what is collected.
3. **Same constant for measuring and draining?** `min_days`, `min_runs` and `max_days` are defined once
   in `config/verifier_shadow.json` and read by the report; the workflow only collects.
4. **What does it print when drained?** `MEETS` with `failed criteria: none` and `still needed: 0
   paired run(s), 0.0 day(s)`; a test pins that output.

## Owner time

One read of the report once it says `MEETS` or `DOES NOT MEET` (about 2 minutes). Nothing waits on the
owner while the shadow runs, and the report issue is a single edited issue, so it cannot accumulate.

## Promotion

Promotion is not automatic. After `MEETS`, a pull request changes the production slot's model in
`config/model_registry.json` and `config/llm_slots.json` and cites the report; the previous model stays
in the registry for a one-line revert. After promotion the same shadow can be pointed at the demoted
model for 14 days as the rollback check.

## Adding or replacing a candidate

Edit `candidates` in `config/verifier_shadow.json`; each candidate's evaluation window starts at the first
record that includes it, so adding one never restarts the others, and criteria changes need their own pull request so they are fixed before data.

## Several candidates at once

All candidates in the config judge every verified PR **in parallel** (one thread each, so the step costs
the slowest candidate's latency, not the sum). Each is scored on its own window against the production
slot of its own provider (openai candidates against gpt-5.6-terra, anthropic against claude-sonnet-5-5),
and the daily report opens with one table row per candidate. Seven are listed today. One failing or
timing-out candidate records its own error and never disturbs the others.

Multiple-comparisons caution: with seven candidates, the chance that at least one meets the criteria by
luck is much higher than for one. Promotion picks, among candidates that MEET, the cheapest; a lone
MEETS among many is not proof of superiority, and the day-21 cap applies to each independently.
