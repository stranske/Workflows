# Verifier shadow evaluation of candidate judges

Owner decision 2026-10-22: a candidate verifier judge earns promotion by running in **shadow** for at
least 7 days against the production comparison, not by clearing a benchmark. Background and costs:
`docs/ops/VERIFIER_STANDARDS_ANALYSIS.md` (zero-error benchmark bounds approved only a perfect model).

## What runs

* The reusable verifier workflow (`reusable-agents-verifier.yml`, called by every consumer at `@main`)
  has a step after the production comparison: `scripts/langchain/verifier_shadow.py`. For each candidate
  in `config/verifier_shadow.json` it runs the production per-slot code path
  (`ComparisonRunner.run_single`) on the **same context and diff** the production judges saw and writes
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

## How candidates are graded (owner direction 2026-10-28)

The verifier runs two judges from different provider families on purpose and expects them to
disagree; a split is information, not an error. The first version of these criteria graded a
candidate by whether its verdict matched ONE production judge (a candidate PASS where that judge
did not PASS was a "miss", and one miss ended the evaluation). That contradicts the design, and on
the first live data it marked Muse "DOES NOT MEET" after two runs because the openai judge had said
UNVERIFIABLE_INPUT (it could not verify, it found no defect) while the anthropic judge and Muse
both said PASS. Those criteria are withdrawn.

Candidates are now graded on the quality of their **work**, against the production judges' work on
the same runs:

1. `tools/verifier_shadow_adjudicate.py` (a step of the daily job) gives a reasoning model that is
   neither a candidate nor a production judge (`adjudicator` in the config: `claude-fable-5-1`)
   the PR's plan and context, its diff and **every** evaluation of the run, production and
   candidate alike, relabelled A, B, C... in a shuffled order. It lists the tasks and acceptance
   criteria, decides the verdict the evidence best supports, and rates each evaluation:
   * **accuracy**: accurate, partly inaccurate, or inaccurate (verdict unsupported or a
     load-bearing claim wrong). Each error must quote the evaluation's claim and the context or
     diff text that contradicts it; the quotes are checked, and an error whose quotes cannot be
     found is discarded and cannot mark anyone down (the rating becomes `unsupported`);
   * **rigor**: each task and criterion was checked against the diff (1), only asserted (0.5) or
     missed (0);
   * **usefulness** (1-5): specific, evidence-citing, comparable point by point with another
     reviewer's work.
2. `tools/verifier_shadow_report.py` compares each candidate with the production judges on the
   runs where both were rated:

| Criterion | Value |
| --- | --- |
| Window | at least 7 days **and** 10 adjudicated runs; at 21 days `INSUFFICIENT AT CAP`, never a pass |
| Usable evaluations | at least 90% of attempts produce a usable evaluation |
| Inaccuracy | the candidate's inaccurate share is at most 0.10 above the production judges' share on the same runs |
| Rigor | mean task/criteria coverage at most 0.10 below the production judges' |
| Usefulness | mean usefulness at most 0.5 below the production judges' |
| Decisive at any time | the candidate's PASS evaluation is rated inaccurate by the adjudicator on a run where both production judges raised a finding (FAIL or CONCERNS) |
| Listed, never graded alone | a candidate PASS rated accurate on a run where both production judges raised a finding; a candidate finding where both production judges passed |

The four margins were set in this change, after two runs that had no adjudication and before any
adjudication data. UNVERIFIABLE_INPUT is not a finding. The production judges are rated by the same
adjudicator, so the report also says how often THEY are inaccurate, for example how many of their
UNVERIFIABLE_INPUT verdicts the evidence supported.

**Bias controls and limits.** The adjudicator shares a provider family with the production
anthropic judge and two candidates; blinding and the side-by-side incumbent ratings are the
control (a family preference would show as a gap the incumbents share). One adjudicator is one
reader: its ratings are a real trial on live work, not a ground truth.

**Cost.** About 25k input tokens per run (the context dominates), roughly $0.30-0.60 per run at
the registry list price, at most 20 runs a day, typically 2-4.

## Latched-gate check

1. **What decrements the gate?** Each adjudicated run lowers `runs_still_needed`; time lowers
   `days_still_needed`. Both are printed.
2. **Can that run while the gate is closed?** Yes: shadowing runs on every verification whatever the
   status, and nothing the report says changes what is collected.
3. **Same constant for measuring and draining?** `min_days`, `min_runs` and `max_days` are defined once
   in `config/verifier_shadow.json` and read by the report; the workflow only collects.
4. **What does it print when drained?** `MEETS` with `failed criteria: none` and `still needed: 0
   adjudicated run(s), 0.0 day(s)`; a test pins that output.

5. **Adjudication gate** (`needs_adjudication`). What drains it: a run is adjudicated once every
   candidate has an evaluation, or when it is `SETTLE_DAYS` (6) old, so a candidate that never
   answers cannot hold a run past its artifact's 7-day life. A failed adjudication is retried once
   (`MAX_ATTEMPTS` 2). It reports `adjudicated`, `failed`, `capped`, `out_of_time`, `unusable` and
   `skipped_private` each day; runs skipped for time or the cap are picked up the next day. Fully
   drained prints `adjudicated: 0` with every other count 0.

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

## Candidate choice and external candidates

Only the newest model of each line is shadowed (gpt-6.1-sol, not gpt-6-sol or gpt-5.6; claude-opus-5-5,
not opus-5; no Anthropic model older than the production claude-sonnet-5-5; gpt-6-luna stays because no
6.1 luna exists).

Muse (`muse-api`, muse-spark-1.3, own pay-as-you-go key, non-contributor tier) and Cursor (`cursor-cli`,
read-only ask mode) are `runner: external` candidates. Consumer workflows hold no credential for them,
so they cannot judge inside a verification run. Instead the daily report job
(`tools/verifier_shadow_external.py`) replays each fresh run's saved context and diff (the
`comparison-results-*` artifact, 7-day retention) through the same production prompt and appends the
verdict to that run's ledger record. They are scored by the same criteria; their baseline is the
production OpenAI judge. Bounds: public repositories only, at most 25 new pull requests judged per daily
run, one request per candidate per run (never repeated). Limits: the replay uses chain depth 0 and the
Cursor/Muse harness differs from the LangChain one, so a MEETS here is a screen-grade result for a
different harness, not proof the model would behave identically inside the production verifier.

## Correction 2026-10-27: candidates now run the production path

The first nine shadow records were discarded. In-workflow candidates were judged through
`pr_verifier.evaluate_pr`, whose lenient coverage rule (`evaluate_minimum=True`) production does not use,
so candidates answered an easier question than the incumbent: the production OpenAI judge returned
UNVERIFIABLE_INPUT on 7 of 9 runs while every candidate returned PASS, and the report scored that
disagreement as candidate "misses". Candidates now run `ComparisonRunner.run_single`, the exact per-slot
production path (strict coverage, chunked review, coverage floor), and each entry records its
`pipeline`; the report ignores entries without an accepted pipeline tag. A second fault: haiku and opus
returned "Failed to parse JSON" on every run, which was recorded as a CONCERNS verdict. An entry with an
error is now a failed attempt (it lowers coverage) and never a verdict. Candidate windows restart.

Muse and Cursor now take the same path: `tools/verifier_shadow_external.py` wraps each judge so it
answers `invoke(prompt)` and runs it through `ComparisonRunner.run_single`, with the same chunking,
response parsing and coverage floor. The one difference is the pre-flight input-size check, which
production restricts to OpenAI, Anthropic and GitHub Models clients and fails closed on anything else;
it is skipped for these two in the report job only (each entry records `capacity_preflight: skipped`).
Entries with an error keep a 400-character `raw_excerpt` of the model's answer.

## Review fixes 2026-10-28

- **Dependencies.** The daily job installs `tools/requirements-llm.txt`, the file the production
  verifier installs, before any run is replayed.
- **One run per PR.** A PR is verified again on every push. The external judges take one run per
  repository and PR: the one already judged, otherwise the newest, so a later push never causes a
  second paid judgment and the PR is counted once.
- **Time budget.** One run can make several sequential judge calls (production chunks a large
  input). Each run gets `RUN_BUDGET_SECONDS` (two judge timeouts plus a minute, derived from the one
  `JUDGE_TIMEOUT_SECONDS`), and the judge client refuses any call that could not finish inside it.
  `--budget-seconds` (1620) starts a run only if that whole budget still fits; the step has a
  30-minute timeout and the job 45. The ledger is rewritten atomically after every judged run, the
  step is `continue-on-error`, and the report step runs after it unless the job was cancelled.
  Drain check: a run skipped for time is counted as `out_of_time` and is picked up by the next
  daily job.
- **Semantic runs.** Records carry `semantic_mode` (the expanded profile). Production judges those
  with the semantic package matrix, which the per-slot candidate path does not reproduce, so they
  are neither replayed nor paired.
